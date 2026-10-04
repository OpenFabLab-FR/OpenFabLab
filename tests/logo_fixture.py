"""Header regression fixture: fictional identity, local-only, external actions off."""
import atexit
import os
import signal
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
runtime = tempfile.TemporaryDirectory(prefix='openfablab-header-test-')
atexit.register(runtime.cleanup)
os.environ.update(OPENFABLAB_DATABASE=str(Path(runtime.name)/'import.db'),
    OPENFABLAB_SECRET_KEY_FILE=str(Path(runtime.name)/'import.secret'),
    OPENFABLAB_ENABLE_SCHEDULER='0', OPENFABLAB_ENABLE_WEATHER='0',
    OPENFABLAB_EXTERNAL_ACTIONS='0')
from tests import test_app as fixtures
from app import write_setting

case = fixtures.OpenFabLabTestCase()
case.setUp()
atexit.register(case.tearDown)
atexit.register(case.doCleanups)
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
case.app.config.update(EXTERNAL_ACTIONS=False, AUTO_CLOSURE_WORKER=False, WEATHER_ENABLED=False)
branding = Path(case.database_path).parent/'branding'
with case.database() as db:
    for kind in ('wordmark', 'header_institution', 'network'):
        # Simple geometric placeholders, never private logos.
        (branding/(kind+'.png')).write_bytes((branding/'main.png').read_bytes())
        write_setting(db, 'structure_'+kind+'_logo',
            '' if kind=='wordmark' and sys.argv[2]=='default' else kind+'.png')
        write_setting(db, 'structure_show_'+kind+'_logo', '1')
    now = datetime.now(timezone.utc).isoformat()
    users = db.execute('SELECT id,category FROM users ORDER BY id').fetchall()
    for index, user in enumerate(users):
        db.execute("UPDATE users SET first_name=?,last_name='EXEMPLE',email='',phone='' WHERE id=?",
            (['Camille', 'Anne-Lise', 'Elouan', 'Noa', 'Alex'][index%5], user['id']))
        db.execute('INSERT INTO sessions(user_id,check_in,entry_method,statistical_category) VALUES(?,?,?,?)',
            (user['id'], now, 'manual', user['category']))
    db.executemany('INSERT INTO visitors(created_at) VALUES(?)', [(now,)]*7)
    write_setting(db, 'home_theme', 'classic')
    write_setting(db, 'lock_home_scroll', '1')
    for key in ('module_discord', 'module_weather', 'smtp_enabled', 'module_public_reservations'):
        write_setting(db, key, '0')
case.app.run(host='127.0.0.1', port=int(sys.argv[1]), debug=False, use_reloader=False)
