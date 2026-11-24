"""At most one outstanding delivery per worker; no token in a durable outbox.

Tickets are committed before transport. A delivery of uncertain outcome may
be retried; first invalidate that attempt's ticket. Permanent SMTP failure is
visible to staff and cannot activate a person.
"""
from email.message import EmailMessage
from urllib.parse import urlsplit
import time
import re
import online_accounts as online
import family_model as family
import welcome_mail
from outbound_actions import transaction
from reservation_email_templates import ACCOUNT_LINK_MODELS, ONLINE_INTRO, load, render_online

def portal_url(db):
    url=family.setting(db,'online_account_url','')
    parsed=urlsplit(url)
    site=urlsplit(family.setting(db,'reservation_wordpress_url',''))
    if (parsed.scheme!='https' or not parsed.hostname or parsed.netloc!=site.netloc or site.scheme!='https'
            or parsed.username or parsed.password or parsed.query or parsed.fragment or '\\' in url or any(ord(c)<=32 for c in url)):
        raise ValueError('Adresse HTTPS de la page Mon compte requise sur le WordPress configuré.')
    return url

def deliver_one(db,path,now=None,transport=None,config=None):
    from runtime_policy import external_allowed
    if transport is None and not external_allowed(path):return False
    if family.setting(db,'online_accounts_enabled')!='1':return False
    now=int(time.time()) if now is None else now
    with transaction(db):
        row=db.execute('SELECT * FROM online_mail WHERE retry<=? AND created>? AND attempts<4 ORDER BY id LIMIT 1',(now,now-86400)).fetchone()
        if not row:return False
        db.execute('UPDATE online_mail SET retry=?,attempts=attempts+1 WHERE id=?',(now+180*(1+row['attempts']),row['id']))
    try:
        conf=welcome_mail.validate_config(config if config is not None else welcome_mail.load_config(path))
        with transaction(db):
            if not db.execute('SELECT 1 FROM online_mail WHERE id=?',(row['id'],)).fetchone():return False
            kind=row['kind']
            model='online_'+kind
            if model not in ONLINE_INTRO:raise ValueError('Modèle de compte inconnu.')
            public_id=''
            user=None
            if row['owner'] is not None:
                if kind=='child_welcome':
                    match=re.fullmatch(r'guardian:([0-9]+)',row['browser'])
                    guardian=online.account(db,int(match[1])) if match else None
                    if guardian and guardian['email'].strip().lower()==row['address'] and family.eligible(db,guardian):
                        user=next((u for u in family.members(db,guardian['id']) if u['id']==row['owner'] and u['active']
                                   and (years:=family.age(u,family.local_day(db))) is not None and 0<=years<18),None)
                else:
                    user=(online.identifier_target(db,row['address']) if kind in ('recover','identifier')
                          else online.account(db,row['owner']))
                if not user or user['id']!=row['owner'] or (kind not in ('email','child_welcome') and row['address']!=user['email'].strip().lower()):
                    db.execute('DELETE FROM online_mail WHERE id=?',(row['id'],))
                    return False
                public_id=user['public_id']
            url=''
            if model in ACCOUNT_LINK_MODELS:
                url=portal_url(db)
                db.execute('DELETE FROM online_tickets WHERE purpose=? AND address=? AND browser=? AND request_id IS ?',
                           (kind,row['address'],row['browser'],row['request_id']))
                url+='#ofl-account='+online.issue_ticket(db,row,now)
            locale=row['locale']
            title,body,html=render_online(model,load(db,model,locale),
                family.setting(db,'structure_name','Mon FabLab'),url,public_id,locale,
                first_name=user['first_name'] if user and kind=='child_welcome' else '',
                last_name=user['last_name'] if user and kind=='child_welcome' else '')
            message=EmailMessage()
            message['From']=conf['sender_email']; message['To']=online.address(row['address'])
            message['Subject']=title
            message.set_content(body)
            message.add_alternative(html,subtype='html')
            if kind=='child_welcome':
                message.add_attachment(welcome_mail.qr_png(public_id),maintype='image',subtype='png',filename='OpenFabLab-QR.png')
                # Retries after an uncertain SMTP result use the same Message-ID.
                import hashlib
                message['Message-ID']='<ofl-'+hashlib.sha256(f"{row['id']}:{row['created']}:{row['address']}".encode()).hexdigest()+'@'+conf['sender_email'].split('@')[-1]+'>'
        (transport or welcome_mail.send)(conf,message)
    except (OSError,ValueError,RuntimeError):
        return False
    with transaction(db):
        if row['kind']=='child_welcome':
            from evolution_schema import now as provenance_date
            db.execute("UPDATE users SET welcome_sent_at=?,welcome_status='sent' WHERE id=?",(provenance_date(),row['owner']))
        db.execute('DELETE FROM online_mail WHERE id=?',(row['id'],))
    return True
