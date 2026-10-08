"""Shared 2.8.3 presentation/user settings; no reservation decisions."""
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ID_MODES = {
    'automatic_discreet': 'Automatique discret',
    'automatic_visible': 'Automatique visible (recommandé)',
    'customizable': 'Identifiant personnalisable',
}
MONTHS = ('janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet',
          'août', 'septembre', 'octobre', 'novembre', 'décembre')


def setting(db, key, default):
    row = db.execute('SELECT value FROM app_settings WHERE key=?', (key,)).fetchone()
    return row[0] if row else default


def enrollment_mode(db):
    value = setting(db, 'public_id_assignment_mode', 'automatic_discreet')
    return value if value in ID_MODES else 'automatic_discreet'


def attendance_reference(db):
    try:
        value = int(setting(db, 'attendance_reference', '10'))
        return value if 1 <= value <= 10000 else 10
    except (TypeError, ValueError):
        return 10


def validate_reference(value):
    if not re.fullmatch(r'[0-9]{1,5}', value or '') or not 1 <= int(value) <= 10000:
        raise ValueError('Choisissez un seuil entre 1 et 10 000 personnes.')
    return str(int(value))


def local_moment(db, value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    try:
        zone = ZoneInfo(setting(db, 'structure_timezone', 'Europe/Paris'))
    except (ValueError, ZoneInfoNotFoundError):
        zone = ZoneInfo('Europe/Paris')
    return value.astimezone(zone)


def french_datetime(db, value):
    moment = local_moment(db, value)
    return f'{moment.day:02d} {MONTHS[moment.month - 1]} {moment.year} à {moment.hour:02d}h{moment.minute:02d}'


def affiliation_choices(db):
    # Team only; no client contacts, addresses, invoice amounts or public API.
    return db.execute("SELECT id,structure_name FROM billing_clients WHERE TRIM(structure_name)!='' ORDER BY structure_name COLLATE NOCASE,id").fetchall()


def validate_affiliation(db, form):
    name = form.get('affiliation_name', '').strip()
    if len(name) > 160 or any(ord(c) < 32 for c in name):
        raise ValueError('Le nom de structure est limité à 160 caractères, sur une ligne.')
    raw = form.get('affiliation_client_id', '').strip()
    client_id = None
    if raw:
        if not re.fullmatch(r'[0-9]{1,12}', raw):
            raise ValueError('Choisissez une structure disponible.')
        row = db.execute("SELECT id,structure_name FROM billing_clients WHERE id=? AND TRIM(structure_name)!=''", (int(raw),)).fetchone()
        if not row:
            raise ValueError('Cette structure n’est plus disponible. Rechargez la fiche.')
        client_id, name = row['id'], row['structure_name']
    return {'affiliation_client_id': client_id, 'affiliation_name': name}


def save_affiliation(db, user_id, values):
    if 'affiliation_name' in values:
        db.execute('UPDATE users SET affiliation_client_id=?,affiliation_name=? WHERE id=?',
                   (values['affiliation_client_id'], values['affiliation_name'], user_id))
