"""Read-only release audit; no application import, database or private-file access."""
import hashlib
import argparse
import re
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_openfablab as application
import build_wordpress_plugin as plugin

SENSITIVE = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    rb"|https://(?:discord(?:app)?\.com)/api/webhooks/"
    rb"|\bAKIA[A-Z0-9]{16}\b"
    rb"|(?i:fictional-only-slot-fixture|fixture\d+@example\.invalid)"
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(path, expected):
    with ZipFile(path) as archive:
        assert archive.testzip() is None, "CRC"
        assert archive.namelist() == expected, "Allowlist"
        for info in archive.infolist():
            name = info.filename.lower()
            assert not name.startswith("/") and ".." not in Path(name).parts
            assert not application.is_macos_metadata(info.filename), "macOS metadata"
            assert not name.endswith((".db", ".sqlite", ".sqlite3", ".sql", ".openfablab-profile.zip"))
            assert not any(part in {".env", "data", "saves", "__pycache__", ".venv", "tests", "branding"} for part in Path(name).parts)
            assert not any(word in name for word in ("screenshot", "capture", "secret_key", "signature.png", "phase2_"))
            assert not SENSITIVE.search(archive.read(info)), "Sensitive literal or fixture"
            if path == plugin.OUTPUT:
                assert not re.search(rb"fougereslab|fougeres-agglo", archive.read(info), re.I), "Structure-specific data in generic plugin"
    print(path.name + ": allowlist/CRC/private-files/literal scan OK (" + str(len(expected)) + " files)")
    print("SHA256=" + digest(path))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-plugin',action='store_true')
    options=parser.parse_args()
    check(application.OUTPUT, [p.relative_to(ROOT).as_posix() for p in application.included_paths()])
    check(plugin.OUTPUT, ["openfablab-reservations/" + name for name in plugin.INCLUDED])
    with tempfile.TemporaryDirectory(prefix='openfablab-release-audit-') as directory:
        repeat_application=application.build(Path(directory)/'application.zip')
        repeat_plugin=plugin.OUTPUT if options.reuse_plugin else plugin.build(Path(directory)/'plugin.zip')
        assert digest(repeat_application)==digest(application.OUTPUT), 'Application reproducibility'
        assert digest(repeat_plugin)==digest(plugin.OUTPUT), 'Plugin reproducibility'
        if options.reuse_plugin:
            with ZipFile(plugin.OUTPUT) as archive:
                for name in plugin.INCLUDED:
                    assert archive.read('openfablab-reservations/'+name)==(plugin.ROOT/'wordpress/openfablab-reservations'/name).read_bytes(),name
        for distribution in (application.OUTPUT,plugin.OUTPUT):
            with ZipFile(distribution) as archive:
                assert any(name.endswith('/LICENSE') or name=='LICENSE' for name in archive.namelist())
                assert any(name.endswith('THIRD_PARTY_NOTICES.md') for name in archive.namelist())
        with ZipFile(application.OUTPUT) as archive:
            for name in archive.namelist():
                assert archive.read(name)==(ROOT/name).read_bytes(),name
    (ROOT/'dist/SHA256SUMS').write_text(''.join(digest(path)+'  '+path.name+'\n' for path in (application.OUTPUT,plugin.OUTPUT)))
    print('APPLICATION_REPRODUCIBLE=YES PLUGIN='+('REUSED_SOURCES_MATCH' if options.reuse_plugin else 'REPRODUCIBLE')+' PUBLIC_SOURCES_MATCH=YES LICENSES=YES')


if __name__ == "__main__":
    main()
