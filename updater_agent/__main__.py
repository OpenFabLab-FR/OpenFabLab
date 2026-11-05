"""Independent operator entry point: serve, diagnose, resume, disable or enroll."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import stat
import sys
import threading
import secrets
from .docker_executor import DockerExecutor
from .engine import Engine
from .releases import OfficialReleases
from .security import Refused,load_policy,pack,private_json
from .service import Service


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--policy',required=True)
    parser.add_argument('--helper-image',required=True)
    sub=parser.add_subparsers(dest='operation',required=True)
    sub.add_parser('serve')
    sub.add_parser('disable')
    enable=sub.add_parser('enable');enable.add_argument('--confirm',required=True)
    enroll=sub.add_parser('enroll');enroll.add_argument('--manifest',required=True);enroll.add_argument('--confirm',required=True)
    diagnostic=sub.add_parser('diagnose');diagnostic.add_argument('--job',required=True)
    resume=sub.add_parser('resume');resume.add_argument('--job',required=True);resume.add_argument('--confirm',required=True)
    initial=sub.add_parser('setup-check');initial.add_argument('--manifest',required=True)
    prepare=sub.add_parser('setup-prepare');prepare.add_argument('--manifest',required=True);prepare.add_argument('--docker-cli',required=True);prepare.add_argument('--compose-cli',required=True)
    install=sub.add_parser('setup-install');install.add_argument('--manifest',required=True);install.add_argument('--confirm',required=True)
    args=parser.parse_args()
    from .privileges import validate_if_expected
    nnp_evidence=validate_if_expected()
    if os.geteuid()!=0:
        raise Refused('LOCAL_ADMINISTRATOR_REQUIRED')
    policy=load_policy(args.policy)
    if nnp_evidence is not None:private_json(Path(policy['state'])/'agent-no-new-privileges.json',nnp_evidence)
    executor=DockerExecutor(policy,args.helper_image)
    engine=Engine(policy,OfficialReleases(policy['repository_id']),executor)
    if args.operation.startswith('setup-'):
        from . import installation
        manifest_path=Path(args.manifest)
        if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_uid!=0 or manifest_path.stat().st_mode & 0o022:
            raise Refused('AGENT_ENROLLMENT_MANIFEST_OWNERSHIP_UNSAFE')
        manifest=json.loads(manifest_path.read_bytes())
        folder=engine.root/secrets.token_hex(16);folder.mkdir(mode=0o700)
        try:
            with engine.locked():
                if args.operation=='setup-check':result=installation.check(policy,manifest,executor,folder)
                elif args.operation=='setup-prepare':
                    installation.check(policy,manifest,executor,folder)
                    identity=installation.build_image(executor,folder,executor.container()['Image'],args.docker_cli,args.compose_cli)
                    private_json(engine.root/'prepared-agent.json',dict(image=identity,manifest_sha256=__import__('hashlib').sha256(pack(manifest)).hexdigest(),
                        source_image=executor.container()['Image'],created_at=__import__('time').time()))
                    result=dict(success=True,agent_image=identity,production_modified=False)
                else:result=installation.install(policy,manifest,executor,folder,args.helper_image,args.confirm)
            private_json(folder/'setup-result.json',result)
            print(pack(result).decode());return 0
        except Exception as error:
            private_json(folder/'setup-result.json',dict(success=False,code=error.code if isinstance(error,Refused) else 'AGENT_SETUP_FAILED'))
            raise
    if args.operation=='disable':
        private_json(engine.root/'disabled',dict(disabled=True))
        print('AGENT_DISABLED_NO_NEW_UPDATE_ACCEPTED');return 0
    if args.operation=='enable':
        if args.confirm!='ENABLE-LOCAL-OPENFABLAB-AGENT':raise Refused('AGENT_ENABLE_CONFIRMATION_REQUIRED')
        (engine.root/'disabled').unlink(missing_ok=True)
        print('AGENT_ENABLED');return 0
    if args.operation=='enroll':
        if args.confirm!='AUTHORIZE-APPROVED-LOCAL-OPENFABLAB':raise Refused('AGENT_ENROLLMENT_CONFIRMATION_REQUIRED')
        manifest_path=Path(args.manifest)
        if manifest_path.is_symlink() or manifest_path.stat().st_uid!=0 or manifest_path.stat().st_mode & 0o022:
            raise Refused('AGENT_ENROLLMENT_MANIFEST_OWNERSHIP_UNSAFE')
        result=executor.enroll(json.loads(manifest_path.read_bytes()))
    elif args.operation=='diagnose':
        result=engine.recovery_diagnostic(args.job)
    elif args.operation=='resume':
        result=engine.resume(args.job,args.confirm)
    else:
        executor.capability_preflight()
        # The daemon lock is acquired before removing a demonstrably stale
        # agent-owned socket. It is never a broad removal of a shared directory.
        with (engine.root/'daemon.lock').open('a+') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise Refused('AGENT_DAEMON_ALREADY_RUNNING') from None
            socket_path=Path(policy['socket'])
            if socket_path.exists() or socket_path.is_symlink():
                info=socket_path.lstat()
                if info.st_uid!=0 or not stat.S_ISSOCK(info.st_mode):raise Refused('AGENT_SOCKET_PATH_UNSAFE')
                socket_path.unlink()
            token_path=Path(policy['token_file'])
            if token_path.is_symlink() or token_path.stat().st_uid!=0 or token_path.stat().st_mode & 0o007:
                raise Refused('AGENT_TOKEN_PERMISSIONS_UNSAFE')
            server=Service(engine,token_path.read_bytes(),socket_path,policy['web_gid'])
            def stop(*_):threading.Thread(target=server.shutdown,daemon=True).start()
            signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
            try:server.serve_forever(poll_interval=.5)
            finally:
                server.server_close()
                if socket_path.exists() and stat.S_ISSOCK(socket_path.lstat().st_mode):socket_path.unlink()
        return 0
    # All returned values are the safe diagnostic/phase projection, not private
    # settings, environment, backup contents or exception tracebacks.
    print(pack(result).decode());return 0


if __name__=='__main__':
    try:sys.exit(main())
    except Exception as error:
        print('AGENT_REFUSED='+(error.code if isinstance(error,Refused) else 'UNCLASSIFIED_AGENT_OPERATION_FAILED'))
        sys.exit(1)
