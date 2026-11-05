"""Real agent state machine with a fault-injected executor, never a DSM claim."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile
from updater_agent.engine import Engine
from updater_agent.releases import OfficialReleases, REPO, unpack, safe_url
from updater_agent.security import Authentication, Refused


class Releases:
    def latest(self):
        return dict(version='2.15.1',notes='Version fictive',page='https://example.invalid')
    def download(self, release, destination):
        return destination

class OfficialDiscovery(unittest.TestCase):
    def test_fixed_repository_stable_tag_asset_and_digest(self):
        origin='https://api.github.com/repos/'+REPO
        archive='https://github.com/'+REPO+'/releases/download/v2.15.2/OpenFabLab-2.15.2.zip'
        response={origin:dict(id=42,full_name=REPO,private=False),
            origin+'/releases/latest':dict(id=1,tag_name='v2.15.2',draft=False,prerelease=False,body='Notes de test',
                assets=[dict(name='OpenFabLab-2.15.2.zip',size=123,id=2,digest='sha256:'+'a'*64,browser_download_url=archive)]),
            origin+'/git/ref/tags/v2.15.2':dict(object=dict(type='tag',sha='b'*40)),
            origin+'/git/tags/'+'b'*40:dict(object=dict(type='commit',sha='c'*40))}
        provider=OfficialReleases(42)
        provider.read=lambda url,_:json.dumps(response[url]).encode()
        self.assertEqual((provider.latest()['version'],provider.latest()['commit']),('2.15.2','c'*40))
        for flag in ('prerelease','draft'):
            response[origin+'/releases/latest'][flag]=True
            with self.assertRaisesRegex(Refused,'OFFICIAL_RELEASE_NOT_STABLE'):provider.latest()
            response[origin+'/releases/latest'][flag]=False
        response[origin]['id']=43
        with self.assertRaisesRegex(Refused,'OFFICIAL_REPOSITORY_IDENTITY_CHANGED'):provider.latest()


class Executor:
    def __init__(self):
        self.calls=[]
        self.failure=None
        self.interruption=None
        self.stopped=False
        self.schema=26
        self.writes=['FICTIONAL_BEFORE']
    def call(self, step):
        self.calls.append(step)
        if self.interruption==step:
            raise KeyboardInterrupt()
        if self.failure==step:
            raise Refused('FICTIONAL_'+step.upper())
    def inspect(self):
        self.call('inspect');return dict(version='2.15.0',schema=26,runtime='fictional',image='fictional')
    def unpack(self, *args):
        self.call('unpack');return dict(source_schemas=[26],schema=27)
    def preflight(self, job):self.call('preflight')
    def build(self, job):self.call('build');return {'image':'fictional-built'}
    def probe(self, job):self.call('probe')
    def verify_source(self, job):self.call('verify_source')
    def hot_backup(self, job):self.call('hot_backup')
    def stop_source(self, job):self.call('stop_source');self.stopped=True
    def cold_backup(self, job):self.call('cold_backup');return 'FICTIONAL_PRE26'
    def migrate(self, job):self.call('migrate');self.schema=27
    def verify_migration(self, job):self.call('verify_migration')
    def install_runtime(self, job):self.call('install_runtime')
    def start_target(self, job):self.call('start_target');self.stopped=False;self.writes.append('FICTIONAL_AFTER_PUBLIC')
    def health(self, job):self.call('health')
    def verify_live(self, job):self.call('verify_live')
    def relay(self, job):self.call('relay')
    def post_backup(self, job):self.call('post_backup');return 'FICTIONAL_POST27'
    def stop_target(self, job):self.call('stop_target');self.stopped=True
    def preserve(self, job):self.call('preserve')
    def recovery_check(self, job):
        self.call('recovery_check');return dict(can_resume_target=self.schema==27)


class Agent(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.executor=Executor()
        self.engine=Engine(dict(state=self.temp.name,enabled=True),Releases(),self.executor)
    def ready(self):return self.engine.prepare()
    def test_prepare_does_not_stop_or_migrate_and_has_no_secrets(self):
        value=self.ready()
        self.assertEqual(value['phase'],'ready')
        self.assertNotIn('stop_source',self.executor.calls)
        self.assertNotIn('migrate',self.executor.calls)
        self.assertNotIn('confirmation_hash',self.engine.status())
        self.assertNotIn('source',self.engine.status())
    def test_complete_sequence_and_confirmation_replay_refused(self):
        value=self.ready()
        result=self.engine.install(value['id'],value['confirmation'])
        self.assertEqual(result['result'],'success')
        self.assertEqual(self.executor.schema,27)
        self.assertLess(self.executor.calls.index('build'),self.executor.calls.index('stop_source'))
        self.assertLess(self.executor.calls.index('cold_backup'),self.executor.calls.index('migrate'))
        with self.assertRaises(Refused):self.engine.install(value['id'],value['confirmation'])
    def test_bad_confirmation_and_disabled_agent_refused(self):
        value=self.ready()
        with self.assertRaises(Refused):self.engine.install(value['id'],'wrong')
        self.engine.policy['enabled']=False
        with self.assertRaises(Refused):self.engine.install(value['id'],value['confirmation'])
        self.assertNotIn('stop_source',self.executor.calls)
    def test_preparation_failures_preserve_running_source(self):
        for phase in ('inspect','unpack','preflight','build','probe','verify_source'):
            with self.subTest(phase=phase):
                self.executor.failure=phase
                with self.assertRaises(Refused):self.ready()
                self.assertEqual(self.engine.status()['result'],'refused')
                self.assertFalse(self.engine.status()['production_stop_attempted'])
        self.assertNotIn('stop_source',self.executor.calls)
    def test_hot_backup_failure_happens_before_stop(self):
        value=self.ready();self.executor.failure='hot_backup'
        result=self.engine.install(value['id'],value['confirmation'])
        self.assertEqual(result['result'],'refused')
        self.assertNotIn('stop_source',self.executor.calls)
    def test_source_changed_during_hot_backup_refused_before_stop(self):
        value=self.ready()
        def changed(job):
            self.executor.call('hot_backup');self.executor.failure='verify_source'
        self.executor.hot_backup=changed
        result=self.engine.install(value['id'],value['confirmation'])
        self.assertEqual(result['result'],'refused');self.assertFalse(result['production_stop_attempted'])
        self.assertNotIn('stop_source',self.executor.calls);self.assertNotIn('migrate',self.executor.calls)
    def test_failures_after_stop_always_preserve_no_restore_or_remigrate(self):
        for phase in ('cold_backup','migrate','verify_migration','install_runtime','start_target','health','verify_live','relay','post_backup'):
            with self.subTest(phase=phase),tempfile.TemporaryDirectory() as folder:
                executor=Executor();engine=Engine(dict(state=folder,enabled=True),Releases(),executor)
                value=engine.prepare();executor.failure=phase
                result=engine.install(value['id'],value['confirmation'])
                self.assertEqual(result['result'],'failed_preserved')
                self.assertTrue(result['recovery_required'])
                self.assertIn('preserve',executor.calls)
                self.assertFalse(any('restore' in c for c in executor.calls))
                with self.assertRaises(Refused):engine.prepare()
    def test_public_writes_survive_failure_and_independent_resume(self):
        value=self.ready();self.executor.failure='relay'
        self.engine.install(value['id'],value['confirmation'])
        self.assertIn('FICTIONAL_AFTER_PUBLIC',self.executor.writes)
        self.assertTrue(self.executor.stopped)
        check=self.engine.recovery_diagnostic(value['id'])
        self.assertTrue(check['diagnostic']['can_resume_target'])
        self.executor.failure=None
        self.assertEqual(self.engine.resume(value['id'],'RESUME-'+value['id'])['result'],'success')
        self.assertEqual(self.executor.calls.count('migrate'),1)
        self.assertIn('FICTIONAL_AFTER_PUBLIC',self.executor.writes)
    def test_killed_process_requires_human_recovery_even_new_engine(self):
        value=self.ready();self.executor.interruption='migrate'
        with self.assertRaises(KeyboardInterrupt):self.engine.install(value['id'],value['confirmation'])
        restarted=Engine(self.engine.policy,Releases(),self.executor)
        with self.assertRaises(Refused):restarted.prepare()
        self.assertTrue(restarted.status()['migration_attempted'])
        with self.assertRaises(Refused):restarted.resume(value['id'],'RESUME-'+value['id'])
    def test_ready_job_blocks_competing_update_and_paths_are_not_job_ids(self):
        self.ready()
        with self.assertRaises(Refused):self.ready()
        for key in ('../job','/etc/passwd',';whoami',None):
            with self.assertRaises(Refused):self.engine.status(key if key is not None else '../')


class AuthenticationTests(unittest.TestCase):
    def test_tamper_replay_wrong_token_expiration(self):
        auth=Authentication(b'F'*32);value=auth.sign('status',{},1000)
        self.assertEqual(auth.verify(value,1000),('status',{}))
        with self.assertRaises(Refused):auth.verify(value,1000)
        with self.assertRaises(Refused):Authentication(b'G'*32).verify(auth.sign('status',{},1000),1000)
        with self.assertRaises(Refused):auth.verify(auth.sign('status',{},1000),1100)
        value=auth.sign('status',{},1000);value['operation']='shell'
        with self.assertRaises(Refused):auth.verify(value,1000)


class Archives(unittest.TestCase):
    def test_public_dot_examples_allowed_but_real_env_still_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'application.zip'
            files={'.env.example':b'EXAMPLE_ONLY=', '.dockerignore':b'data\n','app.py':b'fictional'}
            manifest=dict(format=1,version='2.15.1',agent_protocol=1,schema=27,source_schemas=[26],migration='family_model.migrate',
                files={name:hashlib.sha256(value).hexdigest() for name,value in files.items()})
            with ZipFile(path,'w') as archive:
                for name,value in files.items():archive.writestr(name,value)
                archive.writestr('UPDATE-MANIFEST.json',json.dumps(manifest))
            self.assertEqual(unpack(path,root/'safe','2.15.1')['schema'],27)
            self.assertTrue((root/'safe/.env.example').is_file())

    def test_official_urls_never_accept_http_credentials_or_private_host(self):
        self.assertEqual(safe_url('https://api.github.com/repos/OpenFabLab-FR/OpenFabLab'),'https://api.github.com/repos/OpenFabLab-FR/OpenFabLab')
        for url in ('http://github.com/a','https://localhost/a','https://github.com.evil.invalid','https://user:secret@github.com/a','https://github.com:444/a'):
            with self.assertRaises(Refused):safe_url(url)
    def test_exact_manifested_files_and_unsafe_archives_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'application.zip'
            manifest=dict(format=1,version='2.15.1',agent_protocol=1,schema=27,source_schemas=[26],
                          migration='family_model.migrate',files={'app.py':hashlib.sha256(b'fictional').hexdigest()})
            with ZipFile(path,'w') as z:
                z.writestr('OpenFabLab/app.py',b'fictional')
                z.writestr('OpenFabLab/UPDATE-MANIFEST.json',json.dumps(manifest))
            self.assertEqual(unpack(path,root/'safe','2.15.1')['schema'],27)
            self.assertEqual((root/'safe/app.py').read_bytes(),b'fictional')
            for extra in ('../secret','OpenFabLab/.env','OpenFabLab/unknown'):
                with ZipFile(path,'w') as z:
                    z.writestr('OpenFabLab/app.py',b'fictional');z.writestr(extra,b'SECRET_FICTIF')
                    z.writestr('OpenFabLab/UPDATE-MANIFEST.json',json.dumps(manifest))
                with self.assertRaises(Refused):unpack(path,root/'refused','2.15.1')
                self.assertFalse((root/'refused').exists())
