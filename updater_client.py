"""Unprivileged web client. No Docker, shell, filesystem policy or remote URL API."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
from update_wire import Authentication, Refused, pack, MAX_LOCAL_ZIP

MAX_RESPONSE = 512*1024


def upload(stream,socket_path=None,token_path=None):
    if request('status',socket_path=socket_path,token_path=token_path).get('local_zip')!=1:
        raise Refused('AGENT_ZIP_UPGRADE_REQUIRED')
    sha=hashlib.sha256();size=0
    for block in iter(lambda:stream.read(65536),b''):
        size+=len(block)
        if size>MAX_LOCAL_ZIP:
            raise Refused('LOCAL_ZIP_SIZE_REFUSED')
        sha.update(block)
    if not size:
        raise Refused('LOCAL_ZIP_SIZE_REFUSED')
    stream.seek(0)
    return request('prepare_zip',{'size':size,'sha256':sha.hexdigest()},socket_path,token_path,stream=stream)


def request(operation, arguments=None, socket_path=None, token_path=None, *, stream=None):
    socket_path = socket_path or os.environ.get('OPENFABLAB_UPDATE_SOCKET')
    token_path = token_path or os.environ.get('OPENFABLAB_UPDATE_TOKEN_FILE')
    if not socket_path or not token_path:
        raise Refused('AGENT_NOT_CONFIGURED_MANUAL_UPDATE_AVAILABLE')
    try:authentication = Authentication(Path(token_path).read_bytes())
    except OSError:raise Refused('AGENT_UNAVAILABLE_MANUAL_UPDATE_AVAILABLE') from None
    envelope = authentication.sign(operation, arguments or {})
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
            connection.settimeout(50)
            connection.connect(socket_path)
            connection.sendall(pack(envelope)+b'\n')
            with connection.makefile('rb') as reader:
                if stream is not None:
                    grant=verify_response(reader.readline(MAX_RESPONSE+1),authentication,envelope)
                    if grant!={'ready_for_upload':True}:
                        raise Refused('AGENT_ZIP_UPGRADE_REQUIRED')
                    for block in iter(lambda:stream.read(65536),b''):
                        connection.sendall(block)
                response = reader.readline(MAX_RESPONSE+1)
    except OSError:
        raise Refused('AGENT_UNAVAILABLE_MANUAL_UPDATE_AVAILABLE') from None
    return verify_response(response,authentication,envelope)


def verify_response(response,authentication,envelope):
    if len(response) > MAX_RESPONSE:
        raise Refused('AGENT_RESPONSE_TOO_LARGE')
    try:
        value = json.loads(response)
        signature = value.pop('signature')
        expected = hmac.new(authentication.token,pack(value),hashlib.sha256).hexdigest()
        if (not isinstance(signature,str) or not hmac.compare_digest(expected,signature)
                or value.pop('nonce') != envelope['nonce']):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise Refused('AGENT_RESPONSE_AUTHENTICATION_FAILED') from None
    if value.get('ok') is not True:
        raise Refused(value.get('code','AGENT_REQUEST_FAILED'))
    return value['value']
