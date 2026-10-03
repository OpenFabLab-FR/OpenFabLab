"""Transactional 2.7 evolution, preserving historical keys and business tables."""
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

HISTORICAL_CATEGORIES = {'user':'Usager', 'volunteer':'Bénévole', 'voluntary':'Volontaire',
                        'fabmanager':'Fabmanager', 'intern':'Stagiaire', 'staff':'Personnel'}
NEW_CATEGORIES = {'user':'Usager', 'volunteer':'Bénévole', 'manager':'Manager'}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def backup_before_evolution(database, path):
    """Called before any initialization writes; SQLite backup includes its WAL."""
    version = database.execute('PRAGMA user_version').fetchone()[0]
    if version>14:
        raise RuntimeError('Schéma plus récent que cette version ; démarrage refusé.')
    exists = database.execute("SELECT 1 FROM sqlite_master WHERE name='user_categories'").fetchone()
    if not version or exists:
        return None
    database.commit()
    directory = Path(path).parent / 'migration-backups'
    directory.mkdir(mode=0o700, exist_ok=True)
    target = directory / ('before-2.7-schema-' + str(version) + '-' + uuid4().hex + '.db')
    with sqlite3.connect(target) as copy:
        database.backup(copy)
        if copy.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or copy.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('Sauvegarde pré-migration invalide ; migration refusée.')
    target.chmod(0o600)
    return target


def migrate(database, new_installation=False):
    if database.execute("SELECT 1 FROM sqlite_master WHERE name='user_categories'").fetchone():
        database.execute('PRAGMA user_version=14')
        return
    database.commit()
    database.execute('PRAGMA foreign_keys=OFF')
    try:
        database.execute('BEGIN IMMEDIATE')
        database.execute('CREATE TABLE user_categories(category_key TEXT PRIMARY KEY, name TEXT NOT NULL, normalized_name TEXT NOT NULL UNIQUE, color TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)), sort_order INTEGER NOT NULL DEFAULT 0, is_default INTEGER NOT NULL DEFAULT 0 CHECK(is_default IN(0,1)), created_at TEXT NOT NULL, updated_at TEXT NOT NULL)')
        for order, (key, name) in enumerate((NEW_CATEGORIES if new_installation else HISTORICAL_CATEGORIES).items()):
            database.execute('INSERT INTO user_categories VALUES(?,?,?,?,?,?,?,?,?)',
                             (key, name, name.casefold(), '#16849c', 1, order, int(key=='user'), now(), now()))
        # Replace only the fixed category CHECK; every other column, value,
        # unique index, trigger and foreign key stays intact. No rename of users
        # before DROP: dependent references must continue pointing to users.
        original = database.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()[0]
        rewritten = re.sub(r"CHECK\s*\(category\s+IN\s*\([^)]*\)\)", 'REFERENCES user_categories(category_key)', original, flags=re.I)
        if rewritten == original:
            raise RuntimeError('Contrainte historique de catégorie inconnue : migration refusée.')
        rewritten = re.sub(r'CREATE TABLE\s+["`\[]?users["`\]]?(?=\s*\()', 'CREATE TABLE users_v27', rewritten, count=1, flags=re.I)
        if 'CREATE TABLE users_v27' not in rewritten:
            raise RuntimeError('Définition users inconnue ; migration refusée.')
        definitions = [row[0] for row in database.execute("SELECT sql FROM sqlite_master WHERE tbl_name='users' AND type='index' AND sql IS NOT NULL")]
        triggers = database.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND instr(sql,'users')>0").fetchall()
        for trigger in triggers:
            database.execute('DROP TRIGGER "' + trigger[0].replace('"','""') + '"')
        sequence = database.execute("SELECT seq FROM sqlite_sequence WHERE name='users'").fetchone()
        database.execute(rewritten)
        database.execute('INSERT INTO users_v27 SELECT * FROM users')
        database.execute('DROP TABLE users')
        database.execute('ALTER TABLE users_v27 RENAME TO users')
        for definition in definitions:
            database.execute(definition)
        for trigger in triggers:
            database.execute(trigger[1])
        if sequence:
            database.execute("UPDATE sqlite_sequence SET seq=? WHERE name='users'", (sequence[0],))
        database.execute('CREATE UNIQUE INDEX category_default_unique ON user_categories(is_default) WHERE is_default=1')
        for name, sql in [('created_source', "TEXT NOT NULL DEFAULT 'historical'"), ('created_by_role', 'TEXT'),
                          ('welcome_sent_at', 'TEXT'), ('welcome_status', 'TEXT')]:
            database.execute('ALTER TABLE users ADD COLUMN ' + name + ' ' + sql)
        statements = [
            'CREATE TABLE resource_types(type_key TEXT PRIMARY KEY, name TEXT NOT NULL, normalized_name TEXT NOT NULL UNIQUE, color TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)), sort_order INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)',
            'CREATE TABLE authorizations(authorization_uuid TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT \'\', active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)), created_at TEXT NOT NULL)',
            'CREATE TABLE resources(resource_uuid TEXT PRIMARY KEY, type_key TEXT NOT NULL REFERENCES resource_types(type_key), name TEXT NOT NULL, description TEXT NOT NULL DEFAULT \'\', active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)), color TEXT, approval_required INTEGER NOT NULL DEFAULT 0 CHECK(approval_required IN(0,1)), price_cents INTEGER NOT NULL DEFAULT 0 CHECK(price_cents>=0), legacy_machine_key TEXT UNIQUE, required_authorization TEXT REFERENCES authorizations(authorization_uuid), created_at TEXT NOT NULL, updated_at TEXT NOT NULL)',
            'CREATE TABLE user_authorizations(grant_uuid TEXT PRIMARY KEY, user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, authorization_uuid TEXT NOT NULL REFERENCES authorizations(authorization_uuid), performed_on TEXT NOT NULL, validated_by TEXT NOT NULL, validator_role TEXT NOT NULL, expires_on TEXT, revoked_at TEXT, revoked_reason TEXT, created_at TEXT NOT NULL)',
            'CREATE TABLE resource_bookings(booking_uuid TEXT PRIMARY KEY, resource_uuid TEXT NOT NULL REFERENCES resources(resource_uuid), user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, starts_at TEXT NOT NULL, ends_at TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN(\'requested\',\'confirmed\',\'performed\',\'refused\',\'cancelled\')), amount_cents INTEGER NOT NULL DEFAULT 0 CHECK(amount_cents>=0), billing_record_id INTEGER UNIQUE REFERENCES billing_records(id) ON DELETE SET NULL, service_id INTEGER UNIQUE REFERENCES fablab_services(id) ON DELETE SET NULL, override_reason TEXT, created_by_role TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)',
            'CREATE INDEX resource_booking_time_index ON resource_bookings(resource_uuid, starts_at, ends_at, status)',
            'CREATE TABLE evolution_audit(id INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT NOT NULL, entity_key TEXT NOT NULL, action TEXT NOT NULL, actor_role TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT \'{}\', created_at TEXT NOT NULL)',
        ]
        for statement in statements:
            database.execute(statement)
        database.execute('INSERT INTO resource_types VALUES(?,?,?,?,?,?,?,?)', ('machine','Machine','machine','#16849c',1,0,now(),now()))
        sync_legacy_machines(database)
        if database.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('Clés étrangères invalides ; migration annulée.')
        database.execute('PRAGMA user_version=14')
        database.commit()
    except Exception:
        database.rollback()
        raise
    finally:
        database.execute('PRAGMA foreign_keys=ON')


