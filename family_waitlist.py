"""Atomic family waitlist and durable native mail, shared by every channel.

Only new family requests are managed here. Historical animation rows are never
adopted, converted or purged. Network delivery always happens after commit.
"""
import hashlib
import html
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

import family_model as family

TERMINAL = ('cancelled', 'expired', 'declined')
LABELS = {'confirmed':'Confirmée', 'waitlisted':'En attente',
          'offer_pending':'Place proposée', 'expired':'Expirée',
          'declined':'Refusée', 'cancelled':'Annulée'}


def utcnow():
    return datetime.now(timezone.utc)


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def ensure_schema(db):
    """Called inside the additive migration transaction, including old candidates."""
    db.execute('''CREATE TABLE IF NOT EXISTS family_booking_groups (
        group_uuid TEXT PRIMARY KEY REFERENCES family_booking_requests(group_uuid) ON DELETE CASCADE,
        service_id INTEGER NOT NULL REFERENCES fablab_services(id),
        owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        slot_uuid TEXT, environment TEXT NOT NULL,
        contact_email TEXT NOT NULL, contact_phone TEXT,
        status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        offer_expires_at TEXT, offer_token_hash TEXT, manage_token TEXT NOT NULL,
        manage_token_hash TEXT NOT NULL UNIQUE, revision INTEGER NOT NULL DEFAULT 0)''')
    db.execute('CREATE INDEX IF NOT EXISTS family_queue_order ON family_booking_groups(service_id,slot_uuid,status,created_at)')
    db.execute('''CREATE TABLE IF NOT EXISTS family_booking_history (
        id INTEGER PRIMARY KEY, group_uuid TEXT NOT NULL REFERENCES family_booking_groups(group_uuid) ON DELETE CASCADE,
        status TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS family_booking_emails (
        message_uuid TEXT PRIMARY KEY, group_uuid TEXT NOT NULL REFERENCES family_booking_groups(group_uuid) ON DELETE CASCADE,
        event_key TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, recipient TEXT NOT NULL,
        payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt_at TEXT, claimed_at TEXT, sent_at TEXT, last_error TEXT)''')
    db.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('reservation_phone_required','0')")
    db.execute("INSERT OR IGNORE INTO app_settings(key,value) VALUES('reservation_public_url','')")


def valid_email(value):
    from welcome_mail import EMAIL
    if not (isinstance(value,str) and len(value)<=254 and EMAIL.fullmatch(value)
            and not any(ord(c)<32 for c in value)):
        return False
    from email.headerregistry import Address
    try:
        address=Address(addr_spec=value)
        return bool(address.username and address.domain)
    except (ValueError,IndexError):
        return False


def valid_phone(value):
    return bool(isinstance(value,str) and re.fullmatch(r'[+\d\s().-]+',value)
                and 8<=len(re.sub(r'\D','',value))<=15)


def contact(db, owner_id, people=()):
    """Resolve one notification contact; never copy a parent's details to a child."""
    owner=db.execute('SELECT * FROM users WHERE id=? AND active=1',(owner_id,)).fetchone()
    if not owner:
        raise ValueError('Le compte responsable de la demande est indisponible.')
    candidates=[dict(owner)]
    if family.state(db,owner) in ('dependent','autonomous'):
        candidates.extend(dict(r) for r in family.responsibles(db,owner_id) if family.eligible(db,r))
    phone_required=family.setting(db,'reservation_phone_required','0')=='1'
    for person in candidates:
        if valid_email(person.get('email')) and (not phone_required or valid_phone(person.get('phone'))):
            return {'user_id':person['id'],'email':person['email'].strip(),
                    'phone':person.get('phone') or '', 'name':person['first_name']+' '+person['last_name']}
    return None


def require_contact(db, owner_id, people=()):
    value=contact(db,owner_id,people)
    if not value:
        suffix=' et un téléphone valide' if family.setting(db,'reservation_phone_required','0')=='1' else ''
        raise ValueError('Pour réserver une animation, renseignez un e-mail valide'+suffix+'. Pour un enfant, les coordonnées d’un responsable rattaché peuvent être utilisées.')
    return value


def export_contact(db, booking):
    """Private team exports use the same group contact as administration.

    Historical rows remain unchanged. No contact is copied into a child's
    account or exposed by the public catalogue.
    """
    value=dict(booking)
    if value['source'].startswith('family_'):
        meta=db.execute('SELECT contact_email,contact_phone FROM family_booking_groups WHERE group_uuid=?',(value['group_uuid'],)).fetchone()
        if meta:
            value.update(email=meta['contact_email'],phone=meta['contact_phone'])
    return value


