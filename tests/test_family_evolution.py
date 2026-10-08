"""2.8 settings, private relationships, transitions and calendar preservation."""
import re
import unittest
from datetime import date, timedelta
from unittest import mock
from werkzeug.datastructures import MultiDict
from tests import test_families as fixture
import family_model as family
from app import write_setting
from fablab_calendar import set_visibility


class FamilyEvolutionTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.FamilyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db,self.client=self.f.db,self.f.client

    def test_default_rules_link_to_actual_family_settings(self):
        with self.client.session_transaction() as session:
            session['access_role']='admin'
            session['admin_authenticated']=True
        page=self.client.get('/admin/reglages/structure')
        self.assertEqual(page.status_code,200)
        text=page.get_data(as_text=True)
        self.assertIn('href="/admin/reglages/usagers#ages-autonomie-familles"',text)
        self.assertIn('Ces valeurs seront proposées lors de la création',text)
        target=self.client.get('/admin/reglages/usagers')
        self.assertEqual(target.status_code,200)
        self.assertIn('id="ages-autonomie-familles"',target.get_data(as_text=True))

    def test_final_typography_preserves_page_hierarchy(self):
        from pathlib import Path
        css=(Path(__file__).resolve().parents[1]/'static/style.css').read_text()
        self.assertIn('--control-font: 400 1rem/1.45 var(--ui-font)',css)
        self.assertIn('--module-title-weight: 500',css)
        self.assertNotIn('max-width:110px;font-size:1.4rem;font-weight:700',css)
        self.assertIn('font-size: clamp(2rem, 5vw, 3.4rem)',css)

    def test_new_minor_exact_birth_and_responsible_required(self):
        data=dict(first_name='Enfant',last_name='FICTIF',active=1,birth_year=self.f.today.year-10,email='',phone='')
        errors=[]
        family.validate_form(self.db,MultiDict({'is_minor':'1'}),data,errors)
        self.assertTrue(errors)
        errors=[]
        form=MultiDict([('is_minor','1'),('birth_date',date(self.f.today.year-10,1,1).isoformat()),('responsible_ids',str(self.f.a)),('responsible_ids',str(self.f.b))])
        family.validate_form(self.db,form,data,errors)
        self.assertEqual(errors,[]);self.assertEqual(data['responsible_ids'],[self.f.a,self.f.b])
        self.assertEqual(data['birth_precision'],'exact')

    def test_historical_missing_contact_link_warns_without_forced_rewrite(self):
        self.db.execute('UPDATE users SET birth_year=?,birth_date=NULL,email=NULL,phone=NULL WHERE id=?',(self.f.today.year-10,self.f.other));self.db.commit()
        user=dict(self.db.execute('SELECT * FROM users WHERE id=?',(self.f.other,)).fetchone());errors=[]
        family.validate_form(self.db,MultiDict(),user,errors,current_id=self.f.other)
        self.assertEqual(errors,[]);self.assertIsNone(user['birth_date'])
        self.f.f.login_admin();page=self.client.get('/admin/usagers/'+str(self.f.other)+'/modifier').get_data(as_text=True)
        self.assertIn('Responsable à renseigner',page)

    def test_bad_settings_do_not_produce_policy(self):
        for changes in ({'family_autonomy_age':'19','family_responsible_age':'18'}, {'family_autonomy_age':'-1'}, {'family_responsible_age':'121'}, {'family_contact_dependent':'invalid'}):
            with self.assertRaises(ValueError): family.validate_settings(changes)
        result=family.validate_settings({'family_autonomy_age':'12','family_responsible_age':'20'})
        self.assertEqual((result['family_autonomy_age'],result['family_responsible_age']),('12','20'))

    def test_relationships_survive_age_threshold_and_manual_unlink(self):
        self.db.execute('UPDATE users SET birth_date=?,birth_year=? WHERE id=?',(date(self.f.today.year-20,1,1).isoformat(),self.f.today.year-20,self.f.c));self.db.commit()
        self.assertEqual(family.state(self.db,self.db.execute('SELECT * FROM users WHERE id=?',(self.f.c,)).fetchone()),'responsible')
        links=family.responsibles(self.db,self.f.c);self.assertEqual(len(links),2)
        with self.db: family.end_link(self.db,links[0]['link_uuid'],self.f.c)
        self.assertEqual(len(family.responsibles(self.db,self.f.c)),1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],self.f.initial_users+7)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM user_family_links WHERE ended_at IS NOT NULL').fetchone()[0],1)

    def test_birthday_notification_once_without_contacts_and_no_sensitive_payload(self):
        born=date(self.f.today.year-18,self.f.today.month,self.f.today.day)
        self.db.execute('UPDATE users SET birth_date=?,birth_year=?,email=NULL,phone=NULL WHERE id=?',(born.isoformat(),born.year,self.f.older))
        self.db.execute('INSERT OR REPLACE INTO family_age_observations(user_id,was_responsible) VALUES(?,0)',(self.f.older,));self.db.commit()
        sent=[]
        family.observe_ages(self.db,self.f.today,sent.append)
        family.observe_ages(self.db,self.f.today,sent.append)
        family.observe_ages(self.db,self.f.today+timedelta(days=1),sent.append)
        self.assertEqual(len(sent),1);self.assertIn('e-mail, téléphone',sent[0]);self.assertNotIn('person5@',sent[0])
        self.assertEqual(self.db.execute('SELECT active FROM users WHERE id=?',(self.f.older,)).fetchone()[0],1)

    def test_uncertain_notification_not_sent_twice(self):
        self.db.execute('UPDATE users SET email=NULL,phone=NULL WHERE id=?',(self.f.other,))
        self.db.execute('INSERT OR REPLACE INTO family_age_observations(user_id,was_responsible) VALUES(?,0)',(self.f.other,));self.db.commit()
        callback=mock.Mock(side_effect=OSError('fictional offline'))
        family.observe_ages(self.db,self.f.today,callback);family.observe_ages(self.db,self.f.today+timedelta(days=1),callback)
        self.assertEqual(callback.call_count,1)

    def test_enrollment_guardian_rate_limit_survives_new_cookies(self):
        write_setting(self.db,'self_enrollment_enabled','1');self.db.commit()
        for attempt in range(6):
            client=self.f.f.app.test_client();page=client.get('/inscription').get_data(as_text=True)
            token=re.search(r'name="evolution_csrf" value="([^"]+)"',page).group(1)
            response=client.post('/inscription',data=dict(evolution_csrf=token,family_step='verify',guardian_public_id='2001',guardian_contact='wrong@example.invalid'))
            self.assertEqual(response.status_code,429 if attempt==5 else 200)
            if attempt<5: self.assertNotIn('Fictif2',response.get_data(as_text=True))

    def test_visibility_changes_no_business_rows(self):
        before=tuple(self.db.execute('SELECT * FROM fablab_services WHERE id=?',(self.f.service,)).fetchone())
        with self.db: set_visibility(self.db,'animation',str(self.f.service),self.f.day,True)
        self.assertEqual(tuple(self.db.execute('SELECT * FROM fablab_services WHERE id=?',(self.f.service,)).fetchone()),before)
        with self.db: set_visibility(self.db,'animation',str(self.f.service),self.f.day,False)
        self.assertEqual(self.db.execute('SELECT hidden FROM calendar_visibility').fetchone()[0],0)
        with self.assertRaises(ValueError): set_visibility(self.db,'animation','not-an-event',self.f.day,True)

    def test_custom_home_title_and_calendar_color_persist_in_settings(self):
        self.f.f.login_admin()
        write_setting(self.db,'home_title','Bienvenue au lieu Exemple');write_setting(self.db,'calendar_color_animation','#123456');self.db.commit()
        self.assertIn('Bienvenue au lieu Exemple',self.client.get('/').get_data(as_text=True))
        page=self.client.get('/admin/calendrier?date='+self.f.day).get_data(as_text=True)
        self.assertIn('#123456',page)

    def test_home_footer_only_shows_management_without_changing_its_destination(self):
        for role in (None,'admin','moderator'):
            with self.subTest(role=role):
                with self.client.session_transaction() as session:
                    session.clear()
                    if role:
                        session['access_role']=role
                        session['admin_authenticated']=True
                response=self.client.get('/')
                self.assertEqual(response.status_code,200)
                footer=re.search(r'<footer class="site-footer">(.*?)</footer>',response.get_data(as_text=True),re.S).group(1)
                self.assertEqual(re.findall(r'<a href="([^"]+)">([^<]+)</a>',footer),[('/admin','Gestion')])
                self.assertIn('2.8.3',footer)
                self.assertNotIn('Gestion des données',footer)
                with self.client.session_transaction() as session:
                    self.assertEqual(session.get('access_role'),role)

    def test_internal_footers_keep_data_management_and_protected_administration(self):
        write_setting(self.db,'self_enrollment_enabled','1');self.db.commit()
        for route in ('/admin/connexion','/identification','/usagers','/inscription','/animations','/gestion-des-donnees'):
            with self.subTest(route=route):
                response=self.client.get(route)
                self.assertEqual(response.status_code,200)
                page=response.get_data(as_text=True)
                footer=re.search(r'<footer class="site-footer">(.*?)</footer>',page,re.S).group(1)
                self.assertEqual(re.findall(r'<a href="([^"]+)">([^<]+)</a>',footer),[('/gestion-des-donnees','Gestion des données'),('/admin','Administration')])
                if route=='/admin/connexion':
                    self.assertIn('<h1 id="login-title">Administration</h1>',page)
                    self.assertIn('Administrateur',page);self.assertIn('Modérateur',page)
                    self.assertIn('name="pin" type="password"',page)
        self.f.f.login_admin()
        page=self.client.get('/admin/calendrier').get_data(as_text=True)
        footer=re.search(r'<footer class="site-footer">(.*?)</footer>',page,re.S).group(1)
        self.assertIn('Gestion des données',footer);self.assertIn('>Administration</a>',footer)

    def test_profile_links_private_and_public_catalogue_has_no_family(self):
        self.f.f.login_admin();page=self.client.get('/admin/usagers/'+str(self.f.c)+'/modifier').get_data(as_text=True)
        self.assertIn('/admin/usagers/'+str(self.f.a),page)
        self.client.post('/admin/deconnexion')
        public=self.client.get('/animations').get_data(as_text=True)
        for name in ('Fictif0','Fictif2','person0@example.invalid'): self.assertNotIn(name,public)

    def test_exact_birthday_is_used_in_profile_display_not_reference_year(self):
        born=date(2011,10,6)
        self.db.execute('UPDATE users SET birth_date=?,birth_year=? WHERE id=?',(born.isoformat(),born.year,self.f.c));self.db.commit()
        self.f.f.login_admin()
        with mock.patch('family_model.local_day',return_value=date(2026,10,5)):
            page=self.client.get('/admin/usagers/'+str(self.f.c)+'/modifier').get_data(as_text=True)
        self.assertIn('Âge actuel',page);self.assertIn('14 ans',page)
        self.assertNotIn('Âge atteint dans l’année, calculé',page)

    def test_current_public_and_settings_copy_does_not_advertise_legacy_model(self):
        public=self.client.get('/animations/'+str(self.f.service)).get_data(as_text=True)
        self.assertIn('Avant 15 ans, un responsable rattaché',public)
        self.assertNotIn('accompagnateur majeur',public)
        self.assertNotIn('dernière synchronisation',public)
        self.f.f.login_admin()
        page=self.client.get('/admin/reglages/structure').get_data(as_text=True)
        self.assertIn('sans ouvrir d’accès public au NAS',page)
        self.assertIn('Réglages historiques conservés',page)
        self.assertNotIn('joignable depuis WordPress',page)

    def test_empty_past_openlab_returns_with_presence_unless_manually_hidden(self):
        day=self.f.today-timedelta(days=14+self.f.today.weekday())
        for key in ('monday','tuesday','wednesday','thursday','friday','saturday','sunday'):
            for edge in ('start','end'): write_setting(self.db,'openlab_attendance_'+key+'_'+edge,'')
        write_setting(self.db,'openlab_attendance_monday_start','09:00');write_setting(self.db,'openlab_attendance_monday_end','12:00');self.db.commit()
        self.f.f.login_admin();route='/admin/calendrier?date='+day.isoformat()
        self.assertNotIn('data-kind="openlab"',self.client.get(route).get_data(as_text=True))
        self.assertIn('Non tenu automatiquement',self.client.get(route+'&hidden=1').get_data(as_text=True))
        self.db.execute("INSERT INTO sessions(user_id,check_in,check_out,statistical_category,statistical_user_key) VALUES(?,?,?,'user','fictional-calendar-user')",(self.f.a,day.isoformat()+'T09:15:00+00:00',day.isoformat()+'T09:45:00+00:00'));self.db.commit()
        self.assertIn('data-kind="openlab"',self.client.get(route).get_data(as_text=True))
        with self.db: set_visibility(self.db,'openlab',day.isoformat(),day.isoformat(),True)
        self.assertNotIn('data-kind="openlab"',self.client.get(route).get_data(as_text=True))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],1)

    def test_resource_popup_price_and_authorization_private(self):
        import resource_booking as resources
        now=family.timestamp();key='fictional-family-training'
        self.db.execute('INSERT INTO authorizations VALUES(?,?,?,?,?)',(key,'Formation fictive','Description fictive',1,now))
        resources.grant(self.db,self.f.a,key,self.f.today.isoformat(),'Équipe Exemple','admin')
        resource=resources.save_resource(self.db,dict(name='Machine fictive',type_key='machine',active=True,price_cents=1250,required_authorization=key),'admin')
        resources.book(self.db,resource,self.f.a,self.f.day+'T10:00:00+02:00',self.f.day+'T11:00:00+02:00','admin');self.db.commit()
        self.f.f.login_admin();page=self.client.get('/admin/calendrier?date='+self.f.day).get_data(as_text=True)
        self.assertIn('12,50 €',page);self.assertIn('Habilitation valable au créneau',page)
        self.assertNotIn('person0@example.invalid',page)
