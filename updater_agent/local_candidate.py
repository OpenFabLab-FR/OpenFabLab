"""Owner-selected bytes, never a path or URL supplied over the socket."""
import hashlib
import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from update_wire import MAX_LOCAL_ZIP
from .security import Refused, digest, version


class LocalCandidate:
    def __init__(self, stream, size, sha256):
        if type(size) is not int or not 0 < size <= MAX_LOCAL_ZIP:
            raise Refused('LOCAL_ZIP_SIZE_REFUSED')
        self.stream, self.size, self.sha256 = stream, size, digest(sha256)

    def latest(self):
        self.stream.seek(0)
        try:
            with ZipFile(self.stream) as archive:
                files = archive.infolist()
                if len(files) > 5000:
                    raise Refused('UPDATE_ARCHIVE_LIMIT_EXCEEDED')
                entries = [i for i in files if not i.is_dir() and i.filename.split('/')[-1] == 'UPDATE-MANIFEST.json']
                if len(entries) != 1 or entries[0].file_size > 2*1024*1024:
                    raise Refused('UPDATE_MANIFEST_UNAVAILABLE_USE_MANUAL')
                value = json.loads(archive.read(entries[0]))
        except (BadZipFile, ValueError, RuntimeError, NotImplementedError) as error:
            if isinstance(error, Refused):
                raise
            raise Refused('LOCAL_ZIP_MALFORMED') from None
        if not isinstance(value, dict):
            raise Refused('UPDATE_MANIFEST_INCOMPATIBLE')
        number = value.get('version')
        version(number)
        notes = value.get('notes')
        return dict(version=number, sha256=self.sha256, size=self.size,
                    notes=notes[:8000] if isinstance(notes,str) else '', channel='zip')

    def download(self, release, destination):
        destination = Path(destination)
        self.stream.seek(0)
        sha = hashlib.sha256()
        remaining = self.size
        with destination.open('xb') as target:
            destination.chmod(0o600)
            while remaining:
                chunk = self.stream.read(min(remaining, 65536))
                if not chunk:
                    raise Refused('LOCAL_ZIP_TRUNCATED')
                remaining -= len(chunk)
                sha.update(chunk)
                target.write(chunk)
            if self.stream.read(1) or sha.hexdigest() != self.sha256:
                raise Refused('LOCAL_ZIP_INTEGRITY_FAILED')
        return destination
