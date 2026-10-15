"""Additive schema20 extensions inside the existing initialization transaction."""
from datetime import datetime,timezone

DEFAULTS={'reservation_waitlist_limit_mode':'automatic','reservation_waitlist_limit_value':'0',
    'retention_contact_notice_enabled':'0','retention_contact_notice_days':'7'}
CLIENT_CATEGORIES=(('company','Entreprise'),('association','Association'),('school','Établissement scolaire'),
    ('authority','Collectivité'),('independent','Indépendant / micro-entrepreneur'),('individual','Particulier'),('other','Autre'))

def ensure(db):
    columns={row[1] for row in db.execute('PRAGMA table_info(animation_reservation_config)')}
    if 'waitlist_limit_mode' not in columns:
        db.execute("ALTER TABLE animation_reservation_config ADD COLUMN waitlist_limit_mode TEXT NOT NULL DEFAULT 'general' CHECK(waitlist_limit_mode IN('general','custom','unlimited'))")
    if 'waitlist_limit_value' not in columns:
        db.execute('ALTER TABLE animation_reservation_config ADD COLUMN waitlist_limit_value INTEGER CHECK(waitlist_limit_value BETWEEN 0 AND 100000)')
    db.execute('''CREATE TABLE IF NOT EXISTS waitlist_full_state(
        service_id INTEGER NOT NULL REFERENCES fablab_services(id) ON DELETE CASCADE,
        environment TEXT NOT NULL,slot_key TEXT NOT NULL DEFAULT '',
        is_full INTEGER NOT NULL DEFAULT 0,sequence INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(service_id,environment,slot_key))''')
    if 'presentation_json' not in {row[1] for row in db.execute('PRAGMA table_info(reservation_discord_events)')}:
        db.execute("ALTER TABLE reservation_discord_events ADD COLUMN presentation_json TEXT NOT NULL DEFAULT '{}'")
    existed=db.execute("SELECT 1 FROM sqlite_master WHERE name='client_categories' AND type='table'").fetchone()
    db.execute('''CREATE TABLE IF NOT EXISTS client_categories(
        category_key TEXT PRIMARY KEY,name TEXT NOT NULL,normalized_name TEXT NOT NULL UNIQUE,
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)),sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''')
    if not existed:
        from participant_search import normalized
        now=datetime.now(timezone.utc).isoformat(timespec='seconds')
        db.executemany('INSERT INTO client_categories VALUES(?,?,?,1,?,?,?)',
            [(key,name,normalized(name),order,now,now) for order,(key,name) in enumerate(CLIENT_CATEGORIES)])
    if 'category_key' not in {row[1] for row in db.execute('PRAGMA table_info(billing_clients)')}:
        db.execute('ALTER TABLE billing_clients ADD COLUMN category_key TEXT REFERENCES client_categories(category_key)')
    db.execute('''CREATE TABLE IF NOT EXISTS retention_contact_notices(
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,deadline TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN('pending','sending','sent','failed','uncertain','cancelled')),
        created_at TEXT NOT NULL,claimed_at TEXT,finished_at TEXT,last_error TEXT,
        PRIMARY KEY(user_id,deadline))''')
    for statement in (
        'CREATE INDEX IF NOT EXISTS sessions_analysis_time ON sessions(check_in,check_out)',
        'CREATE INDEX IF NOT EXISTS sessions_analysis_jd ON sessions(julianday(check_in))',
        'CREATE INDEX IF NOT EXISTS sessions_analysis_category ON sessions(statistical_category,check_in)',
        'CREATE INDEX IF NOT EXISTS sessions_analysis_user ON sessions(user_id,check_in)',
        'CREATE INDEX IF NOT EXISTS sessions_analysis_cohort ON sessions(statistical_user_key,check_in)',
        'CREATE INDEX IF NOT EXISTS client_category_filter ON billing_clients(category_key)',
        'CREATE INDEX IF NOT EXISTS waitlist_scope_count ON animation_bookings(service_id,environment,slot_uuid,status)',
        'CREATE INDEX IF NOT EXISTS retention_notices_state ON retention_contact_notices(state,deadline)'):
        db.execute(statement)
    for key,value in DEFAULTS.items():db.execute('INSERT OR IGNORE INTO app_settings VALUES(?,?)',(key,value))
    # Seed old scopes without a retrospective notification or business mutation.
    from waitlist_limits import seed_states
    seed_states(db)