def complete_contact(db, owner_id, email, phone=None):
    """The identified person may edit only their own contact, not their family."""
    if not valid_email(email):
        raise ValueError('Renseignez une adresse e-mail valide.')
    owner=db.execute('SELECT * FROM users WHERE id=? AND active=1',(owner_id,)).fetchone()
    if not owner:
        raise ValueError('Compte indisponible.')
    number=owner['phone'] if phone is None else str(phone).strip()
    if number and not valid_phone(number):
        raise ValueError('Renseignez un téléphone valide.')
    if family.setting(db,'reservation_phone_required','0')=='1' and not valid_phone(number):
        raise ValueError('Un téléphone valide est nécessaire pour réserver.')
    from outbound_actions import transaction
    with transaction(db):
        db.execute('UPDATE users SET email=?,phone=?,updated_at=? WHERE id=?',
                   (email.strip(),number or None,family.timestamp(),owner_id))


def _active(db, group):
    return db.execute("SELECT * FROM animation_bookings WHERE group_uuid=? AND status NOT IN('cancelled','expired','declined') ORDER BY rowid",(group,)).fetchall()


def _queue(db, group, kind, offer_token=None, now=None, people=None):
    now=now or utcnow()
    row=db.execute('SELECT g.*,s.title,s.service_date,s.start_time,s.end_time FROM family_booking_groups g JOIN fablab_services s ON s.id=g.service_id WHERE group_uuid=?',(group,)).fetchone()
    people=_active(db,group) if people is None else people
    if not people:
        people=db.execute('SELECT first_name,last_name FROM animation_bookings WHERE group_uuid=? ORDER BY rowid',(group,)).fetchall()
    payload={'title':row['title'],'date':row['service_date'],'hours':(row['start_time'] or '')+'–'+(row['end_time'] or ''),
             'participants':[p['first_name']+' '+p['last_name'] for p in people],
             'count':len(people),'token':offer_token or row['manage_token'], 'expires':row['offer_expires_at'],
             'status':row['status'], 'timezone':family.setting(db,'structure_timezone','Europe/Paris')}
    slot=db.execute('SELECT starts_at,ends_at FROM animation_slots WHERE slot_uuid=?',(row['slot_uuid'],)).fetchone() if row['slot_uuid'] else None
    if slot:
        zone=ZoneInfo(payload['timezone'])
        start=datetime.fromisoformat(slot['starts_at']).astimezone(zone)
        end=datetime.fromisoformat(slot['ends_at']).astimezone(zone)
        payload.update(date=start.date().isoformat(),hours=start.strftime('%H:%M')+'–'+end.strftime('%H:%M'))
    db.execute('''INSERT OR IGNORE INTO family_booking_emails(message_uuid,group_uuid,event_key,kind,recipient,payload_json,created_at)
        VALUES(?,?,?,?,?,?,?)''',(str(uuid4()),group,group+'/'+kind+'/'+str(row['revision']),kind,row['contact_email'],json.dumps(payload,ensure_ascii=False),now.isoformat()))


