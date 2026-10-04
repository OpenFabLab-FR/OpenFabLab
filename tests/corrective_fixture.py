"""Isolated, fictional visual fixture. Optional source root for before/after QA."""
import atexit
import os
import signal
import sys
import tempfile
from pathlib import Path
root = Path(sys.argv[2]).resolve() if len(sys.argv)>2 else Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
temporary=tempfile.TemporaryDirectory(prefix='openfablab-corrective-browser-')
atexit.register(temporary.cleanup)
os.environ.update(OPENFABLAB_DATABASE=str(Path(temporary.name)/'import.db'),
    OPENFABLAB_SECRET_KEY_FILE=str(Path(temporary.name)/'import.secret'),
    OPENFABLAB_ENABLE_SCHEDULER='0',OPENFABLAB_ENABLE_WEATHER='0',OPENFABLAB_EXTERNAL_ACTIONS='0')
from tests import test_app as fixtures
from app import write_setting
import resource_booking as resources
import evolution_schema as schema
case=fixtures.OpenFabLabTestCase();case.setUp();atexit.register(case.tearDown)
case.app.config.update(EXTERNAL_ACTIONS=False,AUTO_CLOSURE_WORKER=False,WEATHER_ENABLED=False)
signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
with case.database() as db:
    users=db.execute('SELECT id FROM users ORDER BY id').fetchall()
    for index,row in enumerate(users):
        db.execute("UPDATE users SET first_name=?,last_name='EXEMPLE',email='',phone='',created_source='' WHERE id=?",
            (['Camille','Anne-Lise','Éloïse','Elouan','Alex'][index%5],row['id']))
    schema.save_category(db,'Personnel','#147a39',key='staff')
    schema.save_category(db,'Stagiaire','#345678',False,key='intern')
    db.execute("UPDATE users SET category='staff' WHERE id=?", (users[0]['id'],))
    resources.save_type(db,'Espaces fictifs','#a55b72',key='example-space')
    db.execute("INSERT INTO authorizations VALUES('training-example','Broderie débutant','Initiation fictive : sécurité et réglages.',1,'2026-01-01')")
    db.execute("INSERT INTO authorizations VALUES('training-second','Broderie intermédiaire','Exemple fictif avancé.',1,'2026-01-02')")
    resources.grant(db,users[0]['id'],'training-example','2026-10-03','Équipe Exemple','admin')
    resources.grant(db,users[1]['id'],'training-second','2026-10-03','Équipe Exemple','moderator','2026-11-01')
    for name in ('Laser Exemple','Imprimante Exemple','Brodeuse Exemple'):
        key=resources.save_resource(db,dict(name=name,type_key='machine',active=True,
            price_cents=550 if name.startswith('Laser') else 0,approval_required=False),'admin')
        resources.book(db,key,users[0]['id'],'2026-10-03T10:00:00+02:00','2026-10-03T11:00:00+02:00','admin')
    db.execute("INSERT INTO sessions(user_id,check_in,check_out,statistical_category,statistical_user_key) VALUES(?,'2026-10-03T08:00:00+00:00','2026-10-03T10:00:00+00:00','staff','fictitious-statistical-key')",(users[0]['id'],))
    write_setting(db,'discord_new_user_enabled','1')
    for key in ('first_name','last_initial','category'):write_setting(db,'discord_new_user_'+key,'1')
    write_setting(db,'module_public_reservations','1')
    write_setting(db,'tablet_reservations_enabled','1')
    write_setting(db,'reservation_wordpress_url','https://example.invalid')
    for day,title in [('2026-10-03','Animation Exemple'),('2099-01-01','Atelier Démonstration')]:
        now='2026-10-03T09:00:00+00:00'
        key=db.execute("INSERT INTO fablab_services(service_type,title,description,service_date,start_time,end_time,minimum_age,expected_participants,created_at,updated_at) VALUES('animation',?,'Données fictives : atelier découverte, sécurité et pratique.',?,'14:00','16:00',8,3,?,?)",(title,day,now,now)).lastrowid
        db.execute("INSERT INTO animation_reservation_config(service_id,enabled,environment,capacity,updated_at) VALUES(?,1,'production',3,?)",(key,now))
        if day=='2026-10-03':
            for index,status in enumerate(['confirmed','waitlisted']):
                db.execute("INSERT INTO animation_bookings(external_uuid,environment,service_id,status,first_name,last_name,email,phone,user_id,link_status,created_at,updated_at) VALUES(?,'production',?,?,?,'EXEMPLE','demo@example.invalid','+330600000000',?,'matched',?,?)",('demo-booking-'+str(index),key,status,['Camille','Anne-Lise'][index],users[index]['id'],now,now))
from reservations_sync import save_sync_secret
save_sync_secret(case.database_path,'fictional-browser-secret-'+'x'*48)
case.app.run(host='127.0.0.1',port=int(sys.argv[1]),debug=False,use_reloader=False)
