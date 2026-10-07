"""Fictitious branding fixtures only; no production assets or personal data."""
import io
import re
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET
from PIL import Image

from tests import test_app as fixtures
from app import (get_database, load_structure_settings, generate_badge_svg, generate_badge_png,
                 initialize_database, document_brand_assets, write_setting, STRUCTURE_FIELDS)
from branding import validate_badge_template, migrate_branding_settings
from profile_archive import parse_profile, build_profile

TEMPLATE = b'''<svg xmlns="http://www.w3.org/2000/svg" width="54mm" height="86mm" viewBox="0 0 54 86">
<g id="vector-logo" transform="translate(4.2,3.2) scale(2)"><path d="M0 0L3 0L0 3Z" fill="#ff0000"/></g>
<text id="user-id" x="27" y="9.9" text-anchor="middle" font-size="5.6">ID</text>
<text id="first-name" x="27" y="29.6" text-anchor="middle" font-size="10.7">Alex</text>
<text id="category" x="27" y="36.4" text-anchor="middle" font-size="3.9">Usager</text>
<g id="qr-code"></g></svg>'''


class BrandingTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.OpenFabLabTestCase(); self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.client = self.f.client
        self.data = Path(self.f.database_path).parent
        self.branding = self.data / 'branding'
        self.f.login_admin()

    def set(self, **values):
        with self.f.app.app_context():
            db=get_database()
            for key,value in values.items(): write_setting(db, key, value)
            db.commit()

    def token(self):
        page=self.client.get('/admin/reglages/structure').get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"',page).group(1)

    def svg(self, name='Éléonore-Jean', category='fabmanager'):
        with self.f.app.app_context():
            return generate_badge_svg({'public_id':'2001','first_name':name,'category':category}, load_structure_settings(get_database()))

    def install(self):
        (self.branding/'badge-template.svg').write_bytes(TEMPLATE)
        self.set(structure_badge_template='badge-template.svg')

    def test_default_and_fully_hidden_structure_logo(self):
        self.assertIn('brand/OpenFabLab-logo-horizontal.svg',self.client.get('/').get_data(as_text=True))
        self.set(structure_show_wordmark_logo='0')
        page=self.client.get('/').get_data(as_text=True)
        self.assertNotIn('<a class="brand"',page)
        self.assertNotIn('<div class="partner-logos"',page)

    def test_header_order_and_independent_visibility(self):
        for kind in ('wordmark','header_institution','network'):
            Image.new('RGBA',(40,40),'red').save(self.branding/(kind+'.png'))
            self.set(**{'structure_'+kind+'_logo':kind+'.png'})
        page=self.client.get('/').get_data(as_text=True)
        self.assertLess(page.index('structure/header_institution.png'),page.index('structure/network.png'))
        self.assertLess(page.index('structure/network.png'),page.index('Verrouiller'))
        self.set(structure_show_header_institution_logo='0',structure_show_network_logo='0')
        self.assertNotIn('<div class="partner-logos"', self.client.get('/').get_data(as_text=True))

    def test_document_logo_not_used_in_header(self):
        self.assertNotIn('structure/institution.png',self.client.get('/').get_data(as_text=True))
        with self.f.app.app_context():
            self.assertEqual(document_brand_assets(get_database())[1].name,'institution.png')

    def test_legacy_migration_is_additive_idempotent_and_preserves_off(self):
        with self.f.app.app_context():
            db=get_database()
            before=[tuple(r) for r in db.execute('SELECT * FROM users')]
            db.execute("DELETE FROM app_settings WHERE key='structure_header_institution_logo'")
            migrate_branding_settings(db,self.data);db.commit()
            self.assertEqual(load_structure_settings(db)['header_institution_logo'],'header_institution.png')
            self.assertEqual((self.branding/'institution.png').read_bytes(),(self.branding/'header_institution.png').read_bytes())
            write_setting(db,'structure_header_institution_logo','');write_setting(db,'structure_show_header_institution_logo','0')
            db.commit();migrate_branding_settings(db,self.data);migrate_branding_settings(db,self.data)
            self.assertEqual(load_structure_settings(db)['header_institution_logo'],'')
            self.assertFalse(load_structure_settings(db)['show_header_institution_logo'])
            self.assertEqual(before,[tuple(r) for r in db.execute('SELECT * FROM users')])
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],17)

    def test_custom_badge_not_selected_by_structure_name(self):
        self.set(structure_name='Atelier totalement fictif')
        self.install(); self.assertIn('vector-logo',self.svg().decode())

    def test_private_missing_invalid_never_falls_back(self):
        self.set(structure_badge_template='badge-template.svg')
        with self.assertRaisesRegex(ValueError,'absent'):self.svg()
        (self.branding/'badge-template.svg').write_bytes(b'<svg/>')
        with self.assertRaisesRegex(ValueError,'invalide'):self.svg()

    def test_template_security_and_dynamic_nodes(self):
        self.assertIn('vector-logo',validate_badge_template(TEMPLATE))
        for payload in (b'<script>alert(1)</script>',b'<image href="https://example.invalid/x"/>',
                        b'<g onload="evil()"/>',b'<foreignObject/>',b'<a href="#vector-logo"/>',
                        b'<path style="fill:url(https://example.invalid/x)"/>'):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):validate_badge_template(TEMPLATE.replace(b'</svg>',payload+b'</svg>'))
        with self.assertRaises(ValueError):validate_badge_template(b'<!DOCTYPE svg>'+TEMPLATE)
        with self.assertRaises(ValueError):validate_badge_template(TEMPLATE.replace(b'id="qr-code"',b'id="qr-code" transform="translate(1)"'))

    def test_badge_transforms_unicode_and_long_names(self):
        self.install()
        for name in ('Anne','Éléonore-Jean','Jean-Baptiste-Maximilien','<Fictif & Ami>'):
            raw=self.svg(name); root=ET.fromstring(raw)
            nodes={n.get('id'):n for n in root.iter()}
            self.assertEqual(nodes['first-name'].text,name)
            self.assertEqual(nodes['vector-logo'].get('transform'),'translate(4.2,3.2) scale(2)')
            if len(name)>11:self.assertEqual(nodes['first-name'].get('textLength'),'45')
        self.assertIn('Fabmanager',self.svg().decode())

    def test_qr_identical_generic_and_private(self):
        generic=ET.fromstring(self.svg())
        self.install(); private=ET.fromstring(self.svg())
        qr=lambda root: next(n for n in root.iter() if n.get('id')=='qr-code')
        self.assertEqual([n.attrib for n in qr(generic)],[n.attrib for n in qr(private)])

    def test_png_transparent_same_svg_source(self):
        self.install()
        with self.f.app.app_context():
            raw=generate_badge_png({'public_id':'2001','first_name':'Alex','category':'user'},load_structure_settings(get_database()))
        with Image.open(io.BytesIO(raw)) as image:
            self.assertEqual(image.size,(1913,3047));self.assertEqual(image.mode,'RGBA')
            self.assertEqual(image.getpixel((0,0))[3],0)
            self.assertEqual(image.getextrema()[3],(0,255))

    def test_clear_logo_explicit_nonce_permission_and_confirmation(self):
        token=self.token(); original=(self.branding/'institution.png').read_bytes()
        self.assertEqual(self.client.post('/admin/reglages/structure/supprimer/institution',data={'confirmation':'SUPPRIMER'}).status_code,400)
        self.assertEqual(self.client.post('/admin/reglages/structure/supprimer/institution',data={'csrf_token':token,'confirmation':'non'}).status_code,400)
        self.assertEqual(self.client.post('/admin/reglages/structure/supprimer/institution',data={'csrf_token':token,'confirmation':'SUPPRIMER'}).status_code,302)
        with self.f.app.app_context():self.assertIsNone(document_brand_assets(get_database())[1])
        self.assertEqual((self.branding/'institution.png').read_bytes(),original)
        with self.client.session_transaction() as session:session['access_role']='moderator'
        self.assertEqual(self.client.post('/admin/reglages/structure/supprimer/main',data={'csrf_token':token,'confirmation':'SUPPRIMER'}).status_code,302)
        with self.f.app.app_context():self.assertEqual(load_structure_settings(get_database())['main_logo'],'main.png')

    def test_profile_contains_new_resources_and_privacy_fields(self):
        self.install();self.set(structure_data_controller='Association Fictive',structure_data_controller_representative='Camille Exemple',structure_show_network_logo='0')
        for kind in ('header_institution','network'):
            Image.new('RGB',(30,30),'blue').save(self.branding/(kind+'.png'))
            self.set(**{'structure_'+kind+'_logo':kind+'.png'})
        raw=self.client.get('/admin/profil/exporter').data;profile=parse_profile(raw)
        self.assertEqual(profile['assets']['assets/badge-template.svg'],TEMPLATE)
        self.assertIn('assets/network.png',profile['assets'])
        self.assertEqual(profile['settings']['structure_data_controller_representative'],'Camille Exemple')
        self.assertEqual(profile['settings']['structure_show_network_logo'],'0')
        self.assertNotIn('admin_pin_hash',profile['settings'])
        self.assertNotIn('reservation_wordpress_url',profile['settings'])
        token=self.token()
        for step in ('preview','apply'):
            response=self.client.post('/admin/profil/importer',data={'csrf_token':token,'step':step,'confirmation':'IMPORTER LE PROFIL','profile_file':(io.BytesIO(raw),'example.openfablab-profile.zip')})
            self.assertEqual(response.status_code,302)
        self.assertEqual((self.branding/'badge-template.svg').read_bytes(),TEMPLATE)
        self.assertIn('vector-logo',self.svg().decode())

    def test_privacy_legal_person_and_representative_distinct(self):
        self.set(structure_data_controller='Association Fictive',structure_data_controller_address='Adresse fictive',structure_data_controller_representative='Camille Exemple',structure_data_controller_representative_role='Présidente')
        page=self.client.get('/gestion-des-donnees').get_data(as_text=True)
        for value in ('Association Fictive','Adresse fictive','Camille Exemple','Présidente'):self.assertIn(value,page)
        self.assertNotIn('mailto:privacy@example.invalid',page)
        self.set(structure_data_controller='',structure_data_controller_representative='')
        self.assertIn('doit être renseigné',self.client.get('/gestion-des-donnees').get_data(as_text=True))

    def test_fresh_identity_has_no_private_defaults(self):
        from app import default_application_settings
        values=dict(default_application_settings())
        for key in ('network_logo','header_institution_logo','badge_template','data_controller','data_controller_representative'):
            self.assertEqual(values['structure_'+key],'')

    def test_blank_upload_preserves_and_reupload_restores(self):
        with self.f.app.app_context():
            settings=load_structure_settings(get_database())
        form={key:settings[key] for key in STRUCTURE_FIELDS}
        form['csrf_token']=self.token()
        form.update({f'module_{key}':'1' for key in ('frequency','users','activities','booking_slots','rentals','billing')})
        original=(self.branding/'institution.png').read_bytes()
        self.client.post('/admin/reglages/structure',data=form)
        self.assertEqual((self.branding/'institution.png').read_bytes(),original)
        output=io.BytesIO();Image.new('RGBA',(25,30),'green').save(output,'PNG')
        form['logo_institution']=(io.BytesIO(output.getvalue()),'example.png')
        self.client.post('/admin/reglages/structure',data=form,content_type='multipart/form-data')
        self.assertNotEqual((self.branding/'institution.png').read_bytes(),original)

    def test_badge_preview_is_fictitious_admin_only(self):
        self.install();response=self.client.get('/admin/reglages/structure/badge-apercu.png')
        self.assertEqual(response.status_code,200);self.assertEqual(response.mimetype,'image/png')
        with self.client.session_transaction() as session:session.clear()
        self.assertEqual(self.client.get('/admin/reglages/structure/badge-apercu.png').status_code,302)

    def test_all_four_logos_can_be_removed_and_readded_independently(self):
        token=self.token()
        for kind in ('wordmark','header_institution','network','institution'):
            with self.subTest(kind=kind):
                Image.new('RGBA',(30,30),'orange').save(self.branding/(kind+'.png'))
                self.set(**{'structure_'+kind+'_logo':kind+'.png'})
                before={p.name:p.read_bytes() for p in self.branding.glob('*.png')}
                self.client.post('/admin/reglages/structure/supprimer/'+kind,data={'csrf_token':token,'confirmation':'SUPPRIMER'})
                self.assertEqual(self.client.get('/media/structure/'+kind+'.png').status_code,404)
                self.assertEqual(before,{p.name:p.read_bytes() for p in self.branding.glob('*.png')})
                with self.f.app.app_context():settings=load_structure_settings(get_database())
                form={k:settings[k] for k in STRUCTURE_FIELDS};form['csrf_token']=token
                form.update({f'module_{k}':'1' for k in ('frequency','users','activities','billing')})
                form['logo_'+kind]=(io.BytesIO(before[kind+'.png']),'fictional.png')
                self.client.post('/admin/reglages/structure',data=form,content_type='multipart/form-data')
                response=self.client.get('/media/structure/'+kind+'.png')
                self.assertEqual(response.status_code,200);response.close()

    def test_documents_can_be_generated_without_any_logo(self):
        import zipfile
        self.set(structure_institution_logo='',structure_main_logo='')
        with self.f.app.app_context():
            structure,one,two,_=document_brand_assets(get_database())
            self.assertIsNone(one);self.assertIsNone(two)
        with self.client.session_transaction() as session: session.clear()
        self.f.test_v250_documents_use_configured_identity_without_historical_brand()
        with self.f.database() as db: record=db.execute('SELECT MAX(id) FROM billing_records').fetchone()[0]
        docx=self.client.get(f'/admin/facturation/{record}/devis.docx')
        self.assertEqual(docx.status_code,200)
        with zipfile.ZipFile(io.BytesIO(docx.data)) as archive:
            self.assertFalse(any(n.startswith('word/media/') for n in archive.namelist()))
        pdf=self.client.get(f'/admin/facturation/{record}/devis.pdf')
        self.assertEqual(pdf.status_code,200);self.assertNotIn(b'/Subtype /Image',pdf.data)

    def test_private_glyph_bank_produces_paths_and_survives_profile(self):
        from branding import outline_private_text
        bank='<defs id="badge-glyphs" data-units="1000">'+''.join(f'<path id="g-{ord(c):04x}" data-char="{ord(c):04x}" data-advance="600" d="M0 0L500 0L0 500Z"/>' for c in set('IDAlexUsager '))+'</defs>'
        raw=TEMPLATE.replace(b'<g id="vector-logo"',bank.encode()+b'<g id="vector-logo"',1)
        validate_badge_template(raw)
        outlined=outline_private_text(raw.decode())
        self.assertIn('<use href="#g-',outlined)
        self.assertIn('<desc>Alex</desc>',outlined)
        self.assertNotIn('<text id="first-name"',outlined)
        self.assertEqual(parse_profile(build_profile({'structure_badge_template':'badge-template.svg'},[],{'assets/badge-template.svg':raw}))['assets']['assets/badge-template.svg'],raw)

    def test_private_xml_quote_style_self_closing_qr_and_long_name(self):
        self.install()
        raw=TEMPLATE.replace(b'<g id="qr-code"></g>',b'<g fill="red" id="qr-code"/>')
        raw=raw.replace(b'id="first-name"',b'id="first-name" textLength="45" lengthAdjust="spacingAndGlyphs"').replace(b'"',b"'")
        (self.branding/'badge-template.svg').write_bytes(raw)
        root=ET.fromstring(self.svg('Jean-Baptiste-Maximilien'))
        nodes={n.get('id'):n for n in root.iter()}
        self.assertEqual(nodes['first-name'].get('textLength'),'45')
        self.assertGreater(len(nodes['qr-code']),10)

    def test_additive_migration_refuses_overwrite_of_existing_distinct_logo(self):
        with self.f.app.app_context():
            db=get_database();db.execute("DELETE FROM app_settings WHERE key='structure_header_institution_logo'")
            db.commit()
            (self.branding/'header_institution.png').write_bytes(b'distinct-private-resource')
            with self.assertRaisesRegex(ValueError,'différent'):migrate_branding_settings(db,self.data)
        self.assertEqual((self.branding/'header_institution.png').read_bytes(),b'distinct-private-resource')

    def test_private_canonical_xml_background_is_removed_and_png_transparent(self):
        self.install()
        raw=TEMPLATE.replace(b'<g id="vector-logo"',b'<rect id="card-background" width="54" height="86" fill="#222222"/><g id="vector-logo"',1)
        (self.branding/'badge-template.svg').write_bytes(raw)
        self.assertNotIn('card-background',self.svg().decode())
        with self.f.app.app_context():
            png=generate_badge_png({'public_id':'2001','first_name':'Alex','category':'user'},load_structure_settings(get_database()))
        with Image.open(io.BytesIO(png)) as image:self.assertEqual(image.getpixel((0,0))[3],0)
