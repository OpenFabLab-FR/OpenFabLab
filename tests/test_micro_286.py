"""Fictional micro-release cases. Discord is a captured sender, never a webhook."""
import json,re,secrets,unittest
from unittest.mock import patch
from tests import test_reservation_notifications as notification_fixtures
from tests import test_families as family_fixtures
from app import write_setting
import reservation_notifications as notices
import family_reservations as engine
import family_waitlist as waiting
import profile_archive as profile
from participant_search import search_users


class NotificationPresentationTests(unittest.TestCase):
    def setUp(self):
        self.fixture=notification_fixtures.ReservationDiscordTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.f=self.fixture.f;self.db=self.fixture.db;self.sent=[]
        self.db.execute('UPDATE users SET first_name=?,last_name=? WHERE id=?',('Camille','EXEMPLE',self.f.f.a))
        self.db.execute('UPDATE users SET first_name=?,last_name=? WHERE id=?',('Alex','FICTIF',self.f.f.b))
        self.db.execute('UPDATE fablab_services SET title=? WHERE id=?',('Atelier de broderie fictif',self.f.service));self.db.commit()
    def options(self,**values):
        with self.db:
            for key,value in values.items():write_setting(self.db,'discord_reservation_detail_'+key,'1' if value else '0')
    def send(self):notices.deliver(self.db,self.f.f.f.database_path,self.sent.append);return '\n'.join(self.sent)
    def test_default_title_date_count_no_name_and_no_new_schema(self):
        self.f.book([self.f.f.a],source='wordpress');text=self.send()
        self.assertIn('Animation : Atelier de broderie fictif',text);self.assertIn('Date :',text)
        self.assertIn('de 10h à 12h',text);self.assertIn('Participants : 1',text);self.assertIn('Places restantes : 3',text)
        for secret in ('Camille','EXEMPLE','person0@','060000','2001','http','token'):self.assertNotIn(secret,text)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],21)
    def test_first_name_only_initial_and_full_name_are_independent(self):
        self.f.book([self.f.f.a]);row=self.db.execute("SELECT * FROM reservation_discord_events WHERE event_type='new_booking'").fetchone()
        for options,expected,absent in [({'first_name':1},'Réservant : Camille','EXEMPLE'),({'first_name':1,'last_initial':1},'Réservant : Camille E.','EXEMPLE'),({'first_name':1,'last_initial':1,'last_name':1},'Réservant : Camille EXEMPLE','Camille E.')]:
            self.options(**options);text=notices.message(self.db,row);self.assertIn(expected,text);self.assertNotIn(absent,text)
        self.options(first_name=0,last_name=0,last_initial=0);self.assertNotIn('Réservant',notices.message(self.db,row))
    def test_booker_is_not_replaced_by_first_participant(self):
        self.options(first_name=1,last_name=1)
        self.f.book([self.f.f.b],owner=self.f.f.a,source='administration')
        text=self.send();self.assertIn('Réservant : Camille EXEMPLE',text);self.assertNotIn('Réservant : Alex',text)
    def test_family_count_children_not_leaked_and_no_personal_outbox(self):
        self.options(first_name=1,last_initial=1)
        self.f.book([self.f.f.a,self.f.f.c]);text=self.send()
        self.assertIn('Participants : 2',text);self.assertIn('Réservant : Camille E.',text)
        self.assertNotIn('Fictif2',text)
        raw=str([tuple(row) for row in self.db.execute('SELECT * FROM reservation_discord_events')])
        for value in ('Camille','EXEMPLE','person0@','2001'):self.assertNotIn(value,raw)
        payload=json.loads(self.db.execute('SELECT payload_json FROM family_booking_emails').fetchone()[0])['_discord']
        self.assertEqual(set(payload),{'participants','capacity','occupied'})
    def test_guest_identity_from_own_booking_no_account_created(self):
        self.options(first_name=1,last_initial=1)
        count=self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        booking=engine.reserve_guest(self.db,dict(first_name='Noa',last_name='FICTIF',birth_date='1990-01-01',email='noa@example.invalid',phone=''),self.f.service,None,secrets.token_hex(24))
        self.assertEqual(count,self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0])
        self.assertIn('Réservant : Noa F.',self.send());self.sent.clear()
        self.f.cancel(booking);text=self.send();self.assertIn('Réservant : Noa F.',text);self.assertIn('Places libérées : 1',text)
        self.assertNotIn('noa@example.invalid',text)
    def test_complete_and_partial_cancellation_actual_seats_unchanged(self):
        booking=self.f.book([self.f.f.a,self.f.f.b],source='administration');self.send();self.sent.clear()
        person=self.db.execute('SELECT external_uuid FROM animation_bookings WHERE group_uuid=? AND user_id=?',(booking['group_uuid'],self.f.f.b)).fetchone()[0]
        engine.team_action(self.db,self.f.service,person,'remove','admin')
        text=self.send();self.assertIn('annulation partielle',text);self.assertIn('Places libérées : 1',text)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM animation_bookings WHERE group_uuid=? AND status='confirmed'",(booking['group_uuid'],)).fetchone()[0],1)
        self.assertEqual(self.f.status(booking),'confirmed');self.sent.clear()
        self.f.cancel(booking);text=self.send();self.assertNotIn('annulation partielle',text);self.assertIn('Places libérées : 1',text)
    def test_waitlist_cancel_does_not_invent_freed_seats(self):
        self.f.full();booking=self.f.book([self.f.f.a,self.f.f.c]);self.send();self.sent.clear()
        self.f.cancel(booking);text=self.send();self.assertIn('Participants concernés : 2',text);self.assertIn('Places libérées : 0',text)
    def test_full_animation_is_aggregate_even_when_names_enabled(self):
        self.options(first_name=1,last_name=1);self.f.full()
        row=self.db.execute("SELECT * FROM reservation_discord_events WHERE event_type='animation_full'").fetchone()
        # The message describes reaching capacity, not a later state of the queue.
        value=notices.message(self.db,row);self.assertIn('Capacité atteinte : 4/4',value);self.assertNotIn('Réservant',value)
    def test_technical_errors_no_name_title_date_or_link(self):
        self.options(first_name=1,last_name=1)
        for kind in ('email_error','sync_error'):
            with self.db:notices.queue(self.db,'technical/'+kind,kind,self.f.service)
        text=self.send();self.assertNotIn('Camille',text);self.assertNotIn('Atelier de broderie',text)
        self.assertNotIn('Date :',text);self.assertNotIn('http',text)
    def test_disabled_fields_and_custom_label_no_variable_bypass(self):
        self.options(title=0,date=0,participants=0,remaining=0)
        with self.db:write_setting(self.db,'discord_reservation_message_new_booking','Une nouvelle demande confirmée')
        self.f.book([self.f.f.a]);self.assertEqual(self.send(),'Une nouvelle demande confirmée')
        for bad in ('{reservant}','@everyone','https://example.invalid','two\nlines','x'*151):
            with self.subTest(value=bad),self.assertRaises(ValueError):notices.validate_label(bad,'new_booking')
    def test_profile_round_trip_flags_labels_and_reject_invalid_booleans(self):
        settings={'discord_reservation_detail_first_name':'1','discord_reservation_detail_last_initial':'1','discord_reservation_message_cancellation':'Une inscription annulée'}
        self.assertEqual(profile.parse_profile(profile.build_profile(settings,[],{}))['settings'],settings)
        with self.assertRaises(ValueError):profile.parse_profile(profile.build_profile({'discord_reservation_detail_title':'yes'},[],{}))
        with self.assertRaises(ValueError):profile.parse_profile(profile.build_profile({'discord_reservation_message_cancellation':'{token}'},[],{}))
    def test_date_format_missing_values_and_legacy_event_remain_safe(self):
        self.assertEqual(notices.readable_date('2026-10-23','10:00–12:00'),'23 octobre 2026, de 10h à 12h')
        self.assertEqual(notices.readable_date('bad',''), '')
        with self.db:notices.queue(self.db,'historical-unknown','new_booking')
        self.assertEqual(self.send(),'Nouvelle réservation enregistrée')
    def test_removed_account_does_not_guess_identity_from_name(self):
        self.options(first_name=1,last_name=1);booking=self.f.book([self.f.f.a])
        # An owner no longer available must not be guessed from other accounts.
        self.db.execute('UPDATE family_booking_groups SET owner_id=NULL WHERE group_uuid=?',(booking['group_uuid'],));self.db.commit()
        self.assertNotIn('Réservant :',self.send())
    def test_settings_saved_and_restart_preserves_older_flags_and_preferences(self):
        import app
        self.f.f.f.login_admin();client=self.f.client
        page=client.get('/admin/reglages/notifications')
        self.assertEqual(page.status_code,200)
        token=re.search(r'name="evolution_csrf" value="([^"]+)"',page.text)[1]
        form={'evolution_csrf':token,'enabled':'1','reservation_presentation_present':'1','reservation_detail_title':'1','reservation_detail_date':'1','reservation_detail_first_name':'1','reservation_detail_last_initial':'1','reservation_detail_participants':'1','reservation_detail_remaining':'1','reservation_new_booking':'1','reservation_cancellation':'1','reservation_message_new_booking':'Une inscription reçue','bot_name':'Atelier fictif'}
        with patch.object(app,'read_discord_webhook',return_value='SIMULATED-NOT-A-WEBHOOK'):
            response=client.post('/admin/reglages/notifications',data=form)
        self.assertEqual(response.status_code,302)
        values=notices.presentation(self.db);self.assertTrue(values['details']['first_name']);self.assertTrue(values['details']['last_initial']);self.assertFalse(values['details']['last_name'])
        self.assertEqual(values['messages']['new_booking'],'Une inscription reçue')
        self.assertEqual(notices.setting(self.db,'discord_reservation_offer_proposed'),'0')
        with self.f.f.f.app.app_context():app.initialize_database()
        self.assertEqual(notices.presentation(self.db),values)
        self.assertEqual(notices.setting(self.db,'discord_reservation_offer_proposed'),'0')
    def test_new_user_identity_flags_cannot_enable_reservation_names(self):
        with self.db:
            for key in ('enabled','first_name','last_name','last_initial'):write_setting(self.db,'discord_new_user_'+key,'1')
        self.f.book([self.f.f.a]);self.assertNotIn('Réservant',self.send())


