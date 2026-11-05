"""Real local Unix socket + Flask UI; host/Docker executor remains simulated."""
import hashlib, io, json, os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from tests import test_v214_core as core
from tests.test_updater_agent import Executor, Releases
from updater_agent.engine import Engine
from updater_agent.security import Refused
from updater_agent.service import Service
from updater_client import request
from updater_agent.releases import unpack
from openfablab import __version__


class SocketUI(unittest.TestCase):
    def setUp(self):
        core.NewVersion.setUp(self)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        folder=Path(self.temp.name);self.sock=folder/'s';self.token=folder/'t'
        self.token.write_bytes(b'LOCAL_FICTIONAL_TOKEN_'*3);self.token.chmod(0o600)
        self.executor=Executor();self.engine=Engine(dict(state=str(folder/'agent'),enabled=True),Releases(),self.executor)
        self.service=Service(self.engine,self.token.read_bytes(),self.sock)
        self.thread=threading.Thread(target=self.service.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.service.server_close);self.addCleanup(self.service.shutdown)
        self.environment=patch.dict(os.environ,OPENFABLAB_UPDATE_SOCKET=str(self.sock),OPENFABLAB_UPDATE_TOKEN_FILE=str(self.token))
        self.environment.start();self.addCleanup(self.environment.stop)
    login=core.NewVersion.login
    def call(self,op,**args):return request(op,args,str(self.sock),str(self.token))
    def wait(self):
        deadline=time.monotonic()+5
        while self.service.worker and self.service.worker.is_alive() and time.monotonic()<deadline:
            self.service.worker.join(.05)
        self.assertFalse(self.service.worker.is_alive())
    def test_actual_ui_prepare_confirm_and_status_across_authenticated_socket(self):
        token=self.login()
        path='/admin/reglages/systeme/mises-a-jour'
        page=self.client.get(path)
        self.assertEqual(page.status_code,200)
        self.assertIn('updates.js',page.text)
        self.assertIn('V'+__version__,page.text)
        response=self.client.post(path,data=dict(operation='discover',evolution_csrf=token))
        self.assertEqual(response.json['value']['latest'],'2.15.1')
        self.assertTrue(self.client.post(path,data=dict(operation='prepare',evolution_csrf=token)).json['ok'])
        self.wait()
        value=self.client.post(path,data=dict(operation='status',evolution_csrf=token)).json['value']
        self.assertEqual(value['result'],'ready')
        self.assertNotIn('stop_source',self.executor.calls)
        response=self.client.post(path,data=dict(operation='install',id=value['id'],confirmation=value['confirmation'],consent='INSTALLER',evolution_csrf=token))
        self.assertTrue(response.json['ok']);self.wait()
        status=self.client.post(path,data=dict(operation='status',evolution_csrf=token)).json['value']
        self.assertEqual(status['result'],'success')
        self.assertNotIn('confirmation',status)
    def test_no_role_escalation_no_csrf_bypass_no_arbitrary_host_operation(self):
        path='/admin/reglages/systeme/mises-a-jour'
        self.assertNotEqual(self.client.get(path).status_code,200)
        self.login('moderator')
        self.assertNotEqual(self.client.get(path).status_code,200)
        with self.client.session_transaction() as session:
            session.clear()
        token=self.login()
        self.assertEqual(self.client.post(path,data=dict(operation='prepare')).status_code,400)
        self.assertEqual(self.client.post(path,data=dict(operation='shell',evolution_csrf=token)).status_code,400)
        for op,args in [('shell',{}),('prepare',dict(url='https://example.invalid/evil.zip')),('status',dict(path='/etc/passwd'))]:
            with self.assertRaises(Refused):self.call(op,**args)
        self.assertNotIn('stop_source',self.executor.calls)
    def test_authentication_failure_and_preparation_cancellation(self):
        original=self.token.read_bytes();self.token.write_bytes(b'WRONG_TOKEN'*4)
        with self.assertRaises(Refused):self.call('status')
        self.token.write_bytes(original)
        self.call('prepare');self.wait()
        value=self.call('status');self.assertEqual(value['result'],'ready')
        self.call('cancel',id=value['id'])
        self.assertEqual(self.call('status')['phase'],'cancelled')
        self.assertNotIn('stop_source',self.executor.calls)

    def test_removed_token_is_a_readable_refusal_not_an_application_error(self):
        token=self.login();self.token.unlink()
        response=self.client.post('/admin/reglages/systeme/mises-a-jour',data=dict(operation='status',evolution_csrf=token))
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json['code'],'AGENT_UNAVAILABLE_MANUAL_UPDATE_AVAILABLE')
        self.assertNotIn(str(self.temp.name),response.text)

    def zip_payload(self,version='2.15.1',schema=26,source=26,name='fictional.txt'):
        raw=io.BytesIO();content=b'fictional runtime'
        with ZipFile(raw,'w') as archive:
            archive.writestr(name,content)
            archive.writestr('UPDATE-MANIFEST.json',json.dumps(dict(format=1,version=version,schema=schema,agent_protocol=1,
                source_schemas=[source],migration='family_model.migrate',notes='Notes fictives',
                files={name:hashlib.sha256(content).hexdigest()})))
        return raw.getvalue()

    def upload_candidate(self,data,token):
        return self.client.post('/admin/reglages/systeme/mises-a-jour',
            data=dict(operation='prepare_zip',evolution_csrf=token,candidate=(io.BytesIO(data),'candidate.zip')))

    def test_zip_authenticated_preparation_then_same_schema_install(self):
        self.executor.unpack=unpack
        token=self.login()
        response=self.upload_candidate(self.zip_payload(),token)
        self.assertTrue(response.json['value']['accepted']);self.wait()
        value=self.call('status')
        self.assertEqual((value['result'],value['channel'],value['source_schema'],value['target_schema']),('ready','zip',26,26))
        self.assertTrue(value['isolated_probe_pending']);self.assertFalse(value['migration_required'])
        self.assertEqual(value['notes'],'Notes fictives')
        self.assertNotIn('build',self.executor.calls);self.assertNotIn('stop_source',self.executor.calls)
        self.call('install',id=value['id'],confirmation=value['confirmation']);self.wait()
        status=self.call('status')
        self.assertEqual(status['result'],'success');self.assertEqual(status['history'][0]['result'],'success')
        self.assertFalse(status['migration_attempted']);self.assertNotIn('migrate',self.executor.calls)
        for before,after in (('probe','stop_source'),('hot_backup','stop_source'),('cold_backup','start_target'),('health','post_backup')):
            self.assertLess(self.executor.calls.index(before),self.executor.calls.index(after))
        self.assertEqual(self.executor.writes,['FICTIONAL_BEFORE','FICTIONAL_AFTER_PUBLIC'])

    def test_local_invalid_archives_never_build_or_stop(self):
        self.executor.unpack=unpack
        token=self.login()
        for data,code in ((b'not a zip','LOCAL_ZIP_MALFORMED'),(self.zip_payload(version='2.15.0'),'LOCAL_ZIP_VERSION_NOT_NEWER'),
                (self.zip_payload(source=25),'SOURCE_SCHEMA_NOT_SUPPORTED'),(self.zip_payload(name='../unsafe'),'UPDATE_ARCHIVE_UNSAFE_PATH')):
            with self.subTest(code=code):
                self.assertTrue(self.upload_candidate(data,token).json['ok']);self.wait()
                status=self.call('status')
                self.assertEqual((status['result'],status['code']),('refused',code))
        self.assertNotIn('build',self.executor.calls);self.assertNotIn('stop_source',self.executor.calls)

    def test_upload_is_admin_only_and_requires_csrf_and_matching_digest(self):
        token=self.login('moderator')
        self.assertNotEqual(self.upload_candidate(self.zip_payload(),token).status_code,200)
        with self.client.session_transaction() as session:
            session.clear()
        token=self.login()
        self.assertNotEqual(self.upload_candidate(self.zip_payload(),'invalid').status_code,200)
        data=self.zip_payload()
        with self.assertRaisesRegex(Refused,'LOCAL_ZIP_INTEGRITY_FAILED'):
            request('prepare_zip',dict(size=len(data),sha256='0'*64),str(self.sock),str(self.token),stream=io.BytesIO(data))
        self.assertEqual(self.call('status')['phase'],'idle')

    def test_old_agent_refuses_new_wire_operation_without_side_effects(self):
        from updater_client import upload
        with patch('updater_client.request',return_value={'phase':'idle'}) as call:
            with self.assertRaisesRegex(Refused,'AGENT_ZIP_UPGRADE_REQUIRED'):
                upload(io.BytesIO(self.zip_payload()))
        self.assertEqual(call.call_args.args,('status',))

    def test_local_schema_migration_requires_consent_and_cold_backup(self):
        self.executor.unpack=unpack
        token=self.login()
        self.assertTrue(self.upload_candidate(self.zip_payload(schema=27),token).json['ok']);self.wait()
        state=self.call('status')
        self.assertTrue(state['migration_required'])
        self.assertNotIn('migrate',self.executor.calls)
        self.call('install',id=state['id'],confirmation=state['confirmation']);self.wait()
        self.assertEqual(self.call('status')['result'],'success')
        self.assertLess(self.executor.calls.index('cold_backup'),self.executor.calls.index('migrate'))

if __name__=='__main__':unittest.main()
