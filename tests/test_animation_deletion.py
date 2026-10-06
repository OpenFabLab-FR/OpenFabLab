"""Fictional regressions: scoped, atomic deletion after cancellation."""
import json
import secrets
import sqlite3
import threading
import unittest
from tests import test_families as fixtures
import family_reservations as engine
import family_waitlist as waiting
from reservations_sync import booking_capacity_used
from outbound_actions import process_action


class AnimationDeletionTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.FamilyTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.db, self.client = self.f.db, self.f.client
        self.db.execute('PRAGMA foreign_keys=ON')
        self.f.f.login_admin()

    def delete(self, service=None, confirmation='SUPPRIMER'):
        return self.client.post('/admin/animations/'+str(service or self.f.service)+'/supprimer',
                                data={'confirmation':confirmation}, follow_redirects=True)

    def cancelled(self, ids=None):
        result = self.f.book(ids or [self.f.a])
        engine.team_action(self.db, self.f.service, result['booking_uuids'][0], 'cancel', 'admin')
        self.assertEqual(booking_capacity_used(self.db, self.f.service), 0)
        return result

    def assert_removed(self):
        for table in ('fablab_services','animation_bookings','animation_reservation_config','animation_slots','family_booking_grants','family_booking_groups'):
            key = 'id' if table == 'fablab_services' else 'service_id'
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM '+table+' WHERE '+key+'=?', (self.f.service,)).fetchone()[0], 0, table)
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_create_reserve_cancel_zero_places_unpublish_delete(self):
        result = self.cancelled()
        self.db.execute('UPDATE animation_reservation_config SET enabled=0 WHERE service_id=?', (self.f.service,)); self.db.commit()
        response = self.delete()
        self.assertEqual(response.status_code, 200)
        self.assertIn('a été supprimé', response.get_data(as_text=True))
        self.assert_removed()
        for table in ('family_booking_requests','family_booking_history','family_booking_emails'):
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM '+table+' WHERE group_uuid=?', (result['group_uuid'],)).fetchone()[0], 0)

    def test_animation_never_reserved_can_be_deleted(self):
        self.assertEqual(self.delete().status_code, 200)
        self.assert_removed()

    def test_family_cancelled_group_removed_together(self):
        self.cancelled([self.f.a, self.f.c, self.f.d])
        self.assertIn('a été supprimé', self.delete().get_data(as_text=True))
        self.assert_removed()

    def test_expired_and_declined_groups_can_be_deleted(self):
        value = self.f.book([self.f.a])
        waiting.transition(self.db, value['group_uuid'], 'expired', 'test', notify=False)
        value = self.f.book([self.f.teen], owner=self.f.teen)
        waiting.transition(self.db, value['group_uuid'], 'declined', 'test', notify=False)
        self.db.commit()
        self.delete(); self.assert_removed()

    def test_active_confirmed_waitlisted_and_offer_are_explicitly_refused(self):
        value = self.f.book([self.f.a])
        for status in ('confirmed','waitlisted','offer_pending'):
            with self.subTest(status=status):
                self.db.execute('UPDATE animation_bookings SET status=? WHERE service_id=?', (status, self.f.service))
                self.db.execute('UPDATE family_booking_groups SET status=? WHERE group_uuid=?', (status, value['group_uuid'])); self.db.commit()
                before = [tuple(r) for r in self.db.execute('SELECT * FROM family_booking_groups')]
                with self.assertRaisesRegex(ValueError, 'Annulez-les avant'):
                    engine.delete_animation(self.db, self.f.service)
                self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM family_booking_groups')], before)
                response = self.delete()
                self.assertEqual(response.status_code, 200)
                self.assertIn('Annulez-les avant', response.get_data(as_text=True))
                # A subsequent GET legitimately runs the existing offer worker.
                self.assertIsNotNone(self.db.execute('SELECT 1 FROM fablab_services WHERE id=?', (self.f.service,)).fetchone())

    def test_cancelled_historical_booking_with_slot_can_be_deleted(self):
        self.db.execute("INSERT INTO animation_slots VALUES('old-slot',?,'2099-01-01T10:00:00+00:00','2099-01-01T11:00:00+00:00',1,1)", (self.f.service,))
        self.db.execute("INSERT INTO animation_bookings(external_uuid,service_id,environment,first_name,last_name,status,link_status,source,slot_uuid,created_at,updated_at) VALUES('old-booking',?,'production','Personne','FICTIVE','cancelled','unmatched','online','old-slot','fictitious','fictitious')", (self.f.service,))
        self.db.execute("INSERT INTO reservation_actions(booking_uuid,action,actor_role,created_at) VALUES('old-booking','cancel','admin','fictitious')"); self.db.commit()
        self.delete(); self.assert_removed()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM reservation_actions WHERE booking_uuid='old-booking'").fetchone()[0], 0)

    def test_other_animation_users_relationships_settings_and_receipts_unchanged(self):
        self.cancelled()
        other = self.db.execute("INSERT INTO fablab_services(service_type,title,service_date,start_time,end_time,minimum_age,expected_participants,created_at,updated_at) SELECT service_type,'Autre atelier fictif',service_date,start_time,end_time,minimum_age,expected_participants,created_at,updated_at FROM fablab_services WHERE id=?", (self.f.service,)).lastrowid
        self.db.execute("INSERT INTO animation_reservation_config(service_id,enabled,environment,capacity,updated_at) VALUES(?,1,'test',4,'fictitious')", (other,)); self.db.commit()
        engine.reserve(self.db, self.f.a, [self.f.a], other, None, secrets.token_urlsafe(32), environment='test')
        before = {t:[tuple(r) for r in self.db.execute('SELECT * FROM '+t)] for t in ('users','user_family_links','app_settings','wordpress_action_receipts')}
        others = {t:[tuple(r) for r in self.db.execute('SELECT * FROM '+t+' WHERE service_id=?', (other,))] for t in ('animation_bookings','family_booking_groups','animation_reservation_config')}
        self.delete(); self.assert_removed()
        for table, rows in before.items():
            self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM '+table)], rows, table)
        for table, rows in others.items():
            self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM '+table+' WHERE service_id=?', (other,))], rows, table)

    def test_late_reservation_for_deleted_service_is_refused_without_receipt_loss(self):
        self.cancelled(); self.delete()
        payload = json.dumps({'service_id':self.f.service,'token':'fictitious-expired','participants':[],'consent':True,'environment':'production'})
        import hashlib
        envelope = {'id':secrets.token_hex(24),'type':'reserve','payload_json':payload,'hash':hashlib.sha256(payload.encode()).hexdigest()}
        first = process_action(self.db, envelope, 'production', b'fictional-outbound-shared-secret')
        self.assertFalse(first['ok'])
        self.assertEqual(process_action(self.db, envelope, 'production', b'fictional-outbound-shared-secret'), first)
        self.assert_removed()

    def test_error_rolls_back_dependencies_and_catalogue_tombstone(self):
        self.cancelled()
        tables = ('fablab_services','family_booking_requests','family_booking_groups','family_booking_history','family_booking_emails','animation_bookings','reservation_actions','reservation_outbox')
        before = {t:[tuple(r) for r in self.db.execute('SELECT * FROM '+t)] for t in tables}
        self.db.execute("CREATE TRIGGER fictional_block BEFORE DELETE ON fablab_services BEGIN SELECT RAISE(ABORT,'fictional block'); END"); self.db.commit()
        response = self.delete()
        self.assertEqual(response.status_code, 200)
        self.assertIn('Rien n’a été supprimé', response.get_data(as_text=True))
        for table, rows in before.items():
            self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM '+table)], rows, table)

    def test_reservation_racing_with_deletion_cannot_recreate_it(self):
        self.cancelled()
        ready = threading.Event(); outcomes = []
        def reserve_after_lock():
            with sqlite3.connect(self.f.f.database_path, timeout=10) as db:
                db.row_factory = sqlite3.Row; db.execute('PRAGMA foreign_keys=ON'); ready.set()
                try:
                    engine.reserve(db, self.f.a, [self.f.a], self.f.service, None, secrets.token_urlsafe(32))
                except ValueError as error:
                    outcomes.append(str(error))
        self.db.execute('BEGIN IMMEDIATE')
        thread = threading.Thread(target=reserve_after_lock)
        thread.start(); self.assertTrue(ready.wait(2))
        engine.delete_animation(self.db, self.f.service)
        self.db.commit(); thread.join(12)
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcomes, ['Animation indisponible.'])
        self.assert_removed()

    def test_nested_transaction_failure_preserves_outer_work_and_all_dependencies(self):
        self.cancelled()
        self.db.execute("CREATE TRIGGER fictional_block BEFORE DELETE ON fablab_services BEGIN SELECT RAISE(ABORT,'fictional block'); END"); self.db.commit()
        before = [tuple(r) for r in self.db.execute('SELECT * FROM family_booking_groups')]
        self.db.execute('BEGIN IMMEDIATE')
        self.db.execute("INSERT INTO visitors(created_at) VALUES('fictitious outer work')")
        with self.assertRaisesRegex(ValueError, 'Rien n’a été supprimé'):
            engine.delete_animation(self.db, self.f.service)
        self.assertTrue(self.db.in_transaction)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM family_booking_groups')], before)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM visitors WHERE created_at='fictitious outer work'").fetchone()[0], 1)
        self.db.rollback()

    def test_inconsistent_shared_group_refused_without_touching_other_service(self):
        result = self.cancelled()
        other = self.db.execute("INSERT INTO fablab_services(service_type,title,service_date,created_at,updated_at) VALUES('animation','Autre fictive','2099-01-01','fictitious','fictitious')").lastrowid
        self.db.execute('UPDATE animation_bookings SET service_id=? WHERE group_uuid=?', (other, result['group_uuid'])); self.db.commit()
        before = [tuple(r) for r in self.db.execute('SELECT * FROM animation_bookings')]
        with self.assertRaisesRegex(ValueError, 'autre animation'):
            engine.delete_animation(self.db, self.f.service)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM animation_bookings')], before)
        self.assertIsNotNone(self.db.execute('SELECT 1 FROM fablab_services WHERE id=?', (self.f.service,)).fetchone())

    def test_wrong_confirmation_get_and_moderator_cannot_delete(self):
        self.cancelled()
        self.assertIn('SUPPRIMER', self.delete(confirmation='non').get_data(as_text=True))
        self.assertEqual(self.client.get('/admin/animations/'+str(self.f.service)+'/supprimer').status_code, 405)
        with self.client.session_transaction() as session:
            session['access_role'] = 'moderator'
        self.assertEqual(self.client.post('/admin/animations/'+str(self.f.service)+'/supprimer', data={'confirmation':'SUPPRIMER'}).status_code, 302)
        self.assertIsNotNone(self.db.execute('SELECT 1 FROM fablab_services WHERE id=?', (self.f.service,)).fetchone())


if __name__ == '__main__':
    unittest.main()
