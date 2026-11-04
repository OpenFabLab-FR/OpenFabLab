"""Presentation consolidation, 12-month aggregates and compatible public projection."""
import json,unittest
from datetime import datetime,timedelta,time
from zoneinfo import ZoneInfo
from flask import g
from tests import test_v214_core as core
from app import write_setting,app
import public_resource_labels as labels
import public_snapshot,openlab_openings,outbound_sync,machine_maintenance

class Consolidation(unittest.TestCase):
    setUp=core.NewVersion.setUp
    login=core.NewVersion.login
    def post(self,**values):
        with self.client.session_transaction() as session:token=session.get('evolution_csrf')
        if not token:token=self.login()
        return self.client.post('/admin/reglages/2-14',data=dict(evolution_csrf=token,**values))
    def test_defaults_read_without_inserting_or_renaming(self):
        before=list(map(tuple,self.db.execute('SELECT * FROM resources')))
        settings=dict(self.db.execute('SELECT key,value FROM app_settings'))
        self.assertEqual(labels.choice(self.db),'resources')
        public_snapshot.build(self.db,'production',True,True,details=True,display_options=True)
        self.assertEqual(settings,dict(self.db.execute('SELECT key,value FROM app_settings')))
        self.assertEqual(before,list(map(tuple,self.db.execute('SELECT * FROM resources'))))
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],24)
    def test_each_label_singular_plural_french_english(self):
        for key,words in labels.CHOICES.items():
            write_setting(self.db,'resource_public_name',key)
            with app.test_request_context('/'):
                g.ui_language='fr'
                self.assertEqual(labels.labels(self.db,1)['resource_unavailable_count'],'1 '+words[1]+' indisponible')
                self.assertEqual(labels.labels(self.db,2)['resource_unavailable_count'],'2 '+words[2]+' indisponibles')
                g.ui_language='en'
                for count in (0,1,2):
                    value=labels.labels(self.db,count)
                    self.assertIn('unavailable',value['resource_unavailable_count'])
                    self.assertNotIn('indisponible',value['resource_unavailable_title'])
    def test_save_resource_label_independent_of_booking_and_wordpress(self):
        write_setting(self.db,'module_resources','0');self.db.commit()
        result=self.post(group='resources',enabled='1',resource_public_name='rooms')
        self.assertEqual(result.status_code,302)
        settings=dict(self.db.execute('SELECT key,value FROM app_settings'))
        self.assertEqual(settings['module_resources'],'0');self.assertEqual(settings['module_maintenance'],'1')
        self.assertEqual(settings['resource_public_name'],'rooms')
        self.assertEqual(self.post(group='resources',resource_public_name='rooms').status_code,302)
        self.assertEqual(dict(self.db.execute('SELECT key,value FROM app_settings'))['module_maintenance'],'0')
    def test_unknown_public_label_rejected(self):
        self.assertEqual(self.post(group='resources',resource_public_name='<script>').status_code,400)
        self.assertNotIn('resource_public_name',dict(self.db.execute('SELECT key,value FROM app_settings')))
    def test_resource_settings_admin_only_and_csrf_required(self):
        self.login('moderator')
        self.assertIn(self.client.post('/admin/reglages/2-14',data=dict(group='resources',resource_public_name='rooms')).status_code,(302,403))
        self.assertNotIn('resource_public_name',dict(self.db.execute('SELECT key,value FROM app_settings')))
        with self.client.session_transaction() as session:session.clear()
        self.login()
        self.assertEqual(self.client.post('/admin/reglages/2-14',data=dict(group='resources',resource_public_name='rooms')).status_code,400)
    def test_language_save_preserves_independent_visibility(self):
        write_setting(self.db,'kiosk_machine_information','none');self.db.commit()
        self.assertEqual(self.post(group='kiosk',language='en',idle='10',allow_en='1',language_switch='1').status_code,302)
        settings=dict(self.db.execute('SELECT key,value FROM app_settings'))
        self.assertEqual(settings['kiosk_machine_information'],'none');self.assertEqual(settings['kiosk_language'],'en')
        self.post(group='kiosk-display',machine_information='identification')
        settings=dict(self.db.execute('SELECT key,value FROM app_settings'))
        self.assertEqual(settings['kiosk_machine_information'],'identification');self.assertEqual(settings['kiosk_language'],'en')
    def test_openlab_save_preserves_other_modules_and_settings(self):
        before=dict(self.db.execute('SELECT key,value FROM app_settings'));self.post(group='openlab',public='1',public_average='1')
        after=dict(self.db.execute('SELECT key,value FROM app_settings'))
        self.assertEqual(after['openlab_public_enabled'],'1');self.assertEqual(after['openlab_public_average_enabled'],'1')
        for key,value in before.items():
            if key not in ('openlab_public_enabled','openlab_public_average_enabled'):self.assertEqual(after[key],value)
    def test_structure_layout_location(self):
        self.login();body=self.client.get('/admin/reglages/structure').text
        self.assertLess(body.index('Identité de la structure'),body.index('id="resources-options"'))
        self.assertLess(body.index('id="wordpress-settings"'),body.index('id="openlab-public-settings"'))
        self.assertNotIn('v214-compact-settings',body)
    def test_identification_button_only_in_content_and_all_modes(self):
        machine_maintenance.set_condition(self.db,self.key,dict(status='maintenance',visibility_controls='1',public_visible='1'),'admin','admin')
        for mode in ('none','home','identification','both'):
            write_setting(self.db,'kiosk_machine_information',mode);write_setting(self.db,'resource_public_name','machines');self.db.commit()
            body=self.client.get('/identification').text
            self.assertNotIn('machine-info-trigger',body.split('</header>')[0])
            self.assertEqual('class="identification-secondary-actions"' in body,True)
            self.assertEqual('1 machine indisponible' in body,mode in ('identification','both'))
            self.assertEqual('1 machine indisponible' in self.client.get('/').text,mode in ('home','both'))
    def test_calendar_filters_independent_and_extended_hint_absent(self):
        self.login()
        for view in ('week','month'):
            body=self.client.get('/admin/calendrier?view='+view+'&maintenance=0&hidden=1').text
            self.assertEqual(body.count('Afficher entretiens et rappels'),1)
            self.assertEqual(body.count('Afficher les événements masqués'),1)
            self.assertNotIn('Étendue pour montrer',body)
    def test_public_projection_new_fields_negotiated(self):
        write_setting(self.db,'resource_public_name','machines')
        legacy=public_snapshot.build(self.db,'production',True,True,details=True)
        new=public_snapshot.build(self.db,'test',True,True,details=True,display_options=True)
        self.assertNotIn('resource_label',legacy);self.assertEqual(new['resource_label'],'machines')
        self.assertEqual(legacy['machines'],new['machines'])
    def test_optional_display_capability_strict(self):
        class Client:
            def __init__(self,value):self.value=value
            def post(self,*args):return dict(protocol_version=4,relay_revision=3,outbound_actions_v1=True,public_display_options_v1=self.value)
        self.assertTrue(outbound_sync.negotiate(Client(True),'test')['public_display_options_v1'])
        self.assertFalse(outbound_sync.negotiate(Client(False),'production')['public_display_options_v1'])
        for bad in (0,1,'1',None):
            with self.assertRaises(ValueError):outbound_sync.negotiate(Client(bad),'production')
    def test_public_name_profile_roundtrip_and_invalid_import(self):
        import profile_archive
        for value in labels.CHOICES:
            raw=profile_archive.build_profile(dict(resource_public_name=value),[],{})
            self.assertEqual(profile_archive.parse_profile(raw)['settings']['resource_public_name'],value)
        raw=profile_archive.build_profile(dict(resource_public_name='unknown'),[],{})
        with self.assertRaises(ValueError):profile_archive.parse_profile(raw)
    def test_security_labels_display_without_changing_audit_records(self):
        # These newer audit producers insert into the same table directly.
        stamp=datetime.now(ZoneInfo('Europe/Paris')).isoformat()
        for key in ('enrollment_attempt','family_identify_attempt'):
            self.db.execute('INSERT INTO security_events(event_type,created_at,details_json) VALUES(?,?,?)',(key,stamp,'{"fixture":"private fictitious detail"}'))
        self.db.commit();before=list(map(tuple,self.db.execute("SELECT * FROM security_events WHERE event_type IN ('enrollment_attempt','family_identify_attempt')")))
        self.login();body=self.client.get('/admin/reglages/borne').text
        self.assertIn('Tentative de création d’un compte usager',body);self.assertIn('Tentative d’identification d’une famille',body)
        self.assertNotIn('enrollment_attempt',body);self.assertNotIn('private fictitious detail',body)
        after=list(map(tuple,self.db.execute("SELECT * FROM security_events WHERE event_type IN ('enrollment_attempt','family_identify_attempt')")))
        self.assertEqual(before,after)

