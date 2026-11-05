"""Authenticated Unix-socket endpoint; no TCP listener and no command execution API."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import socketserver
import stat
import threading
import tempfile
import time
from .local_candidate import LocalCandidate
from .security import Authentication, Refused, pack

MAX_MESSAGE = 65536


class Service(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(self, engine, token, path, group=None):
        self.engine = engine
        self.authentication = Authentication(token)
        self.guard = threading.Lock()
        self.worker = None
        self.confirmations = {}
        self.last_error = None
        self.uploading = False
        path = Path(path)
        if path.exists() or path.is_symlink():
            # Installer/operator must decide whether an old socket is stale.
            raise Refused('AGENT_SOCKET_ALREADY_EXISTS')
        super().__init__(str(path), Handler)
        path.chmod(0o660)
        if group is not None and path.stat().st_gid!=group:
            os.chown(path, -1, group)

    def dispatch(self, operation, arguments):
        if operation not in ('discover','prepare','status','install','cancel') or not isinstance(arguments, dict):
            raise Refused('AGENT_OPERATION_FORBIDDEN')
        if operation in ('discover','prepare','status') and arguments:
            raise Refused('AGENT_ARGUMENTS_FORBIDDEN')
        if operation == 'discover':
            return self.engine.discover()
        if operation == 'status':
            value = self.engine.status()
            confirmation = self.confirmations.get(value.get('id'))
            return value | {'local_zip':1,'history':self.engine.history()} | ({'confirmation': confirmation} if confirmation and value.get('result') == 'ready' else {}) | ({'last_error':self.last_error} if self.last_error else {})
        if operation == 'cancel':
            if set(arguments) != {'id'}:
                raise Refused('AGENT_ARGUMENTS_FORBIDDEN')
            with self.engine.locked():
                job = self.engine.read(arguments['id'])
                if job['result'] != 'ready' or job['production_stop_attempted']:
                    raise Refused('UPDATE_CANNOT_BE_CANCELLED')
                job.pop('confirmation_hash', None)
                self.confirmations.pop(job['id'], None)
                self.engine.save(job, 'cancelled', 'refused', 'PREPARATION_CANCELLED')
            return self.engine.status(arguments['id'])
        if operation == 'install' and set(arguments) != {'id','confirmation'}:
            raise Refused('AGENT_ARGUMENTS_FORBIDDEN')
        with self.guard:
            if self.uploading or self.worker and self.worker.is_alive():
                raise Refused('AGENT_OPERATION_IN_PROGRESS')
            self.last_error = None
            self.worker = threading.Thread(target=self.perform, args=(operation,arguments), daemon=True)
            self.worker.start()
        return {'accepted': True, 'operation': operation}

    def receive_zip(self, arguments, reader, connection, acknowledge):
        if not isinstance(arguments,dict) or set(arguments)!={'size','sha256'}:
            raise Refused('AGENT_ARGUMENTS_FORBIDDEN')
        with self.guard:
            if self.uploading or self.worker and self.worker.is_alive():
                raise Refused('AGENT_OPERATION_IN_PROGRESS')
            self.uploading = True
        stream = None
        try:
            with self.engine.locked():
                self.engine.available()
            stream = tempfile.TemporaryFile(mode='w+b',dir=self.engine.root)
            candidate = LocalCandidate(stream,arguments['size'],arguments['sha256'])
            acknowledge()
            remaining = candidate.size
            deadline = time.monotonic()+90
            checksum = hashlib.sha256()
            while remaining:
                seconds = deadline-time.monotonic()
                if seconds <= 0:
                    raise Refused('LOCAL_ZIP_UPLOAD_TIMEOUT')
                connection.settimeout(min(10,seconds))
                try:
                    block = reader.read1(min(remaining,65536))
                except TimeoutError:
                    raise Refused('LOCAL_ZIP_UPLOAD_TIMEOUT') from None
                if not block:
                    raise Refused('LOCAL_ZIP_TRUNCATED')
                checksum.update(block); stream.write(block); remaining -= len(block)
            if not hmac.compare_digest(checksum.hexdigest(),candidate.sha256):
                raise Refused('LOCAL_ZIP_INTEGRITY_FAILED')
            with self.guard:
                self.last_error = None
                self.worker = threading.Thread(target=self.perform,args=('prepare_zip',candidate),daemon=True)
                self.worker.start()
                stream = None  # worker owns it
            return {'accepted':True,'operation':'prepare_zip'}
        finally:
            if stream is not None:
                stream.close()
            with self.guard:
                self.uploading = False

    def perform(self, operation, arguments):
        try:
            if operation in ('prepare','prepare_zip'):
                value = self.engine.prepare(local=arguments) if operation=='prepare_zip' else self.engine.prepare()
                self.confirmations[value['id']] = value.pop('confirmation')
            else:
                self.engine.install(arguments['id'],arguments['confirmation'])
                self.confirmations.pop(arguments['id'],None)
        except Refused as error:
            # Detailed safe failure code is already persisted by Engine. No
            # exception text, environment, request or credentials in stdout.
            self.last_error = error.code
        except Exception:
            self.last_error = 'AGENT_OPERATION_FAILED_REVIEW_REQUIRED'
        finally:
            if operation=='prepare_zip':
                arguments.stream.close()


class Handler(socketserver.StreamRequestHandler):
    def reply(self,result,nonce):
        response = result | {'nonce':nonce}
        signature = hmac.new(self.server.authentication.token, pack(response), hashlib.sha256).hexdigest()
        self.wfile.write(pack(response | {'signature':signature})+b'\n')

    def handle(self):
        self.request.settimeout(5)
        nonce = ''
        try:
            raw = self.rfile.readline(MAX_MESSAGE+1)
            if len(raw) > MAX_MESSAGE or not raw.endswith(b'\n'):
                raise Refused('AGENT_REQUEST_TOO_LARGE')
            envelope = json.loads(raw)
            with self.server.guard:
                operation, arguments = self.server.authentication.verify(envelope)
            nonce = envelope['nonce']
            if operation=='prepare_zip':
                value=self.server.receive_zip(arguments,self.rfile,self.request,
                    lambda:self.reply(dict(ok=True,value={'ready_for_upload':True}),nonce))
            else:
                value=self.server.dispatch(operation,arguments)
            result = dict(ok=True, value=value)
        except Exception as error:
            result = dict(ok=False, code=error.code if isinstance(error,Refused) else 'AGENT_REQUEST_FAILED')
        try:
            self.reply(result,nonce)
        except OSError:
            pass
