"""Unprivileged local wire format. No filesystem, policy or Docker operations."""
import hashlib
import hmac
import json
import re
import secrets
import time

MAX_LOCAL_ZIP = 64 * 1024 * 1024

class Refused(RuntimeError):
    def __init__(self,code):
        self.code=code if isinstance(code,str) and re.fullmatch(r'[A-Z][A-Z0-9_]{1,99}',code) else 'UNCLASSIFIED_FAILURE'
        super().__init__(self.code)

def pack(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()

class Authentication:
    def __init__(self,token):
        if not isinstance(token,bytes) or len(token)<32:raise Refused('AGENT_TOKEN_INVALID')
        self.token=token;self.seen={}
    def sign(self,operation,arguments,current=None):
        value=dict(operation=operation,arguments=arguments,timestamp=int(current if current is not None else time.time()),nonce=secrets.token_hex(16))
        return value|{'signature':hmac.new(self.token,pack(value),hashlib.sha256).hexdigest()}
    def verify(self,envelope,current=None):
        current=int(current if current is not None else time.time())
        if not isinstance(envelope,dict) or set(envelope)!={'operation','arguments','timestamp','nonce','signature'}:raise Refused('AGENT_REQUEST_INVALID')
        if (type(envelope['timestamp']) is not int or abs(current-envelope['timestamp'])>60
                or not isinstance(envelope['nonce'],str) or not re.fullmatch('[0-9a-f]{32}',envelope['nonce'])
                or not isinstance(envelope['signature'],str) or len(envelope['signature'])!=64):raise Refused('AGENT_AUTHENTICATION_REFUSED')
        value={k:v for k,v in envelope.items() if k!='signature'}
        if not hmac.compare_digest(hmac.new(self.token,pack(value),hashlib.sha256).hexdigest(),envelope['signature']):raise Refused('AGENT_AUTHENTICATION_REFUSED')
        self.seen={k:t for k,t in self.seen.items() if current-t<=120}
        if envelope['nonce'] in self.seen:raise Refused('AGENT_REPLAY_REFUSED')
        self.seen[envelope['nonce']]=current
        return value['operation'],value['arguments']