class CompactSearchTests(unittest.TestCase):
    def setUp(self):
        self.f=family_fixtures.FamilyTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.db=self.f.db
    def test_empty_query_performs_no_directory_operation(self):
        class NoQueries:
            def __getattr__(self,name):raise AssertionError('Empty search must not touch directory: '+name)
        for value in ('',' ','\t',None):self.assertEqual(search_users(NoQueries(),value),dict(users=[],more=False))
    def test_partial_first_last_accents_case_code_and_no_match(self):
        with self.db:self.db.execute('UPDATE users SET first_name=?,last_name=? WHERE id=?',('Élodie','DÉMONSTRATION',self.f.a))
        for query in ('elo','ELO','demonstr','DÉMON','2001'):
            self.assertIn(self.f.a,[row['id'] for row in search_users(self.db,query)['users']])
        self.assertEqual(search_users(self.db,'NotARealPerson')['users'],[])
    def test_staff_only_no_store_and_bounded_results(self):
        endpoint='/admin/api/participants'
        self.assertNotEqual(self.f.client.get(endpoint+'?q=Fictif').status_code,200)
        self.f.f.login_admin()
        for n in range(40):
            self.db.execute("INSERT INTO users(public_id,first_name,last_name,active,category,created_at) VALUES(?,?,?,1,'user','2026-10-12')",(str(7000+n),'Commun'+str(n),'EXEMPLE'))
        self.db.commit();response=self.f.client.get(endpoint+'?q=Commun')
        self.assertEqual(response.status_code,200);self.assertEqual(len(response.json['users']),25);self.assertTrue(response.json['more'])
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertEqual(self.f.client.get(endpoint+'?q=').json,dict(users=[],more=False))
    def test_both_picker_templates_empty_without_losing_booked_people(self):
        booking=self.f.book([self.f.a,self.f.b]);self.f.f.login_admin()
        page=self.f.client.get('/admin/animations/'+str(self.f.service)+'/inscriptions')
        self.assertEqual(page.status_code,200)
        self.assertGreaterEqual(page.text.count('Saisissez un prénom, un nom ou un identifiant pour rechercher un usager.'),2)
        self.assertNotIn('Jusqu’à 25 résultats',page.text)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings WHERE group_uuid=?',(booking['group_uuid'],)).fetchone()[0],2)
