"""Correlated fixed-vocabulary selftest reports, never raw Docker/Python logs."""
import inspect
import json
import re
import sqlite3
from .security import Refused
from .no_new_privileges import FAILURE_CODES,kernel_nnp,decide_nnp,observe_nnp,validated_nnp

PHASES={'IMPORTS','IDENTITY','CAPABILITY_METADATA','CAPABILITY_PROFILE','NO_NEW_PRIVILEGES','FIXTURE_METADATA',
    'NEGATIVE_ACCESS','SQLITE_OPEN','SQLITE_SCHEMA','SQLITE_INTEGRITY','READONLY_GUARD',
    'WRITE_CREATE','WRITE_FSYNC','WRITE_VERIFY','WRITE_RENAME','WRITE_REMOVE','DONE'}
CODES={'SELFTEST_OK','SELFTEST_EXCEPTION','SELFTEST_UID_NOT_ROOT','SELFTEST_NO_NEW_PRIVILEGES_MISMATCH',
    'SELFTEST_NEGATIVE_STAT_ACCESSIBLE','SELFTEST_NEGATIVE_OPEN_ACCESSIBLE','SELFTEST_NEGATIVE_STAT_ERRNO',
    'SELFTEST_NEGATIVE_OPEN_ERRNO','SELFTEST_SQLITE_SCHEMA_MISMATCH','SELFTEST_SQLITE_INTEGRITY_FAILED',
    'SELFTEST_READONLY_OPEN_ALLOWED','SELFTEST_READONLY_WRONG_ERRNO','SELFTEST_WRITE_CONTENT_MISMATCH',
    *{'SELFTEST_'+key+'_'+suffix for key in ('CAP_EFF','CAP_PRM','CAP_BND','CAP_INH','CAP_AMB') for suffix in ('MISSING','INVALID','MISMATCH')}}
CODES.update('SELFTEST_'+code for code in FAILURE_CODES)
TYPES={'NONE','PermissionError','FileNotFoundError','OSError','OperationalError','DatabaseError','RuntimeError',
    'ValueError','TypeError','KeyError','ImportError','ModuleNotFoundError','OTHER'}
BOOLS={'uid_is_root','gid_is_root','directory_owner_matches','directory_group_matches','acl_marker_present',
    'stat_denied','open_denied','integrity_ok','readonly_refused','fsync_done','probe_read_matches','renamed','removed'}
NUMBERS={'cap_eff','cap_prm','cap_bnd','cap_inh','cap_amb','nnp','seccomp_mode','stat_errno','open_errno','readonly_errno','sqlite_schema'}
TRANSPORT_PHASES={'DOCKER_LAUNCH','DOCKER_CLIENT','SELFTEST_PROTOCOL','SELFTEST_NO_START_PROOF'}

class CapabilityRefused(Refused):
    def __init__(self,value):
        super().__init__(value['code'])
        script=value.get('script')
        phase=script['phase'] if script else {'DOCKER_LAUNCH':'DOCKER_LAUNCH','DOCKER_CLIENT':'DOCKER_CLIENT','SCRIPT':'SELFTEST_PROTOCOL','UNDETERMINED':'SELFTEST_NO_START_PROOF'}[value['origin']]
        self.diagnostic=dict(code=value['code'],context=value['context'],phase=phase,docker_exit_code=value['docker_exit_code'],
            script_started=value['script_started'],sqlite_errorname=script['sqlite_errorname'] if script else None)

