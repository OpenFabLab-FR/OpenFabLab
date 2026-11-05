"""Fixed Docker/Compose executor for an operator-approved local installation.

Runs only inside the separately installed agent, never in the web container.
All paths and the service originate in the private root-owned policy. Remote
requests cannot supply a Docker command, mount, environment or executable.
"""
import hashlib
import base64
import io
import json
import os
from pathlib import Path
import re
import shutil
import secrets
import sqlite3
import subprocess
import threading
import time
from zipfile import ZipFile,ZIP_DEFLATED
from .filesystem import checked_path, copy_verified_runtime, inventory, sha, write_probe,readonly_storage_lock
from .releases import unpack
from .security import Refused, pack, private_json
from .diagnostics import DiagnosticFailure,from_stdout,validated
from .privileges import CAPABILITY,EXPECTED_ENV,FIXTURE_SCRIPT,mounts as worker_mounts
from .capability_diagnostics import CapabilityRefused,transport as capability_transport,validated_transport
from .stage_diagnostics import phase,recorded

HASH_SCRIPT = """import hashlib,json,pathlib,sys
result={}
for name in json.load(sys.stdin):
 p=pathlib.Path('/app')/name
 result[name]='UNSAFE' if p.is_symlink() or any(x.is_symlink() for x in p.parents) else hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else 'MISSING'
print(json.dumps(result,sort_keys=True))
"""
HEALTH_SCRIPT = """import urllib.request
with urllib.request.urlopen('http://127.0.0.1:8000/stat/sante',timeout=3) as response:
 assert response.status==200 and response.read(1024)==b'OK\\n'
print('HEALTH_OK')
"""
WORKER_LAUNCHER="""import base64,io,runpy,sys,tempfile,zipfile
with tempfile.TemporaryDirectory(prefix='fixed-updater-worker-') as folder:
 with zipfile.ZipFile(io.BytesIO(base64.b64decode(sys.stdin.buffer.read(1048577),validate=True))) as archive:
  archive.extractall(folder)
 sys.path.insert(0,folder)
 sys.argv=['updater_agent.worker',*sys.argv[1:]]
 runpy.run_module('updater_agent.worker',run_name='__main__')
"""
BUILD_ERRORS={
    'MAX_LAYER_DEPTH':r'max(?:imum)? (?:layer )?depth exceeded|too many layers',
    'INSUFFICIENT_SPACE':r'no space left on device|insufficient disk space',
    'MEMORY_UNAVAILABLE':r'out of memory|cannot allocate memory',
    'DOCKER_ACCESS_REFUSED':r'permission denied|cannot connect to the docker daemon',
    'BUILD_DEPENDENCY_FAILED':r'no matching distribution|could not find a version|failed building wheel|resolutionimpossible',
    'BUILD_NETWORK_FAILED':r'temporary failure in name resolution|network is unreachable|connection timed out|tls handshake timeout',
    'BUILD_INPUT_INVALID':r'failed to compute cache key|file not found|dockerfile parse error',
    'BUILD_ARCHITECTURE_UNSUPPORTED':r'exec format error|no matching manifest',
}

def bounded_process(command,environment,payload,timeout):
    """Drain both streams with a hard memory bound; never persist raw output."""
    process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=environment)
    streams=[bytearray(),bytearray()];exceeded=threading.Event()
    def read(stream,index):
        try:
            while True:
                chunk=stream.read(65536)
                if not chunk:break
                if len(streams[index])+len(chunk)>16*1024*1024:
                    exceeded.set();process.kill();break
                streams[index].extend(chunk)
        finally:stream.close()
    def write():
        try:
            if payload:process.stdin.write(payload);process.stdin.flush()
        except (BrokenPipeError,OSError):pass
        finally:process.stdin.close()
    readers=[threading.Thread(target=read,args=(stream,i),daemon=True) for i,stream in enumerate((process.stdout,process.stderr))]
    writer=threading.Thread(target=write,daemon=True)
    for thread in readers+[writer]:thread.start()
    try:process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill();process.wait();raise
    finally:
        for thread in readers+[writer]:thread.join(5)
    if exceeded.is_set():raise Refused('DOCKER_RESPONSE_TOO_LARGE')
    if any(thread.is_alive() for thread in readers+[writer]):raise Refused('DOCKER_STREAM_DID_NOT_CLOSE')
    return subprocess.CompletedProcess(command,process.returncode,bytes(streams[0]),bytes(streams[1]))


