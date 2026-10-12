"""Fictional people, bounded staff search, information URLs and aggregate exports."""
import csv
import io
import json
import re
import secrets
import unittest
from datetime import timedelta
from tests import test_family_waitlist as fixtures
from animation_information import validate_url,metrics
from participant_search import search_users
import family_waitlist as waiting
import outbound_actions as actions
from app import write_setting


class Corrective285Tests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.WaitlistTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db,self.client,self.service=self.f.db,self.f.client,self.f.service

    def test_safe_optional_public_urls_without_fetch(self):
        for value in ('','https://example.invalid/programme','http://example.org/page?utm_source=calendar'):
            self.assertEqual(validate_url(value),value)
        import ipaddress
        private_ip='https://'+str(ipaddress.ip_address(3232235780))
        for value in ('javascript:alert(1)','file:///etc/passwd','https://localhost/admin',private_ip,'http://127.0.0.1','http://[::1]','https://user:password@example.org','https://example.org/?token=private'):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_url(value)

    def test_search_partial_accent_case_id_and_limit(self):
        with self.db:
            self.db.execute("UPDATE users SET first_name='Élodie',last_name='Exemple-Aumont',public_id='0042' WHERE id=?",(self.f.f.a,))
        for value in ('elo','ELO','AUM','0042'):
            self.assertIn(self.f.f.a,{p['id'] for p in search_users(self.db,value)['users']})
        self.assertEqual(search_users(self.db,'nothing-found')['users'],[])
        self.assertLessEqual(len(search_users(self.db,'')['users']),25)
        self.assertEqual(search_users(self.db,'%')['users'],[])

    def test_search_never_exposes_contacts_or_inactive_users(self):
        with self.db:self.db.execute('UPDATE users SET active=0 WHERE id=?',(self.f.f.a,))
        rows=search_users(self.db,'')['users']
        self.assertNotIn(self.f.f.a,{r['id'] for r in rows})
        self.assertTrue(all(set(r)=={'id','public_id','first_name','last_name'} for r in rows))

    def test_search_auth_admin_and_moderator(self):
        path='/admin/api/participants?q=fictif'
        self.assertNotEqual(self.client.get(path).status_code,200)
        self.f.f.f.login_admin();self.assertEqual(self.client.get(path).status_code,200)
        with self.client.session_transaction() as session:session['access_role']='moderator';session['admin_authenticated']=True
        response=self.client.get(path);self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Cache-Control'],'private, no-store')

    def test_personal_link_get_then_cancel_confirmation(self):
        booking=self.f.book([self.f.f.a,self.f.f.c])
        token=self.f.meta(booking)['manage_token'];path='/animations/demande/'+token
        page=self.client.get(path)
        self.assertIn('Gérer ma réservation',page.text)
        self.assertNotIn('Je confirme vouloir annuler',page.text)
        self.assertEqual(self.f.status(booking),'confirmed')
        csrf=re.search(r'name="evolution_csrf" value="([^"]+)"',page.text)[1]
        page=self.client.post(path,data=dict(action='prepare_cancel',evolution_csrf=csrf))
        self.assertIn('pour 2 personnes',page.text);self.assertEqual(self.f.status(booking),'confirmed')
        self.client.post(path,data=dict(action='cancel',evolution_csrf=csrf))
        self.assertEqual(self.f.status(booking),'confirmed')
        page=self.client.post(path,data=dict(action='cancel',consent='1',evolution_csrf=csrf),follow_redirects=True)
        self.assertIn('Votre réservation est annulée.',page.text)
        self.assertEqual(self.f.status(booking),'cancelled')

    def test_relay_personal_view_has_only_authorized_details(self):
        booking=self.f.book([self.f.f.a,self.f.f.c])
        token=self.f.meta(booking)['manage_token'];secret=b'f'*64
        link=actions.issue_link(secret,token,'production')
        view=actions.dispatch(self.db,dict(environment='production',link=link),'view','production',secret,'fictional-request')
        self.assertEqual(view['count'],2)
        self.assertEqual(set(view['participants']),{'Fictif0 EXEMPLE','Fictif2 EXEMPLE'})
        self.assertNotIn('person0@example.invalid',json.dumps(view))
        self.assertNotIn('Fictif1',json.dumps(view))

    def test_catalogue_optional_information_requires_negotiation(self):
        with self.db:self.db.execute('UPDATE fablab_services SET information_url=? WHERE id=?',('https://example.invalid/programme',self.service))
        old=actions.public_catalogue(self.db,'production')[0]
        new=actions.public_catalogue(self.db,'production',include_information=True)[0]
        self.assertNotIn('information_url',old)
        self.assertEqual(new['information_url'],'https://example.invalid/programme')
        self.assertEqual({k:v for k,v in new.items() if k!='information_url'},old)

    def test_capacity_metrics_distinguish_confirmed_waiting_and_presence(self):
        self.f.book([self.f.f.a,self.f.f.c]);self.f.book([self.f.f.teen]);self.f.book([self.f.f.other])
        self.f.book([self.f.f.b])
        value=metrics(self.db,self.service)
        self.assertEqual((value['capacity'],value['confirmed_count'],value['remaining_count'],value['present_count'],value['waitlisted_count']),(4,4,0,0,1))

    def test_ics_uses_real_aggregates_information_url_and_stable_uid(self):
        self.f.book([self.f.f.a,self.f.f.c]);self.f.f.f.login_admin()
        with self.db:self.db.execute('UPDATE fablab_services SET information_url=? WHERE id=?',('https://example.invalid/programme',self.service))
        response=self.client.get('/admin/animations/'+str(self.service)+'/calendrier.ics')
        text=response.data.decode().replace('\r\n ','')
        for value in ('Capacité : 4 places','Inscriptions confirmées : 2','Places restantes : 2','Participants présents : 0','URL:https://example.invalid/programme'):
            self.assertIn(value,text)
        self.assertNotIn('Fictif0',text);self.assertNotIn('person0@',text)

    def test_volunteer_csv_closed_durations_only_and_column_position(self):
        self.f.f.f.login_admin();person=self.f.f.a
        with self.db:
            self.db.execute("UPDATE users SET category='volunteer' WHERE id=?",(person,))
            for offset,minutes,entry,exit in ((0,90,'qr','manual'),(2,65,'manual','automatic'),(4,600,'id','manual')):
                start=self.f.now-timedelta(days=10,hours=offset+12)
                self.db.execute('INSERT INTO sessions(user_id,check_in,check_out,entry_method,exit_method) VALUES(?,?,?,?,?)',(person,start.isoformat(),(start+timedelta(minutes=minutes)).isoformat(),entry,exit))
            self.db.execute("INSERT INTO sessions(user_id,check_in,entry_method) VALUES(?,?,'qr')",(person,self.f.now.isoformat()))
        rows=list(csv.reader(io.StringIO(self.client.get('/admin/exports/benevoles.csv').data.decode('utf-8-sig')),delimiter=';'))
        index=rows[0].index('Durée cumulée au FabLab')
        self.assertEqual(rows[0][index+1],'Nombre de visites')
        row=next(row for row in rows[1:] if row[0]=='2001')
        self.assertEqual(row[index],'12 h 35 min');self.assertEqual(row[index+1],'4')
        generic=self.client.get('/admin/exports/usagers.csv').data.decode('utf-8-sig')
        self.assertNotIn('Durée cumulée au FabLab',generic)

    def test_existing_cadence_values_survive_initialization(self):
        with self.db:
            write_setting(self.db,'reservation_action_interval_seconds','15')
            write_setting(self.db,'reservation_sync_interval_minutes','1.5')
        import family_model
        family_model.migrate(self.db)
        self.assertEqual(self.db.execute("SELECT value FROM app_settings WHERE key='reservation_action_interval_seconds'").fetchone()[0],'15')
        self.assertEqual(self.db.execute("SELECT value FROM app_settings WHERE key='reservation_sync_interval_minutes'").fetchone()[0],'1.5')

    def test_new_install_defaults_are_ten_and_sixty_seconds(self):
        self.assertEqual(self.db.execute("SELECT value FROM app_settings WHERE key='reservation_action_interval_seconds'").fetchone()[0],'10')
        self.assertEqual(self.db.execute("SELECT value FROM app_settings WHERE key='reservation_sync_interval_minutes'").fetchone()[0],'1')
