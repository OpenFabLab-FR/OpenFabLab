"""Fictional core protocol-4 receipts, privacy and crash/concurrency guards."""
import hashlib,hmac,json,secrets,time,threading,sqlite3,unittest
from unittest import mock
from tests import test_families as family_fixtures
import outbound_actions as relay
import outbound_sync as sync
import family_waitlist as waiting
from reservations_sync import signed_headers


class OutboundTests(unittest.TestCase):
    def setUp(self):
        self.f=family_fixtures.FamilyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db=self.f.db;self.secret=b'fictional-outbound-shared-secret'
    def envelope(self,kind,data,env='production',key=None):
        raw=json.dumps(dict(data,environment=env),ensure_ascii=False,separators=(',',':'))
        return {'id':key or secrets.token_hex(24),'type':kind,'payload_json':raw,'hash':hashlib.sha256(raw.encode()).hexdigest()}
    def process(self,kind,data,env='production'):
        return relay.process_action(self.db,self.envelope(kind,data,env),env,self.secret)
    def identify(self):
        return self.process('identify',{'service_id':self.f.service,'public_id':'2001','contact':'person0@example.invalid','client_bucket':'fictitious'})['value']
    def reservation(self,ids=None):
        identity=self.identify();people=ids or [0,2,3]
        return self.envelope('reserve',{'service_id':self.f.service,'token':identity['token'],'participants':[p['key'] for p in identity['participants'] if int(p['name'][6:7]) in people],'consent':True})
    def test_receipt_replay_same_result_not_second_reservation(self):
        request=self.reservation();first=relay.process_action(self.db,request,'production',self.secret)
        self.assertEqual(relay.process_action(self.db,request,'production',self.secret),first)
        self.assertEqual(first['value']['count'],3)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],3)
    def test_crash_between_effect_and_receipt_rolls_back_both(self):
        request=self.reservation()
        def crash(db):raise RuntimeError('Fictional crash')
        with self.assertRaises(RuntimeError):relay.process_action(self.db,request,'production',self.secret,crash)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM wordpress_action_receipts WHERE action_type='reserve'").fetchone()[0],0)
        self.assertTrue(relay.process_action(self.db,request,'production',self.secret)['ok'])
    def test_reused_id_changed_payload_refused(self):
        request=self.reservation();relay.process_action(self.db,request,'production',self.secret)
        request2=self.envelope('reserve',{'service_id':1},key=request['id'])
        with self.assertRaises(ValueError):relay.process_action(self.db,request2,'production',self.secret)
    def test_tampered_payload_hash_refused(self):
        request=self.reservation();request['payload_json']+=' '
        with self.assertRaises(ValueError):relay.process_action(self.db,request,'production',self.secret)
    def test_environment_cannot_cross(self):
        request=self.reservation()
        with self.assertRaises(ValueError):relay.process_action(self.db,request,'test',self.secret)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],0)
    def test_foreign_choice_refused(self):
        identity=self.identify()
        result=self.process('reserve',{'service_id':self.f.service,'token':identity['token'],'participants':['a'*64],'consent':True})
        self.assertFalse(result['ok']);self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],0)
    def test_no_consent_no_seats(self):
        request=self.reservation();data=json.loads(request['payload_json']);data['consent']=False
        request=self.envelope('reserve',data)
        self.assertFalse(relay.process_action(self.db,request,'production',self.secret)['ok'])
    def test_non_autonomous_without_guardian_rejected(self):
        request=self.reservation([2]);value=relay.process_action(self.db,request,'production',self.secret)
        self.assertFalse(value['ok']);self.assertIn('responsable',value['message'])
    def test_removed_link_revalidated_at_processing(self):
        request=self.reservation([0,2]);self.db.execute('UPDATE user_family_links SET ended_at=? WHERE member_id=? AND responsible_id=?',('ended',self.f.c,self.f.a));self.db.commit()
        self.assertFalse(relay.process_action(self.db,request,'production',self.secret)['ok'])
    def test_insufficient_capacity_waitlists_whole_group(self):
        self.f.book([self.f.teen],owner=self.f.teen);self.f.book([self.f.older],owner=self.f.older)
        result=relay.process_action(self.db,self.reservation(),'production',self.secret)
        self.assertEqual((result['value']['status'],result['value']['count']),('waitlisted',3))
    def test_identification_attempts_survive_validation_refusal(self):
        for _ in range(5):
            self.assertFalse(self.process('identify',{'service_id':self.f.service,'public_id':'2001','contact':'wrong','client_bucket':'same'})['ok'])
        refused=self.process('identify',{'service_id':self.f.service,'public_id':'2001','contact':'person0@example.invalid','client_bucket':'same'})
        self.assertIn('tentatives',refused['message'])
    def test_receipt_replay_does_not_count_an_identification_attempt(self):
        request=self.envelope('identify',{'service_id':self.f.service,'public_id':'2001','contact':'wrong','client_bucket':'same'})
        for _ in range(10):relay.process_action(self.db,request,'production',self.secret)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM security_events WHERE event_type='family_identify_attempt'").fetchone()[0],1)
    def test_private_identity_receipt_pruned_without_losing_idempotence(self):
        self.identify();self.db.execute('UPDATE wordpress_action_receipts SET private_until=0');self.db.commit();relay.prune_private_receipts(self.db)
        row=self.db.execute('SELECT result_json FROM wordpress_action_receipts').fetchone()[0]
        self.assertNotIn('Fictif',row);self.assertNotIn('token',row)
    def test_failed_names_pruned_too(self):
        relay.process_action(self.db,self.reservation([2]),'production',self.secret)
        self.db.execute('UPDATE wordpress_action_receipts SET private_until=0');self.db.commit();relay.prune_private_receipts(self.db)
        self.assertNotIn('Fictif',''.join(r[0] for r in self.db.execute('SELECT result_json FROM wordpress_action_receipts')))
    def test_catalogue_contains_no_accounts_or_contacts(self):
        data=relay.public_catalogue(self.db,'production');raw=json.dumps(data)
        self.assertEqual(len(data),1)
        for word in ('Fictif','@','public_id','user_id','responsible','"phone":','"email":'):self.assertNotIn(word,raw)
        self.assertIs(type(data[0]['phone_required']),bool)
    def test_intervals(self):
        for value in (0,1,9,61,'15.1','nan',None):self.assertEqual(relay.action_interval(value),15)
        for value in (10,15,60):self.assertEqual(relay.action_interval(str(value)),value)
    def test_link_signature_and_scope(self):
        value=relay.issue_link(self.secret,'a'*43,'production','offer',int(time.time())+60)
        self.assertEqual(relay.verify_link(self.secret,value,'production','accept')['k'],'offer')
        for env,secret,token in [('test',self.secret,value),('production',b'wrong',value),('production',self.secret,value+'0')]:
            with self.assertRaises(ValueError):relay.verify_link(secret,token,env)
    def test_offer_expiry_at_engine_time(self):
        value=relay.issue_link(self.secret,'a'*43,'production','offer',int(time.time())-1)
        with self.assertRaisesRegex(ValueError,'expiré'):relay.verify_link(self.secret,value,'production','accept')
    def test_manage_link_cannot_accept_offer(self):
        value=relay.issue_link(self.secret,'a'*43,'production','manage')
        with self.assertRaises(ValueError):relay.verify_link(self.secret,value,'production','accept')
    def test_view_no_business_transition_even_expired_group(self):
        result=self.f.book([self.f.a]);payload=json.loads(self.db.execute('SELECT payload_json FROM family_booking_emails').fetchone()[0])
        link=relay.issue_link(self.secret,payload['token'],'production')
        before=[tuple(r) for r in self.db.execute('SELECT * FROM animation_bookings')]
        self.assertTrue(self.process('view',{'link':link})['ok'])
        self.assertEqual(before,[tuple(r) for r in self.db.execute('SELECT * FROM animation_bookings')])
    def test_cancellation_replay_no_second_offer(self):
        self.f.book([self.f.a,self.f.c,self.f.d]);payload=json.loads(self.db.execute('SELECT payload_json FROM family_booking_emails').fetchone()[0]);link=relay.issue_link(self.secret,payload['token'],'production')
        request=self.envelope('cancel',{'link':link,'consent':True});first=relay.process_action(self.db,request,'production',self.secret)
        self.assertEqual(first,relay.process_action(self.db,request,'production',self.secret))
        self.assertEqual(first['value']['status'],'cancelled')
    def test_unknown_action_no_receipt(self):
        with self.assertRaises(ValueError):relay.process_action(self.db,self.envelope('delete',{}),'production',self.secret)
    def test_invalid_payload_size(self):
        with self.assertRaises(ValueError):relay.process_action(self.db,self.envelope('identify',{'contact':'x'*20000}),'production',self.secret)
    def test_two_threads_same_envelope_no_double_effect(self):
        request=self.reservation();results=[];errors=[]
        def worker():
            try:
                with sqlite3.connect(self.f.f.database_path,timeout=15) as db:
                    db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON');results.append(relay.process_action(db,request,'production',self.secret))
            except Exception as e:errors.append(type(e).__name__)
        threads=[threading.Thread(target=worker) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(errors,[]);self.assertEqual(results[0],results[1]);self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],3)
    def test_old_capability_fail_closed(self):
        client=mock.Mock();client.post.return_value={'protocol_version':3,'family_gateway_v1':True}
        with self.assertRaises(ValueError):sync.negotiate(client,'production')
    def test_sqlite_schema_and_integrity(self):
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],18)
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_schema_fifteen_failure_is_atomic_then_retry_is_idempotent(self):
        import family_model as family
        self.f.book([self.f.a,self.f.c,self.f.d])
        self.db.execute('DROP TABLE wordpress_action_receipts')
        self.db.execute('DROP TABLE wordpress_relay_state')
        self.db.execute("DELETE FROM app_settings WHERE key IN ('reservation_action_interval_seconds','reservation_link_mode')")
        self.db.execute('PRAGMA user_version=15');self.db.commit()
        before=list(self.db.iterdump())
        def crash(db):raise RuntimeError('Fictional migration interruption')
        with self.assertRaises(RuntimeError):family.migrate(self.db,crash)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],15)
        self.assertEqual(list(self.db.iterdump()),before)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'wordpress_%'").fetchone()[0],0)
        family.migrate(self.db);after=list(self.db.iterdump());family.migrate(self.db)
        self.assertEqual(list(self.db.iterdump()),after)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],18)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM animation_bookings WHERE status='confirmed'").fetchone()[0],3)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_idle_poll_reads_no_accounts_or_catalogue(self):
        client=mock.Mock();client.post.return_value={'protocol_version':4,'relay_revision':3,'outbound_actions_v1':True,'actions':[]}
        statements=[];self.db.set_trace_callback(statements.append)
        with mock.patch('runtime_policy.external_allowed',return_value=True),mock.patch('outbound_sync.load_sync_secret',return_value=self.secret):
            self.assertEqual(sync.poll(self.db,self.f.f.database_path,'https://example.invalid',client)['processed'],0)
        self.db.set_trace_callback(None)
        self.assertEqual(len(client.post.call_args_list),2)
        for statement in statements:
            if statement.upper().startswith('SELECT'):
                for private in ('users','family_booking','fablab_services','animation_bookings'):
                    self.assertNotIn(private,statement)

    def test_worker_separates_fifteen_second_actions_and_ninety_second_catalogue(self):
        from app import write_setting
        write_setting(self.db,'reservation_wordpress_url','https://example.invalid');self.db.commit()
        class StopWorker(BaseException):pass
        clock=[0];catalogue_times=[];poll_times=[]
        def sleep(seconds):
            self.assertEqual(seconds,15);clock[0]+=seconds
            if clock[0]>=105:raise StopWorker()
        with mock.patch('threading.Thread') as thread:
            sync.start_worker(self.f.f.app,lambda:self.db,lambda db:{'public_reservations':True})
        worker=thread.call_args.kwargs['target']
        with mock.patch('runtime_policy.external_allowed',return_value=True),mock.patch('outbound_sync.time.monotonic',side_effect=lambda:clock[0]),mock.patch('outbound_sync.time.sleep',side_effect=sleep),mock.patch('outbound_sync.catalogue',side_effect=lambda *a,**kw:catalogue_times.append(clock[0])),mock.patch('outbound_sync.poll',side_effect=lambda *a,**kw:poll_times.append(clock[0])),mock.patch('outbound_actions.prune_private_receipts'):
            with self.assertRaises(StopWorker):worker()
        self.assertEqual(catalogue_times,[0,90])
        self.assertEqual(poll_times,[0,15,30,45,60,75,90])

    def test_legacy_worker_cannot_duplicate_schema_sixteen_network(self):
        import app
        from app import write_setting
        from reservations_sync import save_sync_secret
        write_setting(self.db,'module_public_reservations','1');write_setting(self.db,'reservation_wordpress_url','https://example.invalid');self.db.commit()
        save_sync_secret(self.f.f.database_path,'fictional-secret-'+('x'*48))
        class StopWorker(BaseException):pass
        with mock.patch('app.threading.Thread') as thread:
            app.start_local_reservation_sync_worker(self.f.f.app)
        worker=thread.call_args.kwargs['target']
        with mock.patch('app.run_sync_cycle') as old,mock.patch('app.time.sleep',side_effect=StopWorker):
            with self.assertRaises(StopWorker):worker()
            old.assert_not_called()

    def test_catalogue_not_rebuilt_before_ninety_seconds(self):
        from datetime import datetime,timezone
        stamp=datetime.now(timezone.utc).isoformat()
        for env in relay.ENVIRONMENTS:self.db.execute('INSERT INTO wordpress_relay_state(environment,catalogue_at) VALUES(?,?) ON CONFLICT(environment) DO UPDATE SET catalogue_at=excluded.catalogue_at',(env,stamp))
        self.db.commit();client=mock.Mock()
        with mock.patch('runtime_policy.external_allowed',return_value=True),mock.patch('outbound_sync.load_sync_secret',return_value=self.secret),mock.patch('outbound_actions.public_catalogue') as build:
            sync.catalogue(self.db,self.f.f.database_path,'https://example.invalid',client,force=False)
            build.assert_not_called();client.post.assert_not_called()

    def test_failed_environment_does_not_block_other_environment(self):
        client=mock.Mock()
        def post(route,payload):
            if payload['environment']=='production':raise ValueError('fictional network failure')
            return {'protocol_version':4,'relay_revision':3,'outbound_actions_v1':True,'actions':[],'queue':{'pending':2,'processing':1,'failed':0,'retrying':0}}
        client.post.side_effect=post
        with mock.patch('runtime_policy.external_allowed',return_value=True),mock.patch('outbound_sync.load_sync_secret',return_value=self.secret):
            result=sync.poll(self.db,self.f.f.database_path,'https://example.invalid',client)
        self.assertEqual([e['environment'] for e in result['errors']],['production'])
        state=self.db.execute("SELECT * FROM wordpress_relay_state WHERE environment='test'").fetchone()
        self.assertEqual((state['pending'],state['processing']),(2,1));self.assertIsNone(state['last_error'])
        self.assertIsNotNone(self.db.execute("SELECT last_error FROM wordpress_relay_state WHERE environment='production'").fetchone()[0])


