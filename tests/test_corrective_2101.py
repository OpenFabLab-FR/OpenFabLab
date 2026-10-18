"""Slot presentation and sound preferences; fabricated data, simulated transports."""
import json
import secrets
import unittest
from unittest.mock import patch
from tests import test_families as family_fixture
from tests import test_memberships_210 as sound_fixture
import family_reservations as engine
import family_waitlist as waiting
import reservation_notifications as discord
from animation_slots import save_slots
from outbound_actions import public_catalogue
from app import write_setting, create_app


class SlotPresentationTests(unittest.TestCase):
    def setUp(self):
        self.f=family_fixture.FamilyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db=self.f.db
        with self.db:
            self.db.execute("UPDATE fablab_services SET end_time='13:00' WHERE id=?",(self.f.service,))
            self.db.execute("UPDATE animation_reservation_config SET booking_mode='slots',slot_duration_minutes=30,slot_gap_minutes=0,slot_capacity=1 WHERE service_id=?",(self.f.service,))
            service=self.db.execute('SELECT * FROM fablab_services WHERE id=?',(self.f.service,)).fetchone()
            config=self.db.execute('SELECT * FROM animation_reservation_config WHERE service_id=?',(self.f.service,)).fetchone()
            self.slots=save_slots(self.db,service,config,'Europe/Paris')
            write_setting(self.db,'discord_notifications_enabled','1')
            write_setting(self.db,'reservation_waitlist_limit_mode','automatic')
        self.slot=self.slots[0]['slot_uuid']
    def book(self,person,slot=None):
        return engine.reserve(self.db,person,[person],self.f.service,slot or self.slot,secrets.token_urlsafe(32),source='wordpress')
    def catalogue(self):return public_catalogue(self.db,'production',True,True)[0]
    def test_six_independent_slots_and_no_catalogue_write(self):
        self.book(self.f.a);self.book(self.f.b);self.book(self.f.teen,self.slots[1]['slot_uuid'])
        before=self.db.total_changes;item=self.catalogue();self.assertEqual(self.db.total_changes,before)
        self.assertEqual(item['available'],4)
        self.assertEqual([slot['availability_state'] for slot in item['slots']],['waiting_full','waiting']+['available']*4)
        self.assertEqual((item['slots'][0]['waiting'],item['slots'][0]['waiting_limit']),(1,1))
    def test_saturated_slot_does_not_block_other_slots(self):
        self.book(self.f.a);self.book(self.f.b)
        with self.assertRaises(ValueError):self.book(self.f.other)
        self.assertEqual(self.book(self.f.other,self.slots[2]['slot_uuid'])['status'],'confirmed')
    def test_guest_slot_real_reservation_replay_and_cancellation_without_new_account(self):
        before=self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        data=dict(first_name='Invité',last_name='FICTIF',birth_date='1990-01-01',email='guest@example.invalid',phone='')
        key=secrets.token_urlsafe(32)
        value=engine.reserve_guest(self.db,data,self.f.service,self.slot,key)
        self.assertEqual(value['status'],'confirmed')
        self.assertEqual(engine.reserve_guest(self.db,data,self.f.service,self.slot,key),value)
        group=self.db.execute('SELECT * FROM family_booking_groups WHERE group_uuid=?',(value['group_uuid'],)).fetchone()
        self.assertIsNone(group['owner_id']);waiting.respond(self.db,group['manage_token'],'cancel')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],before)
        rows=self.db.execute("SELECT * FROM reservation_discord_events WHERE event_type IN ('new_booking','cancellation')").fetchall()
        self.assertEqual(len(rows),2)
        self.assertTrue(all('Créneau : 10:00–10:30' in discord.message(self.db,row) for row in rows))
    def test_simultaneous_distinct_requests_one_confirmed_one_waiting_per_slot(self):
        import sqlite3,threading
        barrier=threading.Barrier(2);results=[];errors=[]
        def submit(person):
            db=sqlite3.connect(self.f.f.database_path,timeout=10);db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
            try:
                barrier.wait();results.append(engine.reserve(db,person,[person],self.f.service,self.slot,secrets.token_urlsafe(32),source='wordpress')['status'])
            except Exception as error:errors.append(type(error).__name__)
            finally:db.close()
        threads=[threading.Thread(target=submit,args=(person,)) for person in (self.f.a,self.f.b)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(errors,[]);self.assertCountEqual(results,['confirmed','waitlisted'])
        self.assertEqual(self.catalogue()['slots'][0]['availability_state'],'waiting_full')
        self.assertEqual(self.catalogue()['slots'][1]['availability_state'],'available')
    def test_partial_family_cancellation_keeps_scope_and_real_released_places(self):
        with self.db:self.db.execute('UPDATE animation_slots SET capacity=2 WHERE slot_uuid=?',(self.slot,))
        value=self.f.book([self.f.a,self.f.c],slot=self.slot)
        booking=self.db.execute('SELECT external_uuid FROM animation_bookings WHERE group_uuid=? AND user_id=?',(value['group_uuid'],self.f.c)).fetchone()[0]
        engine.team_action(self.db,self.f.service,booking,'remove','admin')
        row=self.db.execute("SELECT * FROM reservation_discord_events WHERE event_type='cancellation'").fetchone()
        text=discord.message(self.db,row)
        for expected in ['annulation partielle','Créneau : 10:00–10:30','Participants concernés : 1','Places libérées : 1']:self.assertIn(expected,text)
    def test_families_never_split_or_overfill_queue(self):
        with self.assertRaises(ValueError):self.f.book([self.f.a,self.f.c],slot=self.slot)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],0)
    def test_deferred_full_notice_keeps_exact_scope_after_schedule_change(self):
        self.book(self.f.a);self.book(self.f.b)
        row=self.db.execute("SELECT * FROM reservation_discord_events WHERE event_type='waitlist_full'").fetchone()
        snapshot=json.loads(row['presentation_json']);self.assertEqual(snapshot['slot_uuid'],self.slot)
        with self.db:self.db.execute("UPDATE animation_slots SET starts_at=ends_at WHERE slot_uuid=?",(self.slot,))
        text=discord.message(self.db,row)
        for expected in ['Créneau : 10:00–10:30','Participants confirmés : 1/1','Liste d’attente : 1/1','pour ce créneau.']:self.assertIn(expected,text)
        self.assertNotIn('10:00–13:00',text);self.assertNotIn('Réservant',text)
    def test_booking_waiting_offer_accept_cancel_exact_hours_and_no_duplicates(self):
        first=self.book(self.f.a);second=self.book(self.f.b)
        group=self.db.execute('SELECT * FROM family_booking_groups WHERE group_uuid=?',(first['group_uuid'],)).fetchone()
        waiting.respond(self.db,group['manage_token'],'cancel')
        group=self.db.execute('SELECT * FROM family_booking_groups WHERE group_uuid=?',(second['group_uuid'],)).fetchone()
        # The durable mail carries the actual offer token; no inference from names.
        mail=json.loads(self.db.execute("SELECT payload_json FROM family_booking_emails WHERE group_uuid=? AND kind='offer_pending'",(second['group_uuid'],)).fetchone()[0])
        waiting.respond(self.db,mail['token'],'accept')
        sent=[];discord.deliver(self.db,self.f.f.database_path,sent.append);discord.deliver(self.db,self.f.f.database_path,sent.append)
        for event in ['Nouvelle réservation','Nouvelle entrée','Place proposée','Place acceptée','Réservation annulée','Créneau complet']:
            texts=[text for text in sent if text.startswith(event)];self.assertTrue(texts,event)
            self.assertTrue(all('Créneau : 10:00–10:30' in text and '10:00–13:00' not in text for text in texts))
        self.assertEqual(len(sent),self.db.execute("SELECT COUNT(*) FROM reservation_discord_events WHERE state='sent'").fetchone()[0])
    def test_global_animation_retains_global_hours(self):
        with self.db:self.db.execute("UPDATE animation_reservation_config SET booking_mode='whole' WHERE service_id=?",(self.f.service,))
        value=engine.reserve(self.db,self.f.a,[self.f.a],self.f.service,None,secrets.token_urlsafe(32))
        row=self.db.execute("SELECT * FROM reservation_discord_events WHERE event_type='new_booking'").fetchone()
        self.assertIn('de 10h à 13h',discord.message(self.db,row));self.assertNotIn('Créneau :',discord.message(self.db,row))
    def test_scope_validation_rejects_private_or_untrusted_fields(self):
        for scope in [{'slot_uuid':self.slot,'date':self.f.day,'hours':'10:00–10:30','email':'no@example.invalid'},
                      {'slot_uuid':'not-a-slot','date':self.f.day,'hours':'10:00–10:30'},
                      {'slot_uuid':self.slot,'date':self.f.day,'hours':'secret@example.invalid'}]:
            with self.assertRaises(ValueError):discord.queue(self.db,secrets.token_hex(8),'waitlist_full',self.f.service,presentation=scope)
            self.db.rollback()
    def test_old_pending_saturation_does_not_claim_global_hours_as_slot(self):
        self.book(self.f.a);self.book(self.f.b)
        with self.db:
            self.db.execute("UPDATE reservation_discord_events SET presentation_json=? WHERE event_type='waitlist_full'",(json.dumps(dict(capacity=1,occupied=1,confirmed=1,waiting=1,waiting_limit=1)),))
        row=self.db.execute("SELECT * FROM reservation_discord_events WHERE event_type='waitlist_full'").fetchone()
        text=discord.message(self.db,row)
        self.assertIn('ancienne notification',text);self.assertNotIn('13h',text);self.assertNotIn('10:00–13:00',text)


