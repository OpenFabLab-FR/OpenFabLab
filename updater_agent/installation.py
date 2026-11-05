"""One-time operator-authorized agent installation; never reachable from the web.

The operator provides a reviewed local policy and exact application manifest.
No migration is performed here: the application must already be 2.15/schema26.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from .docker_executor import DockerExecutor
from .security import Refused,checked_path,pack,private_json,load_policy
from .data_checks import compare_live
from .filesystem import sha,write_probe

AGENT_NAME='openfablab-updater-agent'
CHANNEL_TARGET='/run/openfablab-updater'
REPOSITORY_ID=1399693198

def validate_layout(policy):
    project=checked_path(policy['project']);data=checked_path(policy['data']);backups=checked_path(policy['backups'])
    state=checked_path(policy['state'],False);shared=checked_path(Path(policy['socket']).parent,False)
    if Path(policy['token_file']).parent!=shared:raise Refused('AGENT_CHANNEL_LAYOUT_INVALID')
    if (state==shared or state.is_relative_to(shared) or shared.is_relative_to(state)
            or any(p==root or p.is_relative_to(root) or root.is_relative_to(p) for p in (state,shared) for root in (project,data,backups))):
        raise Refused('AGENT_DIRECTORIES_MUST_BE_INDEPENDENT')
    if Path(policy['database'])!=data/'openfablab.db' or not Path(policy['compose_file']).is_relative_to(project):
        raise Refused('AGENT_PRODUCTION_LAYOUT_UNRECOGNIZED')
    for directory in (state,shared):
        if directory.exists() and (not directory.is_dir() or directory.stat().st_uid!=0 or directory.stat().st_mode & 0o022):
            raise Refused('AGENT_DIRECTORY_OWNERSHIP_UNSAFE')

def channel_configuration(configuration,service,shared):
    value=copy.deepcopy(configuration)
    try:item=value['services'][service]
    except (KeyError,TypeError):raise Refused('AGENT_COMPOSE_SERVICE_UNKNOWN') from None
    environment=item.get('environment') or {}
    if not isinstance(environment,dict):raise Refused('AGENT_COMPOSE_ENVIRONMENT_UNRECOGNIZED')
    if any(key in environment for key in ('OPENFABLAB_UPDATE_SOCKET','OPENFABLAB_UPDATE_TOKEN_FILE')):
        raise Refused('AGENT_CHANNEL_ALREADY_CONFIGURED_REVIEW_REQUIRED')
    environment.update(OPENFABLAB_UPDATE_SOCKET=CHANNEL_TARGET+'/agent.sock',OPENFABLAB_UPDATE_TOKEN_FILE=CHANNEL_TARGET+'/token')
    item['environment']=environment
    volumes=item.setdefault('volumes',[])
    if not isinstance(volumes,list) or any(not isinstance(v,dict) for v in volumes):
        raise Refused('AGENT_RESOLVED_COMPOSE_VOLUMES_REQUIRED')
    if any(v.get('target') in (CHANNEL_TARGET,'/var/run/docker.sock') for v in volumes):raise Refused('AGENT_CHANNEL_MOUNT_CONFLICT')
    volumes.append(dict(type='bind',source=str(shared),target=CHANNEL_TARGET,read_only=True,bind=dict(create_host_path=False)))
    return value

def expected_launch(item,shared):
    value=copy.deepcopy(item)
    value['Config']['Env']=[*value['Config'].get('Env',[]),'OPENFABLAB_UPDATE_SOCKET='+CHANNEL_TARGET+'/agent.sock','OPENFABLAB_UPDATE_TOKEN_FILE='+CHANNEL_TARGET+'/token']
    value['Mounts'].append(dict(Type='bind',Source=str(shared),Destination=CHANNEL_TARGET,RW=False))
    return value

def agent_command(policy,image):
    shared=Path(policy['socket']).parent
    command=['run','-d','--name',AGENT_NAME,'--restart','unless-stopped','--read-only','--cap-drop','ALL','--cap-add','DAC_OVERRIDE','--security-opt','no-new-privileges',
        '-e','OPENFABLAB_UPDATER_EXPECTED_CAPABILITY=DAC_OVERRIDE',
        '--log-driver','json-file','--log-opt','max-size=5m','--log-opt','max-file=2',
        '--tmpfs','/tmp:rw,nosuid,nodev','--mount','type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock']
    mounts={(policy[key],policy[key],key=='docker_root') for key in ('project','data','backups','state','docker_root')}
    mounts.add((str(shared),str(shared),False))
    for source,target,readonly in sorted(mounts):command+=['--mount','type=bind,source='+source+',target='+target+(',readonly' if readonly else '')]
    return command+['--entrypoint','python',image,'-m','updater_agent','--policy',str(Path(policy['state'])/'policy.json'),'--helper-image',image,'serve']

def check(policy,manifest,executor,report_root):
    """All production/backups mounts must be read-only in the check launcher."""
    validate_layout(policy)
    if manifest.get('version')!='2.15.0' or manifest.get('schema')!=26 or manifest.get('agent_protocol')!=1:
        raise Refused('AGENT_INSTALL_REQUIRES_APPROVED_2_15_SCHEMA26')
    if policy.get('repository_id')!=REPOSITORY_ID:raise Refused('AGENT_OFFICIAL_REPOSITORY_ID_MISMATCH')
    root=Path(report_root)
    if not root.is_dir() or root.is_symlink():raise Refused('AGENT_REPORT_DIRECTORY_REQUIRED')
    item=executor.container()
    if item['HostConfig'].get('Privileged') or item['HostConfig'].get('CapAdd') or any(m['Destination']=='/var/run/docker.sock' or m.get('Source')=='/var/run/docker.sock' for m in item['Mounts']):
        raise Refused('WEB_CONTAINER_PRIVILEGES_UNSAFE')
    if executor.run(['ps','-a','--filter','name=^/'+AGENT_NAME+'$','--format','{{.ID}}']).strip():
        raise Refused('AGENT_CONTAINER_ALREADY_EXISTS_REVIEW_REQUIRED')
    if not any(m['Destination']=='/data' and m['Source']==policy['data'] and m['RW'] for m in item['Mounts']):raise Refused('DATA_VOLUME_MISMATCH')
    for name,expected in manifest['runtime_files'].items():
        path=checked_path(Path(policy['project'])/name,False)
        if not path.is_file() or sha(path)!=expected:raise Refused('AGENT_INSTALL_STORAGE_RUNTIME_MISMATCH')
    executor.runtime_hashes(item['Id'],manifest['runtime_files'],active=True)
    executor.runtime_hashes(item['Image'],manifest['runtime_files'])
    executor.helper('snapshot',root/'database-before-agent.json',extra=['--schema',26])
    executor.preflight(dict(id=root.name,source=dict(image=item['Image']),result='preparing'))
    # Confirm that the actual CLI/Compose combination can render the existing
    # project; never infer compatibility just from a file being executable.
    configuration=json.loads(executor.compose(['config','--format','json']))
    if configuration.get('name')!=(item['Config'].get('Labels') or {}).get('com.docker.compose.project'):
        raise Refused('AGENT_COMPOSE_PROJECT_IDENTITY_MISMATCH')
    shared=Path(policy['socket']).parent
    channel_configuration(configuration,policy['service'],shared)
    from .relay_check import check as relay_check
    relay_check(executor.database,executor.data,report=root/'wordpress-stages.json')
    if len(os.fsencode(policy['socket']))>=100:raise Refused('AGENT_UNIX_SOCKET_PATH_TOO_LONG')
    return dict(success=True,version='2.15.0',schema=26,production_modified=False,image=item['Image'],container=item['Id'])

def build_image(executor,folder,web_image,docker_cli,compose_cli):
    """Use approved web dependencies plus fixed agent code and host CLI tools."""
    folder=checked_path(folder)
    context=folder/'agent-build';context.mkdir(mode=0o700)
    bundle=context/'bundle';agent=bundle/'opt/agent';agent.mkdir(parents=True,mode=0o700)
    import update_wire
    shutil.copy2(update_wire.__file__,agent/'update_wire.py')
    code=agent/'updater_agent';code.mkdir(mode=0o700)
    for source in Path(__file__).parent.glob('*.py'):
        if source.is_symlink():raise Refused('AGENT_INSTALL_SOURCE_UNSAFE')
        shutil.copy2(source,code/source.name)
    for source,target in ((docker_cli,bundle/'usr/local/bin/docker'),(compose_cli,bundle/'usr/local/lib/docker/cli-plugins/docker-compose')):
        source=checked_path(source,False)
        if not source.is_file():raise Refused('HOST_DOCKER_CLI_OR_COMPOSE_MISSING')
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o700);shutil.copy2(source,target);target.chmod(0o755)
    text='FROM '+web_image+'\nCOPY bundle/ /\nUSER 0\nENV PYTHONPATH=/opt/agent:/app PYTHONDONTWRITEBYTECODE=1\nWORKDIR /opt/agent\nHEALTHCHECK NONE\n'
    (context/'Dockerfile').write_text(text)
    tag='openfablab:local-agent-215-'+hashlib.sha256(text.encode()+pack({str(p.relative_to(bundle)):sha(p) for p in bundle.rglob('*') if p.is_file()})).hexdigest()[:12]
    executor.run(['build','--file',str(context/'Dockerfile'),'--tag',tag,str(context)],timeout=1800)
    image=json.loads(executor.run(['image','inspect',tag]))[0]
    layers=image.get('RootFS',{}).get('Layers')
    if not isinstance(layers,list) or len(layers)>=125:raise Refused('AGENT_IMAGE_LAYER_BUDGET_REFUSED')
    # Run the baked-in client against the daemon before any web interruption.
    for command in (['version'],['compose','version']):
        executor.run(['run','--rm','--read-only','--network','none','--mount','type=bind,source=/var/run/docker.sock,target=/var/run/docker.sock',
            '--entrypoint','/usr/local/bin/docker',image['Id'],'--host','unix:///var/run/docker.sock',*command])
    private_json(folder/'agent-image.json',dict(image=image['Id'],layers=len(layers),host_cli_sha256=sha(docker_cli),host_compose_sha256=sha(compose_cli)))
    return image['Id']

def install(policy,manifest,executor,folder,agent_image,confirmation):
    """Independent explicit confirmation; preserves state rather than restoring."""
    if confirmation!='AUTHORIZE-LOCAL-AGENT-2.15.0':raise Refused('AGENT_INSTALL_EXPLICIT_CONFIRMATION_REQUIRED')
    state=Path(policy['state']);shared=Path(policy['socket']).parent;folder=Path(folder)
    if (state/'current.json').exists() or (state/'agent-installation.json').exists() or Path(policy['token_file']).exists():raise Refused('AGENT_INSTALL_ALREADY_STARTED_NO_OVERWRITE')
    prepared=state/'prepared-agent.json'
    if not prepared.is_file() or prepared.is_symlink():raise Refused('AGENT_PREPARATION_RECEIPT_REQUIRED')
    preparation=json.loads(prepared.read_bytes())
    if (preparation.get('image')!=agent_image or preparation.get('manifest_sha256')!=hashlib.sha256(pack(manifest)).hexdigest()
            or preparation.get('source_image')!=executor.container()['Image']):
        raise Refused('AGENT_PREPARATION_IDENTITY_CHANGED')
    check(policy,manifest,executor,folder)
    before=executor.container();compose=Path(policy['compose_file'])
    original=compose.read_bytes();configuration=json.loads(executor.compose(['config','--format','json']))
    expected=expected_launch(before,shared)
    from .channel_normalization import checked_configuration
    replacement=checked_configuration(executor,configuration,policy['service'],shared,folder,channel_configuration)
    for root in (executor.project,executor.data,executor.backups):write_probe(root)
    for directory in (state,shared):
        checked_path(directory,False);directory.mkdir(mode=0o700,exist_ok=True)
        if directory.stat().st_uid!=0:raise Refused('AGENT_DIRECTORY_OWNERSHIP_UNSAFE')
    # setgid makes future sockets inherit the approved web group, so the
    # long-running agent does not need CAP_CHOWN just to recreate its socket.
    os.chown(shared,0,policy['web_gid']);shared.chmod(0o2750)
    token=Path(policy['token_file'])
    with token.open('xb') as stream:stream.write(os.urandom(48));stream.flush();os.fsync(stream.fileno())
    os.chown(token,0,policy['web_gid']);token.chmod(0o640)
    private_json(state/'policy.json',policy)
    load_policy(state/'policy.json')
    backup=executor.backups/('PRE-AGENT-'+str(int(time.time())))
    executor.helper('backup',folder/'pre-agent-backup.json',access='rw',extra=['--destination',backup,'--project',executor.project,
        '--compose',compose,'--version','2.15.0','--schema',26])
    executor.run(['image','save','--output',str(backup/'source-image.tar'),before['Image']],timeout=1800)
    if not (backup/'source-image.tar').is_file() or (backup/'source-image.tar').stat().st_size<=0:raise Refused('AGENT_PRE_IMAGE_BACKUP_FAILED')
    (backup/'source-image.tar').chmod(0o600)
    (folder/'compose-before-agent.private').write_bytes(original);(folder/'compose-before-agent.private').chmod(0o600)
    receipt=dict(phase='before_channel_installation',schema=26,version='2.15.0',image=before['Image'],agent_image=agent_image,
        configuration_before_sha256=executor.configuration_hash(),production_stop_attempted=True,public_restart_attempted=False,
        backup=backup.name,automatic_restore=False)
    private_json(state/'agent-installation.json',receipt)
    try:
        executor.run(['stop','--time','45',before['Id']],timeout=90)
        if json.loads(executor.run(['inspect',before['Id']]))[0]['State']['Running']:raise Refused('AGENT_INSTALL_SOURCE_STOP_UNCONFIRMED')
        temporary=compose.with_name('.'+compose.name+'.agent-channel')
        try:
            with temporary.open('xb') as stream:stream.write(pack(replacement)+b'\n');stream.flush();os.fsync(stream.fileno())
            # Resolved Compose may contain formerly interpolated environment
            # values. It must never inherit a world-readable source file mode.
            temporary.chmod(0o600);os.replace(temporary,compose)
        finally:
            if temporary.exists():temporary.unlink()
        receipt.update(phase='channel_installed',public_restart_attempted=True);private_json(state/'agent-installation.json',receipt)
        started=int(time.time())
        executor.compose(['up','-d','--no-build','--pull','never','--no-deps',policy['service']])
        private_json(folder/'compose-target.json',dict(services={policy['service']:{'image':before['Image']}}))
        job=dict(id=folder.name,source={'launch_sha256':executor.launch_hash(expected)},target={'image':before['Image']},manifest=manifest)
        executor.health(job)
        executor.helper('compare-live',folder/'after-agent-start.json',extra=['--baseline',folder/'database-before-agent.json'])
        from .relay_check import check as relay_check
        relay_check(executor.database,executor.data,started=started,report=folder/'wordpress-stages.json')
        executor.helper('compare-live',folder/'after-agent-relay.json',extra=['--baseline',folder/'database-before-agent.json'])
        # Only this operator-authorized installation enrolls the observed image.
        # All executable bytes must match the approved manifest beforehand.
        permanent=DockerExecutor(policy|{'docker':executor.policy['docker']},agent_image);permanent.enroll(manifest)
        executor.run(agent_command(policy,agent_image))
        from updater_client import request as call
        deadline=time.monotonic()+30
        while True:
            try:call('status',{},policy['socket'],policy['token_file']);break
            except Refused:
                if time.monotonic()>=deadline:raise Refused('AGENT_SERVICE_CHANNEL_UNVERIFIED')
                time.sleep(1)
        executor.helper('backup',folder/'post-agent-backup.json',access='rw',extra=['--destination',executor.backups/('POST-AGENT-'+folder.name),
            '--project',executor.project,'--compose',compose,'--version','2.15.0','--schema',26])
        receipt.update(phase='success',result='AGENT_INSTALLATION_SUCCESS',automatic_update=False)
        private_json(state/'agent-installation.json',receipt)
        return dict(success=True,agent_installed=True,automatic_update=False,schema=26)
    except Exception as error:
        receipt.update(phase='failed_preserved',result='HUMAN_REVIEW_REQUIRED',code=error.code if isinstance(error,Refused) else 'AGENT_INSTALLATION_FAILED')
        private_json(state/'agent-installation.json',receipt)
        # No DB restoration, migration or old-image restart. Preserve new writes.
        raise Refused(receipt['code']) from None