class ResponseSignatureTests(unittest.TestCase):
    def response(self,request,mutate=None):
        raw=b'{"ok":true,"protocol_version":4}';route='/openfablab/v1/sync/capabilities';stamp=str(int(time.time()));nonce=request.get_header('X-openfablab-nonce')
        headers={'X-OpenFabLab-Response-Timestamp':stamp,'X-OpenFabLab-Response-Nonce':nonce}
        canonical=f'response/v1\n{stamp}\n{nonce}\n{route}\n200\n{hashlib.sha256(raw).hexdigest()}'
        headers['X-OpenFabLab-Response-Signature']=hmac.new(b'fictional',canonical.encode(),hashlib.sha256).hexdigest()
        if mutate:mutate(headers)
        response=mock.MagicMock();response.status=200;response.headers=headers;response.read.return_value=raw;response.__enter__.return_value=response
        return response
    def test_signed_response_accepted(self):
        client=sync.OutboundClient('https://example.invalid',b'fictional',transport=lambda request,**_:self.response(request))
        self.assertTrue(client.post('/sync/capabilities',{})['ok'])
    def test_unsigned_bad_nonce_bad_stamp_bad_hmac_refused(self):
        for header,value in [('X-OpenFabLab-Response-Signature',''),('X-OpenFabLab-Response-Signature','a'*64),('X-OpenFabLab-Response-Nonce','old-nonce'),('X-OpenFabLab-Response-Timestamp','0')]:
            with self.subTest(header=header,value=value):
                client=sync.OutboundClient('https://example.invalid',b'fictional',transport=lambda request,**_:self.response(request,lambda h:h.update({header:value})))
                with self.assertRaises(ValueError):client.post('/sync/capabilities',{})
