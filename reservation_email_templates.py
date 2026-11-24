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
 'reminder':('Rappel de votre réservation','Votre animation « {animation} » approche. Votre réservation est confirmée.'),
 'confirmed':('Réservation confirmée','Votre inscription à l’animation « {animation} » est confirmée.'),
 'modified':('Réservation modifiée','Les participants de votre réservation pour « {animation} » ont été mis à jour.'),
 'cancelled':('Réservation annulée','Votre réservation pour « {animation} » est annulée. Aucune place n’est retenue.'),
 'waitlisted':('Inscription en liste d’attente','Votre demande pour « {animation} » est en liste d’attente. Aucune place n’est encore confirmée.'),
 'offer_pending':('Une place est disponible','Des places sont disponibles pour tout votre groupe à l’animation « {animation} ».'),
 'accepted':('Place acceptée','Votre proposition pour « {animation} » a été acceptée. Votre réservation est confirmée.'),
 'expired':('Proposition expirée','La proposition pour « {animation} » a expiré. Aucune place n’a été confirmée par cette proposition.'),
 'declined':('Proposition refusée','Votre proposition pour « {animation} » a été refusée. Les places sont libérées.'),
}
ONLINE_INTRO={
 'online_verify':('Vérifiez votre adresse e-mail','Pour confirmer votre demande, ouvrez le lien dans le navigateur utilisé pour la commencer.'),
 'online_login':('Connexion à Mon compte','Pour vous connecter, ouvrez le lien dans le navigateur utilisé pour la demande.'),
 'online_recover':('Retrouver votre identifiant','Confirmez votre demande dans le même navigateur.'),
 'online_email':('Confirmer la nouvelle adresse','Confirmez la modification dans le navigateur de votre session.'),
 'online_activated':('Votre compte est activé','Votre compte OpenFabLab est actif. Votre identifiant de borne :'),
 'online_identifier':('Votre identifiant','Votre identifiant de borne :'),
 'online_review':('Demande reçue','Votre adresse a été vérifiée. L’équipe va examiner votre demande.'),
 'online_denied':('Décision de l’équipe','Votre demande n’a pas été acceptée. Contactez l’équipe pour en discuter.'),
 'online_family_done':('Rattachement familial','Votre espace familial a été actualisé.'),
 'online_child_welcome':('Identifiant et QR Code de votre enfant','La fiche de {prenom} {nom} est prête. Présentez le QR Code joint ou saisissez son identifiant sur la borne du FabLab. Ce code ne permet pas de se connecter sur Internet.'),
 'online_assistance':('Contacter l’équipe','Votre situation nécessite une vérification par l’équipe du FabLab.'),
}
ACCOUNT_LINK_MODELS={
 'online_verify':'Confirmer mon adresse e-mail',
 'online_login':'Me connecter',
 'online_recover':'Retrouver mon identifiant',
 'online_email':'Confirmer ma nouvelle adresse',
}
ACCOUNT_ID_MODELS={'online_activated','online_identifier','online_child_welcome'}
ACCOUNT_NOTICE='Si vous n’êtes pas à l’origine de cette démarche, contactez votre FabLab.'


def variables_for(kind,field='body'):
    if kind not in ONLINE_INTRO:
        return HEADERS if field=='subject' else VARIABLES
    return {'structure'} | (
        ({'lien_compte'} if kind in ACCOUNT_LINK_MODELS else set())
        | ({'identifiant'} if kind in ACCOUNT_ID_MODELS else set())
        | ({'prenom','nom'} if kind=='online_child_welcome' else set())
        if field=='body' else set()
    )


def default(kind,locale='fr'):
    if kind in ONLINE_INTRO:
        from i18n import CATALOGS
        tr=CATALOGS.get(locale,{})
        subject,body=(tr.get(text,text) for text in ONLINE_INTRO[kind])
        if kind in ACCOUNT_LINK_MODELS:
            body+='\n\n{lien_compte}'
        if kind in ACCOUNT_ID_MODELS:
            body+=' {identifiant}'
        return dict(subject=subject,body=body)
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
    if kind in ONLINE_INTRO:
        # Local to the installation, like the previous portal signature;
        # portable profile imports do not replace these texts implicitly.
        return kind.replace('online_','online_email_',1)+'_'+field
    return 'reservation_email_'+kind+'_'+field


def allowed_key(name):
    return name in {key(kind,field) for kind in INTRO for field in ('subject','body')}


def validate(value,field,kind=None):
    if isinstance(value,str) and field=='body':
        # HTML forms submit textarea lines as CRLF. Normalize only legitimate
        # pairs; lone CR and every subject newline remain forbidden.
        value=value.replace('\r\n','\n')
    if not isinstance(value,str) or not value.strip() or len(value)>(200 if field=='subject' else 8000):
        raise ValueError('Sujet de 1 à 200 caractères et contenu de 1 à 8 000 caractères requis.')
    if any(ord(c)<32 and c not in ('\n','\t') for c in value) or (field=='subject' and ('\n' in value or '\r' in value)):
        raise ValueError('Le modèle contient des caractères de contrôle interdits.')
    try:
        fields=[(name,spec,conversion) for _,name,spec,conversion in Formatter().parse(value) if name is not None]
        for name,spec,conversion in fields:
            if name not in variables_for(kind,field) or spec or conversion:
                raise ValueError('Variable inconnue ou format non autorisé dans le modèle.')
    except ValueError:
        raise ValueError('Utilisez uniquement les variables documentées, entourées d’accolades.') from None
    for name in ('lien_reservation','lien_information','lien_compte'):
        if sum(field_name==name for field_name,_,_ in fields)>1:
            raise ValueError('Chaque lien ne peut apparaître qu’une seule fois dans un modèle.')
    return value.strip()