def create_group(db, group, owner_id, service_id, slot, environment, status, details, now=None):
    now=now or utcnow();token=secrets.token_urlsafe(32)
    db.execute('''INSERT INTO family_booking_groups(group_uuid,service_id,owner_id,slot_uuid,environment,contact_email,
        contact_phone,status,created_at,updated_at,manage_token,manage_token_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
        (group,service_id,owner_id,slot or None,environment,details['email'],details['phone'],status,
         now.isoformat(),now.isoformat(),token,digest(token)))
    db.execute('INSERT INTO family_booking_history(group_uuid,status,actor,created_at) VALUES(?,?,?,?)',(group,status,'reservation',now.isoformat()))
    _queue(db,group,status,now=now)


def adopt_candidates(db):
    """Resume earlier local 2.8 requests only. Never reinterpret 2.7 history."""
    rows=db.execute('SELECT r.*,b.service_id,b.slot_uuid,b.environment,b.status FROM family_booking_requests r JOIN animation_bookings b USING(group_uuid) LEFT JOIN family_booking_groups g USING(group_uuid) WHERE g.group_uuid IS NULL AND b.source LIKE ? GROUP BY r.group_uuid ORDER BY r.created_at,r.rowid',('family_%',)).fetchall()
    for row in rows:
        details=contact(db,row['owner_id']) if row['owner_id'] else None
        states={r[0] for r in db.execute("SELECT status FROM animation_bookings WHERE group_uuid=? AND status NOT IN('cancelled','expired','declined')",(row['group_uuid'],))}
        if details and len(states)==1:
            create_group(db,row['group_uuid'],row['owner_id'],row['service_id'],row['slot_uuid'],row['environment'],next(iter(states)),details)
            # Original chronology, not the adoption date.
            db.execute('UPDATE family_booking_groups SET created_at=? WHERE group_uuid=?',(row['created_at'],row['group_uuid']))


def transition(db, group, status, actor, now=None, notify=True):
    now=now or utcnow()
    current=db.execute('SELECT status FROM family_booking_groups WHERE group_uuid=?',(group,)).fetchone()
    if not current or current['status']==status:
        return
    before=_active(db,group)
    db.execute('UPDATE family_booking_groups SET status=?,updated_at=?,revision=revision+1 WHERE group_uuid=?',(status,now.isoformat(),group))
    db.execute("UPDATE animation_bookings SET status=?,updated_at=?,is_present=CASE WHEN ? IN('cancelled','expired','declined') THEN 0 ELSE is_present END WHERE group_uuid=? AND status NOT IN('cancelled','expired','declined')",(status,now.isoformat(),status,group))
    db.execute('INSERT INTO family_booking_history(group_uuid,status,actor,created_at) VALUES(?,?,?,?)',(group,status,actor,now.isoformat()))
    # A proposal supersedes its still-unsent waitlist notice. No stale proposal
    # may be sent after acceptance, cancellation or expiry.
    if status!='offer_pending':
        db.execute("UPDATE family_booking_emails SET state='superseded' WHERE group_uuid=? AND kind='offer_pending' AND state='pending'",(group,))
    if notify:
        _queue(db,group,status,now=now,people=before)


def _cutoff(db, service, slot=None):
    zone=ZoneInfo(family.setting(db,'structure_timezone','Europe/Paris'))
    if slot:
        row=db.execute('SELECT starts_at FROM animation_slots WHERE slot_uuid=?',(slot,)).fetchone()
        start=datetime.fromisoformat(row[0])
    else:
        start=datetime.fromisoformat(service['service_date']+'T'+(service['start_time'] or '00:00'))
    if not start.tzinfo:
        start=start.replace(tzinfo=zone)
    return start.astimezone(timezone.utc)-timedelta(minutes=service['close_minutes'])


def settle(db, now=None):
    """Must run under BEGIN IMMEDIATE. Capacity-aware FIFO, indivisible holds."""
    from family_reservations import effective_service, participants
    from reservations_sync import booking_capacity_used
    now=now or utcnow()
    for group in db.execute("SELECT * FROM family_booking_groups WHERE status='offer_pending' AND offer_expires_at<=?",(now.isoformat(),)).fetchall():
        transition(db,group['group_uuid'],'expired','expiration',now)
    for group in db.execute("SELECT g.* FROM family_booking_groups g WHERE g.status='waitlisted' ORDER BY g.created_at,g.rowid").fetchall():
        rows=_active(db,group['group_uuid'])
        if not rows:
            continue
        try:
            service=effective_service(db,group['service_id'],group['slot_uuid'],group['environment'],False)
            cutoff=_cutoff(db,service,group['slot_uuid'])
            if now>=cutoff:
                transition(db,group['group_uuid'],'expired','cloture',now);continue
            from family_reservations import validate_group
            validate_group(db,group,rows,service)
        except (ValueError,TypeError):
            # Invalidated relationship/account is not silently confirmed.
            continue
        if len(rows)>service['capacity']-booking_capacity_used(db,group['service_id'],group['slot_uuid']):
            continue
        token=secrets.token_urlsafe(32)
        hours=int(family.setting(db,'reservation_offer_hours','24'))
        deadline=min(now+timedelta(hours=hours),cutoff)
        db.execute('UPDATE family_booking_groups SET offer_expires_at=?,offer_token_hash=? WHERE group_uuid=?',(deadline.isoformat(),digest(token),group['group_uuid']))
        transition(db,group['group_uuid'],'offer_pending','proposition',now,notify=False)
        db.execute("UPDATE family_booking_emails SET state='superseded' WHERE group_uuid=? AND kind='waitlisted' AND state='pending'",(group['group_uuid'],))
        _queue(db,group['group_uuid'],'offer_pending',token,now)


def process_due(db, now=None):
    from outbound_actions import transaction
    with transaction(db):
        adopt_candidates(db);settle(db,now)


def lookup(db, token):
    if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{40,80}',token):
        raise ValueError('Ce lien de réservation est invalide ou indisponible.')
    row=db.execute('SELECT * FROM family_booking_groups WHERE manage_token_hash=? OR offer_token_hash=?',(digest(token),digest(token))).fetchone()
    if not row:
        raise ValueError('Ce lien de réservation est invalide ou indisponible.')
    return dict(row)


def respond(db, token, action, now=None):
    from family_reservations import effective_service, participants, result
    now=now or utcnow()
    if action not in ('accept','decline','cancel'):
        raise ValueError('Choisissez une action disponible.')
    process_due(db,now)
    owns_transaction = not db.in_transaction
    if owns_transaction: db.execute('BEGIN IMMEDIATE')
    try:
        settle(db,now);group=lookup(db,token)
        if action in ('accept','decline'):
            if group['offer_token_hash']!=digest(token):
                raise ValueError('Utilisez le lien de proposition reçu par e-mail.')
            if group['status']=='confirmed' and action=='accept':
                value=result(db,group['group_uuid'])
                if owns_transaction: db.commit()
                return value
            if group['status']=='declined' and action=='decline':
                value=result(db,group['group_uuid'])
                if owns_transaction: db.commit()
                return value
            if group['status']!='offer_pending' or group['offer_expires_at']<=now.isoformat():
                raise ValueError('Cette proposition n’est plus disponible. Aucune place n’a été confirmée.')
            if action=='accept':
                rows=_active(db,group['group_uuid'])
                service=effective_service(db,group['service_id'],group['slot_uuid'],group['environment'],False)
                if now>=_cutoff(db,service,group['slot_uuid']):
                    raise ValueError('Les inscriptions sont closes.')
                from family_reservations import validate_group
                validate_group(db,group,rows,service)
                from reservations_sync import booking_capacity_used
                if booking_capacity_used(db,group['service_id'],group['slot_uuid'])>service['capacity']:
                    raise ValueError('La capacité a changé. Contactez l’équipe.')
            transition(db,group['group_uuid'],'confirmed' if action=='accept' else 'declined','usager',now)
        elif group['status'] not in TERMINAL:
            transition(db,group['group_uuid'],'cancelled','usager',now)
        settle(db,now);value=result(db,group['group_uuid'])
        if owns_transaction: db.commit()
        return value
    except Exception:
        if owns_transaction: db.rollback()
        raise


def build_message(config, row, base_url, link_url=None):
    from welcome_mail import validate_config
    config=validate_config(config);parsed=urlsplit(base_url)
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.scheme not in ('http','https'):
        raise ValueError('Adresse publique OpenFabLab invalide.')
    payload=json.loads(row['payload_json']);kind=row['kind']
    subjects={'confirmed':'Réservation confirmée', 'waitlisted':'Inscription en liste d’attente',
              'offer_pending':'Une place est disponible pour votre groupe', 'expired':'Proposition expirée',
              'declined':'Proposition refusée', 'cancelled':'Réservation annulée', 'modified':'Réservation modifiée'}
    title=subjects[kind];url=link_url or base_url.rstrip('/')+'/animations/demande/'+payload['token']
    body=title+'\n\n'+payload['title']+'\n'+payload['date']+' · '+payload['hours']+'\n\nParticipants :\n'
    body+='\n'.join('- '+name for name in payload['participants'])+'\n\n'+str(payload['count'])+' place(s) pour le groupe entier.\n'
    if kind=='offer_pending':
        expires=datetime.fromisoformat(payload['expires']).astimezone(ZoneInfo(payload.get('timezone','Europe/Paris')))
        body+='\nCes places sont bloquées temporairement. Acceptez ou refusez avant le '+expires.strftime('%d/%m/%Y à %H:%M')+'.\nSans acceptation dans ce délai, la proposition expire et les places sont libérées.\n'
    elif kind=='waitlisted':
        body+='\nAucune place n’est confirmée. Vous recevrez automatiquement une proposition si tout votre groupe peut être accueilli.\n'
    body+='\nVoir la demande'+(' et accepter ou refuser' if kind=='offer_pending' else '')+' :\n'+url+'\n'
    message=EmailMessage();message['Subject']=title+' — OpenFabLab'
    message['From']=(config['sender_name']+' <'+config['sender_email']+'>') if config['sender_name'] else config['sender_email']
    message['To']=row['recipient'];message['Message-ID']='<'+row['message_uuid']+'@openfablab.local>'
    if config['reply_to']:message['Reply-To']=config['reply_to']
    message.set_content(body)
    message.add_alternative('<!doctype html><html lang="fr"><body><p>'+html.escape(body).replace('\n','<br>')+'</p><p><a href="'+html.escape(url,quote=True)+'">Voir ma réservation</a></p></body></html>',subtype='html')
    return message


def deliver(db, database_path, sender=None, now=None, base_url=None):
    """Durable bounded SMTP retries; stable Message-ID and exclusive claim.

    SMTP has no end-to-end exactly-once guarantee after a lost acknowledgement.
    Replays cannot consume seats: tokens and engine transitions are idempotent.
    """
    from runtime_policy import external_allowed
    from welcome_mail import load_config, send
    now=now or utcnow()
    if sender is None and not external_allowed(database_path):
        return 0
    config=load_config(database_path)
    explicit_base=base_url is not None
    base_url=base_url or family.setting(db,'reservation_wordpress_url','') or family.setting(db,'reservation_public_url','')
    if not base_url or (sender is None and urlsplit(base_url).scheme!='https') or not config:
        return 0
    # Recover claims after a process restart. A live claim never exceeds SMTP's
    # 10-second timeout; ten minutes prevent competing maintenance cycles.
    with db:
        db.execute("UPDATE family_booking_emails SET state='pending' WHERE state='sending' AND claimed_at<?",((now-timedelta(minutes=10)).isoformat(),))
    sent=0
    for item in db.execute("SELECT e.message_uuid FROM family_booking_emails e JOIN family_booking_groups g USING(group_uuid) WHERE e.state='pending' AND (e.next_attempt_at IS NULL OR e.next_attempt_at<=?) AND (? OR g.environment='production') ORDER BY e.created_at,e.rowid LIMIT 30",(now.isoformat(),sender is not None)).fetchall():
        db.execute('BEGIN IMMEDIATE')
        claimed=db.execute("UPDATE family_booking_emails SET state='sending',claimed_at=?,attempts=attempts+1 WHERE message_uuid=? AND state='pending'",(now.isoformat(),item[0]))
        row=db.execute('SELECT e.*,g.environment FROM family_booking_emails e JOIN family_booking_groups g USING(group_uuid) WHERE message_uuid=?',(item[0],)).fetchone();db.commit()
        if not claimed.rowcount:continue
        try:
            # Recheck that a pending proposal has not expired before delivery.
            if row['kind']=='offer_pending':
                group=db.execute('SELECT status,offer_expires_at FROM family_booking_groups WHERE group_uuid=?',(row['group_uuid'],)).fetchone()
                delivery_now=utcnow() if sender is None else now
                if not group or group['status']!='offer_pending' or group['offer_expires_at']<=delivery_now.isoformat():
                    with db:db.execute("UPDATE family_booking_emails SET state='superseded' WHERE message_uuid=?",(item[0],))
                    continue
            from outbound_actions import email_link
            link=None if explicit_base else email_link(db,database_path,json.loads(row['payload_json']),row['kind'],row['environment'])
            message=build_message(config,row,base_url,link)
            (sender or (lambda message:send(config,message)))(message)
        except Exception as error:
            # Store only an exception class, never SMTP payloads or credentials.
            delay=min(60,2**min(row['attempts'],6))
            with db:db.execute("UPDATE family_booking_emails SET state='pending',next_attempt_at=?,last_error=? WHERE message_uuid=?",((now+timedelta(minutes=delay)).isoformat(),type(error).__name__,item[0]))
        else:
            with db:db.execute("UPDATE family_booking_emails SET state='sent',sent_at=?,last_error=NULL WHERE message_uuid=?",(now.isoformat(),item[0]))
            sent+=1
    return sent


def run(db, database_path, sender=None, now=None, base_url=None):
    process_due(db,now)
    return deliver(db,database_path,sender,now,base_url)


def start_worker(application,get_database,load_modules):
    """Native queue without WordPress or the optional attendance scheduler."""
    import logging
    import threading
    import time
    from runtime_policy import storage_guard
    def work():
        while True:
            try:
                with storage_guard(application.config['DATABASE']), application.app_context():
                    db=get_database()
                    if load_modules(db)['public_reservations']:
                        run(db,application.config['DATABASE'])
            except Exception as error:
                logging.getLogger(__name__).warning('Reservation maintenance: %s',type(error).__name__)
            time.sleep(30)
    threading.Thread(target=work,name='openfablab-native-reservations',daemon=True).start()
