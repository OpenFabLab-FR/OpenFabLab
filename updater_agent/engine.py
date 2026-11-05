"""Durable update state machine. Host operations belong only to the executor.

No automatic restoration, downgrade or resumption, including after SIGKILL.
Every dangerous boundary is persisted *before* calling the executor.
"""
import fcntl
import hashlib
import json
from pathlib import Path
import re
import secrets
import time
from .security import Refused, private_json, version

TERMINAL = {'success','refused','failed_preserved'}
VISIBLE = {'id','phase','result','code','version','source_version','source_schema','target_schema',
           'created_at','updated_at','events','public_start_attempted','migration_attempted',
           'production_stop_attempted','pre_backup','post_backup','recovery_required',
           'channel','notes','migration_required','isolated_probe_pending'}


class Engine:
    def __init__(self, policy, releases, executor):
        self.policy, self.releases, self.executor = policy, releases, executor
        self.root = Path(policy['state'])
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.root.chmod(0o700)

    def locked(self):
        lock = (self.root/'operation.lock').open('a+')
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            raise Refused('AGENT_OPERATION_IN_PROGRESS') from None
        return lock

    def read(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch('[0-9a-f]{32}', identifier):
            raise Refused('UPDATE_JOB_UNKNOWN')
        try:
            return json.loads((self.root/identifier/'job.json').read_bytes())
        except FileNotFoundError:
            raise Refused('UPDATE_JOB_UNKNOWN') from None

    def save(self, job, phase, result=None, code=None):
        job['phase'] = phase
        job['updated_at'] = int(time.time())
        if result:
            job['result'] = result
        if code:
            job['code'] = code
        job['events'].append(dict(phase=phase, at=job['updated_at'], code=code or 'OK'))
        private_json(self.root/job['id']/'job.json', job)

    def status(self, identifier=None):
        if identifier is None:
            jobs = sorted(self.root.glob('*/job.json'), key=lambda p:p.stat().st_mtime, reverse=True)
            if not jobs:
                return dict(phase='idle', enabled=self.policy['enabled'])
            identifier = jobs[0].parent.name
        job = self.read(identifier)
        return {k: v for k, v in job.items() if k in VISIBLE}

    def available(self):
        if not self.policy['enabled'] or (self.root/'disabled').exists():
            raise Refused('AGENT_DISABLED')
        for path in self.root.glob('*/job.json'):
            previous = json.loads(path.read_bytes())
            if previous['result'] not in TERMINAL:
                raise Refused('UNFINISHED_JOB_REQUIRES_HUMAN_DECISION')
            if previous.get('recovery_required'):
                raise Refused('PRESERVED_STATE_REQUIRES_RECOVERY')

    def history(self):
        paths = sorted(self.root.glob('*/job.json'), key=lambda p:p.stat().st_mtime, reverse=True)
        keys = {'id','version','source_version','source_schema','target_schema','channel','result','code','updated_at'}
        return [{k:v for k,v in self.read(p.parent.name).items() if k in keys} for p in paths[:6]]

    def discover(self):
        if not self.policy['enabled'] or (self.root/'disabled').exists():
            raise Refused('AGENT_DISABLED')
        source = self.executor.inspect()
        release = self.releases.latest()
        return dict(current=source['version'], schema=source['schema'], latest=release['version'],
                    newer=version(release['version']) > version(source['version']), notes=release['notes'],
                    page=release['page'], automatic_compatibility='not_yet_verified')

    def prepare(self, local=None):
        with self.locked():
            self.available()
            identifier = secrets.token_hex(16)
            (self.root/identifier).mkdir(mode=0o700)
            job = dict(id=identifier, result='preparing', phase='created', events=[], created_at=int(time.time()),
                       production_stop_attempted=False, migration_attempted=False,
                       public_start_attempted=False, recovery_required=False)
            self.save(job, 'checking_source')
            try:
                source = self.executor.inspect()
                provider = local if local is not None else self.releases
                release = provider.latest()
                if version(release['version']) <= version(source['version']):
                    raise Refused('LOCAL_ZIP_VERSION_NOT_NEWER' if local is not None else 'NO_NEWER_OFFICIAL_STABLE')
                job.update(source=source, release=release, version=release['version'],
                           source_version=source['version'], source_schema=source['schema'],
                           channel='zip' if local is not None else 'github', notes=release.get('notes','')[:8000])
                self.save(job, 'validating_zip' if local is not None else 'downloading')
                archive = provider.download(release, self.root/identifier/'application.zip')
                manifest = self.executor.unpack(archive, self.root/identifier/'runtime', release['version'])
                if source['schema'] not in manifest['source_schemas'] or manifest['schema'] < source['schema']:
                    raise Refused('SOURCE_SCHEMA_NOT_SUPPORTED')
                job.update(manifest=manifest, target_schema=manifest['schema'],
                           migration_required=manifest['schema']>source['schema'], isolated_probe_pending=local is not None)
                self.save(job, 'checking_space_and_access')
                self.executor.preflight(job)
                # A local archive contains executable code. Structural and
                # compatibility checks are safe before explicit consent; do
                # not build or run that code before the administrator agrees.
                if local is None:
                    self.build_and_probe(job)
                self.save(job, 'verifying_source_unchanged')
                self.executor.verify_source(job)
                confirmation = secrets.token_urlsafe(32)
                job['confirmation_hash'] = hashlib.sha256(confirmation.encode()).hexdigest()
                job['confirmation_expires'] = int(time.time())+1800
                self.save(job, 'ready', 'ready')
                return self.status(identifier) | dict(confirmation=confirmation)
            except Exception as error:
                self.fail(job, error)
                raise Refused(job['code']) from None

    def build_and_probe(self,job):
        self.save(job, 'building_image')
        job['target'] = self.executor.build(job)
        self.save(job, 'isolated_migration_and_health')
        self.executor.probe(job)
        job['isolated_probe_pending'] = False

    def fail(self, job, error):
        code = error.code if isinstance(error, Refused) else 'UNCLASSIFIED_AGENT_FAILURE'
        dangerous = job['production_stop_attempted']
        if job['public_start_attempted']:
            # Fail closed without overwriting even a single newly recorded row.
            try:
                self.executor.stop_target(job)
            except Exception:
                code += '_STOP_UNCONFIRMED'
        if dangerous:
            try:
                self.executor.preserve(job)
            except Exception:
                code += '_PRESERVATION_UNCONFIRMED'
        job['recovery_required'] = dangerous
        self.save(job, 'failed_preserved' if dangerous else 'refused',
                  'failed_preserved' if dangerous else 'refused', code)

    def install(self, identifier, confirmation):
        import hmac
        with self.locked():
            if not self.policy['enabled'] or (self.root/'disabled').exists():
                raise Refused('AGENT_DISABLED')
            job = self.read(identifier)
            if (job['result'] != 'ready' or type(confirmation) is not str or len(confirmation) > 100
                    or int(time.time()) > job['confirmation_expires']
                    or not hmac.compare_digest(hashlib.sha256(confirmation.encode()).hexdigest(), job['confirmation_hash'])):
                raise Refused('UPDATE_CONFIRMATION_REFUSED')
            # Consumed before any action; a replay cannot start a second update.
            job.pop('confirmation_hash')
            self.save(job, 'checking_before_install', 'installing')
            try:
                self.executor.verify_source(job)
                self.executor.preflight(job)
                if job.get('isolated_probe_pending'):
                    self.build_and_probe(job)
                    self.executor.verify_source(job)
                self.save(job, 'coherent_hot_backup')
                self.executor.hot_backup(job)
                self.save(job, 'last_source_check_before_stop')
                self.executor.verify_source(job)
                job['production_stop_attempted'] = True
                self.save(job, 'stopping_source')
                self.executor.stop_source(job)
                self.save(job, 'complete_cold_pre_backup')
                job['pre_backup'] = self.executor.cold_backup(job)
                if job['target_schema'] > job['source_schema']:
                    job['migration_attempted'] = True
                    self.save(job, 'migration')
                    self.executor.migrate(job)
                self.save(job, 'verifying_migration')
                self.executor.verify_migration(job)
                self.save(job, 'installing_runtime')
                self.executor.install_runtime(job)
                job['public_start_attempted'] = True
                job['public_started_at'] = int(time.time())
                self.save(job, 'starting_target')
                self.executor.start_target(job)
                self.finish(job)
            except Exception as error:
                self.fail(job, error)
            return self.status(identifier)

    def finish(self, job):
        self.save(job, 'http_health_and_identity')
        self.executor.health(job)
        self.save(job, 'data_and_private_state')
        self.executor.verify_live(job)
        self.save(job, 'wordpress_normal_test')
        self.executor.relay(job)
        self.save(job, 'post_relay_integrity')
        self.executor.verify_live(job)
        self.save(job, 'complete_post_backup')
        job['post_backup'] = self.executor.post_backup(job)
        job['recovery_required'] = False
        self.save(job, 'success', 'success', 'UPDATE_SUCCESS')

    def recovery_diagnostic(self, identifier):
        with self.locked():
            job = self.read(identifier)
            if not job['production_stop_attempted'] or job['result'] == 'success':
                raise Refused('NO_PRESERVED_RECOVERY_STATE')
            # Independent executor inspection. Never replays migration or guesses
            # that source version can run against the database now on disk.
            result = self.executor.recovery_check(job)
            return dict(job=identifier, diagnostic=result, automatic_restore=False)

    def resume(self, identifier, confirmation):
        with self.locked():
            job = self.read(identifier)
            if confirmation != 'RESUME-'+identifier or not self.policy['enabled'] or (self.root/'disabled').exists():
                raise Refused('RECOVERY_CONFIRMATION_REFUSED')
            if job['result'] == 'success' or not job['production_stop_attempted']:
                raise Refused('NO_PRESERVED_RECOVERY_STATE')
            check = self.executor.recovery_check(job)
            if check.get('can_resume_target') is not True:
                raise Refused('RECOVERY_TARGET_NOT_VERIFIED')
            try:
                self.save(job, 'resuming_verified_target', 'recovering')
                job['public_start_attempted'] = True
                job['public_started_at'] = int(time.time())
                self.save(job, 'starting_target')
                self.executor.start_target(job)
                self.finish(job)
            except Exception as error:
                self.fail(job, error)
            return self.status(identifier)
