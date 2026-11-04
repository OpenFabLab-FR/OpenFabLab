"""Negotiated old/new plugin payloads, public opt-ins and personal calendar edges."""
import copy,json
from email.message import EmailMessage
from unittest.mock import patch
from tests.test_v214_core import NewVersion
from app import write_setting
import machine_maintenance as machines,outbound_sync as sync
from reservation_calendar import attach,event,ics

class Compatibility(NewVersion):
    # Exact capability set returned by Reservations 2.13.0 (protocol 4/rev 3).
    OLD=dict(ok=True,animation_slots_v1=True,custom_categories_v1=True,catalog_snapshot_v1=False,
        family_gateway_v1=False,protocol_version=4,outbound_actions_v1=True,transport_only_v1=True,
        relay_revision=3,plugin_version='2.13.0',animation_information_v1=True,waitlist_limits_v1=True,publication_visibility_v1=True)
    def catalogue(self,caps,accepted=True):
        class Client:
            payloads=[]
            def post(client,route,payload):
                if route=='/sync/capabilities':return caps
                client.payloads.append(payload)
                return dict(ok=accepted,plugin_version=caps['plugin_version'])
        client=Client()
        with patch('runtime_policy.external_allowed',return_value=True),patch('outbound_sync.load_sync_secret',return_value=b'fictional-secret'):
            result=sync.catalogue(self.db,self.path,'https://example.invalid',client,environments=('production',))
        return client.payloads,result
    def test_plugin_213_receives_only_legacy_payload_and_remains_usable(self):
        payloads,result=self.catalogue(copy.deepcopy(self.OLD))
        self.assertFalse(result['errors']);self.assertEqual(len(payloads),1)
        self.assertEqual(set(payloads[0]),{'environment','animations','protocol_version','relay_revision'})
        self.assertEqual(payloads[0]['protocol_version'],4);self.assertEqual(payloads[0]['relay_revision'],3)
        self.assertTrue(payloads[0]['animations']);self.assertNotIn('calendar',json.dumps(payloads))
        self.assertEqual(self.db.execute("SELECT value FROM app_settings WHERE key='reservation_participant_calendar_production'").fetchone()[0],'0')
    def test_new_caps_are_independent_and_not_applied_before_acknowledgement(self):
        caps=dict(self.OLD,plugin_version='2.14.0',public_machines_v1=True,participant_calendar_v1=True)
        payloads,result=self.catalogue(caps,False);self.assertTrue(result['errors'])
        self.assertFalse(self.db.execute("SELECT 1 FROM app_settings WHERE key='reservation_participant_calendar_production' AND value='1'").fetchone())
        payloads,result=self.catalogue(caps);self.assertFalse(result['errors'])
        self.assertIn('machines',payloads[0]['public_data']);self.assertNotIn('calendar',payloads[0]['public_data'])
        self.assertEqual(self.db.execute("SELECT value FROM app_settings WHERE key='reservation_participant_calendar_production'").fetchone()[0],'1')
    def test_public_announcement_is_independent_of_rental_bookable_flag(self):
        self.db.execute('UPDATE resources SET active=0 WHERE resource_uuid=?',(self.key,))
        machines.set_condition(self.db,self.key,dict(status='out_of_service',announce='1',public_listed='1',public_reason='Public example'),'admin','admin')
        self.assertIn(self.key,[item['id'] for item in machines.public_machines(self.db,True)])
        self.assertEqual(self.db.execute('SELECT active FROM resources WHERE resource_uuid=?',(self.key,)).fetchone()[0],0)
        self.assertFalse(machines.technically_available(self.db,self.key))
        machines.set_condition(self.db,self.key,dict(status='out_of_service',announce='0',public_listed='1'),'admin','admin')
        self.assertFalse(machines.public_machines(self.db));self.assertFalse(machines.public_machines(self.db,True))
    def test_custom_fragment_and_cancellation_have_explicit_calendar_notice(self):
        self.f.book([self.f.a]);group=dict(self.db.execute('SELECT * FROM family_booking_groups').fetchone())
        initial=event(self.db,group)
        def message():
            value=EmailMessage();value.set_content('Customized plain text');value.add_alternative('<p>Customized HTML fragment</p>',subtype='html');return value
        confirmed=message();attach(self.db,confirmed,group,'confirmed')
        for part in confirmed.walk():
            if part.get_content_type() in ('text/plain','text/html'):self.assertIn('Ajouter à mon calendrier',part.get_content())
        self.db.execute("UPDATE family_booking_groups SET status='cancelled',updated_at='2027-01-01T12:00:00+00:00'")
        cancelled=message();attach(self.db,cancelled,group,'cancelled')
        for part in cancelled.walk():
            if part.get_content_type() in ('text/plain','text/html'):
                self.assertIn('annulée',part.get_content());self.assertIn('synchronisation automatique',part.get_content());self.assertNotIn('calendar.google.com',part.get_content())
        current=dict(self.db.execute('SELECT * FROM family_booking_groups').fetchone());value=event(self.db,current);raw=ics(value)
        self.assertEqual(initial['uid'],value['uid']);self.assertIn(b'METHOD:CANCEL',raw);self.assertIn(b'STATUS:CANCELLED',raw)
        self.assertNotIn(current['manage_token'].encode(),raw)
        self.assertTrue(all(len(line)<=75 for line in raw.split(b'\r\n')))

for name in vars(NewVersion):
    if name.startswith('test_'):setattr(Compatibility,name,None)
def load_tests(loader,suite,pattern):return loader.loadTestsFromTestCase(Compatibility)
