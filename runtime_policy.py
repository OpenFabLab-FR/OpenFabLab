"""Persistent test isolation and cooperative storage lock (including workers)."""
import fcntl
import ipaddress
import os
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

TEST_MARKER = '.openfablab-test-instance.json'
_mutex = threading.RLock()
_local = threading.local()
_installed = False


def is_test_instance(database_path):
    # Fail closed: even an unreadable/corrupted marker must not enable networking.
    return Path(database_path).with_name(TEST_MARKER).exists()


def external_allowed(database_path=None):
    if os.environ.get('OPENFABLAB_EXTERNAL_ACTIONS') == '0':
        return False
    try:
        flask = sys.modules.get('flask')
        if flask and flask.has_app_context():
            if flask.current_app.config.get('EXTERNAL_ACTIONS') is False:
                return False
            database_path = database_path or flask.current_app.config['DATABASE']
    except ImportError:
        pass
    database_path = database_path or os.environ.get('OPENFABLAB_DATABASE') or os.environ.get('COMPTEUR_DATABASE')
    return not database_path or not is_test_instance(database_path)


def require_external():
    if not external_allowed():
        raise OSError('Connexions externes interdites pour cette instance isolée.')


def _loopback(host):
    if host in ('localhost', b'localhost'):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError):
        return False


def install_network_guard():
    """Audit the socket boundary too: no DNS/HTTPS/SMTP bypass in a test clone."""
    global _installed
    if _installed:
        return
    def audit(event, args):
        if event not in ('socket.getaddrinfo', 'socket.connect', 'socket.sendto'):
            return
        if external_allowed():
            return
        if event == 'socket.getaddrinfo' and not _loopback(args[0]):
            require_external()
        if event in ('socket.connect', 'socket.sendto'):
            address = args[-1]
            if isinstance(address, tuple) and not _loopback(address[0]):
                require_external()
    sys.addaudithook(audit)
    _installed = True


@contextmanager
def storage_guard(database_path):
    """One reentrant lock per process plus flock across processes/CLI backups."""
    with _mutex:
        depth = getattr(_local, 'depth', 0)
        descriptor = None
        if depth == 0:
            path = Path(database_path).with_name('.openfablab-state.lock')
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
            except PermissionError:
                descriptor = os.open(path, os.O_RDONLY)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        _local.depth = depth + 1
        try:
            yield
        finally:
            _local.depth = depth
            if descriptor is not None:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)


def register_storage(application):
    from flask import g
    # Acquire BEFORE Flask decodes a session cookie, not just before a route.
    # Otherwise a queued request could keep the old installation's authority
    # across a full restore that replaces the signing key and PIN credentials.
    original_wsgi = application.wsgi_app
    def guarded_wsgi(environ, start_response):
        with storage_guard(application.config['DATABASE']):
            return original_wsgi(environ, start_response)
    application.wsgi_app = guarded_wsgi
    @application.before_request
    def acquire():
        g._storage_guard = storage_guard(application.config['DATABASE'])
        g._storage_guard.__enter__()
    @application.teardown_request
    def release(_error):
        # Close the connection before allowing a complete replacement.
        database = g.pop('database', None)
        if database is not None:
            database.close()
        guard = g.pop('_storage_guard', None)
        if guard is not None:
            guard.__exit__(None, None, None)
