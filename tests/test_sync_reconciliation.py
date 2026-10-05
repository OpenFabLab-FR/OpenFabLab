"""Local, fictional regressions: lost catalog commands and blocked deletions."""
import json
import unittest
from datetime import datetime, timezone
from tests import test_app as fixtures
from reservations_sync import _sync_environment, enqueue_animation


class SyncReconciliationTests(unittest.TestCase):
    def setUp(self):
        fixtures.OpenFabLabTestCase.setUp(self)
        # Explicitly exercise archived protocol-2 helpers, never the 2.8 worker.
        # Schema-15 refusal and protocol-3 behavior are covered in test_families.
        with self.database() as db:db.execute('PRAGMA user_version=14')
    tearDown = fixtures.OpenFabLabTestCase.tearDown
    database = fixtures.OpenFabLabTestCase.database

    def test_delete_not_blocked_by_another_rejected_current_animation(self):
        class Client:
            deleted=[]
            def post(self,route,payload):
                if route=='/sync/animations':
                    if payload['command']=='upsert':raise ValueError('Other incompatible current configuration')
                    self.deleted.append(payload['service_id'])
                return {'ok':True,'events':[],'cursor':'0'}
        with self.database() as db:
            remains=self.animation(db);deleted=self.animation(db)
            enqueue_animation(db,remains);enqueue_animation(db,deleted,'delete')
            db.execute('DELETE FROM fablab_services WHERE id=?',(deleted,));db.commit()
            client=Client()
            with self.assertRaises(ValueError):_sync_environment(db,client,'test',[],datetime.now(timezone.utc),[],[])
            self.assertIn(deleted,client.deleted)
            self.assertEqual(db.execute('SELECT attempts FROM reservation_outbox WHERE entity_key=?',(str(remains),)).fetchone()[0],1)

    def test_partial_event_page_uses_raw_pagination_marker(self):
        class Client:
            pages=0
            def post(self,route,payload):
                if route=='/sync/events':
                    self.pages+=1
                    return {'ok':True,'events':[],'cursor':str(self.pages),'has_more':self.pages==1}
                return {'ok':True}
        with self.database() as db:
            client=Client();_sync_environment(db,client,'test',[],datetime.now(timezone.utc),[],[])
            self.assertEqual(client.pages,2)

    def test_non_advancing_cursor_refused_instead_of_infinite_loop(self):
        class Client:
            def post(self,route,payload):
                if route=='/sync/events':return {'ok':True,'events':[],'cursor':'','has_more':True}
                return {'ok':True}
        with self.database() as db:
            with self.assertRaises(ValueError):_sync_environment(db,Client(),'test',[],datetime.now(timezone.utc),[],[])

    def test_network_failure_retains_unsent_outbox_for_retry(self):
        class Client:
            def post(self,route,payload):
                if route=='/sync/animations':raise OSError('fictional outage')
                return {'ok':True}
        with self.database() as db:
            service=self.animation(db);enqueue_animation(db,service);db.commit()
            with self.assertRaises(OSError):_sync_environment(db,Client(),'test',[],datetime.now(timezone.utc),[],[])
            row=db.execute('SELECT sent_at,attempts,last_error FROM reservation_outbox').fetchone()
            self.assertIsNone(row['sent_at']);self.assertEqual(row['attempts'],1);self.assertTrue(row['last_error'])

    def test_old_plugin_404_keeps_classic_incremental_protocol(self):
        import urllib.error
        class Client:
            def post(self,route,payload):
                if route=='/sync/capabilities':raise urllib.error.HTTPError('https://example.invalid',404,'old plugin',{},None)
                return {'ok':True,'events':[],'cursor':'0'}
        with self.database() as db:
            service=self.animation(db);enqueue_animation(db,service);db.commit()
            _sync_environment(db,Client(),'test',[],datetime.now(timezone.utc),[],[])
            self.assertIsNotNone(db.execute('SELECT sent_at FROM reservation_outbox').fetchone()[0])

    def animation(self, db, environment='test'):
        now = datetime.now(timezone.utc).isoformat()
        service = db.execute("INSERT INTO fablab_services(service_type,title,service_date,start_time,end_time,created_at,updated_at) VALUES('animation','Atelier fictif','2099-01-01','10:00','12:00',?,?)", (now, now)).lastrowid
        db.execute("INSERT INTO animation_reservation_config(service_id,enabled,environment,capacity,updated_at) VALUES(?,1,?,6,?)", (service, environment, now))
        return service

    def test_old_refused_upsert_must_not_block_later_delete(self):
        class Client:
            deleted = False
            def post(self, route, payload):
                if route == '/sync/animations':
                    if payload['command'] == 'upsert':
                        raise ValueError('Reproduction: old incompatible update')
                    self.deleted = True
                return {'ok': True, 'events': [], 'cursor': '0'}
        with self.database() as db:
            service = self.animation(db)
            enqueue_animation(db, service)
            enqueue_animation(db, service, 'delete')
            db.execute('DELETE FROM fablab_services WHERE id=?', (service,))
            db.commit()
            client = Client()
            _sync_environment(db, client, 'test', [], datetime.now(timezone.utc), [], [])
            self.assertTrue(client.deleted)

    def test_lost_delete_is_repaired_by_snapshot_without_reservation_payload(self):
        class Client:
            snapshots = []
            def post(self, route, payload):
                if route == '/sync/capabilities':
                    return {'ok': True, 'catalog_snapshot_v1': True, 'animation_slots_v1': True, 'plugin_version': '2.7.0', 'protocol_version': 2}
                if route == '/sync/snapshot':
                    self.snapshots.append(payload)
                return {'ok': True, 'events': [], 'cursor': '0'}
        with self.database() as db:
            service = self.animation(db)
            self.animation(db, 'production')
            client = Client()
            _sync_environment(db, client, 'test', [], datetime.now(timezone.utc), [], [])
            self.assertEqual(len(client.snapshots), 1)
            self.assertEqual([a['service_id'] for a in client.snapshots[0]['animations']], [service])
            self.assertNotIn('bookings', client.snapshots[0])
            self.assertNotIn('reservations', client.snapshots[0])


if __name__ == '__main__':
    unittest.main()
