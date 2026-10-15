"""Admission only: real fictitious transactions, groups, offers and episodes."""
import json,secrets,sqlite3,threading,unittest
from tests import test_family_waitlist as fixtures
from unittest.mock import patch
import family_reservations as engine,family_waitlist as waiting,waitlist_limits as limits
import reservation_notifications as notices
from app import write_setting

class WaitlistLimitTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.WaitlistTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db=self.f.db
        write_setting(self.db,'reservation_waitlist_limit_mode','automatic');write_setting(self.db,'discord_notifications_enabled','1');self.db.commit()
    def settings(self,mode,value=0):
        write_setting(self.db,'reservation_waitlist_limit_mode',mode);write_setting(self.db,'reservation_waitlist_limit_value',str(value));self.db.commit()
    def service(self):return engine.effective_service(self.db,self.f.service,None,'production',False)
    def test_automatic_only_waiting_capacity_and_indivisible_family(self):
        self.f.full();self.f.book([self.f.f.a,self.f.f.c,self.f.f.d]);self.f.book([self.f.f.teen])
        self.assertEqual(limits.waiting(self.db,self.f.service),4)
        with self.assertRaisesRegex(ValueError,'liste d’attente'):self.f.book([self.f.f.other])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],8)
    def test_family_exceeding_remaining_queue_never_splits(self):
        self.f.full();self.settings('custom',2)
        with self.assertRaisesRegex(ValueError,'groupe'):self.f.book([self.f.f.a,self.f.f.c,self.f.f.d])
        self.assertEqual(limits.waiting(self.db,self.f.service),0)
    def test_zero_one_large_custom_validation(self):
        self.f.full();self.settings('custom',0)
        with self.assertRaises(ValueError):self.f.book([self.f.f.a])
        self.settings('custom',1);self.f.book([self.f.f.a])
        with self.assertRaises(ValueError):self.f.book([self.f.f.b])
        for value in ('-1','1.5','100001','False',True):
            with self.assertRaises(ValueError):limits.integer(value)
        self.assertEqual(limits.integer('100000'),100000)
    def test_unlimited_and_service_override(self):
        self.f.full();self.settings('custom',0)
        self.db.execute("UPDATE animation_reservation_config SET waitlist_limit_mode='unlimited' WHERE service_id=?",(self.f.service,));self.db.commit()
        for person in (self.f.f.a,self.f.f.b,self.f.f.teen,self.f.f.other,self.f.f.older):self.f.book([person])
        self.assertEqual(limits.waiting(self.db,self.f.service),5)
        self.assertIsNone(limits.limit(self.db,self.service()))
    def test_disabled_waitlist_is_not_unlimited(self):
        self.settings('unlimited');self.f.full();self.db.execute('UPDATE animation_reservation_config SET waitlist_enabled=0');self.db.commit()
        with self.assertRaisesRegex(ValueError,'fermée'):self.f.book([self.f.f.a])
    def test_lower_limit_preserves_rows_order_and_existing_offer(self):
        self.settings('unlimited');fills=self.f.full();group=self.f.book([self.f.f.a,self.f.f.c]);other=self.f.book([self.f.f.teen])
        self.f.cancel(fills[0]);self.assertEqual(self.f.status(other),'offer_pending')
        before=[tuple(row) for row in self.db.execute('SELECT * FROM animation_bookings ORDER BY external_uuid')]
        self.settings('custom',1);limits.observe_service(self.db,self.f.service);self.db.commit()
        self.assertEqual(before,[tuple(row) for row in self.db.execute('SELECT * FROM animation_bookings ORDER BY external_uuid')])
        self.assertEqual(self.f.status(group),'waitlisted');self.assertEqual(self.f.status(other),'offer_pending')
        with self.assertRaises(ValueError):self.f.book([self.f.f.b])
        waiting.respond(self.db,self.f.token(other),'accept',self.f.now)
        self.assertEqual(self.f.status(other),'confirmed')
    def test_waitlisted_admin_add_is_bounded_without_extra_seat(self):
        self.f.full();self.settings('custom',1);group=self.f.book([self.f.f.a],source='administration')
        booking=self.db.execute('SELECT external_uuid FROM animation_bookings WHERE group_uuid=?',(group['group_uuid'],)).fetchone()[0]
        with self.assertRaises(ValueError):engine.team_action(self.db,self.f.service,booking,'add','admin',self.f.f.b)
        self.assertEqual(limits.waiting(self.db,self.f.service),1)
    def test_existing_receipt_survives_limit_changes_and_retry(self):
        self.f.full();key=secrets.token_urlsafe(32)
        value=engine.reserve(self.db,self.f.f.a,[self.f.f.a],self.f.service,None,key)
        self.settings('custom',0)
        self.assertEqual(value,engine.reserve(self.db,self.f.f.a,[self.f.f.a],self.f.service,None,key))
    def test_waitlist_full_global_snapshot_deduplicated_and_no_name(self):
        self.f.full();self.settings('custom',1);group=self.f.book([self.f.f.a])
        waiting._queue(self.db,group['group_uuid'],'waitlisted');self.db.commit()
        rows=self.db.execute("SELECT * FROM reservation_discord_events WHERE event_type='waitlist_full'").fetchall();self.assertEqual(len(rows),1)
        text=notices.message(self.db,rows[0]);self.assertIn('Participants confirmés : 4/4',text);self.assertIn('Liste d’attente : 1/1',text)
        self.assertNotIn('Réservant',text);self.assertNotIn('person0',text)
        sent=[];notices.deliver(self.db,self.f.f.f.database_path,sent.append);notices.deliver(self.db,self.f.f.f.database_path,sent.append)
        self.assertEqual(sum('Liste d’attente complète' in item for item in sent),1)
    def test_new_full_episode_after_cancel_not_every_observation(self):
        self.f.full();self.settings('custom',1);group=self.f.book([self.f.f.a]);self.f.cancel(group);self.f.book([self.f.f.b])
        for _ in range(3):limits.observe_service(self.db,self.f.service)
        self.db.commit();self.assertEqual(self.db.execute("SELECT COUNT(*) FROM reservation_discord_events WHERE event_type='waitlist_full'").fetchone()[0],2)
    def test_normal_test_counts_are_separate_and_event_can_be_disabled(self):
        self.f.full();self.settings('custom',1)
        write_setting(self.db,'discord_reservation_waitlist_full','0');self.db.commit();self.f.book([self.f.f.a])
        self.assertEqual(limits.waiting(self.db,self.f.service,environment='test'),0)
        self.assertEqual(self.db.execute("SELECT state FROM reservation_discord_events WHERE event_type='waitlist_full'").fetchone()[0],'skipped')
    def test_concurrent_one_person_queue_admission_exact(self):
        self.f.full();self.settings('custom',1);path=self.f.f.f.database_path;barrier=threading.Barrier(2);results=[]
        def submit(person):
            db=sqlite3.connect(path,timeout=10);db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
            try:
                barrier.wait();results.append(engine.reserve(db,person,[person],self.f.service,None,secrets.token_urlsafe(32))['status'])
            except ValueError:results.append('refused')
            finally:db.close()
        threads=[threading.Thread(target=submit,args=(person,)) for person in (self.f.f.a,self.f.f.b)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertCountEqual(results,['waitlisted','refused']);self.assertEqual(limits.waiting(self.db,self.f.service),1)
