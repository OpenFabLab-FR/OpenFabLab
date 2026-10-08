"""Fictional persistent installations only. No production secrets or databases."""
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from zipfile import ZipFile, ZIP_DEFLATED

import test_app
import app
import private_backup as backup
from pin_security import check_pin, credential_path
from runtime_policy import TEST_MARKER, external_allowed


class PrivateBackupTests(unittest.TestCase):
    def setUp(self):
        self.f = test_app.OpenFabLabTestCase(); self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.db = Path(self.f.database_path)
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / 'private.zip'
        (self.db.parent / '.openfablab_flask_secret').write_text('fictional-session-signing-key')
        (self.db.parent / '.openfablab_sync_secret').write_text('fictional-wordpress-secret')
        (self.db.parent / '.discord_webhook_url').write_text('https://example.invalid/webhook')
        (self.db.parent / '.openfablab_smtp.json').write_text(json.dumps(dict(enabled=True,password='fictional-password',host='example.invalid',username='fictional')))
        (self.db.parent / 'future-private-resource').write_text('fictive persistent value')

    def export(self, kind='complete'):
        return backup.create_backup(self.db, self.archive, kind=kind)

    def restore(self):
        target = self.root / 'restored' / 'openfablab.db'
        backup.restore_backup(self.archive, target)
        return target

    def alter(self, change):
        with ZipFile(self.archive) as z:
            contents = {n:z.read(n) for n in z.namelist()}
        change(contents)
        with ZipFile(self.archive,'w',ZIP_DEFLATED) as z:
            for name,data in contents.items():z.writestr(name,data)

    def test_complete_manifest_schema_and_components(self):
        m=self.export(); self.assertEqual((m['format_version'],m['kind'],m['sqlite_schema']),(1,'complete',18))
        self.assertTrue(m['components']['admin_pin']);self.assertTrue(m['components']['branding'])
        self.assertTrue(m['components']['smtp']);self.assertTrue(m['components']['wordpress'])

    def test_manifest_never_contains_secret_values(self):
        self.export()
        with ZipFile(self.archive) as z:
            data=z.read(backup.MANIFEST)
            for secret in (b'fictional-password',b'fictional-wordpress-secret',b'fictional-session-signing-key'):
                self.assertNotIn(secret,data)

    def test_archive_private_permissions(self):
        self.export();self.assertEqual(self.archive.stat().st_mode&0o777,0o600)

    def test_unknown_future_persistent_file_included(self):
        self.export();target=self.restore()
        self.assertEqual((target.parent/'future-private-resource').read_text(),'fictive persistent value')

    def test_transients_excluded(self):
        for name in ('test.log','.session.lock','temporary.tmp','.openfablab_pin_recovery'):
            (self.db.parent/name).write_text('fictive transient')
        (self.db.parent/'Saves').mkdir();(self.db.parent/'Saves'/'old.db').write_text('old')
        m=self.export();self.assertFalse(any(r['path'].endswith(('.lock','.log','.tmp')) or 'Saves/' in r['path'] for r in m['files']))

    def test_symlink_refused(self):
        (self.db.parent/'unexpected-link').symlink_to(self.db)
        with self.assertRaises(ValueError):self.export()

    def test_altered_file_refused_before_replacement(self):
        self.export();self.alter(lambda c:c.update({'persistent/future-private-resource':b'altered'}))
        with self.assertRaises(ValueError):backup.restore_backup(self.archive,self.db)
        self.assertTrue(check_pin(self.db,'admin','1379'))

    def test_extra_file_refused(self):
        self.export();self.alter(lambda c:c.update({'persistent/extra':b'unknown'}))
        with self.assertRaises(ValueError):backup.validate_backup(self.archive)

    def test_traversal_refused(self):
        self.export();self.alter(lambda c:c.update({'../unsafe':b'no'}))
        with self.assertRaises(ValueError):backup.validate_backup(self.archive)

    def test_newer_version_refused(self):
        self.export()
        def change(c):
            m=json.loads(c[backup.MANIFEST]);m['openfablab_version']='2.9.0';c[backup.MANIFEST]=json.dumps(m).encode()
        self.alter(change)
        with self.assertRaises(ValueError):backup.validate_backup(self.archive)

    def test_newer_schema_refused(self):
        with sqlite3.connect(self.db) as db:db.execute('PRAGMA user_version=19')
        with self.assertRaises(ValueError):self.export()

    def test_wrong_sqlite_refused(self):
        bad=self.root/'bad.db'
        with sqlite3.connect(bad) as db:db.execute('PRAGMA user_version=14')
        with self.assertRaises(ValueError):backup.sqlite_check(bad)

    def test_pin_derivation_transport_and_login(self):
        self.export();target=self.restore()
        self.assertEqual(credential_path(self.db,'admin').read_bytes(),credential_path(target,'admin').read_bytes())
        self.assertTrue(check_pin(target,'admin','1379'));self.assertTrue(check_pin(target,'moderator','8642'))
        self.assertNotEqual(b'1379',credential_path(target,'admin').read_bytes().strip())

    def test_branding_transport(self):
        self.export();target=self.restore()
        self.assertEqual((target.parent/'branding/main.png').read_bytes(),(self.db.parent/'branding/main.png').read_bytes())

    def test_full_backup_preserves_external_configuration(self):
        self.export();target=self.restore()
        self.assertEqual((target.parent/'.openfablab_sync_secret').read_text(),'fictional-wordpress-secret')
        self.assertEqual(json.loads((target.parent/'.openfablab_smtp.json').read_text())['password'],'fictional-password')

    def test_restore_is_replacement_not_merge_and_safety_backup(self):
        self.export();(self.db.parent/'obsolete-resource').write_text('old')
        m,safety=backup.restore_backup(self.archive,self.db)
        self.assertFalse((self.db.parent/'obsolete-resource').exists())
        self.assertTrue((safety/'before-restore.zip').is_file());backup.validate_backup(safety/'before-restore.zip')
        self.assertEqual(backup.sqlite_check(self.db),18)

    def test_restore_failure_rolls_back_all_files(self):
        self.export();(self.db.parent/'old-only').write_text('preserved')
        original=backup.os.replace
        def failure(source,target):
            if '/payload/' in str(source) and Path(target).name=='branding':raise OSError('simulated disk failure')
            return original(source,target)
        with mock.patch('private_backup.os.replace',side_effect=failure):
            with self.assertRaises(OSError):backup.restore_backup(self.archive,self.db)
        self.assertEqual((self.db.parent/'old-only').read_text(),'preserved')
        self.assertTrue(check_pin(self.db,'admin','1379'));self.assertEqual(backup.sqlite_check(self.db),18)

    def test_custom_flask_path_restored(self):
        backup.create_backup(self.db,self.archive,extras={'flask':self.db.parent/'.openfablab_flask_secret'})
        target=self.root/'custom'/'openfablab.db'
        backup.restore_backup(self.archive,target,bindings={'flask':target.parent/'.secret_key'})
        self.assertEqual((target.parent/'.secret_key').read_text(),'fictional-session-signing-key')

    def test_test_copy_original_unchanged(self):
        before=self.db.read_bytes();self.export('test')
        self.assertEqual(self.db.read_bytes(),before)
        self.assertEqual((self.db.parent/'.openfablab_sync_secret').read_text(),'fictional-wordpress-secret')

    def test_test_clone_pin_kept_session_key_rotated(self):
        self.export('test');target=self.restore()
        self.assertTrue(check_pin(target,'admin','1379'))
        self.assertNotEqual((target.parent/'.openfablab_flask_secret').read_text(),'fictional-session-signing-key')

    def test_test_clone_integrations_removed(self):
        self.export('test');target=self.restore()
        self.assertFalse((target.parent/'.openfablab_sync_secret').exists());self.assertFalse((target.parent/'.discord_webhook_url').exists())
        config=json.loads((target.parent/'.openfablab_smtp.json').read_text());self.assertFalse(config['enabled']);self.assertEqual(config['password'],'')
        with sqlite3.connect(target) as db:
            for key in ('module_public_reservations','module_discord','module_weather'):
                self.assertEqual(db.execute('SELECT value FROM app_settings WHERE key=?',(key,)).fetchone()[0],'0')

    def test_clone_marker_and_no_first_setup(self):
        self.export('test');target=self.restore()
        application=app.create_app({'DATABASE':str(target),'TESTING':True,'SECRET_KEY':'fixture','AUTO_CLOSURE_WORKER':True})
        self.assertFalse(application.config['AUTO_CLOSURE_WORKER']);self.assertFalse(application.config['WEATHER_ENABLED'])
        client=application.test_client();self.assertEqual(client.get('/admin/initialisation').status_code,302)
        with client.session_transaction() as s:s['access_role']='admin';s['admin_authenticated']=True
        self.assertNotIn('Instance issue d’une copie de test',client.get('/admin/reglages/donnees').get_data(as_text=True))
        from runtime_policy import external_allowed, is_test_instance
        self.assertTrue(is_test_instance(target))
        with application.app_context():
            self.assertFalse(external_allowed(target))

    def test_clone_no_smtp_transport_even_if_reconfigured(self):
        self.export('test');target=self.restore()
        application=app.create_app({'DATABASE':str(target),'TESTING':True,'SECRET_KEY':'fixture'})
        import welcome_mail
        with application.app_context(),mock.patch('welcome_mail.smtplib.SMTP') as transport:
            with self.assertRaises(OSError):welcome_mail.send({},None)
            transport.assert_not_called()

    def test_clone_no_wordpress_transport(self):
        self.export('test');target=self.restore()
        import reservations_sync
        client=mock.Mock()
        with sqlite3.connect(target) as db:
            self.assertTrue(reservations_sync.run_sync_cycle(db,target,'https://example.invalid',client=client)['isolated'])
        self.assertFalse(client.mock_calls)

    def test_clone_no_discord_transport(self):
        self.export('test');target=self.restore()
        application=app.create_app({'DATABASE':str(target),'TESTING':True,'SECRET_KEY':'fixture'})
        with application.app_context(),mock.patch('app.urllib.request.urlopen') as transport:
            with self.assertRaises(OSError):app.post_discord_message('https://example.invalid','fictional')
            transport.assert_not_called()

    def test_clone_socket_and_dns_blocked_loopback_allowed(self):
        self.export('test');target=self.restore()
        code="import runtime_policy,socket;runtime_policy.install_network_guard();\ntry:socket.getaddrinfo('example.invalid',443)\nexcept OSError:print('DNS_BLOCKED')\ntry:socket.create_connection(('203.0.113.1',443),timeout=.01)\nexcept OSError:print('CONNECT_BLOCKED')\nprint('LOOPBACK',bool(socket.getaddrinfo('127.0.0.1',80)))"
        env=os.environ.copy();env['OPENFABLAB_DATABASE']=str(target)
        result=subprocess.run([sys.executable,'-c',code],cwd=Path(app.__file__).parent,env=env,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('DNS_BLOCKED',result.stdout);self.assertIn('CONNECT_BLOCKED',result.stdout);self.assertIn('LOOPBACK True',result.stdout)

    def test_complete_restore_cannot_reenable_test_instance(self):
        self.export();(self.db.parent/TEST_MARKER).write_text('{}')
        m,_=backup.restore_backup(self.archive,self.db)
        self.assertEqual(m['kind'],'test');self.assertFalse(external_allowed(self.db))

    def test_web_permissions_nonce_and_acknowledgement(self):
        client=self.f.app.test_client()
        self.assertEqual(client.post('/admin/sauvegarde/privee/complete').status_code,302)
        with client.session_transaction() as s:s['access_role']='moderator'
        self.assertIn(client.post('/admin/sauvegarde/privee/complete').status_code,(302,403))
        with client.session_transaction() as s:s['access_role']='admin';s['pin_csrf']='fixture-nonce'
        self.assertEqual(client.post('/admin/sauvegarde/privee/complete',data={'sensitive_ack':'1'}).status_code,400)
        self.assertEqual(client.post('/admin/sauvegarde/privee/complete',data={'csrf_token':'fixture-nonce'}).status_code,400)
        self.assertEqual(client.get('/admin/sauvegarde/privee/complete').status_code,405)

    def test_web_backup_and_copy(self):
        client=self.f.app.test_client()
        with client.session_transaction() as s:s['access_role']='admin';s['pin_csrf']='fixture-nonce'
        for kind in ('complete','test'):
            response=client.post('/admin/sauvegarde/privee/'+kind,data={'csrf_token':'fixture-nonce','sensitive_ack':'1'})
            self.assertEqual(response.status_code,200);self.assertEqual(response.headers['Cache-Control'],'no-store, private')
            self.archive.write_bytes(response.data);self.assertEqual(backup.validate_backup(self.archive)['kind'],kind)

    def test_web_restore_confirmation_and_nonce(self):
        client=self.f.app.test_client()
        with client.session_transaction() as s:s['access_role']='admin';s['pin_csrf']='fixture-nonce'
        self.assertEqual(client.post('/admin/sauvegarde/restaurer-privee',data={'confirmation':'RESTAURER INSTALLATION'}).status_code,400)
        self.assertEqual(client.post('/admin/sauvegarde/restaurer-privee',data={'csrf_token':'fixture-nonce','confirmation':'RESTAURER'}).status_code,400)

    def test_schema13_backup_restored_then_normal_migration14(self):
        from schema12_fixture import create_schema12
        legacy=self.root/'legacy'/'openfablab.db';legacy.parent.mkdir()
        create_schema12(legacy)
        # 13 adds slot support; the fixture's classic data is valid at schema 13.
        with sqlite3.connect(legacy) as db:db.execute('PRAGMA user_version=13')
        backup.create_backup(legacy,self.archive,app_version='2.6.3')
        target=self.restore()
        self.assertEqual(backup.sqlite_check(target),13)
        application=app.create_app({'DATABASE':str(target),'SECRET_KEY':'fictional','TESTING':True})
        self.assertEqual(backup.sqlite_check(target),18)
        backup.create_backup(target,self.root/'after.zip',kind='test')
        self.assertEqual(backup.validate_backup(self.root/'after.zip')['sqlite_schema'],18)

    def test_initialization_failure_rolls_back(self):
        self.export();(self.db.parent/'must-survive').write_text('before')
        with self.assertRaises(RuntimeError):
            backup.restore_backup(self.archive,self.db,after_restore=lambda:(_ for _ in ()).throw(RuntimeError('simulated initialization failure')))
        self.assertEqual((self.db.parent/'must-survive').read_text(),'before')
        self.assertTrue(check_pin(self.db,'admin','1379'))

    def test_web_complete_restore_and_reauthentication(self):
        self.export()
        client=self.f.app.test_client()
        with client.session_transaction() as s:s['access_role']='admin';s['pin_csrf']='fixture-nonce'
        response=client.post('/admin/sauvegarde/restaurer-privee',data={'csrf_token':'fixture-nonce','confirmation':'RESTAURER INSTALLATION','private_backup':(io.BytesIO(self.archive.read_bytes()),'private.zip')})
        self.assertEqual(response.status_code,302);self.assertIn('/admin/connexion',response.headers['Location'])
        self.assertTrue(check_pin(self.db,'admin','1379'))

    def test_plaintext_pin_env_not_exported(self):
        (self.db.parent/'.env').write_text('OPENFABLAB_ADMIN_PIN=1379\nOTHER_PRIVATE_SETTING=fictive\n')
        self.export();target=self.restore()
        self.assertNotIn('ADMIN_PIN',(target.parent/'.env').read_text())
        self.assertIn('OTHER_PRIVATE_SETTING=fictive',(target.parent/'.env').read_text())

    def test_legacy_plaintext_pin_refused(self):
        with sqlite3.connect(self.db) as db:db.execute("INSERT OR REPLACE INTO app_settings VALUES('moderator_pin','8642')")
        with self.assertRaises(ValueError):self.export()

    def test_private_badge_and_profile_survive_full_restore(self):
        import profile_archive
        raw=(Path(app.__file__).parent/'badge_templates/OpenFabLab-template.svg').read_bytes()
        (self.db.parent/'branding/badge-template.svg').write_bytes(raw)
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE app_settings SET value='badge-template.svg' WHERE key='structure_badge_template'")
            db.execute("UPDATE app_settings SET value='1' WHERE key='structure_use_badge_template'")
            profile=profile_archive.build_profile(dict(db.execute('SELECT key,value FROM app_settings')),[],{'assets/badge-template.svg':raw})
        (self.db.parent/'fictive.openfablab-profile.zip').write_bytes(profile)
        self.export();target=self.restore()
        self.assertEqual((target.parent/'branding/badge-template.svg').read_bytes(),raw)
        self.assertEqual((target.parent/'fictive.openfablab-profile.zip').read_bytes(),profile)
        profile_archive.parse_profile(profile)
        application=app.create_app({'DATABASE':str(target),'TESTING':True,'SECRET_KEY':'fixture','WEATHER_ENABLED':False})
        with application.app_context():
            db=app.get_database();structure=app.load_structure_settings(db)
            user=dict(first_name='Anne-Lise Éloïse',public_id='7998',category='user')
            self.assertIn('7998',app.generate_badge_svg(user,structure).decode())
            self.assertTrue(app.generate_badge_png(user,structure).startswith(b'\x89PNG'))

    def test_private_marker_git_and_docker_exclusions(self):
        root=Path(app.__file__).parent
        for file in ('.gitignore','.dockerignore'):
            text=(root/file).read_text();self.assertIn('.openfablab-*',text);self.assertIn('restore-backups',text)

    def test_storage_lock_precedes_session_decoding(self):
        import threading
        from runtime_policy import storage_guard
        client=self.f.app.test_client()
        with client.session_transaction() as s:s['access_role']='admin'
        entered=threading.Event();decoded=threading.Event();responses=[]
        original=self.f.app.wsgi_app
        def signal(environ,start_response):
            entered.set();return original(environ,start_response)
        self.f.app.wsgi_app=signal
        open_session=self.f.app.session_interface.open_session
        def decode(*args,**kwargs):
            decoded.set();return open_session(*args,**kwargs)
        self.f.app.session_interface.open_session=decode
        with storage_guard(self.db):
            thread=threading.Thread(target=lambda:responses.append(client.get('/admin/reglages/donnees').status_code))
            thread.start();self.assertTrue(entered.wait(1));self.assertFalse(decoded.wait(.05))
            self.f.app.secret_key='new-restore-signing-key-fixture'
        thread.join(5);self.assertFalse(thread.is_alive());self.assertEqual(responses,[302])


if __name__=='__main__':unittest.main()
