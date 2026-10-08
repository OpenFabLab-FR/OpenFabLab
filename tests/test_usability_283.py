"""2.8.3 invariants, fictional accounts only, no outbound service required."""
import concurrent.futures
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from flask.testing import FlaskClient
from tests import test_app as fixtures
import app as application
import usability as ui
import family_model
from profile_archive import build_profile, parse_profile


class UsabilityTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.OpenFabLabTestCase(); self.f.setUp(); self.addCleanup(self.f.tearDown)
        self.db=self.f.database(); self.addCleanup(self.db.close)
        self.f.app.test_client_class=FlaskClient
        self.client=self.f.app.test_client()
        self.set(self_enrollment_enabled='1')

    def set(self, **values):
        for key,value in values.items(): application.write_setting(self.db,key,value)
        self.db.commit()

    def form(self, code='0042', **extra):
        return dict(first_name='Camille',last_name='EXEMPLE',birth_year='1990',
                    city='Ville exemple',nationality='Française',
                    email='camille@example.invalid',phone='0600000000',phone_country_code='+33',
                    public_id=code,category='user',active='1',**extra)

    def page(self, client=None):
        client=client or self.client
        page=client.get('/inscription')
        self.assertEqual(page.status_code,200)
        return re.search(r'name="evolution_csrf" value="([^"]+)"',page.text)[1],page.text

    def enroll(self, values=None, client=None):
        client=client or self.client
        token,_=self.page(client)
        return client.post('/inscription',data=dict(values or self.form(),evolution_csrf=token))

    def test_new_installation_recommends_visible(self):
        self.assertEqual(dict(application.default_application_settings())['public_id_assignment_mode'],'automatic_visible')
        self.assertEqual(ui.enrollment_mode(self.db),'automatic_visible')

    def test_existing_installation_preserves_discreet_and_settings(self):
        self.db.execute("DELETE FROM app_settings WHERE key='public_id_assignment_mode'")
        self.db.execute('PRAGMA user_version=17'); self.db.commit()
        application.create_app(dict(self.f.app.config))
        self.assertEqual(ui.enrollment_mode(self.db),'automatic_discreet')
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],18)

    def test_existing_choice_retained_on_restart(self):
        self.set(public_id_assignment_mode='customizable',attendance_reference='30')
        application.create_app(dict(self.f.app.config))
        self.assertEqual(ui.enrollment_mode(self.db),'customizable')
        self.assertEqual(ui.attendance_reference(self.db),30)

    def test_discreet_ignores_forged_public_id(self):
        self.set(public_id_assignment_mode='automatic_discreet')
        _,html=self.page(); self.assertNotIn('name="public_id"',html)
        self.assertEqual(self.enroll().status_code,302)
        self.assertNotEqual(self.db.execute("SELECT public_id FROM users WHERE created_source='kiosk'").fetchone()[0],'0042')

    def test_visible_code_is_readonly_and_server_controlled(self):
        token,html=self.page(); self.assertIn('readonly',html)
        with self.client.session_transaction() as s: proposed=s['enrollment_proposal']
        result=self.client.post('/inscription',data=dict(self.form('0042'),evolution_csrf=token))
        self.assertEqual(result.status_code,302)
        self.assertEqual(self.db.execute("SELECT public_id FROM users WHERE created_source='kiosk'").fetchone()[0],proposed)

    def test_custom_preserves_leading_zero_and_receipt_qr(self):
        self.set(public_id_assignment_mode='customizable')
        self.assertEqual(self.enroll().status_code,302)
        self.assertEqual(self.db.execute("SELECT public_id FROM users WHERE created_source='kiosk'").fetchone()[0],'0042')
        self.assertIn('0042',self.client.get('/inscription/terminee').text)
        self.assertEqual(self.client.get('/inscription/qr.png').status_code,200)

    def test_invalid_custom_codes_do_not_create(self):
        self.set(public_id_assignment_mode='customizable')
        before=self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        for code in ('12','abcd','１２３４','12345','0042 '):
            # Leading/trailing whitespace is normalized by the existing form.
            if code.endswith(' '): continue
            self.assertEqual(self.enroll(self.form(code)).status_code,400)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],before)

    def test_used_code_has_no_other_account_data(self):
        self.set(public_id_assignment_mode='customizable')
        code=self.db.execute('SELECT public_id FROM users LIMIT 1').fetchone()[0]
        result=self.enroll(self.form(code)); self.assertEqual(result.status_code,409)
        self.assertIn('proposé',result.text)
        self.assertNotIn('Victor',result.text)

    def test_collision_after_display_requires_new_confirmation(self):
        token,_=self.page()
        with self.client.session_transaction() as s: code=s['enrollment_proposal']
        self.db.execute("INSERT INTO users(public_id,first_name,last_name,active,category,created_at) VALUES(?, 'Autre','FICTIF',1,'user','2026-01-01')",(code,)); self.db.commit()
        result=self.client.post('/inscription',data=dict(self.form(),evolution_csrf=token))
        self.assertEqual(result.status_code,409)
        with self.client.session_transaction() as s: self.assertNotEqual(s['enrollment_proposal'],code)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM users WHERE created_source='kiosk'").fetchone()[0],0)

    def test_parallel_custom_creation_unique(self):
        self.set(public_id_assignment_mode='customizable')
        clients=[self.f.app.test_client(),self.f.app.test_client()]
        tokens=[self.page(c)[0] for c in clients]
        def create(index):
            return clients[index].post('/inscription',data=dict(self.form(),evolution_csrf=tokens[index])).status_code
        with concurrent.futures.ThreadPoolExecutor(2) as pool: states=list(pool.map(create,range(2)))
        self.assertEqual(sorted(states),[302,409])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM users WHERE public_id='0042'").fetchone()[0],1)

    def test_sequential_submission_replay_not_create_second_user(self):
        token,_=self.page(); payload=dict(self.form(),evolution_csrf=token)
        self.assertEqual(self.client.post('/inscription',data=payload).status_code,302)
        self.assertEqual(self.client.post('/inscription',data=payload).status_code,400)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM users WHERE created_source='kiosk'").fetchone()[0],1)

    def test_mode_changed_while_form_open_requires_confirmation(self):
        token,_=self.page();self.set(public_id_assignment_mode='customizable')
        self.assertEqual(self.client.post('/inscription',data=dict(self.form(),evolution_csrf=token)).status_code,409)

    def test_public_forgery_cannot_add_structure_or_rights(self):
        result=self.enroll(self.form(affiliation_name='FAUX DROITS',affiliation_client_id='123'))
        self.assertEqual(result.status_code,302)
        user=self.db.execute("SELECT * FROM users WHERE created_source='kiosk'").fetchone()
        self.assertIsNone(user['affiliation_client_id']);self.assertEqual(user['affiliation_name'],'')
        self.assertEqual(user['category'],'user')

    def test_public_has_no_affiliation_directory(self):
        _,html=self.page();self.assertNotIn('name="affiliation_client_id"',html)
        self.assertNotIn('name="affiliation_name"',html)

    def test_csrf_and_abuse_guard(self):
        self.page(); self.assertEqual(self.client.post('/inscription',data=self.form()).status_code,400)
        for _ in range(5): self.assertEqual(self.enroll({'first_name':'Fictif'}).status_code,400)
        self.assertEqual(self.enroll({'first_name':'Fictif'}).status_code,429)

    def test_public_form_private_no_store(self):
        self.assertIn('no-store',self.client.get('/inscription').headers['Cache-Control'])

    def test_team_creation_custom_in_all_public_modes(self):
        for i,(role,mode) in enumerate((role,mode) for role in ('admin','moderator') for mode in ui.ID_MODES):
            self.set(public_id_assignment_mode=mode)
            client=self.f.app.test_client()
            with client.session_transaction() as s:s['access_role']=role
            page=client.get('/admin/usagers/nouveau').text
            token=re.search(r'name="evolution_csrf" value="([^"]+)"',page)[1]
            values=self.form(f'00{i+10}'); values['first_name']=('Alice','Béatrice','Camille','Daniel','Élodie','Félix')[i]
            values['confirm_duplicates']='1'
            result=client.post('/admin/usagers/nouveau',data=dict(values,evolution_csrf=token))
            self.assertEqual(result.status_code,302,re.findall(r'<li>(.*?)</li>',result.text,re.S))
            self.assertIsNotNone(self.db.execute('SELECT id FROM users WHERE public_id=?',(values['public_id'],)).fetchone())

    def test_free_affiliation_save_modify_remove(self):
        person=self.db.execute('SELECT id FROM users LIMIT 1').fetchone()[0]
        for name in ('Association exemple','Entreprise fictive',''):
            ui.save_affiliation(self.db,person,ui.validate_affiliation(self.db,{'affiliation_name':name}))
            self.assertEqual(self.db.execute('SELECT affiliation_name FROM users WHERE id=?',(person,)).fetchone()[0],name)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM billing_clients').fetchone()[0],0)

    def test_affiliation_validation_rejects_invalid_or_missing(self):
        for form in ({'affiliation_client_id':'99999'},{'affiliation_client_id':'x'},{'affiliation_name':'x'*161},{'affiliation_name':'x\ny'}):
            with self.assertRaises(ValueError): ui.validate_affiliation(self.db,form)

    def test_existing_structure_multiple_people_and_deletion_keeps_name(self):
        stamp='2026-01-01T00:00:00+00:00'
        key=self.db.execute("INSERT INTO billing_clients(contact_name,contact_name_normalized,structure_name,address_line,postal_code,city,created_at,updated_at) VALUES(?,?,?,'','','',?,?)",('Contact fictif','contact fictif','Atelier fictif',stamp,stamp)).lastrowid
        people=[r[0] for r in self.db.execute('SELECT id FROM users LIMIT 2')]
        for person in people:ui.save_affiliation(self.db,person,ui.validate_affiliation(self.db,{'affiliation_client_id':str(key)}))
        self.assertEqual([r[0] for r in self.db.execute('SELECT id FROM billing_clients')],[key])
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.commit(); self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('DELETE FROM billing_clients WHERE id=?',(key,)); self.db.commit()
        for person in people:
            row=self.db.execute('SELECT affiliation_client_id,affiliation_name FROM users WHERE id=?',(person,)).fetchone()
            self.assertEqual(tuple(row),(None,'Atelier fictif'))

    def test_profile_settings_roundtrip_and_invalid_values(self):
        for mode in ui.ID_MODES:
            parsed=parse_profile(build_profile({'public_id_assignment_mode':mode,'attendance_reference':'30'},[],{}))
            self.assertEqual(parsed['settings']['public_id_assignment_mode'],mode)
            self.assertEqual(parsed['settings']['attendance_reference'],'30')
        for values in ({'public_id_assignment_mode':'unknown'},{'attendance_reference':'0'}):
            with self.assertRaises(ValueError):parse_profile(build_profile(values,[],{}))

    def test_attendance_boundaries_do_not_block_arrival(self):
        self.set(attendance_reference='1')
        for person in ('1001','1002'):
            self.assertEqual(self.client.post('/identification',data={'public_id':person}).status_code,302)
        self.assertGreaterEqual(self.db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],1)
        html=self.client.get('/').text;self.assertIn('/1',html)

    def test_attendance_validation_and_fallback(self):
        for value in ('1','30','10000'): self.assertEqual(ui.validate_reference(value),value)
        for value in ('0','-1','10001','1.5','abc'):
            with self.assertRaises(ValueError):ui.validate_reference(value)
            self.set(attendance_reference=value);self.assertEqual(ui.attendance_reference(self.db),10)

    def test_attendance_post_admin_only_csrf_and_server_validation(self):
        client=self.f.client;self.f.login_admin()
        page=client.get('/admin/reglages/affichage').text
        token=re.search(r'name="evolution_csrf" value="([^"]+)"',page)[1]
        route='/admin/reglages/affichage/frequentation'
        self.assertEqual(client.post(route,data={'attendance_reference':'30','evolution_csrf':token}).status_code,302)
        self.assertEqual(ui.attendance_reference(self.db),30)
        self.assertEqual(client.post(route,data={'attendance_reference':'0','evolution_csrf':token}).status_code,400)
        with client.session_transaction() as s:s['access_role']='moderator'
        self.assertEqual(client.post(route,data={'attendance_reference':'50','evolution_csrf':token}).status_code,302)
        self.assertEqual(ui.attendance_reference(self.db),30)

    def test_paris_summer_winter_and_dst_boundaries(self):
        for value,expected in [('2026-10-07T16:37:31+00:00','07 octobre 2026 à 18h37'),('2026-01-07T16:37:31+00:00','07 janvier 2026 à 17h37'),('2026-03-29T00:59:00Z','29 mars 2026 à 01h59'),('2026-03-29T01:00:00Z','29 mars 2026 à 03h00'),('2026-10-25T00:59:00Z','25 octobre 2026 à 02h59'),('2026-10-25T01:00:00Z','25 octobre 2026 à 02h00')]:
            self.assertEqual(ui.french_datetime(self.db,value),expected)

    def test_other_timezones_and_invalid_fallback(self):
        self.set(structure_timezone='America/Montreal')
        self.assertEqual(ui.french_datetime(self.db,'2026-10-07T16:37:31Z'),'07 octobre 2026 à 12h37')
        self.set(structure_timezone='Bad/Zone')
        self.assertEqual(ui.french_datetime(self.db,'2026-10-07T16:37:31Z'),'07 octobre 2026 à 18h37')

    def test_no_change_to_reservation_or_plugin_runtime(self):
        root=Path(__file__).resolve().parents[1]
        self.assertIn('Version: 2.8.2',(root/'wordpress/openfablab-reservations/openfablab-reservations.php').read_text())
        self.assertEqual(dict(application.default_application_settings())['reservation_sync_interval_minutes'],'1.5')
        from outbound_actions import action_interval
        self.assertEqual(action_interval('15'),15)

    def test_migration_idempotent_and_foreign_keys(self):
        before=[tuple(r) for r in self.db.execute('SELECT * FROM users')]
        self.db.commit();family_model.migrate(self.db);family_model.migrate(self.db)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM users')],before)
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_schema17_failure_rolls_back_columns_settings_and_version(self):
        self.db.commit()
        self.db.execute('ALTER TABLE users DROP COLUMN affiliation_client_id')
        self.db.execute('ALTER TABLE users DROP COLUMN affiliation_name')
        self.db.execute("DELETE FROM app_settings WHERE key IN ('public_id_assignment_mode','attendance_reference')")
        self.db.execute('PRAGMA user_version=17');self.db.commit()
        schema=[tuple(r) for r in self.db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name')]
        users=[tuple(r) for r in self.db.execute('SELECT * FROM users')]
        settings=[tuple(r) for r in self.db.execute('SELECT * FROM app_settings ORDER BY key')]
        def interruption(db): raise RuntimeError('Fictional migration interruption')
        with self.assertRaises(RuntimeError):family_model.migrate(self.db,interruption)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],17)
        self.assertEqual(schema,[tuple(r) for r in self.db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name')])
        self.assertEqual(users,[tuple(r) for r in self.db.execute('SELECT * FROM users')])
        self.assertEqual(settings,[tuple(r) for r in self.db.execute('SELECT * FROM app_settings ORDER BY key')])
        family_model.migrate(self.db)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],18)

    def dossier(self):
        self.f.login_admin()
        response=self.f.client.post('/admin/facturation/nouveau',data=dict(
            quote_date='2026-10-08',client_contact='Alex FICTIF',client_structure='Association imaginaire',
            address_line='1 voie fictive',postal_code='00000',city='Ville exemple',
            email='alex@example.invalid',title='Projet fictif de fabrication',
            description='Description autorisée. '+('Explication fictive. '*40),
            activity_date='2026-10-08',activity_time_details='09h00 à 12h00',participants='2',
            rate_category='normal',rate_unit='hourly',rate_quantity='1',travel_quantity='0',
            consumable_mode='included',consumable_quantity='0'))
        self.assertEqual(response.status_code,302)
        record=self.db.execute('SELECT * FROM billing_records ORDER BY id DESC LIMIT 1').fetchone()
        self.assertIsNotNone(record)
        # Link a real dossier to a real service; business creation route is covered separately.
        service=self.db.execute("INSERT INTO fablab_services(service_type,title,description,service_date,start_time,end_time,created_at,updated_at) VALUES('reservation','Projet fictif','Contenu privé du créneau','2026-10-08','09:00','12:00','2026-10-08','2026-10-08')").lastrowid
        self.db.execute('UPDATE billing_records SET service_id=? WHERE id=?',(service,record['id']));self.db.commit()
        return record,service

    def test_calendar_admin_dossier_description_and_link(self):
        record,service=self.dossier()
        html=self.f.client.get('/admin/calendrier?date=2026-10-08').text
        self.assertIn('Association imaginaire',html);self.assertIn('Dossier : '+record['quote_number'],html)
        self.assertIn('Description autorisée',html);self.assertIn('Ouvrir le dossier',html)
        self.assertIn('data-title="Projet fictif de fabrication"',html)
        self.assertIn('/admin/facturation/'+str(record['id']),html)

    def test_calendar_moderator_never_serializes_dossier_even_legacy_flag(self):
        self.dossier()
        with self.f.client.session_transaction() as s:s['access_role']='moderator';s['admin_authenticated']=True
        html=self.f.client.get('/admin/calendrier?date=2026-10-08').text
        self.assertIn('Projet fictif',html)
        for private in ('Association imaginaire','Description autorisée','Contenu privé du créneau','Ouvrir le dossier'):
            self.assertNotIn(private,html)

    def test_calendar_anonymous_redirects(self):
        self.dossier()
        response=self.client.get('/admin/calendrier?date=2026-10-08')
        self.assertEqual(response.status_code,302);self.assertNotIn('Association imaginaire',response.text)

    def test_discord_format_does_not_add_contact_or_code(self):
        from evolution_users import creation_message
        self.set(discord_new_user_enabled='1',discord_new_user_time='1')
        user=dict(self.db.execute('SELECT * FROM users LIMIT 1').fetchone())
        user['created_at']='2026-10-07T16:37:31+00:00'
        message=creation_message(self.db,user)
        self.assertIn('Créé le : 07 octobre 2026 à 18h37',message)
        self.assertNotIn('T16:',message);self.assertNotIn(user['public_id'],message)
        self.assertNotIn('@',message)

    def test_internal_id_and_links_survive_admin_code_change(self):
        self.f.login_admin()
        user=dict(self.db.execute("SELECT * FROM users WHERE public_id='1001'").fetchone())
        other=self.db.execute('SELECT id FROM users WHERE id!=? LIMIT 1',(user['id'],)).fetchone()[0]
        self.db.execute("INSERT INTO user_family_links(link_uuid,member_id,responsible_id,created_at) VALUES('fictitious-preserved-link',?,?, '2026-10-01')",(other,user['id']))
        service=self.db.execute("INSERT INTO fablab_services(service_type,title,service_date,created_at,updated_at) VALUES('animation','Animation fictive','2026-10-08','2026-10-01','2026-10-01')").lastrowid
        self.db.execute("INSERT INTO animation_bookings(external_uuid,service_id,environment,first_name,last_name,status,link_status,public_id,user_id,created_at,updated_at) VALUES('fictitious-preserved-booking',?,'production','Camille','EXEMPLE','cancelled','linked','1001',?,'2026-10-01','2026-10-01')",(service,user['id']))
        booking=tuple(self.db.execute("SELECT * FROM animation_bookings WHERE external_uuid='fictitious-preserved-booking'").fetchone())
        self.db.execute("INSERT INTO sessions(user_id,check_in,check_out) VALUES(?,'2026-10-01T09:00:00','2026-10-01T10:00:00')",(user['id'],));self.db.commit()
        route='/admin/usagers/'+str(user['id'])+'/modifier'
        page=self.f.client.get(route)
        self.assertEqual(page.status_code,200)
        token=re.search(r'name="evolution_csrf" value="([^"]+)"',page.text)[1]
        values=self.form('0007');values.update(first_name=user['first_name'],last_name=user['last_name'])
        response=self.f.client.post(route,data=dict(values,evolution_csrf=token,confirm_duplicates='1'))
        self.assertEqual(response.status_code,302)
        now=self.db.execute('SELECT * FROM users WHERE id=?',(user['id'],)).fetchone()
        self.assertEqual(now['public_id'],'0007');self.assertEqual(now['statistics_key'],user['statistics_key'])
        self.assertEqual(self.db.execute('SELECT user_id FROM sessions ORDER BY id DESC LIMIT 1').fetchone()[0],user['id'])
        self.assertEqual(self.db.execute("SELECT responsible_id FROM user_family_links WHERE link_uuid='fictitious-preserved-link'").fetchone()[0],user['id'])
        self.assertEqual(tuple(self.db.execute("SELECT * FROM animation_bookings WHERE external_uuid='fictitious-preserved-booking'").fetchone()),booking)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])
