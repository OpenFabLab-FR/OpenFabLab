"""V2.6 slot regression: temporary databases, mock transport, no real services."""
import io
import json
import re
import sqlite3
import threading
import unittest
import zlib
import base64
import tempfile
import subprocess
import sys
import os
import hashlib
from pathlib import Path
from zipfile import ZipFile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest import mock

from tests import test_app as fixture
from animation_slots import generate_slots, save_slots, slots_summary
from reservations_sync import enqueue_animation, import_events, _sync_environment


class AnimationSlotTests(unittest.TestCase):
    setUp = fixture.OpenFabLabTestCase.setUp
    tearDown = fixture.OpenFabLabTestCase.tearDown
    database = fixture.OpenFabLabTestCase.database
    login_admin = fixture.OpenFabLabTestCase.login_admin
    _login_token = fixture.OpenFabLabTestCase._login_token
    _animation_booking_fixture = fixture.OpenFabLabTestCase._animation_booking_fixture
    _animation_booking_row = fixture.OpenFabLabTestCase._animation_booking_row

    def create(self, **changes):
        with self.client.session_transaction() as session:
            authenticated = session.get('access_role') == 'admin'
        if not authenticated:
            self.login_admin()
        with self.database() as db:
            db.execute("INSERT INTO app_settings(key,value) VALUES('module_public_reservations','1') ON CONFLICT(key) DO UPDATE SET value='1'")
        form = self.client.get('/admin/animations/nouveau').get_data(as_text=True)
        with self.client.session_transaction() as session:
            token = session.setdefault('pin_csrf','fictional-slot-csrf')
        values = dict(csrf_token=token, title='Découverte casque VR', service_date='2027-10-08',
                      start_time='10:00', end_time='12:00', expected_participants='4', actual_participants='',
                      minimum_age='6', online_enabled='1', online_environment='test', booking_mode='slots',
                      slot_duration_minutes='20', slot_gap_minutes='10', slot_capacity='1', capacity='4',
                      accompaniment_under_age='15', waitlist_enabled='1', close_minutes='0')
        values.update(changes)
        response = self.client.post('/admin/animations/nouveau', data=values)
        with self.database() as db:
            row = db.execute('SELECT id FROM fablab_services ORDER BY id DESC LIMIT 1').fetchone()
        return (row[0] if row else None), token, values, response

    def slots(self, service):
        with self.database() as db:
            return slots_summary(db, service)

    def add(self, service, slot, status='confirmed', presence=None, group=None):
        booking = self._animation_booking_row(service, status, group, presence)
        with self.database() as db:
            db.execute('UPDATE animation_bookings SET slot_uuid=? WHERE external_uuid=?', (slot, booking))
        return booking

    def test_four_slots_gap_and_capacity_derived_server_side(self):
        service, _, _, result = self.create(capacity='999', expected_participants='999')
        self.assertEqual(result.status_code, 302)
        self.assertEqual([s['label'] for s in self.slots(service)], ['10:00–10:20','10:30–10:50','11:00–11:20','11:30–11:50'])
        with self.database() as db:
            self.assertEqual(db.execute('SELECT capacity FROM animation_reservation_config WHERE service_id=?',(service,)).fetchone()[0], 4)
            self.assertEqual(db.execute('SELECT expected_participants FROM fablab_services WHERE id=?',(service,)).fetchone()[0], 4)

    def test_six_slots_without_gap_and_two_seats(self):
        service, _, _, result = self.create(slot_gap_minutes='0',slot_capacity='2')
        self.assertEqual(result.status_code, 302)
        self.assertEqual(len(self.slots(service)), 6)
        self.assertEqual(sum(s['capacity'] for s in self.slots(service)), 12)

    def test_invalid_configurations(self):
        for changes in ({'slot_duration_minutes':'0'},{'slot_gap_minutes':'-1'},{'slot_capacity':'0'},
                        {'end_time':'09:00'},{'slot_duration_minutes':'121'}, {'booking_mode':'invalid'}):
            with self.subTest(changes=changes):
                self.assertEqual(self.create(**changes)[3].status_code, 400)

    def test_stable_ids_and_environment_isolation(self):
        service, _, values, _ = self.create()
        config=dict(booking_mode='slots',slot_duration_minutes=20,slot_gap_minutes=10,slot_capacity=1,environment='test')
        first=generate_slots(values,config,service_id=service)
        increased=generate_slots(values,dict(config,slot_capacity=2),service_id=service)
        normal=generate_slots(values,dict(config,environment='production'),service_id=service)
        self.assertEqual(first[0]['slot_uuid'],increased[0]['slot_uuid'])
        self.assertNotEqual(first[0]['slot_uuid'],normal[0]['slot_uuid'])

    def test_dst_ambiguity_rejected(self):
        config=dict(booking_mode='slots',slot_duration_minutes=20,slot_gap_minutes=0,slot_capacity=1,environment='test')
        for date in ('2026-03-29','2026-10-25'):
            with self.assertRaises(ValueError):
                generate_slots(dict(service_date=date,start_time='02:00',end_time='04:00'),config)

    def test_classic_default_and_null_booking(self):
        service, _ = self._animation_booking_fixture(4)
        booking = self._animation_booking_row(service)
        with self.database() as db:
            self.assertEqual(db.execute('SELECT booking_mode FROM animation_reservation_config').fetchone()[0],'whole')
            self.assertIsNone(db.execute('SELECT slot_uuid FROM animation_bookings WHERE external_uuid=?',(booking,)).fetchone()[0])
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],14)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_activity_counts_seats_waiting_presence_and_plural(self):
        service,_=self._animation_booking_fixture(4)
        with self.database() as db:
            db.execute('UPDATE fablab_services SET expected_participants=4,actual_participants=2 WHERE id=?',(service,))
        for status,presence in [('confirmed',1),('confirmed',1),('offer_pending',None),('waitlisted',None),('cancelled',None),('expired',None)]:
            self._animation_booking_row(service,status,presence=presence)
        page=self.client.get('/admin/animations').get_data(as_text=True)
        self.assertIn('4 places / 3 inscrits / 2 présents',page)
        self.assertIn('1 en attente',page);self.assertNotIn('0 en attente',page)
        with self.database() as db:
            db.execute("DELETE FROM animation_bookings WHERE status!='confirmed'")
            db.execute('DELETE FROM animation_bookings WHERE rowid NOT IN (SELECT MIN(rowid) FROM animation_bookings)')
            db.execute('UPDATE fablab_services SET expected_participants=1,actual_participants=1 WHERE id=?',(service,))
        self.assertIn('1 place / 1 inscrit / 1 présent',self.client.get('/admin/animations').get_data(as_text=True))

    def test_slots_summary_and_counts_pair_and_group_order(self):
        service,_,_,_=self.create(slot_capacity='2')
        slots=self.slots(service)
        self.add(service,slots[0]['slot_uuid'],presence=1,group='pair')
        self.add(service,slots[0]['slot_uuid'],group='pair')
        self.add(service,slots[0]['slot_uuid'],'waitlisted')
        self.add(service,slots[1]['slot_uuid'])
        summary=self.slots(service)
        self.assertEqual((summary[0]['occupied'],summary[0]['waiting'],summary[1]['occupied'],summary[2]['occupied']),(2,1,1,0))
        page=self.client.get(f'/admin/animations/{service}/inscriptions').get_data(as_text=True)
        self.assertIn('2/2 réservés',page);self.assertIn('Créneau : 10:00–10:20',page)
        self.assertIn('4 créneaux / 3 inscrits / 0 présent',self.client.get('/admin/animations').get_data(as_text=True))

    def test_modify_regenerates_before_booking(self):
        service,_,values,_=self.create()
        result=self.client.post(f'/admin/animations/{service}/modifier',data=dict(values,slot_gap_minutes='0'))
        self.assertEqual(result.status_code,302);self.assertEqual(len(self.slots(service)),6)

    def test_bookings_protect_geometry_mode_and_reduction(self):
        service,_,values,_=self.create(slot_capacity='2')
        slot=self.slots(service)[0]['slot_uuid'];booking=self.add(service,slot)
        for changes in ({'start_time':'10:10'},{'end_time':'12:10'},{'slot_duration_minutes':'30'},
                        {'slot_gap_minutes':'0'},{'booking_mode':'whole'},{'slot_capacity':'1'},{'online_environment':'production'}):
            self.assertEqual(self.client.post(f'/admin/animations/{service}/modifier',data=dict(values,**changes)).status_code,400)
        self.assertEqual(self.client.post(f'/admin/animations/{service}/modifier',data=dict(values,slot_capacity='3')).status_code,302)
        with self.database() as db:
            self.assertEqual(db.execute('SELECT slot_uuid FROM animation_bookings WHERE external_uuid=?',(booking,)).fetchone()[0],slot)

    def test_disabled_module_still_protects_existing_times(self):
        service,_,values,_=self.create();self.add(service,self.slots(service)[0]['slot_uuid'])
        with self.database() as db:db.execute("UPDATE app_settings SET value='0' WHERE key='module_public_reservations'")
        self.assertEqual(self.client.post(f'/admin/animations/{service}/modifier',data=dict(values,start_time='10:15')).status_code,400)

    def test_walkin_only_target_slot_capacity_and_permissions(self):
        service,token,_,_=self.create();slots=self.slots(service)
        base=dict(csrf_token=token,first_name='Fictif',last_name='LOCAL',birth_year='1990')
        route=f'/admin/animations/{service}/inscriptions/sur-place'
        for slot in (slots[0]['slot_uuid'],slots[0]['slot_uuid'],slots[1]['slot_uuid']):
            self.client.post(route,data=dict(base,slot_uuid=slot))
        self.assertEqual([s['occupied'] for s in self.slots(service)],[1,1,0,0])
        self.client.post(route,data=base)
        self.assertEqual(sum(s['occupied'] for s in self.slots(service)),2)
        self.client.post('/admin/deconnexion');self.login_admin('8642')
        page=self.client.get(f'/admin/animations/{service}/inscriptions').get_data(as_text=True)
        self.assertNotIn('>Modifier</a>',page)

    def test_concurrent_walkins_no_overbooking(self):
        service,token,_,_=self.create(slot_capacity='2');slot=self.slots(service)[0]['slot_uuid']
        barrier=threading.Barrier(3)
        def add(n):
            client=self.app.test_client()
            with self.client.session_transaction() as source:session=dict(source)
            with client.session_transaction() as target:target.update(session)
            barrier.wait()
            return client.post(f'/admin/animations/{service}/inscriptions/sur-place',data=dict(csrf_token=token,
                first_name=f'Fictif{n}',last_name='LOCAL',birth_year='1990',slot_uuid=slot)).status_code
        with ThreadPoolExecutor(max_workers=3) as pool:self.assertEqual(list(pool.map(add,range(3))),[302]*3)
        self.assertEqual(self.slots(service)[0]['occupied'],2)

    def test_confirmation_and_cancellation_target_slot(self):
        service,token,_,_=self.create();slots=self.slots(service)
        self.add(service,slots[0]['slot_uuid'])
        waiting=self.add(service,slots[0]['slot_uuid'],'waitlisted')
        other=self.add(service,slots[1]['slot_uuid'],'waitlisted')
        route=lambda uuid:f'/admin/animations/{service}/inscriptions/{uuid}/action'
        self.client.post(route(waiting),data=dict(csrf_token=token,action='confirm'))
        self.client.post(route(other),data=dict(csrf_token=token,action='confirm'))
        with self.database() as db:self.assertEqual(db.execute('SELECT status FROM animation_bookings WHERE external_uuid=?',(waiting,)).fetchone()[0],'waitlisted')
        self.assertEqual(self.slots(service)[1]['occupied'],1)
        self.client.post(route(other),data=dict(csrf_token=token,action='cancel'))
        self.assertEqual([s['occupied'] for s in self.slots(service)],[1,0,0,0])

    def test_payload_and_import_stable_slot_and_replay(self):
        service,_,_,_=self.create();slot=self.slots(service)[0]['slot_uuid']
        with self.database() as db:
            payload=json.loads(db.execute('SELECT payload_json FROM reservation_outbox ORDER BY id DESC LIMIT 1').fetchone()[0])
            self.assertEqual(len(payload['animation']['slots']),4)
            event={'id':1,'type':'reservation_confirmed','booking':dict(uuid='fixture-uuid',service_id=service,
                environment='test',slot_uuid=slot,first_name='Anne',last_name='FICTIF',birth_year=1990,status='confirmed',
                link_status='visitor',created_at='2026-10-01',updated_at='2026-10-01')}
            self.assertEqual(import_events(db,'test',[event]),1);self.assertEqual(import_events(db,'test',[event]),0)
            bad=dict(event,id=2,booking=dict(event['booking'],slot_uuid=None))
            with self.assertRaises(ValueError):import_events(db,'test',[bad])
            moved=dict(event,id=3,booking=dict(event['booking'],slot_uuid=self.slots(service)[1]['slot_uuid']))
            with self.assertRaises(ValueError):import_events(db,'test',[moved])

    def test_capability_handshake_blocks_old_plugin_before_publish(self):
        service,_,_,_=self.create()
        class Client:
            def __init__(self,supported):self.supported=supported;self.routes=[]
            def post(self,route,payload):
                self.routes.append(route)
                if route=='/sync/capabilities':return {'ok':True,'animation_slots_v1':self.supported}
                return {'ok':True,'events':[],'cursor':0}
        with self.database() as db:
            old=Client(False)
            with self.assertRaises(ValueError):_sync_environment(db,old,'test',[],datetime.now(timezone.utc),[],[])
            self.assertNotIn('/sync/animations',old.routes)
            new=Client(True);_sync_environment(db,new,'test',[],datetime.now(timezone.utc),[],[])
            self.assertIn('/sync/animations',new.routes)

    def test_exports_and_single_global_calendar(self):
        service,_,_,_=self.create();self.add(service,self.slots(service)[1]['slot_uuid'])
        csv=self.client.get(f'/admin/animations/{service}/inscriptions.csv').get_data(as_text=True)
        self.assertIn('Créneau',csv);self.assertIn('10:30–10:50',csv)
        pdf=self.client.get(f'/admin/animations/{service}/inscriptions.pdf')
        self.assertEqual(pdf.status_code,200);self.assertTrue(pdf.data.startswith(b'%PDF'))
        streams=pdf_streams(pdf.data)
        self.assertIn(b'Cr\\351neau',b''.join(streams));self.assertIn(b'10:30',b''.join(streams));self.assertIn(b'10:50',b''.join(streams))
        ics=self.client.get(f'/admin/animations/{service}/calendrier.ics').get_data(as_text=True)
        self.assertEqual(ics.count('BEGIN:VEVENT'),1);self.assertIn('T100000',ics);self.assertIn('T120000',ics)

    def test_multpage_pdf_repeats_slot_heading(self):
        service,_,_,_=self.create();slot=self.slots(service)[0]['slot_uuid']
        for _ in range(45):self.add(service,slot,'waitlisted')
        pdf=self.client.get(f'/admin/animations/{service}/inscriptions.pdf')
        pages=re.findall(rb'/Type /Page\b',pdf.data)
        self.assertGreater(len(pages),1)
        self.assertEqual(sum(stream.count(b'Cr\\351neau') for stream in pdf_streams(pdf.data)),len(pages))

    def test_migration_12_to_13_on_fictional_copy_preserves_all_business_rows(self):
        root=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='openfablab-schema13-copy-') as directory:
            from tests.schema12_fixture import create_schema12
            base=Path(directory)
            source=base/'source.db';target=base/'copy.db'
            create_schema12(source)
            digest=hashlib.sha256(source.read_bytes()).digest()
            with sqlite3.connect(source) as old,sqlite3.connect(target) as new:
                self.assertEqual(old.execute('PRAGMA user_version').fetchone()[0],12)
                old.backup(new)
                tables=[r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('app_settings','sqlite_sequence')")]
                before={table:old.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall() for table in tables}
            fixture.create_app(dict(TESTING=True,SEED_DEMO_USERS=False,DATABASE=str(target),ADMIN_PIN=None,MODERATOR_PIN=None,WEATHER_ENABLED=False,SECRET_KEY='fictional-test'))
            with sqlite3.connect(target) as migrated:
                self.assertEqual(migrated.execute('PRAGMA user_version').fetchone()[0],14)
                self.assertEqual(migrated.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(migrated.execute('PRAGMA foreign_key_check').fetchall(),[])
                for table,rows in before.items():
                    after=migrated.execute('SELECT * FROM '+table+' ORDER BY rowid').fetchall()
                    self.assertEqual([r[:len(rows[0])] for r in after] if rows else after,rows,table)
                self.assertEqual(migrated.execute('SELECT booking_mode FROM animation_reservation_config').fetchone()[0],'whole')
                self.assertEqual(migrated.execute('SELECT COUNT(*) FROM animation_slots').fetchone()[0],0)
                self.assertEqual(migrated.execute('SELECT COUNT(*) FROM animation_bookings WHERE slot_uuid IS NOT NULL').fetchone()[0],0)
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(),digest)


def pdf_streams(data):
    result=[]
    for match in re.finditer(rb'stream\r?\n(.*?)endstream',data,re.S):
        header=data[data.rfind(b'<<',0,match.start()):match.start()]
        if b'/FlateDecode' not in header:continue
        encoded=match.group(1).strip()
        if b'/ASCII85Decode' in header:encoded=base64.a85decode(encoded[:-2])
        result.append(zlib.decompress(encoded))
    return result

if __name__=='__main__':unittest.main()
