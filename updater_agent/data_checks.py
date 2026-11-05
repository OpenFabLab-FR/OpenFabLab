"""Hash-only database evidence, with separate pre-open and live invariants.

Never compare a live installation as though no legitimate business write could
have occurred. Never interpret a merely present ZIP as a restorable backup.
"""
from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
from .security import Refused, pack
from .diagnostics import step


def quote(name):
    return '"'+name.replace('"','""')+'"'


@contextmanager
def connection(path):
    path=Path(path)
    with step('DATABASE_METADATA'):
        if not path.is_file() or path.is_symlink():
            raise Refused('DATABASE_FILE_MISSING_OR_UNSAFE')
    with step('SQLITE_OPEN'):
        db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=30)
    try:
        with step('SQLITE_READ_BEGIN'):
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
        yield db
    finally:
        db.close()


def hashed(value):
    # SQLite BLOBs have an explicit encoding, never an accidental repr truncation.
    def cell(v):
        return {'blob':v.hex()} if isinstance(v,bytes) else v
    return hashlib.sha256(pack([cell(v) for v in value])).hexdigest()


def table_evidence(db,table,columns=None):
    with step('SQLITE_TABLE_INFO'):info=db.execute('PRAGMA table_info('+quote(table)+')').fetchall()
    columns=columns or [r[1] for r in info]
    primary=[r[1] for r in sorted(info,key=lambda r:r[5]) if r[5] and r[1] in columns]
    with step('SQLITE_TABLE_READ'):rows=db.execute('SELECT '+','.join(quote(c) for c in columns)+' FROM '+quote(table)).fetchall()
    with step('SQLITE_ROW_HASH'):row_hashes=sorted(hashed(row) for row in rows)
    indices=[columns.index(c) for c in primary]
    keys=sorted(hashed([row[i] for i in indices]) for row in rows) if indices else []
    return dict(columns=columns,primary=primary,rows=len(rows),sha256=hashlib.sha256(pack(row_hashes)).hexdigest(),
                keys=keys,row_hashes=row_hashes)


def snapshot(path,expected=None):
    with connection(path) as db:
        with step('SQLITE_USER_VERSION'):schema=db.execute('PRAGMA user_version').fetchone()[0]
        if expected is not None and schema!=expected:
            raise Refused('SQLITE_SCHEMA_MISMATCH')
        with step('SQLITE_INTEGRITY'):
            if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
                raise Refused('SQLITE_INTEGRITY_FAILED')
        with step('SQLITE_FOREIGN_KEYS'):
            if db.execute('PRAGMA foreign_key_check').fetchall():
                raise Refused('SQLITE_FOREIGN_KEYS_FAILED')
        with step('SQLITE_TABLE_LIST'):tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        if not {'users','app_settings','sessions','visitors','resources','billing_records'} <= set(tables):
            raise Refused('OPENFABLAB_DATABASE_INCOMPLETE')
        evidence={t:table_evidence(db,t) for t in tables if t!='app_settings'}
        with step('SQLITE_SETTINGS_READ'):settings={k:hashlib.sha256(str(v).encode()).hexdigest() for k,v in db.execute('SELECT key,value FROM app_settings')}
        return dict(schema=schema,integrity='ok',foreign_keys='ok',tables=evidence,settings=settings)


def compare_before_open(path,before,manifest):
    """Migration must retain every old table/column/row, barring settings additions.

    A future migration rewriting existing business values needs a new reviewed
    agent capability, not a browser-provided permission to ignore differences.
    """
    after=snapshot(path,manifest['schema'])
    allowed_tables=set(manifest.get('new_tables',[]))
    if set(after['tables'])-set(before['tables']) != allowed_tables-set(before['tables']):
        raise Refused('UNEXPECTED_ADDED_TABLE')
    if not set(before['tables']) <= set(after['tables']):
        raise Refused('HISTORICAL_TABLE_MISSING')
    with connection(path) as db:
        for name,old in before['tables'].items():
            if not set(old['columns']) <= set(after['tables'][name]['columns']):
                raise Refused('HISTORICAL_COLUMN_MISSING')
            evidence=table_evidence(db,name,old['columns'])
            if evidence['sha256']!=old['sha256']:
                raise Refused('HISTORICAL_DATA_CHANGED_DURING_MIGRATION')
    for key,value in before['settings'].items():
        if after['settings'].get(key)!=value:
            raise Refused('HISTORICAL_SETTING_CHANGED_DURING_MIGRATION')
    additions=manifest.get('new_settings',{})
    for key in set(after['settings'])-set(before['settings']):
        if key not in additions or after['settings'][key]!=hashlib.sha256(str(additions[key]).encode()).hexdigest():
            raise Refused('UNEXPECTED_ADDED_SETTING')
    return after


# Operational changes are reviewed in this agent version, not a release's broad
# wildcard. Participant-calendar flags are negotiated lazily at first sync.
OPERATIONAL_SETTINGS={
    'reservation_participant_calendar_production':{'0','1'},
    'reservation_participant_calendar_test':{'0','1'},
}
OPERATIONAL_PREFIXES=('reservation_protocol_','reservation_plugin_','reservation_outbound_ready_',
                      'reservation_discord_sync_','reservation_sync_incident_')
MUTABLE_OPERATIONAL_TABLES={'wordpress_relay_state','reservation_sync_state','reservation_outbox',
    'wordpress_action_receipts','automatic_deliveries','reservation_discord_events',
    'family_booking_grants','family_api_nonces','security_events','family_booking_emails',
    'family_age_observations','reservation_sync_nonces'}


def operational_setting(key,value_hash):
    if key in OPERATIONAL_SETTINGS:
        return value_hash in {hashlib.sha256(v.encode()).hexdigest() for v in OPERATIONAL_SETTINGS[key]}
    # Existing operational keys may change with a real signed sync; new keys are
    # never authorized solely by a prefix (the original POST23 incident).
    return False


def compare_live(path,before_public):
    """Check old identities survive without forbidding new registrations/writes."""
    after=snapshot(path,before_public['schema'])
    if set(after['tables'])!=set(before_public['tables']):
        raise Refused('LIVE_DATABASE_STRUCTURE_CHANGED')
    for table,previous in before_public['tables'].items():
        actual=after['tables'].get(table)
        if actual is None or actual['columns']!=previous['columns']:
            raise Refused('LIVE_DATABASE_STRUCTURE_CHANGED')
        if table in MUTABLE_OPERATIONAL_TABLES:
            continue
        if previous['primary']:
            # PK loss, not a changed balance, departure timestamp or attendance
            # is the relevant post-open data-preservation invariant.
            if Counter(previous['keys'])-Counter(actual['keys']):
                raise Refused('HISTORICAL_IDENTITIES_MISSING_AFTER_START')
        elif Counter(previous['row_hashes'])-Counter(actual['row_hashes']):
            raise Refused('HISTORICAL_ROWS_MISSING_AFTER_START')
    for key,previous in before_public['settings'].items():
        actual=after['settings'].get(key)
        if actual==previous:
            continue
        if key in OPERATIONAL_SETTINGS:
            if operational_setting(key,actual):
                continue
        elif key.startswith(OPERATIONAL_PREFIXES) and actual is not None:
            continue
        # No silently accepted edits to historical module, SMTP, PIN, language
        # or backup configuration. Concurrent admin edits can require review.
        raise Refused('HISTORICAL_SETTING_CHANGED_AFTER_START')
    for key in set(after['settings'])-set(before_public['settings']):
        if not operational_setting(key,after['settings'][key]):
            raise Refused('UNEXPECTED_ADDED_SETTING')
    return after
