"""Capability-negotiated projection never allocates a seat in WordPress."""
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from tests import test_family_waitlist as fixtures
from app import write_setting
import outbound_actions as actions,waitlist_limits as limits

class CatalogueLimitTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.WaitlistTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.db=self.f.db
    def item(self,new=True):return next(v for v in actions.public_catalogue(self.db,'production',include_limits=new) if v['service_id']==self.f.service)
    def test_capability_has_explicit_type_no_silent_incompatible_payload(self):
        from outbound_sync import negotiate
        from unittest.mock import Mock
        client=Mock();base=dict(protocol_version=4,relay_revision=3,outbound_actions_v1=True)
        client.post.return_value=base;self.assertNotIn('waitlist_limits_v1',negotiate(client,'production'))
        for flag in (True,False):client.post.return_value=dict(base,waitlist_limits_v1=flag);self.assertIs(negotiate(client,'production')['waitlist_limits_v1'],flag)
        for flag in ('true',1,None,{}):
            client.post.return_value=dict(base,waitlist_limits_v1=flag)
            with self.assertRaises(ValueError):negotiate(client,'production')
    def test_old_plugin_projection_unchanged(self):
        value=self.item(False);self.assertNotIn('waiting',value);self.assertNotIn('availability_state',value)
    def test_available_then_waiting_then_full(self):
        self.assertEqual(self.item()['availability_state'],'available')
        self.f.full();self.assertEqual(self.item()['availability_state'],'waiting')
        write_setting(self.db,'reservation_waitlist_limit_mode','custom');write_setting(self.db,'reservation_waitlist_limit_value','1');self.db.commit()
        self.f.book([self.f.f.a]);item=self.item();self.assertEqual((item['availability_state'],item['waiting'],item['waiting_limit']),('waiting_full',1,1))
    def test_no_waitlist_distinct_from_queue_full(self):
        self.f.full();self.db.execute('UPDATE animation_reservation_config SET waitlist_enabled=0');self.db.commit()
        self.assertEqual(self.item()['availability_state'],'full')
    def test_opening_and_closure_not_capacity_full(self):
        tomorrow=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
        self.db.execute('UPDATE animation_reservation_config SET signup_open_at=?',(tomorrow,));self.db.commit()
        self.assertEqual(self.item()['availability_state'],'not_open')
        self.assertFalse(actions.public_catalogue(self.db,'production'))
        self.db.execute('UPDATE animation_reservation_config SET signup_open_at=NULL,close_minutes=40000');self.db.commit()
        self.assertEqual(self.item()['availability_state'],'closed')
    def test_queue_limit_checked_again_after_display(self):
        self.f.full();write_setting(self.db,'reservation_waitlist_limit_mode','custom');write_setting(self.db,'reservation_waitlist_limit_value','1');self.db.commit()
        self.assertEqual(self.item()['availability_state'],'waiting');self.f.book([self.f.f.a])
        with self.assertRaises(ValueError):self.f.book([self.f.f.b])
    def test_unlimited_projection_null_not_false(self):
        self.f.full();write_setting(self.db,'reservation_waitlist_limit_mode','unlimited');self.db.commit()
        self.assertIsNone(self.item()['waiting_limit']);self.assertEqual(self.item()['availability_state'],'waiting')
