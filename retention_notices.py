"""Opt-in SMTP coordinate-erasure notice, expressly authorized by the user.

Destination: only the structure's administrator-selected existing SMTP provider
and the concerned account's own address. No third-party/family fallback. Tests
use a simulated sender; this development task sends no real message.
Minimal durable journal: no contact or message copy. Ambiguous sends not replayed.
"""
import html
import smtplib
import string
import time
from datetime import datetime,timedelta,timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo
from family_model import setting
import welcome_mail

SUBJECT='{structure_name} : suppression prochaine de vos coordonnées'
BODY='''Bonjour,

Conformément à notre politique de conservation des données personnelles, l’e-mail et le téléphone associés à votre compte OpenFabLab seront prochainement effacés.

Cette opération est prévue le {date_suppression}.
Pour toute question concernant vos données personnelles, vous pouvez contacter notre équipe : {contact_equipe}.

Cet e-mail est envoyé automatiquement par {structure_name}.'''
FIELDS={'structure_name','date_suppression','contact_equipe'}
PARIS=ZoneInfo('Europe/Paris')


def validate(subject,body):
    if not isinstance(subject,str) or not isinstance(body,str) or not subject.strip() or not body.strip() or len(subject)>240 or len(body)>8000 or any(ord(c)<32 for c in subject):
        raise ValueError('Objet (240 caractères) et message (8 000 caractères) requis, en texte brut.')
    if '{date_suppression}' not in body:
        raise ValueError('Conservez {date_suppression} dans le message pour annoncer l’échéance réelle.')
    try:
        for _,field,spec,conversion in string.Formatter().parse(subject+'\n'+body):
            if field is not None and (field not in FIELDS or spec or conversion):raise ValueError
    except ValueError:
        raise ValueError('Variables autorisées : {structure_name}, {date_suppression}, {contact_equipe}, sans expression.') from None


def preferences(db):
    try:days=int(setting(db,'retention_contact_notice_days','7'))
    except ValueError:days=7
    return dict(enabled=setting(db,'retention_contact_notice_enabled','0')=='1',days=max(1,min(90,days)),
        subject=setting(db,'retention_contact_notice_subject',SUBJECT),body=setting(db,'retention_contact_notice_body',BODY))


