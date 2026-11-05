"""Operator-authorized capability, never selected by a web request."""
import os
from pathlib import Path
import sys
from .security import Refused
from .capability_diagnostics import FIXTURE_SCRIPT
from .no_new_privileges import observe_nnp

CAPABILITY='DAC_OVERRIDE'
EXPECTED_ENV='OPENFABLAB_UPDATER_EXPECTED_CAPABILITY'
NNP_ENV='OPENFABLAB_UPDATER_EXPECT_NNP'

def checked_nnp(metadata):
    observation=observe_nnp(metadata)
    if not observation['verified']:
        from .diagnostics import DiagnosticFailure,describe
        value=describe(Refused(observation['code']),phase='NO_NEW_PRIVILEGES')
        value['no_new_privileges']=observation
        raise DiagnosticFailure(value)
    return observation

def current_nnp():
    try:metadata={k:v.strip() for line in Path('/proc/self/status').read_text().splitlines() if ':' in line for k,v in [line.split(':',1)]}
    except OSError:metadata=None
    return checked_nnp(metadata)

def validate_if_expected():
    # Portable direct worker invocations are used by the isolated native tests.
    # Every actual Docker helper/permanent agent launch sets this expectation.
    expected=os.environ.get(EXPECTED_ENV)
    expected_nnp=os.environ.get(NNP_ENV)
    if expected is None and expected_nnp is None:return
    if expected is not None and expected!=CAPABILITY:raise Refused('HELPER_CAPABILITY_EXPECTATION_REFUSED')
    if expected_nnp is not None and expected_nnp!='1':raise Refused('HELPER_NNP_EXPECTATION_REFUSED')
    if sys.platform!='linux':raise Refused('HELPER_LINUX_CAPABILITY_CHECK_REQUIRED')
    try:
        metadata={k:v.strip() for line in Path('/proc/self/status').read_text().splitlines() if ':' in line for k,v in [line.split(':',1)]}
        if expected is not None and (os.geteuid()!=0 or any(int(metadata[k],16)!=2 for k in ('CapEff','CapPrm','CapBnd'))):
            raise Refused('HELPER_CAPABILITY_PROFILE_REFUSED')
        return checked_nnp(metadata)
    except (OSError,KeyError,ValueError):raise Refused('HELPER_CAPABILITY_METADATA_UNAVAILABLE') from None

def mounts(operation,access,project,data,backups,state):
    expected={'snapshot':'ro','compare':'ro','compare-live':'ro','probe':'ro','probe-copy':'ro',
        'backup':'rw','migrate':'rw','write-preflight':'rw'}
    if operation not in expected or access!=expected[operation]:raise Refused('HELPER_OPERATION_ACCESS_REFUSED')
    result=[(state,state,'rw')]
    if operation=='backup':result += [(project,project,'ro'),(backups,backups,'rw')]
    elif operation=='write-preflight':result += [(project,project,'rw'),(backups,backups,'rw')]
    result.append((data,data,'rw' if operation in ('migrate','write-preflight') else 'ro'))
    return result
