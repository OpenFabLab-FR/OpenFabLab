"""Safe fixed-vocabulary helper failures. Never serialize an exception message."""
from contextlib import contextmanager
import errno
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
from .security import Refused
from .no_new_privileges import FAILURE_CODES as NNP_FAILURE_CODES,validated_nnp

OPERATIONS={'snapshot','probe','probe-copy','migrate','compare','compare-live','backup','write-preflight'}
PHASES={'WORKER_INPUT','WORKER_OPERATION','DATABASE_METADATA','SQLITE_OPEN','SQLITE_READ_BEGIN',
    'SQLITE_USER_VERSION','SQLITE_INTEGRITY','SQLITE_FOREIGN_KEYS','SQLITE_TABLE_LIST',
    'SQLITE_TABLE_INFO','SQLITE_TABLE_READ','SQLITE_ROW_HASH','SQLITE_SETTINGS_READ','OUTPUT_PERSIST','CAPABILITY_PROFILE','NO_NEW_PRIVILEGES'}
TYPES={'Refused','PermissionError','FileNotFoundError','NotADirectoryError','IsADirectoryError','OSError',
    'OperationalError','DatabaseError','IntegrityError','ProgrammingError','DataError','InterfaceError','InternalError','NotSupportedError',
    'UnicodeDecodeError','UnicodeEncodeError','TypeError','ValueError','OverflowError','MemoryError','RuntimeError',
    'KeyError','IndexError','AttributeError','AssertionError','StopIteration','ImportError','ModuleNotFoundError',
    'RecursionError','ZeroDivisionError','JSONDecodeError','OTHER'}
FIXED_REFUSALS={
 'DATABASE_FILE_MISSING_OR_UNSAFE','SQLITE_SCHEMA_MISMATCH','SQLITE_INTEGRITY_FAILED','SQLITE_FOREIGN_KEYS_FAILED',
 'OPENFABLAB_DATABASE_INCOMPLETE','UNEXPECTED_ADDED_TABLE','HISTORICAL_TABLE_MISSING','HISTORICAL_COLUMN_MISSING',
 'HISTORICAL_DATA_CHANGED_DURING_MIGRATION','HISTORICAL_SETTING_CHANGED_DURING_MIGRATION','UNEXPECTED_ADDED_SETTING',
 'LIVE_DATABASE_STRUCTURE_CHANGED','HISTORICAL_IDENTITIES_MISSING_AFTER_START','HISTORICAL_ROWS_MISSING_AFTER_START',
 'HISTORICAL_SETTING_CHANGED_AFTER_START','POLICY_PATH_INVALID','POLICY_SYMLINK_REFUSED','POLICY_DIRECTORY_MISSING',
 'PERSISTENT_SYMLINK_REFUSED','PERSISTENT_SPECIAL_FILE_REFUSED','COOPERATIVE_SOURCE_LOCK_MISSING',
 'ISOLATED_COPY_DESTINATION_UNSAFE','DATABASE_FILENAME_INVALID','SOURCE_CHANGED_DURING_COHERENT_COPY',
 'ISOLATED_COPY_SQLITE_INVALID','PERSISTENT_COPY_HASH_MISMATCH','PERSISTENT_STATE_CHANGED_DURING_COPY',
 'WRITE_PREFLIGHT_CONTENT_MISMATCH','WRITE_PREFLIGHT_ACCESS_REFUSED','RUNTIME_DESTINATION_UNSAFE','TARGET_RUNTIME_HASH_MISMATCH',
 'MIGRATION_API_SCHEMA_MISMATCH','MIGRATION_SOURCE_SCHEMA_REFUSED','ISOLATED_GUNICORN_START_FAILED',
 'ISOLATED_GUNICORN_HTTP_FAILED','ISOLATED_RUNTIME_IDENTITY_FAILED','ISOLATED_HTTP_FAILED','BACKUP_DESTINATION_EXISTS',
 'HELPER_REFUSED','HELPER_CAPABILITY_EXPECTATION_REFUSED','HELPER_LINUX_CAPABILITY_CHECK_REQUIRED',
 'HELPER_CAPABILITY_PROFILE_REFUSED','HELPER_NO_NEW_PRIVILEGES_REQUIRED','HELPER_CAPABILITY_METADATA_UNAVAILABLE',
 'WRITE_PREFLIGHT_DATABASE_FILE_UNSAFE','WRITE_PREFLIGHT_EXISTING_DATABASE_ACCESS_REFUSED',
 'PROJECT_WRITE_PREFLIGHT_CONTENT_MISMATCH','DATA_WRITE_PREFLIGHT_CONTENT_MISMATCH','BACKUPS_WRITE_PREFLIGHT_CONTENT_MISMATCH','STATE_WRITE_PREFLIGHT_CONTENT_MISMATCH',
 'PROJECT_WRITE_PREFLIGHT_ACCESS_REFUSED','DATA_WRITE_PREFLIGHT_ACCESS_REFUSED','BACKUPS_WRITE_PREFLIGHT_ACCESS_REFUSED','STATE_WRITE_PREFLIGHT_ACCESS_REFUSED'}
