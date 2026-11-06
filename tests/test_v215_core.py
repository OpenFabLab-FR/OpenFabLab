"""V2.15 additive data model: fictional people, real SQLite transactions."""
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from tests import test_v214_core as core
import family_model
import resource_booking as bookings
import resource_loans as loans
import machine_maintenance as machines
import user_participation as participation

class Migration(unittest.TestCase):
    setUp = core.NewVersion.setUp

    def source25(self):
        from tests.schema_fixtures import remove_27
        remove_27(self.db)
        for table in ('resource_document_links', 'resource_documents', 'user_booking_restrictions'):
            self.db.execute('DROP TABLE '+table)
        for table, columns in {'resources':['availability_mode'],'resource_bookings': ['handed_over_at','returned_at'],
                              'billing_records': ['handed_over_at','returned_at','rental_user_id']}.items():
            for column in columns:
                self.db.execute('ALTER TABLE '+table+' DROP COLUMN '+column)
        self.db.execute("DELETE FROM app_settings WHERE key IN('resource_public_base_url','resource_public_pages_enabled','setup_completed','setup_progress')")
        self.db.execute('PRAGMA user_version=25')
        self.db.commit()

    def test_additive_preserves_every_old_column_and_setting(self):
        self.source25()
        columns = {r[0]: [c[1] for c in self.db.execute('PRAGMA table_info('+r[0]+')')]
                   for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        previous = {t: list(map(tuple, self.db.execute('SELECT * FROM '+t))) for t in columns}
        family_model.migrate(self.db)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0], family_model.SCHEMA)
        for table, names in columns.items():
            query = 'SELECT '+','.join('"'+n+'"' for n in names)+' FROM '+table
            actual = list(map(tuple, self.db.execute(query)))
            if table == 'app_settings':
                self.assertTrue(set(previous[table]) <= set(actual))
            else:
                self.assertEqual(previous[table], actual, table)
        self.assertEqual(participation.setting(self.db,'setup_completed'), '1')
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertFalse(self.db.execute('PRAGMA foreign_key_check').fetchall())

    def test_interruption_rolls_back_all_ddl_and_settings(self):
        self.source25()
        before = list(self.db.iterdump())
        def fail(db):
            raise RuntimeError('FICTIONAL_INTERRUPTION')
        with self.assertRaises(RuntimeError):
            family_model.migrate(self.db, fail)
        self.assertEqual(before, list(self.db.iterdump()))
        family_model.migrate(self.db)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0], family_model.SCHEMA)

    def test_idempotence_and_future_schema_refusal(self):
        before = list(self.db.iterdump())
        family_model.migrate(self.db)
        self.assertEqual(before, list(self.db.iterdump()))
        self.db.execute('PRAGMA user_version='+str(family_model.SCHEMA+1))
        self.db.commit()
        with self.assertRaises(RuntimeError):
            family_model.migrate(self.db)

    def test_missing_columns_cannot_masquerade_as26(self):
        self.db.execute('ALTER TABLE resource_bookings DROP COLUMN handed_over_at')
        with self.assertRaises(RuntimeError):
            family_model.migrate(self.db)

