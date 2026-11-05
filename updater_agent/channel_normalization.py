"""Normalize both Compose models, then permit exactly the three channel adds."""
import copy,json
from pathlib import Path
from .security import Refused,pack,private_json

TARGET='/run/openfablab-updater'
ENVIRONMENT={'OPENFABLAB_UPDATE_SOCKET':TARGET+'/agent.sock','OPENFABLAB_UPDATE_TOKEN_FILE':TARGET+'/token'}

def without_channel(model,service,shared):
    value=copy.deepcopy(model)
    try:
        item=value['services'][service];environment=item['environment'];volumes=item['volumes']
        if not isinstance(environment,dict) or not isinstance(volumes,list):raise ValueError
        if any(environment.get(k)!=v for k,v in ENVIRONMENT.items()):raise ValueError
        selected=[v for v in volumes if isinstance(v,dict) and v.get('target')==TARGET]
        if len(selected)!=1:raise ValueError
        mount=selected[0]
        if set(mount)-{'type','source','target','read_only','bind'}:raise ValueError
        if mount.get('type')!='bind' or mount.get('source')!=str(shared) or mount.get('read_only') is not True:raise ValueError
        bind=mount.get('bind',{})
        if not isinstance(bind,dict) or set(bind)-{'create_host_path'}:raise ValueError
        if 'create_host_path' in bind and bind['create_host_path'] is not False:raise ValueError
        for key in ENVIRONMENT:del environment[key]
        item['volumes']=[v for v in volumes if v is not mount]
    except (KeyError,TypeError,ValueError):raise Refused('AGENT_CHANNEL_ADDITIONS_INVALID') from None
    return value

def render(executor,model,folder,name):
    # Compose's JSON renderer already escapes literal dollar values for reuse.
    # Preserve that canonical representation; do not double-escape it ourselves.
    path=Path(folder)/(name+'.private.json');private_json(path,model)
    try:value=json.loads(executor.compose(['config','--format','json'],replacement=path))
    except (ValueError,TypeError):raise Refused('AGENT_CHANNEL_RENDER_INVALID') from None
    if not isinstance(value,dict):raise Refused('AGENT_CHANNEL_RENDER_INVALID')
    return value

def checked_configuration(executor,configuration,service,shared,folder,constructor):
    # The same installed Compose binary and flags normalize BOTH sides.
    baseline=render(executor,configuration,folder,'agent-baseline-normalization')
    replacement=constructor(baseline,service,shared)
    proposed=Path(folder)/'agent-channel-proposal.json'
    document=copy.deepcopy(replacement);private_json(proposed,document)
    try:rendered=json.loads(executor.compose(['config','--format','json'],replacement=proposed))
    except (ValueError,TypeError):raise Refused('AGENT_CHANNEL_RENDER_INVALID') from None
    stripped=without_channel(rendered,service,shared)
    if pack(stripped)!=pack(baseline):
        private_json(Path(folder)/'channel-comparison.json',dict(success=False,code='AGENT_CHANNEL_UNEXPECTED_CHANGE',
            baseline_normalized=True,proposal_normalized=True,raw_output_saved=False))
        raise Refused('AGENT_CHANNEL_UNEXPECTED_CHANGE')
    # Both normalized models must preserve the already resolved baseline.
    # A surprise outside the three additions is never silently canonicalized.
    if pack(baseline)!=pack(configuration):raise Refused('AGENT_BASELINE_NORMALIZATION_REQUIRES_REVIEW')
    private_json(Path(folder)/'channel-comparison.json',dict(success=True,baseline_normalized=True,proposal_normalized=True,
        only_two_environment_and_one_ro_mount=True,bind_false_omitted='create_host_path' not in next(v for v in rendered['services'][service]['volumes'] if v['target']==TARGET).get('bind',{}),
        existing_configuration_unchanged=True,raw_output_saved=False))
    return document
