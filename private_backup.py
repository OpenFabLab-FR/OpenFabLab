"""Private persistent-state backups. No application import, no network access.

All persistent files are included by default; only documented transient and
source-tree families are excluded. The ZIP is sensitive, not encrypted.
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, ZIP_DEFLATED
from runtime_policy import TEST_MARKER, storage_guard, is_test_instance
from openfablab import __version__

FORMAT = 'openfablab-private-backup'
FORMAT_VERSION = 1
MAX_TOTAL = 2 * 1024**3
MAX_FILES = 20000
MANIFEST = 'backup-manifest.json'
JOURNAL = '.openfablab-restore-in-progress.json'
TRANSIENT_DIRS = {'__pycache__', '.pytest_cache', '.cache', 'cache', 'caches', 'logs',
                  'tmp', 'temp', 'backups', 'Saves', 'sauvegardes', 'migration-backups',
                  'restore-backups'}
SOURCE_DIRS = {'static', 'templates', 'openfablab', 'badge_templates', 'docs', 'tests',
               'tools', 'wordpress', 'dist', 'node_modules', '.venv', '.git', '.checks', 'review'}


def _json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    with open(temporary, 'x', encoding='utf-8') as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _safe_name(name):
    if (not isinstance(name, str) or not name or '\\' in name or '\x00' in name
            or name.startswith('/') or ':' in name
            or any(p in ('', '.', '..') for p in name.split('/'))):
        raise ValueError('Chemin d’archive interdit.')
    return name


def sqlite_check(path, expected=None):
    if not Path(path).is_file():
        raise ValueError('Base SQLite absente.')
    with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        schema = db.execute('PRAGMA user_version').fetchone()[0]
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'users', 'sessions', 'visitors', 'app_settings'} <= tables:
            raise ValueError('Ce fichier n’est pas une base OpenFabLab.')
        if schema not in (13, 14, 15, 16, 17, 18) or (expected is not None and schema != expected):
            raise ValueError('Schéma SQLite incompatible (13 à 18 requis).')
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Intégrité SQLite invalide.')
        if db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Clés étrangères SQLite invalides.')
        return schema


def persistent_files(database_path):
    database = Path(database_path).resolve()
    root = database.parent
    co_located = (root / 'app.py').is_file() and (root / 'openfablab').is_dir()
    public = set()
    if co_located:
        manifest = root / 'PUBLIC_FILES.txt'
        if manifest.is_file():
            public = set(manifest.read_text().splitlines())
    def excluded(relative):
        parts, name = relative.parts, relative.name
        if name == database.name or name in {JOURNAL, '.openfablab_pin_recovery'}:
            return True
        if any(p in TRANSIENT_DIRS or p.startswith('.openfablab-restore-stage-') for p in parts):
            return True
        if (name in {'.DS_Store', *(database.name + s for s in ('-wal','-shm','-journal'))}
                or name.startswith('._') or name.endswith(('.lock', '.log', '.tmp', '.temp', '.pyc'))):
            return True
        if name.startswith(('openfablab-sauvegarde-', 'openfablab-copie-test-', 'before-2.7-schema-')):
            return True
        if co_located and (relative.as_posix() in public or parts[0] in SOURCE_DIRS
                           or name.endswith(('.py', '.command')) or name in
                           {'Dockerfile', 'compose.yaml', 'requirements.txt', 'requirements-nas.txt'}):
            return True
        return False
    result = []
    def visit(folder):
        for path in sorted(folder.iterdir()):
            relative = path.relative_to(root)
            if excluded(relative):
                continue
            if path.is_symlink():
                raise ValueError('Lien symbolique persistant non pris en charge ; sauvegarde refusée.')
            if path.is_dir():
                visit(path)
            elif path.is_file():
                result.append(path)
            else:
                raise ValueError('Fichier persistant spécial non pris en charge.')
    visit(root)
    return result


def neutralize(root, bindings=None):
    """Only a staged COPY is changed; original data and credentials never touched."""
    root = Path(root)
    db_path = root / 'openfablab.db'
    with sqlite3.connect(db_path) as db:
        for key, value in list(db.execute('SELECT key,value FROM app_settings')):
            if (key in {'module_public_reservations', 'module_discord', 'module_weather', 'welcome_enabled', 'smtp_enabled'}
                    or (key.startswith('discord_') and key.endswith('_enabled'))):
                db.execute('UPDATE app_settings SET value=? WHERE key=?', ('0', key))
            elif key == 'discord_enabled':
                db.execute('UPDATE app_settings SET value=? WHERE key=?', ('0', key))
            elif any(word in key.lower() for word in ('webhook', 'secret', 'password', 'token')) or key == 'reservation_wordpress_url':
                db.execute('UPDATE app_settings SET value=? WHERE key=?', ('', key))
        db.commit()
    for path in list(root.rglob('*')):
        if not path.is_file():
            continue
        name = path.name.lower()
        # Unknown private files are retained in a FULL backup. A test clone must
        # fail closed rather than leak opaque credentials from a future version.
        if ('sync_secret' in name or 'webhook' in name or name.startswith('.discord_')
                or name.startswith('.env') or name == '.openfablab_pin_recovery'):
            path.unlink()
        elif name == '.openfablab_smtp.json':
            config = json.loads(path.read_text())
            config.update(enabled=False, password='', username='', host='')
            path.unlink(); _json(path, config)
    bindings = bindings or {}
    if bindings.get('discord'):
        (root / bindings['discord']).unlink(missing_ok=True)
    # Session signing keys are regenerated for a test clone; PIN derivations
    # are independent and preserved verbatim. Production cookies cannot work.
    flask_file = bindings.get('flask', '.openfablab_flask_secret')
    secret_path = root / flask_file
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    session_key = secrets.token_hex(32)
    secret_path.write_text(session_key); secret_path.chmod(0o600)
    for name in ('.secret_key', '.openfablab_flask_secret'):
        alternate = root / name
        if alternate.is_file():
            alternate.write_text(session_key); alternate.chmod(0o600)
    marker = root / TEST_MARKER
    marker.unlink(missing_ok=True)
    _json(marker, {'format': 'openfablab-test-instance', 'version': 1, 'external_actions': False})


def create_backup(database_path, output, *, app_version=__version__, kind='complete', extras=None,
                  secret_key=None):
    if kind not in ('complete', 'test'):
        raise ValueError('Type de sauvegarde inconnu.')
    database, output = Path(database_path).resolve(), Path(output).resolve()
    if output.parent == database.parent:
        raise ValueError('Créez l’archive hors du dossier persistant actif.')
    with storage_guard(database), tempfile.TemporaryDirectory(prefix='openfablab-backup-') as folder:
        root = Path(folder) / 'persistent'; root.mkdir(mode=0o700)
        schema = sqlite_check(database)
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as source:
            with sqlite3.connect(root / 'openfablab.db') as target:
                source.backup(target)
                target.execute('PRAGMA journal_mode=DELETE')
        for path in persistent_files(database):
            target = root / path.relative_to(database.parent)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(path, target)
        bindings = {'flask': ('.secret_key' if (root / '.secret_key').is_file() and not (root / '.openfablab_flask_secret').exists()
                              else '.openfablab_flask_secret'), 'discord': '.discord_webhook_url'}
        for component, path in (extras or {}).items():
            if component not in bindings:
                raise ValueError('Composant supplémentaire inconnu.')
            path = Path(path).resolve()
            name = path.relative_to(database.parent).as_posix() if path.is_relative_to(database.parent) else bindings[component]
            _safe_name(name); bindings[component] = name
            if path.is_file():
                target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        if secret_key is not None:
            path = root / bindings['flask']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(secret_key)); path.chmod(0o600)
        if kind == 'test' or is_test_instance(database):
            kind = 'test'
            neutralize(root, bindings)
        sqlite_check(root / 'openfablab.db', schema)
        with sqlite3.connect(root / 'openfablab.db') as copied:
            if copied.execute("SELECT 1 FROM app_settings WHERE key IN ('admin_pin','moderator_pin') AND COALESCE(value,'')!=''").fetchone():
                raise ValueError('Ancien PIN en clair : dérivation préalable nécessaire avant une sauvegarde privée.')
        for path in root.rglob('.env*'):
            if path.is_file():
                text = path.read_text()
                path.write_text(re.sub(r'(?m)^\s*(?:export\s+)?(?:OPENFABLAB|COMPTEUR)_(?:ADMIN|MODERATOR)_PIN\s*=.*(?:\n|$)', '', text))
        records = []
        for path in sorted(root.rglob('*')):
            if path.is_file():
                data = path.read_bytes()
                records.append({'path': path.relative_to(root).as_posix(), 'size': len(data),
                                'sha256': hashlib.sha256(data).hexdigest(),
                                'mode': stat.S_IMODE(path.stat().st_mode) & 0o777})
        if len(records) > MAX_FILES or sum(r['size'] for r in records) > MAX_TOTAL:
            raise ValueError('Sauvegarde trop volumineuse pour ce format.')
        manifest = {'format': FORMAT, 'format_version': FORMAT_VERSION, 'kind': kind,
                    'openfablab_version': app_version, 'sqlite_schema': schema,
                    'created_at': datetime.now(timezone.utc).isoformat(), 'files': records,
                    'bindings': bindings, 'components': {
                        'database': True, 'admin_pin': (root / '.openfablab_admin_pin').is_file(),
                        'moderator_pin': (root / '.openfablab_moderator_pin').is_file(),
                        'branding': (root / 'branding').is_dir(),
                        'smtp': (root / '.openfablab_smtp.json').is_file(),
                        'wordpress': (root / '.openfablab_sync_secret').is_file(),
                        'discord': (root / bindings['discord']).is_file(),
                        'flask_key': (root / bindings['flask']).is_file()}}
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_name(output.name + '.' + secrets.token_hex(8) + '.tmp')
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'wb') as stream, ZipFile(stream, 'w', ZIP_DEFLATED) as archive:
                archive.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
                for record in records:
                    archive.write(root / record['path'], 'persistent/' + record['path'])
            validate_backup(temporary)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
        return manifest


def validate_backup(archive_path, destination=None):
    """Validate every byte and exact membership before accepting a restore."""
    with ZipFile(archive_path) as archive, tempfile.TemporaryDirectory(prefix='openfablab-validate-') as folder:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        if len(names) != len(set(names)) or len(names) > MAX_FILES + 1 or MANIFEST not in names:
            raise ValueError('Liste de fichiers de sauvegarde invalide.')
        if sum(i.file_size for i in infos) > MAX_TOTAL or archive.getinfo(MANIFEST).file_size > 8 * 1024**2:
            raise ValueError('Archive trop volumineuse.')
        for info in infos:
            _safe_name(info.filename)
            mode = info.external_attr >> 16
            if info.is_dir() or stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
                raise ValueError('Type de fichier ZIP interdit.')
        manifest = json.loads(archive.read(MANIFEST))
        if (manifest.get('format') != FORMAT or manifest.get('format_version') != FORMAT_VERSION
                or manifest.get('kind') not in ('complete', 'test')):
            raise ValueError('Format de sauvegarde inconnu.')
        version = manifest.get('openfablab_version', '')
        if not re.fullmatch(r'2\.(?:6\.[0-9]+|7\.[0-9]+|8\.[0-9]+)', version):
            raise ValueError('Version OpenFabLab incompatible avec cette restauration.')
        records = manifest.get('files')
        if not isinstance(records, list):
            raise ValueError('Manifeste invalide.')
        paths = [_safe_name(r['path']) for r in records]
        if len(paths) != len({p.casefold() for p in paths}) or set(names) != {MANIFEST, *('persistent/' + p for p in paths)}:
            raise ValueError('Contenu différent du manifeste.')
        if 'openfablab.db' not in paths or any(p.split('/')[0] in SOURCE_DIRS | TRANSIENT_DIRS or p == JOURNAL
                                             or p.endswith('.lock') or p in {'openfablab.db-wal','openfablab.db-shm','openfablab.db-journal'} for p in paths):
            raise ValueError('Fichier persistant interdit dans la sauvegarde.')
        bindings = manifest.get('bindings', {})
        if set(bindings) != {'flask', 'discord'} or len(set(bindings.values())) != 2:
            raise ValueError('Liaisons privées invalides.')
        for name in bindings.values():
            _safe_name(name)
            if name == 'openfablab.db':
                raise ValueError('Liaison privée invalide.')
        root = Path(folder)
        for record in records:
            data = archive.read('persistent/' + record['path'])
            if len(data) != record['size'] or hashlib.sha256(data).hexdigest() != record['sha256']:
                raise ValueError('Empreinte de sauvegarde invalide.')
            path = root / record['path']; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data); path.chmod(0o600)
        sqlite_check(root / 'openfablab.db', manifest.get('sqlite_schema'))
        for role in ('admin', 'moderator'):
            pin = root / ('.openfablab_' + role + '_pin')
            if pin.exists() and not re.fullmatch(r'(?:scrypt\$16384\$8\$1|pbkdf2-sha256\$600000\$0\$0)\$[a-f0-9]{32}\$[a-f0-9]{64}\s*', pin.read_text()):
                raise ValueError('Dérivation de PIN invalide.')
        if manifest['kind'] == 'test':
            neutralize(root, bindings)
        if destination is not None:
            destination = Path(destination)
            if destination.exists() and any(destination.iterdir()):
                raise ValueError('Le dossier de validation doit être vide.')
            shutil.copytree(root, destination, dirs_exist_ok=True)
        return manifest


def recover_restore(database_path):
    """Recover an interrupted replacement without ever merging installations."""
    database = Path(database_path).resolve(); root = database.parent
    with storage_guard(database):
        journal_path = root / JOURNAL
        if not journal_path.exists():
            return
        journal = json.loads(journal_path.read_text())
        transaction = _safe_name(journal['transaction'])
        if not re.fullmatch(r'restore-backups/[a-f0-9]{32}', transaction):
            raise ValueError('Journal de restauration invalide.')
        transaction = root / transaction
        for group in ('old_names', 'new_names'):
            if any('/' in _safe_name(n) or n in SOURCE_DIRS | TRANSIENT_DIRS for n in journal[group]):
                raise ValueError('Journal de restauration invalide.')
        failed = transaction / 'failed'; failed.mkdir(exist_ok=True)
        if journal['phase'] == 'installing':
            for name in journal['new_names']:
                if (root / name).exists():
                    os.replace(root / name, failed / name)
        for name in journal['old_names']:
            old = transaction / 'old' / name
            if old.exists():
                os.replace(old, root / name)
        for suffix in ('-wal', '-shm', '-journal'):
            path = transaction / 'old' / (database.name + suffix)
            if path.exists():
                os.replace(path, Path(str(database) + suffix))
        os.replace(journal_path, transaction / 'recovered-journal.json')


def restore_backup(archive_path, database_path, *, bindings=None, secret_key=None, after_restore=None):
    database = Path(database_path).resolve(); root = database.parent
    root.mkdir(parents=True, exist_ok=True)
    with storage_guard(database):
        if (root / JOURNAL).exists():
            raise ValueError('Restauration interrompue : utilisez la récupération hors ligne avant de poursuivre.')
        with tempfile.TemporaryDirectory(prefix='.openfablab-restore-stage-', dir=root) as folder:
            stage = Path(folder) / 'payload'
            manifest = validate_backup(archive_path, stage)
            if (root / 'PUBLIC_FILES.txt').is_file():
                public = set((root / 'PUBLIC_FILES.txt').read_text().splitlines())
                if any(p.relative_to(stage).as_posix() in public for p in stage.rglob('*') if p.is_file()):
                    raise ValueError('La sauvegarde contient un fichier de code public, pas un fichier persistant.')
            if is_test_instance(database) and manifest['kind'] != 'test':
                neutralize(stage, manifest['bindings']); manifest['kind'] = 'test'
            # Map persistent keys to THIS runtime's paths, not the source host.
            for component, target in (bindings or {}).items():
                if component not in manifest['bindings']:
                    raise ValueError('Liaison de restauration inconnue.')
                target = Path(target).resolve()
                if not target.is_relative_to(root):
                    raise ValueError('Restaurez d’abord hors ligne : une clé privée est configurée hors du dossier persistant.')
                source = stage / manifest['bindings'][component]
                relative = target.relative_to(root)
                _safe_name(relative.as_posix())
                if relative.as_posix() == database.name or relative.name.endswith('.lock'):
                    raise ValueError('Liaison privée incompatible avec le stockage.')
                if source.exists() and source != stage / relative:
                    if (stage / relative).exists():
                        raise ValueError('Liaison de clé ambiguë.')
                    (stage / relative).parent.mkdir(parents=True, exist_ok=True)
                    os.replace(source, stage / relative)
            if database.name != 'openfablab.db':
                if (stage / database.name).exists():
                    raise ValueError('Nom de base ambigu.')
                os.replace(stage / 'openfablab.db', stage / database.name)
            transaction = root / 'restore-backups' / secrets.token_hex(16)
            if not transaction.resolve().is_relative_to(root):
                raise ValueError('Dossier de sécurité hors du stockage persistant.')
            transaction.mkdir(parents=True, mode=0o700)
            if database.exists():
                create_backup(database, transaction / 'before-restore.zip', secret_key=secret_key)
            old_names = sorted({p.relative_to(root).parts[0] for p in persistent_files(database)} | ({database.name} if database.exists() else set()))
            new_names = sorted(p.name for p in stage.iterdir())
            journal = {'transaction': transaction.relative_to(root).as_posix(), 'phase': 'moving',
                       'old_names': old_names, 'new_names': new_names}
            (transaction / 'old').mkdir()
            _json(root / JOURNAL, journal)
            try:
                for name in old_names:
                    os.replace(root / name, transaction / 'old' / name)
                # SQLite sidecars refer to the previous installation, never merge.
                for suffix in ('-wal', '-shm', '-journal'):
                    path = Path(str(database) + suffix)
                    if path.exists():
                        os.replace(path, transaction / 'old' / path.name)
                journal['phase'] = 'installing'; _json(root / JOURNAL, journal)
                for name in new_names:
                    os.replace(stage / name, root / name)
                sqlite_check(database, manifest['sqlite_schema'])
                if after_restore is not None:
                    after_restore()
                    sqlite_check(database)
                os.replace(root / JOURNAL, transaction / 'completed-journal.json')
            except BaseException:
                recover_restore(database)
                raise
            return manifest, transaction


def register(application, api, csrf_valid):
    from flask import abort, flash, redirect, request, send_file, session, url_for
    import io
    def bindings():
        database = Path(application.config['DATABASE'])
        return {'flask': Path(application.config['PRIVATE_SECRET_PATH']),
                'discord': Path(application.config['DISCORD_WEBHOOK_FILE'])}
    def allowed():
        if session.get('access_role') != 'admin' and not session.get('admin_authenticated'):
            abort(403)
        if not csrf_valid():
            abort(400)
    @application.post('/admin/sauvegarde/privee/<kind>')
    def admin_private_backup(kind):
        allowed()
        if kind not in ('complete', 'test') or request.form.get('sensitive_ack') != '1':
            abort(400)
        with tempfile.TemporaryDirectory(prefix='openfablab-private-download-') as folder:
            path = Path(folder) / 'backup.zip'
            try:
                create_backup(application.config['DATABASE'], path, kind=kind,
                              extras=bindings(), secret_key=application.secret_key)
            except (OSError, ValueError, sqlite3.Error):
                flash('Sauvegarde privée refusée : vérifiez le stockage persistant et l’intégrité de la base.', 'error')
                return redirect(url_for('admin_settings_data'))
            data = io.BytesIO(path.read_bytes())
        name = ('openfablab-copie-test-' if kind == 'test' else 'openfablab-sauvegarde-complete-') + datetime.now().strftime('%Y-%m-%d_%H-%M') + '.zip'
        response = send_file(data, mimetype='application/zip', as_attachment=True, download_name=name)
        response.headers['Cache-Control'] = 'no-store, private'
        return response
    @application.post('/admin/sauvegarde/restaurer-privee')
    def admin_restore_private():
        allowed()
        if request.form.get('confirmation') != 'RESTAURER INSTALLATION':
            abort(400)
        uploaded = request.files.get('private_backup')
        if uploaded is None:
            abort(400)
        with tempfile.TemporaryDirectory(prefix='openfablab-private-upload-') as folder:
            path = Path(folder) / 'backup.zip'; uploaded.save(path)
            try:
                api['close_database']()
                def initialize_restored():
                    try:
                        api['initialize_database']()
                    finally:
                        api['close_database']()
                manifest, _safety = restore_backup(path, application.config['DATABASE'], bindings=bindings(), secret_key=application.secret_key, after_restore=initialize_restored)
                key = bindings()['flask']
                if key.is_file():
                    application.secret_key = key.read_text().strip()
                if manifest['kind'] == 'test':
                    application.config.update(EXTERNAL_ACTIONS=False, AUTO_CLOSURE_WORKER=False, WEATHER_ENABLED=False)
            except (OSError, ValueError, RuntimeError, sqlite3.Error, __import__('zipfile').BadZipFile, KeyError, TypeError):
                flash('Archive invalide ou restauration refusée. L’état précédent est conservé ; vérifiez l’archive et le stockage.', 'error')
                return redirect(url_for('admin_settings_data'))
        session.clear()
        flash('Installation restaurée. Reconnectez-vous avec le PIN de la sauvegarde.', 'success')
        return redirect(url_for('admin_login'))


def main():
    parser = argparse.ArgumentParser(description='Sauvegarde privée OpenFabLab — fichiers sensibles, jamais publics.')
    parser.add_argument('action', choices=('export', 'validate', 'restore', 'recover'))
    parser.add_argument('--database', type=Path)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--kind', choices=('complete', 'test'), default='complete')
    parser.add_argument('--app-version', default=__version__)
    args = parser.parse_args()
    if args.action == 'validate':
        validate_backup(args.archive)
    elif args.action == 'export':
        create_backup(args.database, args.archive, kind=args.kind, app_version=args.app_version)
    elif args.action == 'restore':
        restore_backup(args.archive, args.database)
    else:
        recover_restore(args.database)
    print('PRIVATE_BACKUP_OPERATION=OK (contenu et secrets non affichés)')


if __name__ == '__main__':
    main()
