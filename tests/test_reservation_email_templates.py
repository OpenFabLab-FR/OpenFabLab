"""Editable native reservation mail; no real mail or private link is sent."""
import json
import re
import unittest
from tests import test_family_waitlist as fixtures
import reservation_email_templates as templates
from profile_archive import build_profile,parse_profile
from app import write_setting


class ReservationEmailTemplateTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.WaitlistTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db,self.client=self.f.db,self.f.client
        value=self.f.book([self.f.f.a])
        self.row=dict(self.db.execute('SELECT * FROM family_booking_emails WHERE group_uuid=?',(value['group_uuid'],)).fetchone())
        self.payload=json.loads(self.row['payload_json'])
        self.url='https://example.invalid/personal-fictitious-link'

    def test_all_defaults_have_one_management_url_and_html_button(self):
        for kind in templates.INTRO:
            with self.subTest(kind=kind):
                payload=dict(self.payload,event=kind,expires='2026-11-10T12:00:00+00:00')
                row=dict(self.row,kind=kind,payload_json=json.dumps(payload))
                message=templates.build_message(self.f.config,row,'https://example.invalid',self.url,self.db)
                plain=message.get_body(preferencelist=('plain',)).get_content()
                html=message.get_body(preferencelist=('html',)).get_content()
                self.assertEqual(plain.count(self.url),1)
                self.assertEqual(html.count(self.url),1)
                self.assertIn('Gérer ma réservation',html)
                self.assertNotIn('Voir la demande',html)
                self.assertNotIn(self.url+ '<br>',html)
                self.assertIn('Fictif0 EXEMPLE',plain)
                self.assertNotIn('En savoir plus',html)

    def test_custom_subject_body_and_default_restore(self):
        with self.db:
            write_setting(self.db,templates.key('confirmed','subject'),'Votre atelier : {animation}')
            write_setting(self.db,templates.key('confirmed','body'),'Bonjour\n{participants}\n{places} personnes\n{lien_reservation}')
        message=templates.build_message(self.f.config,self.row,'https://example.invalid',self.url,self.db)
        self.assertIn('Votre atelier',str(message['Subject']))
        self.assertIn('1 personnes',message.get_body(preferencelist=('plain',)).get_content())
        with self.db:
            self.db.execute('DELETE FROM app_settings WHERE key IN (?,?)',(templates.key('confirmed','subject'),templates.key('confirmed','body')))
        self.assertEqual(templates.load(self.db,'confirmed'),templates.default('confirmed'))

    def test_dynamic_values_and_authored_html_are_escaped(self):
        payload=dict(self.payload,title='<script>alert(1)</script>',participants=['<b>Camille</b>'])
        template=dict(subject='Atelier {animation}',body='<img src=x onerror=alert(1)>\n{participants}\n{lien_reservation}')
        _,_,html=templates.render(payload,'confirmed',template,self.url)
        self.assertNotIn('<script>',html);self.assertNotIn('<img',html);self.assertNotIn('<b>Camille',html)
        self.assertIn('&lt;img',html)

    def test_invalid_variables_and_formats_are_rejected(self):
        for value in ('{secret}','{animation.__class__}','{places:04}','{animation!r}','{','{lien_reservation}\n{lien_reservation}'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                templates.validate(value,'body')

    def test_header_injection_and_limits_are_rejected(self):
        for value in ('Bonjour\nBcc: other@example.invalid','x'*201,'{participants}'):
            with self.assertRaises(ValueError):templates.validate(value,'subject')
        with self.assertRaises(ValueError):templates.validate('x'*8001,'body')
    def test_browser_crlf_normalized_but_subject_and_lone_cr_refused(self):
        self.assertEqual(templates.validate('Bonjour\r\n{participants}\r\n{lien_reservation}','body'),'Bonjour\n{participants}\n{lien_reservation}')
        for value,field in [('Bonjour\rAutre','body'),('Bonjour\r\nBcc: autre@example.invalid','subject')]:
            with self.assertRaises(ValueError):templates.validate(value,field)

    def test_missing_link_variable_gets_exactly_one_secure_footer(self):
        _,plain,html=templates.render(self.payload,'confirmed',dict(subject='Réservation',body='Votre réservation est confirmée.'),self.url)
        self.assertEqual(plain.count(self.url),1);self.assertEqual(html.count(self.url),1)

    def test_optional_information_link_no_empty_or_unsafe_link(self):
        for info in ('','javascript:alert(1)','https://example.invalid/programme'):
            payload=dict(self.payload,information_url=info)
            _,plain,html=templates.render(payload,'confirmed',templates.default('confirmed'),self.url)
            if info.startswith('https'):
                self.assertIn('En savoir plus sur cette animation',html)
                self.assertEqual(plain.count(info),1)
            else:
                self.assertNotIn('En savoir plus',html);self.assertNotIn('javascript:',plain)

    def test_french_date_and_local_offer_deadline(self):
        payload=dict(self.payload,date='2026-10-25',expires='2026-10-25T12:05:00+00:00',timezone='Europe/Paris')
        _,body,_=templates.render(payload,'offer_pending',templates.default('offer_pending'),self.url)
        self.assertIn('25 octobre 2026',body);self.assertIn('13h05',body)

    def test_profiles_preserve_templates_without_smtp_secrets(self):
        key=templates.key('confirmed','subject')
        profile=parse_profile(build_profile({key:'Mon atelier {animation}','smtp_password':'not-a-real-secret'},[],{}))
        self.assertEqual(profile['settings'][key],'Mon atelier {animation}')
        self.assertNotIn('smtp_password',profile['settings'])

    def test_admin_editor_preview_save_reset_and_csrf(self):
        self.f.f.f.login_admin()
        path='/admin/reglages/structure/emails-reservation'
        page=self.client.get(path)
        self.assertEqual(page.status_code,200);self.assertIn('Aperçu fictif',page.text)
        token=re.search(r'name="evolution_csrf" value="([^"]+)"',page.text)[1]
        self.assertEqual(self.client.post(path,data={'kind':'confirmed','action':'save'}).status_code,400)
        data=dict(evolution_csrf=token,kind='confirmed',subject='Atelier {animation}',body='Bonjour {participants}',action='preview')
        self.assertEqual(self.client.post(path,data=data).status_code,200)
        self.assertIsNone(self.db.execute('SELECT value FROM app_settings WHERE key=?',(templates.key('confirmed','subject'),)).fetchone())
        data['action']='save';self.assertEqual(self.client.post(path,data=data).status_code,302)
        self.assertEqual(templates.load(self.db,'confirmed')['subject'],'Atelier {animation}')
        data['action']='reset';self.assertEqual(self.client.post(path,data=data).status_code,302)
        self.assertEqual(templates.load(self.db,'confirmed'),templates.default('confirmed'))

    def test_public_and_moderator_cannot_edit(self):
        with self.client.session_transaction() as session:session.clear()
        self.assertNotEqual(self.client.get('/admin/reglages/structure/emails-reservation').status_code,200)
        with self.client.session_transaction() as session:session['access_role']='moderator';session['admin_authenticated']=True
        self.assertNotEqual(self.client.get('/admin/reglages/structure/emails-reservation').status_code,200)

    def test_invalid_imported_template_falls_back_without_losing_mail(self):
        with self.db:write_setting(self.db,templates.key('confirmed','body'),'{forbidden}')
        message=templates.build_message(self.f.config,self.row,'https://example.invalid',self.url,self.db)
        self.assertIn('Votre inscription',message.get_body(preferencelist=('plain',)).get_content())