def load(db,kind,locale='fr'):
    result=default(kind,locale)
    if db is not None:
        for field in result:
            row=db.execute('SELECT value FROM app_settings WHERE key=?',(key(kind,field),)).fetchone()
            if row:
                try:
                    result[field]=validate(row[0],field,kind)
                except ValueError:
                    pass  # Invalid old/imported setting never prevents delivery.
    return result


def action_link(url,label):
    return '<a class="reservation-mail-button" href="'+html.escape(url,quote=True)+'" style="display:inline-block;background:#2e809b;color:white;padding:12px 18px;border-radius:10px;text-decoration:none">'+html.escape(label)+'</a>'


def mail_document(body,locale='fr'):
    return '<!doctype html><html lang="'+html.escape(locale,quote=True)+'"><body><div style="font-family:Arial,sans-serif;line-height:1.6;max-width:640px;margin:auto">'+body+'</div></body></html>'


def render_online(kind,template,structure,url='',public_id='',locale='fr',*,first_name='',last_name=''):
    from i18n import CATALOGS
    tr=CATALOGS.get(locale,{})
    values=dict(structure=re.sub(r'[\x00-\x1f]',' ',structure or 'Mon FabLab'),
                lien_compte=url,identifiant=public_id,prenom=first_name,nom=last_name)
    subject=validate(template['subject'],'subject',kind).format_map(values)
    subject=re.sub(r'[\r\n\x00-\x1f]',' ',subject)[:250]
    raw=validate(template['body'],'body',kind)
    # Escaped braces are literal text, not a real variable.
    used={name for _,name,_,_ in Formatter().parse(raw) if name is not None}
    if kind in ACCOUNT_LINK_MODELS:
        if not url:
            raise ValueError('Lien sécurisé de compte manquant.')
        if 'lien_compte' not in used:
            raw+='\n\n{lien_compte}'
    if kind in ACCOUNT_ID_MODELS:
        if not public_id:
            raise ValueError('Identifiant usager manquant.')
        if 'identifiant' not in used:
            raw+='\n\n'+tr.get('Votre identifiant de borne :','Votre identifiant de borne :')+' {identifiant}'
    if kind=='online_child_welcome' and not {'prenom','nom'}<=used:
        raw+='\n\n{prenom} {nom}'
    notice=tr.get(ACCOUNT_NOTICE,ACCOUNT_NOTICE)
    body=raw.format_map(values)+'\n\n'+notice
    marker='\x01ACCOUNT\x01'
    html_body=html.escape(raw.format_map(dict(values,lien_compte=marker))+'\n\n'+notice).replace('\n','<br>')
    if kind in ACCOUNT_LINK_MODELS:
        label=ACCOUNT_LINK_MODELS[kind]
        html_body=html_body.replace(marker,action_link(url,tr.get(label,label)))
    return subject,body,mail_document(html_body,locale if locale in CATALOGS else 'fr')


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
    escaped=escaped.replace('\x01MANAGE\x01',action_link(url,'Gérer ma réservation'))
    escaped=escaped.replace('\x01INFO\x01','<a href="'+html.escape(information,quote=True)+'">En savoir plus sur cette animation</a>')
    return subject,body,mail_document(escaped)


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
    if db is not None:
        from reservation_calendar import attach
        attach(db,message,row,kind)
    return message


def register(application,a):
    from flask import Blueprint,request,abort,render_template,flash,redirect,url_for
    from i18n import flash
    from markupsafe import Markup
    from evolution_routes import require_csrf,require_team
    bp=Blueprint('reservation_emails',__name__)
    @bp.route('/admin/reglages/structure/emails-reservation',methods=['GET','POST'])
    def settings():
        require_team(True)
        db=a.get_database()
        kind=request.values.get('kind','confirmed')
        if kind not in INTRO and kind not in ONLINE_INTRO:
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
                template={field:validate(request.form.get(field,''),field,kind) for field in ('subject','body')}
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
        is_account=kind in ONLINE_INTRO
        if is_account:
            subject,_,html_body=render_online(kind,template,fake['structure'],
                'https://example.invalid/mon-compte/#lien-de-demonstration',public_id='0420',first_name='Camille',last_name='EXEMPLE')
        else:
            subject,_,html_body=render(fake,kind,template,'https://example.invalid/reservation-fictive')
        return render_template('reservation_email_settings.html',kind=kind,
            model_groups=(('Réservations',INTRO),('Comptes et familles',ONLINE_INTRO)),
            template=template,errors=errors,preview_subject=subject,
            preview_html=Markup(html_body.split('<body>',1)[1].split('</body>',1)[0]),
            variables=sorted(variables_for(kind)),subject_variables=sorted(variables_for(kind,'subject')),
            is_account=is_account,account_link=kind in ACCOUNT_LINK_MODELS,account_id=kind in ACCOUNT_ID_MODELS)
    application.register_blueprint(bp)
