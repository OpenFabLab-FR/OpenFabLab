"""PIN credentials kept outside SQLite exports and deployment archives."""

import ast
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path


PIN_PATTERN = re.compile(r"^[0-9]{4}$")
SCRYPT_N = 1 << 14
SCRYPT_R = 8
SCRYPT_P = 1
PBKDF2_ITERATIONS = 600_000


def valid_pin(pin):
    return isinstance(pin, str) and PIN_PATTERN.fullmatch(pin) is not None


def credential_path(database_path, role):
    if role not in {"admin", "moderator"}:
        raise ValueError("Rôle de PIN inconnu")
    return Path(database_path).with_name(f".openfablab_{role}_pin")


def recovery_path(database_path):
    return Path(database_path).with_name(".openfablab_pin_recovery")


def _private_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _derive(pin, salt, algorithm):
    if algorithm == "scrypt":
        return hashlib.scrypt(pin.encode("ascii"), salt=salt, n=SCRYPT_N,
                              r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    if algorithm == "pbkdf2-sha256":
        return hashlib.pbkdf2_hmac("sha256", pin.encode("ascii"), salt,
                                   PBKDF2_ITERATIONS, dklen=32)
    raise ValueError("Algorithme de PIN inconnu")


def set_pin(database_path, role, pin):
    if not valid_pin(pin):
        raise ValueError("Le PIN doit contenir exactement quatre chiffres.")
    salt = secrets.token_bytes(16)
    algorithm = "scrypt" if hasattr(hashlib, "scrypt") else "pbkdf2-sha256"
    digest = _derive(pin, salt, algorithm)
    params = (f"{SCRYPT_N}${SCRYPT_R}${SCRYPT_P}" if algorithm == "scrypt"
              else f"{PBKDF2_ITERATIONS}$0$0")
    _private_write(credential_path(database_path, role),
                   f"{algorithm}${params}${salt.hex()}${digest.hex()}\n")


def migrate_legacy_admin_pin(database_path, legacy_archive):
    """Derive the configured legacy fallback from a local backup, never execute it."""
    if has_pin(database_path, "admin"):
        raise ValueError("Un PIN administrateur sécurisé est déjà configuré.")
    with zipfile.ZipFile(legacy_archive) as archive:
        source = archive.getinfo("app.py")
        if source.file_size > 2_000_000:
            raise ValueError("L'archive historique est invalide.")
        tree = ast.parse(archive.read(source).decode("utf-8"))
    configured_values = [node.value for node in ast.walk(tree)
                         if isinstance(node, ast.keyword) and node.arg == "ADMIN_PIN"]
    configured_values.extend(
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "ADMIN_PIN"
                for target in node.targets)
    )
    candidates = {child.value for value in configured_values
                  for child in ast.walk(value)
                  if isinstance(child, ast.Constant) and valid_pin(child.value)}
    if len(candidates) != 1:
        raise ValueError("L'archive ne contient pas un PIN historique unique.")
    set_pin(database_path, "admin", candidates.pop())


def has_pin(database_path, role):
    return credential_path(database_path, role).is_file()


def check_pin(database_path, role, candidate):
    if not valid_pin(candidate):
        return False
    try:
        algorithm, n, r, p, salt, digest = credential_path(database_path, role).read_text(
            encoding="ascii"
        ).strip().split("$")
        parameters = (int(n), int(r), int(p))
        if not ((algorithm == "scrypt" and parameters ==
                 (SCRYPT_N, SCRYPT_R, SCRYPT_P)) or
                (algorithm == "pbkdf2-sha256" and parameters ==
                 (PBKDF2_ITERATIONS, 0, 0))):
            return False
        return hmac.compare_digest(_derive(candidate, bytes.fromhex(salt), algorithm),
                                   bytes.fromhex(digest))
    except (OSError, ValueError, UnicodeError, AttributeError):
        return False


@contextmanager
def _recovery_lock(database_path):
    path = Path(database_path).with_name(".openfablab_pin_recovery.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def issue_recovery_token(database_path, now=None):
    """Only a local CLI should call this; replaces any previous token."""
    token = secrets.token_urlsafe(32)
    issued_at = time.time() if now is None else now
    state = {"digest": hashlib.sha256(token.encode("ascii")).hexdigest(),
             "expires_at": issued_at + 600}
    with _recovery_lock(database_path):
        _private_write(recovery_path(database_path), json.dumps(state))
    return token


def token_status(database_path, token, now=None):
    if not isinstance(token, str) or len(token) > 128:
        return "invalid"
    path = recovery_path(database_path)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "invalid"
    if (time.time() if now is None else now) >= state.get("expires_at", 0):
        return "expired"
    candidate = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return "valid" if hmac.compare_digest(candidate, state.get("digest", "")) else "invalid"


def consume_recovery_token(database_path, token, new_pin, now=None):
    if not valid_pin(new_pin):
        return "invalid_pin"
    with _recovery_lock(database_path):
        status = token_status(database_path, token, now)
        if status == "valid":
            set_pin(database_path, "admin", new_pin)
            recovery_path(database_path).unlink(missing_ok=True)
        elif status == "expired":
            recovery_path(database_path).unlink(missing_ok=True)
        return status
