"""Plain-text editable templates, escaped HTML and one personal action link."""
import html
import json
import re
from datetime import datetime
from email.message import EmailMessage
from string import Formatter
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from animation_information import optional_url
from usability import MONTHS

VARIABLES={'structure','animation','date','horaire','participants','places',
           'lien_reservation','lien_information','date_limite'}
HEADERS={'structure','animation','date','horaire','places'}
INTRO={
 'confirmed':('Réservation confirmée','Votre inscription à l’animation « {animation} » est confirmée.'),
 'modified':('Réservation modifiée','Les participants de votre réservation pour « {animation} » ont été mis à jour.'),
 'cancelled':('Réservation annulée','Votre réservation pour « {animation} » est annulée. Aucune place n’est retenue.'),
 'waitlisted':('Inscription en liste d’attente','Votre demande pour « {animation} » est en liste d’attente. Aucune place n’est encore confirmée.'),
 'offer_pending':('Une place est disponible','Des places sont disponibles pour tout votre groupe à l’animation « {animation} ».'),
 'accepted':('Place acceptée','Votre proposition pour « {animation} » a été acceptée. Votre réservation est confirmée.'),
 'expired':('Proposition expirée','La proposition pour « {animation} » a expiré. Aucune place n’a été confirmée par cette proposition.'),
 'declined':('Proposition refusée','Votre proposition pour « {animation} » a été refusée. Les places sont libérées.'),
}


def default(kind):
    label,intro=INTRO[kind]
    body=intro+'\n\n{date} · {horaire}\n\nParticipants :\n{participants}\n\nNombre de participants : {places}.\n'
    if kind=='offer_pending':
        body+='\nCes places sont bloquées temporairement. Acceptez ou refusez avant le {date_limite}. Sans acceptation dans ce délai, la proposition expire et les places sont libérées.\n'
    elif kind=='waitlisted':
        body+='\nVous recevrez automatiquement une proposition si tout votre groupe peut être accueilli.\n'
    help_text='Vous pouvez consulter les informations de cette demande.' if kind in ('cancelled','expired','declined') else 'Vous pouvez consulter les informations de votre réservation ou l’annuler si vous ne pouvez plus participer.'
    body+='\n{lien_reservation}\n\n'+help_text+'\n\n{lien_information}\n'
    return dict(subject=label+' — {structure}',body=body)


def key(kind,field):
    return 'reservation_email_'+kind+'_'+field


def allowed_key(name):
    return name in {key(kind,field) for kind in INTRO for field in ('subject','body')}


def validate(value,field):
    if isinstance(value,str) and field=='body':
        # HTML forms submit textarea lines as CRLF. Normalize only legitimate
        # pairs; lone CR and every subject newline remain forbidden.
        value=value.replace('\r\n','\n')
    if not isinstance(value,str) or not value.strip() or len(value)>(200 if field=='subject' else 8000):
        raise ValueError('Sujet de 1 à 200 caractères et contenu de 1 à 8 000 caractères requis.')
    if any(ord(c)<32 and c not in ('\n','\t') for c in value) or (field=='subject' and ('\n' in value or '\r' in value)):
        raise ValueError('Le modèle contient des caractères de contrôle interdits.')
    try:
        for _,name,spec,conversion in Formatter().parse(value):
            if name is not None and (name not in (HEADERS if field=='subject' else VARIABLES) or spec or conversion):
                raise ValueError('Variable inconnue ou format non autorisé dans le modèle.')
    except ValueError:
        raise ValueError('Utilisez uniquement les variables documentées, entourées d’accolades.') from None
    for name in ('lien_reservation','lien_information'):
        if value.count('{'+name+'}')>1:
            raise ValueError('Chaque lien ne peut apparaître qu’une seule fois dans un modèle.')
    return value.strip()


def load(db,kind):
    result=default(kind)
    if db is not None:
        for field in result:
            row=db.execute('SELECT value FROM app_settings WHERE key=?',(key(kind,field),)).fetchone()
            if row:
                try:
                    result[field]=validate(row[0],field)
                except ValueError:
                    pass  # Invalid old/imported setting never prevents delivery.
    return result


def date_label(value):
    moment=datetime.fromisoformat(value)
    return f'{moment.day:02d} {MONTHS[moment.month-1]} {moment.year}'


