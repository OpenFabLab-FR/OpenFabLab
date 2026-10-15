"""Durable Discord outbox with opt-in presentation. I/O is post-commit.

Discord has no idempotency API. An ambiguous send or crashed claim is retained
as uncertain and is never automatically retransmitted, preventing duplicates.
"""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

LABELS = {
    'new_booking':'Nouvelle réservation enregistrée',
    'waitlist_entry':'Nouvelle entrée en liste d’attente',
    'cancellation':'Réservation annulée',
    'offer_proposed':'Place proposée',
    'offer_accepted':'Place acceptée',
    'link_review':'Rattachement à vérifier',
    'animation_full':'Animation complète',
    'waitlist_full':'Liste d’attente complète',
    'email_error':'Erreur d’envoi d’un e-mail de réservation',
    'sync_error':'Synchronisation WordPress momentanément indisponible',
}
KINDS = {'confirmed':'new_booking','waitlisted':'waitlist_entry','cancelled':'cancellation',
         'offer_pending':'offer_proposed','accepted':'offer_accepted'}
DETAILS={'title':('Titre de l’animation','1'),'date':('Date et horaires','1'),
         'first_name':('Prénom du réservant','0'),'last_name':('Nom complet du réservant','0'),
         'last_initial':('Initiale du nom (si nom complet désactivé)','0'),
         'participants':('Nombre de participants','1'),'remaining':('Places restantes','1')}
MESSAGE_KINDS=tuple(kind for kind in LABELS if kind not in ('email_error','sync_error'))


def presentation(db):
    return dict(details={key:setting(db,'discord_reservation_detail_'+key,default)=='1' for key,(_,default) in DETAILS.items()},
                messages={key:setting(db,'discord_reservation_message_'+key,LABELS[key]) for key in MESSAGE_KINDS})


def validate_label(value,kind):
    value=str(value or '').strip() or LABELS[kind]
    if len(value)>150 or any(ord(c)<32 for c in value) or any(c in value for c in '{}@') or re.search(r'https?://|www\.',value,re.I):
        raise ValueError('Le texte principal est limité à 150 caractères, sans variable, lien ni mention Discord.')
    return value


def plain(value,maximum=180):
    value=re.sub(r'https?://\S+|www\.\S+|[^\s@]+@[^\s@]+', '', str(value or ''), flags=re.I)
    value=re.sub(r'[\x00-\x1f\x7f@]', ' ',value)
    return ' '.join(value.split())[:maximum].replace('*','\\*').replace('_','\\_').replace('~','\\~').replace('`','\\`')


