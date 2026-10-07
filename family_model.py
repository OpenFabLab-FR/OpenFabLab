"""Private user relationships and age policy; no independent family accounts.

Year-only ages intentionally retain the historical reference-year method.
Exact dates use the local calendar birthday. Neither autonomy nor eligibility
to be responsible is a declaration of legal majority.
"""
import json
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

SCHEMA = 17
POLICIES = {'none':'Aucun', 'email':'E-mail', 'phone':'Téléphone',
            'either':'E-mail ou téléphone', 'both':'E-mail et téléphone'}
DEFAULTS = {'family_autonomy_age':'15', 'family_responsible_age':'18',
            'family_contact_dependent':'none', 'family_contact_autonomous':'none',
            'family_contact_responsible':'both', 'home_title':'Aujourd’hui au FabLab',
            'reservation_account_required':'0'}
LABELS = {'dependent':'Responsable nécessaire', 'autonomous':'Participant autonome',
          'responsible':'Peut être responsable', 'unknown':'Âge à renseigner'}


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def setting(db, key, default=''):
    row = db.execute('SELECT value FROM app_settings WHERE key=?', (key,)).fetchone()
    return row[0] if row else default


def local_day(db):
    return datetime.now(ZoneInfo(setting(db, 'structure_timezone', 'Europe/Paris'))).date()


