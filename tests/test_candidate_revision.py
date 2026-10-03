"""Ergonomic revision: fictional fixtures only, no production dependencies."""
import re
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock
from flask import session
from tests import test_app as fixtures
import app
import evolution_schema
from fablab_calendar import calendar_view
from profile_archive import build_profile, parse_profile


class CandidateRevisionTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.OpenFabLabTestCase(); self.f.setUp(); self.addCleanup(self.f.tearDown)
        self.client = self.f.app.test_client()
        with self.client.session_transaction() as s:
            s['access_role']='admin';s['admin_authenticated']=True

    def configure(self, **values):
        with self.f.database() as db:
            for key,value in values.items():app.write_setting(db,key,value)

    def calendar(self, selected='2099-10-08'):
        with self.f.app.test_request_context('/admin/calendrier'):
            session['access_role']='admin'
            return calendar_view(app.get_database(),{'date':selected},app)

    def structure_post(self, values):
        page=self.client.get('/admin/reglages/structure').get_data(as_text=True)
        token=re.search(r'name="csrf_token" value="([^"]+)"',page)[1]
        return self.client.post('/admin/reglages/structure',data=dict(values,csrf_token=token))

    def test_new_install_has_only_three_categories_and_default_window(self):
        with tempfile.TemporaryDirectory() as folder:
            candidate=app.create_app(dict(TESTING=True,DATABASE=str(Path(folder)/'new.db'),SECRET_KEY='fictive',
                SEED_DEMO_USERS=False,ADMIN_PIN=None,MODERATOR_PIN=None,WEATHER_ENABLED=False,AUTO_CLOSURE_WORKER=False))
            with candidate.app_context():
                db=app.get_database()
                self.assertEqual([(r['category_key'],r['name']) for r in evolution_schema.categories(db)],
                                 [('user','Usager'),('volunteer','Bénévole'),('manager','Manager')])
                self.assertEqual(app.read_setting(db,'calendar_display_start'),'09:00')
                self.assertEqual(app.read_setting(db,'calendar_display_end'),'19:00')
                self.assertEqual(db.execute('SELECT COUNT(*) FROM users').fetchone()[0],0)

    def test_empty_existing_schema13_retains_six_categories_including_intern(self):
        with tempfile.TemporaryDirectory() as folder:
            config=dict(TESTING=True,DATABASE=str(Path(folder)/'old.db'),SECRET_KEY='fictive',SEED_DEMO_USERS=False,
                        ADMIN_PIN=None,MODERATOR_PIN=None,WEATHER_ENABLED=False,AUTO_CLOSURE_WORKER=False)
            with mock.patch.object(app,'migrate_evolution',lambda db,**kwargs:None):app.create_app(config)
            candidate=app.create_app(config)
            with candidate.app_context():
                db=app.get_database()
                self.assertEqual({r['category_key'] for r in evolution_schema.categories(db)},set(evolution_schema.HISTORICAL_CATEGORIES))
                self.assertEqual(evolution_schema.default_category(db),'user')

    def test_calendar_default_window_compact(self):
        view=self.calendar()
        self.assertEqual((view['visible_start'],view['visible_end'],view['timeline_height']),('09:00','19:00',600))
        self.assertFalse(view['window_extended'])
        self.assertEqual(len(view['hours']),10)

    def test_calendar_configurable_display_only(self):
        with self.f.database() as db:before=app.load_openlab_schedule(db)
        self.configure(calendar_display_start='08:30',calendar_display_end='20:15')
        view=self.calendar()
        self.assertEqual((view['visible_start'],view['visible_end']),('08:30','20:15'))
        with self.f.database() as db:self.assertEqual(app.load_openlab_schedule(db),before)

    def test_calendar_settings_invalid_server_rejected(self):
        self.client.post('/admin/reglages/affichage/enregistrer',data=dict(calendar_display_start='19:00',calendar_display_end='09:00'))
        with self.f.database() as db:self.assertEqual(app.read_setting(db,'calendar_display_start'),'09:00')
        self.client.post('/admin/reglages/affichage/enregistrer',data=dict(calendar_display_start='08:15',calendar_display_end='20:30'))
        with self.f.database() as db:self.assertEqual(app.read_setting(db,'calendar_display_start'),'08:15')

    def test_calendar_extends_for_out_of_range_booking(self):
        import resource_booking
        with self.f.database() as db:
            key=resource_booking.save_resource(db,dict(name='Ressource fictive',type_key='machine',active=True),'admin')
            user=db.execute('SELECT id FROM users LIMIT 1').fetchone()[0]
            resource_booking.book(db,key,user,'2099-10-08T07:00:00+02:00','2099-10-08T08:00:00+02:00','admin')
        view=self.calendar()
        self.assertTrue(view['window_extended']);self.assertEqual(view['visible_start'],'07:00')
        self.assertTrue(any(e['title'].startswith('Ressource fictive') for d in view['days'] for e in d['events']))

    def test_future_openlabs_have_no_attendance_count(self):
        self.assertTrue(any(e['kind']=='openlab' for d in self.calendar()['days'] for e in d['events']))
        self.assertTrue(all('attendance' not in e for d in self.calendar()['days'] for e in d['events'] if e['kind']=='openlab'))

    def test_past_openlab_uses_existing_attendance_and_preserves_rows(self):
        self.configure(openlab_attendance_tuesday_start='14:00',openlab_attendance_tuesday_end='17:00')
        with self.f.database() as db:
            user=db.execute('SELECT id FROM users LIMIT 1').fetchone()[0]
            db.execute("INSERT INTO sessions(user_id,check_in,check_out) VALUES(?,'2020-10-06T12:30:00+00:00','2020-10-06T13:00:00+00:00')",(user,))
            db.execute("INSERT INTO visitors(created_at) VALUES('2020-10-06T12:30:00+00:00')")
            before=[tuple(r) for r in db.execute('SELECT * FROM sessions')]
        view=self.calendar('2020-10-06')
        event=next(e for d in view['days'] for e in d['events'] if e['kind']=='openlab' and str(e['day'])=='2020-10-06')
        self.assertEqual(event['attendance'],'1 usager · 1 visiteur')
        with self.f.database() as db:self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM sessions')],before)

    def test_overview_first_subtab_keeps_legacy_route(self):
        page=self.client.get('/admin/animations').get_data(as_text=True)
        self.assertIn('Aperçu',page)
        self.assertLess(page.index('>Aperçu</a>'),page.index('>Ressources</a>'))

    def test_disabled_modules_hide_navigation_and_block_mutations_without_deletion(self):
        self.client.get('/admin/ressources')
        self.configure(module_resources='0',module_authorizations='0')
        page=self.client.get('/admin/animations').get_data(as_text=True)
        for label in ('>Ressources</a>','>Réservations de ressources</a>','>Formations et habilitations</a>'):
            self.assertNotIn(label,page)
        for path in ('/admin/ressources','/admin/ressources/reservations','/admin/habilitations'):
            self.assertIn(self.client.get(path).status_code,(302,403,404))
            self.assertIn(self.client.post(path,data={'action':'definition','name':'Blocked'}).status_code,(302,403,404))
        with self.f.database() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM resources').fetchone()[0],6)

    def test_cannot_disable_authorizations_with_active_dependent_resource(self):
        self.client.get('/admin/ressources')
        with self.f.database() as db:
            db.execute("INSERT INTO authorizations VALUES('fictive','Habilitation exemple','',1,'2026-01-01')")
            db.execute("UPDATE resources SET required_authorization='fictive' WHERE active=1")
        response=self.structure_post({'module_resources':'1','module_activities':'1','module_billing':'1'})
        with self.f.database() as db:self.assertEqual(app.read_setting(db,'module_authorizations'),'1')
        page=self.client.get(response.headers['Location']).get_data(as_text=True)
        self.assertIn('ressources actives dépendantes',page)

    def test_can_disable_authorizations_after_explicitly_deactivating_dependents(self):
        with self.f.database() as db:db.execute('UPDATE resources SET active=0')
        self.structure_post({'module_resources':'1','module_activities':'1','module_billing':'1'})
        with self.f.database() as db:self.assertEqual(app.read_setting(db,'module_authorizations'),'0')

    def test_seven_settings_tabs_in_requested_order(self):
        page=self.client.get('/admin/reglages/usagers').get_data(as_text=True)
        nav=re.search(r'<nav[^>]*settings-subtabs.*?</nav>',page,re.S)[0]
        self.assertEqual(re.findall(r'>([^<>]+)</a>',nav),['Affichage','Usagers','Borne','Notifications','Tarifs','Données','Structure'])
        self.assertIn('Usagers et catégories',page)
        self.assertNotIn('Les catégories décrivent les personnes',page)

    def test_smtp_in_structure_discord_in_notifications_privacy_in_data(self):
        self.assertIn('id="smtp"',self.client.get('/admin/reglages/structure').get_data(as_text=True))
        self.assertIn('Notifications à la création d’usager',self.client.get('/admin/reglages/notifications').get_data(as_text=True))
        self.assertIn('name="dpo"',self.client.get('/admin/reglages/donnees').get_data(as_text=True))
        self.assertNotIn('name="dpo"',self.client.get('/admin/reglages/structure').get_data(as_text=True))

    def test_privacy_form_preserves_all_modules_and_other_fields(self):
        with self.f.database() as db:before=app.load_modules(db);name=app.read_setting(db,'structure_name')
        self.structure_post({'privacy_only':'1','dpo':'Service fictif libre','dpo_email':'dpo@example.invalid'})
        with self.f.database() as db:
            self.assertEqual(app.load_modules(db),before)
            self.assertEqual(app.read_setting(db,'structure_name'),name)
            self.assertEqual(app.read_setting(db,'structure_dpo'),'Service fictif libre')

    def test_footer_only_account_link_and_optional_activation(self):
        self.configure(self_enrollment_enabled='1')
        page=self.client.get('/').get_data(as_text=True)
        self.assertEqual(page.count('>Créer un compte</a>'),1)
        self.assertIn('Créer un compte',page.split('<footer')[1])
        self.assertNotIn('Créer un compte',page.split('<footer')[0])
        self.configure(self_enrollment_enabled='0')
        self.assertNotIn('>Créer un compte</a>',self.client.get('/').get_data(as_text=True))

    def test_profile_roundtrips_new_window_and_modules_and_rejects_invalid(self):
        settings={'calendar_display_start':'08:30','calendar_display_end':'20:15','module_resources':'0','module_authorizations':'1'}
        self.assertEqual(parse_profile(build_profile(settings,[],{}))['settings'],settings)
        with self.assertRaises(ValueError):parse_profile(build_profile(dict(settings,calendar_display_end='07:30'),[],{}))

    def test_moderator_business_allowed_admin_settings_forbidden(self):
        with self.client.session_transaction() as s:s['access_role']='moderator';s.pop('admin_authenticated',None)
        for path in ('/admin/calendrier','/admin/ressources','/admin/ressources/reservations','/admin/habilitations'):
            self.assertEqual(self.client.get(path).status_code,200)
        for path in ('/admin/reglages/structure','/admin/reglages/usagers','/admin/reglages/donnees','/admin/reglages/notifications'):
            self.assertIn(self.client.get(path).status_code,(302,403))
