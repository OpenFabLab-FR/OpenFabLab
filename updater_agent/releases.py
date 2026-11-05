"""Fixed official repository, HTTPS, asset API digest and bounded extraction."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile
from .security import Refused, digest, version

REPO = 'OpenFabLab-FR/OpenFabLab'
HOSTS = {'api.github.com','github.com','release-assets.githubusercontent.com',
         'objects.githubusercontent.com'}
MAX_ASSET = 128 * 1024 * 1024


def safe_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.port not in (None,443)
            or parsed.username or parsed.password or parsed.fragment):
        raise Refused('OFFICIAL_DOWNLOAD_URL_REFUSED')
    return url


class Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, safe_url(newurl))


class OfficialReleases:
    def __init__(self, repository_id):
        self.repository_id = repository_id
        self.opener = build_opener(Redirects())

    def read(self, url, maximum):
        request = Request(safe_url(url), headers={'User-Agent':'OpenFabLab-local-updater/1',
            'Accept':'application/vnd.github+json', 'X-GitHub-Api-Version':'2022-11-28'})
        with self.opener.open(request, timeout=40) as response:
            data = response.read(maximum+1)
        if len(data) > maximum:
            raise Refused('OFFICIAL_RESPONSE_TOO_LARGE')
        return data

    def latest(self):
        repository = json.loads(self.read('https://api.github.com/repos/'+REPO, 100000))
        if repository.get('id') != self.repository_id or repository.get('full_name') != REPO or repository.get('private'):
            raise Refused('OFFICIAL_REPOSITORY_IDENTITY_CHANGED')
        release = json.loads(self.read('https://api.github.com/repos/'+REPO+'/releases/latest', 1000000))
        tag = release.get('tag_name', '')
        number = tag.removeprefix('v')
        version(number)
        if tag != 'v'+number or release.get('draft') or release.get('prerelease'):
            raise Refused('OFFICIAL_RELEASE_NOT_STABLE')
        assets = [a for a in release.get('assets', []) if a['name'] == 'OpenFabLab-'+number+'.zip']
        if len(assets) != 1:
            raise Refused('OFFICIAL_APPLICATION_ASSET_MISSING')
        asset = assets[0]
        sha = asset.get('digest','')
        if not sha.startswith('sha256:') or not 0 < asset['size'] <= MAX_ASSET:
            raise Refused('OFFICIAL_ASSET_DIGEST_UNAVAILABLE')
        digest(sha[7:])
        if asset.get('browser_download_url')!='https://github.com/'+REPO+'/releases/download/'+tag+'/OpenFabLab-'+number+'.zip':
            raise Refused('OFFICIAL_ASSET_LOCATION_MISMATCH')
        reference=json.loads(self.read('https://api.github.com/repos/'+REPO+'/git/ref/tags/'+tag,100000))
        target=reference.get('object',{})
        seen=set()
        for _ in range(5):
            identity=target.get('sha')
            if not isinstance(identity,str) or not re.fullmatch('[0-9a-f]{40}',identity) or identity in seen:
                raise Refused('OFFICIAL_TAG_IDENTITY_INVALID')
            if target.get('type')=='commit':break
            if target.get('type')!='tag':raise Refused('OFFICIAL_TAG_IDENTITY_INVALID')
            seen.add(identity)
            target=json.loads(self.read('https://api.github.com/repos/'+REPO+'/git/tags/'+identity,100000)).get('object',{})
        else:raise Refused('OFFICIAL_TAG_CHAIN_REFUSED')
        # Repository identity + TLS-protected GitHub asset metadata are the trust
        # anchor. No checksum supplied by the browser is accepted as authority.
        return dict(version=number, tag=tag, commit=identity, release_id=release['id'], asset_id=asset['id'],
                    sha256=sha[7:], size=asset['size'], url=safe_url(asset['browser_download_url']),
                    notes=str(release.get('body') or '')[:30000],
                    page='https://github.com/'+REPO+'/releases/tag/'+tag)

    def download(self, release, destination):
        data = self.read(release['url'], MAX_ASSET)
        if len(data) != release['size'] or hashlib.sha256(data).hexdigest() != release['sha256']:
            raise Refused('OFFICIAL_ASSET_INTEGRITY_FAILED')
        destination = Path(destination)
        with destination.open('xb') as stream:
            stream.write(data)
        destination.chmod(0o600)
        return destination


def unpack(path, destination, expected_version):
    """Exact manifested regular files only; no link, collision or path traversal."""
    try:return _unpack(path,destination,expected_version)
    except (BadZipFile, UnicodeError, NotImplementedError, json.JSONDecodeError):
        raise Refused('UPDATE_ARCHIVE_MALFORMED') from None

def _unpack(path,destination,expected_version):
    destination = Path(destination)
    if destination.exists():
        raise Refused('UPDATE_DESTINATION_ALREADY_EXISTS')
    with ZipFile(path) as archive:
        entries=archive.infolist()
        files = [i for i in entries if not i.is_dir()]
        if len(entries) > 5000 or sum(i.file_size for i in files) > 512*1024*1024:
            raise Refused('UPDATE_ARCHIVE_LIMIT_EXCEEDED')
        names = [i.filename for i in files]
        if len(names) != len(set(names)) or len({n.casefold() for n in names}) != len(names):
            raise Refused('UPDATE_ARCHIVE_DUPLICATE_PATH')
        seen=set()
        for item in entries:
            directory=item.is_dir()
            normalized=item.filename.rstrip('/') if directory else item.filename
            parts = normalized.split('/')
            mode = item.external_attr >> 16
            if (len(normalized)>500 or len(parts)>30 or
                    any(p in ('','.','..') or (p.startswith('.') and not (not directory and index==len(parts)-1 and p in ('.env.example','.dockerignore'))) for index,p in enumerate(parts))
                    or '\\' in item.filename or ':' in item.filename or '\x00' in item.filename
                    or any(ord(char)<32 for char in normalized)
                    or stat.S_IFMT(mode) not in (0,stat.S_IFDIR if directory else stat.S_IFREG)):
                raise Refused('UPDATE_ARCHIVE_UNSAFE_PATH')
            if normalized.casefold() in seen:raise Refused('UPDATE_ARCHIVE_DUPLICATE_PATH')
            seen.add(normalized.casefold())
            if item.flag_bits&1 or item.compress_type not in (ZIP_STORED,ZIP_DEFLATED):
                raise Refused('UPDATE_ARCHIVE_COMPRESSION_REFUSED')
        folded={name.casefold() for name in names}
        if any('/'.join(name.casefold().split('/')[:i]) in folded for name in names for i in range(1,len(name.split('/')))):
            raise Refused('UPDATE_ARCHIVE_FILE_DIRECTORY_COLLISION')
        manifests = [n for n in names if n == 'UPDATE-MANIFEST.json' or n.endswith('/UPDATE-MANIFEST.json')]
        if len(manifests) != 1:
            raise Refused('UPDATE_MANIFEST_UNAVAILABLE_USE_MANUAL')
        manifest_name = manifests[0]
        prefix = manifest_name[:-len('UPDATE-MANIFEST.json')]
        manifest_item = archive.getinfo(manifest_name)
        if manifest_item.file_size > 2*1024*1024:
            raise Refused('UPDATE_MANIFEST_TOO_LARGE')
        manifest = json.loads(archive.read(manifest_name))
        if (not isinstance(manifest,dict) or manifest.get('format') != 1 or manifest.get('version') != expected_version
                or manifest.get('agent_protocol') != 1 or type(manifest.get('schema')) is not int
                or not isinstance(manifest.get('source_schemas'), list)
                or not manifest['source_schemas'] or any(type(v) is not int for v in manifest['source_schemas'])
                or not 1<=manifest['schema']<=9999
                or any(not 1<=v<=manifest['schema'] for v in manifest['source_schemas'])
                or manifest.get('migration') != 'family_model.migrate'):
            raise Refused('UPDATE_MANIFEST_INCOMPATIBLE')
        expected = manifest.get('files', {})
        if not isinstance(expected, dict) or not expected or {prefix+n for n in expected} != set(names)-{manifest_name}:
            raise Refused('UPDATE_MANIFEST_FILE_LIST_MISMATCH')
        # All content checked before creating the extraction destination.
        for name, sha in expected.items():
            digest(sha)
            with archive.open(prefix+name) as stream:
                actual=hashlib.file_digest(stream,'sha256').hexdigest()
            if actual != sha:
                raise Refused('UPDATE_FILE_INTEGRITY_FAILED')
        destination.mkdir(mode=0o700)
        for name in expected:
            target = destination / PurePosixPath(name)
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with target.open('xb') as stream,archive.open(prefix+name) as contents:
                shutil.copyfileobj(contents,stream,65536)
            target.chmod(0o600)
    return manifest
