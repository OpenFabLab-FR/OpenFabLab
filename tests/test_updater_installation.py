"""Operator installation planning/refusals, no real daemon or host alteration."""
import copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack
from updater_agent.installation import channel_configuration,expected_launch,validate_layout,install,CHANNEL_TARGET
from updater_agent.security import Refused,private_json,pack
import hashlib

class Installation(unittest.TestCase):
    def test_only_local_channel_is_added_and_input_configuration_untouched(self):
        original=dict(name='fablab',services=dict(application=dict(image='approved',environment=dict(TZ='Europe/Paris'),
            volumes=[dict(type='bind',source='/example/data',target='/data')]),other=dict(image='untouched')))
        saved=copy.deepcopy(original);result=channel_configuration(original,'application','/example/agent-shared')
        self.assertEqual(original,saved);self.assertEqual(result['services']['other'],saved['services']['other'])
        app=result['services']['application'];self.assertEqual(app['image'],'approved');self.assertEqual(app['volumes'][0],saved['services']['application']['volumes'][0])
        self.assertEqual(app['volumes'][-1],dict(type='bind',source='/example/agent-shared',target=CHANNEL_TARGET,read_only=True,bind=dict(create_host_path=False)))
        self.assertEqual(set(app['environment'])-set(saved['services']['application']['environment']),{'OPENFABLAB_UPDATE_SOCKET','OPENFABLAB_UPDATE_TOKEN_FILE'})
        self.assertNotIn('/var/run/docker.sock',str(result))
    def test_existing_channels_and_socket_access_refused(self):
        source=dict(services=dict(application=dict(environment={},volumes=[])))
        first=channel_configuration(source,'application','/example/shared')
        with self.assertRaisesRegex(Refused,'ALREADY_CONFIGURED'):channel_configuration(first,'application','/example/shared')
        source['services']['application']['volumes']=[dict(target='/var/run/docker.sock')]
        with self.assertRaisesRegex(Refused,'MOUNT_CONFLICT'):channel_configuration(source,'application','/example/shared')
    def test_confirmation_is_checked_before_any_access_or_system_operation(self):
        for token in ('',None,'INSTALL','AUTHORIZE-LOCAL-AGENT-2.14.4'):
            with self.assertRaisesRegex(Refused,'EXPLICIT_CONFIRMATION'):
                install({},None,None,None,None,token)
    def test_production_folders_never_become_the_agent_shared_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ('project','data','backups'):(root/name).mkdir()
            policy=dict(project=str(root/'project'),data=str(root/'data'),backups=str(root/'backups'),state=str(root/'new-state'),
                socket=str(root/'new-shared/agent.sock'),token_file=str(root/'new-shared/token'),database=str(root/'data/openfablab.db'),compose_file=str(root/'project/compose.yaml'))
            validate_layout(policy)
            for name in ('project','data','backups'):
                changed=policy|dict(socket=str(root/name/'agent.sock'),token_file=str(root/name/'token'))
                with self.assertRaisesRegex(Refused,'INDEPENDENT'):validate_layout(changed)
            self.assertFalse((root/'new-state').exists());self.assertFalse((root/'new-shared').exists())

