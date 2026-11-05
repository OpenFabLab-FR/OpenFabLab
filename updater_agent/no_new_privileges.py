"""Read-only kernel NNP query and one shared fail-closed evidence policy."""
FAILURE_CODES={'NNP_PROC_STATUS_INVALID','NNP_KERNEL_QUERY_UNSUPPORTED','NNP_KERNEL_QUERY_FAILED',
    'NNP_KERNEL_QUERY_UNAVAILABLE','NNP_KERNEL_QUERY_INVALID','NNP_EVIDENCE_CONFLICT','NNP_DISABLED'}

def kernel_nnp():
    import sys
    if sys.platform!='linux':return dict(status='NON_LINUX',value=None,errno=None)
    try:
        import ctypes
        library=ctypes.CDLL(None,use_errno=True)
        function=library.prctl
        function.argtypes=[ctypes.c_int,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong,ctypes.c_ulong]
        function.restype=ctypes.c_int
    except Exception:return dict(status='UNAVAILABLE',value=None,errno=None)
    try:
        ctypes.set_errno(0)
        # PR_GET_NO_NEW_PRIVS=39. All four unused unsigned-long arguments must
        # be zero, including on 32-bit ABIs. Never calls PR_SET_NO_NEW_PRIVS.
        result=function(39,0,0,0,0)
        number=ctypes.get_errno()
    except Exception:return dict(status='ERROR',value=None,errno=None)
    if type(result) is int and result in (0,1):return dict(status='OK',value=result,errno=None)
    if type(result) is int and result==-1:
        number=number if type(number) is int and 0<=number<=4095 else None
        return dict(status='UNSUPPORTED' if number in (22,38) else 'ERROR',value=None,errno=number)
    return dict(status='INVALID_RESULT',value=None,errno=None)

def decide_nnp(proc_status,proc_value,kernel_status,kernel_value,kernel_errno):
    value=dict(verified=False,code='NNP_KERNEL_QUERY_INVALID',proc_status=proc_status,proc_value=proc_value,
        kernel_status=kernel_status,kernel_value=kernel_value,kernel_errno=kernel_errno)
    if proc_status=='INVALID':value['code']='NNP_PROC_STATUS_INVALID'
    elif kernel_status!='OK':
        value['code']={'UNSUPPORTED':'NNP_KERNEL_QUERY_UNSUPPORTED','ERROR':'NNP_KERNEL_QUERY_FAILED',
            'UNAVAILABLE':'NNP_KERNEL_QUERY_UNAVAILABLE','NON_LINUX':'NNP_KERNEL_QUERY_UNAVAILABLE','INVALID_RESULT':'NNP_KERNEL_QUERY_INVALID'}.get(kernel_status,'NNP_KERNEL_QUERY_INVALID')
    elif proc_status=='AVAILABLE' and proc_value!=kernel_value:value['code']='NNP_EVIDENCE_CONFLICT'
    elif kernel_value==0:value['code']='NNP_DISABLED'
    elif kernel_value==1:value.update(verified=True,code='NNP_VERIFIED')
    return value

def observe_nnp(metadata):
    if not isinstance(metadata,dict):proc_status='UNREADABLE';proc_value=None
    elif 'NoNewPrivs' not in metadata:proc_status='ABSENT';proc_value=None
    elif metadata['NoNewPrivs'] in ('0','1'):proc_status='AVAILABLE';proc_value=int(metadata['NoNewPrivs'])
    else:proc_status='INVALID';proc_value=None
    kernel=kernel_nnp()
    return decide_nnp(proc_status,proc_value,kernel['status'],kernel['value'],kernel['errno'])

def validated_nnp(value):
    fields={'verified','code','proc_status','proc_value','kernel_status','kernel_value','kernel_errno'}
    if not isinstance(value,dict) or set(value)!=fields or type(value['verified']) is not bool:return None
    if not isinstance(value['proc_status'],str) or value['proc_status'] not in {'AVAILABLE','ABSENT','UNREADABLE','INVALID'}:return None
    if not isinstance(value['kernel_status'],str) or value['kernel_status'] not in {'OK','UNSUPPORTED','ERROR','UNAVAILABLE','NON_LINUX','INVALID_RESULT'}:return None
    for key in ('proc_value','kernel_value'):
        if value[key] is not None and (type(value[key]) is not int or value[key] not in (0,1)):return None
    if (value['proc_status']=='AVAILABLE')!=(value['proc_value'] is not None):return None
    if (value['kernel_status']=='OK')!=(value['kernel_value'] is not None):return None
    number=value['kernel_errno']
    if number is not None and (type(number) is not int or not 0<=number<=4095):return None
    if value['kernel_status']=='OK' and number is not None:return None
    if value['kernel_status']=='UNSUPPORTED' and number not in (22,38):return None
    expected=decide_nnp(value['proc_status'],value['proc_value'],value['kernel_status'],value['kernel_value'],number)
    return expected if value==expected else None
