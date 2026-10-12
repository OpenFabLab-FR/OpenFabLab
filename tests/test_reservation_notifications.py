"""Aggregate-only booking notifications, fictional users and simulated sends."""
import secrets
import unittest
from datetime import timedelta
from unittest import mock
from tests import test_family_waitlist as fixtures
import reservation_notifications as discord
import family_waitlist as waiting
from app import write_setting


class ReservationDiscordTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.WaitlistTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db=self.f.db
        write_setting(self.db,'discord_notifications_enabled','1')
        self.db.commit()
        self.sent=[]

    def send(self):
        return discord.deliver(self.db,self.f.f.f.database_path,self.sent.append)

    def count(self,kind):
        return self.db.execute('SELECT COUNT(*) FROM reservation_discord_events WHERE event_type=?',(kind,)).fetchone()[0]

    def test_reservation_every_channel_and_replay(self):
        for source,person in zip(('kiosk','administration','wordpress'),self.f.fill):
            value=self.f.book([person],source=source)
            from family_reservations import reserve
            key=self.db.execute('SELECT request_key FROM family_booking_requests WHERE group_uuid=?',(value['group_uuid'],)).fetchone()[0]
            self.assertEqual(reserve(self.db,person,[person],self.f.service,None,key,source=source,staff=source=='administration'),value)
        self.assertEqual(self.count('new_booking'),3)
        self.assertEqual(self.send(),3);self.assertEqual(self.send(),0)
        self.assertEqual(len(self.sent),3)

    def test_waitlist_proposal_acceptance_cancel_and_full(self):
        full=self.f.full();group=self.f.book([self.f.f.teen])
        self.assertEqual(self.count('waitlist_entry'),1)
        self.assertEqual(self.count('animation_full'),1)
        self.f.cancel(full[0])
        self.assertEqual(self.count('cancellation'),1)
        self.assertEqual(self.count('offer_proposed'),1)
        token=self.f.token(group)
        waiting.respond(self.db,token,'accept',self.f.now)
        waiting.respond(self.db,token,'accept',self.f.now)
        self.assertEqual(self.count('offer_accepted'),1)
        self.send()
        self.assertTrue(any('Place acceptée' in message for message in self.sent))

    def test_invalidated_family_has_single_review_notice(self):
        self.f.full();group=self.f.book([self.f.f.a,self.f.f.c])
        self.db.execute('UPDATE user_family_links SET ended_at=? WHERE member_id=?',
                        (self.f.now.isoformat(),self.f.f.c));self.db.commit()
        waiting.process_due(self.db);waiting.process_due(self.db)
        self.assertEqual(self.count('link_review'),1)
        self.assertEqual(self.f.status(group),'waitlisted')

    def test_mail_failure_is_logged_once_for_retries(self):
        self.f.book([self.f.f.a])
        def fail(_message):
            raise OSError('Fictional transport failure')
        self.f.deliver(fail)
        self.f.deliver(fail,self.f.now+timedelta(hours=2))
        self.assertEqual(self.count('email_error'),1)

    def test_sync_failed_episode_then_recovery(self):
        with self.db:
            discord.sync_episode(self.db,'production','poll',True)
            discord.sync_episode(self.db,'production','poll',True)
        self.assertEqual(self.count('sync_error'),1)
        with self.db:
            discord.sync_episode(self.db,'production','poll',False)
            discord.sync_episode(self.db,'production','poll',True)
        self.assertEqual(self.count('sync_error'),2)

    def test_rollback_never_leaves_notification(self):
        from outbound_actions import transaction
        with self.assertRaises(RuntimeError):
            with transaction(self.db):
                discord.queue(self.db,'rollback','new_booking',self.f.service)
                raise RuntimeError('Injected rollback')
        self.assertEqual(self.count('new_booking'),0)

    def test_no_send_inside_uncommitted_business_transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        discord.queue(self.db,'uncommitted','new_booking',self.f.service)
        self.assertEqual(self.send(),0);self.assertEqual(self.sent,[])
        self.db.commit();self.assertEqual(self.send(),1)

    def test_all_existing_flags_are_respected(self):
        for kind in discord.LABELS:
            with self.db:
                write_setting(self.db,'discord_reservation_'+kind,'0')
                discord.queue(self.db,'disabled/'+kind,kind,self.f.service)
            self.assertEqual(self.send(),0)
        self.assertEqual(self.sent,[])

    def test_no_personal_data_in_any_message_or_outbox(self):
        for kind in discord.LABELS:
            with self.db:
                discord.queue(self.db,'private-key/'+kind,kind,self.f.service)
        self.send()
        content='\n'.join(self.sent)+str([tuple(r) for r in self.db.execute('SELECT * FROM reservation_discord_events')])
        for private in ('person0@example.invalid','Fictif0','2001','0600000000','private-key','http'):
            self.assertNotIn(private,content)

    def test_test_environment_never_sends_real_or_simulated_notice(self):
        with self.db:
            discord.queue(self.db,'test-only','new_booking',self.f.service,'test')
        self.assertEqual(self.send(),0)
        self.assertEqual(self.db.execute('SELECT state FROM reservation_discord_events').fetchone()[0],'skipped')

    def test_lost_discord_ack_is_not_resent(self):
        with self.db:
            discord.queue(self.db,'lost-ack','new_booking',self.f.service)
        calls=[]
        def uncertain(message):
            calls.append(message)
            raise TimeoutError('Simulated lost acknowledgment')
        self.assertEqual(discord.deliver(self.db,self.f.f.f.database_path,uncertain),0)
        self.assertEqual(self.send(),0)
        self.assertEqual(len(calls),1)
        self.assertEqual(self.db.execute('SELECT state FROM reservation_discord_events').fetchone()[0],'uncertain')

    def test_restart_after_claim_never_replays_ambiguous_send(self):
        with self.db:
            discord.queue(self.db,'restart','new_booking',self.f.service)
            self.db.execute("UPDATE reservation_discord_events SET state='sending',claimed_at=?",((self.f.now-timedelta(hours=1)).isoformat(),))
        self.assertEqual(self.send(),0)
        self.assertEqual(self.db.execute('SELECT state FROM reservation_discord_events').fetchone()[0],'uncertain')


