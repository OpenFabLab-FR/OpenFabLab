"""Schema 27: preserve machine conditions, add a private report and decision log."""

TABLES = ('resource_problem_reports', 'resource_problem_decisions', 'user_profile_activity')
SETTINGS = {'resource_reports_enabled': '0', 'resource_reports_discord': '0'}


def validate(db):
    from v215_schema import validate as previous
    previous(db)
    condition=db.execute("SELECT sql FROM sqlite_schema WHERE type='table' AND name='machine_condition'").fetchone()
    expected={
        'resource_problem_reports': {'report_id','resource_uuid','description','received_at','rate_key','state','intervention_uuid'},
        'resource_problem_decisions': {'id','report_id','action','role','reason','created_at'},
        'user_profile_activity': {'id','user_id','created_at'},
    }
    if not condition or "'unavailable'" not in condition[0] or any(
        not columns <= {r[1] for r in db.execute(f'PRAGMA table_info({name})')} for name,columns in expected.items()
    ):
        raise RuntimeError('Schéma 27 incomplet.')


def ensure(db):
    # This table has no incoming FK, trigger or explicit index in schema 26.
    # Check rather than silently losing local extensions during the rebuild.
    old = db.execute("SELECT sql FROM sqlite_schema WHERE name='machine_condition'").fetchone()
    if not old:
        raise RuntimeError('Conditions de ressources absentes.')
    clause = "CHECK(status IN('operational','maintenance','out_of_service'))"
    if old[0].count(clause) != 1 or db.execute(
            "SELECT 1 FROM sqlite_schema WHERE tbl_name='machine_condition' AND type IN('index','trigger') AND sql IS NOT NULL").fetchone():
        raise RuntimeError('Structure des conditions inattendue ; migration refusée.')
    for name, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'").fetchall():
        quoted = '"' + name.replace('"', '""') + '"'
        if any(fk[2].casefold() == 'machine_condition' for fk in db.execute('PRAGMA foreign_key_list(' + quoted + ')')):
            raise RuntimeError('Une extension référence les conditions de ressources.')
    columns = ('resource_uuid,status,status_since,announce,public_listed,public_reason,'
               'return_estimate,publish_return,updated_at')
    if ','.join(r[1] for r in db.execute('PRAGMA table_info(machine_condition)')) != columns:
        raise RuntimeError('Colonnes des conditions inattendues.')
    sql = old[0].replace('machine_condition', 'machine_condition_v27', 1).replace(
        clause, "CHECK(status IN('operational','maintenance','out_of_service','unavailable'))")
    db.execute(sql)
    db.execute(f'INSERT INTO machine_condition_v27({columns}) SELECT {columns} FROM machine_condition')
    if db.execute('SELECT * FROM machine_condition EXCEPT SELECT * FROM machine_condition_v27').fetchone():
        raise RuntimeError('Les conditions de ressources ne sont pas identiques.')
    db.execute('DROP TABLE machine_condition')
    db.execute('ALTER TABLE machine_condition_v27 RENAME TO machine_condition')
    db.execute('''CREATE TABLE resource_problem_reports(
        report_id TEXT PRIMARY KEY, resource_uuid TEXT NOT NULL REFERENCES resources(resource_uuid) ON DELETE RESTRICT,
        description TEXT NOT NULL CHECK(length(description) BETWEEN 1 AND 500), received_at TEXT NOT NULL,
        rate_key TEXT, state TEXT NOT NULL DEFAULT 'new' CHECK(state IN('new','assigned','dismissed','resolved')),
        intervention_uuid TEXT UNIQUE REFERENCES machine_interventions(intervention_uuid) ON DELETE RESTRICT)''')
    db.execute('CREATE INDEX reports_resource_recent ON resource_problem_reports(resource_uuid,received_at DESC)')
    db.execute('CREATE INDEX reports_state_recent ON resource_problem_reports(state,received_at DESC)')
    db.execute('CREATE INDEX reports_recent ON resource_problem_reports(received_at DESC)')
    db.execute('CREATE INDEX reports_rate ON resource_problem_reports(rate_key,received_at) WHERE rate_key IS NOT NULL')
    db.execute('''CREATE TABLE resource_problem_decisions(
        id INTEGER PRIMARY KEY, report_id TEXT NOT NULL REFERENCES resource_problem_reports(report_id) ON DELETE RESTRICT,
        action TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN('admin','moderator')),
        reason TEXT NOT NULL CHECK(length(reason)<=500), created_at TEXT NOT NULL)''')
    db.execute('CREATE INDEX report_decisions_history ON resource_problem_decisions(report_id,id)')
    db.execute('''CREATE TABLE user_profile_activity(
        id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL)''')
    db.execute('CREATE INDEX user_profile_activity_recent ON user_profile_activity(created_at DESC,id DESC)')
    for name,table,columns in (
        ('dashboard_users_recent','users','created_at DESC,id DESC'),
        ('dashboard_booking_recent','resource_bookings','created_at DESC,booking_uuid DESC'),
        ('dashboard_animation_recent','animation_bookings','created_at DESC,external_uuid DESC'),
        ('dashboard_animation_group','animation_bookings','group_uuid,created_at DESC,external_uuid DESC'),
        ('dashboard_audit_recent','evolution_audit','entity_type,created_at DESC,id DESC'),
        ('dashboard_audit_entity','evolution_audit','entity_type,entity_key,id'),
        ('dashboard_machine_recent','machine_history','created_at DESC,id DESC'),
        ('dashboard_quotes_recent','billing_records','created_at DESC,id DESC'),
        ('dashboard_quotes_signed','billing_records','quote_signed_at DESC,id DESC'),
        ('dashboard_invoices_recent','billing_records','invoice_date DESC,id DESC'),
        ('dashboard_invoices_paid','billing_records','paid_at DESC,id DESC'),
    ):
        db.execute(f'CREATE INDEX {name} ON {table}({columns})')
    for key, value in SETTINGS.items():
        db.execute('INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)', (key,value))
    validate(db)
