"""Guest bookings are snapshots, not users; same engine and durable receipts."""
import hashlib
import json
import secrets
import sqlite3
import threading
import unittest
from datetime import date, timedelta
from unittest import mock
from tests import test_families as fixtures
import family_model as family
import family_reservations as engine
import family_waitlist as waiting
import outbound_actions as relay
import outbound_sync as sync
from evolution_routes import category_palette
from reservations_sync import booking_capacity_used


class GuestTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.FamilyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db=self.f.db;self.secret=b'fictional-guest-relay-key'
        self.db.execute('PRAGMA foreign_keys=ON')
        self.data=dict(first_name='Camille',last_name='FICTIF',birth_date='1990-01-02',email='camille@example.invalid',phone='')
    def book(self, data=None, key=None, env='production'):
        return engine.reserve_guest(self.db,data or self.data,self.f.service,None,key or secrets.token_hex(24),env)
    def envelope(self, data=None, env='production', key=None):
        raw=json.dumps(dict(data or self.data,service_id=self.f.service,environment=env,consent=True))
        return dict(id=key or secrets.token_hex(24),type='guest',payload_json=raw,hash=hashlib.sha256(raw.encode()).hexdigest())
    def token(self, value, offer=False):
        if offer:
            return json.loads(self.db.execute("SELECT payload_json FROM family_booking_emails WHERE group_uuid=? AND kind='offer_pending' ORDER BY rowid DESC",(value['group_uuid'],)).fetchone()[0])['token']
        return self.db.execute('SELECT manage_token FROM family_booking_groups WHERE group_uuid=?',(value['group_uuid'],)).fetchone()[0]
    def full(self):
        return [self.f.book([p],owner=p) for p in (self.f.teen,self.f.older,self.f.other,self.f.b)]
    def setting(self,key,value):
        self.db.execute('INSERT INTO app_settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value));self.db.commit()
    def test_default_optional_snapshot_no_user_pin_or_qr(self):
        before=[tuple(r) for r in self.db.execute('SELECT * FROM users')]
        value=self.book();self.assertEqual((value['status'],value['count']),('confirmed',1))
        row=self.db.execute('SELECT * FROM animation_bookings').fetchone()
        self.assertIsNone(row['user_id']);self.assertIsNone(row['public_id']);self.assertEqual(row['source'],engine.GUEST_SOURCE)
        self.assertEqual(row['guest_birth_date'],'1990-01-02')
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM users')],before)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM family_booking_grants').fetchone()[0],0)
    def test_required_refuses_guest_but_preserves_account_family(self):
        self.setting('reservation_account_required','1')
        with self.assertRaisesRegex(ValueError,'compte'):self.book()
        self.assertEqual(self.f.book([self.f.a,self.f.c,self.f.d])['count'],3)
    def test_catalogue_sole_configuration_authority(self):
        for required in ('0','1'):
            self.setting('reservation_account_required',required);self.setting('reservation_phone_required',required)
            item=relay.public_catalogue(self.db,'production')[0]
            self.assertEqual(item['account_required'],required=='1');self.assertEqual(item['phone_required'],required=='1')
            self.assertEqual(item['autonomy_age'],15);self.assertNotIn('email',item)
    def test_email_always_required(self):
        for email in ('',None,'broken','a@example.invalid\r\nBcc: x@example.invalid'):
            with self.subTest(email=email),self.assertRaisesRegex(ValueError,'mail'):self.book(dict(self.data,email=email))
    def test_phone_optional(self):
        self.assertEqual(self.book()['status'],'confirmed')
    def test_account_policy_profile_roundtrip(self):
        from profile_archive import build_profile, parse_profile
        for required in ('0','1'):
            profile=parse_profile(build_profile({'reservation_account_required':required},[],{}))
            self.assertEqual(profile['settings']['reservation_account_required'],required)
        with self.assertRaises(ValueError):parse_profile(build_profile({'reservation_account_required':'yes'},[],{}))
    def test_qr_identifier_never_replaces_identity_check(self):
        with self.assertRaises(ValueError):engine.identify(self.db,self.f.service,'2001','wrong@example.invalid','qr-test')
        with self.assertRaises(ValueError):engine.identify(self.db,self.f.service,'9999','person0@example.invalid','qr-test')
    def test_phone_required_independent(self):
        self.setting('reservation_phone_required','1')
        with self.assertRaisesRegex(ValueError,'téléphone'):self.book()
        self.assertEqual(self.book(dict(self.data,phone='0600000000'))['status'],'confirmed')
    def test_invalid_optional_phone_refused(self):
        with self.assertRaisesRegex(ValueError,'téléphone'):self.book(dict(self.data,phone='bad'))
    def test_minimum_age_on_animation_date(self):
        self.db.execute('UPDATE fablab_services SET minimum_age=50');self.db.commit()
        with self.assertRaisesRegex(ValueError,'âge minimum'):self.book()
    def test_non_autonomous_guest_cannot_bypass_responsible_rule(self):
        born=date(self.f.today.year-10,1,1).isoformat()
        with self.assertRaisesRegex(ValueError,'responsable'):self.book(dict(self.data,birth_date=born))
    def test_autonomous_teen_and_configurable_threshold(self):
        born=date(self.f.today.year-16,1,1).isoformat()
        self.setting('family_autonomy_age','17')
        with self.assertRaises(ValueError):self.book(dict(self.data,birth_date=born))
        self.setting('family_autonomy_age','16');self.assertEqual(self.book(dict(self.data,birth_date=born))['status'],'confirmed')
    def test_birth_date_required_not_future_or_implausible(self):
        for born in ('',None,'invalid','2999-01-01','1800-01-01'):
            with self.subTest(born=born),self.assertRaises(ValueError):self.book(dict(self.data,birth_date=born))
    def test_name_sanitation_and_parameterized_storage(self):
        for name in ('','<script>','a\x00b','=formula',None,'a'*121):
            with self.subTest(name=name),self.assertRaises(ValueError):self.book(dict(self.data,first_name=name))
        value=self.book(dict(self.data,first_name="  Élodie   d’Exemple  ",last_name="O'FICTIF"))
        self.assertEqual(self.db.execute('SELECT first_name FROM animation_bookings').fetchone()[0],'Élodie d’Exemple')
        self.assertEqual(value['count'],1)
    def test_no_artificial_guest_family_or_identifier(self):
        for key in ('participants','companion','public_id','user_id','owner_id'):
            with self.subTest(key=key),self.assertRaises(ValueError):self.book(dict(self.data,**{key:'fake'}))
    def test_exact_capacity_and_closed_waitlist(self):
        self.db.execute('UPDATE animation_reservation_config SET capacity=1,waitlist_enabled=0');self.db.commit()
        self.assertEqual(self.book()['status'],'confirmed')
        with self.assertRaisesRegex(ValueError,'places'):self.book(dict(self.data,last_name='AUTRE'))
        self.assertEqual(booking_capacity_used(self.db,self.f.service),1)
    def test_duplicate_new_request_normalized_identity_refused(self):
        self.book()
        with self.assertRaisesRegex(ValueError,'existe déjà'):self.book(dict(self.data,first_name='  CAMILLE ',email='CAMILLE@example.invalid'))
        self.assertEqual(booking_capacity_used(self.db,self.f.service),1)
    def test_idempotent_after_restart_and_account_required_change(self):
        key=secrets.token_hex(24);value=self.book(key=key);self.setting('reservation_account_required','1')
        self.assertEqual(self.book(key=key),value)
        with self.assertRaises(ValueError):self.book(dict(self.data,last_name='Changed'),key)
    def test_waitlist_offer_accept_idempotent(self):
        fills=self.full();value=self.book();self.assertEqual(value['status'],'waitlisted')
        waiting.respond(self.db,self.token(fills[0]),'cancel')
        token=self.token(value,True);accepted=waiting.respond(self.db,token,'accept')
        self.assertEqual((accepted['status'],accepted['count']),('confirmed',1))
        self.assertEqual(waiting.respond(self.db,token,'accept'),accepted)
        self.assertEqual(booking_capacity_used(self.db,self.f.service),4)
    def test_offer_decline_and_expiration(self):
        fills=self.full();one=self.book();two=self.book(dict(self.data,last_name='SECOND'))
        waiting.respond(self.db,self.token(fills[0]),'cancel');waiting.respond(self.db,self.token(one,True),'decline')
        self.assertEqual(engine.result(self.db,two['group_uuid'])['status'],'offer_pending')
        now=waiting.utcnow()+timedelta(hours=25);waiting.process_due(self.db,now)
        with self.assertRaises(ValueError):waiting.respond(self.db,self.token(two,True),'accept',now)
        self.assertEqual(engine.result(self.db,two['group_uuid'])['status'],'expired')
    def test_fifo_fit_guest_after_large_family(self):
        fills=self.full();large=self.f.book([self.f.a,self.f.c,self.f.d]);small=self.book()
        waiting.respond(self.db,self.token(fills[0]),'cancel')
        self.assertEqual(engine.result(self.db,large['group_uuid'])['status'],'waitlisted')
        self.assertEqual(engine.result(self.db,small['group_uuid'])['status'],'offer_pending')
        self.assertEqual(booking_capacity_used(self.db,self.f.service),4)
    def test_cancellation_link_without_identification_get_no_mutation(self):
        value=self.book();token=self.token(value);link=relay.issue_link(self.secret,token,'production')
        view=relay.dispatch(self.db,dict(environment='production',link=link),'view','production',self.secret,'unused')
        self.assertEqual(view['status'],'confirmed');self.assertEqual(booking_capacity_used(self.db,self.f.service),1)
        with self.assertRaises(ValueError):relay.dispatch(self.db,dict(environment='production',link=link),'cancel','production',self.secret,'unused')
        cancelled=relay.dispatch(self.db,dict(environment='production',link=link,consent=True),'cancel','production',self.secret,'unused')
        self.assertEqual(cancelled['status'],'cancelled');self.assertEqual(booking_capacity_used(self.db,self.f.service),0)
    def test_atomic_receipt_crash_then_replay(self):
        envelope=self.envelope()
        with self.assertRaises(RuntimeError):relay.process_action(self.db,envelope,'production',self.secret,lambda db:(_ for _ in ()).throw(RuntimeError('crash')))
        self.assertEqual(booking_capacity_used(self.db,self.f.service),0)
        first=relay.process_action(self.db,envelope,'production',self.secret)
        self.assertTrue(first['ok']);self.assertEqual(relay.process_action(self.db,envelope,'production',self.secret),first)
        self.assertEqual(booking_capacity_used(self.db,self.f.service),1)
    def test_wrong_environment_signature_payload_and_consent(self):
        envelope=self.envelope()
        with self.assertRaises(ValueError):relay.process_action(self.db,envelope,'test',self.secret)
        envelope['hash']='0'*64
        with self.assertRaises(ValueError):relay.process_action(self.db,envelope,'production',self.secret)
        envelope=self.envelope(dict(self.data,consent=False))
        data=json.loads(envelope['payload_json']);data['consent']=False;raw=json.dumps(data);envelope.update(payload_json=raw,hash=hashlib.sha256(raw.encode()).hexdigest())
        self.assertFalse(relay.process_action(self.db,envelope,'production',self.secret)['ok'])
    def test_test_catalogue_does_not_contain_normal(self):
        self.assertEqual(relay.public_catalogue(self.db,'test'),[])
        result=relay.process_action(self.db,self.envelope(env='test'),'test',self.secret)
        self.assertFalse(result['ok']);self.assertEqual(booking_capacity_used(self.db,self.f.service),0)
    def test_concurrent_guest_capacity_one(self):
        self.db.execute('UPDATE animation_reservation_config SET capacity=1');self.db.commit()
        barrier=threading.Barrier(2);results=[]
        def submit(name):
            with sqlite3.connect(self.f.f.database_path,timeout=15) as db:
                db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON');barrier.wait()
                results.append(engine.reserve_guest(db,dict(self.data,last_name=name),self.f.service,None,secrets.token_hex(24)))
        threads=[threading.Thread(target=submit,args=(name,)) for name in ('PREMIER','SECOND')]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(sorted(v['status'] for v in results),['confirmed','waitlisted'])
        self.assertEqual(booking_capacity_used(self.db,self.f.service),1)
    def test_team_presence_cancel_permissions_and_no_family_add(self):
        value=self.book();key=value['booking_uuids'][0]
        with self.assertRaises(ValueError):engine.team_action(self.db,self.f.service,key,'cancel','visitor')
        with self.assertRaises(ValueError):engine.team_action(self.db,self.f.service,key,'add','admin',self.f.a)
        engine.team_action(self.db,self.f.service,key,'present','moderator')
        self.assertEqual(self.db.execute('SELECT is_present FROM animation_bookings').fetchone()[0],1)
        engine.team_action(self.db,self.f.service,key,'cancel','admin');self.assertEqual(booking_capacity_used(self.db,self.f.service),0)
    def test_guest_private_team_page_csv_pdf_and_no_user_link(self):
        self.book();self.f.f.login_admin()
        page=self.f.client.get(f'/admin/animations/{self.f.service}/inscriptions')
        self.assertEqual(page.status_code,200);self.assertIn('Sans compte',page.get_data(as_text=True))
        self.assertNotIn('Ajouter à cette même demande',page.get_data(as_text=True))
        export=self.f.client.get(f'/admin/animations/{self.f.service}/inscriptions.csv')
        self.assertEqual(export.status_code,200);self.assertIn('Sans compte',export.get_data(as_text=True))
        pdf=self.f.client.get(f'/admin/animations/{self.f.service}/inscriptions.pdf')
        self.assertEqual(pdf.status_code,200);self.assertTrue(pdf.data.startswith(b'%PDF'))
    def test_delete_cancelled_guest_animation_preserves_users(self):
        value=self.book();waiting.respond(self.db,self.token(value),'cancel');engine.delete_animation(self.db,self.f.service)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],0)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])
    def test_additive_schema16_migration_atomic_idempotent(self):
        before=[tuple(r) for r in self.db.execute('SELECT * FROM users')];self.db.execute('ALTER TABLE animation_bookings DROP COLUMN guest_birth_date');self.db.execute('PRAGMA user_version=16');self.db.commit()
        with self.assertRaises(RuntimeError):family.migrate(self.db,lambda db:(_ for _ in ()).throw(RuntimeError('crash')))
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],16)
        family.migrate(self.db);family.migrate(self.db)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],17)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT * FROM users')],before)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])
    def test_revision2_refused_before_business_poll(self):
        client=mock.Mock();client.post.return_value={'protocol_version':4,'relay_revision':2,'outbound_actions_v1':True,'actions':[]}
        with self.assertRaises(ValueError):sync.negotiate(client,'production')
        with self.assertRaises(ValueError):sync._poll_environment(self.db,'unused',client,'production',self.secret)
    def test_palette_configured_custom_fallback_and_contrast(self):
        for color in ('#000000','#ffffff','#FFFF00','#117733','#ff8800','#ffffff;}bad',None):
            bg,fg=category_palette(color);self.assertRegex(bg,r'^#[0-9a-fA-F]{6}$')
            def luminance(c):
                values=[int(c[i:i+2],16)/255 for i in (1,3,5)]
                return sum((v/12.92 if v<=0.04045 else ((v+.055)/1.055)**2.4)*w for v,w in zip(values,(.2126,.7152,.0722)))
            a,b=sorted([luminance(bg),luminance(fg)]);self.assertGreaterEqual((b+.05)/(a+.05),4.5)
        self.assertEqual(category_palette('#112233')[0],'#e7e9eb')
    def test_home_uses_custom_category_and_configured_color(self):
        stamp=family.timestamp()
        self.db.execute('INSERT INTO user_categories VALUES(?,?,?,?,?,?,?,?,?)',('custom_fixture','Nouvelle catégorie fictive','nouvelle categorie fictive','#ffee44',1,99,0,stamp,stamp))
        self.db.execute("UPDATE users SET category='custom_fixture' WHERE id=?",(self.f.a,))
        self.db.execute('INSERT INTO sessions(user_id,check_in,entry_method) VALUES(?,?,?)',(self.f.a,stamp,'id'));self.db.commit()
        text=self.f.client.get('/').get_data(as_text=True)
        self.assertIn('category-badge category-custom_fixture',text);self.assertIn('Nouvelle catégorie fictive',text)
        self.assertIn('--category-color:#ffee44;--category-background:#fffdec',text)
        self.assertIn('--category-ink:#665f1b',text)
    def test_home_displays_user_category_and_safe_color_fallback(self):
        self.db.execute("UPDATE user_categories SET color='not-a-color' WHERE category_key='user'")
        self.db.execute('INSERT INTO sessions(user_id,check_in,entry_method) VALUES(?,?,?)',(self.f.a,family.timestamp(),'id'));self.db.commit()
        text=self.f.client.get('/').get_data(as_text=True)
        self.assertIn('category-badge category-user',text);self.assertIn('--category-color:#72828a',text)
