"""Change one image reference, then require semantic Compose equivalence.

Complex YAML syntax is refused, not guessed or rewritten by an incomplete parser.
The daemon's real `compose config` is the authority for both before/after values.
"""
import json
import re
from .security import Refused,pack

def proposal(raw,service,image):
    if not re.fullmatch('sha256:[0-9a-f]{64}',image):raise Refused('TARGET_IMAGE_NOT_PINNED')
    try:value=json.loads(raw)
    except (ValueError,UnicodeError):value=None
    if isinstance(value,dict):
        try:value['services'][service]['image']=image
        except (KeyError,TypeError):raise Refused('COMPOSE_SERVICE_UNRECOGNIZED') from None
        return json.dumps(value,ensure_ascii=False,indent=2).encode()+b'\n'
    try:lines=raw.decode('utf-8').splitlines(keepends=True)
    except UnicodeError:raise Refused('COMPOSE_ENCODING_UNSUPPORTED') from None
    services_indent=None;service_indent=None;selected=[]
    for index,line in enumerate(lines):
        if not line.strip() or line.lstrip().startswith('#'):continue
        indent=len(line)-len(line.lstrip(' '))
        if '\t' in line[:indent+1]:raise Refused('COMPOSE_SYNTAX_REQUIRES_MANUAL_UPDATE')
        text=line.strip()
        if re.fullmatch(r'services:\s*(?:#.*)?',text):services_indent=indent;service_indent=None;continue
        if services_indent is None:continue
        if indent<=services_indent:services_indent=None;service_indent=None;continue
        if re.fullmatch(re.escape(service)+r':\s*(?:#.*)?',text):service_indent=indent;continue
        if service_indent is not None and indent<=service_indent:service_indent=None
        if service_indent is not None and re.match(r'image\s*:',text):
            if not re.fullmatch(r'image:\s*[^\s#]+\s*(?:#.*)?',text):raise Refused('COMPOSE_IMAGE_SYNTAX_REQUIRES_MANUAL_UPDATE')
            selected.append(index)
    if len(selected)!=1:raise Refused('COMPOSE_IMAGE_LOCATION_AMBIGUOUS')
    index=selected[0];line=lines[index];prefix=line[:len(line)-len(line.lstrip(' '))]
    comment=re.search(r'\s+#.*',line.rstrip('\r\n'))
    lines[index]=prefix+'image: '+image+(comment.group() if comment else '')+'\n'
    return ''.join(lines).encode()

def equivalent(before,after,service,image):
    expected=json.loads(json.dumps(before))
    try:expected['services'][service]['image']=image
    except (KeyError,TypeError):raise Refused('COMPOSE_SERVICE_UNRECOGNIZED') from None
    if pack(expected)!=pack(after):raise Refused('COMPOSE_IMAGE_CHANGE_ALTERS_OTHER_CONFIGURATION')
