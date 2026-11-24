"""Isolated fictional SQLite families, captured email only, no HTTP/SMTP."""
import hashlib
import json
import re
import secrets
import unittest
from unittest import mock
from tests import test_families as fixtures
import online_accounts as accounts
import online_mail
from outbound_actions import transaction,process_action

class Portal(unittest.TestCase):
    def setUp(self):
        f=fixtures.FamilyTests();f.setUp();self.addCleanup(f.doCleanups)
        self.f,self.db=f,f.db
        self.db.execute('PRAGMA foreign_keys=ON')
        self.browser='a'*64;self.secret=b'fictional isolated environment'
        self.now=2000000000
        self.conf=dict(host='smtp.example.invalid',security='tls',sender_email='mail@example.invalid')
        for key,val in [('online_accounts_enabled','1'),('online_signup_enabled','1'),
                        ('reservation_wordpress_url','https://demo.example.invalid'),('online_account_url','https://demo.example.invalid/compte/')]:
            self.db.execute('INSERT OR REPLACE INTO app_settings VALUES(?,?)',(key,val))
        self.db.commit()
    def call(self,op,env='production',**data):
        with transaction(self.db):
            return accounts.dispatch(self.db,dict(browser=self.browser,op=op,**data),env,self.secret,secrets.token_hex(16),self.now)
    def email(self):
        captured=[]
        self.assertTrue(online_mail.deliver_one(self.db,'not-a-real-db',self.now,
                        lambda _,msg:captured.append(msg),self.conf))
        return captured[0].get_body(preferencelist=('plain',)).get_content()
    def ticket(self):
        return re.search(r'#ofl-account=([\w-]+)',self.email())[1]
    def signup(self):
        return self.call('signup',email='ines@example.invalid',first_name='Inès',last_name='Fictive',
                         birth_date='1985-02-02',phone='0612121212',consent=True)
    def bind(self,key):
        u=self.db.execute('SELECT * FROM users WHERE id=?',(key,)).fetchone()
        self.db.execute('INSERT INTO online_identities VALUES(?,?,?)',(key,u['email'],self.now));self.db.commit()
        self.call('login',email=u['email'])
        self.call('confirm',ticket=self.ticket())
    def test_manual_automatic_and_conditional(self):
        for mode in ('manual','automatic','conditional'):
            with self.subTest(mode=mode):
                self.db.execute("UPDATE app_settings SET value=? WHERE key='online_approval'",(mode,));self.db.commit()
                self.assertEqual(self.signup(),accounts.PUBLIC_REPLY)
                ticket=self.ticket()
                self.assertFalse(self.db.execute("SELECT 1 FROM users WHERE email='ines@example.invalid'").fetchone())
                self.call('confirm',ticket=ticket)
                if mode=='manual':
                    req=self.db.execute("SELECT id FROM online_requests WHERE state='review'").fetchone()[0]
                    self.assertIn('examiner',self.email())
                    with transaction(self.db):accounts.review(self.db,req,'accept',checked=True,now=self.now)
                    with self.assertRaises(ValueError),transaction(self.db):accounts.review(self.db,req,'accept',checked=True,now=self.now)
                self.assertIn('identifiant',self.email())
                with self.assertRaises(ValueError):self.call('confirm',ticket=ticket)
                self.db.execute("DELETE FROM users WHERE email='ines@example.invalid'");self.db.commit()
    def test_ticket_binding_expiry_and_revocation(self):
        self.bind(self.f.a)
        self.assertEqual(self.call('overview')['me']['first_name'],'Fictif0')
        self.browser='b'*64
        with self.assertRaises(ValueError):self.call('overview')
        self.browser='a'*64
        with self.assertRaises(ValueError):self.call('overview',env='test')
        self.call('logout')
        with self.assertRaises(ValueError):self.call('overview')
        self.call('login',email='person0@example.invalid');t=self.ticket();self.browser='b'*64
        with self.assertRaises(ValueError):self.call('confirm',ticket=t)
        self.browser='a'*64;self.now+=1801
        with self.assertRaises(ValueError):self.call('confirm',ticket=t)
    def test_family_scope_and_atomic_booking(self):
        self.bind(self.f.a)
        people=self.call('overview')['people']
        self.assertEqual({p['id'] for p in people},{self.f.a,self.f.c,self.f.d})
        for ids in ([self.f.d],[self.f.other],[self.f.b]):
            with self.assertRaises(ValueError):self.call('reserve',participants=ids,service_id=self.f.service,consent=True)
        self.assertEqual(self.call('reserve',participants=[self.f.a,self.f.d],service_id=self.f.service,consent=True),
                         {'count':2,'status':'confirmed'})
        bookings=self.call('overview')['reservations']
        self.assertEqual(len(bookings),2)
        self.assertEqual(self.call('cancel',group=bookings[0]['cancel'],consent=True)['status'],'cancelled')
        self.call('child',first_name='Noé',last_name='Fictif',birth_date='2014-12-12',consent=True)
        self.assertIn('Noé',[p['first_name'] for p in self.call('overview')['people']])
    def test_recovery_shared_with_own_child_in_manual_does_not_activate(self):
        self.db.execute("UPDATE users SET email='family@example.invalid' WHERE id IN (?,?)",(self.f.a,self.f.d))
        self.db.commit()
        self.assertEqual(self.call('recover',email='family@example.invalid'),self.call('recover',email='absent@example.invalid'))
        self.call('confirm',ticket=self.ticket())
        self.assertIn('2001',self.email())
        with self.assertRaises(ValueError):self.call('overview')
        self.assertFalse(self.db.execute('SELECT 1 FROM online_requests').fetchone())
        self.assertFalse(self.db.execute('SELECT 1 FROM online_identities').fetchone())
        self.call('login',email='family@example.invalid')
        self.call('confirm',ticket=self.ticket())
        req=self.db.execute("SELECT * FROM online_requests WHERE state='review'").fetchone()
        self.assertEqual([p['id'] for p in accounts.review_candidates(self.db,req)],[self.f.a])
        with self.assertRaises(ValueError),transaction(self.db):accounts.review(self.db,req['id'],'accept',self.f.d,True,self.now)
        with transaction(self.db):accounts.review(self.db,req['id'],'accept',self.f.a,True,self.now)
        self.assertEqual(self.db.execute('SELECT user_id FROM online_identities').fetchone()[0],self.f.a)

    def test_recovery_ambiguous_independent_contacts_stays_neutral(self):
        email='fictif@example.invalid'
        self.db.execute('UPDATE users SET email=? WHERE id IN (?,?)',(email,self.f.a,self.f.b));self.db.commit()
        self.assertEqual(self.call('recover',email=email),self.call('recover',email='absent@example.invalid'))
        self.assertNotIn('#ofl-account',self.email())
        self.assertFalse(self.db.execute('SELECT 1 FROM online_requests').fetchone())
        self.assertFalse(self.db.execute('SELECT 1 FROM online_identities').fetchone())

    def test_automatic_redirects_an_ambiguous_signup_conditional_queues_it(self):
        self.db.execute("UPDATE users SET email='ines@example.invalid' WHERE id=?",(self.f.a,));self.db.commit()
        for mode in ('automatic','conditional'):
            self.db.execute("UPDATE app_settings SET value=? WHERE key='online_approval'",(mode,));self.db.commit()
            self.signup()
            self.call('confirm',ticket=self.ticket())
            pending=self.db.execute("SELECT count(*) FROM online_requests WHERE state='review'").fetchone()[0]
            self.assertEqual(pending,int(mode=='conditional'))
            self.assertFalse(self.db.execute('SELECT 1 FROM online_identities').fetchone())
            self.assertEqual(self.db.execute("SELECT count(*) FROM users WHERE email='ines@example.invalid'").fetchone()[0],1)
            self.email()

    def test_child_profile_welcome_scope_and_notifications(self):
        from base64 import b64decode
        self.db.execute("UPDATE users SET postal_code='35300',city='Fougères' WHERE id=?",(self.f.a,))
        self.db.commit()
        self.bind(self.f.a)
        common=dict(last_name='Exemple',birth_date='2014-04-04',gender='non_binary',
                    nationality='française',consent=True)
        self.call('child',first_name='Camille',same_address=True,same_contact=True,**common)
        child=self.db.execute("SELECT * FROM users WHERE first_name='Camille'").fetchone()
        self.assertEqual((child['postal_code'],child['city'],child['email'],child['gender'],child['nationality']),
                         ('35300','Fougères','person0@example.invalid','non_binary','France'))
        self.assertEqual(child['created_source'],'online')
        self.assertFalse(accounts.account(self.db,child['id']))
        captured=[]
        self.assertTrue(online_mail.deliver_one(self.db,'fiction',self.now,lambda _,msg:captured.append(msg),self.conf))
        self.assertIn(child['public_id'],captured[0].get_body(preferencelist=('plain',)).get_content())
        self.assertIn('Camille',captured[0].get_body(preferencelist=('plain',)).get_content())
        self.assertEqual(str(captured[0]['To']),'person0@example.invalid')
        self.assertTrue(next(captured[0].iter_attachments()).get_payload(decode=True).startswith(b'\x89PNG'))
        self.assertTrue(self.db.execute('SELECT welcome_sent_at FROM users WHERE id=?',(child['id'],)).fetchone()[0])
        self.assertTrue(b64decode(self.call('qr',person=child['id'])['png']).startswith(b'\x89PNG'))
        with self.assertRaises(ValueError):self.call('qr',person=self.f.other)
        before_count=self.db.execute("SELECT count(*) FROM reservation_discord_events WHERE event_type='online_family_done'").fetchone()[0]
        self.assertEqual(self.db.execute("SELECT count(*) FROM reservation_discord_events WHERE event_type='online_child_created'").fetchone()[0],1)
        with transaction(self.db):
            from family_model import link
            link(self.db,child['id'],self.f.b);link(self.db,child['id'],self.f.b)
        self.assertEqual(self.db.execute("SELECT count(*) FROM reservation_discord_events WHERE event_type='online_family_done'").fetchone()[0],before_count+1)
        self.call('child',first_name='Noémie',postal_code='35000',city='Rennes',
                  email='contact-fictif@example.invalid',phone_country_code='+32',phone='484222333',**common)
        self.assertEqual(tuple(self.db.execute("SELECT postal_code,city,email,phone_country_code FROM users WHERE first_name='Noémie'").fetchone()),
                         ('35000','Rennes','contact-fictif@example.invalid','+32'))
        from family_waitlist import contacts
        self.assertEqual({row['user_id'] for row in contacts(self.db,child['id']) if row['user_id']!=child['id']},{self.f.a,self.f.b})
        self.f.f.login_admin()
        csv=self.f.client.get('/admin/exports/usagers.csv')
        self.assertEqual(csv.status_code,200)
        for field in ('Camille','Noémie','Rennes','35000','France','contact-fictif@example.invalid'):
            self.assertIn(field,csv.text)
    def test_mail_failure_no_activation_and_retry(self):
        self.signup()
        broken=mock.Mock(side_effect=OSError('fictional transport error'))
        self.assertFalse(online_mail.deliver_one(self.db,'fake',self.now,broken,self.conf))
        self.assertFalse(self.db.execute('SELECT 1 FROM online_identities').fetchone())
        self.assertEqual(self.db.execute('SELECT attempts FROM online_mail').fetchone()[0],1)
        self.now+=200
        self.assertEqual(len(self.ticket()),43)

    def test_notification_privacy_failure_defaults_and_volume(self):
        import reservation_notifications as discord
        self.db.execute("UPDATE app_settings SET value='1' WHERE key='discord_notifications_enabled'")
        self.db.commit()
        with transaction(self.db):
            for _ in range(15):accounts.record_creation(self.db,'created','automatic',self.now)
        self.assertEqual(self.db.execute("SELECT count(*) FROM reservation_discord_events WHERE event_type='online_creation_volume'").fetchone()[0],1)
        row=self.db.execute("SELECT * FROM reservation_discord_events WHERE event_type='online_created'").fetchone()
        self.assertEqual(discord.message(self.db,row),discord.ONLINE_LABELS['online_created'])
        sender=mock.Mock(side_effect=OSError('fictitious failure'))
        self.assertEqual(discord.deliver(self.db,'fiction',sender),0)
        self.assertEqual(discord.deliver(self.db,'fiction',sender),0)
        self.assertEqual(sender.call_count,16)
        self.assertEqual(self.db.execute("SELECT count(*) FROM online_events WHERE kind='created'").fetchone()[0],15)
        self.db.execute("INSERT OR REPLACE INTO app_settings VALUES('online_discord_created','0')");self.db.commit()
        with transaction(self.db):accounts.record_creation(self.db,'created','admin',self.now)
        self.assertEqual(self.db.execute("SELECT count(*) FROM reservation_discord_events WHERE event_type='online_created'").fetchone()[0],15)

    def test_family_creation_is_limited_per_authenticated_parent(self):
        self.bind(self.f.a)
        for name in ('Alba','Basile','Cléo','Diane','Emma','Flora'):
            self.call('child',first_name=name,last_name='Exemple',birth_date='2014-06-14',consent=True)
        with self.assertRaisesRegex(ValueError,'Plusieurs demandes'):
            self.call('child',first_name='Gabriel',last_name='Exemple',birth_date='2014-06-14',consent=True)
        self.assertEqual(self.db.execute("SELECT count(*) FROM online_events WHERE kind='child_created'").fetchone()[0],6)

    def test_custom_mail_keeps_link_single_use_and_bound_to_browser(self):
        import reservation_email_templates as templates
        self.db.executemany('INSERT INTO app_settings VALUES(?,?)', [
            (templates.key('online_verify','subject'),'Confirmez chez {structure}'),
            (templates.key('online_verify','body'),'Merci pour votre demande.\n\nL’équipe.'),
        ])
        self.db.commit()
        self.signup()
        captured=[]
        self.assertTrue(online_mail.deliver_one(self.db,'not-a-real-db',self.now,
            lambda _,msg:captured.append(msg),self.conf))
        message=captured[0]
        self.assertIn('Confirmez chez Atelier Exemple',str(message['Subject']))
        plain=message.get_body(preferencelist=('plain',)).get_content()
        html=message.get_body(preferencelist=('html',)).get_content()
        link=re.search(r'https://demo\.example\.invalid/compte/#ofl-account=([\w-]{43})',plain)
        self.assertIsNotNone(link)
        self.assertEqual(plain.count(link[0]),1)
        self.assertEqual(html.count(link[0]),1)
        self.browser='b'*64
        with self.assertRaises(ValueError):self.call('confirm',ticket=link[1])
        self.browser='a'*64
        self.call('confirm',ticket=link[1])
        with self.assertRaises(ValueError):self.call('confirm',ticket=link[1])
    def test_disabled_and_relay_idempotence(self):
        env='production'; data=dict(environment=env,browser=self.browser,client_bucket='f'*64,op='login',email='absent@example.invalid')
        raw=json.dumps(data);msg=dict(type='account',id=secrets.token_hex(24),payload_json=raw,hash=hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(process_action(self.db,msg,env,self.secret),process_action(self.db,msg,env,self.secret))
        self.assertEqual(self.db.execute('SELECT count(*) FROM wordpress_action_receipts').fetchone()[0],1)
        self.db.execute("UPDATE app_settings SET value='0' WHERE key='online_accounts_enabled'");self.db.commit()
        with self.assertRaises(ValueError):self.call('login',email='absent@example.invalid')

    def test_captured_localised_mail_and_verified_recovery(self):
        self.bind(self.f.a)
        self.call('recover',email='person0@example.invalid',lang='fi')
        message=self.email()
        self.assertIn('Vahvista pyyntö',message)
        token=re.search(r'#ofl-account=([\w-]+)',message)[1]
        self.assertNotIn('2001',str(self.call('confirm',ticket=token,lang='fi')))
        identifier=self.email();self.assertIn('2001',identifier);self.assertIn('Päätetunnuksesi',identifier)
        self.call('email',email='new@example.invalid')
        self.assertEqual(self.call('overview')['me']['email'],'person0@example.invalid')
        self.call('confirm',ticket=self.ticket())
        with self.assertRaises(ValueError):self.call('overview')
        self.call('login',email='new@example.invalid');self.call('confirm',ticket=self.ticket())
        self.assertEqual(self.call('overview')['me']['email'],'new@example.invalid')

    def test_review_queue_counter_permissions_and_refusal(self):
        import time
        self.now=int(time.time())
        self.db.execute("UPDATE app_settings SET value='1' WHERE key='online_discord_signup_review'");self.db.commit()
        self.signup()
        self.assertEqual(self.db.execute("SELECT count(*) FROM reservation_discord_events WHERE event_type='online_signup_review'").fetchone()[0],0)
        self.call('confirm',ticket=self.ticket())
        self.assertEqual(self.db.execute("SELECT count(*) FROM reservation_discord_events WHERE event_type='online_signup_review'").fetchone()[0],1)
        rid=self.db.execute("SELECT id FROM online_requests WHERE state='review'").fetchone()[0]
        c=self.f.client;url='/admin/usagers/demandes';counter='/admin/elements-a-traiter.json'
        self.assertNotIn('ines@example.invalid',c.get(url,follow_redirects=True).text)
        with c.session_transaction() as s:s.update(access_role='moderator',admin_authenticated=False)
        self.assertNotIn('ines@example.invalid',c.get(url,follow_redirects=True).text)
        self.assertFalse(any(x['url'].endswith(url) for x in c.get(counter).json['groups']))
        with c.session_transaction() as s:s.clear()
        self.f.f.login_admin()
        response=c.get(url);self.assertIn('ines@example.invalid',response.text)
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertTrue(any(x['url'].endswith(url) for x in c.get(counter).json['groups']))
        self.db.execute("UPDATE app_settings SET value='1' WHERE key='setup_completed'");self.db.commit()
        self.assertIn('Demandes de création de compte',c.get('/admin').text)
        self.assertNotEqual(c.post(url,data=dict(id=rid,decision='refuse')).status_code,200)
        self.assertTrue(self.db.execute('SELECT id FROM online_requests WHERE id=?',(rid,)).fetchone())
        with c.session_transaction() as s:csrf=s['evolution_csrf']
        c.post(url,data=dict(id=rid,decision='refuse',evolution_csrf=csrf),follow_redirects=True)
        self.assertFalse(self.db.execute('SELECT id FROM online_requests WHERE id=?',(rid,)).fetchone())
        self.assertFalse(any(x['url'].endswith(url) for x in c.get(counter).json['groups']))
        self.assertFalse(self.db.execute("SELECT 1 FROM users WHERE email='ines@example.invalid'").fetchone())

    def test_concurrent_confirmation_only_once(self):
        import sqlite3,threading
        self.db.execute("UPDATE app_settings SET value='automatic' WHERE key='online_approval'");self.db.commit()
        self.signup();token=self.ticket();barrier=threading.Barrier(2);results=[]
        def confirm():
            with sqlite3.connect(self.f.f.database_path,timeout=10) as db:
                db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON');barrier.wait()
                try:
                    with transaction(db):accounts.confirm(db,token,self.browser,self.now)
                    results.append('ok')
                except ValueError:results.append('refused')
        threads=[threading.Thread(target=confirm) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join(15)
        self.assertCountEqual(results,['ok','refused'])
        self.assertEqual(self.db.execute("SELECT count(*) FROM users WHERE email='ines@example.invalid'").fetchone()[0],1)

    def test_offer_owner_and_family_scope(self):
        import family_reservations as engine
        import family_waitlist as waiting
        self.db.execute("UPDATE animation_reservation_config SET capacity=2 WHERE service_id=?",(self.f.service,));self.db.commit()
        other=engine.reserve(self.db,self.f.other,[self.f.other],self.f.service,None,secrets.token_hex(24),'production','kiosk')
        self.bind(self.f.a)
        wait=self.call('reserve',participants=[self.f.a,self.f.d],service_id=self.f.service,consent=True)
        self.assertEqual(wait['status'],'waitlisted')
        grp=self.call('overview')['reservations'][0]['cancel']
        with self.assertRaises(ValueError):self.call('cancel',group=other['group_uuid'],consent=True)
        with self.assertRaises(ValueError):self.call('accept_offer',group=grp,consent=True)
        g=self.db.execute('SELECT manage_token FROM family_booking_groups WHERE group_uuid=?',(other['group_uuid'],)).fetchone()
        waiting.respond(self.db,g[0],'cancel')
        self.assertEqual(self.call('accept_offer',group=grp,consent=True)['status'],'confirmed')
        self.assertEqual([r['status'] for r in self.call('overview')['reservations']],['confirmed','confirmed'])
        self.assertEqual(self.call('cancel',group=grp,consent=True)['status'],'cancelled')