FIXED_REFUSALS.update(NNP_FAILURE_CODES|{'HELPER_NNP_EXPECTATION_REFUSED'})

def runtime():
    return dict(python_version='.'.join(map(str,sys.version_info[:3])),sqlite_version=sqlite3.sqlite_version)

def failure_code(phase,error_type,os_errno=None,sql_name=None,refused=None):
    if error_type=='Refused':return refused if refused in FIXED_REFUSALS else 'HELPER_REFUSED'
    prefix='HELPER_OUTPUT_' if phase=='OUTPUT_PERSIST' else ('SNAPSHOT_' if phase.startswith(('SQLITE_','DATABASE_')) else 'HELPER_')
    if sql_name:return prefix+sql_name
    names={errno.EACCES:'ACCESS_DENIED',errno.EPERM:'ACCESS_DENIED',errno.EROFS:'READ_ONLY_FILESYSTEM',
        errno.ENOENT:'PATH_NOT_FOUND',errno.ENOTDIR:'PATH_NOT_DIRECTORY',errno.ENOSPC:'SPACE_EXHAUSTED',
        errno.EIO:'IO_ERROR',errno.EINVAL:'INVALID_OS_OPERATION',errno.EMFILE:'PROCESS_FILE_LIMIT',errno.ENFILE:'SYSTEM_FILE_LIMIT'}
    if os_errno is not None:return prefix+names.get(os_errno,'OS_ERROR')
    return prefix+{'UnicodeDecodeError':'TEXT_DECODE_FAILED','UnicodeEncodeError':'TEXT_ENCODE_FAILED','MemoryError':'MEMORY_ALLOCATION_FAILED',
        'TypeError':'TYPE_ERROR','ValueError':'VALUE_ERROR','OverflowError':'OVERFLOW'}.get(error_type,'UNCLASSIFIED_EXCEPTION')

def describe(error,phase='WORKER_OPERATION',operation='snapshot',request_id=None):
    if isinstance(error,DiagnosticFailure):value=dict(error.diagnostic)
    else:
        error_type='Refused' if isinstance(error,Refused) else type(error).__name__
        if error_type not in TYPES:error_type='OTHER'
        number=getattr(error,'sqlite_errorcode',None) if isinstance(error,sqlite3.Error) else None
        sql_name=getattr(error,'sqlite_errorname',None) if isinstance(error,sqlite3.Error) else None
        if not (type(number) is int and 0<=number<=0x7fffffff):number=None
        if not (isinstance(sql_name,str) and sql_name.startswith('SQLITE_') and type(getattr(sqlite3,sql_name,None)) is int and getattr(sqlite3,sql_name)==number):sql_name=None
        os_errno=error.errno if isinstance(error,OSError) and type(error.errno) is int and 0<=error.errno<=4095 else None
        code=failure_code(phase,error_type,os_errno,sql_name,getattr(error,'code',None))
        value=dict(code=code,phase=phase,error_type=error_type,errno=os_errno,sqlite_errorcode=number,sqlite_errorname=sql_name)
    value.update(operation=operation,request_id=request_id,**runtime())
    return value

class DiagnosticFailure(Refused):
    def __init__(self,diagnostic):
        self.diagnostic=diagnostic
        super().__init__(diagnostic['code'])

