"""Additive schema21; no enrollment, credit, message or activation on upgrade."""
DEFAULTS={
    'module_memberships':'0','membership_control':'informative',
    'membership_require_period':'0','membership_require_credit':'0',
    'membership_exempt_categories':'[]','membership_notice_days':'14',
    'membership_low_threshold':'2','membership_smtp_enabled':'0','membership_discord_enabled':'0',
    'membership_hourly_shortfall':'available',
    'kiosk_sound_enabled':'1','kiosk_sound_volume':'50','kiosk_sound_ambience':'auto',
    'kiosk_sound_countdown':'1',
    'discord_sync_delay_minutes':'10','discord_sync_recovery_enabled':'0',
}
def ensure(db):
    statements=(
    '''CREATE TABLE IF NOT EXISTS membership_plans(
      plan_id TEXT PRIMARY KEY,name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',
      kind TEXT NOT NULL CHECK(kind IN('period','credits')),scope TEXT NOT NULL CHECK(scope IN('individual','family')),
      unit TEXT NOT NULL CHECK(unit IN('none','passage','session','hour','halfday')),
      price_cents INTEGER NOT NULL CHECK(price_cents BETWEEN 0 AND 100000000),
      terms_json TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1 CHECK(active IN(0,1)),created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS membership_grants(
      grant_id TEXT PRIMARY KEY,plan_id TEXT REFERENCES membership_plans(plan_id) ON DELETE SET NULL,
      owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,terms_json TEXT NOT NULL,
      starts_on TEXT NOT NULL,ends_on TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'active' CHECK(status IN('active','suspended')),
      balance INTEGER NOT NULL DEFAULT 0 CHECK(balance BETWEEN 0 AND 1000000000000),
      revision INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,
      billing_record_id INTEGER REFERENCES billing_records(id) ON DELETE SET NULL)''',
    '''CREATE TABLE IF NOT EXISTS membership_beneficiaries(
      grant_id TEXT NOT NULL REFERENCES membership_grants(grant_id) ON DELETE CASCADE,
      user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      created_at TEXT NOT NULL,ended_at TEXT,PRIMARY KEY(grant_id,user_id))''',
    '''CREATE TABLE IF NOT EXISTS membership_preferences(
      user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      primary_plan_id TEXT REFERENCES membership_plans(plan_id) ON DELETE SET NULL,
      exempt INTEGER NOT NULL DEFAULT 0 CHECK(exempt IN(0,1)),reason TEXT NOT NULL DEFAULT '')''',
    '''CREATE TABLE IF NOT EXISTS membership_ledger(
      operation_key TEXT PRIMARY KEY,request_hash TEXT NOT NULL,
      grant_id TEXT NOT NULL REFERENCES membership_grants(grant_id) ON DELETE RESTRICT,
      user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
      kind TEXT NOT NULL CHECK(kind IN('initial','recharge','consumption','correction','reversal','renewal','status','beneficiaries','selection','reconciliation')),
      quantity INTEGER NOT NULL,balance_after INTEGER NOT NULL CHECK(balance_after>=0),
      actor TEXT NOT NULL,reason TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,
      reversal_of TEXT UNIQUE REFERENCES membership_ledger(operation_key) ON DELETE RESTRICT,charge_key TEXT)''',
    '''CREATE TABLE IF NOT EXISTS membership_session_links(
      session_id INTEGER PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
      grant_id TEXT REFERENCES membership_grants(grant_id) ON DELETE SET NULL,
      user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      review_required INTEGER NOT NULL DEFAULT 0 CHECK(review_required IN(0,1)),created_at TEXT NOT NULL)''',
    '''CREATE TABLE IF NOT EXISTS membership_consumptions(
      charge_key TEXT PRIMARY KEY,grant_id TEXT NOT NULL REFERENCES membership_grants(grant_id) ON DELETE RESTRICT,
      user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
      session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
      requested INTEGER NOT NULL CHECK(requested>=0),settled INTEGER NOT NULL CHECK(settled>=0),
      remaining INTEGER NOT NULL CHECK(remaining>=0),revision INTEGER NOT NULL DEFAULT 1,
      updated_at TEXT NOT NULL,waived INTEGER NOT NULL DEFAULT 0 CHECK(waived>=0),CHECK(requested=settled+remaining+waived))''',
    '''CREATE TABLE IF NOT EXISTS membership_notifications(
      notification_key TEXT PRIMARY KEY,grant_id TEXT NOT NULL REFERENCES membership_grants(grant_id) ON DELETE CASCADE,
      event_type TEXT NOT NULL,channel TEXT NOT NULL CHECK(channel IN('smtp','discord')),
      state TEXT NOT NULL CHECK(state IN('pending','sending','sent','failed','uncertain','cancelled')),
      created_at TEXT NOT NULL,claimed_at TEXT,finished_at TEXT,last_error TEXT)''',
    '''CREATE TABLE IF NOT EXISTS membership_notice_state(
      grant_id TEXT PRIMARY KEY REFERENCES membership_grants(grant_id) ON DELETE CASCADE,
      states_json TEXT NOT NULL DEFAULT '{}',sequence INTEGER NOT NULL DEFAULT 0)''',
    '''CREATE TABLE IF NOT EXISTS calendar_notes(
      event_kind TEXT NOT NULL,event_key TEXT NOT NULL,occurrence_date TEXT NOT NULL,
      note TEXT NOT NULL CHECK(length(note)<=2000),updated_at TEXT NOT NULL,
      PRIMARY KEY(event_kind,event_key,occurrence_date))''',
    '''CREATE TABLE IF NOT EXISTS wordpress_sync_incidents(
      environment TEXT PRIMARY KEY CHECK(environment IN('production','test')),
      sequence INTEGER NOT NULL DEFAULT 0,started_at TEXT,channels_json TEXT NOT NULL DEFAULT '{}',
      alert_key TEXT,active INTEGER NOT NULL DEFAULT 0 CHECK(active IN(0,1)))''',
    '''CREATE TABLE IF NOT EXISTS kiosk_action_receipts(
      request_key TEXT PRIMARY KEY,payload_hash TEXT NOT NULL,result_json TEXT NOT NULL,
      created_at TEXT NOT NULL)''',
    'CREATE INDEX IF NOT EXISTS membership_grant_dates ON membership_grants(status,ends_on,starts_on)',
    'CREATE INDEX IF NOT EXISTS membership_user_benefits ON membership_beneficiaries(user_id,ended_at)',
    'CREATE INDEX IF NOT EXISTS membership_ledger_grant ON membership_ledger(grant_id,created_at)',
    'CREATE INDEX IF NOT EXISTS membership_notice_pending ON membership_notifications(state,created_at)',
    'CREATE INDEX IF NOT EXISTS kiosk_receipts_date ON kiosk_action_receipts(created_at)',
    '''CREATE TRIGGER IF NOT EXISTS calendar_notes_deleted_service AFTER DELETE ON fablab_services
       BEGIN DELETE FROM calendar_notes WHERE event_kind IN('animation','reservation','rental') AND event_key=CAST(OLD.id AS TEXT); END''',
    '''CREATE TRIGGER IF NOT EXISTS calendar_notes_deleted_resource AFTER DELETE ON resource_bookings
       BEGIN DELETE FROM calendar_notes WHERE event_kind='reservation' AND event_key=OLD.booking_uuid; END''',
    '''CREATE TRIGGER IF NOT EXISTS calendar_notes_deleted_training AFTER DELETE ON user_authorizations
       BEGIN DELETE FROM calendar_notes WHERE event_kind='training' AND event_key=OLD.grant_uuid; END''',
    )
    for statement in statements:db.execute(statement)
    for key,value in DEFAULTS.items():db.execute('INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)',(key,value))