def execute_fixture():
    import sys
    if len(sys.argv)!=3:return 2
    nonce,mode=sys.argv[1:]
    if len(nonce)!=32 or any(c not in '0123456789abcdef' for c in nonce) or mode not in ('denied','read','write'):return 2
    print('OFL_CAPABILITY_STARTED='+nonce,flush=True)
    import json
    record=dict(format=1,request_id=nonce,context=mode,success=False,phase='IMPORTS',code='SELFTEST_EXCEPTION',error_type='NONE',errno=None,
        sqlite_errorcode=None,sqlite_errorname=None,checks={})
    checks=record['checks']
    def need(condition,code):
        if not condition:record['code']=code;raise RuntimeError()
    try:
        import errno,os,pathlib,sqlite3
        database=pathlib.Path('/fixture/data/openfablab.db')
        record['phase']='IDENTITY';checks['uid_is_root']=os.geteuid()==0;checks['gid_is_root']=os.getegid()==0
        need(checks['uid_is_root'],'SELFTEST_UID_NOT_ROOT')
        record['phase']='CAPABILITY_METADATA'
        metadata={k:v.strip() for line in pathlib.Path('/proc/self/status').read_text().splitlines() if ':' in line for k,v in [line.split(':',1)]}
        for key in ('CapEff','CapPrm','CapBnd','CapInh','CapAmb'):
            label={'CapEff':'CAP_EFF','CapPrm':'CAP_PRM','CapBnd':'CAP_BND','CapInh':'CAP_INH','CapAmb':'CAP_AMB'}[key]
            if key not in metadata:
                if key in ('CapInh','CapAmb'):continue
                need(False,'SELFTEST_'+label+'_MISSING')
            value=metadata[key]
            need(1<=len(value)<=16 and all(c in '0123456789abcdefABCDEF' for c in value),'SELFTEST_'+label+'_INVALID')
            checks[label.lower()]=int(value,16)
        for key,label in (('Seccomp','seccomp_mode'),):
            value=metadata.get(key)
            checks[label]=int(value) if value in ('0','1','2') else None
        record['phase']='CAPABILITY_PROFILE';mask=0 if mode=='denied' else 2
        for key in ('cap_eff','cap_prm','cap_bnd'):need(checks[key]==mask,'SELFTEST_'+key.upper()+'_MISMATCH')
        record['phase']='NO_NEW_PRIVILEGES'
        evidence=observe_nnp(metadata);checks['nnp_evidence']=evidence;checks['nnp']=evidence['kernel_value']
        need(evidence['verified'],'SELFTEST_'+evidence['code'])
        record['phase']='FIXTURE_METADATA';info=database.parent.lstat()
        checks['directory_mode']=format(info.st_mode & 0o7777,'04o')
        checks['directory_owner_matches']=info.st_uid==os.geteuid()
        checks['directory_group_matches']=info.st_gid in {os.getegid(),*os.getgroups()}
        checks['acl_marker_present']=None
        try:checks['acl_marker_present']=any('acl' in n.lower() for n in os.listxattr(database.parent,follow_symlinks=False))
        except (OSError,AttributeError,NotImplementedError):pass
        if mode=='denied':
            record['phase']='NEGATIVE_ACCESS'
            for operation in ('stat','open'):
                checks[operation+'_denied']=False;checks[operation+'_errno']=None
                try:
                    if operation=='stat':database.stat()
                    else:
                        with database.open('rb'):pass
                except OSError as error:
                    checks[operation+'_denied']=error.errno==errno.EACCES
                    checks[operation+'_errno']=error.errno if type(error.errno) is int and 0<=error.errno<=4095 else None
            # Preserve the r3 negative stat requirement and also prove that a
            # real open is refused. Never accept a merely decorative mode000.
            need(checks['stat_denied'],'SELFTEST_NEGATIVE_STAT_ACCESSIBLE' if checks['stat_errno'] is None else 'SELFTEST_NEGATIVE_STAT_ERRNO')
            need(checks['open_denied'],'SELFTEST_NEGATIVE_OPEN_ACCESSIBLE' if checks['open_errno'] is None else 'SELFTEST_NEGATIVE_OPEN_ERRNO')
        else:
            record['phase']='SQLITE_OPEN'
            with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
                record['phase']='SQLITE_SCHEMA';checks['sqlite_schema']=db.execute('PRAGMA user_version').fetchone()[0]
                need(checks['sqlite_schema']==25,'SELFTEST_SQLITE_SCHEMA_MISMATCH')
                record['phase']='SQLITE_INTEGRITY';checks['integrity_ok']=db.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
                need(checks['integrity_ok'],'SELFTEST_SQLITE_INTEGRITY_FAILED')
            if mode=='read':
                record['phase']='READONLY_GUARD';checks['readonly_refused']=False;checks['readonly_errno']=None
                try:fd=os.open(database,os.O_RDWR|os.O_NOFOLLOW)
                except OSError as error:
                    checks['readonly_errno']=error.errno if type(error.errno) is int and 0<=error.errno<=4095 else None
                    checks['readonly_refused']=error.errno==errno.EROFS
                else:os.close(fd)
                need(checks['readonly_refused'],'SELFTEST_READONLY_OPEN_ALLOWED' if checks['readonly_errno'] is None else 'SELFTEST_READONLY_WRONG_ERRNO')
            else:
                path=database.parent/'own-probe';record['phase']='WRITE_CREATE'
                with path.open('xb') as stream:
                    stream.write(b'FICTIONAL_PROBE');stream.flush();record['phase']='WRITE_FSYNC';os.fsync(stream.fileno());checks['fsync_done']=True
                record['phase']='WRITE_VERIFY';checks['probe_read_matches']=path.read_bytes()==b'FICTIONAL_PROBE'
                need(checks['probe_read_matches'],'SELFTEST_WRITE_CONTENT_MISMATCH')
                record['phase']='WRITE_RENAME';renamed=path.with_name('own-renamed');path.rename(renamed);checks['renamed']=True
                record['phase']='WRITE_REMOVE';renamed.unlink();checks['removed']=True
        record.update(success=True,phase='DONE',code='SELFTEST_OK')
    except Exception as error:
        names={'PermissionError','FileNotFoundError','OSError','OperationalError','DatabaseError','RuntimeError','ValueError','TypeError','KeyError','ImportError','ModuleNotFoundError'}
        record['error_type']=type(error).__name__ if type(error).__name__ in names else 'OTHER'
        number=getattr(error,'errno',None)
        record['errno']=number if type(number) is int and 0<=number<=4095 else None
        sql=locals().get('sqlite3')
        if sql is not None and isinstance(error,sql.Error):
            number=getattr(error,'sqlite_errorcode',None);name=getattr(error,'sqlite_errorname',None)
            if type(number) is int and 0<=number<=2**31-1:record['sqlite_errorcode']=number
            if isinstance(name,str) and name.startswith('SQLITE_') and type(getattr(sql,name,None)) is int and getattr(sql,name)==number:record['sqlite_errorname']=name
    print('OFL_CAPABILITY_RESULT='+json.dumps(record,sort_keys=True,separators=(',',':')),flush=True)
    return 0 if record['success'] else 1

