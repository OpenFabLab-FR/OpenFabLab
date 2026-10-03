"""Optional native SMTP. Credentials are private files, never SQLite settings."""
import html
import io
import json
import os
import re
import secrets
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
import segno

EMAIL = re.compile(r'[^\s@]+@[^\s@]+\.[^\s@]+')
FIELDS = {'structure_name','first_name','last_name','public_id','contact','website'}
SUBJECT = 'Bienvenue à {{structure_name}}'
BODY = ('Bonjour {{first_name}},\n\nBienvenue à {{structure_name}}.\n'
        'Votre identifiant : {{public_id}}\nVotre QR Code est joint à ce message.\n\n{{contact}}\n{{website}}')


def path_for(database_path):
    return Path(database_path).with_name('.openfablab_smtp.json')


def load_config(database_path):
    try:
        value = json.loads(path_for(database_path).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def load_public_config(database_path):
    """Only non-secret fields may be passed to an administrator's form."""
    return {key: value for key, value in load_config(database_path).items() if key != 'password'}


def validate_config(value):
    value = dict(value)
    if not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', str(value.get('host', ''))):
        raise ValueError('Serveur SMTP invalide.')
    try:
        value['port'] = int(value.get('port', 587))
        if not 1 <= value['port'] <= 65535:
            raise ValueError()
    except (TypeError, ValueError):
        raise ValueError('Port SMTP invalide.') from None
    if value.get('security') not in {'starttls','tls'}:
        raise ValueError('Choisissez TLS ou STARTTLS.')
    for key in ('username','sender_name','sender_email','reply_to'):
        text = str(value.get(key, ''))
        if any(ord(c)<32 for c in text) or len(text)>254:
            raise ValueError('En-tête SMTP invalide.')
        value[key] = text
    if not EMAIL.fullmatch(value['sender_email']) or (value['reply_to'] and not EMAIL.fullmatch(value['reply_to'])):
        raise ValueError('Adresse expéditeur ou Répondre à invalide.')
    return value


def save_config(database_path, value):
    value = validate_config(value)
    path = path_for(database_path)
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8) + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(value, stream)
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def validate_template(subject, body):
    if not subject.strip() or not body.strip() or len(subject)>240 or len(body)>8000 or '\n' in subject or '\r' in subject:
        raise ValueError('Sujet et message de bienvenue requis (texte brut).')
    unknown = set(re.findall(r'{{\s*([^{}]+?)\s*}}', subject + body)) - FIELDS
    if unknown:
        raise ValueError('Variable inconnue : ' + ', '.join(sorted(unknown)))


def render(text, values):
    return re.sub(r'{{\s*([^{}]+?)\s*}}', lambda m: str(values[m[1]]), text)


def qr_png(public_id):
    output = io.BytesIO()
    segno.make_qr(str(public_id), error='h').save(output, kind='png', scale=12, border=4)
    return output.getvalue()


def build_message(config, recipient, values, subject=SUBJECT, body=BODY):
    config = validate_config(config)
    validate_template(subject, body)
    if not EMAIL.fullmatch(str(recipient or '')):
        raise ValueError('Adresse destinataire valide requise.')
    subject, body = render(subject, values), render(body, values)
    if '\n' in subject or '\r' in subject:
        raise ValueError('Sujet invalide.')
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = (config['sender_name'] + ' <' + config['sender_email'] + '>') if config['sender_name'] else config['sender_email']
    message['To'] = recipient
    if config['reply_to']:
        message['Reply-To'] = config['reply_to']
    message.set_content(body)
    # HTML generated solely from escaped text; no executable template engine.
    cid = secrets.token_hex(16) + '@openfablab'
    message.add_alternative('<!doctype html><html><body><p>' + html.escape(body).replace('\n','<br>')
                            + '</p><img width="240" height="240" alt="Votre QR Code" src="cid:' + cid + '"></body></html>', subtype='html')
    png = qr_png(values['public_id'])
    message.get_payload()[1].add_related(png, maintype='image', subtype='png', cid='<' + cid + '>')
    message.add_attachment(png, maintype='image', subtype='png', filename='OpenFabLab-QR.png')
    return message


def send(config, message):
    from runtime_policy import require_external
    require_external()
    config = validate_config(config)
    context = ssl.create_default_context()
    factory = smtplib.SMTP_SSL if config['security']=='tls' else smtplib.SMTP
    options = {'timeout':10}
    if config['security']=='tls':
        options['context'] = context
    with factory(config['host'], config['port'], **options) as smtp:
        if config['security']=='starttls':
            smtp.ehlo(); smtp.starttls(context=context); smtp.ehlo()
        if config['username']:
            smtp.login(config['username'], str(config.get('password','')))
        if smtp.send_message(message):
            raise smtplib.SMTPException('Destinataire refusé')


def send_welcome(database, database_path, user):
    from runtime_policy import external_allowed
    if not external_allowed(database_path):
        return False
    def setting(key, default=''):
        row = database.execute('SELECT value FROM app_settings WHERE key=?', (key,)).fetchone()
        return row[0] if row else default
    values = {'structure_name':setting('structure_name','Mon FabLab'), 'first_name':user['first_name'],
              'last_name':user['last_name'], 'public_id':user['public_id'],
              'contact':setting('structure_email'), 'website':setting('structure_website')}
    try:
        message = build_message(load_config(database_path), user['email'], values,
                                setting('welcome_subject', SUBJECT), setting('welcome_body', BODY))
        send(load_config(database_path), message)
    except (OSError, ValueError, smtplib.SMTPException):
        database.execute("UPDATE users SET welcome_status='failed' WHERE id=?", (user['id'],))
        database.commit()
        return False
    from evolution_schema import now
    database.execute("UPDATE users SET welcome_sent_at=?,welcome_status='sent' WHERE id=?", (now(),user['id']))
    database.commit()
    return True
