"""User provenance and optional, privacy-controlled creation notifications."""
import secrets
from datetime import datetime, timezone
from evolution_schema import now, category_label

SOURCES = {'admin':'Administrateur', 'moderator':'Modérateur', 'kiosk':'Auto-inscription sur borne',
           'import':'Migration / import', 'historical':'Historique / inconnue', 'technical':'Technique'}


def create_user(database, values, source, creator=None):
    if source not in SOURCES:
        raise ValueError('Origine de création inconnue.')
    keys = ('public_id','first_name','last_name','active','category','birth_year','gender','city','city_normalized',
            'postal_code','nationality','nationality_normalized','email','phone_country_code','phone')
    cursor = database.execute('INSERT INTO users(' + ','.join(keys) + ',statistics_key,created_at,updated_at,created_source,created_by_role) VALUES(' + ','.join('?' for _ in range(len(keys)+5)) + ')',
                              tuple(values.get(key) for key in keys) + (secrets.token_hex(16),now(),now(),source,creator))
    return cursor.lastrowid


def creation_message(database, user):
    def enabled(key, default='0'):
        row = database.execute('SELECT value FROM app_settings WHERE key=?', ('discord_new_user_' + key,)).fetchone()
        return (row[0] if row else default)=='1'
    if not enabled('enabled'):
        return None
    pieces = ['Nouvel usager créé']
    identity = []
    if enabled('first_name'):
        identity.append(user['first_name'])
    if enabled('last_name'):
        identity.append(user['last_name'])
    elif enabled('last_initial') and user['last_name']:
        identity.append(user['last_name'][0] + '.')
    if identity:
        pieces.append(' '.join(identity))
    if enabled('age') and user['birth_year']:
        pieces.append(str(datetime.now(timezone.utc).year - user['birth_year']) + ' ans')
    if enabled('category'):
        pieces.append('Catégorie : ' + category_label(database,user['category']))
    if enabled('source'):
        pieces.append('Origine : ' + SOURCES.get(user['created_source'],SOURCES['historical']))
    if enabled('time'):
        pieces.append('Création : ' + user['created_at'])
    # No contact, address, ID or QR field is admitted, including in templates.
    return '\n'.join(pieces)