@contextmanager
def step(phase,operation='snapshot'):
    try:yield
    except DiagnosticFailure:raise
    except Exception as error:raise DiagnosticFailure(describe(error,phase,operation)) from None

def validated(value,request_id,operation):
    required={'code','phase','error_type','errno','sqlite_errorcode','sqlite_errorname','operation','request_id','python_version','sqlite_version'}
    if not isinstance(value,dict) or not required<=set(value) or set(value)-required-{'no_new_privileges'}:return None
    if 'no_new_privileges' in value:
        evidence=validated_nnp(value['no_new_privileges'])
        if evidence is None or evidence['verified'] or evidence['code']!=value['code'] or value['phase']!='NO_NEW_PRIVILEGES':return None
    if value['request_id']!=request_id or value['operation']!=operation or operation not in OPERATIONS:return None
    if not isinstance(request_id,str) or not re.fullmatch('[0-9a-f]{32}',request_id):return None
    if not isinstance(value['phase'],str) or value['phase'] not in PHASES or not isinstance(value['error_type'],str) or value['error_type'] not in TYPES:return None
    if not isinstance(value['code'],str):return None
    for key in ('python_version','sqlite_version'):
        if not isinstance(value[key],str) or not re.fullmatch(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}',value[key]):return None
    for key,maximum in (('errno',4095),('sqlite_errorcode',0x7fffffff)):
        if value[key] is not None and (type(value[key]) is not int or not 0<=value[key]<=maximum):return None
    sql=value['sqlite_errorname']
    if sql is not None and (not isinstance(sql,str) or not sql.startswith('SQLITE_') or type(getattr(sqlite3,sql,None)) is not int or getattr(sqlite3,sql)!=value['sqlite_errorcode']):return None
    if value['error_type']=='Refused' and value['code'] not in FIXED_REFUSALS:return None
    expected=failure_code(value['phase'],value['error_type'],value['errno'],sql,value['code'])
    return dict(value) if expected==value['code'] else None

def from_stdout(raw,request_id,operation):
    if not isinstance(raw,bytes) or len(raw)>8192:return None
    lines=raw.splitlines();marker=b'OFL_HELPER_DIAGNOSTIC='
    if len(lines)!=1 or not lines[0].startswith(marker):return None
    try:value=json.loads(lines[0][len(marker):])
    except (ValueError,UnicodeError):return None
    return validated(value,request_id,operation)

def read_context(database):
    """Metadata observations only, never permission-bit admission rules."""
    result=dict(runtime(),process_is_root=os.geteuid()==0,files={})
    database=Path(database)
    result['directory_read_access']=os.access(database.parent,os.R_OK)
    result['directory_search_access']=os.access(database.parent,os.X_OK)
    result['primary_group_is_root']=os.getegid()==0
    result['directories']={}
    for role,path in (('data',database.parent),('parent',database.parent.parent)):
        try:
            info=path.lstat()
            entry=dict(mode=format(stat.S_IMODE(info.st_mode),'04o'),same_owner_as_process=info.st_uid==os.geteuid(),
                group_matches_process=info.st_gid in {os.getegid(),*os.getgroups()},symlink=stat.S_ISLNK(info.st_mode),acl_marker_present=None)
            try:entry['acl_marker_present']=any('acl' in n.lower() for n in os.listxattr(path,follow_symlinks=False))
            except (OSError,AttributeError,NotImplementedError):pass
            result['directories'][role]=entry
        except OSError as error:result['directories'][role]=dict(metadata_errno=error.errno if error.errno in errno.errorcode else None)
    result['linux_read_capabilities']=None
    try:
        with Path('/proc/self/status').open() as status:
            for line in status:
                if line.startswith('CapEff:'):
                    bits=int(line.split(':',1)[1].strip(),16)
                    result['linux_read_capabilities']=dict(dac_override=bool(bits & (1<<1)),dac_read_search=bool(bits & (1<<2)));break
    except (OSError,ValueError):pass
    for role,path in (('database',database),('wal',Path(str(database)+'-wal')),('shm',Path(str(database)+'-shm')),('journal',Path(str(database)+'-journal'))):
        value={}
        try:
            info=path.lstat();value=dict(exists=True,regular=stat.S_ISREG(info.st_mode),symlink=stat.S_ISLNK(info.st_mode),
                mode=format(stat.S_IMODE(info.st_mode),'04o'),same_owner_as_process=info.st_uid==os.geteuid(),read_access=os.access(path,os.R_OK))
        except OSError as error:value=dict(exists=False if error.errno in (errno.ENOENT,errno.ENOTDIR) else None,metadata_errno=error.errno if error.errno in errno.errorcode else None)
        result['files'][role]=value
    try:
        info=os.statvfs(database.parent);flag=getattr(os,'ST_RDONLY',None)
        result['data_mount_read_only']=bool(info.f_flag & flag) if flag is not None else None
    except OSError:result['data_mount_read_only']=None
    try:
        if not result['files']['database'].get('regular') or any(p.is_symlink() for p in (database,*database.parents)):return result
        with database.open('rb') as stream:header=stream.read(20)
        result['header_is_sqlite']=header[:16]==b'SQLite format 3\0'
        result['header_uses_wal']=bool(result['header_is_sqlite'] and len(header)==20 and header[18:20]==b'\2\2')
    except OSError as error:result['header_read_errno']=error.errno if error.errno in errno.errorcode else None
    return result