def ensure_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS reservation_discord_events (
        event_key TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        service_id INTEGER REFERENCES fablab_services(id) ON DELETE SET NULL,
        environment TEXT NOT NULL,
        created_at TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending',
        claimed_at TEXT, finished_at TEXT, last_error TEXT)''')
    db.execute('CREATE INDEX IF NOT EXISTS reservation_discord_pending ON reservation_discord_events(state,created_at)')


def setting(db,key,default=''):
    row=db.execute('SELECT value FROM app_settings WHERE key=?',(key,)).fetchone()
    return row[0] if row else default


def queue(db,key,kind,service_id=None,environment='production',now=None,presentation=None):
    """No commits, no personal payload: share the caller's business transaction."""
    if kind not in LABELS or environment not in ('production','test'):
        raise ValueError('Événement de réservation invalide.')
    enabled=(environment=='production' and setting(db,'module_discord','1')=='1'
             and setting(db,'discord_notifications_enabled','0')=='1'
             and setting(db,'discord_reservation_'+kind,'1')=='1')
    db.execute('''INSERT OR IGNORE INTO reservation_discord_events
        (event_key,event_type,service_id,environment,created_at,state) VALUES(?,?,?,?,?,?)''',
        (hashlib.sha256(str(key).encode()).hexdigest(),kind,service_id,environment,
         (now or datetime.now(timezone.utc)).isoformat(),'pending' if enabled else 'skipped'))
    if presentation is not None:
        allowed={'capacity','occupied','confirmed','waiting','waiting_limit'}
        if set(presentation)!=allowed or any(type(value) is not int or not 0<=value<=100000 for value in presentation.values()):
            raise ValueError('Instantané technique de disponibilité invalide.')
        db.execute("UPDATE reservation_discord_events SET presentation_json=? WHERE event_key=? AND presentation_json='{}'",
            (json.dumps(presentation,separators=(',',':')),hashlib.sha256(str(key).encode()).hexdigest()))


def booking_event(db,group,kind,revision,notice=None):
    row=db.execute('SELECT service_id,environment,slot_uuid FROM family_booking_groups WHERE group_uuid=?',(group,)).fetchone()
    if not row:
        return
    flag='cancellation' if kind=='modified' and (notice or {}).get('cancelled_participants') else KINDS.get(kind)
    if flag:
        queue(db,'booking/'+group+'/'+kind+'/'+str(revision),flag,row['service_id'],row['environment'])
    if kind in ('confirmed','offer_pending'):
        from family_reservations import effective_service
        from reservations_sync import booking_capacity_used
        try:
            service=effective_service(db,row['service_id'],row['slot_uuid'],row['environment'],False)
            full=service['capacity']>0 and booking_capacity_used(db,row['service_id'],row['slot_uuid'])>=service['capacity']
        except ValueError:
            full=False
        if full:
            queue(db,'full/'+group+'/'+kind+'/'+str(revision),'animation_full',row['service_id'],row['environment'])


def sync_episode(db,environment,channel,failed):
    """One error notice per uninterrupted failed episode and transport channel."""
    key='reservation_discord_sync_'+environment+'_'+channel
    state=json.loads(setting(db,key,'{"active":false,"sequence":0}'))
    if failed and not state['active']:
        state={'active':True,'sequence':state['sequence']+1}
        queue(db,key+'/'+str(state['sequence']),'sync_error',environment=environment)
    elif not failed and state['active']:
        state['active']=False
    else:
        return
    db.execute('INSERT INTO app_settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
               (key,json.dumps(state,separators=(',',':'))))


def email_snapshot(db,row):
    """Resolve the unchanged hashed outbox key from existing durable mail data.

    No new table/column, personal log or copied identity. Never return the mail
    token/recipient/management URL to the renderer; expose a narrow allowlist.
    """
    if row['service_id'] is None or row['event_type'] in ('email_error','sync_error','link_review','waitlist_full'):
        return {}
    prefix='full/' if row['event_type']=='animation_full' else 'booking/'
    rows=db.execute('''SELECT e.event_key,e.payload_json,g.group_uuid,g.owner_id,g.slot_uuid,g.environment
        FROM family_booking_emails e JOIN family_booking_groups g USING(group_uuid)
        WHERE g.service_id=? ORDER BY e.created_at DESC''',(row['service_id'],))
    for record in rows:
        payload=json.loads(record['payload_json']);event=payload.get('event')
        key=prefix+record['group_uuid']+'/'+str(event)+'/'+record['event_key'].rsplit('/',1)[-1]
        if hashlib.sha256(key.encode()).hexdigest()!=row['event_key']:
            continue
        info={key:payload.get(key) for key in ('title','date','hours','count')}
        info.update(group=record['group_uuid'],owner=record['owner_id'],slot=record['slot_uuid'],environment=record['environment'],notice=payload.get('_discord',{}))
        return info
    return {}


def readable_date(value,hours):
    from usability import MONTHS
    try:
        day=datetime.fromisoformat(str(value)).date()
    except (ValueError,TypeError):
        return ''
    result=f'{day.day} {MONTHS[day.month-1]} {day.year}'
    parts=str(hours or '').split('–')
    def hour(value):
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',value):return ''
        h,m=map(int,value.split(':'));return str(h)+'h'+(f'{m:02d}' if m else '')
    if len(parts)==2 and all(hour(part) for part in parts):
        result+=', de '+hour(parts[0])+' à '+hour(parts[1])
    return result


def message(db,row):
    kind=row['event_type'];options=presentation(db);details=options['details']
    # Technical/global notices never identify a person, regardless of settings.
    if kind in ('email_error','sync_error'):
        return LABELS[kind]
    text=plain(options['messages'].get(kind,LABELS[kind]),150) or LABELS[kind]
    info=email_snapshot(db,row);notice=info.get('notice') or {}
    if kind=='cancellation' and notice.get('partial'):
        text+=' — annulation partielle'
    lines=[text]
    service=db.execute('SELECT title,service_date,start_time,end_time FROM fablab_services WHERE id=?',(row['service_id'],)).fetchone() if row['service_id'] is not None else None
    title=info.get('title') or (service['title'] if service else '')
    if details['title'] and plain(title):lines.append('Animation : '+plain(title))
    date=info.get('date') or (service['service_date'] if service else '')
    hours=info.get('hours') or ((service['start_time'] or '')+'–'+(service['end_time'] or '') if service else '')
    if details['date'] and readable_date(date,hours):lines.append('Date : '+readable_date(date,hours))
    if kind=='waitlist_full':
        snapshot=json.loads(dict(row).get('presentation_json','{}'))
        if details['participants'] and type(snapshot.get('confirmed')) is int and type(snapshot.get('capacity')) is int:
            lines.append('Participants confirmés : '+str(snapshot['confirmed'])+'/'+str(snapshot['capacity']))
            if snapshot.get('occupied',0)>snapshot['confirmed']:
                lines.append('Places proposées : '+str(snapshot['occupied']-snapshot['confirmed']))
        if details['remaining'] and type(snapshot.get('waiting')) is int and type(snapshot.get('waiting_limit')) is int:
            lines.append('Liste d’attente : '+str(snapshot['waiting'])+'/'+str(snapshot['waiting_limit']))
        lines.append('Les nouvelles inscriptions en attente sont closes.')
        return '\n'.join(lines)
    if info and kind!='animation_full' and any(details[key] for key in ('first_name','last_name','last_initial')):
        owner=db.execute('SELECT first_name,last_name FROM users WHERE id=?',(info['owner'],)).fetchone() if info['owner'] is not None else None
        if owner is None and info['owner'] is None:
            # Anonymous one-person requests only; never infer from matching names.
            from family_reservations import GUEST_SOURCE
            people=db.execute('SELECT first_name,last_name FROM animation_bookings WHERE group_uuid=? AND source=?',(info['group'],GUEST_SOURCE)).fetchall()
            if len(people)==1:owner=people[0]
        if owner:
            first=plain(owner['first_name'],60) if details['first_name'] else ''
            last=plain(owner['last_name'],80) if details['last_name'] else (plain(owner['last_name'],1)+'.' if details['last_initial'] and owner['last_name'] else '')
            name=' '.join(part for part in (first,last) if part)
            if name:lines.append('Réservant : '+name)
    if details['participants'] and kind!='animation_full':
        count=notice.get('participants',info.get('count'))
        if type(count) is int and count>0:lines.append('Participants concernés : '+str(count) if kind=='cancellation' else 'Participants : '+str(count))
        released=notice.get('released')
        if kind=='cancellation' and type(released) is int and released>=0:lines.append('Places libérées : '+str(released))
    if details['remaining'] and service:
        try:
            from family_reservations import effective_service
            from reservations_sync import booking_capacity_used
            current=effective_service(db,row['service_id'],info.get('slot'),info.get('environment','production'),False)
            capacity=current['capacity'];used=booking_capacity_used(db,row['service_id'],info.get('slot'))
            if capacity>0:
                if kind=='animation_full':
                    maximum=notice.get('capacity');occupied=notice.get('occupied')
                    if type(maximum) is int and maximum>0 and type(occupied) is int and occupied>=maximum:
                        lines.append('Capacité atteinte : '+str(occupied)+'/'+str(maximum))
                else:
                    lines.append('Places restantes : '+str(max(0,capacity-used)))
        except ValueError:
            pass
    return '\n'.join(lines)


def deliver(db,database_path,sender=None,now=None):
    if db.in_transaction:
        return 0
    if setting(db,'module_discord','1')!='1' or setting(db,'discord_notifications_enabled','0')!='1':
        return 0
    if sender is None:
        from runtime_policy import external_allowed
        if not external_allowed(database_path):
            return 0
        from app import read_discord_webhook,post_discord_message
        webhook=read_discord_webhook()
        if not webhook:
            return 0
        sender=lambda text:post_discord_message(webhook,text,setting(db,'discord_bot_name','OpenFabLab'))
    now=now or datetime.now(timezone.utc)
    with db:
        db.execute("UPDATE reservation_discord_events SET state='uncertain',last_error='InterruptedDelivery' WHERE state='sending' AND claimed_at<?",((now-timedelta(minutes=10)).isoformat(),))
    sent=0
    for event in db.execute("SELECT event_key FROM reservation_discord_events WHERE state='pending' AND environment='production' ORDER BY created_at,event_key LIMIT 30").fetchall():
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM reservation_discord_events WHERE event_key=?',(event[0],)).fetchone()
        if row['state']!='pending':
            db.commit();continue
        enabled=(setting(db,'module_discord','1')=='1' and setting(db,'discord_notifications_enabled','0')=='1'
                 and setting(db,'discord_reservation_'+row['event_type'],'1')=='1')
        db.execute('UPDATE reservation_discord_events SET state=?,claimed_at=? WHERE event_key=?',
                   ('sending' if enabled else 'skipped',now.isoformat(),event[0]))
        db.commit()
        if not enabled:
            continue
        try:
            sender(message(db,row))
        except Exception as error:
            with db:
                db.execute("UPDATE reservation_discord_events SET state='uncertain',last_error=?,finished_at=? WHERE event_key=?",(type(error).__name__,now.isoformat(),event[0]))
        else:
            with db:
                db.execute("UPDATE reservation_discord_events SET state='sent',finished_at=?,last_error=NULL WHERE event_key=?",(now.isoformat(),event[0]))
            sent+=1
    return sent
