"""Create the pre-slots schema using the unchanged migrations through schema 12.

No old archive, production database or neighbouring source directory is consulted.
The only migration omitted is the additive schema-13 slots migration.
"""
import sqlite3
from unittest import mock


def create_schema12(path):
    import app
    config = {'TESTING': True, 'SEED_DEMO_USERS': False, 'DATABASE': str(path),
              'ADMIN_PIN': None, 'MODERATOR_PIN': None, 'SECRET_KEY': 'fictional-schema12',
              'WEATHER_ENABLED': False, 'AUTO_CLOSURE_WORKER': False}
    with mock.patch.object(app, 'migrate_animation_slots_schema', lambda database: None):
        app.create_app(config)
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 12
        assert 'booking_mode' not in {r[1] for r in db.execute('PRAGMA table_info(animation_reservation_config)')}
        assert 'slot_uuid' not in {r[1] for r in db.execute('PRAGMA table_info(animation_bookings)')}
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='animation_slots'").fetchone()
        db.execute("INSERT INTO users(public_id,first_name,last_name,active,nationality_normalized,created_at) VALUES('2001','Ancienne','FICTIVE',1,'','2026-01-01')")
        db.execute("INSERT INTO sessions(user_id,check_in,check_out) VALUES(1,'2026-01-01T10:00:00','2026-01-01T11:00:00')")
        db.execute("INSERT INTO visitors(created_at) VALUES('2026-01-01T10:00:00')")
        db.execute("INSERT INTO fablab_services(service_type,title,service_date,start_time,end_time,duration_minutes,created_at,updated_at) VALUES('animation','Ancienne animation fictive','2027-10-08','10:00','12:00',120,'2026-01-01','2026-01-01')")
        db.execute("INSERT INTO animation_reservation_config(service_id,environment,enabled,capacity,updated_at) VALUES(1,'test',1,4,'2026-01-01')")
        for i,status in enumerate(('confirmed','waitlisted','cancelled')):
            db.execute("INSERT INTO animation_bookings(external_uuid,service_id,environment,first_name,last_name,status,link_status,source,created_at,updated_at) VALUES(?,1,'test','Ancien','FICTIF',?,'visitor','online','2026-01-01','2026-01-01')", (str(i),status))
    # Materialize the pre-existing normalization/statistical snapshots at schema 12.
    with mock.patch.object(app, 'migrate_animation_slots_schema', lambda database: None):
        app.create_app(config)
