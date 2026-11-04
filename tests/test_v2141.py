"""2.14.1 consolidation: real SQLite/HTTP; fictional data only."""
import json,sqlite3,unittest
from datetime import date,timedelta
from werkzeug.datastructures import MultiDict
from tests import test_v214_core as fixtures
import machine_maintenance as m
from app import write_setting

class Consolidation(unittest.TestCase):
    setUp=fixtures.NewVersion.setUp
    def login(self,role='admin'):
        with self.client.session_transaction() as session:session.clear()
        return fixtures.NewVersion.login(self,role)
    def create_reminder(self):
        return m.reminder(self.db,self.key,dict(due_on=date.today().isoformat(),subject='Contrôle fictif'),'moderator','moderator')
    def perform(self,**extra):
        return m.intervention(self.db,self.key,dict(performed_on=date.today().isoformat(),kind='care',description='Intervention fictive',**extra),'moderator','moderator')
    def test_association_adds_no_storage_beyond_declared_schema24(self):
        before=[tuple(r) for r in self.db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name')]
        identifier=self.create_reminder();self.perform(reminder_id=identifier,reminder_revision='1');self.db.commit()
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],24)
        self.assertEqual(before,[tuple(r) for r in self.db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name')])
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0],'ok');self.assertFalse(self.db.execute('PRAGMA foreign_key_check').fetchall())
    def test_selected_reminder_only_completed_with_link(self):
        first=self.create_reminder();second=self.create_reminder()
        intervention=self.perform(reminder_id=first,reminder_revision='1');self.db.commit()
        rows={r['reminder_uuid']:dict(r) for r in self.db.execute('SELECT * FROM machine_reminders')}
        self.assertEqual(rows[first]['state'],'done');self.assertEqual(rows[first]['intervention_uuid'],intervention)
        self.assertEqual(rows[second]['state'],'pending');self.assertIsNone(rows[second]['intervention_uuid'])
    def test_double_submission_refused_without_extra_intervention(self):
        first=self.create_reminder();self.db.commit()
        with self.db:self.perform(reminder_id=first,reminder_revision='1')
        with self.assertRaises(ValueError),self.db:self.perform(reminder_id=first,reminder_revision='1')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM machine_interventions').fetchone()[0],1)
    def test_failed_intervention_keeps_reminder_pending(self):
        first=self.create_reminder();self.db.commit()
        with self.assertRaises(ValueError),self.db:
            m.intervention(self.db,self.key,dict(performed_on=date.today().isoformat(),kind='care',description='',reminder_id=first,reminder_revision='1'),'moderator','moderator')
        self.assertEqual(self.db.execute('SELECT state FROM machine_reminders').fetchone()[0],'pending')
    def test_intervention_never_implicitly_changes_machine_status(self):
        m.set_condition(self.db,self.key,dict(status='out_of_service'),'admin','admin')
        self.perform(status='operational');self.assertEqual(m.machine(self.db,self.key)['status'],'out_of_service')
    def test_old_preventive_kind_and_corrections_preserved(self):
        key=m.intervention(self.db,self.key,dict(performed_on=date.today().isoformat(),kind='preventive',description='Ancienne prévention'),'admin','admin')
        self.db.commit();self.login();body=self.client.get('/admin/ressources/'+self.key+'/maintenance').text
        self.assertIn('value="preventive" selected',body)
        m.intervention(self.db,self.key,dict(performed_on=date.today().isoformat(),kind='preventive',description='Correction conservée',revision='1'),'admin','admin',key)
        self.assertEqual(self.db.execute('SELECT kind FROM machine_interventions').fetchone()[0],'preventive')
    def test_reminder_new_is_pending_even_if_state_submitted(self):
        m.reminder(self.db,self.key,dict(due_on=date.today().isoformat(),subject='Nouveau',state='done'),'admin','admin')
        self.assertEqual(self.db.execute('SELECT state FROM machine_reminders').fetchone()[0],'pending')
    def test_reminder_postpone_cancel_and_close_with_revision(self):
        for action in ('reminder_reschedule','reminder_cancel','reminder_close'):
            key=self.create_reminder();m.reminder_action(self.db,self.key,dict(identifier=key,revision='1',action=action,due_on='2027-01-02'),'moderator','moderator')
            value=self.db.execute('SELECT * FROM machine_reminders WHERE reminder_uuid=?',(key,)).fetchone()
            self.assertEqual(value['state'],{'reminder_reschedule':'pending','reminder_cancel':'cancelled','reminder_close':'done'}[action])
            self.assertIsNone(value['intervention_uuid'])
    def test_cross_machine_link_refused(self):
        key=self.create_reminder();other=m.directory(self.db)[1]['resource_uuid']
        with self.assertRaises(ValueError):m.intervention(self.db,other,dict(performed_on=date.today().isoformat(),kind='care',description='Test',reminder_id=key,reminder_revision='1'),'moderator','moderator')
    def test_asymmetric_visibility_requires_explicit_shared_publication(self):
        for announce,listed in ((0,1),(1,0),(0,0),(1,1)):
            m.set_condition(self.db,self.key,dict(status='maintenance',announce=announce,public_listed=listed),'admin','admin')
            if announce!=listed:
                self.assertFalse(m.public_machines(self.db))
                self.assertEqual(bool(m.public_machines(self.db,True)),bool(announce))
            values=dict(status='maintenance',visibility_controls='1',public_visible='1' if announce and listed else '0')
            m.set_condition(self.db,self.key,values,'moderator','moderator');machine=m.machine(self.db,self.key)
            self.assertEqual((machine['announce'],machine['public_listed']),(int(bool(announce and listed)),)*2)
        m.set_condition(self.db,self.key,dict(status='maintenance',visibility_controls='1',public_visible='1'),'moderator','moderator')
        self.assertTrue(m.public_machines(self.db));self.assertTrue(m.public_machines(self.db,True))
    def test_main_visibility_off_hides_both_channels(self):
        m.set_condition(self.db,self.key,dict(status='maintenance',announce='1',public_listed='1',visibility_controls='1'),'admin','admin')
        self.assertFalse(m.public_machines(self.db));self.assertFalse(m.public_machines(self.db,True))
    def test_previous_incident_never_republished_after_operational(self):
        m.set_condition(self.db,self.key,dict(status='maintenance',public_reason='Ancienne panne',return_estimate='2027-01-01',announce=1,public_listed=1,publish_return=1),'admin','admin')
        m.set_condition(self.db,self.key,dict(m.machine(self.db,self.key),status='operational'),'admin','admin')
        machine=m.machine(self.db,self.key);self.assertEqual(machine['public_reason'],'');self.assertIsNone(machine['return_estimate'])
        m.set_condition(self.db,self.key,dict(machine,status='maintenance'),'admin','admin')
        self.assertEqual(m.public_machines(self.db)[0]['reason'],'');self.assertIsNone(m.public_machines(self.db)[0]['return_estimate'])
        self.assertTrue(any('Ancienne panne' in row['before_json'] for row in self.db.execute('SELECT * FROM machine_history')))
    def test_operational_never_unavailability_message(self):
        m.set_condition(self.db,self.key,dict(status='operational',announce=1,public_listed=1,public_reason='Ne pas publier'),'admin','admin')
        self.assertFalse(m.public_machines(self.db,True));self.assertEqual(m.public_machines(self.db)[0]['reason'],'')
    def test_maintenance_forms_compact_and_internal(self):
        self.login();body=self.client.get('/admin/ressources/'+self.key+'/maintenance').text
        self.assertIn('Historique des interventions',body);self.assertIn('Rappels à venir',body)
        self.assertNotIn('Changement de statut, facultatif',body);self.assertNotIn('indépendamment',body)
        self.assertIn('machine-unavailable-fields" hidden',body);self.assertNotIn('<pre>',body)
    def test_team_and_csrf_linked_routes(self):
        key=self.create_reminder();self.db.commit()
        for role in ('admin','moderator'):
            token=self.login(role)
            self.assertEqual(self.client.get('/admin/ressources/'+self.key+'/maintenance').status_code,200)
            self.assertEqual(self.client.post('/admin/ressources/'+self.key+'/maintenance',data=dict(action='reminder_cancel',identifier=key,revision='1')).status_code,400)
            self.assertEqual(self.client.post('/admin/ressources/'+self.key+'/maintenance',data=dict(action='reminder_reschedule',identifier=key,revision='1' if role=='admin' else '2',due_on='2027-01-03',evolution_csrf=token)).status_code,302)
        outsider=self.f.f.app.test_client();self.assertNotEqual(outsider.get('/admin/maintenance/'+self.key).status_code,200)
    def test_calendar_checkbox_preserves_last_form_value(self):
        from fablab_calendar import show_maintenance
        self.assertTrue(show_maintenance(MultiDict([('maintenance','0'),('maintenance','1')])));self.assertFalse(show_maintenance(MultiDict([('maintenance','0')])))
        self.login();body=self.client.get('/admin/calendrier?view=week&maintenance=0').text
        self.assertIn('Afficher entretiens et rappels',body);self.assertIn('maintenance=0',body)
        self.assertNotIn('data-calendar-maintenance checked',body)
    def test_closure_hides_regular_public_openlab_without_publish_checkbox(self):
        import openlab_openings as openings
        day=date.today();write_setting(self.db,'openlab_public_enabled','1')
        openings.save_exception(self.db,dict(day=day.isoformat(),kind='closed'),'admin')
        self.assertFalse(openings.public_openings(self.db,[dict(active=True,start='10:00',end='18:00')]*7,day,day+timedelta(days=1)))
    def test_disabled_language_switch_reverts_public_not_admin(self):
        write_setting(self.db,'kiosk_language','fr');write_setting(self.db,'kiosk_language_switch_enabled','0');self.db.commit()
        with self.client.session_transaction() as session:session['kiosk_language_selected']='en';session['admin_language']='en'
        page=self.client.get('/');self.assertIn('lang="fr"',page.text);self.assertNotIn('<details class="ui-language-menu"',page.text)
        with self.client.session_transaction() as session:self.assertEqual(session['admin_language'],'en');self.assertNotIn('kiosk_language_selected',session)
    def test_default_switch_shown_only_with_multiple_languages(self):
        self.assertIn('ui-language-menu',self.client.get('/').text)
        write_setting(self.db,'kiosk_languages','fr');self.db.commit();self.assertNotIn('<details class="ui-language-menu"',self.client.get('/').text)
    def test_disabled_switch_cannot_be_changed_by_direct_post(self):
        token=self.login();write_setting(self.db,'kiosk_language_switch_enabled','0');self.db.commit()
        self.assertEqual(self.client.post('/langue',data=dict(evolution_csrf=token,scope='kiosk',language='en')).status_code,400)
    def test_kiosk_option_persistence_independent_of_admin_language(self):
        token=self.login();values=dict(group='kiosk',language='en',allow_fr='1',allow_en='1',idle='8',machine_information='both',evolution_csrf=token)
        self.client.post('/admin/reglages/2-14',data=values)
        self.assertEqual(self.db.execute("SELECT value FROM app_settings WHERE key='kiosk_language_switch_enabled'").fetchone()[0],'0')
        self.assertIn('lang="en"',self.client.get('/').text)
        self.client.post('/admin/reglages/2-14',data=dict(values,language_switch='1'))
        self.assertEqual(self.db.execute("SELECT value FROM app_settings WHERE key='kiosk_language_switch_enabled'").fetchone()[0],'1')
