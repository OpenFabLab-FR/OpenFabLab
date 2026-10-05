"""Current kiosk contract; obsolete companion UI tests are replaced by family tests.
Historical receipts and cancellations remain covered on the candidate schema.
"""
import json
import re
import secrets
import time
import unittest
from unittest import mock
from tests import test_families as family_fixtures
from app import write_setting
import tablet_reservations as tablet

class TabletTests(unittest.TestCase):
    def setUp(self):
        self.family=family_fixtures.FamilyTests();self.family.setUp();self.addCleanup(self.family.doCleanups)
        self.f=self.family.f;self.db=self.family.db;self.client=self.family.client;self.service=self.family.service

    def legacy(self,state='pending',companion=False):
        key=secrets.token_urlsafe(24)
        data=dict(service_id=self.service,environment='production',first_name='Fictif',last_name='EXEMPLE',birth_year=1990,email='fictif@example.invalid',phone='0600000000')
        if companion:data['companion']=dict(first_name='Autre',last_name='EXEMPLE',birth_year=1985,email='autre@example.invalid',phone='0600000000')
        payload=dict(state=state,request=data,title='Atelier fictif',date=self.family.day,hours='10:00–12:00')
        self.db.execute("INSERT INTO reservation_outbox(environment,command_type,entity_key,payload_json,created_at) VALUES('production','public_request',?,?,?)",(key,json.dumps(payload),tablet.timestamp()));self.db.commit()
        return key

    def test_disabled_option_blocks_all_kiosk_routes(self):
        write_setting(self.db,'tablet_reservations_enabled','0');self.db.commit()
        for route in ('/animations',f'/animations/{self.service}',f'/animations/{self.service}/reserver',f'/animations/{self.service}/famille'):
            self.assertEqual(self.client.get(route).status_code,404)

    def test_home_footer_removed_quick_access_present_on_login(self):
        self.assertNotIn('Réserver une animation',self.client.get('/').get_data(as_text=True))
        self.assertIn('Réserver une animation',self.client.get('/admin/connexion').get_data(as_text=True))
        write_setting(self.db,'tablet_reservations_enabled','0');self.db.commit()
        self.assertNotIn('Réserver une animation',self.client.get('/admin/connexion').get_data(as_text=True))

    def test_catalogue_does_not_expose_family_or_contacts(self):
        page=self.client.get('/animations');text=page.get_data(as_text=True)
        self.assertEqual(page.status_code,200);self.assertIn('Atelier fictif',text)
        self.assertNotIn('Fictif2',text);self.assertNotIn('person0@example.invalid',text)
        self.assertEqual(page.headers['Cache-Control'],'private, no-store')

    def test_old_reserve_route_redirects_to_new_flow_without_creating_rows(self):
        for method in ('get','post'):
            response=getattr(self.client,method)(f'/animations/{self.service}/reserver')
            self.assertEqual(response.status_code,303);self.assertTrue(response.location.endswith('/famille'))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],0)

    def test_public_path_locks_both_team_roles(self):
        for role in ('admin','moderator'):
            with self.client.session_transaction() as s:s.update(access_role=role,admin_authenticated=True)
            self.client.get(f'/animations/{self.service}/famille')
            with self.client.session_transaction() as s:self.assertNotIn('access_role',s);self.assertNotIn('admin_authenticated',s)
            self.assertEqual(self.client.get('/admin/usagers').status_code,302)

    def test_closed_past_disabled_or_test_events_are_not_public(self):
        for field,value in [('enabled',0),('environment','test')]:
            self.db.execute('UPDATE animation_reservation_config SET '+field+'=?',(value,));self.db.commit()
            self.assertNotIn('Atelier fictif',self.client.get('/animations').get_data(as_text=True))
            self.db.execute("UPDATE animation_reservation_config SET enabled=1,environment='production'");self.db.commit()
        self.db.execute("UPDATE fablab_services SET service_date='2000-01-01'");self.db.commit()
        self.assertNotIn('Atelier fictif',self.client.get('/animations').get_data(as_text=True))

    def test_legacy_companion_request_is_still_readable_without_migration(self):
        self.legacy(companion=True)
        rows=tablet.requests_for(self.db,self.service)
        self.assertEqual(rows[0]['payload']['request']['companion']['first_name'],'Autre')
        self.f.login_admin()
        page=self.client.get(f'/admin/animations/{self.service}/inscriptions')
        self.assertEqual(page.status_code,200);self.assertIn('Demandes depuis la borne',page.get_data(as_text=True))

    def test_legacy_receipt_remains_private_and_expiring(self):
        key=self.legacy()
        with self.client.session_transaction() as s:s['tablet_receipt']=dict(key=key,until=time.time()+600)
        page=self.client.get('/animations/demande')
        self.assertEqual(page.status_code,200);self.assertNotIn('fictif@example.invalid',page.get_data(as_text=True))
        self.assertEqual(page.headers['Cache-Control'],'private, no-store')
        with self.client.session_transaction() as s:s['tablet_receipt']['until']=0;s.modified=True
        self.assertEqual(self.client.get('/animations/demande').status_code,404)

    def test_team_can_cancel_legacy_pending_but_not_uncertain(self):
        self.f.login_admin('8642')
        key=self.legacy()
        page=self.client.get(f'/admin/animations/{self.service}/inscriptions')
        token=re.search(r'name="evolution_csrf" value="([^"]+)"',page.get_data(as_text=True))[1]
        route=f'/admin/animations/{self.service}/demandes/{key}/annuler'
        self.assertEqual(self.client.post(route,data={'evolution_csrf':'forged'}).status_code,400)
        self.assertEqual(self.client.post(route,data={'evolution_csrf':token}).status_code,302)
        self.assertEqual(tablet.requests_for(self.db)[0]['payload']['state'],'cancelled')
        key=self.legacy('uncertain')
        self.assertEqual(self.client.post(f'/admin/animations/{self.service}/demandes/{key}/annuler',data={'evolution_csrf':token}).status_code,409)

    def test_schema15_does_not_send_historical_pending_requests(self):
        self.legacy(companion=True);transport=mock.Mock()
        with mock.patch('runtime_policy.external_allowed',return_value=True):
            tablet.process_requests(self.db,transport,'production')
        transport.post.assert_not_called()
        self.assertEqual(tablet.requests_for(self.db)[0]['payload']['state'],'pending')
