"""Docker is modeled, commands/policies are real Python; no production daemon."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch,Mock
from updater_agent.docker_executor import DockerExecutor,bounded_process
from updater_agent.releases import OfficialReleases,REPO
from updater_agent.security import Refused,load_policy,private_json
from updater_agent import relay_check
from updater_agent.compose_image import proposal,equivalent
from tests import test_v214_core as core
from app import write_setting
from reservations_sync import save_sync_secret

IMAGE='sha256:'+'a'*64
OTHER='sha256:'+'b'*64
CONTAINER='c'*64

class Docker(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for key in ('project','data','backups','state','shared','docker-root'):(self.root/key).mkdir(mode=0o700)
        self.policy=dict(protocol=1,project=str(self.root/'project'),data=str(self.root/'data'),backups=str(self.root/'backups'),
            state=str(self.root/'state'),docker_root=str(self.root/'docker-root'),compose_file=str(self.root/'project/custom-compose.yml'),
            database=str(self.root/'data/openfablab.db'),socket=str(self.root/'shared/agent.sock'),token_file=str(self.root/'shared/token'),
            docker='/bin/true',service='openfablab',enabled=True,repository_id=123,web_gid=os.getgid())
        Path(self.policy['compose_file']).write_text('services: {}\n');Path(self.policy['database']).touch()
        (self.root/'data/.openfablab-state.lock').touch()
        (self.root/'project/app.py').write_bytes(b'FICTIONAL_RUNTIME')
        self.files={'app.py':hashlib.sha256(b'FICTIONAL_RUNTIME').hexdigest()}
        self.item=dict(Id=CONTAINER,Image=IMAGE,State=dict(Status='running',Running=True),
            Config=dict(Cmd=['gunicorn'],Entrypoint=None,Env=['TZ=Europe/Paris','PYTHON_VERSION=3.12.1'],User='',WorkingDir='/app',
                Labels={'com.docker.compose.service':'openfablab','com.docker.compose.project.working_dir':self.policy['project']}),
            HostConfig=dict(Privileged=False,NetworkMode='bridge',RestartPolicy={'Name':'unless-stopped'}),
            Mounts=[dict(Type='bind',Source=self.policy['data'],Destination='/data',RW=True)])
        self.executor=DockerExecutor(self.policy,IMAGE)
        self.receipt=dict(version='2.14.4',schema=25,image=IMAGE,files=self.files,
            launch_sha256=self.executor.launch_hash(self.item),configuration_sha256=self.executor.configuration_hash())
        private_json(self.root/'state/current.json',self.receipt)

    def test_policy_layout_owner_and_no_symlinks(self):
        policy=self.root/'policy.json';private_json(policy,self.policy)
        self.assertEqual(load_policy(policy,owner=os.getuid())['service'],'openfablab')
        policy.chmod(0o666)
        with self.assertRaisesRegex(Refused,'OWNERSHIP'):load_policy(policy,owner=os.getuid())
        policy.chmod(0o600)
        for field,value in [('data',str(self.root/'state')),('backups',str(self.root)),('database',str(self.root/'data/unknown.db')),('socket',str(self.root/'state/sock'))]:
            with self.subTest(field=field):
                private_json(policy,self.policy|{field:value})
                with self.assertRaises(Refused):load_policy(policy,owner=os.getuid())
        (self.root/'link').symlink_to(self.root/'data');private_json(policy,self.policy|{'data':str(self.root/'link')})
        with self.assertRaisesRegex(Refused,'SYMLINK'):load_policy(policy,owner=os.getuid())

    def test_mount_order_is_irrelevant_but_actual_configuration_is_not(self):
        self.item['Mounts'].append(dict(Type='bind',Source='/example/read-only',Destination='/example',RW=False))
        original=self.executor.launch_hash(self.item)
        self.item['Mounts'].reverse();self.assertEqual(self.executor.launch_hash(self.item),original)
        self.item['Config']['Env'].append('PYTHON_VERSION=3.12.2')
        self.assertEqual(self.executor.launch_hash(self.item),original)
        self.item['Config']['Env'].append('OPENFABLAB_DATABASE=/unexpected.db')
        self.assertNotEqual(self.executor.launch_hash(self.item),original)

    def test_image_active_container_and_storage_checked_independently(self):
        with patch.object(self.executor,'container',return_value=self.item),patch.object(self.executor,'runtime_hashes') as hashes,patch.object(self.executor,'helper'):
            self.executor.inspect()
            self.assertEqual(hashes.call_args_list[0].args[0],CONTAINER)
            self.assertEqual(hashes.call_args_list[1].args[0],IMAGE)
            (self.root/'project/app.py').write_bytes(b'DIVERGENCE')
            with self.assertRaisesRegex(Refused,'STORAGE'):self.executor.inspect()
        for active in (True,False):
            with patch.object(self.executor,'run',return_value=b'{"app.py":"mismatch"}'):
                with self.assertRaisesRegex(Refused,'ACTIVE' if active else 'IMAGE'):
                    self.executor.runtime_hashes(CONTAINER if active else IMAGE,self.files,active=active)

    def test_wrong_data_mount_privileged_web_and_docker_socket_refused(self):
        for mutation in ('mount','privilege','socket'):
            item=json.loads(json.dumps(self.item))
            if mutation=='mount':item['Mounts'][0]['Source']='/incorrect/data'
            elif mutation=='privilege':item['HostConfig']['Privileged']=True
            else:item['Mounts'].append(dict(Type='bind',Source='/var/run/docker.sock',Destination='/var/run/docker.sock',RW=True))
            receipt=self.receipt|{'launch_sha256':self.executor.launch_hash(item)};private_json(self.root/'state/current.json',receipt)
            with patch.object(self.executor,'container',return_value=item):
                with self.assertRaisesRegex(Refused,'DATA_VOLUME|PRIVILEGES'):self.executor.inspect()

    def test_effective_write_probes_only_at_install_and_space_failure_before_stop(self):
        job=dict(id='1'*32,source=dict(image=IMAGE),result='preparing')
        with patch.object(self.executor,'run',return_value=b'[{"Size":1000000}]'),patch.object(self.executor,'compose'),patch('updater_agent.docker_executor.shutil.disk_usage',return_value=Mock(free=10**13)),patch('updater_agent.docker_executor.write_probe') as probe:
            self.executor.preflight(job);probe.assert_not_called()
            self.executor.preflight(job|{'result':'installing'});self.assertEqual(probe.call_count,4)
            probe.side_effect=Refused('WRITE_PREFLIGHT_ACCESS_REFUSED')
            with self.assertRaisesRegex(Refused,'ACCESS_REFUSED'):self.executor.preflight(job|{'result':'installing'})
        with patch.object(self.executor,'run',return_value=b'[{"Size":1000000}]'),patch('updater_agent.docker_executor.shutil.disk_usage',return_value=Mock(free=100)):
            with self.assertRaisesRegex(Refused,'SPACE'):self.executor.preflight(job)

    def test_docker_failure_classified_without_printing_raw_secret_on_either_stream(self):
        secret=b'https://example.invalid/?token=FICTIONAL_SECRET\n'
        for stdout,stderr in ((secret+b'max depth exceeded',b''),(b'',secret+b'no space left on device')):
            result=subprocess.CompletedProcess([],1,stdout,stderr)
            with patch('updater_agent.docker_executor.bounded_process',return_value=result),self.assertRaises(Refused) as error:self.executor.run(['build','fictional'])
            self.assertNotIn('SECRET',str(error.exception));self.assertIn(error.exception.code,('MAX_LAYER_DEPTH','INSUFFICIENT_SPACE'))

    def test_real_process_drains_both_streams_and_bounds_output(self):
        result=bounded_process([sys.executable,'-c','import sys;sys.stdout.write("FICTIONAL_OUT");sys.stderr.write("FICTIONAL_ERR")'],os.environ,None,5)
        self.assertEqual(result.stdout,b'FICTIONAL_OUT');self.assertEqual(result.stderr,b'FICTIONAL_ERR')
        with self.assertRaisesRegex(Refused,'TOO_LARGE'):
            bounded_process([sys.executable,'-c','import sys;sys.stdout.write("x"*18000000)'],os.environ,None,5)

    def test_helper_production_mounts_read_only_and_network_disabled(self):
        output=self.root/'state/inspection.json';private_json(output,{'success':True})
        with patch.object(self.executor,'run',return_value=b'') as run:self.executor.helper('snapshot',output)
        command=run.call_args.args[0]
        self.assertIn('--read-only',command);self.assertIn('none',command)
        mounts=[command[i+1] for i,v in enumerate(command) if v=='--mount']
        self.assertTrue(all('readonly' in m for m in mounts if self.policy['project'] in m or self.policy['data'] in m or self.policy['backups'] in m))

class Official(unittest.TestCase):
    def setUp(self):
        self.service=OfficialReleases(123)
        self.url='https://api.github.com/repos/'+REPO
        self.release=dict(tag_name='v2.15.1',id=5,draft=False,prerelease=False,body='Fictitious release',assets=[dict(name='OpenFabLab-2.15.1.zip',id=6,size=10,digest='sha256:'+'a'*64,browser_download_url='https://github.com/'+REPO+'/releases/download/v2.15.1/OpenFabLab-2.15.1.zip')])
    def read(self,url,maximum):
        data={self.url:dict(id=123,full_name=REPO,private=False),self.url+'/releases/latest':self.release,
            self.url+'/git/ref/tags/v2.15.1':dict(object=dict(type='tag',sha='b'*40)),
            self.url+'/git/tags/'+'b'*40:dict(object=dict(type='commit',sha='c'*40))}
        return json.dumps(data[url]).encode()
    def test_repository_annotated_tag_commit_and_asset_identity(self):
        with patch.object(self.service,'read',side_effect=self.read):
            value=self.service.latest();self.assertEqual(value['commit'],'c'*40)
            self.release['assets'][0]['browser_download_url']='https://github.com/another/repo/file.zip'
            with self.assertRaisesRegex(Refused,'LOCATION'):self.service.latest()
    def test_missing_digest_prerelease_and_wrong_repository_are_refused(self):
        with patch.object(self.service,'read',side_effect=self.read):
            self.release['prerelease']=True
            with self.assertRaisesRegex(Refused,'STABLE'):self.service.latest()
            self.release['prerelease']=False;self.release['assets'][0]['digest']=''
            with self.assertRaisesRegex(Refused,'DIGEST'):self.service.latest()
            self.service.repository_id=999
            with self.assertRaisesRegex(Refused,'IDENTITY'):self.service.latest()

class ComposeImage(unittest.TestCase):
    def test_changes_one_service_image_and_preserves_comments_and_other_fields(self):
        raw=b'# Operator notes\nservices:\n  openfablab:\n    image: old:image # current image\n    environment:\n      TZ: Europe/Paris\n  unrelated:\n    image: other:image\n'
        changed=proposal(raw,'openfablab',OTHER)
        self.assertIn(b'# Operator notes',changed);self.assertIn(b'# current image',changed)
        self.assertIn(b'image: other:image',changed);self.assertIn(OTHER.encode(),changed)
        self.assertEqual(changed.count(OTHER.encode()),1)
        before=dict(services=dict(openfablab=dict(image='old:image',environment=dict(TZ='Europe/Paris'))))
        equivalent(before,dict(services=dict(openfablab=dict(image=OTHER,environment=dict(TZ='Europe/Paris')))),'openfablab',OTHER)
        with self.assertRaisesRegex(Refused,'OTHER_CONFIGURATION'):
            equivalent(before,dict(services=dict(openfablab=dict(image=OTHER,environment=dict(TZ='UTC')))),'openfablab',OTHER)
    def test_complex_yaml_is_refused_instead_of_guessed_and_json_supported(self):
        for raw in (b'services: {openfablab: {image: old}}',b'services:\n  openfablab: *alias\n',b'services:\n  openfablab:\n    image: old\n    image: duplicate\n'):
            with self.assertRaises(Refused):proposal(raw,'openfablab',OTHER)
        raw=json.dumps(dict(services=dict(openfablab=dict(image='old',ports=['123:8000'])))).encode()
        changed=json.loads(proposal(raw,'openfablab',OTHER))
        self.assertEqual(changed['services']['openfablab'],dict(image=OTHER,ports=['123:8000']))

class Relay(unittest.TestCase):
    setUp=core.NewVersion.setUp
    def configured(self):
        for key,value in [('module_public_reservations','1'),('module_activities','1'),('reservation_wordpress_url','https://wordpress.example.invalid')]:write_setting(self.db,key,value)
        for env in ('production','test'):
            self.db.execute('INSERT INTO wordpress_relay_state(environment,catalogue_count,last_error) VALUES(?,2,NULL) ON CONFLICT(environment) DO UPDATE SET catalogue_count=2,last_error=NULL',(env,))
        self.db.commit();save_sync_secret(self.path,'FICTITIOUS_SYNC_SECRET_'*3)
    def test_normal_test_read_only_capabilities_never_business_actions(self):
        self.configured();calls=[]
        class Client:
            def post(self,route,payload):
                calls.append((route,payload));return dict(protocol_version=4,relay_revision=3,outbound_actions_v1=True,
                    relay_state=dict(environment=payload['environment'],catalogue_at=1000,polled_at=1000,animations=2,queue=dict(pending=0,processing=0)))
        before=self.db.total_changes
        value=relay_check.check(self.path,Path(self.path).parent,started=990,clock=lambda:1010,client_factory=lambda *_:Client())
        self.assertTrue(value['success']);self.assertEqual(self.db.total_changes,before)
        self.assertEqual([v[1]['environment'] for v in calls],['production','test'])
        self.assertTrue(all(v[0]=='/sync/capabilities' for v in calls))
    def test_disabled_optional_service_not_a_false_alarm(self):
        write_setting(self.db,'module_public_reservations','0');self.db.commit()
        self.assertIn('NOT_APPLICABLE',relay_check.check(self.path,Path(self.path).parent)['status'])
    def test_stale_test_environment_remains_a_refusal(self):
        self.configured()
        class Client:
            def post(self,route,payload):return dict(protocol_version=4,relay_revision=3,outbound_actions_v1=True,
                relay_state=dict(environment=payload['environment'],catalogue_at=1000 if payload['environment']=='production' else 1,polled_at=1000,animations=2,queue=dict(pending=0,processing=0)))
        with self.assertRaisesRegex(Refused,'TEST_EXCHANGE'):
            relay_check.check(self.path,Path(self.path).parent,clock=lambda:1010,client_factory=lambda *_:Client())

if __name__=='__main__':unittest.main()
