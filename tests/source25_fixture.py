"""Fictional SQLite25 fixture, optionally created by an approved old runtime.

OPENFABLAB_TEST_SOURCE_2144 may select an extracted, trusted 2.14.4 source tree.
Without it the fixture is explicitly synthetic, not a claimed old-runtime test.
No production database, profile, credential or outbound service is ever used.
"""
import json,os,shutil,sqlite3,sys
from pathlib import Path
destination=Path(sys.argv[1]).resolve();destination.mkdir(mode=0o700)
reference=os.environ.get('OPENFABLAB_TEST_SOURCE_2144')
source=Path(reference).resolve() if reference else Path(__file__).resolve().parents[1]
os.environ.update(OPENFABLAB_DATABASE=str(destination/'import.db'),OPENFABLAB_SECRET_KEY_FILE=str(destination/'import.secret'),
    OPENFABLAB_EXTERNAL_ACTIONS='0',OPENFABLAB_ENABLE_SCHEDULER='0',OPENFABLAB_ENABLE_WEATHER='0')
def deny(event,args):
    if event in ('socket.connect','socket.sendto','socket.getaddrinfo'):raise OSError('FICTIONAL_FIXTURE_NETWORK_DENIED')
sys.addaudithook(deny);sys.path.insert(0,str(source));sys.path.insert(0,str(source/'tests'))
from openfablab import __version__
if reference and __version__!='2.14.4':raise SystemExit('APPROVED_REFERENCE_VERSION_MISMATCH')
from tests.test_v214_core import NewVersion
import machine_maintenance as machines
f=NewVersion();f.setUp()
try:
    f.f.book([f.f.a,f.f.c])
    machines.intervention(f.db,f.key,dict(performed_on='2020-01-01',description='Entretien fictif',kind='care'),'admin','admin')
    machines.reminder(f.db,f.key,dict(due_on='2099-01-01',subject='Rappel fictif'),'admin','admin');f.db.commit()
    if not reference:
        for table in ('resource_document_links','resource_documents','user_booking_restrictions'):f.db.execute('DROP TABLE '+table)
        for table,columns in {'resources':['availability_mode'],'resource_bookings':['handed_over_at','returned_at'],'billing_records':['handed_over_at','returned_at','rental_user_id']}.items():
            for column in columns:f.db.execute('ALTER TABLE '+table+' DROP COLUMN '+column)
        f.db.execute("DELETE FROM app_settings WHERE key IN('resource_public_base_url','resource_public_pages_enabled','setup_completed','setup_progress')")
        f.db.execute('PRAGMA user_version=25');f.db.commit()
    if f.db.execute('PRAGMA user_version').fetchone()[0]!=25:raise SystemExit('FICTIONAL_SOURCE25_REQUIRED')
    data=destination/'data';data.mkdir(mode=0o700);name=Path(f.path).name
    for path in Path(f.path).parent.iterdir():
        if path.name in (name,*(name+s for s in ('-wal','-shm','-journal'))):continue
        if path.is_dir():shutil.copytree(path,data/path.name)
        elif path.is_file():shutil.copy2(path,data/path.name)
    with sqlite3.connect(data/'openfablab.db') as target:f.db.backup(target)
    (destination/'fixture-origin.json').write_text(json.dumps(dict(mode='approved_runtime_2.14.4' if reference else 'synthetic_schema25',fictional=True)))
    print('FICTIONAL_SOURCE25_READY')
finally:f.doCleanups()
