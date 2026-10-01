"""First public release: neutral defaults, preservation, licensing and packaging."""
import hashlib
import re
import sqlite3
import tempfile
import os
import subprocess
import sys
import unittest
from pathlib import Path
from zipfile import ZipFile

from tests import test_app as fixtures
from app import create_app, default_application_settings, get_database, initialize_database
from billing import _document_identity
from openfablab import __version__

ROOT=Path(__file__).resolve().parents[1]


class PublicReleaseTests(unittest.TestCase):
    def test_canonical_version_and_compose(self):
        self.assertEqual(__version__,'2.6.1')
        self.assertIn('openfablab:v2.6.1',(ROOT/'compose.yaml').read_text())

    def test_every_default_is_generic_even_with_legacy_flag(self):
        for flag in (False,True):
            settings=dict(default_application_settings(flag))
            self.assertEqual(settings['structure_name'],'Mon FabLab')
            self.assertEqual(settings['structure_iban'],'')
            self.assertEqual(settings['structure_signer_name'],'')
            self.assertEqual(settings['structure_wordmark_logo'],'')
            self.assertEqual(settings['module_public_reservations'],'0')
            self.assertEqual(settings['reservation_sync_interval_minutes'],'2')
            self.assertTrue(all(value=='0' for key,value in settings.items() if key.startswith('billing_') and key.endswith('_cents')))

    def test_new_instance_empty_schema13_no_pin_or_secret(self):
        from pin_security import has_pin
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'openfablab.db'
            application=create_app(dict(TESTING=True,SEED_DEMO_USERS=False,DATABASE=str(path),
                                        SECRET_KEY='fictional-only',ADMIN_PIN=None,MODERATOR_PIN=None,
                                        AUTO_CLOSURE_WORKER=False,WEATHER_ENABLED=False))
            with application.app_context():
                db=get_database()
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],13)
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                for table in ('users','sessions','visitors','rental_catalog','billing_tariff_catalog','billing_clients','billing_records','animation_bookings'):
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0,table)
            self.assertFalse(has_pin(path,'admin'));self.assertFalse(has_pin(path,'moderator'))
            self.assertFalse((Path(directory)/'.openfablab_sync_secret').exists())
            self.assertFalse((Path(directory)/'.discord_webhook_url').exists())

    def test_configured_legacy_structure_values_are_preserved(self):
        # Structure name is a historical compatibility example; all financial/contact values are fictitious.
        fixture=fixtures.OpenFabLabTestCase();fixture.setUp()
        try:
            with fixture.app.app_context():
                db=get_database()
                initialize_database()  # Stabilize only the fictional test seed snapshots first.
                chosen={'structure_name':'FougèresLab','structure_description':'Description fictive configurée',
                        'structure_iban':'FICTIONAL-CONFIGURED-ACCOUNT','structure_email':'configured@example.invalid',
                        'structure_phone':'0600000000','structure_signer_name':'Responsable Fictif',
                        'structure_main_logo':'main.png','structure_signature':'signature.png',
                        'billing_rate_normal_hourly_cents':'4300','automatic_backup_subdirectory':'ArchivesPersonnalisees',
                        'discord_message_arrival':'Texte personnalisé {name}'}
                db.executemany('UPDATE app_settings SET value=? WHERE key=?',[(v,k) for k,v in chosen.items()]);db.commit()
                before=db.execute('SELECT * FROM users ORDER BY id').fetchall()
                initialize_database();initialize_database()
                actual=dict(db.execute('SELECT key,value FROM app_settings').fetchall())
                self.assertEqual({k:actual[k] for k in chosen},chosen)
                self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM users ORDER BY id')],[tuple(r) for r in before])
                self.assertTrue((Path(fixture.database_path).parent/'branding/signature.png').is_file())
        finally:
            fixture.tearDown()

    def test_direct_document_identity_has_no_financial_fallback(self):
        values=_document_identity()
        self.assertEqual(values['name'],'Mon FabLab')
        for field in ('iban','bic','siret','vat_number','email','phone','address','account_holder','legal_entity'):
            self.assertEqual(values[field],'',field)

    def test_only_verified_font_weights_are_present(self):
        fonts=ROOT/'static/fonts'
        self.assertEqual(sorted(p.name for p in fonts.glob('*.ttf')),['LibreFranklin-Bold.ttf','LibreFranklin-Regular.ttf'])
        for name,expected in [('LibreFranklin-Regular.ttf','01e26222a56e141e3abae670ab22be77f063999fc4ef64c4a9651de19b7728a8'),
                              ('LibreFranklin-Bold.ttf','3134a143a2a801a0e80198ea03cd7cc99066bcaeeaaecda758e852725c225303')]:
            self.assertEqual(hashlib.sha256((fonts/name).read_bytes()).hexdigest(),expected)
        self.assertIn('SIL OPEN FONT LICENSE Version 1.1',(fonts/'OFL.txt').read_text())
        self.assertIn('Copyright',(fonts/'OFL.txt').read_text())

    def test_generic_badge_escapes_text_and_uses_libre_font(self):
        from app import generate_badge_svg
        from xml.etree import ElementTree
        svg=generate_badge_svg(dict(first_name='<Fictif & Ami>',public_id='2001',category='user'),
                               dict(name='<Structure & Exemple>',short_name='Fictive')).decode()
        ElementTree.fromstring(svg)
        self.assertIn('Libre Franklin',svg)
        self.assertIn('&lt;Fictif &amp; Ami&gt;',svg)
        self.assertIn('id="qr-code"',svg)
        self.assertNotIn('fougeres',svg.lower())

    def test_no_institutional_asset_is_public(self):
        self.assertEqual({p.name for p in (ROOT/'static/brand').iterdir()},
                         {'OpenFabLab-logo-horizontal.svg','OpenFabLab-logo-complet.svg'})
        self.assertEqual({p.name for p in (ROOT/'badge_templates').iterdir()}, {'OpenFabLab-template.svg'})

    def test_full_mit_and_third_party_licenses_are_distributed(self):
        import build_openfablab,build_wordpress_plugin
        with tempfile.TemporaryDirectory() as directory:
            for output in (build_openfablab.build(Path(directory)/'app.zip'),build_wordpress_plugin.build(Path(directory)/'plugin.zip')):
                with ZipFile(output) as archive:
                    prefix='' if output.name=='app.zip' else 'openfablab-reservations/'
                    self.assertEqual(archive.read(prefix+'LICENSE'),(ROOT/'LICENSE').read_bytes())
                    self.assertIn(b'Apache',archive.read(prefix+'THIRD_PARTY_NOTICES.md'))

    def test_docker_statically_keeps_data_and_licenses(self):
        import yaml
        compose=yaml.safe_load((ROOT/'compose.yaml').read_text())
        service=compose['services']['application']
        self.assertEqual(service['ports'],['5080:8000'])
        self.assertIn('./data:/data',service['volumes'])
        self.assertEqual(service['environment']['OPENFABLAB_DATABASE'],'/data/openfablab.db')
        self.assertEqual(service['environment']['OPENFABLAB_URL_PREFIX'],'/stat')
        docker=(ROOT/'Dockerfile').read_text()
        self.assertIn('HEALTHCHECK',docker)
        self.assertIn('COPY LICENSE THIRD_PARTY_NOTICES.md',docker)

    def test_public_docs_links_resolve_without_private_documents(self):
        for path in [ROOT/'README.md',ROOT/'CONTRIBUTING.md',ROOT/'SECURITY.md']+list((ROOT/'docs').glob('*.md')):
            for target in re.findall(r'\]\(([^)]+)\)',path.read_text()):
                if '://' not in target and not target.startswith('#'):
                    self.assertTrue((path.parent/target.split('#')[0]).is_file(),str(path.relative_to(ROOT))+': '+target)
        for name in ('DEPLOIEMENT_NAS.md','PHASE2_MIGRATION.sh','PROJET.md','Ressources','Saves'):
            self.assertFalse((ROOT/name).exists(),name)

    def test_gitignore_keeps_examples_and_protects_private_families(self):
        content=(ROOT/'.gitignore').read_text()
        for pattern in ('.env','!.env.example','*.db','*.db-*','data/','branding/','dist/','node_modules/','.venv/','*.openfablab-profile.zip'):
            self.assertIn(pattern,content)
        self.assertNotRegex((ROOT/'.env.example').read_text(),r'(?i)fougeres|/volume1|https://|[A-Za-z0-9]{32}')

    def test_application_zip_runs_independently_of_the_repository(self):
        import build_openfablab
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);install=base/'installed';install.mkdir()
            output=build_openfablab.build(base/'release.zip')
            with ZipFile(output) as archive:
                archive.extractall(install)
            env={k:v for k,v in os.environ.items() if not k.startswith(('OPENFABLAB_','COMPTEUR_')) and k!='PYTHONPATH'}
            env.update(OPENFABLAB_DATABASE=str(base/'data/openfablab.db'),
                       OPENFABLAB_SECRET_KEY_FILE=str(base/'data/.secret_key'),
                       OPENFABLAB_ENABLE_SCHEDULER='0',OPENFABLAB_ENABLE_WEATHER='0',
                       PYTHONDONTWRITEBYTECODE='1')
            code='''
import pathlib,sqlite3,app
assert pathlib.Path(app.__file__).resolve().parent==pathlib.Path.cwd()
assert app.app.config['APP_VERSION']=='V2.6.1'
client=app.app.test_client()
for route in ('/','/sante','/gestion-des-donnees','/static/fonts/LibreFranklin-Regular.ttf','/static/fonts/LibreFranklin-Bold.ttf','/static/brand/OpenFabLab-logo-horizontal.svg'):
    response=client.get(route)
    assert response.status_code==200,route
    response.close()
with sqlite3.connect(app.app.config['DATABASE']) as db:
    assert db.execute('PRAGMA user_version').fetchone()[0]==13
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0]==0
    assert db.execute('SELECT COUNT(*) FROM rental_catalog').fetchone()[0]==0
'''
            result=subprocess.run([sys.executable,'-c',code],cwd=install,env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse((install/'Ressources').exists())

    def test_exact_public_manifest_and_content_guards(self):
        from tools.check_public_tree import check
        names=check()
        self.assertIn('PUBLIC_FILES.txt',names)
        self.assertNotIn('test_phase2a_script.py','\n'.join(names))
        self.assertNotIn('test_phase2_migration.py','\n'.join(names))
        self.assertNotIn('test_nas_update_v26.py','\n'.join(names))


if __name__=='__main__':
    unittest.main()
