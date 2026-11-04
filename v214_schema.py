"""Schema 23: additive equipment log, reminders and dated opening exceptions.

Called inside the existing family migration transaction. No new migration engine,
no identity copies and no catalogue/booking/history rewrite.
"""
from datetime import datetime,timezone

DEFAULTS={
    'module_maintenance':'0','kiosk_machine_information':'both',
    'kiosk_language':'fr','kiosk_languages':'fr,en','kiosk_language_idle_minutes':'10',
    'maintenance_discord_enabled':'0','maintenance_reminder_hour':'9',
    'openlab_public_enabled':'0','reservation_reminder_hours':'48',
    'reservation_calendar_enabled':'1',
}

def ensure(db):
    from uuid import uuid4
    statements=[
        '''CREATE TABLE IF NOT EXISTS machine_condition(
            resource_uuid TEXT PRIMARY KEY REFERENCES resources(resource_uuid) ON DELETE RESTRICT,
            status TEXT NOT NULL DEFAULT 'operational' CHECK(status IN('operational','maintenance','out_of_service')),
            status_since TEXT NOT NULL,announce INTEGER NOT NULL DEFAULT 0 CHECK(announce IN(0,1)),
            public_listed INTEGER NOT NULL DEFAULT 0 CHECK(public_listed IN(0,1)),
            public_reason TEXT NOT NULL DEFAULT '',return_estimate TEXT,
            publish_return INTEGER NOT NULL DEFAULT 0 CHECK(publish_return IN(0,1)),
            updated_at TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS machine_interventions(
            intervention_uuid TEXT PRIMARY KEY,
            resource_uuid TEXT NOT NULL REFERENCES resources(resource_uuid) ON DELETE RESTRICT,
            performed_on TEXT NOT NULL,kind TEXT NOT NULL CHECK(kind IN('care','preventive','repair','other')),
            description TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>0))''',
        '''CREATE TABLE IF NOT EXISTS machine_history(
            id INTEGER PRIMARY KEY,resource_uuid TEXT NOT NULL REFERENCES resources(resource_uuid) ON DELETE RESTRICT,
            entity_uuid TEXT NOT NULL,action TEXT NOT NULL,actor TEXT NOT NULL,
            before_json TEXT NOT NULL,after_json TEXT NOT NULL,created_at TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS machine_reminders(
            reminder_uuid TEXT PRIMARY KEY,resource_uuid TEXT NOT NULL REFERENCES resources(resource_uuid) ON DELETE RESTRICT,
            intervention_uuid TEXT REFERENCES machine_interventions(intervention_uuid) ON DELETE RESTRICT,
            due_on TEXT NOT NULL,subject TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN('pending','done','cancelled')),
            revision INTEGER NOT NULL DEFAULT 1,actor TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS openlab_exceptions(
            day TEXT PRIMARY KEY,kind TEXT NOT NULL CHECK(kind IN('closed','extra','hours')),
            starts_at TEXT,ends_at TEXT,public_title TEXT NOT NULL DEFAULT '',
            publish INTEGER NOT NULL DEFAULT 0 CHECK(publish IN(0,1)),
            actor TEXT NOT NULL,updated_at TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS automatic_deliveries(
            delivery_key TEXT PRIMARY KEY,kind TEXT NOT NULL CHECK(kind IN('maintenance','animation_reminder')),
            state TEXT NOT NULL CHECK(state IN('claimed','sent','uncertain','skipped')),
            claimed_at TEXT NOT NULL,finished_at TEXT,error_code TEXT)''',
        'CREATE INDEX IF NOT EXISTS machine_interventions_chronology ON machine_interventions(resource_uuid,performed_on)',
        'CREATE INDEX IF NOT EXISTS machine_reminder_due ON machine_reminders(state,due_on)',
    ]
    for statement in statements:db.execute(statement)
    for key,value in DEFAULTS.items():
        db.execute('INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)',(key,value))
    db.execute("INSERT OR IGNORE INTO app_settings VALUES('reservation_reminder_enabled',?)",('0' if db.execute('PRAGMA user_version').fetchone()[0]>0 else 'auto',))
    db.execute("INSERT OR IGNORE INTO app_settings VALUES('calendar_instance_uuid',?)",(str(uuid4()),))
    # Upgrading never sends retrospective mail, regardless of historical dormant
    # reminder settings. New installs choose the SMTP-aware default at runtime.
    stamp=datetime.now(timezone.utc).isoformat(timespec='seconds')
    db.execute("INSERT OR IGNORE INTO app_settings VALUES('v214_reminders_available_since',?)",(stamp,))
