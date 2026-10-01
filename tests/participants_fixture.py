"""Temporary local UI fixture: no development database, worker or remote service."""

import atexit
import json
import os
import signal
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
temporary = tempfile.TemporaryDirectory(prefix="openfablab_participants_ui_")
atexit.register(temporary.cleanup)
os.environ["OPENFABLAB_DATABASE"] = str(Path(temporary.name) / "import.db")
os.environ["OPENFABLAB_ENABLE_SCHEDULER"] = "0"

from tests.test_app import OpenFabLabTestCase

case = OpenFabLabTestCase()
case.setUp()
atexit.register(case.tearDown)
def stop_fixture(_signal, _frame):
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop_fixture)
service_id, _ = case._animation_booking_fixture(5)
confirmed = case._animation_booking_row(service_id)
waiting = case._animation_booking_row(service_id, "waitlisted")
if os.environ.get('OPENFABLAB_SLOT_UI') == '1':
    from animation_slots import save_slots
    with case.database() as database:
        database.execute("UPDATE fablab_services SET title='Découverte casque VR',start_time='10:00',end_time='12:00',expected_participants=8 WHERE id=?", (service_id,))
        database.execute("UPDATE animation_reservation_config SET booking_mode='slots',slot_duration_minutes=20,slot_gap_minutes=10,slot_capacity=2,capacity=8 WHERE service_id=?", (service_id,))
        service=database.execute('SELECT * FROM fablab_services WHERE id=?',(service_id,)).fetchone()
        config=database.execute('SELECT * FROM animation_reservation_config WHERE service_id=?',(service_id,)).fetchone()
        slots=save_slots(database,service,config,'Europe/Paris')
        database.execute('UPDATE animation_bookings SET slot_uuid=? WHERE service_id=?',(slots[0]['slot_uuid'],service_id))
with case.database() as database:
    user = database.execute("SELECT id FROM users WHERE public_id='1001'").fetchone()
    database.execute("UPDATE users SET first_name='Anne-Lise',last_name='EXEMPLE LOCAL',"
                     "birth_year=1990,email='anne@example.invalid',phone='0600000000' WHERE id=?", (user[0],))
    database.execute("UPDATE animation_bookings SET user_id=?,public_id='1001',link_status='matched',"
                     "first_name='Anne-Lise',last_name='EXEMPLE LOCAL',"
                     "email='une.adresse.longue.pour.le.controle@example.invalid' WHERE external_uuid=?",
                     (user[0], confirmed))
    database.execute("UPDATE animation_bookings SET first_name='Elouan',last_name='EXEMPLE LOCAL' "
                     "WHERE external_uuid=?", (waiting,))

print(json.dumps({"service_id": service_id, "confirmed": confirmed, "waiting": waiting}), flush=True)
# app.run directly: unlike the normal launcher this fixture never starts a worker.
case.app.run(host="127.0.0.1", port=int(sys.argv[1]), debug=False, use_reloader=False)
