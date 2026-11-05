"""Coherent isolated copies. Never remove a production WAL, SHM or journal."""
from contextlib import contextmanager
import fcntl
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
import stat
import tempfile
from .security import Refused, checked_path, private_json


def sha(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            result.update(block)
    return result.hexdigest()


def inventory(root,exclude=()):
    root=checked_path(root)
    result={}
    def visit(folder):
        for path in sorted(folder.iterdir()):
            relative=path.relative_to(root).as_posix()
            if relative in exclude:
                continue
            info=path.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise Refused('PERSISTENT_SYMLINK_REFUSED')
            if stat.S_ISDIR(info.st_mode):
                visit(path)
            elif stat.S_ISREG(info.st_mode):
                result[relative]=dict(size=info.st_size,sha256=sha(path),mode=stat.S_IMODE(info.st_mode))
            else:
                raise Refused('PERSISTENT_SPECIAL_FILE_REFUSED')
    visit(root)
    return result


@contextmanager
def readonly_storage_lock(data):
    # Existing lock only: --check/preparation cannot create even a lock file in
    # production. Both the web process and its workers already use this flock.
    path=Path(data)/'.openfablab-state.lock'
    if path.is_symlink() or not path.is_file():
        raise Refused('COOPERATIVE_SOURCE_LOCK_MISSING')
    with path.open('rb') as stream:
        fcntl.flock(stream.fileno(),fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def coherent_copy(data,destination,database_name='openfablab.db'):
    data=checked_path(data)
    destination=Path(destination)
    if destination.exists() or destination.is_symlink() or destination.resolve().is_relative_to(data):
        raise Refused('ISOLATED_COPY_DESTINATION_UNSAFE')
    if Path(database_name).name!=database_name:
        raise Refused('DATABASE_FILENAME_INVALID')
    database=data/database_name
    excluded={database_name,'.openfablab-state.lock',*(database_name+s for s in ('-wal','-shm','-journal'))}
    # SQLite's online backup API merges committed WAL pages into the copied DB.
    # It does not copy a live main file and then discard its needed sidecars.
    # Source sidecars are opened read-only by SQLite and never deleted here.
    with readonly_storage_lock(data):
        before=inventory(data,excluded)
        with tempfile.TemporaryDirectory(prefix='isolated-state-',dir=destination.parent) as temporary:
            copied=Path(temporary)/'data';copied.mkdir(mode=0o700)
            with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True,timeout=30) as source:
                source.execute('PRAGMA query_only=ON')
                with sqlite3.connect(copied/database_name) as target:
                    source.backup(target)
                    target.execute('PRAGMA journal_mode=DELETE')
                    if target.execute('PRAGMA integrity_check').fetchall()!=[('ok',)] or target.execute('PRAGMA foreign_key_check').fetchall():
                        raise Refused('ISOLATED_COPY_SQLITE_INVALID')
            for name,item in before.items():
                target=copied/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                shutil.copy2(data/name,target);target.chmod(item['mode'] & 0o700 or 0o600)
                if sha(target)!=item['sha256']:
                    raise Refused('PERSISTENT_COPY_HASH_MISMATCH')
            if inventory(data,excluded)!=before:
                raise Refused('PERSISTENT_STATE_CHANGED_DURING_COPY')
            os.replace(copied,destination)
    return before


def write_probe(path):
    """Update-only capability check, before stopping; remove only our own file."""
    root=checked_path(path)
    target=root/('.openfablab-write-probe-'+secrets.token_hex(16))
    content=secrets.token_bytes(32)
    try:
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(content);stream.flush();os.fsync(stream.fileno())
        if target.read_bytes()!=content:
            raise Refused('WRITE_PREFLIGHT_CONTENT_MISMATCH')
    except OSError:
        raise Refused('WRITE_PREFLIGHT_ACCESS_REFUSED') from None
    finally:
        if target.is_file() and not target.is_symlink():
            target.unlink()


def copy_verified_runtime(source,destination,files):
    source,destination=checked_path(source),checked_path(destination)
    for name,expected in files.items():
        relative=Path(name)
        if relative.is_absolute() or any(p in ('','.','..') or p.startswith('.') for p in relative.parts):
            raise Refused('RUNTIME_DESTINATION_UNSAFE')
        origin=checked_path(source/relative,False)
        if not origin.is_file() or sha(origin)!=expected:
            raise Refused('TARGET_RUNTIME_HASH_MISMATCH')
        target=destination/relative
        checked_path(target,False)
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
        temporary=target.with_name('.'+target.name+'.update-'+secrets.token_hex(8))
        try:
            with temporary.open('xb') as stream:
                stream.write(origin.read_bytes());stream.flush();os.fsync(stream.fileno())
            temporary.chmod(0o644)
            os.replace(temporary,target)
        finally:
            if temporary.exists():temporary.unlink()
