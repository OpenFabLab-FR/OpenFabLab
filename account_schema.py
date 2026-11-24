"""Additive migration. The online directory starts empty, even on upgrades."""

TABLES = {
    'online_identities': """user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        email TEXT NOT NULL UNIQUE, verified_at INTEGER NOT NULL""",
    'online_requests': """id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('signup','child','claim')),
        data TEXT NOT NULL, email TEXT NOT NULL, owner INTEGER REFERENCES users(id) ON DELETE CASCADE,
        state TEXT NOT NULL CHECK(state IN ('verify','review')), created INTEGER NOT NULL, expires INTEGER NOT NULL""",
    'online_tickets': """digest TEXT PRIMARY KEY, purpose TEXT NOT NULL, address TEXT NOT NULL,
        request_id TEXT REFERENCES online_requests(id) ON DELETE CASCADE,
        owner INTEGER REFERENCES users(id) ON DELETE CASCADE, browser TEXT NOT NULL, expires INTEGER NOT NULL""",
    'online_sessions': """browser TEXT PRIMARY KEY, owner INTEGER NOT NULL REFERENCES online_identities(user_id)
        ON DELETE CASCADE, expires INTEGER NOT NULL, issued INTEGER NOT NULL""",
    'online_limits': """bucket TEXT NOT NULL, window INTEGER NOT NULL, hits INTEGER NOT NULL,
        PRIMARY KEY(bucket,window)""",
    'online_events': """id INTEGER PRIMARY KEY, kind TEXT NOT NULL, request_id TEXT NOT NULL,
        actor TEXT NOT NULL, created INTEGER NOT NULL""",
    'online_mail': """id INTEGER PRIMARY KEY, kind TEXT NOT NULL, address TEXT NOT NULL,
        request_id TEXT REFERENCES online_requests(id) ON DELETE CASCADE, owner INTEGER REFERENCES users(id) ON DELETE CASCADE,
        browser TEXT NOT NULL, created INTEGER NOT NULL, retry INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
        locale TEXT NOT NULL DEFAULT 'fr' CHECK(locale IN ('fr','en','de','es','fi'))""",
}
SETTINGS = {'online_accounts_enabled':'0','online_signup_enabled':'0','online_approval':'manual',
            'online_relay_environment':'production','online_session_minutes':'20','online_ticket_minutes':'15',
            'online_header_tasks':'1','online_account_url':'','online_mail_signature':'',
            **{'online_discord_'+kind:'0' for kind in ('signup_review','activated','family_review','denied')}}

def ensure(db):
    from maintenance_planning import validate as previous
    previous(db)
    for name, fields in TABLES.items():
        db.execute(f'CREATE TABLE {name} ({fields})')
    db.execute('CREATE INDEX online_review_queue ON online_requests(state,kind,created)')
    db.execute('CREATE INDEX online_pending_address ON online_requests(email,kind,state)')
    db.execute('CREATE INDEX online_ticket_expiry ON online_tickets(expires)')
    db.execute('CREATE INDEX online_mail_next ON online_mail(retry,id)')
    db.executemany('INSERT INTO app_settings(key,value) VALUES(?,?)', SETTINGS.items())
    validate(db)

def validate(db):
    from maintenance_planning import validate as previous
    previous(db)
    for name,fields in TABLES.items():
        actual=db.execute('SELECT sql FROM sqlite_schema WHERE name=? AND type=?',(name,'table')).fetchone()
        if not actual or actual[0] != f'CREATE TABLE {name} ({fields})':
            raise RuntimeError('Schéma 29 des comptes en ligne incomplet.')
