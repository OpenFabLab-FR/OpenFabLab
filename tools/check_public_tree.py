"""Validate the exact first-publication manifest, resource licenses and exclusions.

This is a deterministic guard, not a substitute for a human privacy review.
Development environments and generated release ZIPs are deliberately outside Git.
"""
import hashlib
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
GENERATED={'.git','.venv','node_modules','dist','__pycache__'}
FORBIDDEN_SUFFIXES=('.db','.sqlite','.sqlite3','.sql','.zip','.pyc','.pdf','.docx','.xlsx','.csv')
SENSITIVE=re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}|\bAKIA[A-Z0-9]{16}\b')
PRIVATE_INFRA=re.compile(rb'/Users/[A-Za-z][A-Za-z0-9_.-]*/|/volume[0-9]+/(?:docker|Coffre)|\b192\.168\.\d{1,3}\.\d{1,3}\b|\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',re.I)


def check():
    names=(ROOT/'PUBLIC_FILES.txt').read_text().splitlines()
    if names!=sorted(set(names)):
        raise ValueError('Public manifest must be sorted and unique')
    actual=[]
    for path in ROOT.rglob('*'):
        relative=path.relative_to(ROOT)
        if any(part in GENERATED for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError('Symlink not permitted: '+relative.as_posix())
        if path.is_file():
            actual.append(relative.as_posix())
    if sorted(actual)!=names:
        raise ValueError('Public manifest does not match the source tree')
    for name in names:
        path=ROOT/name
        if name.endswith(FORBIDDEN_SUFFIXES):
            raise ValueError('Generated or private file in manifest: '+name)
        if any(part.startswith('.') and part not in {'.env.example','.gitignore','.dockerignore'} for part in Path(name).parts):
            raise ValueError('Unexpected hidden file: '+name)
        data=path.read_bytes()
        if SENSITIVE.search(data) or PRIVATE_INFRA.search(data):
            raise ValueError('Private literal detected in '+name+' (value withheld)')
        if data.startswith(b'SQLite format 3'):
            raise ValueError('SQLite content detected in '+name)
    fonts=ROOT/'static/fonts'
    for name,expected in [('LibreFranklin-Regular.ttf','01e26222a56e141e3abae670ab22be77f063999fc4ef64c4a9651de19b7728a8'),
                          ('LibreFranklin-Bold.ttf','3134a143a2a801a0e80198ea03cd7cc99066bcaeeaaecda758e852725c225303')]:
        if hashlib.sha256((fonts/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Upstream font changed without license review')
    print('PUBLIC_MANIFEST=OK FILES='+str(len(names)))
    print('PRIVATE_LITERALS=NONE LICENSED_FONTS=OK')
    return names


if __name__=='__main__':
    check()