class SoundPreferencesTests(unittest.TestCase):
    setUp=sound_fixture.MembershipTest.setUp;tearDown=sound_fixture.MembershipTest.tearDown
    database=sound_fixture.MembershipTest.database;set=sound_fixture.MembershipTest.set
    login_admin=sound_fixture.MembershipTest.login_admin;_login_token=sound_fixture.MembershipTest._login_token
    def test_schema_and_new_default_only(self):
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],21)
        self.assertEqual(self.db.execute("SELECT value FROM app_settings WHERE key='kiosk_sound_countdown'").fetchone()[0],'1')
        self.assertEqual(self.db.execute("SELECT value FROM app_settings WHERE key='module_memberships'").fetchone()[0],'0')
    def test_all_ambiences_profile_roundtrip(self):
        from profile_archive import build_profile,parse_profile
        for ambience in ['auto','classic','halloween','christmas','summer','steampunk']:
            values=dict(kiosk_sound_enabled='0',kiosk_sound_countdown='0',kiosk_sound_volume='37',kiosk_sound_ambience=ambience)
            self.assertEqual(parse_profile(build_profile(values,[],{}))['settings'],values)
    def test_real_sound_form_saves_new_checkbox_and_themes(self):
        import re
        self.login_admin()
        for ambience,enabled,countdown in [('summer',True,True),('steampunk',True,False),('auto',False,True)]:
            html=self.client.get('/admin/reglages/borne').get_data(as_text=True)
            token=re.search(r'name="evolution_csrf" value="([^"]+)"',html)[1]
            data=dict(evolution_csrf=token,kiosk_sound_volume='37',kiosk_sound_ambience=ambience)
            if enabled:data['kiosk_sound_enabled']='1'
            if countdown:data['kiosk_sound_countdown']='1'
            response=self.client.post('/admin/reglages/2-10/sound',data=data)
            self.assertEqual(response.status_code,302)
            values=dict(self.db.execute("SELECT key,value FROM app_settings WHERE key LIKE 'kiosk_sound_%'"))
            self.assertEqual((values['kiosk_sound_enabled'],values['kiosk_sound_countdown'],values['kiosk_sound_volume'],values['kiosk_sound_ambience']),('1' if enabled else '0','1' if countdown else '0','37',ambience))
    def test_theme_auto_reuses_existing_resolver(self):
        import re
        self.set(kiosk_sound_ambience='auto')
        for theme in ['classic','halloween','christmas','summer','steampunk','unknown']:
            self.set(home_theme=theme)
            config=json.loads(re.search(r'id="kiosk-audio">(.*?)</script>',self.client.get('/').get_data(as_text=True))[1])
            self.assertEqual(config['ambience'],theme if theme!='unknown' else 'classic')
    def test_existing_off_custom_volume_and_countdown_survive_restart(self):
        self.set(kiosk_sound_enabled='0',kiosk_sound_volume='37',kiosk_sound_countdown='0',module_memberships='0')
        schema=[tuple(row) for row in self.db.execute('SELECT name,sql FROM sqlite_master ORDER BY name')]
        create_app(dict(TESTING=True,DATABASE=self.database_path,SECRET_KEY='fictional-only',SEED_DEMO_USERS=False,WEATHER_ENABLED=False,AUTO_CLOSURE_WORKER=False))
        self.assertEqual([tuple(row) for row in self.db.execute('SELECT name,sql FROM sqlite_master ORDER BY name')],schema)
        self.assertEqual(dict(self.db.execute("SELECT key,value FROM app_settings WHERE key IN ('kiosk_sound_enabled','kiosk_sound_volume','kiosk_sound_countdown','module_memberships')")),dict(kiosk_sound_enabled='0',kiosk_sound_volume='37',kiosk_sound_countdown='0',module_memberships='0'))
