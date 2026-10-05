"""Fictional users only; shared engine, privacy and additive migration checks."""
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock
from tests import test_app as fixtures
from app import write_setting
import family_model as family
import family_reservations as engine
from reservations_sync import save_sync_secret, _sync_environment


class FamilyTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.OpenFabLabTestCase();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.client=self.f.client
        self.today=date.today();self.day=(self.today+timedelta(days=20)).isoformat()
        self.db=self.f.database();self.addCleanup(self.db.close)
        self.initial_users=self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        self.people=[]
        for index,years in enumerate((40,38,10,12,15,17,35)):
            born=date(self.today.year-years,1,1).isoformat()
            key=self.db.execute("INSERT INTO users(public_id,first_name,last_name,active,category,birth_year,birth_date,birth_precision,email,phone,created_at) VALUES(?,?,?,1,'user',?,?,'exact',?,?,?)",
                (str(2001+index),'Fictif'+str(index),'EXEMPLE',int(born[:4]),born,'person'+str(index)+'@example.invalid','06000000'+str(index).zfill(2),family.timestamp())).lastrowid
            self.people.append(key)
        self.a,self.b,self.c,self.d,self.teen,self.older,self.other=self.people
        for child in (self.c,self.d):
            family.link(self.db,child,self.a);family.link(self.db,child,self.b)
        self.service=self.db.execute("INSERT INTO fablab_services(service_type,title,description,service_date,start_time,end_time,minimum_age,expected_participants,created_at,updated_at) VALUES('animation','Atelier fictif','Description fictive',?,'10:00','12:00',0,4,?,?)",(self.day,family.timestamp(),family.timestamp())).lastrowid
        self.db.execute("INSERT INTO animation_reservation_config(service_id,enabled,environment,capacity,waitlist_enabled,updated_at) VALUES(?,1,'production',4,1,?)",(self.service,family.timestamp()))
        for key,value in [('tablet_reservations_enabled','1'),('module_public_reservations','1')]:
            write_setting(self.db,key,value)
        self.db.commit()

    def book(self,ids,owner=None,key=None,staff=False,slot=None):
        return engine.reserve(self.db,owner or self.a,ids,self.service,slot,key or secrets.token_urlsafe(32),source='administration' if staff else 'kiosk',staff=staff)

    def test_real_people_one_seat_each(self):
        for ids in ([self.a],[self.a,self.c],[self.a,self.c,self.d],[self.a,self.b,self.c,self.d],[self.teen],[self.older]):
            with self.subTest(ids=ids):
                value=self.book(ids,owner=ids[0])
                self.assertEqual((value['status'],value['count']),('confirmed',len(ids)))
                rows=self.db.execute('SELECT * FROM animation_bookings').fetchall()
                self.assertEqual(len(rows),len(ids));self.assertEqual({r['user_id'] for r in rows},set(ids))
                self.assertTrue(all(r['email'] is None and r['phone'] is None for r in rows))
                self.db.execute('DELETE FROM family_booking_requests');self.db.execute('DELETE FROM animation_bookings');self.db.commit()

    def test_missing_or_unrelated_responsible_refused(self):
        for ids in ([self.c],[self.other,self.c]):
            with self.subTest(ids=ids),self.assertRaisesRegex(ValueError,'responsable'):
                self.book(ids,staff=True)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],0)

    def test_inactive_or_incomplete_responsible_refused(self):
        for field,value in [('active',0),('email',None)]:
            with self.subTest(field=field):
                self.db.execute('UPDATE users SET '+field+'=? WHERE id=?',(value,self.a));self.db.commit()
                with self.assertRaises(ValueError):self.book([self.a,self.c],staff=True)
                self.db.execute("UPDATE users SET active=1,email='person0@example.invalid' WHERE id=?",(self.a,));self.db.commit()

    def test_same_responsible_is_not_duplicated(self):
        value=self.book([self.a,self.a,self.c,self.d]);self.assertEqual(value['count'],3)

    def test_whole_group_waitlisted_when_only_two_places_remain(self):
        self.book([self.teen],owner=self.teen);self.book([self.older],owner=self.older)
        value=self.book([self.a,self.c,self.d]);self.assertEqual((value['status'],value['count']),('waitlisted',3))
        self.assertEqual({r[0] for r in self.db.execute('SELECT status FROM animation_bookings WHERE group_uuid=?',(value['group_uuid'],))},{'waitlisted'})

    def test_closed_waitlist_refuses_all_and_total_cap_cannot_be_exceeded(self):
        self.db.execute('UPDATE animation_reservation_config SET capacity=2,waitlist_enabled=0');self.db.commit()
        with self.assertRaises(ValueError):self.book([self.a,self.c,self.d])
        self.book([self.teen],owner=self.teen)
        with self.assertRaises(ValueError):self.book([self.a,self.c])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],1)

    def test_retry_is_idempotent_and_modified_retry_is_refused(self):
        key=secrets.token_urlsafe(32);before=self.book([self.a,self.c],key=key)
        self.assertEqual(self.book([self.c,self.a],key=key),before)
        with self.assertRaises(ValueError):self.book([self.a,self.d],key=key)
        with self.assertRaises(ValueError):self.book([self.a,self.c])

    def test_manual_confirmation_is_atomic_and_respects_capacity(self):
        self.book([self.teen],owner=self.teen);self.book([self.older],owner=self.older)
        wait=self.book([self.a,self.c,self.d]);uuid=wait['booking_uuids'][0]
        with self.assertRaises(ValueError):engine.team_action(self.db,self.service,uuid,'confirm','moderator')
        self.db.execute("UPDATE animation_bookings SET status='cancelled' WHERE user_id=?",(self.teen,));self.db.commit()
        engine.team_action(self.db,self.service,uuid,'confirm','moderator')
        self.assertEqual(engine.result(self.db,wait['group_uuid'])['status'],'confirmed')

    def test_remove_responsible_refused_add_checks_capacity_and_permissions(self):
        value=self.book([self.a,self.c]);rows=self.db.execute('SELECT * FROM animation_bookings WHERE group_uuid=?',(value['group_uuid'],)).fetchall()
        adult=next(r for r in rows if r['user_id']==self.a)
        with self.assertRaises(ValueError):engine.team_action(self.db,self.service,adult['external_uuid'],'remove','admin')
        with self.assertRaises(ValueError):engine.team_action(self.db,self.service,adult['external_uuid'],'add','visitor',self.d)
        engine.team_action(self.db,self.service,adult['external_uuid'],'add','moderator',self.d)
        engine.team_action(self.db,self.service,adult['external_uuid'],'add','admin',self.b)
        with self.assertRaises(ValueError):engine.team_action(self.db,self.service,adult['external_uuid'],'add','admin',self.other)
        self.assertEqual(engine.result(self.db,value['group_uuid'])['count'],4)

    def test_presence_is_individual_and_cancel_is_group_wide(self):
        value=self.book([self.a,self.c]);uuid=value['booking_uuids'][0]
        engine.team_action(self.db,self.service,uuid,'present','moderator')
        self.assertEqual(self.db.execute('SELECT SUM(is_present) FROM animation_bookings').fetchone()[0],1)
        engine.team_action(self.db,self.service,uuid,'cancel','admin')
        self.assertEqual(engine.result(self.db,value['group_uuid'])['count'],0)

    def test_concurrent_capacity_never_splits_groups(self):
        self.db.execute('UPDATE animation_reservation_config SET capacity=3');self.db.commit()
        barrier=threading.Barrier(2);results=[]
        def submit(ids,owner):
            with sqlite3.connect(self.f.database_path,timeout=15) as db:
                db.row_factory=sqlite3.Row;barrier.wait()
                results.append(engine.reserve(db,owner,ids,self.service,None,secrets.token_urlsafe(32)))
        threads=[threading.Thread(target=submit,args=([self.a,self.c],self.a)),threading.Thread(target=submit,args=([self.b,self.d],self.b))]
        for t in threads:t.start()
        for t in threads:t.join(20)
        self.assertEqual(sorted(v['status'] for v in results),['confirmed','waitlisted'])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM animation_bookings WHERE status='confirmed'").fetchone()[0],2)

    def test_link_end_keeps_users_and_history(self):
        key=family.responsibles(self.db,self.c)[0]['link_uuid']
        family.end_link(self.db,key,self.c);self.db.commit()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],self.initial_users+7)
        self.assertIsNotNone(self.db.execute('SELECT ended_at FROM user_family_links WHERE link_uuid=?',(key,)).fetchone()[0])

    def test_configurable_threshold_and_exact_birthday(self):
        user=dict(self.db.execute('SELECT * FROM users WHERE id=?',(self.c,)).fetchone())
        user['birth_date']='2011-10-06'
        self.assertEqual(family.age(user,date(2026,10,5)),14);self.assertEqual(family.age(user,date(2026,10,6)),15)
        user['birth_date']=None;user['birth_year']=2011;self.assertEqual(family.age(user,date(2026,1,1)),15)
        for autonomy,responsible in [(0,0),(16,21),(15,18)]:
            self.assertEqual(family.validate_settings(dict(family_autonomy_age=str(autonomy),family_responsible_age=str(responsible)))['family_autonomy_age'],str(autonomy))
        with self.assertRaises(ValueError):family.validate_settings(dict(family_autonomy_age='20',family_responsible_age='18'))

    def test_contact_policies(self):
        empty={'email':None,'phone':None}
        self.assertEqual(family.missing_contacts('none',empty),[])
        self.assertEqual(len(family.missing_contacts('both',empty)),2)
        self.assertEqual(family.missing_contacts('either',{'email':'ok@example.invalid','phone':None}),[])
        self.assertEqual(family.missing_contacts('email',{'email':'broken','phone':'0600000000'}),['e-mail'])
        self.assertEqual(family.missing_contacts('phone',{'email':None,'phone':'1'}),['téléphone'])

    def test_identity_no_public_directory_rate_limit_and_expiration(self):
        for _ in range(5):
            with self.assertRaises(ValueError):engine.identify(self.db,self.service,'2001','wrong','bucket')
        with self.assertRaisesRegex(ValueError,'Trop de tentatives'):engine.identify(self.db,self.service,'2001','person0@example.invalid','bucket')
        token,owner=engine.identify(self.db,self.service,'2001','person0@example.invalid','different')
        self.assertEqual(owner,self.a);self.assertEqual(engine.grant(self.db,token,self.service,'production'),owner)
        self.assertNotIn(token,str([tuple(r) for r in self.db.execute('SELECT * FROM family_booking_grants')]))
        with self.assertRaises(ValueError):engine.grant(self.db,token,self.service+1,'production')
        self.db.execute('UPDATE family_booking_grants SET expires_at=0');self.db.commit()
        with self.assertRaises(ValueError):engine.grant(self.db,token,self.service,'production')
        self.assertEqual(self.client.get('/animations/usagers').status_code,404)

    def csrf(self,page):
        return re.search(r'name="evolution_csrf" value="([^"]+)"',page.get_data(as_text=True))[1]

    def test_kiosk_progressive_flow_without_wordpress_or_javascript(self):
        path=f'/animations/{self.service}/famille';page=self.client.get(path)
        self.assertNotIn('Fictif2',page.get_data(as_text=True))
        page=self.client.post(path,data=dict(evolution_csrf=self.csrf(page),step='identify',public_id='2001',contact='person0@example.invalid'))
        self.assertIn('Fictif2',page.get_data(as_text=True));self.assertNotIn('Ajouter un accompagnateur majeur',page.get_data(as_text=True))
        page=self.client.post(path,data=dict(evolution_csrf=self.csrf(page),step='select',person_ids=[str(self.a),str(self.c),str(self.d)]))
        self.assertIn('3 place(s)',page.get_data(as_text=True))
        nonce=re.search(r'name="nonce" value="([^"]+)"',page.get_data(as_text=True))[1]
        with mock.patch('urllib.request.urlopen',side_effect=AssertionError('No network')):
            result=self.client.post(path,data=dict(evolution_csrf=self.csrf(page),step='confirm',consent='1',nonce=nonce),follow_redirects=True)
        self.assertEqual(result.status_code,200);self.assertIn('3',result.get_data(as_text=True))
        self.assertEqual(result.headers['Cache-Control'],'private, no-store')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],3)

    def test_kiosk_bad_csrf_or_unrelated_selection_refused(self):
        path=f'/animations/{self.service}/famille';page=self.client.get(path)
        self.assertEqual(self.client.post(path,data=dict(evolution_csrf='bad',step='identify')).status_code,400)
        page=self.client.post(path,data=dict(evolution_csrf=self.csrf(page),step='identify',public_id='2001',contact='person0@example.invalid'))
        page=self.client.post(path,data=dict(evolution_csrf=self.csrf(page),step='select',person_ids=[str(self.other)]))
        self.assertIn('comptes actifs autorisés',page.get_data(as_text=True))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],0)

    def signed(self,action,data,nonce=None,https=True,secret=None):
        secret=secret or self.secret;stamp=str(int(time.time()));nonce=nonce or secrets.token_urlsafe(24)
        raw=json.dumps(dict(environment='production',**data),separators=(',',':')).encode();path='/api/reservations/familles/'+action
        canonical='\n'.join((stamp,nonce,'POST',path,hashlib.sha256(raw).hexdigest()))
        headers={'X-OpenFabLab-Timestamp':stamp,'X-OpenFabLab-Nonce':nonce,'X-OpenFabLab-Signature':hmac.new(secret.encode(),canonical.encode(),hashlib.sha256).hexdigest()}
        return self.client.post(path,data=raw,content_type='application/json',headers=headers,base_url='https://localhost' if https else 'http://localhost')

    def test_signed_wordpress_uses_same_engine_opaque_choices_no_private_fields(self):
        self.secret='fictional-shared-secret-'+'x'*40;save_sync_secret(self.f.database_path,self.secret)
        catalogue=self.signed('catalogue',{});self.assertEqual(catalogue.status_code,200)
        self.assertNotIn('Fictif2',catalogue.get_data(as_text=True))
        identity=self.signed('identify',dict(service_id=self.service,public_id='2001',contact='person0@example.invalid',client_bucket='fictional-client'))
        self.assertEqual(identity.status_code,200);data=identity.get_json()
        self.assertEqual(set(data),{'token','participants','contact_required','phone_required'})
        self.assertTrue(all(set(p)=={'key','name','label'} for p in data['participants']))
        selected=[p['key'] for p in data['participants'] if p['name'].startswith(('Fictif0 ','Fictif2 ','Fictif3 '))]
        body=dict(service_id=self.service,token=data['token'],participants=selected,request_key=secrets.token_urlsafe(32),consent=True)
        value=self.signed('reserve',body);self.assertEqual(value.status_code,200);self.assertEqual(value.get_json()['count'],3)
        self.assertEqual(self.signed('reserve',body).get_json(),value.get_json())
        self.assertTrue(all(r[0]=='family_wordpress' for r in self.db.execute('SELECT source FROM animation_bookings')))

    def test_unsigned_bad_signature_replay_and_forged_choices_refused(self):
        self.secret='fictional-shared-secret-'+'x'*40;save_sync_secret(self.f.database_path,self.secret)
        nonce=secrets.token_urlsafe(24)
        self.assertEqual(self.signed('catalogue',{},nonce=nonce).status_code,200)
        self.assertEqual(self.signed('catalogue',{},nonce=nonce).status_code,409)
        self.assertEqual(self.signed('catalogue',{},https=False).status_code,403)
        self.assertEqual(self.signed('catalogue',{},secret='wrong').status_code,403)
        self.assertEqual(self.signed('reserve',dict(service_id=self.service,token='invented',participants=['invented'],consent=True)).status_code,409)

    def test_legacy_plugin_sync_refused_without_replaying_or_deleting_history(self):
        client=mock.Mock();client.post.return_value={'protocol_version':2}
        with self.assertRaises(ValueError):_sync_environment(self.db,client,'production',[],None,[],[])
        self.assertEqual(client.post.call_count,1)
        client.post.return_value={'family_gateway_v1':True,'plugin_version':'2.8.0'}
        self.assertEqual(_sync_environment(self.db,client,'production',[],None,[],[]),0)
        self.assertEqual(client.post.call_count,2)

    def test_schema15_restart_and_fault_rollback_preserve_old_rows(self):
        # Simulate a coherent 14 fixture by removing only the added schema.
        self.db.execute('PRAGMA foreign_keys=OFF')
        for name in ('family_booking_requests','family_booking_grants','family_api_nonces','family_age_observations','user_family_links','calendar_visibility'):
            self.db.execute('DROP TABLE '+name)
        self.db.execute('ALTER TABLE users DROP COLUMN birth_date');self.db.execute('ALTER TABLE users DROP COLUMN birth_precision')
        self.db.execute('PRAGMA user_version=14');self.db.commit()
        before=[tuple(r) for r in self.db.execute('SELECT * FROM users ORDER BY id')]
        pre=family.backup_before(self.db,self.f.database_path);self.assertTrue(Path(pre).is_file())
        with self.assertRaises(RuntimeError):family.migrate(self.db,lambda db: (_ for _ in ()).throw(RuntimeError('injected')))
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],14)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM users ORDER BY id')],before)
        family.migrate(self.db);family.migrate(self.db)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],15)
        columns=[r['name'] for r in self.db.execute('PRAGMA table_info(users)') if r['name'] not in ('birth_date','birth_precision')]
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT '+','.join(columns)+' FROM users ORDER BY id')],before)
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0],'ok');self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_team_page_displays_accounts_and_group_without_old_companion_form(self):
        self.book([self.a,self.c,self.d]);self.f.login_admin()
        page=self.client.get(f'/admin/animations/{self.service}/inscriptions')
        self.assertEqual(page.status_code,200);text=page.get_data(as_text=True)
        self.assertIn('Une même demande · 3 place(s)',text);self.assertIn('Ajouter des participants',text)
        self.assertNotIn('Usager existant (facultatif)',text)


if __name__=='__main__':unittest.main()
