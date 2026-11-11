"""Package only the reviewed installer and agent; never package local policy."""
from pathlib import Path
import argparse
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[2]


def build(output):
    kit = ROOT / 'tools/agent-setup'
    names = {name: kit / name for name in ('README.md', 'activate.sh', 'activate.py')}
    names.update({path.relative_to(ROOT).as_posix(): path for path in (ROOT / 'updater_agent').glob('*.py')})
    with ZipFile(output, 'x', compression=ZIP_DEFLATED) as bundle:
        for name, path in sorted(names.items()):
            if path.is_symlink() or not path.is_file():
                raise ValueError('Unsafe agent source: ' + name)
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = (0o755 if name == 'activate.sh' else 0o644) << 16
            bundle.writestr(info, path.read_bytes())
    with ZipFile(output) as bundle:
        if bundle.testzip():
            raise RuntimeError('Corrupted agent kit')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    build(parser.parse_args().output)
