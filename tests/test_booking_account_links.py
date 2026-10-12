"""Verified relay identities and explicit staff attachment of fictitious guests."""
import json,re,secrets,unittest
from tests import test_family_waitlist as fixtures
import outbound_actions as actions
import family_reservations as engine
import family_waitlist as waiting
from booking_account_links import attach

class BookingAccountLinkTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.WaitlistTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db=self.f.db;self.core=self.f.f;self.client=self.f.client
    def guest(self):
        return engine.reserve_guest(self.db,dict(first_name='Camille',last_name='EXEMPLE',birth_date='1990-01-01',email='camille@example.invalid',phone='',consent=True),self.f.service,None,secrets.token_hex(24))
    def row(self,booking):return self.db.execute('SELECT * FROM animation_bookings WHERE group_uuid=?',(booking['group_uuid'],)).fetchone()
    def test_verified_wordpress_family_uses_each_real_account(self):
        secret=b'f'*64
        grant=actions.dispatch(self.db,dict(environment='production',public_id='2001',contact='person0@example.invalid',service_id=self.f.service),'identify','production',secret,secrets.token_hex(24))
        selected=[p['key'] for p in grant['participants'] if p['name'].startswith(('Fictif0 ','Fictif2 '))]
        result=actions.dispatch(self.db,dict(environment='production',token=grant['token'],service_id=self.f.service,participants=selected,consent=True),'reserve','production',secret,secrets.token_hex(24))
        rows=self.db.execute('SELECT user_id,public_id FROM animation_bookings WHERE group_uuid=? ORDER BY user_id',(result['group_uuid'],)).fetchall()
        self.assertEqual([r['user_id'] for r in rows],sorted([self.core.a,self.core.c]))
        self.assertTrue(all(r['public_id'] for r in rows))
    def test_unverified_id_or_wrong_contact_never_links(self):
        self.assertIsNone(engine.matching_account(self.db,'2001','wrong@example.invalid'))
        with self.assertRaises(ValueError):actions.dispatch(self.db,dict(service_id=self.f.service,public_id='2001',participants=['x'],consent=True),'reserve','production',b'f'*64,secrets.token_hex(24))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],0)
    def test_guest_no_account_then_attach_preserves_every_other_column(self):
        booking=self.guest();before=dict(self.row(booking));users=self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        self.assertIsNone(before['user_id'])
        self.assertTrue(attach(self.db,self.f.service,before['external_uuid'],self.core.a,'admin',True))
        after=dict(self.row(booking))
        changed={'user_id','public_id','link_status','verified_at','verified_by_role'}
        self.assertEqual({k:v for k,v in before.items() if k not in changed},{k:v for k,v in after.items() if k not in changed})
        self.assertEqual(after['user_id'],self.core.a)
        self.assertEqual(users,self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM reservation_actions WHERE booking_uuid=?',(before['external_uuid'],)).fetchone()[0],1)
        self.assertFalse(attach(self.db,self.f.service,before['external_uuid'],self.core.a,'admin',True))
    def test_consent_role_csrf_and_explicit_preview(self):
        booking=self.guest();row=self.row(booking);path='/admin/animations/'+str(self.f.service)+'/inscriptions/'+row['external_uuid']+'/compte'
        for role,consent in [('admin',False),('public',True)]:
            with self.assertRaises(ValueError):attach(self.db,self.f.service,row['external_uuid'],self.core.a,role,consent)
        self.assertNotEqual(self.client.get(path).status_code,200)
        self.core.f.login_admin();page=self.client.get(path);self.assertEqual(page.status_code,200)
        self.assertEqual(self.client.post(path,data=dict(person_id=self.core.a,action='attach',consent='1')).status_code,400)
        token=re.search(r'name="evolution_csrf" value="([^"]+)"',page.text)[1]
        preview=self.client.post(path,data=dict(evolution_csrf=token,person_id=self.core.a,action='preview'))
        self.assertIn('Compte choisi',preview.text);self.assertIsNone(self.row(booking)['user_id'])
        with self.client.session_transaction() as session:session['access_role']='moderator';session['admin_authenticated']=True
        response=self.client.post(path,data=dict(evolution_csrf=token,person_id=self.core.a,action='attach',consent='1'))
        self.assertEqual(response.status_code,302);self.assertEqual(self.row(booking)['user_id'],self.core.a)
    def test_wrong_family_inactive_duplicate_and_already_attached_refused(self):
        booking=self.guest();row=self.row(booking)
        with self.assertRaises(ValueError):attach(self.db,self.f.service,row['external_uuid'],self.core.c,'admin',True)
        with self.db:self.db.execute('UPDATE users SET active=0 WHERE id=?',(self.core.a,))
        with self.assertRaises(ValueError):attach(self.db,self.f.service,row['external_uuid'],self.core.a,'admin',True)
        with self.db:self.db.execute('UPDATE users SET active=1 WHERE id=?',(self.core.a,))
        self.f.book([self.core.a])
        with self.assertRaises(ValueError):attach(self.db,self.f.service,row['external_uuid'],self.core.a,'admin',True)
        attach(self.db,self.f.service,row['external_uuid'],self.core.b,'admin',True)
        with self.assertRaises(ValueError):attach(self.db,self.f.service,row['external_uuid'],self.core.teen,'admin',True)
    def test_cancellation_and_waitlist_offer_after_link_use_same_booking(self):
        fills=[self.f.book([p]) for p in (self.core.a,self.core.b,self.core.teen,self.core.older)]
        guest=self.guest();row=self.row(guest)
        self.assertEqual(row['status'],'waitlisted')
        attach(self.db,self.f.service,row['external_uuid'],self.core.other,'moderator',True)
        waiting.respond(self.db,self.f.meta(fills[0])['manage_token'],'cancel')
        self.assertEqual(self.row(guest)['status'],'offer_pending')
        waiting.respond(self.db,self.f.token(guest),'accept')
        self.assertEqual(self.row(guest)['status'],'confirmed')
        waiting.respond(self.db,self.f.meta(guest)['manage_token'],'cancel')
        self.assertEqual(self.row(guest)['status'],'cancelled')
        self.assertEqual(self.row(guest)['external_uuid'],row['external_uuid'])
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])
    def test_unpublished_cancelled_booking_stays_linkable_and_exported(self):
        booking=self.guest();row=self.row(booking)
        waiting.respond(self.db,self.f.meta(booking)['manage_token'],'cancel')
        with self.db:self.db.execute('UPDATE animation_reservation_config SET enabled=0 WHERE service_id=?',(self.f.service,))
        attach(self.db,self.f.service,row['external_uuid'],self.core.a,'admin',True)
        self.assertEqual(self.row(booking)['status'],'cancelled')
        self.core.f.login_admin()
        page=self.client.get('/admin/animations/'+str(self.f.service)+'/inscriptions')
        self.assertIn('Compte rattaché par Administrateur',page.text)
        exported=self.client.get('/admin/animations/'+str(self.f.service)+'/inscriptions.csv')
        self.assertIn(b';Usager;Usager;manual;',exported.data)
        self.assertNotIn(b'Sans compte',exported.data)
