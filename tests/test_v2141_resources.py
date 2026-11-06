"""Complementary resource/public projections: fictional SQLite and HTTP only."""
import json,unittest
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from tests.test_v214_core import NewVersion
from app import write_setting
import machine_maintenance as m
import resource_booking as resources
import openlab_openings as openings
import public_snapshot

class Resources(unittest.TestCase):
    setUp=NewVersion.setUp
    def login(self,role='admin'):
        self.f.f.login_admin()
        with self.client.session_transaction() as s:s['access_role']=role;s['admin_authenticated']=role=='admin'
        self.client.get('/admin/ressources/maintenance')
        with self.client.session_transaction() as s:return s['evolution_csrf']
    def test_registry_reuses_rental_ids_and_preserves_distinct_similar_names(self):
        before={r['legacy_machine_key']:dict(r) for r in self.db.execute('SELECT * FROM resources WHERE legacy_machine_key IS NOT NULL')}
        for name in ('Imprimante fictive A','Imprimante fictive A2'):
            resources.save_resource(self.db,dict(name=name,type_key='machine',active='0'),'admin')
        m.directory(self.db);m.directory(self.db)
        after={r['legacy_machine_key']:dict(r) for r in self.db.execute('SELECT * FROM resources WHERE legacy_machine_key IS NOT NULL')}
        self.assertEqual(before,after)
        self.assertEqual(self.db.execute("SELECT COUNT(DISTINCT resource_uuid) FROM resources WHERE name LIKE 'Imprimante fictive A%'").fetchone()[0],2)
    def test_room_and_custom_category_supported_without_enabling_booking(self):
        self.db.execute("INSERT INTO resource_types VALUES('space','Salle','salle','#16849c',1,10,'2026-01-01','2026-01-01')")
        key=resources.save_resource(self.db,dict(name='Salle fictive',type_key='space',active='0'),'admin')
        m.set_condition(self.db,key,dict(status='maintenance',visibility_controls='1',public_visible='1'),'moderator','moderator')
        self.assertIn(key,[r['resource_uuid'] for r in m.directory(self.db)])
        self.assertEqual(self.db.execute('SELECT active FROM resources WHERE resource_uuid=?',(key,)).fetchone()[0],0)
        item=next(r for r in m.public_machines(self.db,details=True) if r['id']==key)
        self.assertEqual(item['category'],'Salle')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM resource_bookings').fetchone()[0],0)
    def test_legacy_public_operational_resource_is_not_filtered_by_booking_or_age(self):
        self.db.execute('UPDATE resources SET active=0 WHERE resource_uuid=?',(self.key,))
        m.set_condition(self.db,self.key,dict(status='operational',announce='0',public_listed='1'),'admin','admin')
        self.assertEqual(m.public_machines(self.db)[0]['id'],self.key)
        self.assertFalse(m.public_machines(self.db,True))
    def test_all_public_states_keep_same_historical_identifier(self):
        for state in m.STATES:
            m.set_condition(self.db,self.key,dict(status=state,visibility_controls='1',public_visible='1'),'admin','admin')
            items=public_snapshot.build(self.db,'production',machines=True,details=True,unavailable=True)['machines']
            self.assertEqual([(x['id'],x['status']) for x in items],[(self.key,state)])
    def test_private_resource_and_internal_notes_never_projected(self):
        m.intervention(self.db,self.key,dict(performed_on='2026-01-01',kind='care',description='FICTIONAL_PRIVATE_NOTE'),'admin','admin')
        self.assertFalse(m.public_machines(self.db))
        m.set_condition(self.db,self.key,dict(status='maintenance',visibility_controls='1',public_visible='1'),'admin','admin')
        text=json.dumps(public_snapshot.build(self.db,'production',machines=True,details=True))
        self.assertNotIn('FICTIONAL_PRIVATE_NOTE',text)
        self.assertNotIn('actor',text);self.assertNotIn('description',text)
    def test_channel_exceptions_preserved_without_broadening(self):
        m.set_condition(self.db,self.key,dict(status='maintenance',announce='1',public_listed='0'),'admin','admin')
        self.assertFalse(m.public_machines(self.db));self.assertTrue(m.public_machines(self.db,True))
        m.set_condition(self.db,self.key,dict(status='maintenance',announce='0',public_listed='1'),'admin','admin')
        self.assertFalse(m.public_machines(self.db));self.assertFalse(m.public_machines(self.db,True))
    def test_legacy_urls_redirect_to_canonical_without_creating_resources(self):
        self.login();count=len(m.directory(self.db))
        for path,target in [('/admin/maintenance','/admin/ressources/maintenance'),('/admin/maintenance/'+self.key,'/admin/ressources/'+self.key+'/maintenance')]:
            result=self.client.get(path);self.assertEqual(result.status_code,308);self.assertTrue(result.location.endswith(target))
        self.assertEqual(count,len(m.directory(self.db)))
    def test_navigation_and_identity_creation_only_in_resources(self):
        self.login();body=self.client.get('/admin/ressources/maintenance').text
        self.assertNotIn('Ajouter une machine',body)
        self.assertIn('Gestion des ressources',body)
        self.assertNotIn('admin-tab active\" href=\"/admin/maintenance',body)
        self.assertIn('Retour aux ressources',self.client.get('/admin/ressources/'+self.key+'/maintenance').text)
    def test_maintenance_works_without_resource_booking_or_activities_module(self):
        for key in ('module_resources','module_activities'):write_setting(self.db,key,'0')
        self.db.commit();self.login('moderator')
        self.assertEqual(self.client.get('/admin/ressources').status_code,200)
        self.assertEqual(self.client.get('/admin/ressources/maintenance').status_code,200)
        self.assertEqual(self.client.get('/admin/ressources/reservations').status_code,404)
    def test_moderator_can_track_but_not_rename_or_create(self):
        token=self.login('moderator')
        path='/admin/ressources/'+self.key+'/maintenance'
        self.assertEqual(self.client.post(path,data=dict(action='condition',status='maintenance',evolution_csrf=token)).status_code,302)
        self.assertEqual(m.machine(self.db,self.key)['status'],'maintenance')
        before=m.machine(self.db,self.key)['name']
        self.client.post('/admin/ressources',data=dict(action='resource',key=self.key,name='ILLEGAL',type_key='machine',evolution_csrf=token))
        self.assertEqual(m.machine(self.db,self.key)['name'],before)
        self.assertEqual(self.client.post(path,data=dict(action='condition',status='operational')).status_code,400)
    def test_anonymous_cannot_read_history_or_modify(self):
        path='/admin/ressources/'+self.key+'/maintenance'
        self.assertEqual(self.client.get(path).status_code,302)
        self.assertEqual(self.client.post(path,data=dict(action='condition',status='out_of_service')).status_code,302)
        self.assertEqual(m.machine(self.db,self.key)['status'],'operational')
    def test_state_consistent_and_unavailable_booking_not_silently_cancelled(self):
        self.db.execute("INSERT INTO resource_bookings(booking_uuid,resource_uuid,user_id,starts_at,ends_at,status,amount_cents,created_by_role,created_at,updated_at) VALUES('fictional-booking',?,?,'2030-01-01T10:00:00Z','2030-01-01T12:00:00Z','confirmed',0,'admin','2026-01-01','2026-01-01')",(self.key,self.f.a))
        m.set_condition(self.db,self.key,dict(status='out_of_service'),'admin','admin');self.db.commit();self.login()
        self.assertIn('Hors service',self.client.get('/admin/ressources').text)
        self.assertIn('réservation à vérifier',self.client.get('/admin/ressources/'+self.key+'/maintenance').text)
        self.assertEqual(self.db.execute("SELECT status FROM resource_bookings WHERE booking_uuid='fictional-booking'").fetchone()[0],'confirmed')
    def test_visual_colour_retains_old_value_and_reset_uses_category(self):
        values=dict(name=m.machine(self.db,self.key)['name'],type_key='machine',color='#FFA500',active='0')
        resources.save_resource(self.db,values,'admin',self.key);self.db.commit();self.login()
        body=self.client.get('/admin/ressources').text;self.assertIn('type="color" name="color"',body);self.assertIn('#FFA500',body)
        resources.save_resource(self.db,dict(values,color=''),'admin',self.key)
        self.assertIsNone(m.machine(self.db,self.key)['color'])
        with self.assertRaisesRegex(ValueError,'palette'):resources.save_resource(self.db,dict(values,color='Orange'),'admin',self.key)
    def test_human_audit_local_timezone_and_original_trace_preserved(self):
        m.set_condition(self.db,self.key,dict(status='maintenance'),'admin','admin')
        self.db.execute("UPDATE machine_history SET created_at='2026-11-02T21:25:22+00:00'");self.db.commit();self.login()
        path='/admin/ressources/'+self.key+'/maintenance'
        body=self.client.get(path).text;self.assertIn('2 novembre 2026 à 22 h 25',body);self.assertIn('État de la ressource modifié',body)
        self.assertNotIn('· condition',body)
        write_setting(self.db,'structure_timezone','America/New_York');self.db.commit()
        self.assertIn('2 novembre 2026 à 16 h 25',self.client.get(path).text)
        self.assertEqual(self.db.execute('SELECT action FROM machine_history').fetchone()[0],'condition')
    def test_identity_description_changes_are_audited(self):
        prior=m.machine(self.db,self.key)
        resources.save_resource(self.db,dict(prior,description='Nouvelle description fictive'),'admin',self.key)
        self.assertEqual(m.history_entries(self.db,self.key)[0]['label'],'Description modifiée')
    def test_optional_public_details_not_sent_to_legacy_plugin(self):
        m.set_condition(self.db,self.key,dict(status='operational',visibility_controls='1',public_visible='1'),'admin','admin')
        old=public_snapshot.build(self.db,'production',calendar=True,machines=True)
        self.assertNotIn('category',old['machines'][0])
        self.assertTrue(all('description' not in x and 'slots' not in x and 'capacity' not in x for x in old['calendar']))
        new=public_snapshot.build(self.db,'production',calendar=True,machines=True,details=True)
        self.assertIn('category',new['machines'][0])
    def test_defaults_preserved_without_public_statistics_optin(self):
        import family_model
        before=dict(self.db.execute('SELECT key,value FROM app_settings'))
        public_snapshot.build(self.db,'test',calendar=True,machines=True,details=True)
        self.assertEqual(before,dict(self.db.execute('SELECT key,value FROM app_settings')))
        self.assertNotIn('openlab_public_average_enabled',before)
        family_model.migrate(self.db);self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],family_model.SCHEMA)
    def test_calendar_uses_public_description_and_exact_slot_capacity(self):
        import animation_slots
        self.db.execute("UPDATE animation_reservation_config SET booking_mode='slots',slot_duration_minutes=30,slot_gap_minutes=0,slot_capacity=2 WHERE service_id=?",(self.f.service,))
        service=self.db.execute('SELECT * FROM fablab_services WHERE id=?',(self.f.service,)).fetchone()
        config=self.db.execute('SELECT * FROM animation_reservation_config WHERE service_id=?',(self.f.service,)).fetchone()
        slots=animation_slots.save_slots(self.db,service,config,'Europe/Paris')
        self.db.execute('UPDATE animation_slots SET capacity=3 WHERE slot_uuid=?',(slots[0]['slot_uuid'],))
        result=public_snapshot.build(self.db,'production',calendar=True,details=True)
        item=next(x for x in result['calendar'] if x['kind']=='animation')
        self.assertEqual(item['description'],'Description fictive')
        self.assertEqual([x['capacity'] for x in item['slots']],[3,2,2,2])
        self.assertTrue(all(set(x)=={'start','end','capacity','availability_state','close_at'} for x in item['slots']))
        self.assertNotIn('capacity',item)
    def test_public_detail_capability_optional_and_strict_without_protocol_bump(self):
        import outbound_sync
        class Client:
            def __init__(self,extra):self.extra=extra
            def post(self,*args):return dict(protocol_version=4,relay_revision=3,outbound_actions_v1=True,**self.extra)
        self.assertNotIn('public_resources_details_v1',outbound_sync.negotiate(Client({}),'production'))
        self.assertTrue(outbound_sync.negotiate(Client({'public_resources_details_v1':True}),'test')['public_resources_details_v1'])
        with self.assertRaises(ValueError):outbound_sync.negotiate(Client({'public_resources_details_v1':'1'}),'production')