def context_script():
    # Fixed code only, sent to an existing Python process without a temporary
    # file, database connection, app import or change to the live container.
    import inspect
    return 'import os,sys,sqlite3,json,stat,errno\nfrom pathlib import Path\n'+inspect.getsource(runtime)+'\n'+inspect.getsource(read_context)+'\nprint(json.dumps(read_context(Path(sys.argv[1])),sort_keys=True))\n'

def validated_context(value):
    required={'python_version','sqlite_version','process_is_root','files','directory_read_access','directory_search_access','linux_read_capabilities','data_mount_read_only'}
    optional={'header_is_sqlite','header_uses_wal','header_read_errno','primary_group_is_root','directories'}
    if not isinstance(value,dict) or not required<=set(value) or set(value)-required-optional:return None
    for key in ('python_version','sqlite_version'):
        if not isinstance(value[key],str) or not re.fullmatch(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}',value[key]):return None
    for key in ('process_is_root','directory_read_access','directory_search_access'):
        if type(value[key]) is not bool:return None
    if 'primary_group_is_root' in value and type(value['primary_group_is_root']) is not bool:return None
    if 'directories' in value:
        directories=value['directories']
        if not isinstance(directories,dict) or set(directories)!={'data','parent'}:return None
        for record in directories.values():
            if not isinstance(record,dict) or set(record)-{'mode','same_owner_as_process','group_matches_process','symlink','acl_marker_present','metadata_errno'}:return None
            for key,entry in record.items():
                if key=='mode':
                    if not isinstance(entry,str) or not re.fullmatch('[0-7]{4}',entry):return None
                elif key=='metadata_errno':
                    if entry is not None and (type(entry) is not int or not 0<=entry<=4095):return None
                elif key=='acl_marker_present' and entry is None:continue
                elif type(entry) is not bool:return None
    if value['data_mount_read_only'] is not None and type(value['data_mount_read_only']) is not bool:return None
    caps=value['linux_read_capabilities']
    if caps is not None and (not isinstance(caps,dict) or set(caps)!={'dac_override','dac_read_search'} or any(type(v) is not bool for v in caps.values())):return None
    files=value['files']
    if not isinstance(files,dict) or set(files)!={'database','wal','shm','journal'}:return None
    for record in files.values():
        if not isinstance(record,dict) or set(record)-{'exists','regular','symlink','mode','same_owner_as_process','read_access','metadata_errno'}:return None
        for key,entry in record.items():
            if key=='mode':
                if not isinstance(entry,str) or not re.fullmatch('[0-7]{4}',entry):return None
            elif key=='metadata_errno':
                if entry is not None and (type(entry) is not int or not 0<=entry<=4095):return None
            elif key=='exists' and entry is None:continue
            elif type(entry) is not bool:return None
    for key in ('header_is_sqlite','header_uses_wal'):
        if key in value and type(value[key]) is not bool:return None
    if value.get('header_read_errno') is not None and (type(value['header_read_errno']) is not int or not 0<=value['header_read_errno']<=4095):return None
    return value
