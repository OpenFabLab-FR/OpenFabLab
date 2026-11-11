"""Real SQLite/HTTP, fictional data; all external transports denied by runner."""
import unittest
from datetime import date,timedelta
from tests import test_families
from app import write_setting
import family_model
import machine_maintenance as machines
import openlab_openings as openings

class NewVersion(unittest.TestCase):
    def setUp(self):
        self.f=test_families.FamilyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db=self.f.db;self.client=self.f.client;self.path=self.f.f.database_path
        # This populated fixture represents an established FabLab. Fresh
        # storage and the first-run assistant have separate tests.
        write_setting(self.db,'setup_completed','1')
        write_setting(self.db,'module_maintenance','1');self.db.commit()
        self.key=machines.directory(self.db)[0]['resource_uuid'];self.db.commit()
    def login(self,role='admin'):
        self.f.f.login_admin()
        with self.client.session_transaction() as s:s['access_role']=role;s['admin_authenticated']=role=='admin'
        self.client.get('/admin/ressources/maintenance')
        with self.client.session_transaction() as s:return s['evolution_csrf']
    def test_additive_migration_and_idempotency(self):
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],family_model.SCHEMA)
        people=[tuple(r) for r in self.db.execute('SELECT * FROM users')]
        settings=dict(self.db.execute('SELECT key,value FROM app_settings'));family_model.migrate(self.db)
        self.assertEqual(people,[tuple(r) for r in self.db.execute('SELECT * FROM users')])
        self.assertEqual(settings,dict(self.db.execute('SELECT key,value FROM app_settings')))
        self.assertFalse(self.db.execute('PRAGMA foreign_key_check').fetchall())
    def test_atomic_interrupted_migration(self):
        self.db.execute('PRAGMA user_version=22');self.db.commit()
        def fail(db):db.execute("INSERT INTO app_settings VALUES('fictional-failure','1')");raise RuntimeError('simulated')
        with self.assertRaises(RuntimeError):family_model.migrate(self.db,fail)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],22)
        self.assertFalse(self.db.execute("SELECT 1 FROM app_settings WHERE key='fictional-failure'").fetchone())
    def test_newer_schema_refused(self):
        self.db.execute('PRAGMA user_version=99')
        with self.assertRaises(RuntimeError):family_model.migrate(self.db)
    def test_reminders_are_not_implicitly_enabled_for_older_existing_schemas(self):
        from v214_schema import ensure
        for version in (13,19,20,21,22):
            self.db.execute('PRAGMA user_version='+str(version))
            self.db.execute("DELETE FROM app_settings WHERE key='reservation_reminder_enabled'")
            ensure(self.db)
            self.assertEqual(self.db.execute("SELECT value FROM app_settings WHERE key='reservation_reminder_enabled'").fetchone()[0],'0')
    def test_existing_rental_reused_not_duplicated(self):
        before=len(machines.directory(self.db));machines.directory(self.db)
        self.assertEqual(before,len(machines.directory(self.db)))
        self.assertFalse(self.db.execute('SELECT legacy_machine_key FROM resources WHERE legacy_machine_key IS NOT NULL GROUP BY legacy_machine_key HAVING COUNT(*)>1').fetchall())
    def test_status_public_allowlist_and_booking_independence(self):
        machines.set_condition(self.db,self.key,dict(status='maintenance',announce='1',public_listed='1',public_reason='Public',return_estimate='2026-12-01'),'moderator','moderator')
        result=machines.public_machines(self.db,True)
        self.assertEqual(set(result[0]),{'id','name','status','reason','return_estimate'})
        self.assertIsNone(result[0]['return_estimate']);self.assertFalse(machines.technically_available(self.db,self.key))
        write_setting(self.db,'module_maintenance','0');self.assertFalse(machines.public_machines(self.db));self.assertTrue(machines.technically_available(self.db,self.key))
    def test_interventions_and_optimistic_audit(self):
        key=machines.intervention(self.db,self.key,dict(performed_on='2026-10-01',description='SECRET TECHNIQUE',kind='care'),'moderator','moderator')
        machines.intervention(self.db,self.key,dict(performed_on='2026-10-02',description='Correction',kind='care',revision='1'),'admin','admin',key)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM machine_history').fetchone()[0],2)
        self.assertEqual(machines.machine(self.db,self.key)['status'],'operational')
        with self.assertRaises(ValueError):machines.intervention(self.db,self.key,dict(performed_on='2026-10-03',description='Stale',kind='care',revision='1'),'moderator','moderator',key)
    def test_independent_reminder_and_cancellation(self):
        key=machines.reminder(self.db,self.key,dict(due_on='2026-12-01',subject='Vérifier le circuit'),'moderator','moderator')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM machine_interventions').fetchone()[0],0)
        self.assertEqual(machines.machine(self.db,self.key)['status'],'operational')
        machines.reminder(self.db,self.key,dict(due_on='2026-12-02',subject='Report',state='cancelled',revision='1'),'admin','admin',key)
        self.assertEqual(self.db.execute('SELECT state FROM machine_reminders').fetchone()[0],'cancelled')
    def test_unauthorized_and_csrf(self):
        self.assertEqual(self.client.get('/admin/maintenance').status_code,302)
        token=self.login('moderator')
        self.assertEqual(self.client.post('/admin/ressources/'+self.key+'/maintenance',data=dict(action='condition',status='maintenance')).status_code,400)
        response=self.client.post('/admin/ressources/'+self.key+'/maintenance',data=dict(action='condition',status='maintenance',evolution_csrf=token))
        self.assertEqual(response.status_code,302)
        self.assertEqual(machines.machine(self.db,self.key)['status'],'maintenance')
        self.assertNotEqual(self.client.post('/admin/reglages/2-14',data=dict(group='maintenance',enabled='1',evolution_csrf=token)).status_code,200)
    def test_team_views_and_forms(self):
        self.login()
        for path in ('/admin/ressources/maintenance','/admin/ressources/'+self.key+'/maintenance','/admin/calendrier/ouvertures','/admin/reglages/structure','/admin/reglages/borne','/admin/reglages/notifications'):
            with self.subTest(path=path):self.assertEqual(self.client.get(path).status_code,200)
    def test_openlab_closed_extra_and_no_statistics_rewrite(self):
        schedule=[dict(active=True,start='14:00',end='18:00') for _ in range(7)]
        day=date(2026,12,1);write_setting(self.db,'openlab_public_enabled','1')
        sessions=[tuple(r) for r in self.db.execute('SELECT * FROM sessions')]
        openings.save_exception(self.db,dict(day=str(day),kind='closed',publish='1'),'moderator')
        self.assertFalse(openings.public_openings(self.db,schedule,day,day+timedelta(days=1)))
        openings.save_exception(self.db,dict(day=str(day),kind='extra',starts_at='10:00',ends_at='12:00',publish='1'),'admin')
        self.assertIn('10:00',openings.public_openings(self.db,schedule,day,day+timedelta(days=1))[0]['start'])
        self.assertEqual(sessions,[tuple(r) for r in self.db.execute('SELECT * FROM sessions')])
    def test_calendar_privacy_uid(self):
        from reservation_calendar import event,ics,google
        self.f.book([self.f.a,self.f.c]);group=self.db.execute('SELECT * FROM family_booking_groups').fetchone()
        value=event(self.db,group);raw=ics(value)
        for forbidden in ('Fictif','contact_email','manage_token',group['manage_token']):self.assertNotIn(forbidden.encode(),raw)
        self.db.execute('UPDATE fablab_services SET title=? WHERE id=?',('Titre modifié',group['service_id']))
        self.assertEqual(value['uid'],event(self.db,group)['uid']);self.assertIn(b'DTSTART:',raw);self.assertIn('calendar.google.com',google(value))
    def test_calendar_http_only_confirmed(self):
        self.f.book([self.f.a]);group=self.db.execute('SELECT * FROM family_booking_groups').fetchone();self.db.commit()
        response=self.client.get('/animations/demande/'+group['manage_token']+'/calendrier.ics')
        self.assertEqual(response.status_code,200);self.assertIn('no-store',response.headers['Cache-Control'])
        self.db.execute("UPDATE family_booking_groups SET status='waitlisted'");self.db.commit()
        self.assertEqual(self.client.get('/animations/demande/'+group['manage_token']+'/calendrier.ics').status_code,404)
