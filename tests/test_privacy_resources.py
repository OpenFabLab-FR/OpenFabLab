"""2.7.0 regression tests, using only fictional identity and geometric resources."""
import hashlib
import io
import re
import sqlite3
import unittest
from pathlib import Path
from PIL import Image
from tests import test_app as fixtures
from tests.test_branding import TEMPLATE
from app import (STRUCTURE_FIELDS, default_application_settings, get_database, initialize_database,
                 load_structure_settings, document_brand_assets, generate_badge_svg, generate_badge_png,
                 write_setting)
from branding import RESOURCE_USAGE_KEYS
from profile_archive import build_profile, parse_profile


class PrivacyResourceTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.OpenFabLabTestCase();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.f.login_admin();self.client=self.f.client
        self.data=Path(self.f.database_path).parent;self.branding=self.data/'branding'

    def set(self, **values):
        with self.f.app.app_context():
            db=get_database()
            for key,value in values.items():write_setting(db,key,value)
            db.commit()

    def settings(self):
        with self.f.app.app_context():return load_structure_settings(get_database())

    def token(self):
        html=self.client.get('/admin/reglages/structure').get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"',html).group(1)

    def form(self, **values):
        current=self.settings();form={key:current[key] for key in STRUCTURE_FIELDS}
        form.update(csrf_token=self.token())
        form.update({f'module_{key}':'1' for key in ('frequency','users','activities','billing','booking_slots','rentals')})
        form.update(values);return form

    def page(self):return self.client.get('/gestion-des-donnees').get_data(as_text=True)

    def install(self):
        (self.branding/'badge-template.svg').write_bytes(TEMPLATE)
        self.set(structure_badge_template='badge-template.svg')

    def badge(self, png=False):
        with self.f.app.app_context():
            return (generate_badge_png if png else generate_badge_svg)(
                {'public_id':'2001','first_name':'Éloïse-Exemple','category':'user'},self.settings())

    def test_free_dpo_round_trip_preserves_text_and_escapes_markup(self):
        value='  Service DPO — Équipe « Protection » (organisme fictif) & <conseil>  '
        self.client.post('/admin/reglages/structure',data=self.form(dpo=value,dpo_email='dpo@example.invalid'))
        self.assertEqual(self.settings()['dpo'],value)
        html=self.page();self.assertIn('&lt;conseil&gt;',html);self.assertNotIn('<conseil>',html)
        self.assertIn('Délégué à la protection des données',html)

    def test_dpo_service_without_physical_person_or_phone(self):
        self.set(structure_dpo='Service DPO des ateliers fictifs',structure_dpo_email='service@example.invalid')
        html=self.page();self.assertIn('Service DPO des ateliers fictifs',html)
        self.assertIn('mailto:service@example.invalid',html);self.assertNotIn('mailto:privacy@example.invalid',html)

    def test_dpo_email_only_is_allowed(self):
        self.set(structure_dpo='',structure_dpo_email='service@example.invalid')
        self.assertIn('Délégué à la protection des données',self.page())

    def test_dpo_phone_only_is_allowed_and_escaped(self):
        self.set(structure_dpo_phone='Standard fictif <poste 2>')
        self.assertIn('Standard fictif &lt;poste 2&gt;',self.page())

    def test_no_dpo_means_no_card_or_general_email_fallback(self):
        html=self.page()
        self.assertNotIn('Délégué à la protection des données',html)
        self.assertNotIn('Contact pour les données personnelles',html)
        self.assertNotIn('mailto:privacy@example.invalid',html)

    def test_representative_punctuation_with_partial_fields(self):
        for name,role,expected in [('Camille Exemple','Présidente','Camille Exemple, Présidente'),
                                   ('Camille Exemple','','Camille Exemple'),('','Présidente','Présidente')]:
            with self.subTest(name=name,role=role):
                self.set(structure_data_controller_representative=name,structure_data_controller_representative_role=role)
                html=self.page();self.assertIn(expected,html)
                self.assertNotIn('Représentant du responsable du traitement',html)
                self.assertNotIn('<br>, ',html)

    def test_short_representative_label_and_visible_resource_cards(self):
        html=self.client.get('/admin/reglages/structure').get_data(as_text=True)
        privacy=self.client.get('/admin/reglages/donnees').get_data(as_text=True)
        self.assertIn('<span>Représentant</span>',privacy)
        self.assertNotIn('Représentant du responsable du traitement',html)
        self.assertNotIn('<details class="branding-extra"',html)
        for kind in ('main','signature','badge'):self.assertIn('data-resource="'+kind+'"',html)
        for key in RESOURCE_USAGE_KEYS:self.assertIn('name="'+key+'"',html)

    def test_telemetry_notice_and_visible_full_site_url(self):
        html=self.page()
        self.assertIn("Aucune télémétrie n&#39;est transmise automatiquement",html) if 'n&#39;est' in html else self.assertIn("Aucune télémétrie n'est transmise automatiquement",html)
        self.assertIn('href="https://openfablab.fr"',html);self.assertIn('>https://openfablab.fr</a>',html)

    def test_invalid_dpo_email_is_rejected_without_configuration_write(self):
        self.client.post('/admin/reglages/structure',data=self.form(dpo='Ne pas enregistrer',dpo_email='invalid-address'))
        self.assertEqual(self.settings()['dpo'],'')

    def test_private_resource_previews_load_even_when_usage_disabled(self):
        self.set(structure_use_main_logo='0',structure_use_signature='0')
        for kind in ('main','signature'):
            response=self.client.get('/admin/reglages/structure/ressource/'+kind+'.png')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.mimetype,'image/png')
            self.assertEqual(response.headers['Cache-Control'],'private, no-store')
            self.assertEqual(response.data,(self.branding/(kind+'.png')).read_bytes())
            response.close()
        self.assertEqual(self.client.get('/admin/reglages/structure/ressource/unknown.png').status_code,404)
        self.assertEqual(self.client.get('/media/structure/signature.png').status_code,404)

    def test_signature_preview_requires_administrator(self):
        url='/admin/reglages/structure/ressource/signature.png'
        with self.client.session_transaction() as session:session['access_role']='moderator'
        self.assertEqual(self.client.get(url).status_code,302)
        with self.client.session_transaction() as session:session.clear()
        self.assertEqual(self.client.get(url).status_code,302)

    def test_schema13_additive_migration_preserves_all_business_and_files(self):
        self.install()
        before_files={p.name:p.read_bytes() for p in self.branding.iterdir()}
        with self.f.app.app_context():
            db=get_database();initialize_database()
            tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name!='app_settings'")]
            before={table:[tuple(r) for r in db.execute('SELECT * FROM '+table)] for table in tables}
            for key in ('dpo','dpo_email','dpo_phone',*RESOURCE_USAGE_KEYS):
                db.execute('DELETE FROM app_settings WHERE key=?',('structure_'+key,))
            write_setting(db,'dpo_name','Service historique fictif');write_setting(db,'dpo_email','legacy@example.invalid')
            db.commit();initialize_database();initialize_database()
            settings=load_structure_settings(db)
            self.assertEqual(settings['dpo'],'Service historique fictif');self.assertEqual(settings['dpo_email'],'legacy@example.invalid')
            for key in RESOURCE_USAGE_KEYS:self.assertTrue(settings[key])
            self.assertEqual(before,{table:[tuple(r) for r in db.execute('SELECT * FROM '+table)] for table in tables})
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],14)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.assertEqual(before_files,{p.name:p.read_bytes() for p in self.branding.iterdir()})

    def test_explicit_empty_dpo_and_disabled_flags_win_over_legacy(self):
        self.set(structure_dpo='',dpo_name='Ne pas adopter',structure_use_main_logo='0')
        with self.f.app.app_context():initialize_database();initialize_database()
        self.assertEqual(self.settings()['dpo'],'');self.assertFalse(self.settings()['use_main_logo'])

    def test_fresh_defaults_are_generic(self):
        values=dict(default_application_settings())
        for key in ('dpo','dpo_email','dpo_phone','badge_template','network_logo'):self.assertEqual(values['structure_'+key],'')
        for key in RESOURCE_USAGE_KEYS:self.assertEqual(values['structure_'+key],'1')

    def test_disable_and_reenable_resources_preserves_bytes_and_svg_png(self):
        self.install();before={p.name:p.read_bytes() for p in self.branding.iterdir()}
        self.assertIn(b'vector-logo',self.badge())
        values=dict(branding_resources_form='1')
        self.client.post('/admin/reglages/structure',data=self.form(**values))
        with self.f.app.app_context():
            self.assertEqual(document_brand_assets(get_database())[2:],(None,None))
        self.assertNotIn(b'vector-logo',self.badge())
        with Image.open(io.BytesIO(self.badge(True))) as image:self.assertEqual(image.mode,'RGBA')
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.branding.iterdir()})
        values.update({key:'1' for key in RESOURCE_USAGE_KEYS})
        self.client.post('/admin/reglages/structure',data=self.form(**values))
        with self.f.app.app_context():self.assertTrue(all(document_brand_assets(get_database())[2:]))
        self.assertIn(b'vector-logo',self.badge())
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.branding.iterdir()})

    def test_older_form_does_not_disable_new_usage_flags(self):
        self.client.post('/admin/reglages/structure',data=self.form())
        for key in RESOURCE_USAGE_KEYS:self.assertTrue(self.settings()[key])

    def test_disabled_missing_private_template_uses_generic_but_enabled_errors(self):
        self.set(structure_badge_template='badge-template.svg',structure_use_badge_template='0')
        self.assertIn(b'Libre Franklin',self.badge())
        self.set(structure_use_badge_template='1')
        with self.assertRaisesRegex(ValueError,'absent'):self.badge()

    def test_profile_roundtrip_retains_dpo_disabled_flags_and_private_files(self):
        self.install();self.set(structure_dpo='Service fictif — Équipe DPO',structure_dpo_email='dpo@example.invalid',structure_dpo_phone='',
                               structure_use_main_logo='0',structure_use_signature='0',structure_use_badge_template='0')
        raw=self.client.get('/admin/profil/exporter').data;profile=parse_profile(raw)
        self.assertEqual(profile['settings']['structure_dpo'],'Service fictif — Équipe DPO')
        for key in RESOURCE_USAGE_KEYS:self.assertEqual(profile['settings']['structure_'+key],'0')
        self.assertIn('assets/main.png',profile['assets']);self.assertIn('assets/signature.png',profile['assets'])
        self.assertEqual(profile['assets']['assets/badge-template.svg'],TEMPLATE)
        self.set(structure_dpo='Modifié',structure_use_badge_template='1')
        for step in ('preview','apply'):
            response=self.client.post('/admin/profil/importer',data={'csrf_token':self.token(),'step':step,'confirmation':'IMPORTER LE PROFIL',
                'profile_file':(io.BytesIO(raw),'fictional.openfablab-profile.zip')},content_type='multipart/form-data')
            self.assertEqual(response.status_code,302)
        self.assertEqual(self.settings()['dpo'],'Service fictif — Équipe DPO')
        self.assertFalse(self.settings()['use_badge_template']);self.assertEqual((self.branding/'badge-template.svg').read_bytes(),TEMPLATE)

    def test_old_profile_without_new_keys_remains_valid(self):
        profile=parse_profile(build_profile({'structure_name':'Atelier fictif','structure_badge_template':'badge-template.svg'},[],{'assets/badge-template.svg':TEMPLATE}))
        self.assertNotIn('structure_dpo',profile['settings'])
        self.assertIn('assets/badge-template.svg',profile['assets'])

    def test_profile_rejects_bad_boolean_and_bad_email(self):
        for settings in ({'structure_use_signature':'yes'},{'structure_dpo_email':'javascript:invalid'}):
            with self.subTest(settings=settings):
                with self.assertRaises(ValueError):parse_profile(build_profile(settings,[],{}))

    def test_dpo_write_requires_csrf_and_admin(self):
        form=self.form(dpo='Ne pas adopter');token=form.pop('csrf_token')
        self.assertEqual(self.client.post('/admin/reglages/structure',data=form).status_code,400)
        with self.client.session_transaction() as session:session['access_role']='moderator'
        form['csrf_token']=token
        self.client.post('/admin/reglages/structure',data=form)
        self.assertEqual(self.settings()['dpo'],'')


if __name__=='__main__':unittest.main()
