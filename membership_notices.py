"""Minimal outbox, no copied contacts, no ambiguous retry and no payments."""
import hashlib
import json
from datetime import datetime,timedelta,timezone
from email.message import EmailMessage
import memberships as m
import v210_config

LABELS={'soon':'Votre formule arrive bientôt à expiration.','expired':'Votre formule est arrivée à expiration.',
        'low':'Votre solde de crédits est faible.','empty':'Votre carnet de crédits est épuisé.',
        'renewal':'Votre renouvellement est enregistré. Aucun paiement n’est confirmé par ce message.',
        'recharge':'Votre recharge de crédits est enregistrée. Aucun paiement n’est confirmé par ce message.',
        'review':'Une situation de crédits nécessite une régularisation.'}


def queue(db,grant_id,kind,key,now=None):
    now=now or datetime.now(timezone.utc)
    for channel,flag in [('smtp','membership_smtp_enabled'),('discord','membership_discord_enabled')]:
        if m.setting(db,flag,'0')!='1' or (channel=='discord' and kind in ('renewal','recharge')) or (channel=='smtp' and kind=='review'):continue
        db.execute("INSERT OR IGNORE INTO membership_notifications(notification_key,grant_id,event_type,channel,state,created_at) VALUES(?,?,?,?,'pending',?)",
            (m.hashed(key+'/'+channel),grant_id,kind,channel,now.isoformat()))


def reconcile(db,now):
    if not m.enabled(db):
        with m.atomic(db):db.execute("UPDATE membership_notifications SET state='cancelled' WHERE state IN('pending','failed')")
        return
    day=now.astimezone(m.zone(db)).date();prefs=v210_config.preferences(db)
    with m.atomic(db):
        db.execute("UPDATE membership_notifications SET state='uncertain',last_error='InterruptedDelivery' WHERE state='sending' AND claimed_at<?",((now-timedelta(minutes=10)).isoformat(),))
        for grant in db.execute('SELECT * FROM membership_grants WHERE status=\'active\'').fetchall():
            terms=json.loads(grant['terms_json']);end=datetime.fromisoformat(grant['ends_on']).date()
            renewed=db.execute("SELECT 1 FROM membership_grants WHERE owner_id=? AND plan_id=? AND grant_id<>? AND status='active' AND starts_on>? AND starts_on<=date(?,'+1 day') LIMIT 1",(grant['owner_id'],grant['plan_id'],grant['grant_id'],grant['starts_on'],grant['ends_on'])).fetchone()
            threshold=m.units(prefs['membership_low_threshold'],terms) if terms['kind']=='credits' else 0
            review=bool(db.execute('SELECT 1 FROM membership_consumptions WHERE grant_id=? AND remaining>0 UNION ALL SELECT 1 FROM membership_session_links WHERE grant_id=? AND review_required=1 LIMIT 1',(grant['grant_id'],grant['grant_id'])).fetchone())
            states=dict(soon=not renewed and day<=end<=day+timedelta(days=int(prefs['membership_notice_days'])),
                expired=not renewed and end<day,low=terms['kind']=='credits' and 0<grant['balance']<=threshold and day<=end,
                empty=terms['kind']=='credits' and grant['balance']==0 and day<=end,review=review)
            old=db.execute('SELECT * FROM membership_notice_state WHERE grant_id=?',(grant['grant_id'],)).fetchone()
            previous=json.loads(old['states_json']) if old else {};sequence=(old['sequence'] if old else 0)
            for kind,active in states.items():
                if active and not previous.get(kind):
                    sequence+=1;queue(db,grant['grant_id'],kind,'membership/'+grant['grant_id']+'/'+str(sequence)+'/'+kind,now)
                if not active:db.execute("UPDATE membership_notifications SET state='cancelled' WHERE grant_id=? AND event_type=? AND state IN('pending','failed')",(grant['grant_id'],kind))
            db.execute('INSERT INTO membership_notice_state VALUES(?,?,?) ON CONFLICT(grant_id) DO UPDATE SET states_json=excluded.states_json,sequence=excluded.sequence',(grant['grant_id'],m.pack(states),sequence))