def backup_before(db, path):
    """Coherent offline PRE before *any* initialization writes, not a DB copy."""
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version > SCHEMA:
        raise RuntimeError('Base plus récente que la candidate 2.8.2 ; démarrage refusé.')
    extra_needed = (version == 15 and not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='family_booking_groups'").fetchone())
    if version not in (14, 15, 16) and not extra_needed:
        return None
    root = Path(path).parent / 'migration-backups'
    root.mkdir(mode=0o700, exist_ok=True)
    target = root / ('before-2.8-schema-' + str(version) + '-' + uuid4().hex + '.db')
    with sqlite3.connect(target) as copy:
        db.backup(copy)
        if copy.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or copy.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('Sauvegarde avant migration invalide ; démarrage refusé.')
    target.chmod(0o600)
    return target


def migrate(db, fail_after=None):
    """Additive schema 14/15/16→17; guest birthday is a booking snapshot."""
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version not in (14, 15, 16, SCHEMA):
        # Earlier schemas must first complete the existing evolution migration.
        # In particular, never stamp an incomplete old database as schema 15.
        if version > SCHEMA:
            raise RuntimeError('Schéma plus récent non pris en charge.')
        return
    db.commit()
    try:
        db.execute('BEGIN IMMEDIATE')
        columns={row['name'] for row in db.execute('PRAGMA table_info(users)')}
        if 'birth_date' not in columns:
            db.execute('ALTER TABLE users ADD COLUMN birth_date TEXT')
        if 'birth_precision' not in columns:
            db.execute("ALTER TABLE users ADD COLUMN birth_precision TEXT NOT NULL DEFAULT 'year' CHECK(birth_precision IN('year','exact'))")
        db.execute('''CREATE TABLE IF NOT EXISTS user_family_links (
            link_uuid TEXT PRIMARY KEY,
            member_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            responsible_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL, ended_at TEXT,
            CHECK(member_id != responsible_id))''')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS family_active_pair ON user_family_links(member_id,responsible_id) WHERE ended_at IS NULL')
        db.execute('CREATE INDEX IF NOT EXISTS family_responsible_index ON user_family_links(responsible_id,ended_at)')
        db.execute('''CREATE TABLE IF NOT EXISTS family_booking_requests(
            request_key TEXT PRIMARY KEY, request_hash TEXT NOT NULL,
            owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            group_uuid TEXT NOT NULL UNIQUE, source TEXT NOT NULL,
            created_at TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS family_booking_grants(
            token_hash TEXT PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            service_id INTEGER NOT NULL REFERENCES fablab_services(id) ON DELETE CASCADE,
            environment TEXT NOT NULL, expires_at INTEGER NOT NULL)''')
        db.execute('CREATE TABLE IF NOT EXISTS family_api_nonces(nonce_hash TEXT PRIMARY KEY, expires_at INTEGER NOT NULL)')
        db.execute('''CREATE TABLE IF NOT EXISTS family_age_observations(
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            was_responsible INTEGER NOT NULL DEFAULT 0,
            notified_at TEXT, notification_state TEXT)''')
        db.execute('''CREATE TABLE IF NOT EXISTS calendar_visibility(
            event_kind TEXT NOT NULL, event_key TEXT NOT NULL, occurrence_date TEXT NOT NULL,
            hidden INTEGER NOT NULL CHECK(hidden IN(0,1)), updated_at TEXT NOT NULL,
            PRIMARY KEY(event_kind,event_key,occurrence_date))''')
        from family_waitlist import ensure_schema
        ensure_schema(db)
        from outbound_actions import ensure_schema as ensure_outbound_schema
        ensure_outbound_schema(db)
        booking_columns={row['name'] for row in db.execute('PRAGMA table_info(animation_bookings)')}
        if 'guest_birth_date' not in booking_columns:
            db.execute('ALTER TABLE animation_bookings ADD COLUMN guest_birth_date TEXT')
        for key, value in DEFAULTS.items():
            db.execute('INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)', (key,value))
        # Baseline existing adults: a migration is not a birthday notification.
        today = local_day(db)
        for user in db.execute('SELECT * FROM users').fetchall():
            db.execute('INSERT OR IGNORE INTO family_age_observations(user_id,was_responsible) VALUES(?,?)',
                       (user['id'], int(state(db,user,today)=='responsible')))
        if fail_after:
            fail_after(db)
        if db.execute('PRAGMA foreign_key_check').fetchall() or db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Migration famille refusée : intégrité invalide.')
        db.execute('PRAGMA user_version=17')
        db.commit()
    except Exception:
        db.rollback()
        raise


def age(user, today):
    user = dict(user)
    if user.get('birth_date'):
        born = date.fromisoformat(user['birth_date'])
        return today.year-born.year-((today.month,today.day)<(born.month,born.day))
    return today.year-int(user['birth_year']) if user.get('birth_year') else None


def state(db, user, today=None):
    years = age(user, today or local_day(db))
    if years is None:
        return 'unknown'
    if years < int(setting(db,'family_autonomy_age','15')):
        return 'dependent'
    if years < int(setting(db,'family_responsible_age','18')):
        return 'autonomous'
    return 'responsible'


def missing_contacts(policy, user):
    user = dict(user)
    email = bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', user.get('email') or ''))
    phone = len(re.sub(r'\D','',user.get('phone') or '')) >= 8
    if policy == 'either':
        return [] if email or phone else ['e-mail ou téléphone']
    return ([label for label, present in [('e-mail',email),('téléphone',phone)] if not present]
            if policy=='both' else ([] if policy=='none' or (email if policy=='email' else phone)
                                   else ['e-mail' if policy=='email' else 'téléphone']))


def contact_policy(db, user, today=None):
    status = state(db,user,today)
    return setting(db,'family_contact_'+status,'both' if status in ('responsible','unknown') else 'none')


def eligible(db, user, today=None):
    return bool(user['active'] and state(db,user,today)=='responsible'
                and not missing_contacts(setting(db,'family_contact_responsible','both'),user))


def validate_settings(values):
    result = {k:str(values.get(k,v)).strip() for k,v in DEFAULTS.items() if k.startswith('family_')}
    try:
        autonomy, responsible = int(result['family_autonomy_age']), int(result['family_responsible_age'])
        if not 0 <= autonomy <= responsible <= 120:
            raise ValueError
    except ValueError:
        raise ValueError('Âges requis de 0 à 120 ans, avec autonomie ≤ responsable. Ces seuils ne définissent pas la majorité juridique.')
    for key in ('family_contact_dependent','family_contact_autonomous','family_contact_responsible'):
        if result[key] not in POLICIES:
            raise ValueError('Règle de coordonnées inconnue.')
    return result


def responsibles(db, member_id):
    return db.execute('SELECT u.*,l.link_uuid FROM user_family_links l JOIN users u ON u.id=l.responsible_id WHERE l.member_id=? AND l.ended_at IS NULL ORDER BY u.last_name,u.first_name', (member_id,)).fetchall()


def members(db, responsible_id):
    return db.execute('SELECT u.*,l.link_uuid FROM user_family_links l JOIN users u ON u.id=l.member_id WHERE l.responsible_id=? AND l.ended_at IS NULL ORDER BY u.last_name,u.first_name', (responsible_id,)).fetchall()


def link(db, member_id, responsible_id):
    person = db.execute('SELECT * FROM users WHERE id=?', (responsible_id,)).fetchone()
    if member_id == responsible_id or not person or not eligible(db,person):
        raise ValueError('Responsable non éligible : vérifiez son âge, son activité et ses coordonnées.')
    if not db.execute('SELECT 1 FROM users WHERE id=?', (member_id,)).fetchone():
        raise ValueError('Usager inconnu.')
    existing = db.execute('SELECT link_uuid FROM user_family_links WHERE member_id=? AND responsible_id=? AND ended_at IS NULL', (member_id,responsible_id)).fetchone()
    if existing:
        return existing[0]
    key = str(uuid4())
    db.execute('INSERT INTO user_family_links VALUES(?,?,?,?,NULL)', (key,member_id,responsible_id,timestamp()))
    return key


def end_link(db, key, user_id):
    changed = db.execute('UPDATE user_family_links SET ended_at=? WHERE link_uuid=? AND (member_id=? OR responsible_id=?) AND ended_at IS NULL', (timestamp(),key,user_id,user_id))
    if changed.rowcount != 1:
        raise ValueError('Rattachement déjà terminé ou inconnu.')


def apply_details(db, user_id, values):
    db.execute('UPDATE users SET birth_date=?,birth_precision=? WHERE id=?',
               (values.get('birth_date'), 'exact' if values.get('birth_date') else 'year', user_id))
    for responsible_id in values.get('responsible_ids',[]):
        link(db,user_id,responsible_id)
    user=db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone()
    db.execute('INSERT OR IGNORE INTO family_age_observations(user_id,was_responsible) VALUES(?,?)',
               (user_id,int(state(db,user)=='responsible')))


def validate_form(db, form, data, errors, current_id=None, public=False):
    """Only new records are required to comply; historical accounts remain usable."""
    current = db.execute('SELECT * FROM users WHERE id=?',(current_id,)).fetchone() if current_id else None
    exact = str(form.get('birth_date','')).strip()
    if current and 'birth_date' not in form:
        exact = current['birth_date'] or ''
    if form.get('is_minor')=='1' and not exact:
        errors.append('La date de naissance complète est obligatoire pour un mineur.')
    if exact:
        try:
            born = date.fromisoformat(exact)
            if born > local_day(db) or born.year < 1900:
                raise ValueError
            data['birth_year'] = born.year
        except ValueError:
            errors.append('Date de naissance invalide.')
            exact = ''
    data['birth_date'] = exact or None
    data['birth_precision'] = 'exact' if exact else 'year'
    data['responsible_ids'] = []
    raw_ids = form.getlist('responsible_ids') if hasattr(form,'getlist') else form.get('responsible_ids',[])
    if isinstance(raw_ids,str):
        raw_ids = [raw_ids]
    for value in raw_ids:
        try:
            key = int(value)
            responsible = db.execute('SELECT * FROM users WHERE id=?',(key,)).fetchone()
            if not responsible or not eligible(db,responsible) or key==current_id:
                raise ValueError
            if public:
                from flask import session
                grant = session.get('family_enrollment_guardian',{})
                import time
                if key != grant.get('id') or grant.get('until',0)<time.time():
                    raise ValueError
            data['responsible_ids'].append(key)
        except (ValueError,TypeError):
            errors.append('Rattachement non autorisé ou responsable non éligible.')
    if not current_id:
        if data.get('birth_year') and local_day(db).year-int(data['birth_year'])<18 and not exact:
            errors.append('Pour un nouvel usager mineur, cochez « Je suis mineur » et indiquez sa date de naissance.')
        if state(db,data)=='dependent' and not data['responsible_ids']:
            errors.append('Choisissez au moins un responsable rattaché avant de créer cette fiche.')
        missing = missing_contacts(contact_policy(db,data),data)
        if missing:
            errors.append('Coordonnées obligatoires : '+', '.join(missing)+'.')


def observe_ages(db, today=None, notify=None):
    """At-most-once durable claim before delivery; never replay uncertain sends.

Inactive integration leaves a pending transition for a later enabled check.
No birthdays are sent for already-eligible migration baselines. One local-day
scan marker, plus per-user claims, protects concurrent workers/restarts.
"""
    today = today or local_day(db)
    if setting(db,'family_age_checked_on') == today.isoformat():
        return
    db.commit()
    db.execute('BEGIN IMMEDIATE')
    if setting(db,'family_age_checked_on') == today.isoformat():
        db.rollback(); return
    notifications = []
    for user in db.execute('SELECT * FROM users WHERE active=1').fetchall():
        row = db.execute('SELECT * FROM family_age_observations WHERE user_id=?',(user['id'],)).fetchone()
        reached = state(db,user,today)=='responsible'
        if row is None:
            # New adult accounts are not age transitions.
            db.execute('INSERT INTO family_age_observations(user_id,was_responsible) VALUES(?,?)',(user['id'],int(reached)))
            continue
        if reached and not row['was_responsible']:
            missing = missing_contacts(setting(db,'family_contact_responsible','both'),user)
            if missing and notify and not row['notified_at']:
                message = ('🎂 Usager devenu responsable possible\n'+user['first_name']+' '+user['last_name']
                           +' a atteint le seuil permettant d’être responsable.\nCoordonnées à compléter : '
                           +', '.join(missing)+'.\nLes rattachements sont conservés à titre informatif.')
                db.execute("UPDATE family_age_observations SET notified_at=?,notification_state='claimed',was_responsible=1 WHERE user_id=? AND notified_at IS NULL",(timestamp(),user['id']))
                notifications.append((user['id'],message))
            elif not missing:
                db.execute('UPDATE family_age_observations SET was_responsible=1 WHERE user_id=?',(user['id'],))
    db.execute("INSERT INTO app_settings(key,value) VALUES('family_age_checked_on',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(today.isoformat(),))
    db.commit()
    for user_id,message in notifications:
        try:
            notify(message)
            result='sent'
        except (OSError,ValueError):
            result='uncertain'
        db.execute('UPDATE family_age_observations SET notification_state=? WHERE user_id=?',(result,user_id))
        db.commit()
