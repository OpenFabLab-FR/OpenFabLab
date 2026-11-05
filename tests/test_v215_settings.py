"""Existing preferences remain local to each form; setup never resets them."""
import json
import unittest
from tests import test_v214_core as core
from family_model import setting
from app import write_setting,load_openlab_schedule
import admin_summary
import app

class Settings(unittest.TestCase):
    setUp=core.NewVersion.setUp
    login=core.NewVersion.login

    def post(self,step,**values):
        state=json.loads(setting(self.db,'setup_progress','{}'))
        return self.client.post('/admin/reglages/assistant',data=dict(evolution_csrf=self.token,
            step=step,revision=str(state.get('revision',0)),**values))

    def test_all_groups_render_and_moved_controls_present_once(self):
        self.login()
        pages={key:self.client.get('/admin/reglages/'+key) for key in ('accueil','structure','borne','affichage','activites','ressources','notifications','wordpress','assistant','donnees','systeme/mises-a-jour')}
        for key,response in pages.items():
            with self.subTest(key=key):self.assertEqual(response.status_code,200)
        self.assertNotIn('id="reservations"',pages['structure'].text)
        self.assertIn('id="reservations"',pages['wordpress'].text)
        self.assertIn('name="resource_public_name"',pages['ressources'].text)
        self.assertIn('id="smtp-settings"',pages['notifications'].text)
        self.assertIn('id="presences-animations"',pages['activites'].text)

    def test_calendar_form_only_updates_its_own_settings(self):
        token=self.login();write_setting(self.db,'discord_sync_delay_minutes','17');write_setting(self.db,'kiosk_sound_volume','0.38');self.db.commit()
        before=dict(self.db.execute('SELECT key,value FROM app_settings'))
        data={day['key']+suffix:('10:00' if suffix=='_start' else '15:00') for day in load_openlab_schedule(self.db) for suffix in ('_start','_end')}
        self.assertEqual(self.client.post('/admin/reglages/activites',data=data|dict(group='hours',evolution_csrf=token)).status_code,302)
        after=dict(self.db.execute('SELECT key,value FROM app_settings'))
        changed={key for key in after if after[key]!=before.get(key)}
        self.assertTrue(changed);self.assertTrue(all(key.startswith('openlab_attendance_') for key in changed))
        self.assertEqual(after['discord_sync_delay_minutes'],'17');self.assertEqual(after['kiosk_sound_volume'],'0.38')

    def test_setup_existing_install_not_forced_and_get_is_read_only(self):
        self.login();self.assertEqual(setting(self.db,'setup_completed'),'1')
        before=dict(self.db.execute('SELECT key,value FROM app_settings'))
        self.assertEqual(self.client.get('/admin').status_code,200)
        self.assertEqual(self.client.get('/admin/reglages/assistant').status_code,200)
        self.assertEqual(before,dict(self.db.execute('SELECT key,value FROM app_settings')))

    def test_new_install_setup_redirects_only_admin_home(self):
        self.login();write_setting(self.db,'setup_completed','0');self.db.commit()
        self.assertIn('/admin/reglages/assistant',self.client.get('/admin').location)
        self.assertEqual(self.client.get('/admin/reglages/structure').status_code,200)
        self.assertEqual(self.client.get('/').status_code,200)

    def test_setup_saves_progress_without_secrets_and_preserves_errors(self):
        self.token=self.login();write_setting(self.db,'fictional_secret','NEVER_DISPLAY');self.db.commit()
        response=self.post('identity',name='Atelier fictif',short_name='Essai',city='Ville exemple',country='France',timezone='Europe/Paris')
        self.assertEqual(response.status_code,302);self.assertEqual(setting(self.db,'structure_name'),'Atelier fictif')
        self.assertEqual(json.loads(setting(self.db,'setup_progress'))['step'],'kiosk')
        response=self.post('kiosk',home_title='Mon texte personnalisé',language='unknown')
        self.assertEqual(response.status_code,200);self.assertIn('Mon texte personnalisé',response.text)
        self.assertNotIn('NEVER_DISPLAY',response.text)
        self.assertEqual(setting(self.db,'fictional_secret'),'NEVER_DISPLAY')
        self.assertNotIn('NEVER_DISPLAY',setting(self.db,'setup_progress'))

    def test_counter_only_preset_is_voluntary_and_does_not_delete_data(self):
        self.token=self.login();before=self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        self.assertEqual(self.post('modules',preset='counter').status_code,302)
        self.assertEqual(app.load_modules(self.db),{key:key in ('users','frequency') for key in app.MODULE_LABELS})
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],before)
        self.assertEqual(self.client.get('/admin').status_code,200)

    def test_save_and_resume_later_saves_current_fields_not_only_progress(self):
        self.token=self.login()
        result=self.post('identity',action='later',name='Atelier enregistré',short_name='AE',city='',country='',timezone='Europe/Paris')
        self.assertEqual(result.status_code,302)
        self.assertEqual(setting(self.db,'structure_name'),'Atelier enregistré')
        self.assertEqual(json.loads(setting(self.db,'setup_progress'))['step'],'kiosk')
        result=self.post('identity',action='later',name='Saisie conservée',timezone='incorrect')
        self.assertEqual(result.status_code,200);self.assertIn('Saisie conservée',result.text)
        self.assertEqual(setting(self.db,'structure_name'),'Atelier enregistré')

    def test_first_resource_replay_does_not_duplicate(self):
        self.token=self.login();category=self.db.execute('SELECT type_key FROM resource_types WHERE active=1 LIMIT 1').fetchone()[0]
        data=dict(evolution_csrf=self.token,step='resources',revision='0',name='Machine fictive unique',type_key=category)
        self.assertEqual(self.client.post('/admin/reglages/assistant',data=data).status_code,302)
        self.assertEqual(self.client.post('/admin/reglages/assistant',data=data).status_code,200)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM resources WHERE name='Machine fictive unique'").fetchone()[0],1)

    def test_permissions_and_csrf(self):
        self.login('moderator')
        for path in ('assistant','activites','accueil','ressources','wordpress'):
            self.assertNotEqual(self.client.get('/admin/reglages/'+path).status_code,200)
        with self.client.session_transaction() as session:session.clear()
        self.login()
        self.assertEqual(self.client.post('/admin/reglages/assistant',data=dict(step='summary',action='finish')).status_code,400)
        self.assertEqual(self.client.post('/admin/reglages/activites',data=dict(group='display',start='09:00',end='18:00')).status_code,400)

    def test_summary_respects_modules_roles_and_is_read_only(self):
        self.login();modules={key:False for key in app.MODULE_LABELS}
        write_setting(self.db,'module_maintenance','0');self.db.commit()
        with self.f.f.app.test_request_context('/admin'):
            before=self.db.total_changes
            result=admin_summary.build(self.db,modules,'moderator')
            self.assertEqual(result,dict(cards=[],actions=[],upcoming=[],recent=[]))
            result=admin_summary.build(self.db,app.load_modules(self.db),'moderator')
            self.assertNotIn('Factures',str(result));self.assertEqual(self.db.total_changes,before)

if __name__=='__main__':unittest.main()