def process(db,database_path,now=None,smtp_sender=None,discord_sender=None):
    now=now or datetime.now(timezone.utc)
    reconcile(db,now)
    if not m.enabled(db):return 0
    from runtime_policy import external_allowed
    if smtp_sender is None and discord_sender is None and not external_allowed(database_path):return 0
    count=0
    for item in db.execute("SELECT notification_key FROM membership_notifications WHERE state='pending' ORDER BY created_at LIMIT 30").fetchall():
        with m.atomic(db):
            row=db.execute('SELECT * FROM membership_notifications WHERE notification_key=?',(item[0],)).fetchone()
            if row['state']!='pending':continue
            grant=db.execute('SELECT * FROM membership_grants WHERE grant_id=?',(row['grant_id'],)).fetchone()
            person=db.execute('SELECT email,active FROM users WHERE id=?',(grant['owner_id'],)).fetchone()
            enabled=(m.enabled(db) and m.setting(db,'membership_'+('smtp' if row['channel']=='smtp' else 'discord')+'_enabled','0')=='1')
            if not enabled or grant['status']!='active' or (row['channel']=='smtp' and (not person or not person['active'] or not person['email'])):
                db.execute("UPDATE membership_notifications SET state='cancelled' WHERE notification_key=?",(item[0],));continue
            if row['channel']=='discord' and (m.setting(db,'module_discord','1')!='1' or m.setting(db,'discord_notifications_enabled','0')!='1'):continue
            if row['channel']=='smtp':
                import welcome_mail
                config=welcome_mail.load_config(database_path)
                if smtp_sender is None and (not external_allowed(database_path) or not config.get('host')):continue
                if smtp_sender is None:config=welcome_mail.validate_config(config)
                terms=json.loads(grant['terms_json']);prefs=v210_config.preferences(db)
                v210_config.validate('membership_mail_subject',prefs['membership_mail_subject']);v210_config.validate('membership_mail_body',prefs['membership_mail_body'])
                values=dict(structure_name=m.setting(db,'structure_name','Mon FabLab'),evenement=LABELS[row['event_type']],nom_formule=terms['name'],date_expiration=datetime.fromisoformat(grant['ends_on']).strftime('%d/%m/%Y'),credits_restants=m.amount_label(grant['balance'],terms) if terms['kind']=='credits' else 'Sans consommation')
                message=EmailMessage();message['Subject']=prefs['membership_mail_subject'].format_map(values)
                if any(ord(c)<32 for c in str(message['Subject'])):raise ValueError('Objet invalide.')
                message['From']=(config.get('sender_name','')+' <'+config['sender_email']+'>') if config.get('sender_name') else config.get('sender_email') or 'noreply@example.invalid'
                message['To']=person['email']
                if config.get('reply_to'):message['Reply-To']=config['reply_to']
                message.set_content(prefs['membership_mail_body'].format_map(values))
                sender=smtp_sender or (lambda value:welcome_mail.send(config,value))
            else:
                message='Abonnements et crédits : '+LABELS[row['event_type']]
                if discord_sender is None:
                    from app import read_discord_webhook,send_discord_plain
                    webhook=read_discord_webhook()
                    if not webhook or not external_allowed(database_path):continue
                    sender=lambda value:send_discord_plain(webhook,value,m.setting(db,'discord_bot_name','OpenFabLab'))
                else:sender=discord_sender
            db.execute("UPDATE membership_notifications SET state='sending',claimed_at=? WHERE notification_key=?",(now.isoformat(),item[0]))
        try:sender(message)
        except Exception as error:
            with m.atomic(db):db.execute("UPDATE membership_notifications SET state='uncertain',last_error=?,finished_at=? WHERE notification_key=?",(type(error).__name__,now.isoformat(),item[0]))
        else:
            with m.atomic(db):db.execute("UPDATE membership_notifications SET state='sent',finished_at=? WHERE notification_key=?",(now.isoformat(),item[0]))
            count+=1
    return count