def deadline(activity,years):
    from app import years_after,years_ago
    local=activity.astimezone(PARIS)
    candidate=years_after(local,years).replace(fold=0)
    # Exact inverse of the existing purge predicate, including 29 February.
    if local>years_ago(candidate,years):candidate=(candidate+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
    if candidate.astimezone(timezone.utc).astimezone(PARIS).replace(tzinfo=None)!=candidate.replace(tzinfo=None):
        low,high=int(candidate.timestamp())-10800,int(candidate.timestamp())+10800
        while low+1<high:
            middle=(low+high)//2
            if local<=years_ago(datetime.fromtimestamp(middle,PARIS),years):high=middle
            else:low=middle
        candidate=datetime.fromtimestamp(high,PARIS)
    return candidate.astimezone(timezone.utc)


def candidates(db):
    return db.execute('''SELECT u.id,u.email,u.phone,u.created_at,
        MAX(COALESCE(s.check_out,s.check_in)) AS last_passage FROM users u
        LEFT JOIN sessions s ON s.user_id=u.id GROUP BY u.id''')


def target(db,row,now):
    from app import load_retention_settings,parse_timestamp
    years=load_retention_settings(db)['contact_years']
    if not years or not row or not (row['email'] or row['phone']):return None
    result=deadline(parse_timestamp(row['last_passage'] or row['created_at']),years)
    return result if result>now else None


def reconcile(db,now):
    prefs=preferences(db);stamp=now.isoformat()
    if not prefs['enabled']:
        db.execute("UPDATE retention_contact_notices SET state='cancelled',finished_at=? WHERE state IN('pending','failed')",(stamp,))
        db.commit();return
    db.execute("UPDATE retention_contact_notices SET state='uncertain',finished_at=?,last_error='InterruptedClaim' WHERE state='sending' AND julianday(claimed_at)<julianday(?)",
        (stamp,(now-timedelta(minutes=10)).isoformat()))
    for row in list(candidates(db)):
        due=target(db,row,now)
        db.execute("UPDATE retention_contact_notices SET state='cancelled',finished_at=? WHERE user_id=? AND state IN('pending','failed') AND (?=0 OR deadline<>?)",
            (stamp,row['id'],int(prefs['enabled']),due.isoformat() if due else ''))
        if prefs['enabled'] and row['email'] and due and within(due,now,prefs['days']):
            db.execute("INSERT OR IGNORE INTO retention_contact_notices(user_id,deadline,state,created_at) VALUES(?,?,'pending',?)",
                (row['id'],due.isoformat(),stamp))
    db.commit()


def build(db,config,recipient,due):
    config=welcome_mail.validate_config(config)
    from family_waitlist import valid_email
    if not valid_email(recipient):raise ValueError('Adresse destinataire invalide.')
    prefs=preferences(db);validate(prefs['subject'],prefs['body'])
    values=dict(structure_name=setting(db,'structure_name','Mon FabLab'),
        date_suppression=due.astimezone(ZoneInfo(setting(db,'structure_timezone','Europe/Paris'))).strftime('%d/%m/%Y'),
        contact_equipe=setting(db,'structure_dpo_email','') or setting(db,'structure_email','') or 'l’équipe de la structure')
    subject=prefs['subject'].format_map(values)
    if any(ord(c)<32 for c in subject):raise ValueError('Objet invalide.')
    body=prefs['body'].format_map(values)
    message=EmailMessage();message['Subject']=subject;message['From']=(config['sender_name']+' <'+config['sender_email']+'>') if config['sender_name'] else config['sender_email'];message['To']=recipient
    if config['reply_to']:message['Reply-To']=config['reply_to']
    message.set_content(body)
    message.add_alternative('<!doctype html><html lang="fr"><body><p>'+html.escape(body).replace('\n','<br>')+'</p></body></html>',subtype='html')
    return message


def within(due,now,days):
    return due>now and (due.astimezone(PARIS).date()-now.astimezone(PARIS).date()).days<=days


def process(db,database_path,now=None,sender=None,prepare=True):
    now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    started=time.monotonic()
    if prepare:reconcile(db,now)
    if not preferences(db)['enabled']:return 0
    from runtime_policy import external_allowed
    if sender is None and not external_allowed(database_path):return 0
    config=welcome_mail.load_config(database_path)
    if not config.get('host'):return 0
    delivered=0
    # One eligible FUTURE-deadline notice per existing maintenance tick.
    # Keep the original pre-purge ordering; never turn SMTP into a mass burst.
    items=db.execute("SELECT user_id,deadline FROM retention_contact_notices WHERE state='pending' ORDER BY deadline,user_id LIMIT 1").fetchall()
    for item in items:
        db.execute('BEGIN IMMEDIATE')
        changed=db.execute("UPDATE retention_contact_notices SET state='sending',claimed_at=? WHERE user_id=? AND deadline=? AND state='pending'",
            (now.isoformat(),item['user_id'],item['deadline'])).rowcount
        db.commit()
        if not changed:continue
        # Recheck under lock, excluding a concurrent purge or activity update.
        db.execute('BEGIN IMMEDIATE')
        state=db.execute('SELECT state FROM retention_contact_notices WHERE user_id=? AND deadline=?',tuple(item)).fetchone()
        row=db.execute('''SELECT u.id,u.email,u.phone,u.created_at,MAX(COALESCE(s.check_out,s.check_in)) AS last_passage
            FROM users u LEFT JOIN sessions s ON s.user_id=u.id WHERE u.id=? GROUP BY u.id''',(item['user_id'],)).fetchone()
        checked_now=now+timedelta(seconds=time.monotonic()-started)
        due=target(db,row,checked_now);prefs=preferences(db)
        if not state or state[0]!='sending' or not prefs['enabled'] or not due or due.isoformat()!=item['deadline'] or not within(due,checked_now,prefs['days']) or not row['email']:
            db.execute("UPDATE retention_contact_notices SET state='cancelled',finished_at=? WHERE user_id=? AND deadline=? AND state='sending'",(now.isoformat(),*tuple(item)))
            db.commit();continue
        try:
            message=build(db,config,row['email'],due)
            (sender or (lambda value:welcome_mail.send(config,value)))(message)
            result,error='sent',None;delivered+=1
        except (ValueError,smtplib.SMTPRecipientsRefused) as problem:
            result,error='failed',type(problem).__name__
        except Exception as problem:
            result,error='uncertain',type(problem).__name__
        db.execute('UPDATE retention_contact_notices SET state=?,finished_at=?,last_error=? WHERE user_id=? AND deadline=?',
            (result,now.isoformat(),error,*tuple(item)))
        db.commit()
    return delivered


def summary(db,now=None):
    now=now or datetime.now(timezone.utc)
    due=[value for row in candidates(db) if (value:=target(db,row,now)) and value-now<=timedelta(days=30)]
    states={row[0]:row[1] for row in db.execute('SELECT state,COUNT(*) FROM retention_contact_notices GROUP BY state')}
    return dict(upcoming=len(due),next_date=min(due).astimezone(ZoneInfo(setting(db,'structure_timezone','Europe/Paris'))).strftime('%d/%m/%Y') if due else None,
        sent=states.get('sent',0),errors=states.get('failed',0)+states.get('uncertain',0),pending=states.get('pending',0))


def register(application,a):
    from flask import Blueprint,flash,redirect,request,url_for
    from evolution_routes import require_team,require_csrf
    bp=Blueprint('retention_notices',__name__)
    @application.context_processor
    def notice_context():
        from evolution_routes import actor
        if request.endpoint not in ('admin_settings_data','data_management') or actor()!='admin':return {}
        db=a.get_database()
        return dict(contact_notice=preferences(db),contact_notice_summary=summary(db))
    @bp.post('/admin/reglages/donnees/preavis')
    def save():
        require_team(True);require_csrf();db=a.get_database()
        try:
            days=request.form.get('days','7')
            if not days.isdecimal() or not 1<=int(days)<=90:raise ValueError('Le préavis doit être compris entre 1 et 90 jours.')
            subject,body=request.form.get('subject',''),request.form.get('body','');validate(subject,body)
            with db:
                for key,value in (('enabled','1' if request.form.get('enabled')=='1' else '0'),('days',days),('subject',subject.strip()),('body',body.strip())):
                    a.write_setting(db,'retention_contact_notice_'+key,value)
            reconcile(db,datetime.now(timezone.utc))
            flash('Préavis enregistré. Les durées de conservation restent inchangées.','success')
        except ValueError as error:
            db.rollback();flash(str(error),'error')
        return redirect(url_for('admin_settings_data',_anchor='contact-notice'))
    application.register_blueprint(bp)
