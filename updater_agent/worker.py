"""Fixed helper operations inside a restricted container, never a shell API."""
import argparse
import contextlib
import io
import json
import os
import re
from pathlib import Path
import sqlite3
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from .data_checks import snapshot, compare_before_open, compare_live
from .filesystem import coherent_copy, inventory, sha
from .security import Refused, private_json, version
from .diagnostics import describe,read_context,runtime,step
from .privileges import validate_if_expected


def isolate(database,runtime):
    os.environ.update(OPENFABLAB_DATABASE=str(database),OPENFABLAB_SECRET_KEY_FILE=str(database.parent/'.secret_key'),
        OPENFABLAB_EXTERNAL_ACTIONS='0',OPENFABLAB_ENABLE_SCHEDULER='0',OPENFABLAB_ENABLE_WEATHER='0',PYTHONDONTWRITEBYTECODE='1')
    def deny(event,args):
        if event=='socket.getaddrinfo' and args[0]=='127.0.0.1':return
        if event in ('socket.connect','socket.sendto') and isinstance(args[-1],tuple) and args[-1][0]=='127.0.0.1':return
        if event in ('socket.connect','socket.sendto','socket.getaddrinfo'):
            raise OSError('ISOLATED_HELPER_NETWORK_DENIED')
    sys.addaudithook(deny)
    sys.path.insert(0,str(runtime))

GUNICORN_PROBE="""import sys
def deny(event,args):
 if event not in ('socket.connect','socket.sendto','socket.getaddrinfo'):return
 host=args[0] if event=='socket.getaddrinfo' else args[-1][0] if isinstance(args[-1],tuple) else None
 if host!='127.0.0.1':raise OSError('ISOLATED_HTTP_EXTERNAL_NETWORK_DENIED')
sys.addaudithook(deny)
port=sys.argv[1]
sys.argv=['gunicorn','--bind=127.0.0.1:'+port,'--workers=1','--threads=2','--timeout=15','--graceful-timeout=3','app:app']
from gunicorn.app.wsgiapp import run
run()
"""

