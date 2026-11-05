"""Small audited wire format, private durable state and fixed local policy."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import time
from update_wire import Refused,pack,Authentication


def private_json(path, value):
    path = Path(path)
    temporary = path.with_name('.'+path.name+'.'+secrets.token_hex(8))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(pack(value)); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}', value):
        raise Refused('INVALID_STABLE_VERSION')
    return tuple(map(int, value.split('.')))


def digest(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise Refused('INVALID_DIGEST')
    return value


def checked_path(value, directory=True):
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts or path == Path('/'):
        raise Refused('POLICY_PATH_INVALID')
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise Refused('POLICY_SYMLINK_REFUSED')
    if directory and not path.is_dir():
        raise Refused('POLICY_DIRECTORY_MISSING')
    return path


def load_policy(path, owner=0):
    path = checked_path(path, False)
    info = path.stat()
    if info.st_uid != owner or stat.S_IMODE(info.st_mode) & 0o022:
        raise Refused('POLICY_OWNERSHIP_UNSAFE')
    value = json.loads(path.read_bytes())
    required = {'protocol','project','compose_file','service','data','database','backups',
                'state','socket','token_file','repository_id','docker','docker_root','enabled','web_gid'}
    if set(value) != required or value['protocol'] != 1 or type(value['enabled']) is not bool:
        raise Refused('POLICY_FORMAT_INVALID')
    for key in ('project', 'data', 'backups', 'state','docker_root'):
        checked_path(value[key])
    for key in ('compose_file', 'database', 'socket', 'token_file', 'docker'):
        checked_path(value[key], False)
    project, data, backups, state = (Path(value[k]) for k in ('project','data','backups','state'))
    if not Path(value['database']).is_relative_to(data) or not Path(value['compose_file']).is_relative_to(project):
        raise Refused('POLICY_LAYOUT_INVALID')
    if state == data or state.is_relative_to(data) or state == project or state.is_relative_to(project):
        raise Refused('AGENT_STATE_MUST_BE_INDEPENDENT')
    if backups == data or backups.is_relative_to(data):
        raise Refused('BACKUP_DESTINATION_UNSAFE')
    if (data.is_relative_to(backups) or project.is_relative_to(backups)
            or backups==state or backups.is_relative_to(state) or state.is_relative_to(backups)
            or project.is_relative_to(state) or data.is_relative_to(state)):
        raise Refused('POLICY_DIRECTORIES_MUST_BE_SEPARATE')
    compose=Path(value['compose_file']);database=Path(value['database'])
    if not compose.is_file() or not database.is_file() or database.name!='openfablab.db' or database.parent!=data:
        raise Refused('POLICY_CANONICAL_DATABASE_OR_COMPOSE_INVALID')
    shared=Path(value['socket']).parent
    if (shared!=Path(value['token_file']).parent or not shared.is_dir() or
            any(shared==root or shared.is_relative_to(root) or root.is_relative_to(shared) for root in (state,project,data,backups))):
        raise Refused('POLICY_SHARED_CHANNEL_LAYOUT_INVALID')
    for protected in (state,shared):
        info=protected.stat()
        if info.st_uid!=owner or stat.S_IMODE(info.st_mode)&0o022:
            raise Refused('AGENT_DIRECTORY_OWNERSHIP_UNSAFE')
    if (not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', value['service'])
            or type(value['repository_id']) is not int or value['repository_id'] <= 0
            or type(value['web_gid']) is not int or value['web_gid'] < 0):
        raise Refused('POLICY_IDENTITY_INVALID')
    return value


