"""Shared-device enrollment isolation; fictional accounts, no external calls."""
import re
import time
import unittest
from unittest import mock
from flask.testing import FlaskClient
from tests import test_families as fixtures
from app import write_setting


class EnrollmentPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.FamilyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db=self.f.db;self.app=self.f.f.app
        self.app.test_client_class=FlaskClient;self.client=self.app.test_client()
        write_setting(self.db,'self_enrollment_enabled','1')
        write_setting(self.db,'public_id_assignment_mode','customizable');self.db.commit()
        self.before=self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0]

    def start(self, client=None):
        response=(client or self.client).get('/inscription')
        self.assertEqual(response.status_code,200)
        return re.search(r'name="evolution_csrf" value="([^"]+)"',response.text)[1]

    def verify(self, token=None, **extra):
        token=token or self.start()
        response=self.client.post('/inscription',data=dict(evolution_csrf=token,family_step='verify',guardian_public_id='2001',guardian_contact='person0@example.invalid',public_id='0042',**extra))
        self.assertEqual(response.status_code,200)
        self.assertIn('data-selected-responsible',response.text)
        token=re.search(r'name="evolution_csrf" value="([^"]+)"',response.text)[1]
        return token,response

    def values(self, token):
        return dict(evolution_csrf=token,public_id='0042',first_name='Enfant fictif',last_name='EXEMPLE',
                    birth_year=str(self.f.today.year-10),birth_date=f'{self.f.today.year-10}-01-01',is_minor='1',city='Ville fictive',nationality='Française',
                    phone_country_code='+33',responsible_ids=str(self.f.a))

    def no_created(self):
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],self.before)

    def test_new_get_revokes_guardian_and_form(self):
        old,_=self.verify();fresh=self.start()
        self.assertNotEqual(old,fresh)
        with self.client.session_transaction() as s:self.assertNotIn('family_enrollment_guardian',s)
        response=self.client.post('/inscription',data=self.values(fresh))
        self.assertEqual(response.status_code,400);self.no_created()

    def test_completed_form_cannot_be_replayed(self):
        token,_=self.verify();cookie=self.client.get_cookie('session').value
        result=self.client.post('/inscription',data=self.values(token))
        self.assertEqual(result.status_code,302)
        created=self.db.execute("SELECT * FROM users WHERE public_id='0042'").fetchone()
        self.assertIsNotNone(created)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM user_family_links WHERE member_id=?',(created['id'],)).fetchone()[0],1)
        self.client.set_cookie('session',cookie)
        self.assertEqual(self.client.post('/inscription',data=self.values(token)).status_code,400)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],self.before+1)

    def test_cancel_revokes_even_old_signed_cookie(self):
        token,_=self.verify();cookie=self.client.get_cookie('session').value
        self.assertEqual(self.client.post('/inscription/annuler',data={'evolution_csrf':token}).status_code,204)
        self.client.set_cookie('session',cookie)
        self.assertEqual(self.client.post('/inscription',data=self.values(token)).status_code,400)
        self.no_created()

    def test_home_revokes_even_old_signed_cookie(self):
        token,_=self.verify();cookie=self.client.get_cookie('session').value
        self.assertEqual(self.client.get('/').status_code,200)
        self.client.set_cookie('session',cookie)
        self.assertEqual(self.client.post('/inscription',data=self.values(token)).status_code,400)
        self.no_created()

    def test_other_html_revokes_form(self):
        token,_=self.verify();self.client.get('/animations')
        self.assertEqual(self.client.post('/inscription',data=self.values(token)).status_code,400)
        self.no_created()

    def test_state_requires_same_document(self):
        token=self.start()
        self.assertFalse(self.client.get('/inscription/etat').json['active'])
        self.assertFalse(self.client.get('/inscription/etat',headers={'X-OpenFabLab-Enrollment':'wrong'}).json['active'])
        response=self.client.get('/inscription/etat',headers={'X-OpenFabLab-Enrollment':token})
        self.assertEqual(response.json,{'active':True});self.assertIn('no-store',response.headers['Cache-Control'])
        self.start()
        self.assertFalse(self.client.get('/inscription/etat',headers={'X-OpenFabLab-Enrollment':token}).json['active'])

    def test_expiry_revokes_guardian(self):
        token,_=self.verify()
        with mock.patch('enrollment_privacy.time.time',return_value=time.time()+901):
            self.assertEqual(self.client.post('/inscription',data=self.values(token)).status_code,400)
        self.no_created()

    def test_invalid_csrf_cannot_cancel_active_form(self):
        token=self.start()
        self.assertEqual(self.client.post('/inscription/annuler',data={'evolution_csrf':'wrong'}).status_code,400)
        self.assertTrue(self.client.get('/inscription/etat',headers={'X-OpenFabLab-Enrollment':token}).json['active'])

    def test_get_cannot_cancel(self):
        token=self.start()
        self.assertEqual(self.client.get('/inscription/annuler').status_code,405)
        self.assertTrue(self.client.get('/inscription/etat',headers={'X-OpenFabLab-Enrollment':token}).json['active'])

    def test_same_form_correction_keeps_guardian_and_custom_code(self):
        token,response=self.verify(first_name='Camille',last_name='EXEMPLE')
        self.assertIn('value="0042"',response.text)
        values=self.values(token);values['first_name']=''
        result=self.client.post('/inscription',data=values)
        self.assertEqual(result.status_code,400);self.assertIn('data-selected-responsible',result.text)
        token=re.search(r'name="evolution_csrf" value="([^"]+)"',result.text)[1]
        self.assertEqual(self.client.post('/inscription',data=self.values(token)).status_code,302)

    def test_disabled_enrollment_cannot_verify_guardian(self):
        token=self.start();write_setting(self.db,'self_enrollment_enabled','0');self.db.commit()
        response=self.client.post('/inscription',data={'evolution_csrf':token,'family_step':'verify','guardian_public_id':'2001','guardian_contact':'person0@example.invalid'})
        self.assertEqual(response.status_code,404);self.assertNotIn('Fictif0',response.text)

    def test_forged_guardian_after_abandon_is_not_accepted(self):
        self.verify();token=self.start()
        self.assertEqual(self.client.post('/inscription',data=self.values(token)).status_code,400)
        self.no_created()

    def test_new_browser_has_no_previous_guardian(self):
        self.verify();other=self.app.test_client();token=self.start(other)
        response=other.post('/inscription',data=self.values(token))
        self.assertEqual(response.status_code,400);self.assertNotIn('data-selected-responsible',response.text)
        self.no_created()

    def test_two_devices_keep_independent_forms(self):
        first=self.start();other=self.app.test_client();second=self.start(other)
        self.client.post('/inscription/annuler',data={'evolution_csrf':first})
        self.assertTrue(other.get('/inscription/etat',headers={'X-OpenFabLab-Enrollment':second}).json['active'])

    def test_registry_contains_no_identity_or_raw_token(self):
        token,_=self.verify()
        with self.client.session_transaction() as s:flow=s['_enrollment_flow']
        rows=self.db.execute("SELECT * FROM family_api_nonces WHERE nonce_hash LIKE 'enrollment:%'").fetchall()
        self.assertEqual(len(rows),1)
        for value in (flow,token,'person0@example.invalid','Fictif0','2001'):
            self.assertNotIn(value,repr([tuple(row) for row in rows]))
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],18)

    def test_static_fetch_does_not_abandon(self):
        token=self.start();self.client.get('/static/public-enrollment.js')
        self.assertTrue(self.client.get('/inscription/etat',headers={'X-OpenFabLab-Enrollment':token}).json['active'])

    def test_failed_guardian_verification_removes_old_grant(self):
        token,_=self.verify()
        response=self.client.post('/inscription',data={'evolution_csrf':token,'family_step':'verify','guardian_public_id':'2001','guardian_contact':'wrong@example.invalid'})
        self.assertEqual(response.status_code,200);self.assertNotIn('data-selected-responsible',response.text)
        token=re.search(r'name="evolution_csrf" value="([^"]+)"',response.text)[1]
        self.assertEqual(self.client.post('/inscription',data=self.values(token)).status_code,400)

    def test_existing_permanent_links_are_preserved_on_cancel(self):
        rows=[tuple(row) for row in self.db.execute('SELECT * FROM user_family_links')]
        token,_=self.verify();self.client.post('/inscription/annuler',data={'evolution_csrf':token})
        self.assertEqual([tuple(row) for row in self.db.execute('SELECT * FROM user_family_links')],rows)

    def test_legacy_unscoped_grant_is_rejected(self):
        token=self.start()
        with self.client.session_transaction() as s:s['family_enrollment_guardian']={'id':self.f.a,'until':time.time()+900}
        self.assertEqual(self.client.post('/inscription',data=self.values(token)).status_code,400);self.no_created()

    def test_creation_transaction_restores_receipt_on_failure(self):
        import sqlite3
        token,_=self.verify()
        with mock.patch('evolution_routes.create_user',side_effect=sqlite3.IntegrityError()):
            result=self.client.post('/inscription',data=self.values(token))
            self.assertEqual(result.status_code,409)
        token=re.search(r'name="evolution_csrf" value="([^"]+)"',result.text)[1]
        self.no_created()
        self.assertTrue(self.client.get('/inscription/etat',headers={'X-OpenFabLab-Enrollment':token}).json['active'])

    def test_public_form_copy_and_order(self):
        _,text=self.verify()
        self.assertNotIn('Inscription sur borne',text.text)
        self.assertIn('Un compte par personne. Les coordonnées requises peuvent être différentes pour un enfant.',text.text)
        self.assertIn('Cet envoi vous permet de recevoir votre identifiant.',text.text)
        self.assertLess(text.text.index('name="public_id"'),text.text.index('name="last_name"'))
        self.assertLess(text.text.index('name="last_name"'),text.text.index('name="first_name"'))
        self.assertNotIn('data-affiliation-choice',text.text)

    def test_no_persistent_browser_personal_storage(self):
        from pathlib import Path
        code=(Path(__file__).resolve().parents[1]/'static/public-enrollment.js').read_text()
        self.assertNotIn('localStorage',code);self.assertNotIn('sessionStorage',code)
        self.assertIn('pagehide',code);self.assertIn('pageshow',code)

    def test_reloaded_post_redirects_to_empty_form(self):
        old=self.start();fresh,_=self.verify(old)
        self.assertNotEqual(old,fresh)
        response=self.client.post('/inscription',data={'evolution_csrf':old,'family_step':'verify','guardian_public_id':'2001','guardian_contact':'person0@example.invalid'},follow_redirects=True)
        self.assertEqual(response.status_code,200)
        self.assertNotIn('data-selected-responsible',response.text)
        self.assertNotIn('value="person0@example.invalid"',response.text)
        self.no_created()

    def test_simultaneous_creation_consumes_authorization_once(self):
        import concurrent.futures,threading
        token,_=self.verify();cookie=self.client.get_cookie('session').value
        barrier=threading.Barrier(2)
        def submit():
            client=self.app.test_client();client.set_cookie('session',cookie)
            barrier.wait()
            return client.post('/inscription',data=self.values(token)).status_code
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:submit(),range(2)))
        self.assertEqual(results.count(302),1)
        self.assertIn(next(status for status in results if status!=302),(400,409))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],self.before+1)

    def test_invalid_csrf_cannot_create_account(self):
        self.start()
        self.assertEqual(self.client.post('/inscription',data=self.values('invalid')).status_code,400)
        self.no_created()

    def test_booking_create_link_follows_public_enrollment_setting(self):
        route=f'/animations/{self.f.service}/famille'
        self.assertIn('href="/inscription"',self.client.get(route).text)
        write_setting(self.db,'self_enrollment_enabled','0');self.db.commit()
        text=self.client.get(route).text
        self.assertNotIn('href="/inscription"',text)
        self.assertIn('Adressez-vous à l’équipe du FabLab.',text)

    def test_team_affiliation_after_family_for_both_roles(self):
        for role in ('admin','moderator'):
            with self.subTest(role=role):
                with self.client.session_transaction() as s:
                    s.clear();s['access_role']=role;s['admin_authenticated']=True
                result=self.client.get('/admin/usagers/nouveau')
                self.assertEqual(result.status_code,200)
                self.assertLess(result.text.index('id="family-title"'),result.text.index('class="affiliation-fields'))
                self.assertIn('name="affiliation_client_id"',result.text)

    def test_display_and_catalogue_copy_preserve_boundaries(self):
        with self.client.session_transaction() as s:s['access_role']='admin';s['admin_authenticated']=True
        text=self.client.get('/admin/reglages/affichage').text
        self.assertIn('min="1" max="10000"',text)
        self.assertIn('Un indicateur visuel de fréquentation, sans limitation des entrées.',text)
        text=self.client.get('/animations').text
        self.assertNotIn('Depuis la borne',text)
        self.assertIn('Liste d’attente activée',text)
