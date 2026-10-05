"""Fictional accounts only: native mail, automatic whole-group FIFO, privacy."""
import json
import re
import secrets
import sqlite3
import threading
import unittest
from datetime import timedelta
from unittest import mock
from tests import test_families as fixtures
import family_model as family
import family_reservations as engine
import family_waitlist as queue
from reservations_sync import booking_capacity_used,save_sync_secret
from welcome_mail import save_config


class WaitlistTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.FamilyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db,self.client,self.service=self.f.db,self.f.client,self.f.service
        self.now=queue.utcnow()
        self.config=dict(host='smtp.example.invalid',port=587,security='starttls',username='fictional',
            password='fictional-password-not-a-real-secret',sender_name='Atelier Exemple',sender_email='atelier@example.invalid',reply_to='')
        save_config(self.f.f.database_path,self.config)
        self.fill=[]
        for index in range(4):
            key=self.db.execute("INSERT INTO users(public_id,first_name,last_name,birth_year,active,category,email,created_at) VALUES(?,?,'EXEMPLE',1980,1,'user',?,?)",
                (str(3001+index),'Remplissage'+str(index),'fill'+str(index)+'@example.invalid',family.timestamp())).lastrowid
            self.fill.append(key)
        self.db.commit()

    def book(self,ids,owner=None,source='kiosk'):
        return engine.reserve(self.db,owner or ids[0],ids,self.service,None,secrets.token_urlsafe(32),source=source,staff=source=='administration')

    def full(self):
        return [self.book([person]) for person in self.fill]

    def meta(self,booking):
        return dict(self.db.execute('SELECT * FROM family_booking_groups WHERE group_uuid=?',(booking['group_uuid'],)).fetchone())

    def status(self,booking):return self.meta(booking)['status']

    def cancel(self,booking):return queue.respond(self.db,self.meta(booking)['manage_token'],'cancel',self.now)

    def token(self,booking):
        return json.loads(self.db.execute("SELECT payload_json FROM family_booking_emails WHERE group_uuid=? AND kind='offer_pending' ORDER BY rowid DESC",(booking['group_uuid'],)).fetchone()[0])['token']

    def deliver(self,sender,now=None):
        return queue.deliver(self.db,self.f.f.database_path,sender,now or self.now,'https://atelier.example.invalid/stat')

    def test_individual_confirmed_and_email_queued_once(self):
        value=self.book([self.f.a]);self.assertEqual((value['count'],self.status(value)),(1,'confirmed'))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM family_booking_emails').fetchone()[0],1)
        sent=[];self.assertEqual(self.deliver(sent.append),1);self.assertEqual(self.deliver(sent.append),0)
        self.assertEqual(len(sent),1);self.assertIn('Réservation confirmée',str(sent[0]['Subject']))
        self.assertEqual(list(sent[0].iter_attachments()),[])

    def test_email_missing_or_invalid_refuses_all_before_writes(self):
        for value in (None,'bad','a\r\n@example.invalid','x'*255+'@example.invalid'):
            with self.subTest(value=value):
                self.db.execute('UPDATE users SET email=? WHERE id=?',(value,self.f.a));self.db.commit()
                with self.assertRaisesRegex(ValueError,'e-mail'):self.book([self.f.a])
                self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],0)

    def test_phone_optional_independent_from_account_policy(self):
        self.db.execute('UPDATE users SET phone=NULL WHERE id=?',(self.f.teen,));self.db.commit()
        value=self.book([self.f.teen]);self.assertEqual(self.status(value),'confirmed')

    def test_phone_required_refuses_then_succeeds(self):
        self.db.execute("UPDATE app_settings SET value='1' WHERE key='reservation_phone_required'")
        self.db.execute('UPDATE users SET phone=NULL WHERE id=?',(self.f.teen,));self.db.commit()
        with self.assertRaisesRegex(ValueError,'téléphone'):self.book([self.f.teen])
        queue.complete_contact(self.db,self.f.teen,'teen@example.invalid','0600000015')
        self.assertEqual(self.status(self.book([self.f.teen])),'confirmed')

    def test_child_uses_guardian_contact_without_copying_coordinates(self):
        self.db.execute('UPDATE users SET email=NULL,phone=NULL WHERE id=?',(self.f.c,));self.db.commit()
        value=self.book([self.f.c,self.f.a],owner=self.f.c)
        self.assertEqual(self.meta(value)['contact_email'],'person0@example.invalid')
        self.assertIsNone(self.db.execute('SELECT email FROM users WHERE id=?',(self.f.c,)).fetchone()[0])

    def test_fifo_fitting_group_and_retained_priority(self):
        fills=self.full();a=self.book([self.f.a,self.f.c,self.f.d]);b=self.book([self.f.teen]);c=self.book([self.f.other])
        original=self.meta(a)['created_at'];self.cancel(fills[0]);self.cancel(fills[1])
        self.assertEqual((self.status(a),self.status(b),self.status(c)),('waitlisted','offer_pending','offer_pending'))
        self.assertEqual(booking_capacity_used(self.db,self.service),4)
        queue.respond(self.db,self.token(b),'decline',self.now)
        self.cancel(fills[2]);self.cancel(fills[3])
        self.assertEqual(self.status(a),'offer_pending');self.assertEqual(self.meta(a)['created_at'],original)
        self.assertEqual(booking_capacity_used(self.db,self.service),4)
        self.assertEqual({r[0] for r in self.db.execute('SELECT status FROM animation_bookings WHERE group_uuid=?',(a['group_uuid'],))},{'offer_pending'})

    def test_offer_holds_exact_capacity_and_prevents_new_confirmation(self):
        self.full();a=self.book([self.f.a,self.f.c]);
        self.db.execute("UPDATE animation_bookings SET status='cancelled' WHERE user_id IN (?,?)",tuple(self.fill[:2]));self.db.commit()
        queue.process_due(self.db,self.now)
        b=self.book([self.f.teen]);self.assertEqual(self.status(b),'waitlisted')
        self.assertEqual(booking_capacity_used(self.db,self.service),4)
        self.assertEqual(self.status(a),'offer_pending')

    def test_accept_whole_group_idempotent_no_double_seat(self):
        fills=self.full();a=self.book([self.f.a,self.f.c]);self.cancel(fills[0]);self.cancel(fills[1])
        token=self.token(a);one=queue.respond(self.db,token,'accept',self.now)
        self.assertEqual(queue.respond(self.db,token,'accept',self.now),one)
        self.assertEqual((one['status'],one['count']),('confirmed',2))
        self.assertEqual(booking_capacity_used(self.db,self.service),4)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM family_booking_history WHERE group_uuid=? AND status='confirmed'",(a['group_uuid'],)).fetchone()[0],1)

    def test_refusal_releases_places_and_automatically_offers_next(self):
        fills=self.full();a=self.book([self.f.teen]);b=self.book([self.f.other]);self.cancel(fills[0])
        queue.respond(self.db,self.token(a),'decline',self.now)
        self.assertEqual((self.status(a),self.status(b)),('declined','offer_pending'))
        with self.assertRaises(ValueError):queue.respond(self.db,self.token(a),'accept',self.now)

    def test_expiry_releases_and_advances_without_team(self):
        fills=self.full();a=self.book([self.f.teen]);b=self.book([self.f.other]);self.cancel(fills[0])
        later=self.now+timedelta(hours=25);queue.process_due(self.db,later)
        self.assertEqual((self.status(a),self.status(b)),('expired','offer_pending'))
        with self.assertRaises(ValueError):queue.respond(self.db,self.token(a),'accept',later)
        self.assertEqual(booking_capacity_used(self.db,self.service),4)

    def test_cancel_pending_offer_advances_and_suppresses_stale_email(self):
        fills=self.full();a=self.book([self.f.teen]);b=self.book([self.f.other]);self.cancel(fills[0]);self.cancel(a)
        self.assertEqual(self.status(b),'offer_pending')
        sent=[];self.deliver(sent.append)
        self.assertFalse(any('person4@example.invalid'==str(m['To']) and 'place est disponible' in str(m['Subject']) for m in sent))

    def test_capacity_increase_automatically_offers_entire_group(self):
        self.full();a=self.book([self.f.a,self.f.c,self.f.d]);self.db.execute('UPDATE animation_reservation_config SET capacity=7');self.db.commit()
        queue.process_due(self.db,self.now);self.assertEqual(self.status(a),'offer_pending')
        self.assertEqual(booking_capacity_used(self.db,self.service),7)

    def test_offer_email_contains_people_deadline_and_response_link(self):
        fills=self.full();a=self.book([self.f.a,self.f.c]);self.cancel(fills[0]);self.cancel(fills[1])
        sent=[];self.deliver(sent.append)
        proposal=next(m for m in sent if 'place est disponible' in str(m['Subject']))
        body=proposal.get_body(preferencelist=('plain',)).get_content()
        for part in ('Fictif0','Fictif2','2 place(s)','Acceptez ou refusez','expire','https://atelier.example.invalid/stat/animations/demande/'):
            self.assertIn(part,body)
        self.assertNotIn('fictional-password',body)

    def test_smtp_retry_survives_restart_without_losing_request_or_seats(self):
        a=self.book([self.f.a]);bad=mock.Mock(side_effect=OSError('do-not-log-this-secret'))
        self.assertEqual(self.deliver(bad),0)
        row=self.db.execute('SELECT * FROM family_booking_emails').fetchone()
        self.assertEqual(row['last_error'],'OSError');self.assertNotIn('do-not-log',str(tuple(row)))
        self.assertEqual(self.deliver(bad),0);self.assertEqual(bad.call_count,1)
        sent=[];self.assertEqual(self.deliver(sent.append,self.now+timedelta(minutes=10)),1)
        self.assertEqual(self.status(a),'confirmed');self.assertEqual(booking_capacity_used(self.db,self.service),1)

    def test_stale_claim_is_recovered_but_live_claim_is_not(self):
        self.book([self.f.a]);self.db.execute("UPDATE family_booking_emails SET state='sending',claimed_at=?",(self.now.isoformat(),));self.db.commit()
        sent=[];self.assertEqual(self.deliver(sent.append),0)
        self.assertEqual(self.deliver(sent.append,self.now+timedelta(minutes=11)),1)

    def test_concurrent_delivery_claims_each_message_once(self):
        self.book([self.f.a]);barrier=threading.Barrier(2);sent=[];errors=[]
        def run():
            try:
                with sqlite3.connect(self.f.f.database_path,timeout=15) as db:
                    db.row_factory=sqlite3.Row;barrier.wait()
                    queue.deliver(db,self.f.f.database_path,sent.append,self.now,'https://atelier.example.invalid')
            except Exception as e:errors.append(type(e).__name__)
        threads=[threading.Thread(target=run) for _ in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(20)
        self.assertEqual(errors,[]);self.assertEqual(len(sent),1)

    def test_concurrent_accept_and_wordpress_request_do_not_overbook(self):
        fills=self.full();a=self.book([self.f.a,self.f.c]);self.cancel(fills[0]);self.cancel(fills[1]);token=self.token(a)
        barrier=threading.Barrier(2);answers=[];errors=[]
        def run(offer):
            try:
                with sqlite3.connect(self.f.f.database_path,timeout=15) as db:
                    db.row_factory=sqlite3.Row;barrier.wait()
                    answers.append(queue.respond(db,token,'accept',self.now) if offer else engine.reserve(db,self.f.teen,[self.f.teen],self.service,None,secrets.token_urlsafe(32),source='wordpress'))
            except Exception as e:errors.append(type(e).__name__)
        threads=[threading.Thread(target=run,args=(flag,)) for flag in (True,False)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(20)
        self.assertEqual(errors,[]);self.assertEqual(sorted(r['status'] for r in answers),['confirmed','waitlisted'])
        self.assertEqual(booking_capacity_used(self.db,self.service),4)

    def test_email_links_require_csrf_post_never_accept_on_get(self):
        fills=self.full();a=self.book([self.f.teen]);self.cancel(fills[0]);path='/animations/demande/'+self.token(a)
        page=self.client.get(path);self.assertEqual(page.status_code,200)
        self.assertEqual(self.status(a),'offer_pending');self.assertEqual(page.headers['Cache-Control'],'private, no-store')
        self.assertEqual(page.headers['Referrer-Policy'],'no-referrer')
        self.assertEqual(self.client.post(path,data={'action':'accept'}).status_code,400)
        response=self.client.post(path,data=dict(action='accept',evolution_csrf=self.f.csrf(page)),follow_redirects=True)
        self.assertEqual(response.status_code,200);self.assertEqual(self.status(a),'confirmed')
        self.assertEqual(self.client.get('/animations/demande/'+secrets.token_urlsafe(32)).status_code,404)

    def test_management_token_cannot_accept_or_refuse_offer(self):
        fills=self.full();a=self.book([self.f.teen]);self.cancel(fills[0]);token=self.meta(a)['manage_token']
        for action in ('accept','decline'):
            with self.assertRaises(ValueError):queue.respond(self.db,token,action,self.now)
        self.assertEqual(self.status(a),'offer_pending')

    def test_relationship_removed_after_offer_prevents_acceptance(self):
        fills=self.full();a=self.book([self.f.a,self.f.c]);self.cancel(fills[0]);self.cancel(fills[1])
        for link in family.responsibles(self.db,self.f.c):family.end_link(self.db,link['link_uuid'],self.f.c)
        self.db.commit()
        with self.assertRaisesRegex(ValueError,'responsable'):queue.respond(self.db,self.token(a),'accept',self.now)
        self.assertEqual(self.status(a),'offer_pending')

    def test_historical_bookings_never_adopted_or_modified(self):
        self.db.execute("INSERT INTO animation_bookings(external_uuid,service_id,environment,first_name,last_name,birth_year,status,link_status,group_uuid,source,created_at,updated_at) VALUES('historic',?,'production','Ancien','EXEMPLE',2015,'confirmed','unmatched','historic-group','wordpress',?,?)",(self.service,family.timestamp(),family.timestamp()));self.db.commit()
        before=tuple(self.db.execute("SELECT * FROM animation_bookings WHERE external_uuid='historic'").fetchone())
        queue.process_due(self.db,self.now)
        self.assertEqual(before,tuple(self.db.execute("SELECT * FROM animation_bookings WHERE external_uuid='historic'").fetchone()))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM family_booking_groups').fetchone()[0],0)

    def test_kiosk_missing_email_completion_after_phone_identification(self):
        self.db.execute('UPDATE users SET email=NULL WHERE id=?',(self.f.teen,));self.db.commit()
        path=f'/animations/{self.service}/famille';page=self.client.get(path)
        page=self.client.post(path,data=dict(evolution_csrf=self.f.csrf(page),step='identify',public_id='2005',contact='0600000004'))
        self.assertIn('Compléter mes coordonnées',page.get_data(as_text=True))
        bad=self.client.post(path,data=dict(evolution_csrf=self.f.csrf(page),step='contact',email='invalid'))
        self.assertIn('e-mail valide',bad.get_data(as_text=True))
        good=self.client.post(path,data=dict(evolution_csrf=self.f.csrf(bad),step='contact',email='teen-new@example.invalid',phone='0600000004'))
        self.assertIn('Pour qui réservez-vous',good.get_data(as_text=True))
        self.assertEqual(self.db.execute('SELECT email FROM users WHERE id=?',(self.f.teen,)).fetchone()[0],'teen-new@example.invalid')

    def test_wordpress_contact_completion_requires_valid_private_grant(self):
        self.f.secret='fictional-shared-secret-'+'x'*40;save_sync_secret(self.f.f.database_path,self.f.secret)
        self.db.execute('UPDATE users SET email=NULL WHERE id=?',(self.f.teen,));self.db.commit()
        identity=self.f.signed('identify',dict(service_id=self.service,public_id='2005',contact='0600000004',client_bucket='fictional')).get_json()
        self.assertTrue(identity['contact_required']);self.assertFalse(identity['phone_required'])
        bad=self.f.signed('contact',dict(service_id=self.service,token='forged',email='teen@example.invalid'))
        self.assertEqual(bad.status_code,409)
        done=self.f.signed('contact',dict(service_id=self.service,token=identity['token'],email='teen@example.invalid')).get_json()
        self.assertFalse(done['contact_required']);self.assertEqual(done['participants'],identity['participants'])
        value=self.f.signed('reserve',dict(service_id=self.service,token=done['token'],participants=[done['participants'][0]['key']],request_key=secrets.token_urlsafe(32),consent=True)).get_json()
        self.assertEqual(value['count'],1);self.assertEqual(value['status'],'confirmed')

    def test_native_smtp_mock_sends_without_any_wordpress_call(self):
        self.book([self.f.a]);self.db.execute("UPDATE app_settings SET value='https://atelier.example.invalid' WHERE key='reservation_public_url'");self.db.commit()
        transport=mock.MagicMock()
        transport.__enter__.return_value.send_message.return_value={}
        with mock.patch('runtime_policy.external_allowed',return_value=True),mock.patch('runtime_policy.require_external'),mock.patch('smtplib.SMTP',return_value=transport) as factory,mock.patch('urllib.request.urlopen',side_effect=AssertionError('No WordPress')):
            self.assertEqual(queue.run(self.db,self.f.f.database_path,now=self.now),1)
        factory.assert_called_once();transport.__enter__.return_value.starttls.assert_called_once()
        transport.__enter__.return_value.send_message.assert_called_once()

    def test_private_instance_blocks_all_real_email(self):
        self.book([self.f.a])
        with mock.patch('runtime_policy.external_allowed',return_value=False),mock.patch('welcome_mail.send') as sender:
            self.assertEqual(queue.deliver(self.db,self.f.f.database_path),0)
        sender.assert_not_called()

    def test_display_order_and_simplified_login_and_animation_form(self):
        self.f.f.login_admin();page=self.client.get('/admin/reglages/affichage').get_data(as_text=True)
        self.assertLess(page.index('Thème de la page'),page.index('Couleurs du calendrier'))
        self.assertLess(page.index('Couleurs du calendrier'),page.index('Plage horaire visible'))
        self.assertIn('form="display-options" type="time"',page)
        page=self.client.get(f'/admin/animations/{self.service}/modifier').get_data(as_text=True)
        self.assertNotIn('Inscriptions depuis OpenFabLab',page);self.assertNotIn('confirmés manuellement',page)
        self.client.post('/admin/deconnexion');page=self.client.get('/admin/connexion').get_data(as_text=True)
        self.assertNotIn('Code PIN à quatre chiffres.',page);self.assertIn('id="login-error" class="login-error" hidden',page)

    def test_two_responsibles_and_children_equal_four_places(self):
        value=self.book([self.f.a,self.f.b,self.f.c,self.f.d])
        self.assertEqual((value['count'],self.status(value)),(4,'confirmed'))
        self.assertEqual(booking_capacity_used(self.db,self.service),4)

    def test_administration_and_wordpress_share_atomic_capacity(self):
        self.db.execute('UPDATE animation_reservation_config SET capacity=3');self.db.commit()
        barrier=threading.Barrier(2);answers=[];errors=[]
        def submit(owner,ids,source):
            try:
                with sqlite3.connect(self.f.f.database_path,timeout=15) as db:
                    db.row_factory=sqlite3.Row;barrier.wait()
                    answers.append(engine.reserve(db,owner,ids,self.service,None,secrets.token_urlsafe(32),source=source,staff=source=='administration'))
            except Exception as error:errors.append(type(error).__name__)
        threads=[threading.Thread(target=submit,args=(self.f.a,[self.f.a,self.f.c],'administration')),
            threading.Thread(target=submit,args=(self.f.b,[self.f.b,self.f.d],'wordpress'))]
        for thread in threads:thread.start()
        for thread in threads:thread.join(20)
        self.assertEqual(errors,[]);self.assertEqual(sorted(r['status'] for r in answers),['confirmed','waitlisted'])
        self.assertEqual(booking_capacity_used(self.db,self.service),2)

    def test_test_environment_never_sends_real_smtp_automatically(self):
        self.db.execute("UPDATE animation_reservation_config SET environment='test'");self.db.execute("UPDATE app_settings SET value='https://atelier.example.invalid' WHERE key='reservation_public_url'");self.db.commit()
        engine.reserve(self.db,self.f.a,[self.f.a],self.service,None,secrets.token_urlsafe(32),environment='test')
        with mock.patch('runtime_policy.external_allowed',return_value=True),mock.patch('welcome_mail.send') as sender:
            self.assertEqual(queue.deliver(self.db,self.f.f.database_path,now=self.now),0)
        sender.assert_not_called()

    def test_phone_and_offer_settings_are_saved_without_changing_old_values(self):
        self.f.f.login_admin();page=self.client.get('/admin/reglages/structure').get_data(as_text=True)
        token=re.search(r'name="csrf_token" value="([^"]+)"',page)[1]
        previous=dict(self.db.execute("SELECT key,value FROM app_settings WHERE key IN('reservation_accompaniment_under_age','reservation_reminder_one_hours')"))
        data=dict(csrf_token=token,minimum_age='0',close_minutes='60',offer_hours='36',sync_interval_minutes='1.5',phone_required='1',waitlist_enabled='1',public_url='https://atelier.example.invalid/stat')
        self.assertEqual(self.client.post('/admin/reglages/structure/reservations',data=data).status_code,302)
        self.assertEqual(family.setting(self.db,'reservation_offer_hours'),'36');self.assertEqual(family.setting(self.db,'reservation_phone_required'),'1')
        self.assertEqual(family.setting(self.db,'reservation_public_url'),data['public_url'])
        self.assertEqual(previous,dict(self.db.execute("SELECT key,value FROM app_settings WHERE key IN('reservation_accompaniment_under_age','reservation_reminder_one_hours')")))
        self.client.post('/admin/reglages/structure/reservations',data=dict(data,public_url='https://user:password@example.invalid'))
        self.assertEqual(family.setting(self.db,'reservation_public_url'),data['public_url'])

    def test_native_worker_uses_local_engine_without_wordpress(self):
        application=self.f.f.app
        with mock.patch('threading.Thread') as thread,mock.patch('family_waitlist.run') as run,mock.patch('time.sleep',side_effect=RuntimeError('end fictional cycle')):
            queue.start_worker(application,lambda:self.db,lambda db:{'public_reservations':True})
            target=thread.call_args.kwargs['target']
            with self.assertRaisesRegex(RuntimeError,'fictional cycle'):target()
            run.assert_called_once_with(self.db,application.config['DATABASE'])

    def test_profile_transports_phone_rule_but_not_private_public_url(self):
        from profile_archive import build_profile,parse_profile
        raw=build_profile({'reservation_phone_required':'1','reservation_public_url':'https://private.example.invalid'},[],{})
        profile=parse_profile(raw)
        self.assertEqual(profile['settings']['reservation_phone_required'],'1')
        self.assertNotIn('reservation_public_url',profile['settings'])
        with self.assertRaises(ValueError):
            parse_profile(build_profile({'reservation_phone_required':'yes'},[],{}))

    def test_private_exports_preserve_parent_contact_without_copying_to_child(self):
        self.db.execute('UPDATE users SET email=NULL,phone=NULL WHERE id=?',(self.f.c,));self.db.commit()
        self.book([self.f.c,self.f.a],owner=self.f.c)
        self.f.f.login_admin()
        response=self.client.get(f'/admin/animations/{self.service}/inscriptions.csv')
        self.assertEqual(response.status_code,200)
        self.assertIn('person0@example.invalid',response.get_data(as_text=True))
        response=self.client.get(f'/admin/animations/{self.service}/inscriptions.pdf')
        self.assertEqual(response.status_code,200);self.assertTrue(response.data.startswith(b'%PDF'))
        self.assertIsNone(self.db.execute('SELECT email FROM users WHERE id=?',(self.f.c,)).fetchone()[0])