def audit(database, kind, key, action, role, details=None):
    database.execute('INSERT INTO evolution_audit(entity_type,entity_key,action,actor_role,details_json,created_at) VALUES(?,?,?,?,?,?)',
                     (kind, str(key), action, role, json.dumps(details or {}, ensure_ascii=False), now()))


def sync_legacy_machines(database):
    for row in database.execute('SELECT * FROM rental_catalog').fetchall():
        database.execute('INSERT OR IGNORE INTO resources(resource_uuid,type_key,name,active,legacy_machine_key,created_at,updated_at) VALUES(?,\'machine\',?,?,?,?,?)',
                         (str(uuid4()), row['name'], int(row['active'] and not row['archived']), row['machine_key'], now(), now()))


def categories(database, include_hidden=False):
    return database.execute('SELECT * FROM user_categories' + ('' if include_hidden else ' WHERE active=1') + ' ORDER BY sort_order,name').fetchall()


def default_category(database):
    row = database.execute('SELECT category_key FROM user_categories WHERE active=1 AND is_default=1').fetchone()
    if row is None:
        raise ValueError('Une catégorie active par défaut est nécessaire.')
    return row[0]


def category_label(database, key):
    row = database.execute('SELECT name FROM user_categories WHERE category_key=?', (key,)).fetchone()
    return row[0] if row else HISTORICAL_CATEGORIES.get(key, key or 'Inconnu')


def save_category(database, name, color, active=True, is_default=False, key=None, order=0):
    name = str(name).strip()
    if not name or len(name)>80 or not re.fullmatch('#[0-9a-fA-F]{6}', color):
        raise ValueError('Nom (80 caractères maximum) et couleur de catégorie requis.')
    if is_default and not active:
        raise ValueError('La catégorie par défaut doit rester active.')
    if not isinstance(order,int) or not 0<=order<=100000:
        raise ValueError('Ordre de catégorie invalide.')
    old = database.execute('SELECT * FROM user_categories WHERE category_key=?', (key,)).fetchone() if key else None
    if old and old['is_default'] and not is_default:
        raise ValueError('Choisissez d’abord une autre catégorie par défaut.')
    key = key or 'cat_' + uuid4().hex
    if is_default:
        database.execute('UPDATE user_categories SET is_default=0 WHERE is_default=1')
    database.execute('INSERT INTO user_categories VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(category_key) DO UPDATE SET name=excluded.name,normalized_name=excluded.normalized_name,color=excluded.color,active=excluded.active,sort_order=excluded.sort_order,is_default=excluded.is_default,updated_at=excluded.updated_at',
                     (key,name,name.casefold(),color,int(active),order,int(is_default),now(),now()))
    return key


def remove_category(database, key, replacement=None):
    current = database.execute('SELECT * FROM user_categories WHERE category_key=?', (key,)).fetchone()
    if not current:
        raise ValueError('Catégorie inconnue.')
    if current['is_default']:
        raise ValueError('Changez la catégorie par défaut avant suppression.')
    used = database.execute('SELECT COUNT(*) FROM users WHERE category=?', (key,)).fetchone()[0]
    history = database.execute('SELECT 1 FROM sessions WHERE statistical_category=? LIMIT 1', (key,)).fetchone()
    if used:
        target = database.execute('SELECT 1 FROM user_categories WHERE category_key=? AND active=1', (replacement,)).fetchone()
        if not target or replacement==key:
            raise ValueError('Choisissez une catégorie active de remplacement.')
        database.execute('UPDATE users SET category=? WHERE category=?', (replacement,key))
    if used or history:
        database.execute('UPDATE user_categories SET active=0,updated_at=? WHERE category_key=?', (now(),key))
        return 'archived'
    database.execute('DELETE FROM user_categories WHERE category_key=?', (key,))
    return 'deleted'
