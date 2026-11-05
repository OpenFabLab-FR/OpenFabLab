"""Bounded phase receipts: no exception text, paths, commands or database values."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import errno
from pathlib import Path
import re
from .security import Refused,checked_path,private_json
from .diagnostics import DiagnosticFailure,describe

PHASES={'CONTROLLER_NNP','SOURCE_INSPECTION','CANDIDATE_ARCHIVE','CANDIDATE_UNPACK',
 'PREFLIGHT_STORAGE_LOCK','PREFLIGHT_INVENTORY','PREFLIGHT_IMAGE','PREFLIGHT_SPACE',
 'PREFLIGHT_WRITE_ACCESS','PREFLIGHT_COMPOSE','WORDPRESS_IMPORTS','WORDPRESS_SETTINGS',
 'WORDPRESS_SECRET','WORDPRESS_CLIENT','WORDPRESS_LOCAL_STATE','WORDPRESS_EXCHANGES','DIAGNOSTIC_PERSIST'}
ROLES={'PROJECT','DATA','BACKUPS','STATE','DOCKER','NORMAL','TEST'}
CURRENT=ContextVar('openfablab_operator_stage_recorder',default=None)

def failure(error,name,role=None):
    if isinstance(error,DiagnosticFailure):return error
    value=describe(error,phase=name,operation='controller')
    if isinstance(error,Refused) and re.fullmatch('[A-Z][A-Z0-9_]{1,99}',error.code):code=error.code
    else:
        suffix={errno.EACCES:'ACCESS_DENIED',errno.EPERM:'ACCESS_DENIED',errno.EROFS:'READ_ONLY_FILESYSTEM',
            errno.ENOENT:'PATH_NOT_FOUND',errno.ENOSPC:'SPACE_EXHAUSTED',errno.EIO:'IO_ERROR',errno.ENOTDIR:'NOT_DIRECTORY',
            errno.EINVAL:'INVALID_OS_OPERATION'}.get(value['errno'])
        if suffix is None:suffix=value['sqlite_errorname']
        if suffix is None:suffix={'ModuleNotFoundError':'MODULE_NOT_FOUND','ImportError':'IMPORT_FAILED','KeyError':'MISSING_FIELD',
            'JSONDecodeError':'INVALID_JSON','ValueError':'INVALID_VALUE','TypeError':'INVALID_TYPE','AttributeError':'ATTRIBUTE_ERROR',
            'OverflowError':'OVERFLOW','MemoryError':'MEMORY_UNAVAILABLE','BadZipFile':'ARCHIVE_INVALID'}.get(type(error).__name__,'UNCLASSIFIED_EXCEPTION')
        code=name+('_'+role if role else '')+'_'+suffix
    value['code']=code
    if role:value['role']=role
    return DiagnosticFailure(value)

class Recorder:
    def __init__(self,path):self.path=checked_path(path,False);self.events=[];self.omitted=0
    def emit(self,name,status,error=None,role=None):
        item=dict(phase=name,status=status)
        if role:item['role']=role
        if error is not None:
            safe=error.diagnostic
            item.update(code=safe['code'],error_type=safe['error_type'],errno=safe['errno'])
        self.events.append(item)
        if len(self.events)>256:self.events.pop(32);self.omitted+=1
        try:private_json(self.path,dict(format=1,events=self.events,omitted_events=self.omitted,raw_output_saved=False))
        except Exception as error:raise failure(error,'DIAGNOSTIC_PERSIST') from None

@contextmanager
def recording(path=None):
    if CURRENT.get() is not None or path is None:yield;return
    token=CURRENT.set(Recorder(Path(path)))
    try:yield
    finally:CURRENT.reset(token)

def recorded(destination):
    def decorate(function):
        @wraps(function)
        def call(*args,**kwargs):
            with recording(destination(*args,**kwargs)):return function(*args,**kwargs)
        return call
    return decorate

@contextmanager
def phase(name,role=None):
    if name not in PHASES or (role is not None and role not in ROLES):raise Refused('OPERATOR_DIAGNOSTIC_PHASE_INVALID')
    recorder=CURRENT.get()
    if recorder:recorder.emit(name,'STARTED',role=role)
    try:yield
    except Exception as error:
        safe=failure(error,name,role)
        if recorder:recorder.emit(name,'FAILED',safe,role)
        raise safe from None
    else:
        if recorder:recorder.emit(name,'OK',role=role)
