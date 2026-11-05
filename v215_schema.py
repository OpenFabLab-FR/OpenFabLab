"""Schema26, additive and inside the existing migration transaction."""

def validate(db):
    expected = {
        'resources': {'archived_at','availability_mode'},
        'resource_bookings': {'handed_over_at', 'returned_at'},
        'billing_records': {'handed_over_at', 'returned_at', 'rental_user_id'},
        'user_booking_restrictions': {'restriction_uuid', 'user_id', 'revoked_at'},
        'resource_documents': {'document_uuid', 'sha256', 'revision', 'public'},
        'resource_document_links': {'resource_uuid', 'document_uuid'},
    }
    for table, columns in expected.items():
        actual = {row[1] for row in db.execute('PRAGMA table_info(' + table + ')')}
        if not columns <= actual:
            raise RuntimeError('Structure incompatible avec le schéma26 : ' + table)

def ensure(db):
    additions={
        'resources':{'availability_mode':"TEXT NOT NULL DEFAULT 'on_site' CHECK(availability_mode IN ('on_site','rental'))"},
        'resource_bookings':{'handed_over_at':'TEXT','returned_at':'TEXT'},
        'billing_records':{'handed_over_at':'TEXT','returned_at':'TEXT',
                           'rental_user_id':'INTEGER REFERENCES users(id) ON DELETE SET NULL'},
    }
    for table,columns in additions.items():
        present={r[1] for r in db.execute('PRAGMA table_info('+table+')')}
        for name,definition in columns.items():
            if name not in present:db.execute('ALTER TABLE '+table+' ADD COLUMN '+name+' '+definition)
    db.execute('''CREATE TABLE IF NOT EXISTS user_booking_restrictions(
        restriction_uuid TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        starts_on TEXT NOT NULL,ends_on TEXT NOT NULL,reason TEXT NOT NULL,
        actor_role TEXT NOT NULL,created_at TEXT NOT NULL,revoked_at TEXT,
        CHECK(ends_on>=starts_on))''')
    db.execute('CREATE INDEX IF NOT EXISTS restriction_user_days ON user_booking_restrictions(user_id,starts_on,ends_on)')
    db.execute('''CREATE TABLE IF NOT EXISTS resource_documents(
        document_uuid TEXT PRIMARY KEY,title TEXT NOT NULL,language TEXT NOT NULL,
        sha256 TEXT NOT NULL UNIQUE,size_bytes INTEGER NOT NULL CHECK(size_bytes>0),
        public INTEGER NOT NULL DEFAULT 0 CHECK(public IN(0,1)),
        revision INTEGER NOT NULL DEFAULT 1,archived_at TEXT,
        created_at TEXT NOT NULL,updated_at TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS resource_document_links(
        resource_uuid TEXT NOT NULL REFERENCES resources(resource_uuid) ON DELETE RESTRICT,
        document_uuid TEXT NOT NULL REFERENCES resource_documents(document_uuid) ON DELETE RESTRICT,
        created_at TEXT NOT NULL,PRIMARY KEY(resource_uuid,document_uuid))''')
    for key,value in {'resource_public_base_url':'','resource_public_pages_enabled':'0',
                      'setup_completed':'1','setup_progress':'{}'}.items():
        db.execute('INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)',(key,value))