def render(payload,kind,template,url):
    information=optional_url(payload.get('information_url',''))
    expires=payload.get('expires')
    deadline=''
    if expires:
        moment=datetime.fromisoformat(expires).astimezone(ZoneInfo(payload.get('timezone','Europe/Paris')))
        deadline=date_label(moment.isoformat())+f' à {moment.hour:02d}h{moment.minute:02d}'
    values=dict(structure=payload.get('structure') or 'Mon FabLab',animation=payload['title'],
        date=date_label(payload['date']),horaire=payload['hours'],
        participants='\n'.join('- '+p for p in payload['participants']),places=str(payload['count']),
        lien_reservation=url,lien_information=information,date_limite=deadline)
    subject=validate(template['subject'],'subject').format_map(values)
    # No dynamic participant/title can inject mail headers.
    subject=re.sub(r'[\r\n\x00-\x1f]',' ',subject)[:250]
    raw=validate(template['body'],'body')
    if not information:
        raw='\n'.join(line for line in raw.splitlines() if '{lien_information}' not in line)
    if '{lien_reservation}' not in raw:
        raw+='\n\n{lien_reservation}'
    body=raw.format_map(values)
    # Render link variables as buttons, not duplicated raw technical URLs.
    html_raw=raw.format_map(dict(values,lien_reservation='\x01MANAGE\x01',lien_information='\x01INFO\x01'))
    escaped=html.escape(html_raw).replace('\n','<br>')
    escaped=escaped.replace('\x01MANAGE\x01','<a class="reservation-mail-button" href="'+html.escape(url,quote=True)+'" style="display:inline-block;background:#2e809b;color:white;padding:12px 18px;border-radius:10px;text-decoration:none">Gérer ma réservation</a>')
    escaped=escaped.replace('\x01INFO\x01','<a href="'+html.escape(information,quote=True)+'">En savoir plus sur cette animation</a>')
    return subject,body,'<!doctype html><html lang="fr"><body><div style="font-family:Arial,sans-serif;line-height:1.6;max-width:640px;margin:auto">'+escaped+'</div></body></html>'


def build_message(config,row,base_url,link_url=None,db=None):
    from welcome_mail import validate_config
    config=validate_config(config)
    parts=urlsplit(base_url)
    if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.scheme not in ('http','https'):
        raise ValueError('Adresse publique de réservation invalide.')
    payload=json.loads(row['payload_json'])
    kind=payload.get('event',row['kind'])
    if kind not in INTRO:
        kind=row['kind']
    url=link_url or base_url.rstrip('/')+'/animations/demande/'+payload['token']
    subject,body,html_body=render(payload,kind,load(db,kind),url)
    message=EmailMessage()
    message['Subject']=subject
    message['From']=(config['sender_name']+' <'+config['sender_email']+'>') if config['sender_name'] else config['sender_email']
    message['To']=row['recipient']
    message['Message-ID']='<'+row['message_uuid']+'@openfablab.local>'
    if config['reply_to']:
        message['Reply-To']=config['reply_to']
    message.set_content(body)
    message.add_alternative(html_body,subtype='html')
    return message


def register(application,a):
    from flask import Blueprint,request,abort,render_template,flash,redirect,url_for
    from markupsafe import Markup
    from evolution_routes import require_csrf,require_team
    bp=Blueprint('reservation_emails',__name__)
    @bp.route('/admin/reglages/structure/emails-reservation',methods=['GET','POST'])
    def settings():
        require_team(True)
        db=a.get_database()
        kind=request.values.get('kind','confirmed')
        if kind not in INTRO:
            abort(400)
        template=load(db,kind)
        errors=[]
        if request.method=='POST':
            require_csrf()
            try:
                action=request.form.get('action')
                if action=='reset':
                    with db:
                        db.execute('DELETE FROM app_settings WHERE key IN (?,?)',(key(kind,'subject'),key(kind,'body')))
                    flash('Modèle par défaut restauré.','success')
                    return redirect(url_for('reservation_emails.settings',kind=kind))
                template={field:validate(request.form.get(field,''),field) for field in ('subject','body')}
                if action=='save':
                    with db:
                        for field,value in template.items():
                            db.execute('INSERT INTO app_settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key(kind,field),value))
                    flash('Modèle enregistré.','success')
                    return redirect(url_for('reservation_emails.settings',kind=kind))
                if action!='preview':
                    raise ValueError('Choisissez une action proposée.')
            except ValueError as error:
                errors.append(str(error));template=load(db,kind)
        fake=dict(title='Atelier fictif de fabrication',date='2026-11-12',hours='10:00–12:00',
            participants=['Camille EXEMPLE','Alex EXEMPLE'],count=2,structure='Atelier Exemple',
            information_url='https://example.invalid/programme',expires='2026-11-11T12:00:00+00:00',timezone='Europe/Paris')
        subject,plain,html_body=render(fake,kind,template,'https://example.invalid/reservation-fictive')
        return render_template('reservation_email_settings.html',kind=kind,models=INTRO,
            template=template,errors=errors,preview_subject=subject,preview_html=Markup(html_body.split('<body>',1)[1].split('</body>',1)[0]),variables=sorted(VARIABLES))
    application.register_blueprint(bp)