class PublicAverage(unittest.TestCase):
    setUp=NewVersion.setUp
    def seed(self,count=6):
        self.now=datetime(2026,11,2,12,tzinfo=ZoneInfo('Europe/Paris'))
        self.schedule=[dict(active=True,start='14:00',end='18:00') for _ in range(7)]
        for week in range(1,count+1):
            day=self.now.date()+timedelta(days=1-week*7)
            start=datetime.combine(day,datetime.min.time()).replace(hour=14,minute=15,tzinfo=ZoneInfo('Europe/Paris')).isoformat()
            end=datetime.combine(day,datetime.min.time()).replace(hour=16,tzinfo=ZoneInfo('Europe/Paris')).isoformat()
            visitor=datetime.combine(day,datetime.min.time()).replace(hour=15,tzinfo=ZoneInfo('Europe/Paris')).isoformat()
            for user in self.f.people[:5]:
                self.db.execute("INSERT INTO sessions(user_id,check_in,check_out,statistical_user_key) VALUES(?,?,?,?)",(user,start,end,'fictional-'+str(user)))
            self.db.execute('INSERT INTO visitors(created_at) VALUES(?)',(visitor,))
        write_setting(self.db,'openlab_public_average_enabled','1');self.db.commit()
    def average(self):return openings.attendance_average(self.db,self.schedule,1,'14:00','18:00',self.now)
    def test_at_least_six_observed_comparable_sessions(self):
        self.seed(5);self.assertIsNone(self.average())
    def test_averages_exact_deduplicated_and_no_raw_data(self):
        self.seed();result=self.average();self.assertEqual((result['users'],result['visitors']),(5,1))
        self.assertEqual(set(result),{'users','visitors','since','until','method'})
        self.db.execute('INSERT INTO sessions(user_id,check_in,check_out,statistical_user_key) SELECT user_id,check_in,check_out,statistical_user_key FROM sessions LIMIT 1')
        self.assertEqual(self.average(),result)
    def test_closed_and_changed_hours_are_excluded(self):
        self.seed();day=(self.now.date()+timedelta(days=1-7)).isoformat()
        openings.save_exception(self.db,dict(day=day,kind='closed'),'admin');self.assertIsNone(self.average())
        openings.save_exception(self.db,dict(day=day,kind='hours',starts_at='10:00',ends_at='12:00'),'admin');self.assertIsNone(self.average())
    def test_disabled_never_exposes_average_or_rewrites_settings(self):
        self.seed();write_setting(self.db,'openlab_public_average_enabled','0');self.assertIsNone(self.average())
    def test_small_counts_not_published(self):
        self.seed();self.db.execute('DELETE FROM sessions WHERE user_id!=?',(self.f.a,));self.assertIsNone(self.average())

