"""Real approved 2.14 schema23 fixture; never a production backup."""
import os,sqlite3,tempfile,unittest
from pathlib import Path
import family_model,private_backup
from tests.test_migration_restore import snapshot

class Migration2141(unittest.TestCase):
    def setUp(self):
        path=os.environ.get('OFL_SCHEMA23_FIXTURE')
        if not path or not Path(path).is_file():self.skipTest('Supply an entirely fictional schema23 fixture.')
        self.temp=tempfile.TemporaryDirectory(prefix='v2141-migration-');self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'persistent/source.db';self.path.parent.mkdir()
        with sqlite3.connect('file:'+path+'?mode=ro',uri=True) as source,sqlite3.connect(self.path) as dest:source.backup(dest)
        self.db=sqlite3.connect(self.path);self.addCleanup(self.db.close);self.db.row_factory=sqlite3.Row;self.db.execute('PRAGMA foreign_keys=ON')
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],23)
        machine=self.db.execute('SELECT resource_uuid FROM resources LIMIT 1').fetchone()[0]
        with self.db:
            self.db.execute("INSERT INTO machine_interventions VALUES('old-preventive',?,'2026-10-30','preventive','Historique fictif','moderator','2026-10-30T10:00:00Z','2026-10-30T10:00:00Z',3)",(machine,))
            self.db.execute("INSERT INTO machine_reminders VALUES('linked-old',?,'old-preventive','2026-12-01','Rappel fictif','pending',2,'admin','2026-10-30T10:00:00Z','2026-10-30T10:00:00Z')",(machine,))
    def test_real_schema23_to24_preserves_all_values_and_linked_reminders(self):
        before=snapshot(self.db);rowids={name:[tuple(r) for r in self.db.execute('SELECT rowid,* FROM '+name)] for name in ('machine_interventions','machine_reminders')}
        backup=family_model.backup_before(self.db,self.path);self.assertTrue(backup)
        family_model.migrate(self.db)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],24);self.assertEqual(before,snapshot(self.db))
        for name,rows in rowids.items():self.assertEqual(rows,[tuple(r) for r in self.db.execute('SELECT rowid,* FROM '+name)])
        self.assertEqual(self.db.execute('PRAGMA foreign_keys').fetchone()[0],1);self.assertFalse(self.db.execute('PRAGMA foreign_key_check').fetchall())
        self.db.execute("UPDATE machine_interventions SET kind='inspection' WHERE intervention_uuid='old-preventive'");self.db.commit()
        with sqlite3.connect(backup) as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],23)
    def test_rollback_restores_constraint_data_and_schema23(self):
        before=snapshot(self.db);ddl=[tuple(r) for r in self.db.execute('SELECT name,sql FROM sqlite_master ORDER BY name')]
        def fail(db):raise RuntimeError('FICTIONAL_INTERRUPTION_AFTER_DDL')
        with self.assertRaises(RuntimeError):family_model.migrate(self.db,fail)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],23);self.assertEqual(snapshot(self.db),before)
        self.assertEqual(ddl,[tuple(r) for r in self.db.execute('SELECT name,sql FROM sqlite_master ORDER BY name')]);self.assertFalse(self.db.execute('PRAGMA foreign_key_check').fetchall())
        family_model.migrate(self.db);self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],24)
    def test_idempotent_and_no_parallel_business_storage(self):
        family_model.migrate(self.db);before=snapshot(self.db);ddl=[tuple(r) for r in self.db.execute('SELECT name,sql FROM sqlite_master ORDER BY name')]
        family_model.migrate(self.db);self.assertEqual(before,snapshot(self.db));self.assertEqual(ddl,[tuple(r) for r in self.db.execute('SELECT name,sql FROM sqlite_master ORDER BY name')])
        self.assertFalse(self.db.execute("SELECT 1 FROM sqlite_master WHERE name LIKE '_v2141_%'").fetchone())
    def test_unknown_inbound_reference_refused_without_cascading_loss(self):
        with self.db:
            self.db.execute('CREATE TABLE fictional_external_reference(id INTEGER PRIMARY KEY,reminder TEXT REFERENCES machine_reminders(reminder_uuid) ON DELETE CASCADE)')
            self.db.execute("INSERT INTO fictional_external_reference VALUES(1,'linked-old')")
        before=snapshot(self.db)
        with self.assertRaisesRegex(RuntimeError,'migration refusée'):family_model.migrate(self.db)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],23);self.assertEqual(before,snapshot(self.db))
    def test_full_schema24_backup_restores_and_keeps_secrets(self):
        family_model.migrate(self.db);before=snapshot(self.db)
        (self.path.parent/'.openfablab_sync_secret').write_text('SYNTHETIC_ONLY_NOT_REAL')
        archive=Path(self.temp.name)/'test-backup.zip';private_backup.create_backup(self.path,archive)
        restored=Path(self.temp.name)/'isolated/openfablab.db';private_backup.restore_backup(archive,restored)
        with sqlite3.connect(restored) as db:self.assertEqual(snapshot(db),before);self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],24);self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())
        self.assertEqual((restored.parent/'.openfablab_sync_secret').read_text(),'SYNTHETIC_ONLY_NOT_REAL')