class DockerExecutor:
    def __init__(self,policy,helper_image):
        self.policy=policy
        self.state=Path(policy['state']);self.project=Path(policy['project'])
        self.data=Path(policy['data']);self.backups=Path(policy['backups'])
        self.database=Path(policy['database'])
        if not re.fullmatch(r'sha256:[0-9a-f]{64}',helper_image):
            raise Refused('AGENT_HELPER_IMAGE_NOT_PINNED')
        self.helper_image=helper_image

    def run(self,arguments,*,payload=None,timeout=120):
        # Sanitize inherited Docker/Compose/proxy overrides. Output can contain
        # secrets; callers may parse it in memory but it is NEVER logged raw.
        environment={k:v for k,v in os.environ.items() if not k.startswith(('DOCKER_','COMPOSE_'))}
        environment.update(PYTHONDONTWRITEBYTECODE='1')
        try:
            result=bounded_process([self.policy['docker'],'--host','unix:///var/run/docker.sock',*arguments],environment,payload,timeout)
        except (OSError,subprocess.TimeoutExpired):
            raise Refused('LOCAL_DOCKER_UNAVAILABLE_OR_TIMEOUT') from None
        if FIXTURE_SCRIPT in arguments:
            index=arguments.index(FIXTURE_SCRIPT)
            # Only the exact fixed fictional diagnostic receives this path.
            # A nonzero result becomes a typed failure, never an accepted check.
            nonce,mode=arguments[index+1:index+3]
            return pack(capability_transport(result.stdout,result.returncode,nonce,mode))
        if result.returncode:
            if WORKER_LAUNCHER in arguments:
                launch=arguments.index(WORKER_LAUNCHER)
                if '--diagnostic-id' in arguments[launch+1:]:
                    position=arguments.index('--diagnostic-id',launch+1)
                    if position+1<len(arguments):
                        safe=from_stdout(result.stdout,arguments[position+1],arguments[launch+1])
                        if safe is not None:raise DiagnosticFailure(safe)
            diagnostic=(result.stderr+result.stdout).decode('utf-8','replace')
            code=next((c for c,p in BUILD_ERRORS.items() if re.search(p,diagnostic,re.I)),'LOCAL_DOCKER_OPERATION_FAILED')
            raise Refused(code)
        if len(result.stdout)>16*1024*1024:
            raise Refused('DOCKER_RESPONSE_TOO_LARGE')
        return result.stdout

    def load_current(self):
        path=self.state/'current.json'
        if path.is_symlink() or not path.is_file():
            raise Refused('APPROVED_INSTALLATION_RECEIPT_MISSING')
        result=json.loads(path.read_bytes())
        if not {'version','schema','image','files','launch_sha256','configuration_sha256'}<=set(result):
            raise Refused('APPROVED_INSTALLATION_RECEIPT_INVALID')
        return result

    def compose(self,arguments,override=None,replacement=None):
        command=['compose','--project-directory',str(self.project),'-f',str(replacement or self.policy['compose_file'])]
        env=self.project/'.env'
        if env.is_file():command+=['--env-file',str(env)]
        if override:
            path=checked_path(override,False)
            if not path.is_relative_to(self.state):
                raise Refused('COMPOSE_OVERRIDE_OUTSIDE_AGENT')
            command+=['-f',str(path)]
        return self.run(command+arguments,timeout=180)

    def container(self,override=None,allow_stopped=False):
        identifiers=self.compose(['ps','-a','-q',self.policy['service']],override).decode().split()
        if len(identifiers)!=1 or not re.fullmatch('[0-9a-f]{12,64}',identifiers[0]):
            raise Refused('COMPOSE_SERVICE_IDENTITY_AMBIGUOUS')
        result=json.loads(self.run(['inspect','--type','container',identifiers[0]]))
        if len(result)!=1:
            raise Refused('CONTAINER_INSPECTION_INVALID')
        item=result[0]
        if not allow_stopped and item['State']['Status']!='running':
            raise Refused('APPROVED_SOURCE_NOT_RUNNING')
        labels=item['Config'].get('Labels') or {}
        if labels.get('com.docker.compose.service')!=self.policy['service'] or labels.get('com.docker.compose.project.working_dir')!=str(self.project):
            raise Refused('COMPOSE_PROJECT_IDENTITY_CHANGED')
        return item

    def launch_hash(self,item):
        c,h=item['Config'],item['HostConfig']
        keys=('Cmd','Entrypoint','Env','User','WorkingDir')
        value={k:c.get(k) for k in keys}
        # Explicit OpenFabLab settings and TZ must survive. Python image build
        # metadata (PYTHON_VERSION/SHA256/PIP_VERSION) is not an application
        # configuration and may legitimately change with the clean base image.
        value['Env']=sorted(v for v in value.get('Env') or [] if not v.startswith(('PYTHON_VERSION=','PYTHON_SHA256=','PYTHON_PIP_VERSION=','PYTHON_SETUPTOOLS_VERSION=','PYTHON_GET_PIP_')))
        value['host']={k:h.get(k) for k in ('RestartPolicy','PortBindings','NetworkMode','Privileged','CapAdd','SecurityOpt','ReadonlyRootfs')}
        value['mounts']=sorted((m['Type'],m.get('Source'),m['Destination'],m['RW']) for m in item['Mounts'])
        return hashlib.sha256(pack(value)).hexdigest()

    def configuration_hash(self):
        files={}
        for path in (Path(self.policy['compose_file']),self.project/'.env'):
            checked_path(path,False)
            files[path.name]=sha(path) if path.is_file() else None
        return hashlib.sha256(pack(files)).hexdigest()

    def runtime_hashes(self,image_or_container,files,*,active=False):
        names=sorted(files)
        if active:
            raw=self.run(['exec','-i',image_or_container,'python','-c',HASH_SCRIPT],payload=pack(names))
        else:
            raw=self.run(['run','--rm','-i','--read-only','--network','none','--entrypoint','python',image_or_container,'-c',HASH_SCRIPT],payload=pack(names))
        if json.loads(raw)!=files:
            raise Refused('ACTIVE_RUNTIME_FILES_CHANGED' if active else 'IMAGE_RUNTIME_FILES_CHANGED')

    def helper(self,operation,output,*,access='ro',extra=(),runtime=None,image=None,isolated_probe=None):
        if access not in ('ro','rw'):
            raise Refused('HELPER_ACCESS_INVALID')
        output=checked_path(output,False)
        if not output.is_relative_to(self.state):
            raise Refused('HELPER_OUTPUT_OUTSIDE_AGENT')
        database=self.database
        if isolated_probe is None:
            mounts=worker_mounts(operation,access,self.project,self.data,self.backups,self.state)
        else:
            workspace=checked_path(isolated_probe)
            if operation!='probe' or access!='ro' or not workspace.is_relative_to(self.state) or output.parent!=workspace:
                raise Refused('ISOLATED_PROBE_SCOPE_REFUSED')
            mounts=[(workspace,workspace,'rw')]
            database=workspace/'probe-data'/'openfablab.db'
        if runtime:mounts.append((Path(runtime),Path('/update-runtime'),'ro'))
        command=['run','--rm','-i','--read-only','--network','none','--cap-drop','ALL','--cap-add',CAPABILITY,'--security-opt','no-new-privileges',
                 '--tmpfs','/tmp:rw,nosuid,nodev','--entrypoint','python','-e','PYTHONDONTWRITEBYTECODE=1','-e',EXPECTED_ENV+'='+CAPABILITY]
        for source,target,mode in mounts:
            command+=['--mount','type=bind,source='+str(source)+',target='+str(target)+(',readonly' if mode=='ro' else '')]
        selected=image or self.helper_image
        if not re.fullmatch(r'sha256:[0-9a-f]{64}',selected):raise Refused('WORKER_IMAGE_NOT_PINNED')
        request_id=secrets.token_hex(16)
        command += [selected,'-c',WORKER_LAUNCHER,operation,'--database',str(database),'--output',str(output),'--diagnostic-id',request_id,*map(str,extra)]
        # Fixed worker code comes from this independently installed agent, not
        # the downloaded application. Target-image dependencies are available
        # without ever passing its code a Docker socket or host command API.
        bundle=io.BytesIO()
        with ZipFile(bundle,'w',ZIP_DEFLATED) as archive:
            import update_wire
            archive.writestr('update_wire.py',Path(update_wire.__file__).read_bytes())
            for source in sorted(Path(__file__).parent.glob('*.py')):
                if source.is_symlink():raise Refused('AGENT_WORKER_SOURCE_UNSAFE')
                archive.writestr('updater_agent/'+source.name,source.read_bytes())
        payload=base64.b64encode(bundle.getvalue())
        if len(payload)>1048576:raise Refused('AGENT_WORKER_BUNDLE_TOO_LARGE')
        try:
            self.run(command,timeout=1800,payload=payload)
        except Refused as error:
            if isinstance(error,DiagnosticFailure):raise
            if output.is_file():
                value=json.loads(output.read_bytes())
                if value.get('success') is False:
                    safe=validated(value.get('diagnostic'),request_id,operation)
                    if safe is not None:raise DiagnosticFailure(safe) from None
            raise
        return json.loads(output.read_bytes())

    def capability_preflight(self):
        """Real Docker kernel test on fictional files, safe even in --check."""
        folder=self.state/('capability-fixture-'+secrets.token_hex(8))
        folder.mkdir(mode=0o700);data=folder/'data';data.mkdir(mode=0o700)
        database=data/'openfablab.db'
        with sqlite3.connect(database) as db:
            db.execute('CREATE TABLE fictitious(id INTEGER PRIMARY KEY)');db.execute('PRAGMA user_version=25')
        database.chmod(0o600);original=sha(database);results={}
        data.chmod(0)
        try:
            for mode in ('denied','read','write'):
                command=['run','--rm','--read-only','--network','none','--cap-drop','ALL']
                if mode!='denied':command+=['--cap-add',CAPABILITY]
                nonce=secrets.token_hex(16)
                command+=['--security-opt','no-new-privileges','--entrypoint','python','-e','PYTHONDONTWRITEBYTECODE=1',
                    '--mount','type=bind,source='+str(folder)+',target=/fixture'+('' if mode=='write' else ',readonly'),
                    self.helper_image,'-c',FIXTURE_SCRIPT,nonce,mode]
                try:
                    observed=validated_transport(json.loads(self.run(command,timeout=60)),nonce,mode)
                except (ValueError,Refused):observed=capability_transport(b'',None,nonce,mode)
                if observed is None:observed=capability_transport(b'',0,nonce,mode)
                results[mode]=observed
                # Diagnose all three isolated contexts even if one fails. No
                # production phase can proceed unless every context passes.
                private_json(self.state/'capability-preflight.json',dict(success=False,context=mode,code='SELFTEST_COLLECTION_IN_PROGRESS',
                    fictional_files_only=True,production_mounted=False,raw_output_saved=False,contexts=results))
        finally:
            # This directory was created above for this test only. Never chmod
            # production, real backup storage or any pre-existing path.
            data.chmod(0o700)
        if sha(database)!=original:raise Refused('FICTIONAL_CAPABILITY_DATABASE_CHANGED')
        failures=[mode for mode,result in results.items() if result['success'] is not True]
        first=failures[0] if failures else None
        private_json(self.state/'capability-preflight.json',dict(success=not failures,context=first or 'complete',
            code=results[first]['code'] if first else 'SELFTEST_OK',fictional_files_only=True,raw_output_saved=False,
            production_mounted=False,source_database_unchanged=True,contexts=results))
        if failures:raise CapabilityRefused(results[first])
        return results

    def inspect(self):
        current=self.load_current()
        item=self.container(current.get('override'))
        if item['Image']!=current['image'] or self.launch_hash(item)!=current['launch_sha256']:
            raise Refused('APPROVED_IMAGE_OR_LAUNCH_CHANGED')
        if self.configuration_hash()!=current['configuration_sha256']:
            raise Refused('APPROVED_COMPOSE_OR_ENV_CHANGED')
        mounts=item['Mounts']
        if not any(m['Destination']=='/data' and m['Source']==str(self.data) and m['RW'] for m in mounts):
            raise Refused('DATA_VOLUME_MISMATCH')
        if item['HostConfig'].get('Privileged') or any(m['Destination']=='/var/run/docker.sock' for m in mounts):
            raise Refused('WEB_CONTAINER_PRIVILEGES_UNSAFE')
        for name,expected in current['files'].items():
            path=checked_path(self.project/name,False)
            if not path.is_file() or sha(path)!=expected:
                raise Refused('APPROVED_STORAGE_RUNTIME_CHANGED')
        self.runtime_hashes(item['Id'],current['files'],active=True)
        self.runtime_hashes(current['image'],current['files'])
        output=self.state/'read-only-inspection.json'
        self.helper('snapshot',output,extra=['--schema',current['schema']])
        return {k:current[k] for k in ('version','schema','image','files','launch_sha256','configuration_sha256')}|dict(container=item['Id'],override=current.get('override'))

    def enroll(self,manifest):
        """One-time operator action, only after exact approved runtime checks."""
        if (self.state/'current.json').exists():
            raise Refused('AGENT_ALREADY_ENROLLED_DO_NOT_OVERWRITE')
        required={'app.py','family_model.py','openfablab/__init__.py','runtime_policy.py','requirements.txt','requirements-nas.txt'}
        if manifest.get('agent_protocol')!=1 or not isinstance(manifest.get('runtime_files'),dict) or not required<=manifest['runtime_files'].keys():
            raise Refused('AGENT_ENROLLMENT_MANIFEST_INVALID')
        item=self.container()
        for name,expected in manifest['runtime_files'].items():
            path=checked_path(self.project/name,False)
            if sha(path)!=expected:raise Refused('ENROLLMENT_STORAGE_MISMATCH')
        self.runtime_hashes(item['Id'],manifest['runtime_files'],active=True)
        self.runtime_hashes(item['Image'],manifest['runtime_files'])
        self.helper('snapshot',self.state/'enrollment-database.json',extra=['--schema',manifest['schema']])
        receipt=dict(version=manifest['version'],schema=manifest['schema'],image=item['Image'],files=manifest['runtime_files'],
            launch_sha256=self.launch_hash(item),configuration_sha256=self.configuration_hash())
        private_json(self.state/'current.json',receipt)
        # Reuse the same production mount/privilege checks before authorization.
        self.inspect()
        return dict(success=True,version=manifest['version'],schema=manifest['schema'])

    @recorded(lambda self,path,destination,version:self.state/'unpack-stages.json')
    @phase('CANDIDATE_UNPACK')
    def unpack(self,path,destination,version):
        result=unpack(path,destination,version)
        required={'runtime_files','new_tables','new_settings','base_image'}
        if not required<=set(result) or not isinstance(result['runtime_files'],dict) or not result['runtime_files']:
            raise Refused('EXECUTOR_MANIFEST_INCOMPLETE')
        if not {'app.py','family_model.py','openfablab/__init__.py','runtime_policy.py','requirements.txt','requirements-nas.txt'}<=result['runtime_files'].keys():
            raise Refused('EXECUTOR_CORE_RUNTIME_INCOMPLETE')
        if any(result['files'].get(n)!=v for n,v in result['runtime_files'].items()):
            raise Refused('EXECUTOR_RUNTIME_MANIFEST_MISMATCH')
        if not re.fullmatch(r'python:3\.12-slim-bookworm(?:@sha256:[0-9a-f]{64})?',result['base_image']):
            raise Refused('EXECUTOR_BASE_IMAGE_UNSUPPORTED')
        if (not isinstance(result['new_tables'],list) or any(not isinstance(n,str) or not re.fullmatch('[a-z][a-z0-9_]{0,79}',n) for n in result['new_tables'])
                or not isinstance(result['new_settings'],dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in result['new_settings'].items())):
            raise Refused('EXECUTOR_MIGRATION_MANIFEST_INVALID')
        for name in result['runtime_files']:
            if (not name or name.startswith(('data/','updater_agent/')) or name in ('compose.yaml','UPDATE-MANIFEST.json')
                    or not (name.endswith('.py') or name.startswith(('templates/','static/','translations/','badge_templates/'))
                            or name in ('requirements.txt','requirements-nas.txt','package.json','LICENSE','THIRD_PARTY_NOTICES.md'))):
                raise Refused('EXECUTOR_RUNTIME_PATH_REFUSED')
        return result

    def folder(self,job):return self.state/job['id']

    @recorded(lambda self,job:self.state/'preflight-stages.json')
    def preflight(self,job):
        folder=self.folder(job)
        sidecars={self.database.name+suffix for suffix in ('-wal','-shm','-journal')}
        with phase('PREFLIGHT_STORAGE_LOCK'),readonly_storage_lock(self.data):
            with phase('PREFLIGHT_INVENTORY'):
                size=sum(v['size'] for v in inventory(self.data,sidecars).values())
        with phase('PREFLIGHT_IMAGE'):
            image=json.loads(self.run(['image','inspect',job['source']['image']]))[0]
            required=max(1024**3,size*5+int(image['Size'])*3+512*1024**2)
        for role,root in (('PROJECT',self.project),('BACKUPS',self.backups),('STATE',self.state),('DOCKER',Path(self.policy['docker_root']))):
            with phase('PREFLIGHT_SPACE',role):
                checked_path(root)
                if shutil.disk_usage(root).free<required:
                    raise Refused(role+'_PREPARATION_SPACE_INSUFFICIENT')
        # Effective ACL check, not POSIX mode-bit assumptions. Real temporary
        # writes occur only after the human confirms installation, before stop.
        if job['result']=='installing':
            for role,root in (('PROJECT',self.project),('DATA',self.data),('BACKUPS',self.backups),('STATE',self.state)):
                with phase('PREFLIGHT_WRITE_ACCESS',role):
                    try:write_probe(root)
                    except Refused as error:raise Refused(role+'_'+error.code) from None
        with phase('PREFLIGHT_COMPOSE'):self.compose(['version'])

    def build(self,job):
        folder=self.folder(job);runtime=folder/'runtime';context=folder/'build-context'
        context.mkdir(mode=0o700)
        for name,expected in job['manifest']['runtime_files'].items():
            origin=runtime/name
            if sha(origin)!=expected:raise Refused('BUILD_RUNTIME_HASH_MISMATCH')
            target=context/'runtime'/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            shutil.copy2(origin,target)
        for name in ('requirements.txt','requirements-nas.txt'):
            if name not in job['manifest']['files']:raise Refused('BUILD_REQUIREMENTS_MISSING')
            shutil.copy2(runtime/name,context/name)
        dockerfile='FROM '+job['manifest']['base_image']+'\nWORKDIR /app\nCOPY requirements.txt requirements-nas.txt ./\nRUN pip install --no-cache-dir --disable-pip-version-check -r requirements-nas.txt\nCOPY runtime/ /app/\nENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Europe/Paris\nEXPOSE 8000\nHEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 CMD ["python","-c","import urllib.request; urllib.request.urlopen(\'http://127.0.0.1:8000/stat/sante\',timeout=2).read()"]\nCMD ["gunicorn","--bind=0.0.0.0:8000","--workers=1","--threads=4","--timeout=30","--access-logfile=-","--error-logfile=-","app:app"]\n'
        (context/'Dockerfile').write_text(dockerfile)
        tag='openfablab:agent-'+job['version']+'-'+job['id'][:12]
        # A clean official Python base avoids indefinitely stacking on an old
        # application image. No production data/configuration enters the build.
        try:
            self.run(['build','--file',str(context/'Dockerfile'),'--tag',tag,str(context)],timeout=3600)
        except Refused as error:
            private_json(folder/'docker-build.json',dict(success=False,code=error.code,raw_output_saved=False))
            raise
        image=json.loads(self.run(['image','inspect',tag]))[0]
        layers=image.get('RootFS',{}).get('Layers')
        if not isinstance(layers,list) or len(layers)>=125:
            raise Refused('TARGET_LAYER_BUDGET_REFUSED')
        self.runtime_hashes(image['Id'],job['manifest']['runtime_files'])
        private_json(folder/'docker-build.json',dict(success=True,layers=len(layers),raw_output_saved=False))
        return dict(image=image['Id'],tag=tag,layers=len(layers))

    def probe(self,job):
        folder=self.folder(job)
        private_json(folder/'manifest.json',job['manifest'])
        workspace=folder/'probe-workspace';workspace.mkdir(mode=0o700)
        private_json(workspace/'manifest.json',job['manifest'])
        # Copy using only the existing trusted runtime. Candidate code sees
        # neither the live data mount nor the shared updater state directory.
        self.helper('probe-copy',folder/'probe-copy.json',extra=[
            '--schema',job['source_schema'],'--destination',workspace/'probe-data'])
        self.helper('probe',workspace/'probe.json',runtime=folder/'runtime',image=job['target']['image'],isolated_probe=workspace,extra=[
            '--runtime','/update-runtime','--manifest',workspace/'manifest.json','--destination',workspace/'probe-data','--prepared-copy'])

    def verify_source(self,job):
        source=self.inspect()
        if source!=job['source']:
            raise Refused('SOURCE_CHANGED_SINCE_PREPARATION')

    def hot_backup(self,job):
        folder=self.folder(job)
        # Same namespace/profile as later writes, before any production stop.
        self.helper('write-preflight',folder/'write-preflight.json',access='rw',extra=['--project',self.project,'--destination',self.backups])
        self.helper('backup',folder/'hot-backup.json',access='rw',image=job['source']['image'],extra=['--destination',self.backups/('HOT-'+job['id']),
                    '--project',self.project,'--compose',self.policy['compose_file'],*self.backup_override(job['source'].get('override')),
                    '--version',job['source_version'],'--schema',job['source_schema']])

    def backup_override(self,path):
        return ['--override',path] if path else []

    def stop_source(self,job):
        self.run(['stop','--time','45',job['source']['container']],timeout=90)
        state=json.loads(self.run(['inspect',job['source']['container']]))[0]['State']
        if state['Running']:raise Refused('SOURCE_STOP_NOT_CONFIRMED')

    def cold_backup(self,job):
        folder=self.folder(job);destination=self.backups/('PRE'+str(job['source_schema'])+'-'+job['id'])
        receipt=self.helper('backup',folder/'cold-backup.json',access='rw',image=job['source']['image'],extra=['--destination',destination,
                    '--project',self.project,'--compose',self.policy['compose_file'],*self.backup_override(job['source'].get('override')),
                    '--version',job['source_version'],'--schema',job['source_schema'],'--cold'])
        # Keep the exact source image too. No image or previous backup is deleted.
        image=destination/'source-image.tar'
        self.run(['image','save','--output',str(image),job['source']['image']],timeout=1800)
        image.chmod(0o600)
        if not image.is_file() or image.stat().st_size<=0:raise Refused('SOURCE_IMAGE_BACKUP_FAILED')
        self.helper('snapshot',folder/'baseline.json',extra=['--schema',job['source_schema']])
        private_json(folder/'private-before.json',inventory(self.data,{'openfablab.db','openfablab.db-wal','openfablab.db-shm','openfablab.db-journal','.openfablab-state.lock'}))
        return destination.name

    def migrate(self,job):
        folder=self.folder(job)
        self.helper('migrate',folder/'migration.json',access='rw',runtime=folder/'runtime',image=job['target']['image'],extra=[
            '--runtime','/update-runtime','--baseline',folder/'baseline.json','--manifest',folder/'manifest.json'])

    def verify_migration(self,job):
        folder=self.folder(job)
        self.helper('compare',folder/'before-public.json',extra=['--baseline',folder/'baseline.json','--manifest',folder/'manifest.json'])
        previous=json.loads((folder/'private-before.json').read_bytes())
        for name,record in previous.items():
            path=self.data/name
            if not path.is_file() or sha(path)!=record['sha256']:
                raise Refused('PRIVATE_FILE_CHANGED_DURING_MIGRATION')

    def install_runtime(self,job):
        folder=self.folder(job)
        copy_verified_runtime(folder/'runtime',self.project,job['manifest']['runtime_files'])
        from .compose_image import proposal,equivalent
        compose=checked_path(self.policy['compose_file'],False)
        candidate=folder/'compose-proposal.yaml'
        before=json.loads(self.compose(['config','--format','json']))
        raw=proposal(compose.read_bytes(),self.policy['service'],job['target']['image'])
        candidate.write_bytes(raw);candidate.chmod(0o600)
        proposed=json.loads(self.compose(['config','--format','json'],replacement=candidate))
        equivalent(before,proposed,self.policy['service'],job['target']['image'])
        # Persist the expected post-update configuration before replacing it;
        # recovery can diagnose a kill at either side of the atomic boundary.
        env=self.project/'.env'
        target_hash=hashlib.sha256(pack({compose.name:hashlib.sha256(raw).hexdigest(),'.env':sha(env) if env.is_file() else None})).hexdigest()
        private_json(folder/'target-configuration.json',dict(sha256=target_hash))
        temporary=compose.with_name('.'+compose.name+'.agent-update-'+job['id'])
        try:
            with temporary.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            temporary.chmod(compose.stat().st_mode & 0o777)
            os.replace(temporary,compose)
        finally:
            if temporary.exists():temporary.unlink()
        if self.configuration_hash()!=target_hash:raise Refused('COMPOSE_IMAGE_PERSISTENCE_FAILED')
        override=folder/'compose-target.json'
        private_json(override,dict(services={self.policy['service']:{'image':job['target']['image']}}))
        self.helper('snapshot',folder/'before-public.json',extra=['--schema',job['target_schema']])

    def start_target(self,job):
        self.compose(['up','-d','--no-build','--pull','never','--no-deps',self.policy['service']],self.folder(job)/'compose-target.json')

    def health(self,job):
        deadline=time.monotonic()+180
        while True:
            try:
                item=self.container(self.folder(job)/'compose-target.json')
                if item['Image']!=job['target']['image'] or self.launch_hash(item)!=job['source']['launch_sha256']:
                    raise Refused('TARGET_IMAGE_OR_LAUNCH_MISMATCH')
                self.runtime_hashes(item['Id'],job['manifest']['runtime_files'],active=True)
                self.run(['exec',item['Id'],'python','-c',HEALTH_SCRIPT],timeout=10)
                return
            except Refused:
                if time.monotonic()>=deadline:raise
                time.sleep(2)

    def verify_live(self,job):
        folder=self.folder(job)
        self.helper('compare-live',folder/'live-check.json',extra=['--baseline',folder/'before-public.json'])
        if self.configuration_hash()!=self.expected_configuration(job):
            raise Refused('COMPOSE_OR_ENV_CHANGED_DURING_UPDATE')
        self.verify_private(job)

    def expected_configuration(self,job):
        path=self.folder(job)/'target-configuration.json'
        return json.loads(path.read_bytes())['sha256'] if path.is_file() else job['source']['configuration_sha256']

    def verify_private(self,job):
        previous=json.loads((self.folder(job)/'private-before.json').read_bytes())
        for name,record in previous.items():
            path=checked_path(self.data/name,False)
            if not path.is_file() or sha(path)!=record['sha256']:
                raise Refused('PERSISTENT_PRIVATE_FILE_CHANGED_REVIEW_REQUIRED')

    def relay(self,job):
        # Implemented as a narrowly scoped signed capability/freshness probe,
        # never as replaying business queues. Unknown states remain a refusal.
        from .relay_check import check
        check(self.database,self.data,started=job['public_started_at'],report=self.folder(job)/'wordpress-stages.json')

    def post_backup(self,job):
        folder=self.folder(job);destination=self.backups/('POST'+str(job['target_schema'])+'-'+job['id'])
        self.helper('backup',folder/'post-backup.json',access='rw',runtime=folder/'runtime',image=job['target']['image'],extra=['--runtime','/update-runtime','--destination',destination,
                    '--project',self.project,'--compose',self.policy['compose_file'],'--override',folder/'compose-target.json',
                    '--version',job['version'],'--schema',job['target_schema']])
        image=destination/'target-image.tar'
        self.run(['image','save','--output',str(image),job['target']['image']],timeout=1800)
        if not image.is_file() or image.stat().st_size<=0:raise Refused('TARGET_IMAGE_BACKUP_FAILED')
        image.chmod(0o600)
        item=self.container(folder/'compose-target.json')
        current=dict(version=job['version'],schema=job['target_schema'],image=job['target']['image'],
            files=job['manifest']['runtime_files'],launch_sha256=self.launch_hash(item),
            configuration_sha256=self.configuration_hash(),override=str(folder/'compose-target.json'))
        private_json(self.state/'current.json',current)
        return destination.name

    def stop_target(self,job):
        item=self.container(self.folder(job)/'compose-target.json',allow_stopped=True)
        if item['Image']!=job['target']['image']:raise Refused('REFUSING_TO_STOP_UNRELATED_CONTAINER')
        if item['State']['Running']:self.run(['stop','--time','45',item['Id']],timeout=90)

    def preserve(self,job):
        # A best-effort fresh complete state copy, never PRE restoration. The
        # existing data/runtime/old image and all writes are left in place.
        folder=self.folder(job);destination=self.backups/('PRESERVED-'+job['id']+'-'+str(int(time.time())))
        observed=self.helper('snapshot',folder/'preserved-inspection.json')
        schema=observed['schema']
        if schema not in (job['source_schema'],job['target_schema']):
            raise Refused('PRESERVED_SCHEMA_UNEXPECTED')
        version=job['source_version'] if schema==job['source_schema'] and not job['public_start_attempted'] else job['version']
        self.helper('backup',folder/'preserved.json',access='rw',runtime=folder/'runtime',image=job['target']['image'],extra=['--runtime','/update-runtime','--destination',destination,
            '--project',self.project,'--compose',self.policy['compose_file'],*self.backup_override(str(folder/'compose-target.json') if (folder/'compose-target.json').is_file() else job['source'].get('override')),
            '--version',version,'--schema',schema])

    def recovery_check(self,job):
        folder=self.folder(job)
        if not (folder/'before-public.json').is_file() or not (folder/'compose-target.json').is_file():
            return dict(can_resume_target=False,code='TARGET_INSTALLATION_INCOMPLETE_NO_AUTOMATIC_RESTORE')
        item=self.container(folder/'compose-target.json',allow_stopped=True)
        if item['Image']!=job['target']['image'] or self.launch_hash(item)!=job['source']['launch_sha256']:
            raise Refused('RECOVERY_TARGET_CONFIGURATION_MISMATCH')
        self.runtime_hashes(job['target']['image'],job['manifest']['runtime_files'])
        self.helper('compare-live',folder/'recovery-check.json',extra=['--baseline',folder/'before-public.json'])
        if self.configuration_hash()!=self.expected_configuration(job):
            raise Refused('RECOVERY_COMPOSE_OR_ENV_CHANGED')
        self.verify_private(job)
        for name,expected in job['manifest']['runtime_files'].items():
            if sha(checked_path(self.project/name,False))!=expected:
                raise Refused('RECOVERY_STORAGE_RUNTIME_MISMATCH')
        return dict(can_resume_target=True,version=job['version'],schema=job['target_schema'],automatic_restore=False)