def fixture_script():
    return '\n'.join(inspect.getsource(function) for function in (kernel_nnp,decide_nnp,observe_nnp,execute_fixture))+'\nraise SystemExit(execute_fixture())\n'
FIXTURE_SCRIPT=fixture_script()

def validated(value,nonce,mode):
    fields={'format','request_id','context','success','phase','code','error_type','errno','sqlite_errorcode','sqlite_errorname','checks'}
    if not isinstance(value,dict) or set(value)!=fields or type(value['format']) is not int or value['format']!=1:return None
    if not isinstance(nonce,str) or not re.fullmatch('[a-f0-9]{32}',nonce) or mode not in ('denied','read','write'):return None
    if value['request_id']!=nonce or value['context']!=mode or type(value['success']) is not bool:return None
    for key,allowed in (('phase',PHASES),('code',CODES),('error_type',TYPES)):
        if not isinstance(value[key],str) or value[key] not in allowed:return None
    if value['errno'] is not None and (type(value['errno']) is not int or not 0<=value['errno']<=4095):return None
    if value['sqlite_errorcode'] is not None and (type(value['sqlite_errorcode']) is not int or not 0<=value['sqlite_errorcode']<=2**31-1):return None
    name=value['sqlite_errorname']
    if name is not None and (not isinstance(name,str) or not name.startswith('SQLITE_') or type(getattr(sqlite3,name,None)) is not int or getattr(sqlite3,name)!=value['sqlite_errorcode']):return None
    checks=value['checks']
    if not isinstance(checks,dict) or set(checks)-BOOLS-NUMBERS-{'directory_mode','nnp_evidence'}:return None
    for key,entry in checks.items():
        if key=='nnp_evidence':
            if validated_nnp(entry) is None:return None
        elif key in BOOLS:
            if entry is None and key=='acl_marker_present':continue
            if type(entry) is not bool:return None
        elif key in NUMBERS:
            if entry is None:continue
            maximum=2**64-1 if key.startswith('cap_') else 2**31-1
            if type(entry) is not int or not 0<=entry<=maximum:return None
        elif not isinstance(entry,str) or not re.fullmatch('[0-7]{4}',entry):return None
    if value['success']:
        mask=0 if mode=='denied' else 2
        if value['phase']!='DONE' or value['code']!='SELFTEST_OK' or value['error_type']!='NONE' or any(value[k] is not None for k in ('errno','sqlite_errorcode','sqlite_errorname')):return None
        if checks.get('uid_is_root') is not True or checks.get('nnp')!=1 or any(checks.get(k)!=mask for k in ('cap_eff','cap_prm','cap_bnd')):return None
        evidence=validated_nnp(checks.get('nnp_evidence'))
        if evidence is None or evidence['verified'] is not True or evidence['kernel_value']!=1:return None
        if mode=='denied' and any(checks.get(k+'_denied') is not True or checks.get(k+'_errno')!=13 for k in ('stat','open')):return None
        if mode!='denied' and (checks.get('sqlite_schema')!=25 or checks.get('integrity_ok') is not True):return None
        if mode=='read' and (checks.get('readonly_refused') is not True or checks.get('readonly_errno')!=30):return None
        if mode=='write' and any(checks.get(k) is not True for k in ('fsync_done','probe_read_matches','renamed','removed')):return None
    return value

