"""Isolated browser fixture; generated people/configuration only, workers off."""
import atexit
import json
import os
import signal
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
temporary=tempfile.TemporaryDirectory(prefix='openfablab-evolution-browser-')
atexit.register(temporary.cleanup)
os.environ.update(OPENFABLAB_DATABASE=str(Path(temporary.name)/'import.db'),OPENFABLAB_SECRET_KEY_FILE=str(Path(temporary.name)/'import.secret'),OPENFABLAB_ENABLE_SCHEDULER='0',OPENFABLAB_ENABLE_WEATHER='0')
from tests import test_app as fixtures
from app import write_setting
import resource_booking as resources
import welcome_mail
case=fixtures.OpenFabLabTestCase();case.setUp();atexit.register(case.tearDown)
signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
with case.database() as db:
    write_setting(db,'self_enrollment_enabled','1')
    user=db.execute('SELECT id FROM users LIMIT 1').fetchone()[0]
    db.execute("UPDATE users SET first_name='Camille',last_name='EXEMPLE',email='camille@example.invalid',phone='0600000000'")
    db.execute("INSERT INTO authorizations VALUES('training-example','Initiation machine Exemple','Exemple fictif',1,'2026-01-01')")
    resources.grant(db,user,'training-example','2099-10-08','Équipe Exemple','admin')
    for name in ('Laser Exemple','Imprimante Exemple'):
        key=resources.save_resource(db,dict(name=name,type_key='machine',active=True,price_cents=0),'admin')
        resources.book(db,key,user,'2099-10-08T10:00:00+02:00','2099-10-08T11:00:00+02:00','admin')
welcome_mail.save_config(case.database_path,dict(host='smtp.example.invalid',port=587,security='starttls',sender_email='atelier@example.invalid'))
print(json.dumps({'ready':True}),flush=True)
case.app.run(host='127.0.0.1',port=int(sys.argv[1]),debug=False,use_reloader=False)
