"""Fictitious UI-driven upgrade with real workers, SQLite, backups and runtime.

Only the Docker daemon is modeled. No network, NAS, real release or email is used.
"""
import hashlib,io,json,os,shlex,shutil,sqlite3,subprocess,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile,ZIP_DEFLATED
from tests import test_v214_core as core
from updater_agent.docker_executor import DockerExecutor,HASH_SCRIPT,HEALTH_SCRIPT,WORKER_LAUNCHER
from updater_agent.engine import Engine
from updater_agent.service import Service
from updater_agent.security import Refused,pack,private_json
from updater_agent.filesystem import coherent_copy,sha
from updater_agent.data_checks import snapshot

SOURCE=Path(__file__).resolve().parents[1]
OLD='sha256:'+'1'*64;NEW='sha256:'+'2'*64

def runtime_files():
    result={}
    for line in (SOURCE/'Dockerfile').read_text().splitlines():
        if not line.startswith('COPY '):continue
        for name in shlex.split(line)[1:-1]:
            origin=SOURCE/name
            for path in ([origin] if origin.is_file() else origin.rglob('*')):
                if path.is_file() and not path.name.startswith('.') and '__pycache__' not in path.parts:
                    result[path.relative_to(SOURCE).as_posix()]=path.read_bytes()
    return result

class LocalDocker(DockerExecutor):
    def __init__(self,policy,current):
        super().__init__(policy,OLD);self.current=current;self.images={OLD:self.project}
        self.calls=[];self.failure=None;self.target_runtime=None

    def compose(self,arguments,override=None,replacement=None):
        self.calls.append('compose:'+arguments[0])
        if arguments[0]=='version':return b'FICTIONAL_COMPOSE'
        if arguments[0]=='config':return Path(replacement or self.policy['compose_file']).read_bytes()
        if arguments[0]=='ps':return self.current['Id'].encode()
        if arguments[0]=='up':
            self.current['Id']='d'*64;self.current['Image']=NEW
            self.current['State']=dict(Status='running',Running=True)
            # Model a legitimate new business write after public reopening.
            with sqlite3.connect(self.database) as db:
                db.execute("INSERT INTO visitors(created_at) VALUES('2030-01-01T10:00:00+00:00')")
            return b'FICTIONAL_CONTAINER_STARTED'
        raise AssertionError('Unexpected Compose command')

    def run(self,arguments,*,payload=None,timeout=120):
        self.calls.append(arguments[0])
        if arguments[:2]==['image','inspect']:
            return pack([dict(Id=NEW if arguments[2].startswith('openfablab:agent-') else arguments[2],Size=1000000,RootFS=dict(Layers=['fictional']*20))])
        if arguments[:2]==['image','save']:
            Path(arguments[arguments.index('--output')+1]).write_bytes(b'FICTIONAL_IMAGE_NOT_A_REAL_DOCKER_ARCHIVE');return b''
        if arguments[0]=='inspect':return pack([self.current])
        if arguments[0]=='stop':self.current['State']=dict(Status='exited',Running=False);return b''
        if arguments[0]=='build':
            self.images[NEW]=Path(arguments[-1])/'runtime';self.target_runtime=self.images[NEW];return b'FICTIONAL_BUILD_ONLY'
        if HASH_SCRIPT in arguments:
            root=self.project if arguments[0]=='exec' else self.images[arguments[arguments.index('-c')-1]]
            return pack({name:sha(root/name) for name in json.loads(payload)})
        if WORKER_LAUNCHER in arguments:
            index=arguments.index(WORKER_LAUNCHER)
            self.calls.append('worker:'+arguments[index+1])
            # The bind to /update-runtime is represented by the exact private
            # staging directory on this test host; worker bytes are unchanged.
            values=[str(self.target_runtime.parent.parent/'runtime') if v=='/update-runtime' else v for v in arguments[index+1:]]
            return self.python(['-c',WORKER_LAUNCHER,*values],payload,timeout)
        if HEALTH_SCRIPT in arguments:
            script="import sys;sys.addaudithook(lambda event,args: (_ for _ in ()).throw(OSError('ISOLATED_NETWORK_DENIED')) if event in ('socket.connect','socket.sendto','socket.getaddrinfo') else None);import app;assert app.app.config['APP_VERSION']=='V2.15.1';r=app.app.test_client().get('/sante');assert r.status_code==200 and r.data==b'OK\\n';print('HEALTH_OK')"
            return self.python(['-c',script],None,30,runtime=self.target_runtime)
        raise AssertionError('Unexpected Docker command: '+str(arguments[:2]))

    def python(self,arguments,payload,timeout,runtime=None):
        environment=os.environ|dict(OPENFABLAB_DATABASE=str(self.database),OPENFABLAB_SECRET_KEY_FILE=str(self.data/'.secret_key'),
            OPENFABLAB_EXTERNAL_ACTIONS='0',OPENFABLAB_ENABLE_SCHEDULER='0',OPENFABLAB_ENABLE_WEATHER='0',
            PYTHONPATH=str(runtime or SOURCE)+os.pathsep+os.environ.get('PYTHONPATH',''))
        result=subprocess.run([sys.executable,*arguments],input=payload,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,
            env=environment,cwd=runtime or SOURCE)
        if result.returncode:raise Refused('FICTIONAL_WORKER_FAILED')
        return result.stdout

    def relay(self,job):
        if self.failure=='relay':raise Refused('FICTIONAL_RELAY_FAILURE')
        return super().relay(job)