class RollingAverage(unittest.TestCase):
    setUp=core.NewVersion.setUp
    def average(self,now,days):
        write_setting(self.db,'openlab_public_average_enabled','1')
        self.db.execute('DELETE FROM sessions');self.db.execute('DELETE FROM visitors')
        zone=ZoneInfo('Europe/Paris');schedule=[dict(active=True,start='14:00',end='18:00') for _ in range(7)]
        for day in days:
            begin=datetime.combine(day,time(14,15),zone).isoformat();end=datetime.combine(day,time(16),zone).isoformat()
            for user in self.f.people[:5]:
                for _ in range(2):self.db.execute('INSERT INTO sessions(user_id,check_in,check_out,statistical_user_key) VALUES(?,?,?,?)',(user,begin,end,'fake-'+str(user)))
        return openlab_openings.attendance_average(self.db,schedule,days[0].weekday(),'14:00','18:00',now)
    def test_older_than26weeks_is_included_and_deduplicated(self):
        now=datetime(2026,11,3,12,tzinfo=ZoneInfo('Europe/Paris'))
        result=self.average(now,[now.date()-timedelta(weeks=week) for week in range(35,41)])
        self.assertEqual(result,dict(users=5,visitors=0,since='2025-11-03',until='2026-11-02',method='observed_same_weekday_hours_12m_v1'))
    def test_outside_twelve_months_not_counted(self):
        now=datetime(2026,11,3,12,tzinfo=ZoneInfo('Europe/Paris'))
        self.assertIsNone(self.average(now,[now.date()-timedelta(weeks=week) for week in range(53,59)]))
    def test_leap_anniversary_clamped(self):
        now=datetime(2028,2,29,12,tzinfo=ZoneInfo('Europe/Paris'))
        result=self.average(now,[now.date()-timedelta(weeks=week) for week in range(1,7)])
        self.assertEqual(result['since'],'2027-02-28')
    def test_leap_year_full_anniversary(self):
        now=datetime(2029,3,1,12,tzinfo=ZoneInfo('Europe/Paris'))
        result=self.average(now,[now.date()-timedelta(weeks=week) for week in range(1,7)])
        self.assertEqual(result['since'],'2028-03-01')
