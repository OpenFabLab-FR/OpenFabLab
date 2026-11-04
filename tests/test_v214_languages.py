"""Browser language is isolated; native literals only, no translation of data."""
from tests.test_v214_core import NewVersion
from app import write_setting
from i18n import preprocess_html
from i18n import NativeText,t

class Languages(NewVersion):
    def test_admin_language_and_browser_independence(self):
        token=self.login();r=self.client.post('/langue',data=dict(evolution_csrf=token,scope='admin',language='en',next='/admin/maintenance'),follow_redirects=True)
        self.assertEqual(r.status_code,200);self.assertIn(b'lang="en"',r.data)
        self.assertIn(b'lang="fr"',self.client.get('/').data)
        other=self.f.f.app.test_client();self.assertIn(b'lang="fr"',other.get('/').data)
    def test_custom_machine_name_is_not_translated(self):
        self.db.execute('UPDATE resources SET name=? WHERE resource_uuid=?',('Enregistrer',self.key));self.db.commit()
        token=self.login();r=self.client.post('/langue',data=dict(evolution_csrf=token,scope='admin',language='en',next='/admin/maintenance'),follow_redirects=True)
        self.assertIn(b'<strong>Enregistrer</strong>',r.data)
    def test_language_does_not_open_admin_rights(self):
        token=self.login('moderator')
        r=self.client.post('/langue',data=dict(evolution_csrf=token,scope='admin',language='en',next='/admin/maintenance'))
        self.assertEqual(r.status_code,302)
        self.assertNotEqual(self.client.get('/admin/reglages/structure').status_code,200)
    def test_idle_clears_public_language_not_admin_preference(self):
        token=self.login()
        with self.client.session_transaction() as s:s['admin_language']='en';s['kiosk_language_selected']='en';s['enrollment_receipt']='FAKE'
        r=self.client.post('/langue/repos',data=dict(evolution_csrf=token));self.assertEqual(r.status_code,302)
        with self.client.session_transaction() as s:
            self.assertEqual(s['admin_language'],'en');self.assertNotIn('kiosk_language_selected',s);self.assertNotIn('enrollment_receipt',s)
    def test_native_template_not_javascript_or_business_data(self):
        source='<h1>Enregistrer</h1><input value="Enregistrer" placeholder="Nom"><script>const x="Enregistrer";</script>{{ machine.name }}'
        result=preprocess_html(source)
        self.assertIn('{{ _("Enregistrer") }}',result)
        self.assertIn('value="Enregistrer"',result)
        self.assertIn('const x="Enregistrer";',result)
        self.assertIn('{{ machine.name }}',result)
    def test_calendar_fragment_attributes_not_escaped(self):
        self.login();r=self.client.get('/admin/calendrier?date='+self.f.day)
        self.assertEqual(r.status_code,200);self.assertIn(b'data-calendar-detail data-title="',r.data)
        self.assertNotIn(b'data-title=&#34;',r.data)
    def test_visible_literals_translated_business_values_unchanged(self):
        self.login()
        from flask import render_template_string,g
        with self.f.f.app.test_request_context('/'):
            self.f.f.app.preprocess_request()
            g.ui_language='en'
            body=render_template_string('<option value="{{ \'Présent\' }}">{{ \'Présent\' }}</option><span>{{ name }}</span>',name='Enregistrer')
            self.assertEqual(body,'<option value="Présent">Present</option><span>Enregistrer</span>')
            self.assertEqual(self.f.f.app.json.loads(self.f.f.app.json.dumps(dict(state='confirmed',name='Enregistrer',label=NativeText('Présent')))),dict(state='confirmed',name='Enregistrer',label='Present'))
            self.assertIn('Present',render_template_string('{{ {"label": label}|tojson }}',label=NativeText('Présent')))
    def test_idle_clears_actual_public_grants(self):
        token=self.login()
        with self.client.session_transaction() as s:
            for key in ('_enrollment_flow','_enrollment_previous_document','family_enrollment_guardian','family_booking','family_receipt'):s[key]='FICTITIOUS'
        self.client.post('/langue/repos',data=dict(evolution_csrf=token))
        with self.client.session_transaction() as s:
            for key in ('_enrollment_flow','_enrollment_previous_document','family_enrollment_guardian','family_booking','family_receipt'):self.assertNotIn(key,s)
    def test_native_dynamic_error_escapes_html(self):
        from flask import render_template_string,g
        with self.f.f.app.test_request_context('/'):
            self.f.f.app.preprocess_request()
            g.ui_language='en'
            self.assertEqual(t('Il y a 7 jours'),'7 days ago')
            body=render_template_string('{{ error }}',error='<script>FICTITIOUS</script>')
            self.assertNotIn('<script>',body);self.assertIn('&lt;script&gt;',body)
    def test_language_form_preserves_deployment_prefix(self):
        self.login()
        response=self.client.get('/admin/maintenance',environ_overrides={'SCRIPT_NAME':'/stat'})
        self.assertEqual(response.status_code,200);self.assertIn('value="/stat/admin/maintenance?',response.text)
    def test_language_flags_not_translated_and_business_keys_preserved(self):
        token=self.login()
        self.client.post('/langue',data=dict(evolution_csrf=token,scope='admin',language='en',next='/admin/maintenance'))
        response=self.client.get('/admin/maintenance');self.assertIn('🇫🇷 FR',response.text);self.assertIn('🇬🇧 EN',response.text)
        response=self.client.get('/admin/reglages/borne')
        self.assertIn('value="fr"',response.text);self.assertIn('value="en"',response.text)
    def test_idle_revokes_enrollment_even_if_old_signed_cookie_is_replayed(self):
        import re
        write_setting(self.db,'self_enrollment_enabled','1');self.db.commit()
        self.client.get('/inscription')
        with self.client.session_transaction() as session:token=session['evolution_csrf']
        old=self.client.get_cookie('session').value
        self.assertTrue(self.client.get('/inscription/etat',headers={'X-OpenFabLab-Enrollment':token}).json['active'])
        self.assertEqual(self.client.post('/langue/repos',data=dict(evolution_csrf=token)).status_code,302)
        self.client.set_cookie('session',old)
        self.assertFalse(self.client.get('/inscription/etat',headers={'X-OpenFabLab-Enrollment':token}).json['active'])
    def test_dynamic_health_evidence_is_localized_without_changing_numbers(self):
        from flask import g
        with self.f.f.app.test_request_context('/'):
            self.f.f.app.preprocess_request();g.ui_language='en'
            self.assertEqual(t('12.34 Gio libres observés.'),'12.34 GiB of free space observed.')
            self.assertEqual(t('2 envoi(s) incertain(s), sans renvoi automatique.'),'2 uncertain deliveries; no automatic resend.')
    def test_native_wordpress_errors_have_local_english_entries(self):
        from pathlib import Path
        import re
        from i18n import CATALOG
        folder=Path(__file__).resolve().parents[1]/'wordpress/openfablab-reservations/includes'
        for name in ('relay','api','public'):
            source=(folder/('class-openfablab-'+name+'.php')).read_text()
            messages=re.findall(r"self::error\('([^']+)'",source)+re.findall(r"new WP_Error\('[^']+','([^']+)'",source)
            for message in messages:self.assertIn(message,CATALOG,message)
    def test_public_counter_captions_use_complete_native_phrases(self):
        from flask import g,render_template_string
        with self.f.f.app.test_request_context('/'):
            self.f.f.app.preprocess_request();g.ui_language='en'
            for count,label in ((1,'User present'),(2,'Users present')):
                self.assertEqual(render_template_string("{{ _('Usager présent' if count == 1 else 'Usagers présents') }}",count=count),label)
            self.assertEqual(t("Visiteurs aujourd'hui"),'Visitors today')
    def test_static_html_fragments_are_translated_or_explicitly_technical(self):
        from pathlib import Path
        import re
        from i18n import CATALOG
        messages=set()
        folder=Path(__file__).resolve().parents[1]/'templates'
        for path in folder.glob('*.html'):preprocess_html(path.read_text(),messages)
        technical={'OpenFabLab','OpenLabs','admin-login-page','admin-page','home-document','home-page home-theme-',
            'home-scroll-locked','identification-page home-theme-','https://example.org/programme','https://exemple.fr',
            'https://fablab.exemple.fr/stat','https://openfablab.fr'}
        for message in messages:
            if len(message)<2 or re.fullmatch(r'[A-Z\d_ ./+:-]+',message) or message in technical:continue
            self.assertIn(message,CATALOG,message)

for _name in list(vars(NewVersion)):
    if _name.startswith('test_'):setattr(Languages,_name,None)