def transport(stdout,exit_code,nonce,mode):
    marker=('OFL_CAPABILITY_STARTED='+nonce).encode();lines=stdout.splitlines() if isinstance(stdout,bytes) and len(stdout)<=8192 else []
    started=marker in lines;script=None
    if len(lines)==2 and lines[0]==marker and lines[1].startswith(b'OFL_CAPABILITY_RESULT='):
        try:script=validated(json.loads(lines[1][len(b'OFL_CAPABILITY_RESULT='):]),nonce,mode)
        except (ValueError,UnicodeError):pass
    if exit_code is None:
        origin='DOCKER_CLIENT';code='SELFTEST_DOCKER_CLIENT_UNAVAILABLE_OR_TIMEOUT'
    elif exit_code in (125,126,127):
        origin='DOCKER_LAUNCH';code={125:'SELFTEST_DOCKER_CREATE_OR_START_FAILED',126:'SELFTEST_ENTRYPOINT_NOT_EXECUTABLE',127:'SELFTEST_ENTRYPOINT_NOT_FOUND'}[exit_code]
    elif script is not None:
        origin='SCRIPT';code=script['code'] if script['success']==(exit_code==0) else 'SELFTEST_EXIT_RESULT_CONFLICT'
    else:
        origin='SCRIPT' if started else 'UNDETERMINED'
        code='SELFTEST_SCRIPT_OUTPUT_INVALID' if started else 'SELFTEST_COMMAND_NO_START_PROOF'
    success=exit_code==0 and script is not None and script['success'] is True and code=='SELFTEST_OK'
    return dict(success=success,context=mode,code=code,origin=origin,docker_exit_code=exit_code,script_started=started,
        script=script,raw_output_saved=False)

def validated_transport(value,nonce,mode):
    fields={'success','context','code','origin','docker_exit_code','script_started','script','raw_output_saved'}
    if not isinstance(value,dict) or set(value)!=fields:return None
    if value['context']!=mode or type(value['success']) is not bool or type(value['script_started']) is not bool or value['raw_output_saved'] is not False:return None
    rc=value['docker_exit_code']
    if rc is not None and (type(rc) is not int or not -255<=rc<=255):return None
    raw=('OFL_CAPABILITY_STARTED='+nonce+'\n').encode() if value['script_started'] else b''
    if value['script'] is not None:
        script=validated(value['script'],nonce,mode)
        if script is None:return None
        raw+=b'OFL_CAPABILITY_RESULT='+json.dumps(script).encode()+b'\n'
    expected=transport(raw,rc,nonce,mode)
    return expected if value==expected else None
