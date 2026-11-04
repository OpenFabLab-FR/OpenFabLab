"""Real previous-release database and isolated complete backup restoration."""
import hashlib,json,os,sqlite3,tempfile,unittest
from pathlib import Path
import app,family_model,private_backup
from tests.test_migration_restore import snapshot

class Migration214(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        supplied=os.environ.get('OFL_SCHEMA22_FIXTURE')
        cls.fixture=Path(supplied) if supplied else None
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='migration214-');self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'persistent'/'openfablab.db';self.path.parent.mkdir()
        if not self.fixture or not self.fixture.is_file():self.skipTest('Generate the fictional fixture with source22_fixture.py and set OFL_SCHEMA22_FIXTURE.')
        with sqlite3.connect(self.fixture) as source,sqlite3.connect(self.path) as target:source.backup(target)
        self.db=sqlite3.connect(self.path);self.db.row_factory=sqlite3.Row;self.db.execute('PRAGMA foreign_keys=ON');self.addCleanup(self.db.close)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],22)
    def test_real_stable_migration_preserves_every_existing_value(self):
        before=snapshot(self.db);backup=family_model.backup_before(self.db,self.path)
        self.assertIsNotNone(backup)
        with sqlite3.connect(backup) as saved:self.assertEqual(saved.execute('PRAGMA user_version').fetchone()[0],22)
        family_model.migrate(self.db);after=snapshot(self.db)
        for table,rows in before.items():
            if table=='app_settings':
                settings=dict(after[table]);self.assertTrue(all(settings.get(k)==v for k,v in rows))
            else:self.assertEqual(rows,after[table],table)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],23)
        self.assertEqual(dict(self.db.execute('SELECT key,value FROM app_settings'))['reservation_reminder_enabled'],'0')
        self.assertEqual([tuple(r) for r in self.db.execute('PRAGMA integrity_check')],[('ok',)])
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])
        stable=snapshot(self.db);family_model.migrate(self.db);self.assertEqual(stable,snapshot(self.db))
    def test_interrupted_real_source_stays_schema22_and_recoverable(self):
        before=snapshot(self.db)
        def fail(db):db.execute("UPDATE app_settings SET value='MUST_ROLL_BACK' WHERE key='kiosk_sound_volume'");raise RuntimeError('FICTIONAL_INTERRUPTION')
        with self.assertRaises(RuntimeError):family_model.migrate(self.db,fail_after=fail)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],22);self.assertEqual(before,snapshot(self.db))
        family_model.migrate(self.db);self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],23)
    def test_complete_backup_is_restored_and_reopened_not_just_unzipped(self):
        family_model.migrate(self.db);before=snapshot(self.db);archive=Path(self.temp.name)/'private-fictional.zip'
        secret=self.path.parent/'.openfablab_sync_secret';secret.write_text('FICTITIOUS-ONLY')
        result=private_backup.create_backup(self.path,archive);self.assertEqual(result['sqlite_schema'],23)
        private_backup.validate_backup(archive);restored=Path(self.temp.name)/'restored'/'openfablab.db'
        private_backup.restore_backup(archive,restored)
        with sqlite3.connect(restored) as db:
            self.assertEqual(snapshot(db),before);self.assertEqual(db.execute('PRAGMA integrity_check').fetchall(),[('ok',)])
            self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())
        self.assertEqual((restored.parent/secret.name).read_text(),'FICTITIOUS-ONLY')
        application=app.create_app(dict(TESTING=True,DATABASE=str(restored),SECRET_KEY='FICTIONAL',WEATHER_ENABLED=False))
        self.assertEqual(application.test_client().get('/sante').status_code,200)
    def test_new_installation_defaults_are_safe_and_compatible(self):
        path=Path(self.temp.name)/'new'/'new.db';application=app.create_app(dict(TESTING=True,SEED_DEMO_USERS=False,DATABASE=str(path),SECRET_KEY='FICTIONAL',WEATHER_ENABLED=False))
        with sqlite3.connect(path) as db:
            settings=dict(db.execute('SELECT key,value FROM app_settings'))
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],23)
            for key in ('module_maintenance','module_memberships'):self.assertEqual(settings[key],'0')
            self.assertEqual(settings['reservation_reminder_enabled'],'auto');self.assertEqual(settings['reservation_reminder_hours'],'48')
            self.assertEqual(settings['kiosk_language'],'fr');self.assertEqual(settings['openlab_public_enabled'],'0')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM users').fetchone()[0],0)

def load_tests(loader,suite,pattern):return loader.loadTestsFromTestCase(Migration214)