class InstallationFlow(unittest.TestCase):
    """Real private files/Compose replacement, modeled Docker/ACL/relay only."""
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for name in ('project','data','backups','state','shared','docker'):(self.root/name).mkdir(mode=0o700)
        self.folder=self.root/'state'/('1'*32);self.folder.mkdir()
        self.policy=dict(project=str(self.root/'project'),data=str(self.root/'data'),backups=str(self.root/'backups'),state=str(self.root/'state'),
            socket=str(self.root/'shared/agent.sock'),token_file=str(self.root/'shared/token'),web_gid=os.getgid(),docker='/not-a-real-docker',
            docker_root=str(self.root/'docker'),compose_file=str(self.root/'project/compose.json'),service='application')
        self.manifest=dict(version='2.15.0',schema=26,agent_protocol=1,runtime_files={'app.py':'a'*64})
        self.image='sha256:'+'1'*64;self.agent='sha256:'+'2'*64
        configuration=dict(name='fablab',services=dict(application=dict(image=self.image,environment=dict(TZ='Europe/Paris'),volumes=[])))
        Path(self.policy['compose_file']).write_bytes(pack(configuration));self.configuration=configuration
        self.calls=[];self.fault=None
        owner=self
        class Executor:
            project=owner.root/'project';data=owner.root/'data';backups=owner.root/'backups';database=data/'openfablab.db'
            policy=owner.policy
            def container(self):return dict(Id='c'*64,Image=owner.image,Config=dict(Env=['TZ=Europe/Paris']),Mounts=[])
            def compose(self,arguments,replacement=None):
                owner.calls.append('compose:'+arguments[0])
                if arguments[0]=='config':return Path(replacement or owner.policy['compose_file']).read_bytes()
                if owner.fault=='restart':raise Refused('FICTIONAL_RESTART_FAILED')
                return b''
            def helper(self,operation,output,**kwargs):
                owner.calls.append('helper:'+operation)
                if '--destination' in kwargs.get('extra',[]):
                    values=kwargs['extra'];destination=Path(values[values.index('--destination')+1]);destination.mkdir()
                    (destination/'verified-restoration.txt').write_text('FICTIONAL_BACKUP_TEST')
                private_json(output,dict(success=True));return dict(success=True)
            def run(self,arguments,**kwargs):
                owner.calls.append('docker:'+arguments[0])
                if arguments[:2]==['image','save']:Path(arguments[arguments.index('--output')+1]).write_bytes(b'FICTIONAL_IMAGE_ARCHIVE')
                if arguments[0]=='inspect':return pack([dict(State=dict(Running=False))])
                return b''
            def configuration_hash(self):return hashlib.sha256(Path(owner.policy['compose_file']).read_bytes()).hexdigest()
            def launch_hash(self,item):return 'FICTIONAL_EXPECTED_LAUNCH'
            def health(self,job):owner.calls.append('http-health')
            def enroll(self,manifest):
                owner.calls.append('enroll');private_json(owner.root/'state/current.json',dict(version='2.15.0',schema=26))
        self.executor=Executor()
        private_json(self.root/'state/prepared-agent.json',dict(image=self.agent,source_image=self.image,manifest_sha256=hashlib.sha256(pack(self.manifest)).hexdigest()))

    def patches(self):
        stack=ExitStack()
        # The test runs as a normal Mac user, so no fake ownership is applied
        # outside these temporary directories. Production validation is intact.
        for target,value in (
            ('updater_agent.installation.check',dict(success=True)),('updater_agent.installation.load_policy',self.policy),
            ('updater_agent.relay_check.check',dict(success=True)),('updater_client.request',dict(value=dict(phase='idle')))):
            stack.enter_context(patch(target,return_value=value))
        stack.enter_context(patch('updater_agent.installation.os.chown'))
        # Do not mock pathlib globally; use temporary files' actual owner as
        # installation's root owner for the protected directory check only.
        stack.enter_context(patch('updater_agent.installation.DockerExecutor',return_value=self.executor))
        return stack

    def execute(self):
        # Root-directory check is a distinct unit test. The real flow below
        # uses a temporary path adapter, never escalates or chowns host paths.
        original=Path.stat
        def information(path,*args,**kwargs):
            value=original(path,*args,**kwargs)
            if path in (self.root/'state',self.root/'shared'):
                fields=list(value);fields[4]=0;return os.stat_result(fields)
            return value
        with self.patches(),patch.object(Path,'stat',information):
            return install(self.policy,self.manifest,self.executor,self.folder,self.agent,'AUTHORIZE-LOCAL-AGENT-2.15.0')

    def test_channel_installation_keeps_image_and_data_and_has_verified_pre_post_boundaries(self):
        sentinel=self.root/'data/private.fixture';sentinel.write_bytes(b'FICTITIOUS_PRIVATE_CONFIGURATION')
        result=self.execute();self.assertTrue(result['success'])
        after=json.loads(Path(self.policy['compose_file']).read_bytes())
        self.assertEqual(after,channel_configuration(self.configuration,'application',str(self.root/'shared')))
        self.assertEqual(sentinel.read_bytes(),b'FICTITIOUS_PRIVATE_CONFIGURATION')
        self.assertEqual((self.root/'shared/token').stat().st_mode & 0o777,0o640)
        self.assertLess(self.calls.index('helper:backup'),self.calls.index('docker:stop'))
        self.assertLess(self.calls.index('http-health'),self.calls.index('enroll'))
        self.assertEqual(self.calls.count('helper:compare-live'),2)
        self.assertEqual(self.calls.count('helper:backup'),2)
        self.assertNotIn('helper:migrate',self.calls)
        self.assertEqual(json.loads((self.root/'state/agent-installation.json').read_bytes())['result'],'AGENT_INSTALLATION_SUCCESS')

    def test_failure_after_stop_preserves_current_files_and_never_restores_database(self):
        self.fault='restart';sentinel=self.root/'data/new-write.fixture';sentinel.write_bytes(b'NEW_WRITE_MUST_SURVIVE')
        with self.assertRaisesRegex(Refused,'RESTART_FAILED'):self.execute()
        receipt=json.loads((self.root/'state/agent-installation.json').read_bytes())
        self.assertTrue(receipt['production_stop_attempted']);self.assertTrue(receipt['public_restart_attempted'])
        self.assertFalse(receipt['automatic_restore']);self.assertEqual(receipt['phase'],'failed_preserved')
        self.assertEqual(sentinel.read_bytes(),b'NEW_WRITE_MUST_SURVIVE')
        self.assertNotIn('enroll',self.calls);self.assertNotIn('helper:migrate',self.calls)
        self.assertNotIn('helper:restore',self.calls)

    def test_different_prepared_image_refused_before_any_write_or_stop(self):
        private_json(self.root/'state/prepared-agent.json',dict(image='sha256:'+'3'*64,source_image=self.image,manifest_sha256='a'*64))
        with self.assertRaisesRegex(Refused,'PREPARATION_IDENTITY_CHANGED'):self.execute()
        self.assertFalse((self.root/'shared/token').exists());self.assertEqual(self.calls,[])

if __name__=='__main__':unittest.main()