class Upgrade(unittest.TestCase):
    def setUp(self):
        core.NewVersion.setUp(self)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.project=self.root/'project';self.project.mkdir()
        self.data=self.root/'data'
        coherent_copy(Path(self.path).parent,self.data,database_name=Path(self.path).name)
        (self.data/Path(self.path).name).rename(self.data/'openfablab.db')
        self.database=self.data/'openfablab.db'
        with sqlite3.connect(self.database) as db:
            db.execute("UPDATE app_settings SET value='0' WHERE key='module_public_reservations'")
        source=runtime_files()
        for name,value in source.items():
            target=self.project/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(value)
        state=self.root/'agent';state.mkdir();backups=self.root/'backups';backups.mkdir()
        compose=self.project/'compose.json';compose.write_text(json.dumps(dict(services=dict(openfablab=dict(image=OLD)))))
        self.policy=dict(state=str(state),project=str(self.project),data=str(self.data),database=str(self.database),backups=str(backups),
            compose_file=str(compose),service='openfablab',docker_root=str(self.root),docker='/not-a-real-docker',enabled=True)
        current=dict(Id='c'*64,Image=OLD,State=dict(Status='running',Running=True),
            Config=dict(Cmd=['gunicorn'],Entrypoint=None,Env=['TZ=Europe/Paris'],User='',WorkingDir='/app',Labels={
                'com.docker.compose.service':'openfablab','com.docker.compose.project.working_dir':str(self.project)}),
            HostConfig=dict(Privileged=False),Mounts=[dict(Type='bind',Source=str(self.data),Destination='/data',RW=True)])
        self.executor=LocalDocker(self.policy,current)
        hashes={n:hashlib.sha256(v).hexdigest() for n,v in source.items()}
        private_json(state/'current.json',dict(version='2.15.0',schema=26,image=OLD,files=hashes,
            launch_sha256=self.executor.launch_hash(current),configuration_sha256=self.executor.configuration_hash()))
        target=dict(source)
        target['openfablab/__init__.py']=target['openfablab/__init__.py'].replace(b'2.15.0',b'2.15.1')
        manifest=dict(format=1,version='2.15.1',agent_protocol=1,schema=26,source_schemas=[26],migration='family_model.migrate',
            new_tables=[],new_settings={},base_image='python:3.12-slim-bookworm',
            files={n:hashlib.sha256(v).hexdigest() for n,v in target.items()})
        manifest['runtime_files']=manifest['files']
        self.archive=self.root/'fictional-2.15.1.zip'
        with ZipFile(self.archive,'w',ZIP_DEFLATED) as archive:
            for name,value in target.items():archive.writestr(name,value)
            archive.writestr('UPDATE-MANIFEST.json',json.dumps(manifest))
        archive_path=self.archive
        class Release:
            def latest(self):return dict(version='2.15.1',notes='Mise à jour fictive isolée',page='https://example.invalid')
            def download(self,release,destination):shutil.copyfile(archive_path,destination);return destination
        self.engine=Engine(self.policy,Release(),self.executor)
        socket=self.root/'socket';token=self.root/'token';token.write_bytes(b'FICTIONAL_LOCAL_SECRET_'*3)
        self.service=Service(self.engine,token.read_bytes(),socket)
        threading.Thread(target=self.service.serve_forever,daemon=True).start()
        self.addCleanup(self.service.server_close);self.addCleanup(self.service.shutdown)
        environment=patch.dict(os.environ,OPENFABLAB_UPDATE_SOCKET=str(socket),OPENFABLAB_UPDATE_TOKEN_FILE=str(token));environment.start();self.addCleanup(environment.stop)
        self.f.f.app.config['DATABASE']=str(self.database)
        with self.client.session_transaction() as session:session['access_role']='admin';session['admin_authenticated']=True
        self.path_ui='/admin/reglages/systeme/mises-a-jour'
        self.client.get(self.path_ui)
        with self.client.session_transaction() as session:self.csrf=session['evolution_csrf']

    def operation(self,operation,**values):
        response=self.client.post(self.path_ui,data=dict(operation=operation,evolution_csrf=self.csrf,**values))
        self.assertEqual(response.status_code,200,response.json)
        return response.json
    def wait(self):
        self.service.worker.join(90)
        self.assertFalse(self.service.worker.is_alive());self.assertIsNone(self.service.last_error,self.service.last_error)

    def test_real_workers_sqlite_and_runtime_upgrade_through_ui_then_post_restore(self):
        before=snapshot(self.database)
        with patch('updater_agent.docker_executor.shutil.disk_usage',return_value=type('Disk',(),dict(free=10**13))()):
            self.operation('prepare_zip',candidate=(io.BytesIO(self.archive.read_bytes()),'fixture.zip'));self.wait()
            prepared=self.operation('status')['value'];self.assertEqual(prepared['result'],'ready',prepared)
            self.assertEqual(before,snapshot(self.database));self.assertNotIn('stop',self.executor.calls)
            self.assertNotIn('worker:probe',self.executor.calls)
            self.operation('install',id=prepared['id'],confirmation=prepared['confirmation'],consent='INSTALLER');self.wait()
        final=self.operation('status')['value'];self.assertEqual(final['result'],'success',final)
        self.assertFalse(final['migration_attempted'])
        self.assertEqual(snapshot(self.database)['schema'],26)
        with sqlite3.connect(self.database) as db:self.assertTrue(db.execute("SELECT 1 FROM visitors WHERE created_at='2030-01-01T10:00:00+00:00'").fetchone())
        post=Path(self.policy['backups'])/final['post_backup']
        restored=post/'restoration-test/openfablab.db';self.assertEqual(snapshot(self.database),snapshot(restored))
        self.assertEqual(json.loads(Path(self.policy['compose_file']).read_bytes())['services']['openfablab']['image'],NEW)
        self.assertTrue((post/'target-image.tar').is_file()) # Deliberately simulated image archive.
        self.assertTrue(json.loads((post/'backup-receipt.json').read_bytes())['restoration_test'])

    def test_real_post_public_writes_survive_failure_and_independent_resume(self):
        with patch('updater_agent.docker_executor.shutil.disk_usage',return_value=type('Disk',(),dict(free=10**13))()):
            self.operation('prepare');self.wait();prepared=self.operation('status')['value']
            self.executor.failure='relay'
            self.operation('install',id=prepared['id'],confirmation=prepared['confirmation'],consent='INSTALLER');self.wait()
        failed=self.operation('status')['value'];self.assertEqual(failed['result'],'failed_preserved',failed)
        self.assertFalse(self.executor.current['State']['Running'])
        with sqlite3.connect(self.database) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM visitors WHERE created_at='2030-01-01T10:00:00+00:00'").fetchone()[0],1)
        self.assertTrue(self.engine.recovery_diagnostic(prepared['id'])['diagnostic']['can_resume_target'])
        self.executor.failure=None
        result=self.engine.resume(prepared['id'],'RESUME-'+prepared['id'])
        self.assertEqual(result['result'],'success',result)
        self.assertEqual(self.executor.calls.count('worker:migrate'),0)
        with sqlite3.connect(self.database) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM visitors WHERE created_at='2030-01-01T10:00:00+00:00'").fetchone()[0],2)
        self.assertTrue(list(Path(self.policy['backups']).glob('PRESERVED-*')))

if __name__=='__main__':unittest.main()