class Handovers(unittest.TestCase):
    setUp = core.NewVersion.setUp

    def booking(self):
        begin = datetime.now(timezone.utc)+timedelta(days=10)
        key = bookings.book(self.db, self.key, self.f.a, begin.isoformat(),
                            (begin+timedelta(hours=2)).isoformat(), 'admin')
        self.db.commit()
        if self.db.execute('SELECT status FROM resource_bookings WHERE booking_uuid=?',(key,)).fetchone()[0] == 'requested':
            bookings.transition(self.db, key, 'confirmed', 'admin')
        self.db.commit()
        return key, begin

    def test_future_confirmation_does_not_mean_handed_over(self):
        self.booking()
        self.assertEqual(loans.availability(self.db,self.key)['status'], 'operational')

    def test_past_booking_without_handover_is_not_misrepresented_as_future_or_loaned(self):
        key,begin=self.booking()
        self.assertEqual(loans.user_history(self.db,self.f.a,'admin',begin-timedelta(days=1))[0]['label'],'À venir')
        self.assertEqual(loans.user_history(self.db,self.f.a,'admin',begin+timedelta(days=1))[0]['label'],'Remise non enregistrée')
        self.assertEqual(loans.availability(self.db,self.key,begin+timedelta(days=1))['status'],'operational')
        self.db.execute("UPDATE resource_bookings SET status='cancelled' WHERE booking_uuid=?",(key,));self.db.commit()
        self.assertEqual(loans.user_history(self.db,self.f.a,'admin',begin+timedelta(days=1))[0]['label'],'Annulée')

    def test_explicit_handover_late_and_return_idempotent(self):
        key, begin = self.booking()
        self.assertTrue(loans.transition(self.db,'booking',key,'handover','moderator',current=begin))
        self.assertFalse(loans.transition(self.db,'booking',key,'handover','moderator',current=begin))
        self.assertEqual(loans.availability(self.db,self.key,begin)['status'], 'loaned')
        later = begin+timedelta(days=1)
        self.assertEqual(loans.availability(self.db,self.key,later)['status'], 'overdue')
        self.assertTrue(loans.transition(self.db,'booking',key,'return','moderator',current=later))
        self.assertFalse(loans.transition(self.db,'booking',key,'return','moderator',current=later))
        self.assertEqual(loans.availability(self.db,self.key,later)['status'], 'operational')
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM evolution_audit WHERE entity_type='resource_loan'").fetchone()[0], 2)

    def test_return_never_overwrites_maintenance(self):
        key, begin = self.booking()
        loans.transition(self.db,'booking',key,'handover','admin',current=begin)
        machines.set_condition(self.db,self.key,dict(status='maintenance',public_reason='Vérification fictive'),'admin','admin')
        self.db.commit()
        loans.transition(self.db,'booking',key,'return','admin',current=begin+timedelta(hours=1))
        self.assertEqual(loans.availability(self.db,self.key)['status'], 'maintenance')

    def test_maintenance_blocks_handover_and_unauthorized_action(self):
        key, begin = self.booking()
        machines.set_condition(self.db,self.key,dict(status='out_of_service'),'admin','admin')
        self.db.commit()
        with self.assertRaises(ValueError):
            loans.transition(self.db,'booking',key,'handover','admin',current=begin)
        with self.assertRaises(PermissionError):
            loans.transition(self.db,'booking',key,'handover','user',current=begin)
        self.assertIsNone(self.db.execute('SELECT handed_over_at FROM resource_bookings WHERE booking_uuid=?',(key,)).fetchone()[0])

    def test_return_before_handover_refused(self):
        key, begin = self.booking()
        with self.assertRaises(ValueError):
            loans.transition(self.db,'booking',key,'return','admin',current=begin)

class Participations(unittest.TestCase):
    setUp = core.NewVersion.setUp

    def test_cancelled_never_absent_and_unknown_not_absent(self):
        self.f.book([self.f.a])
        self.db.execute("UPDATE fablab_services SET service_date='2020-01-01',end_time='12:00'")
        self.db.execute("UPDATE animation_bookings SET status='cancelled',is_present=0")
        self.db.commit()
        result=participation.history(self.db,self.f.a)
        self.assertEqual(result['counts']['cancelled'],1)
        self.assertEqual(result['counts']['absent'],0)
        self.db.execute("UPDATE animation_bookings SET status='confirmed',is_present=NULL")
        self.assertEqual(participation.history(self.db,self.f.a)['counts']['unknown'],1)
        self.db.execute("UPDATE animation_bookings SET is_present=0")
        self.assertEqual(participation.history(self.db,self.f.a)['counts']['absent'],1)

    def test_future_absence_not_yet_observed(self):
        self.f.book([self.f.a])
        self.db.execute("UPDATE fablab_services SET service_date='2099-01-01',end_time='12:00'")
        self.db.execute("UPDATE animation_bookings SET is_present=0")
        self.assertEqual(participation.history(self.db,self.f.a)['counts']['absent'],0)

    def test_future_presence_flag_is_not_counted_as_observed_participation(self):
        self.f.book([self.f.a])
        self.db.execute("UPDATE fablab_services SET service_date='2099-01-01'")
        self.db.execute('UPDATE animation_bookings SET is_present=1')
        result=participation.history(self.db,self.f.a)
        self.assertEqual(result['counts']['present'],0);self.assertEqual(result['counts']['unknown'],1)

    def test_manual_restriction_blocks_new_booking_not_user_and_can_be_lifted(self):
        today = loans.local_day(self.db).isoformat()
        values=dict(starts_on=today,ends_on=today,reason='Décision fictive de recette')
        with self.assertRaises(PermissionError):
            participation.restrict(self.db,self.f.a,values,'moderator')
        key=participation.restrict(self.db,self.f.a,values,'admin')
        with self.assertRaisesRegex(ValueError,'suspendues'):
            self.f.book([self.f.a])
        self.assertFalse(self.db.execute('SELECT 1 FROM animation_bookings').fetchone())
        self.assertEqual(self.db.execute('SELECT active FROM users WHERE id=?',(self.f.a,)).fetchone()[0],1)
        participation.lift(self.db,key,'admin')
        self.f.book([self.f.a])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],1)

if __name__ == '__main__':
    unittest.main()