def http_probe(runtime,manifest):
    # The Docker helper has --network none (loopback only). The explicit audit
    # also protects the identical native test on a developer workstation.
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
    process=subprocess.Popen([sys.executable,'-c',GUNICORN_PROBE,str(port)],cwd=runtime,env=os.environ.copy(),
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    try:
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if process.poll() is not None:raise Refused('ISOLATED_GUNICORN_START_FAILED')
            for prefix in ('/stat',''):
                try:
                    with urllib.request.urlopen('http://127.0.0.1:'+str(port)+prefix+'/sante',timeout=.5) as response:
                        if response.status!=200 or response.read(1024)!=b'OK\n':continue
                    with urllib.request.urlopen('http://127.0.0.1:'+str(port)+prefix+'/',timeout=2) as response:
                        if response.status==200 and ('V'+manifest['version']).encode() in response.read(2000000):
                            return dict(server='gunicorn',transport='real_loopback_http',public_port=False,network='none')
                except (OSError,ValueError):pass
            time.sleep(.1)
        raise Refused('ISOLATED_GUNICORN_HTTP_FAILED')
    finally:
        # Kill only the process group created for this isolated probe. Never
        # signal a production PID or leave test workers running after a pause.
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()


def migrate(database,runtime,baseline,manifest):
    isolate(database,runtime)
    import family_model
    if family_model.SCHEMA!=manifest['schema']:
        raise Refused('MIGRATION_API_SCHEMA_MISMATCH')
    with sqlite3.connect(database) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
        if db.execute('PRAGMA user_version').fetchone()[0] not in manifest['source_schemas']:
            raise Refused('MIGRATION_SOURCE_SCHEMA_REFUSED')
        family_model.backup_before(db,database)
        family_model.migrate(db)
    return compare_before_open(database,baseline,manifest)


def probe(data,destination,runtime,manifest,prepared=False):
    if not prepared:coherent_copy(data,destination)
    database=destination/'openfablab.db'
    before=snapshot(database)
    if before['schema']==manifest['schema']:
        isolate(database,runtime)
        import family_model
        if family_model.SCHEMA!=manifest['schema']:
            raise Refused('MIGRATION_API_SCHEMA_MISMATCH')
    else:
        migrate(database,runtime,before,manifest)
    # Real target application startup in the helper network namespace, workers
    # off. No neutralization of source data or source credentials is performed.
    # They remain only in this private copy; transport is denied before import.
    import app
    application=app.create_app(dict(DATABASE=str(database),SECRET_KEY_FILE=str(destination/'.secret_key'),
        ADMIN_PIN=None,MODERATOR_PIN=None,SEED_DEMO_USERS=False,TESTING=True,WEATHER_ENABLED=False,AUTO_CLOSURE_WORKER=False))
    if application.config['APP_VERSION']!='V'+manifest['version'] or application.config.get('EXTERNAL_ACTIONS') is not False:
        raise Refused('ISOLATED_RUNTIME_IDENTITY_FAILED')
    for path in ('/sante','/','/admin/connexion'):
        if application.test_client().get(path).status_code!=200:
            raise Refused('ISOLATED_HTTP_FAILED')
    http=http_probe(runtime,manifest)
    result=compare_before_open(database,before,manifest)
    return dict(success=True,version=manifest['version'],schema=result['schema'],network='none',workers=False,http=http)


def backup(data,destination,project,app_version,schema,*,cold=False,compose=None,override=None):
    from private_backup import create_backup,validate_backup
    destination=Path(destination)
    if destination.exists():
        raise Refused('BACKUP_DESTINATION_EXISTS')
    destination.mkdir(mode=0o700)
    copy=destination/'persistent-state'
    coherent_copy(data,copy)
    snapshot(copy/'openfablab.db',schema)
    archive=destination/'installation-private.zip'
    create_backup(copy/'openfablab.db',archive,app_version=app_version)
    restored=destination/'restoration-test'
    validate_backup(archive,restored)
    snapshot(restored/'openfablab.db',schema)
    # Keep explicit source/Compose configuration outside the data backup too.
    # These files are private and never exposed through agent.status or the web.
    configuration=destination/'configuration';configuration.mkdir(mode=0o700)
    compose=Path(compose) if compose else project/'compose.yaml'
    for name,source in (('private.env',project/'.env'),('compose-source'+compose.suffix,compose),('compose-active-override.json',Path(override) if override else project/'.absent-agent-override')):
        if source.is_file() and not source.is_symlink():
            target=configuration/name;target.write_bytes(source.read_bytes());target.chmod(0o600)
    private_json(destination/'backup-receipt.json',dict(sha256=sha(archive),schema=schema,version=app_version,
        restoration_test=True,cold=cold,persistent=inventory(copy),configuration=inventory(configuration)))
    return dict(success=True,sha256=sha(archive),restoration_test=True,schema=schema)


def write_preflight(database,project,backups,state):
    """Explicit-update only. No bytes are written to an existing SQLite file."""
    from .filesystem import write_probe
    for role,root in (('PROJECT',project),('DATA',database.parent),('BACKUPS',backups),('STATE',state)):
        try:write_probe(root)
        except Refused as error:raise Refused(role+'_'+error.code) from None
    opened=0
    for suffix in ('','-wal','-shm','-journal'):
        path=Path(str(database)+suffix)
        if suffix and not path.exists():continue
        if path.is_symlink() or not path.is_file():raise Refused('WRITE_PREFLIGHT_DATABASE_FILE_UNSAFE')
        try:
            descriptor=os.open(path,os.O_RDWR|os.O_NOFOLLOW)
            os.close(descriptor);opened+=1
        except OSError:raise Refused('WRITE_PREFLIGHT_EXISTING_DATABASE_ACCESS_REFUSED') from None
    return dict(success=True,directory_io_verified=True,existing_database_files_opened=opened,
        existing_database_bytes_written=False,backup_restoration_still_required=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('operation',choices=['snapshot','probe','probe-copy','migrate','compare','compare-live','backup','write-preflight'])
    parser.add_argument('--database',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--runtime')
    parser.add_argument('--baseline')
    parser.add_argument('--manifest')
    parser.add_argument('--destination')
    parser.add_argument('--project')
    parser.add_argument('--compose')
    parser.add_argument('--override')
    parser.add_argument('--version')
    parser.add_argument('--schema',type=int)
    parser.add_argument('--cold',action='store_true')
    parser.add_argument('--prepared-copy',action='store_true')
    parser.add_argument('--diagnostic-id')
    args=parser.parse_args()
    if args.diagnostic_id is not None and not re.fullmatch('[0-9a-f]{32}',args.diagnostic_id):parser.error('DIAGNOSTIC_ID_INVALID')
    database=Path(args.database);output=Path(args.output)
    context={}
    diagnostic_output=output.with_name(output.stem+'.diagnostic.json')
    try:
        with step('CAPABILITY_PROFILE'):nnp_evidence=validate_if_expected()
        with step('DATABASE_METADATA'):context=read_context(database)
        if nnp_evidence is not None:context['no_new_privileges']=nnp_evidence
        with step('WORKER_INPUT'):
            manifest=json.loads(Path(args.manifest).read_bytes()) if args.manifest else None
            before=json.loads(Path(args.baseline).read_bytes()) if args.baseline else None
        if args.operation=='backup' and args.runtime:
            # The already-verified target's backup reader understands its own
            # schema/version, while an old runtime still refuses newer restores.
            sys.path.insert(0,args.runtime)
        # No application messages/tracebacks can leak secrets into Docker logs.
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            if args.operation=='snapshot':result=snapshot(database,args.schema)
            elif args.operation=='probe':result=probe(database.parent,Path(args.destination),Path(args.runtime),manifest,args.prepared_copy)
            elif args.operation=='probe-copy':
                destination=Path(args.destination)
                coherent_copy(database.parent,destination)
                value=snapshot(destination/'openfablab.db',args.schema)
                result=dict(success=True,schema=value['schema'])
            elif args.operation=='migrate':result=migrate(database,Path(args.runtime),before,manifest)
            elif args.operation=='compare':result=compare_before_open(database,before,manifest)
            elif args.operation=='compare-live':result=compare_live(database,before)
            elif args.operation=='write-preflight':result=write_preflight(database,Path(args.project),Path(args.destination),output.parent)
            else:result=backup(database.parent,Path(args.destination),Path(args.project),args.version,args.schema,cold=args.cold,compose=args.compose,override=args.override)
        with step('OUTPUT_PERSIST'):
            private_json(output,result)
            private_json(diagnostic_output,dict(success=True,operation=args.operation,request_id=args.diagnostic_id,read_context=context,**runtime()))
    except Exception as error:
        diagnostic=describe(error,operation=args.operation,request_id=args.diagnostic_id)
        try:
            private_json(output,dict(success=False,code=diagnostic['code'],diagnostic=diagnostic))
            private_json(diagnostic_output,dict(success=False,diagnostic=diagnostic,read_context=context))
        except Exception as persistence_error:
            # Never downgrade a failed fsync/write into a successful check.
            diagnostic=describe(persistence_error,phase='OUTPUT_PERSIST',operation=args.operation,request_id=args.diagnostic_id)
        # One validated envelope survives result-directory failure. No original
        # exception message, path, SQL, traceback or row is emitted.
        print('OFL_HELPER_DIAGNOSTIC='+json.dumps(diagnostic,sort_keys=True,separators=(',',':')));return 1
    print('HELPER_OK='+args.operation);return 0


if __name__=='__main__':
    sys.exit(main())