class PublicCommuneTests(unittest.TestCase):
    def setUp(self):
        from tests.test_enrollment_privacy import EnrollmentPrivacyTests
        self.f=EnrollmentPrivacyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db,self.client=self.f.db,self.f.client

    def test_public_and_staff_forms_use_same_javascript(self):
        page=self.client.get('/inscription')
        self.assertIn('data-postal-code',page.text)
        self.assertIn('data-city-suggestion-status',page.text)
        self.assertIn('/api/communes',page.text)
        self.f.f.f.login_admin()
        self.assertIn('data-postal-code',self.f.f.f.client.get('/admin/usagers/nouveau').text)

    def test_fougeres_lookup_is_shared_and_has_no_account_data(self):
        # The route captured the existing loader; intercept only its transport.
        import app
        with mock.patch.object(app,'COMMUNE_CACHE',{'35300':{'communes':['Fougères'],'available':True,'expires_at':__import__('time').monotonic()+3600}}):
            with mock.patch('urllib.request.urlopen') as transport:
                import json
                transport.return_value.__enter__.return_value.read.return_value=json.dumps([{'nom':'Fougères'}]).encode()
                response=self.client.get('/api/communes?code_postal=35300')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['communes'],['Fougères'])
        self.assertEqual(set(response.json),{'communes','available'})

    def test_invalid_and_foreign_code_has_manual_fallback(self):
        for code in ('SW1A 1AA','999','<script>',''):
            self.assertEqual(self.client.get('/api/communes',query_string={'code_postal':code}).json,dict(communes=[],available=True))

    def test_closed_enrollment_keeps_public_lookup_closed(self):
        with self.db:
            write_setting(self.db,'self_enrollment_enabled','0')
        self.assertEqual(self.client.get('/api/communes?code_postal=35300').status_code,404)

    def test_public_lookup_has_bounded_rate(self):
        with mock.patch('urllib.request.urlopen',side_effect=OSError('Simulated offline reference')):
            for _ in range(30):
                self.assertEqual(self.client.get('/api/communes?code_postal=99999').status_code,200)
            self.assertEqual(self.client.get('/api/communes?code_postal=99999').status_code,429)
