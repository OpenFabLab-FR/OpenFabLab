"""Reusable migration and restore contract, exclusively synthetic local installations."""
import hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path
from tests.test_families import FamilyTests
import app,family_model as family,memberships,private_backup as backup
import animation_attendance as attendance

def snapshot(db,exclude=()):
    tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name") if r[0] not in exclude]
    return {table:sorted([tuple(row) for row in db.execute('SELECT * FROM '+table)],key=repr) for table in tables}

class MigrationRestoreTests(unittest.TestCase):
    def setUp(self):
        self.f=FamilyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db=self.f.db;self.path=Path(self.f.f.database_path)
        group=self.f.book([self.f.a,self.f.c],staff=True)
        attendance.manual(self.db,self.f.service,group['booking_uuids'][0],'present','admin')
        attendance.set_walkins(self.db,self.f.service,3,'admin')
        self.f.book([self.f.teen],owner=self.f.teen);self.f.book([self.f.older],owner=self.f.older)
        self.f.book([self.f.b,self.f.d],staff=True)
        with self.db:
            self.db.execute("INSERT INTO sessions(user_id,check_in,check_out,entry_method) VALUES(?,'2026-08-14T10:00:00+00:00','2026-08-14T12:00:00+00:00','id')",(self.f.a,))
            self.db.execute("INSERT INTO visitors(created_at) VALUES('2026-08-14T11:00:00+00:00')")
            for key,value in [('fake-preserved-secret','synthetic-not-a-real-secret'),('kiosk_sound_enabled','0'),('kiosk_sound_volume','40'),('retention_contact_years','2'),('reservation_discord_sync_error','1')]:app.write_setting(self.db,key,value)
        plan=memberships.save_plan(self.db,dict(name='Crédits fictifs',kind='credits',scope='individual',unit='passage',quantity='10',validity_unit='years',validity_value='1'))
        memberships.assign(self.db,plan,self.f.a,[self.f.a],'2026-01-01','synthetic-grant')
        self.f.f.login_admin()
        response=self.f.client.post('/admin/facturation/nouveau',data=dict(quote_date='2026-08-24',client_contact='Camille FICTIF',client_structure='Association Exemple',address_line='1 voie Fictive',postal_code='00000',city='Ville Fictive',phone='0000000000',email='test@example.invalid',title='Atelier fictif',description='Exemple',activity_date='2026-09-15',activity_time_details='9 h à 12 h',participants='8',rate_category='normal',rate_unit='hourly',rate_quantity='2',travel_quantity='0',consumable_mode='included',consumable_quantity='0'))
        if response.status_code!=302:raise AssertionError('Synthetic billing fixture creation failed')
        record=self.db.execute('SELECT id FROM billing_records').fetchone()
        self.assertIsNotNone(record)
        self.assertEqual(self.f.client.post(f'/admin/facturation/{record[0]}/signer').status_code,302)
        self.assertEqual(self.f.client.post(f'/admin/facturation/{record[0]}/creer-facture').status_code,302)
        self.assertTrue(self.db.execute('SELECT invoice_number FROM billing_records WHERE id=?',(record[0],)).fetchone()[0])

    def make_schema21(self):
        with self.db:
            for suffix in ('insert','update','delete'):self.db.execute('DROP TRIGGER attendance_total_'+suffix)
            self.db.execute('DROP TABLE animation_walkins');self.db.execute('DROP TABLE animation_attendance_origin')
            self.db.execute('DROP INDEX animation_attendance_users')
            self.db.execute("DELETE FROM app_settings WHERE key LIKE 'animation_auto_presence_%'")
            self.db.execute('PRAGMA user_version=21')

    def integrity(self,db):
        self.assertEqual([tuple(r) for r in db.execute('PRAGMA integrity_check')],[('ok',)])
        self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_new_installation_schema22_no_business_seed_and_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'empty.db'
            app.create_app(dict(TESTING=True,SEED_DEMO_USERS=False,DATABASE=str(path),SECRET_KEY='fictive'))
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],22)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM users').fetchone()[0],0)
                self.assertEqual(dict(db.execute('SELECT key,value FROM app_settings'))['module_memberships'],'0')
                self.integrity(db)

    def test_migration21_preserves_all_existing_tables_values_and_secrets(self):
        self.make_schema21();before=snapshot(self.db,{'app_settings'})
        preferences=dict(self.db.execute('SELECT key,value FROM app_settings'))
        self.assertTrue(before['membership_ledger']);self.assertTrue(before['billing_records'])
        self.assertTrue(before['sessions']);self.assertTrue(before['visitors']);self.assertTrue(before['user_family_links'])
        family.migrate(self.db);after=snapshot(self.db)
        for table,rows in before.items():self.assertEqual(after[table],rows,table)
        settings=dict(self.db.execute('SELECT key,value FROM app_settings'))
        self.assertTrue(all(settings.get(key)==value for key,value in preferences.items()))
        self.assertEqual(self.db.execute('SELECT quantity FROM animation_walkins WHERE service_id=?',(self.f.service,)).fetchone()[0],3)
        self.integrity(self.db)

    def test_repeat_migration_is_idempotent(self):
        before=snapshot(self.db);family.migrate(self.db);family.migrate(self.db)
        self.assertEqual(before,snapshot(self.db));self.integrity(self.db)

    def test_exception_rolls_back_schema_and_data(self):
        self.make_schema21();before=snapshot(self.db)
        def fail(db):
            db.execute("UPDATE app_settings SET value='must-rollback' WHERE key='fake-preserved-secret'")
            raise RuntimeError('Synthetic interruption')
        with self.assertRaises(RuntimeError):family.migrate(self.db,fail_after=fail)
        self.assertEqual(before,snapshot(self.db));self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],21)
        family.migrate(self.db);self.integrity(self.db)

    def test_future_unknown_schema_refused_without_modification(self):
        with self.db:self.db.execute('PRAGMA user_version=99')
        before=snapshot(self.db)
        with self.assertRaises(RuntimeError):family.backup_before(self.db,self.path)
        with self.assertRaises(RuntimeError):family.migrate(self.db)
        self.assertEqual(snapshot(self.db),before);self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],99)

    def test_schema22_upgrade_does_not_create_migration_backup(self):
        before=snapshot(self.db);self.assertIsNone(family.backup_before(self.db,self.path))
        family.migrate(self.db);self.assertEqual(before,snapshot(self.db))

    def test_complete_backup_restores_in_isolated_new_directory_and_opens(self):
        before=snapshot(self.db);self.db.commit()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=root/'synthetic.zip';target=root/'isolated'/'openfablab.db'
            secret=self.path.parent/'.openfablab_sync_secret';secret.write_text('fictive-wordpress-secret-only')
            manifest=backup.create_backup(self.path,archive)
            self.assertEqual(manifest['sqlite_schema'],22);backup.validate_backup(archive)
            backup.restore_backup(archive,target)
            with sqlite3.connect(target) as db:
                self.integrity(db);self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],22)
                self.assertEqual(snapshot(db),before)
            self.assertEqual((target.parent/secret.name).read_text(),'fictive-wordpress-secret-only')
            application=app.create_app(dict(TESTING=True,DATABASE=str(target),SECRET_KEY='fictive'))
            self.assertEqual(application.test_client().get('/sante').status_code,200)
        self.assertFalse(root.exists());self.assertEqual(snapshot(self.db),before)

def load_tests(loader,suite,pattern):return loader.loadTestsFromTestCase(MigrationRestoreTests)
