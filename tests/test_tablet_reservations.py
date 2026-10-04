"""Fictional local requests, real sync dispatch, no production transports."""
import io
import json
import re
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from tests import test_app as fixtures
from flask.testing import FlaskClient
import app
import tablet_reservations as tablet
from reservations_sync import _sync_environment, import_events, save_sync_secret, sync_interval_seconds
from profile_archive import build_profile, parse_profile

PERSON=dict(first_name='Camille',last_name='EXEMPLE',birth_year='2000',email='camille@example.invalid',phone='+330600000000',public_id='')


class TabletTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.OpenFabLabTestCase();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.f.app.test_client_class=FlaskClient;self.client=self.f.app.test_client()
        with self.f.database() as db:
            for key,value in [('tablet_reservations_enabled','1'),('module_public_reservations','1'),('reservation_wordpress_url','https://example.invalid')]:
                app.write_setting(db,key,value)
            now=tablet.timestamp()
            self.service=db.execute("INSERT INTO fablab_services(service_type,title,description,service_date,start_time,end_time,minimum_age,expected_participants,created_at,updated_at) VALUES('animation','Atelier Exemple','Description fictive, accents é & sécurité.','2099-01-01','10:00','12:00',10,3,?,?)",(now,now)).lastrowid
            db.execute("INSERT INTO animation_reservation_config(service_id,enabled,environment,capacity,updated_at) VALUES(?,1,'production',3,?)",(self.service,now))
        save_sync_secret(self.f.database_path,'fictional-secret-'+'x'*48)

    def form(self, values=None):
        page=self.client.get(f'/animations/{self.service}/reserver').get_data(as_text=True)
        data=dict(PERSON,participant_kind='visitor',consent='1')
        for key in ('evolution_csrf','form_token'):
            data[key]=re.search(r'name="'+key+'" value="([^"]+)"',page)[1]
        data.update(values or {})
        return data

    def queue(self,values=None):
        return self.client.post(f'/animations/{self.service}/reserver',data=self.form(values))

    def request_row(self,db):
        return tablet.requests_for(db)[0]

    def event(self,data=None):
        data=data or dict(PERSON,birth_year=2000,service_id=self.service,environment='production')
        return dict(id='1',type='reservation_confirmed',booking=dict(data,uuid='fictional-canonical-uuid',status='confirmed',link_status='visitor',created_at=tablet.timestamp(),updated_at=tablet.timestamp(),source='online'))

    def run_queue(self,db,client):
        with mock.patch('runtime_policy.external_allowed',return_value=True):
            tablet.process_requests(db,client,'production')

    def test_option_disabled_blocks_every_direct_route_and_footer(self):
        with self.f.database() as db:app.write_setting(db,'tablet_reservations_enabled','0')
        self.assertNotIn('Réserver une animation',self.client.get('/').get_data(as_text=True))
        for route in ('/animations',f'/animations/{self.service}',f'/animations/{self.service}/reserver','/animations/demande'):
            self.assertEqual(self.client.get(route).status_code,404)
        self.assertEqual(self.client.post(f'/animations/{self.service}/reserver',data=PERSON).status_code,404)

    def test_option_enabled_footer_and_catalogue_are_public_allowlisted(self):
        self.assertIn('Réserver une animation',self.client.get('/').get_data(as_text=True))
        page=self.client.get('/animations').get_data(as_text=True)
        self.assertIn('Atelier Exemple',page);self.assertIn('Description fictive',page)
        self.assertNotIn('camille@example.invalid',page);self.assertNotIn('fictional-secret',page)
        self.assertEqual(self.client.get('/animations').headers['Cache-Control'],'private, no-store')

    def test_past_closed_unpublished_and_test_animations_hidden(self):
        for field,value in [('service_date','2020-01-01'),('signup_open_at','2099-01-01T00:00:00+00:00'),('enabled',0),('environment','test')]:
            with self.subTest(field=field),self.f.database() as db:
                table='fablab_services' if field=='service_date' else 'animation_reservation_config'
                db.execute(f'UPDATE {table} SET {field}=?',(value,));db.commit()
                self.assertNotIn('Description fictive',self.client.get('/animations').get_data(as_text=True))
                db.execute("UPDATE fablab_services SET service_date='2099-01-01'")
                db.execute("UPDATE animation_reservation_config SET signup_open_at=NULL,enabled=1,environment='production'")

    def test_visitor_deposit_is_offline_pending_not_capacity_or_presence(self):
        with mock.patch('urllib.request.urlopen',side_effect=AssertionError('No transport during deposit')):
            self.assertEqual(self.queue().status_code,302)
        with self.f.database() as db:
            row=self.request_row(db);self.assertEqual(row['payload']['state'],'pending')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],0)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],14)
        receipt=self.client.get('/animations/demande').get_data(as_text=True)
        self.assertIn('En attente de confirmation',receipt)
        self.assertNotIn('Votre réservation est enregistrée.',receipt)
        self.assertNotIn(PERSON['email'],receipt);self.assertNotIn(PERSON['last_name'],receipt)

    def test_usager_known_id_contact_no_directory_endpoint(self):
        with self.f.database() as db:
            user=db.execute('SELECT public_id FROM users LIMIT 1').fetchone()[0]
            db.execute("UPDATE users SET email='camille@example.invalid' WHERE public_id=?",(user,))
        self.assertEqual(self.queue(dict(participant_kind='user',public_id=user)).status_code,302)
        self.assertEqual(self.client.get('/animations/usagers').status_code,404)
        self.assertEqual(self.client.get('/animations/demande/invented').status_code,404)

    def test_unknown_id_and_non_matching_contact_rejected_generically(self):
        for public_id in ('0000','bad'):
            self.assertEqual(self.queue(dict(participant_kind='user',public_id=public_id)).status_code,400)

    def test_csrf_and_form_replay_refused(self):
        data=self.form();bad=dict(data,evolution_csrf='forged')
        self.assertEqual(self.client.post(f'/animations/{self.service}/reserver',data=bad).status_code,400)
        self.assertEqual(self.client.post(f'/animations/{self.service}/reserver',data=data).status_code,302)
        self.assertEqual(self.client.post(f'/animations/{self.service}/reserver',data=data).status_code,400)

    def test_duplicate_pending_request_refused(self):
        self.queue();self.assertEqual(self.queue().status_code,400)
        with self.f.database() as db:self.assertEqual(len(tablet.requests_for(db)),1)

    def test_public_path_locks_admin_and_moderator_sessions(self):
        for role in ('admin','moderator'):
            with self.client.session_transaction() as s:s.update(access_role=role,admin_authenticated=True)
            self.client.get('/animations')
            with self.client.session_transaction() as s:
                self.assertNotIn('access_role',s);self.assertNotIn('admin_authenticated',s)
            self.assertEqual(self.client.get('/admin/usagers').status_code,302)

    def test_confirmation_and_waitlist_are_decided_only_by_same_wp_endpoint(self):
        for status in ('confirmed','waitlisted'):
            with self.subTest(status=status),self.f.database() as db:
                db.execute('DELETE FROM reservation_outbox');db.commit()
                self.queue()
                client=mock.Mock();client.post.return_value={'status':status,'count':1}
                self.run_queue(db,client)
                self.assertEqual(client.post.call_args.args[0],'/public/reserve')
                self.assertEqual(client.post.call_args.args[1]['environment'],'production')
                self.assertEqual(self.request_row(db)['payload']['state'],status)
                self.assertIsNotNone(self.request_row(db)['sent_at'])
                self.assertIn('Votre réservation est enregistrée.',self.client.get('/animations/demande').get_data(as_text=True))

    def test_full_without_waitlist_and_duplicate_rejection_do_not_confirm(self):
        self.queue()
        client=mock.Mock();client.post.side_effect=urllib.error.HTTPError('https://example.invalid',409,'refused',{},io.BytesIO(b'{"message":"private value"}'))
        with self.f.database() as db:
            self.run_queue(db,client)
            row=self.request_row(db);self.assertEqual(row['payload']['state'],'rejected')
            self.assertNotIn('private value',row['last_error'])

    def test_unknown_transport_result_is_not_blindly_replayed(self):
        self.queue();client=mock.Mock();client.post.side_effect=OSError('fictional lost response')
        with self.f.database() as db:
            self.run_queue(db,client);self.run_queue(db,client)
            self.assertEqual(client.post.call_count,1)
            self.assertEqual(self.request_row(db)['payload']['state'],'uncertain')
            self.assertIsNone(self.request_row(db)['sent_at'])

    def test_lost_response_recovers_from_canonical_sync_event_without_resubmit(self):
        self.queue();client=mock.Mock();client.post.side_effect=OSError('fictional lost response')
        with self.f.database() as db:
            self.run_queue(db,client)
            self.assertEqual(import_events(db,'production',[self.event()]),1);db.commit()
            self.run_queue(db,client)
            self.assertEqual(client.post.call_count,1)
            self.assertEqual(self.request_row(db)['payload']['state'],'confirmed')
            self.assertEqual(self.request_row(db)['payload']['booking_uuid'],'fictional-canonical-uuid')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],1)

    def test_private_clone_blocks_queue_transport_even_if_configured(self):
        self.queue();client=mock.Mock()
        from runtime_policy import TEST_MARKER
        (Path(self.f.database_path).parent/TEST_MARKER).touch()
        with self.f.app.app_context(),self.f.database() as db:
            tablet.process_requests(db,client,'production');client.post.assert_not_called()
            self.assertEqual(self.request_row(db)['payload']['state'],'pending')

    def test_queue_submission_follows_catalogue_reconciliation_and_event_import(self):
        self.queue();calls=[]
        class Client:
            def post(inner,route,payload):
                calls.append(route)
                if route=='/sync/capabilities':return dict(ok=True,animation_slots_v1=True,catalog_snapshot_v1=True,custom_categories_v1=True,protocol_version=2)
                if route=='/public/reserve':return {'status':'confirmed','count':1}
                return dict(ok=True,events=[],cursor='0')
        with self.f.database() as db,mock.patch('runtime_policy.external_allowed',return_value=True):
            _sync_environment(db,Client(),'production',[],datetime.now(timezone.utc),[],[])
            self.assertLess(calls.index('/sync/snapshot'),calls.index('/public/reserve'))
            self.assertLess(calls.index('/sync/events'),calls.index('/public/reserve'))
            self.assertEqual(calls.count('/sync/events'),2)

    def test_moderator_sees_participants_requests_but_not_secrets(self):
        self.queue()
        with self.client.session_transaction() as s:s.update(access_role='moderator',admin_authenticated=True)
        page=self.client.get(f'/admin/animations/{self.service}/inscriptions')
        self.assertEqual(page.status_code,200);self.assertIn('Demandes depuis la borne',page.get_data(as_text=True))
        for url in ('/admin/reglages/structure','/admin/reglages/usagers'):
            self.assertIn(self.client.get(url).status_code,(302,403))

    def test_success_receipt_follows_later_canonical_cancellation(self):
        self.queue();client=mock.Mock();client.post.return_value={'status':'confirmed','count':1}
        with self.f.database() as db:
            self.run_queue(db,client)
            import_events(db,'production',[self.event()]);db.commit()
            tablet.reconcile_requests(db,'production')
            self.assertEqual(self.request_row(db)['payload']['booking_uuid'],'fictional-canonical-uuid')
            db.execute("UPDATE animation_bookings SET status='cancelled'");db.commit()
            tablet.reconcile_requests(db,'production')
            self.assertEqual(self.request_row(db)['payload']['state'],'cancelled')
        self.assertEqual(self.queue().status_code,302)

    def test_too_many_deposits_and_expired_form_refused(self):
        data=self.form()
        with self.client.session_transaction() as s:s['tablet_form']=dict(s['tablet_form'],started=0)
        self.assertEqual(self.client.post(f'/animations/{self.service}/reserver',data=data).status_code,400)
        for index in range(5):
            self.assertEqual(self.queue(dict(first_name='Exemple'+str(index))).status_code,302)
        self.assertEqual(self.queue(dict(first_name='Exemple6')).status_code,429)

    def test_companion_is_sent_as_same_two_person_request(self):
        values=dict(with_companion='1',**{'companion_'+k:v for k,v in dict(PERSON,first_name='Anne-Lise',email='anne-lise@example.invalid').items()})
        self.assertEqual(self.queue(values).status_code,302)
        client=mock.Mock();client.post.return_value={'status':'waitlisted','count':2}
        with self.f.database() as db:
            self.run_queue(db,client)
            self.assertEqual(client.post.call_args.args[1]['companion']['first_name'],'Anne-Lise')
            self.assertEqual(self.request_row(db)['payload']['state'],'waitlisted')

    def test_bad_fields_consent_and_honeypot_rejected(self):
        for values in ({'birth_year':'abc'},{'email':'broken'},{'phone':'1'},{'consent':''},{'website':'spam.invalid'}):
            with self.subTest(values=values):self.assertEqual(self.queue(values).status_code,400)

    def test_disabled_module_blocks_public_and_team_mutations(self):
        self.queue()
        with self.f.database() as db:
            key=self.request_row(db)['entity_key']
            app.write_setting(db,'module_public_reservations','0')
        self.assertEqual(self.client.get('/animations').status_code,404)
        with self.client.session_transaction() as s:s.update(access_role='moderator',admin_authenticated=True)
        self.assertEqual(self.client.post(f'/admin/animations/{self.service}/demandes/{key}/annuler').status_code,404)

    def test_moderator_can_cancel_only_pending_request_with_csrf(self):
        self.queue()
        with self.f.database() as db:key=self.request_row(db)['entity_key']
        with self.client.session_transaction() as s:s.update(access_role='moderator',admin_authenticated=True)
        route=f'/admin/animations/{self.service}/demandes/{key}/annuler'
        self.assertEqual(self.client.post(route).status_code,400)
        page=self.client.get(f'/admin/animations/{self.service}/inscriptions').get_data(as_text=True)
        token=re.search(r'name="evolution_csrf" value="([^"]+)"',page)[1]
        self.assertEqual(self.client.post(route,data={'evolution_csrf':token}).status_code,302)
        with self.f.database() as db:self.assertEqual(self.request_row(db)['payload']['state'],'cancelled')

    def test_moderator_can_add_walkin_locally_without_secret_permissions(self):
        with self.client.session_transaction() as s:s.update(access_role='moderator',admin_authenticated=True)
        self.client.get(f'/admin/animations/{self.service}/inscriptions')
        with self.client.session_transaction() as s:token=s['pin_csrf']
        response=self.client.post(f'/admin/animations/{self.service}/inscriptions/sur-place',data=dict(PERSON,csrf_token=token))
        self.assertEqual(response.status_code,302)
        with self.f.database() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM animation_bookings WHERE source='walkin'").fetchone()[0],1)
        self.assertIn(self.client.get('/admin/reglages/structure').status_code,(302,403))

    def test_retryable_rate_limit_keeps_pending_and_network_ack_not_replayed(self):
        self.queue();client=mock.Mock();client.post.side_effect=urllib.error.HTTPError('https://example.invalid',429,'busy',{},io.BytesIO())
        with self.f.database() as db:
            self.run_queue(db,client)
            self.assertEqual(self.request_row(db)['payload']['state'],'pending')
            client.post.side_effect=None;client.post.return_value={'status':'confirmed','count':1}
            self.run_queue(db,client);self.run_queue(db,client)
            self.assertEqual(client.post.call_count,2)

    def test_invalid_response_never_claims_confirmation_or_retries(self):
        self.queue();client=mock.Mock();client.post.return_value=[]
        with self.f.database() as db:
            self.run_queue(db,client);self.run_queue(db,client)
            self.assertEqual(self.request_row(db)['payload']['state'],'uncertain')
            self.assertEqual(client.post.call_count,1)

    def test_atomic_claim_does_not_send_a_concurrently_cancelled_request(self):
        self.queue();client=mock.Mock();original=tablet.save_state
        def concurrent_cancel(db,row,payload,state,*args,**kwargs):
            if state=='sending':
                cancelled=json.loads(row['payload_json']);cancelled['state']='cancelled'
                db.execute('UPDATE reservation_outbox SET payload_json=?,sent_at=? WHERE id=?',(json.dumps(cancelled,ensure_ascii=False),tablet.timestamp(),row['id']));db.commit()
            return original(db,row,payload,state,*args,**kwargs)
        with self.f.database() as db,mock.patch('tablet_reservations.save_state',side_effect=concurrent_cancel):
            self.run_queue(db,client);client.post.assert_not_called()
            self.assertEqual(self.request_row(db)['payload']['state'],'cancelled')

    def test_cancellation_compare_and_swap_refuses_already_claimed_request(self):
        self.queue()
        with self.f.database() as db:
            team=self.request_row(db);worker=self.request_row(db)
            self.assertTrue(tablet.save_state(db,worker,worker['payload'],'sending'))
            self.assertFalse(tablet.save_state(db,team,team['payload'],'cancelled',done=True))
            self.assertEqual(self.request_row(db)['payload']['state'],'sending')

    def test_ninety_seconds_profile_and_migration_preserve_custom_intervals(self):
        self.assertEqual(sync_interval_seconds('1.5'),90)
        self.assertEqual(sync_interval_seconds('1'),60)
        self.assertEqual(sync_interval_seconds('2'),120)
        for invalid in ('NaN','inf','0','1.2','invalid'):
            self.assertEqual(sync_interval_seconds(invalid),90)
        profile=parse_profile(build_profile({'tablet_reservations_enabled':'1','reservation_sync_interval_minutes':'1.5'},[],{}))
        self.assertEqual(profile['settings']['reservation_sync_interval_minutes'],'1.5')
        with self.f.app.app_context():
            db=app.get_database()
            for value in ('1.5','2','17'):
                app.write_setting(db,'reservation_sync_interval_minutes',value);db.commit()
                app.initialize_database()
                self.assertEqual(app.read_setting(db,'reservation_sync_interval_minutes'),value)
            db.execute("DELETE FROM app_settings WHERE key='reservation_sync_90s_initialized'")
            app.write_setting(db,'reservation_sync_interval_minutes','2');db.commit()
            app.initialize_database();self.assertEqual(app.read_setting(db,'reservation_sync_interval_minutes'),'1.5')


if __name__=='__main__':unittest.main()
