"""Fictitious identities only. No SMTP/Discord/WordPress transport."""
import os
import json
import re
import sqlite3
import unittest
from datetime import date,datetime,timedelta,timezone
from unittest.mock import patch
from tests import test_app as fixtures
import memberships as m
from app import record_user_presence,record_quick_departure


class MembershipTest(unittest.TestCase):
    database=fixtures.OpenFabLabTestCase.database
    login_admin=fixtures.OpenFabLabTestCase.login_admin
    _login_token=fixtures.OpenFabLabTestCase._login_token
    tearDown=fixtures.OpenFabLabTestCase.tearDown
    def setUp(self):
        isolated=patch.dict(os.environ,{'OPENFABLAB_EXTERNAL_ACTIONS':'0'})
        isolated.start();self.addCleanup(isolated.stop)
        fixtures.OpenFabLabTestCase.setUp(self)
        self.db=self.database();self.db.execute('PRAGMA foreign_keys=ON')
        category=self.db.execute('SELECT category_key FROM user_categories WHERE is_default=1').fetchone()[0]
        self.db.execute("INSERT INTO users(first_name,last_name,public_id,category,created_at,active) VALUES('Camille','FICTIF','0101',?,?,1)",(category,m.stamp()))
        self.user=self.db.execute('SELECT last_insert_rowid()').fetchone()[0]
        self.db.execute("INSERT INTO users(first_name,last_name,public_id,category,created_at,active) VALUES('Alex','EXEMPLE','0102',?,?,1)",(category,m.stamp()))
        self.other=self.db.execute('SELECT last_insert_rowid()').fetchone()[0]
        self.db.commit()
        self.addCleanup(self.db.close)
    def set(self,**values):
        with self.db:self.db.executemany('INSERT INTO app_settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',values.items())
    def plan(self,**values):
        return m.save_plan(self.db,dict({'name':'Formule fictive','kind':'credits','scope':'individual','unit':'passage','quantity':'10','validity_unit':'years','validity_value':'1'},**values))
    def grant(self,plan=None,start='2026-01-01',key='assign'):
        return m.assign(self.db,plan or self.plan(),self.user,[self.user],start,key)
    def test_defaults_and_no_side_effect_off(self):
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],21)
        self.assertEqual(m.setting(self.db,'module_memberships'),'0')
        self.assertEqual(m.setting(self.db,'kiosk_sound_enabled'),'1')
        self.assertEqual(m.setting(self.db,'kiosk_sound_volume'),'50')
        record_user_presence(self.db,self.user);record_quick_departure(self.db,self.user)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM membership_ledger').fetchone()[0],0)
    def test_dates_and_terms_snapshot(self):
        for start,unit,expected in [('2024-02-29','years','2025-02-28'),('2026-01-31','months','2026-02-28'),('2026-10-17','days','2026-10-17')]:
            with self.subTest(start=start,unit=unit):self.assertEqual(str(m.end_date(start,dict(validity_unit=unit,validity_value=1))),expected)
        plan=self.plan();grant=self.grant(plan)
        m.save_plan(self.db,dict(name='Autre prix',kind='credits',scope='individual',unit='passage',quantity=99),plan)
        self.assertEqual(json.loads(self.db.execute('SELECT terms_json FROM membership_grants WHERE grant_id=?',(grant,)).fetchone()[0])['quantity'],10)
    def test_assignment_retry_and_recharge(self):
        plan=self.plan();first=self.grant(plan);self.assertEqual(self.grant(plan),first)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM membership_grants').fetchone()[0],1)
        for _ in range(2):m.adjust(self.db,first,'3','recharge','recharge-1','Recharge fictive')
        self.assertEqual(self.db.execute('SELECT balance FROM membership_grants').fetchone()[0],13)
        with self.assertRaises(ValueError):m.adjust(self.db,first,'4','recharge','recharge-1','Recharge fictive')
        with self.assertRaises(ValueError):m.adjust(self.db,first,'-99','correction','negative','Erreur')
        self.assertEqual(self.db.execute('SELECT balance FROM membership_grants').fetchone()[0],13)
    def test_passage_return_no_double_charge(self):
        grant=self.grant(start=date.today().isoformat());self.set(module_memberships='1')
        record_user_presence(self.db,self.user);record_quick_departure(self.db,self.user);record_user_presence(self.db,self.user)
        self.assertEqual(self.db.execute('SELECT balance FROM membership_grants').fetchone()[0],9)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM membership_ledger WHERE kind='consumption'").fetchone()[0],1)
    def test_hours_shortage_and_review(self):
        plan=self.plan(unit='hour',quantity='1');grant=self.grant(plan,start=date.today().isoformat());self.set(module_memberships='1')
        record_user_presence(self.db,self.user)
        session=self.db.execute('SELECT id FROM sessions WHERE user_id=?',(self.user,)).fetchone()[0]
        now=datetime.now(timezone.utc)
        with self.db:self.db.execute('UPDATE sessions SET check_in=?,check_out=?,exit_method=? WHERE id=?',((now-timedelta(hours=2)).isoformat(),now.isoformat(),'id',session))
        with m.atomic(self.db):m.on_exit(self.db,session)
        row=self.db.execute('SELECT * FROM membership_consumptions').fetchone()
        self.assertEqual((row['settled'],row['remaining']),(3600,3600))
        with m.atomic(self.db):m.on_exit(self.db,session)
        self.assertEqual(self.db.execute('SELECT balance FROM membership_grants').fetchone()[0],0)
        m.adjust(self.db,grant,1,'recharge','r1','Recharge');m.reconcile(self.db,session,'review','Vérification réelle')
        self.assertEqual(self.db.execute('SELECT remaining FROM membership_consumptions').fetchone()[0],0)
    def test_strict_never_prevents_departure(self):
        self.set(module_memberships='1',membership_control='strict',membership_require_credit='1')
        with self.assertRaises(m.EntryDenied):record_user_presence(self.db,self.user)
        self.db.rollback()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=?',(self.user,)).fetchone()[0],0)
        self.set(module_memberships='0');record_user_presence(self.db,self.user)
        self.set(module_memberships='1');self.assertTrue(record_quick_departure(self.db,self.user))
    def test_family_explicit_links(self):
        plan=self.plan(scope='family')
        with self.assertRaises(ValueError):m.assign(self.db,plan,self.user,[self.user,self.other],date.today(),'family')
        from family_model import link
        with self.db:
            self.db.execute("UPDATE users SET birth_date='1985-01-01',birth_year=1985,email='camille@example.invalid',phone='0100000000' WHERE id=?",(self.user,))
            self.db.execute("UPDATE users SET birth_date='2016-01-01',birth_year=2016 WHERE id=?",(self.other,))
        link(self.db,self.other,self.user);self.db.commit()
        grant=m.assign(self.db,plan,self.user,[self.user,self.other],date.today(),'family')
        self.assertEqual(len(m.grants_for(self.db,self.other)),1)
        m.beneficiaries(self.db,grant,[self.user],'family-change','Fin de couverture')
        self.assertTrue(m.grants_for(self.db,self.other)[0]['ended_at'])
    def test_admin_pages_permissions_and_forms(self):
        self.set(module_memberships='1')
        self.assertIn(self.client.get('/admin/abonnements').status_code,(302,403))
        self.login_admin();page=self.client.get('/admin/abonnements?user='+str(self.user))
        self.assertEqual(page.status_code,200)
        self.assertIn('Attribuer une formule',page.get_data(as_text=True))
        self.assertEqual(self.client.post('/admin/abonnements/action',data={'action':'settings','operation_key':'bad'}).status_code,400)
    def test_sound_preferences_restart(self):
        self.login_admin();page=self.client.get('/admin/reglages/borne').get_data(as_text=True)
        token=re.search(r'name="evolution_csrf" value="([^"]+)"',page)[1]
        response=self.client.post('/admin/reglages/2-10/sound',data=dict(evolution_csrf=token,kiosk_sound_enabled='1',kiosk_sound_volume='23',kiosk_sound_ambience='halloween'))
        self.assertEqual(response.status_code,302)
        with self.database() as reopened:self.assertEqual(m.setting(reopened,'kiosk_sound_volume'),'23')
        data=json.loads(re.search(r'id="kiosk-audio">(.*?)</script>',self.client.get('/').get_data(as_text=True))[1])
        self.assertEqual(data['ambience'],'halloween');self.assertTrue(data['enabled'])
    def test_kiosk_idempotency_real_route(self):
        self.set(kiosk_sound_enabled='1')
        data=json.loads(re.search(r'id="kiosk-audio">(.*?)</script>',self.client.get('/identification').get_data(as_text=True))[1])
        for i in range(2):
            response=self.client.post('/identification',data=dict(public_id='0101',kiosk_action=data['token']),headers={'X-OFL-Kiosk':'1'})
            self.assertEqual(response.status_code,200);self.assertEqual(response.json['event'],'arrival' if i==0 else '')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=?',(self.user,)).fetchone()[0],1)
        self.assertFalse(self.db.execute('SELECT check_out FROM sessions WHERE user_id=?',(self.user,)).fetchone()[0])
    def test_sync_delay_and_recovery(self):
        from reservation_notifications import sync_episode,deliver
        self.set(module_discord='1',discord_notifications_enabled='1',discord_sync_recovery_enabled='1')
        start=datetime(2026,10,17,tzinfo=timezone.utc)
        with self.db:sync_episode(self.db,'production','poll',True,start)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM reservation_discord_events').fetchone()[0],0)
        with self.db:sync_episode(self.db,'production','poll',True,start+timedelta(minutes=10))
        sent=[];self.assertEqual(deliver(self.db,self.database_path,sender=sent.append),1)
        with self.db:sync_episode(self.db,'production','poll',False,start+timedelta(minutes=11))
        self.assertEqual(deliver(self.db,self.database_path,sender=sent.append),1)
        self.assertIn('rétablie',sent[-1])
    def test_membership_notices_mocked_no_contact_copy(self):
        import membership_notices
        grant=self.grant(start=date.today().isoformat())
        self.set(module_memberships='1',membership_smtp_enabled='1')
        with self.db:self.db.execute('UPDATE users SET email=? WHERE id=?',('fiction@example.invalid',self.user))
        m.adjust(self.db,grant,-9,'correction','correct','Exemple fictif')
        sent=[];self.assertEqual(membership_notices.process(self.db,self.database_path,smtp_sender=sent.append),1)
        self.assertEqual(membership_notices.process(self.db,self.database_path,smtp_sender=sent.append),0)
        self.assertIn('solde',sent[0].get_content().lower())
        self.assertNotIn('fiction@example.invalid',str([tuple(r) for r in self.db.execute('SELECT * FROM membership_notifications')]))
    def test_renewals_serialized_no_overlap(self):
        plan=self.plan(kind='period',unit='none');first=self.grant(plan)
        second=m.assign(self.db,plan,self.user,[self.user],'2026-05-01','renew1',first)
        third=m.assign(self.db,plan,self.user,[self.user],'2026-05-01','renew2',first)
        rows=self.db.execute('SELECT starts_on,ends_on FROM membership_grants ORDER BY starts_on').fetchall()
        self.assertEqual(len(rows),3);self.assertTrue(all(a['ends_on']<b['starts_on'] for a,b in zip(rows,rows[1:])))

    def test_halfday_windows_and_temporary_return(self):
        plan=self.plan(unit='halfday');grant=self.grant(plan);self.set(module_memberships='1')
        for begin,end in [('2026-10-17T07:30:00+00:00','2026-10-17T10:00:00+00:00'),('2026-10-17T10:05:00+00:00','2026-10-17T12:00:00+00:00')]:
            with m.atomic(self.db):
                cursor=self.db.execute("INSERT INTO sessions(user_id,check_in,check_out,entry_method,exit_method) VALUES(?,?,?,'id','id')",(self.user,begin,end))
                decision=m.access(self.db,self.user,datetime.fromisoformat(begin));m.on_entry(self.db,self.user,cursor.lastrowid,datetime.fromisoformat(begin),decision)
                m.on_exit(self.db,cursor.lastrowid)
        self.assertEqual(self.db.execute('SELECT balance FROM membership_grants').fetchone()[0],8)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM membership_consumptions').fetchone()[0],2)
    def test_automatic_closure_no_invented_hour_charge(self):
        from app import close_all_open_sessions
        grant=self.grant(self.plan(unit='hour'),start=date.today().isoformat());self.set(module_memberships='1')
        record_user_presence(self.db,self.user);close_all_open_sessions(self.db,'automatic')
        self.assertEqual(self.db.execute('SELECT balance FROM membership_grants').fetchone()[0],36000)
        self.assertEqual(self.db.execute('SELECT review_required FROM membership_session_links').fetchone()[0],1)
    def test_last_pass_return_allowed_in_strict_mode(self):
        self.grant(self.plan(quantity=1),start=date.today().isoformat());self.set(module_memberships='1',membership_require_credit='1',membership_control='strict')
        record_user_presence(self.db,self.user);record_quick_departure(self.db,self.user)
        self.assertTrue(m.access(self.db,self.user)['allowed']);record_user_presence(self.db,self.user)
        self.assertEqual(self.db.execute('SELECT balance FROM membership_grants').fetchone()[0],0)
    def test_refund_is_compensating_not_rewritten(self):
        grant=self.grant(start=date.today().isoformat());self.set(module_memberships='1');record_user_presence(self.db,self.user)
        entry=self.db.execute("SELECT * FROM membership_ledger WHERE kind='consumption'").fetchone()
        m.reverse(self.db,entry['operation_key'],'refund','Erreur de pointage fictive')
        self.assertEqual(tuple(entry),tuple(self.db.execute('SELECT * FROM membership_ledger WHERE operation_key=?',(entry['operation_key'],)).fetchone()))
        self.assertEqual(self.db.execute('SELECT balance FROM membership_grants').fetchone()[0],10)
        with self.assertRaises(ValueError):m.reverse(self.db,entry['operation_key'],'refund2','Doublon refusé')
    def test_concurrent_same_recharge_only_once(self):
        import threading
        grant=self.grant();errors=[]
        def task():
            connection=self.database()
            try:m.adjust(connection,grant,2,'recharge','parallel','Recharge simultanée fictive')
            except Exception as error:errors.append(type(error).__name__)
            finally:connection.close()
        threads=[threading.Thread(target=task) for _ in range(4)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertFalse(errors);self.assertEqual(self.db.execute('SELECT balance FROM membership_grants').fetchone()[0],12)
    def test_transaction_failure_rolls_back_attendance_and_debit(self):
        self.grant(start=date.today().isoformat());self.set(module_memberships='1')
        with patch('memberships.movement',side_effect=sqlite3.OperationalError('Simulated')):
            with self.assertRaises(sqlite3.OperationalError):record_user_presence(self.db,self.user)
            self.db.rollback()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=?',(self.user,)).fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT balance FROM membership_grants').fetchone()[0],10)
    def test_validation_units_templates_and_settings(self):
        from v210_config import validate
        for values in [dict(unit='halfday',halfday_windows='[["10:00","15:00"],["14:00","16:00"]]'),dict(quantity='nan'),dict(quantity='-1'),dict(unit='hour',quantity='0.000000001')]:
            with self.subTest(values=values),self.assertRaises(ValueError):self.plan(**values)
        for key,value in [('kiosk_sound_volume','101'),('discord_sync_delay_minutes','-1'),('membership_mail_body','{email}'),('membership_control','freeforall')]:
            with self.subTest(key=key),self.assertRaises(ValueError):validate(key,value)
    def test_sync_short_outage_no_alert_separate_environments(self):
        from reservation_notifications import sync_episode
        start=datetime.now(timezone.utc)
        with self.db:
            sync_episode(self.db,'production','poll',True,start)
            sync_episode(self.db,'test','poll',True,start)
            sync_episode(self.db,'production','poll',False,start+timedelta(minutes=2))
        self.assertEqual(self.db.execute('SELECT active FROM wordpress_sync_incidents WHERE environment=\'test\'').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM reservation_discord_events').fetchone()[0],0)
    def test_sync_recovery_requires_sent_alert_not_pending(self):
        from reservation_notifications import sync_episode,deliver
        self.set(discord_sync_delay_minutes='0',module_discord='1',discord_notifications_enabled='1',discord_sync_recovery_enabled='1')
        with self.db:
            sync_episode(self.db,'production','poll',True)
            sync_episode(self.db,'production','catalogue',True)
            sync_episode(self.db,'production','poll',False)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM reservation_discord_events').fetchone()[0],1)
        with self.db:sync_episode(self.db,'production','catalogue',False)
        self.assertEqual(deliver(self.db,self.database_path,sender=lambda _:self.fail('No delayed message after recovery')),0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM reservation_discord_events').fetchone()[0],1)
    def test_calendar_note_scope_permissions_and_escape(self):
        self.login_admin();page=self.client.get('/admin/calendrier?date=2026-10-23').get_data(as_text=True)
        token=re.search(r'name="evolution_csrf" value="([^"]+)"',page)[1]
        response=self.client.post('/admin/calendrier/note',data=dict(evolution_csrf=token,kind='openlab',key='2026-10-23',day='2026-10-23',date='2026-10-23',note='<script>private-fiction</script>'))
        self.assertEqual(response.status_code,302)
        row=self.db.execute('SELECT * FROM calendar_notes').fetchone();self.assertIsNotNone(row)
        public=self.client.get('/').get_data(as_text=True);self.assertNotIn('private-fiction',public)
        html=self.client.get('/admin/calendrier?date=2026-10-23').get_data(as_text=True)
        self.assertIn('&lt;script&gt;private-fiction',html);self.assertNotIn('<script>private-fiction',html)
        next_week=self.client.get('/admin/calendrier?date=2026-10-30').get_data(as_text=True);self.assertNotIn('private-fiction',next_week)
    def test_missing_contact_and_ambiguous_send(self):
        from membership_notices import process
        grant=self.grant(start=date.today().isoformat());m.adjust(self.db,grant,-10,'correction','empty','Fictif')
        self.set(module_memberships='1',membership_smtp_enabled='1')
        self.assertEqual(process(self.db,self.database_path,smtp_sender=lambda _:self.fail('No recipient')),0)
        with self.db:self.db.execute('UPDATE users SET email=? WHERE id=?',('example@example.invalid',self.user))
        m.adjust(self.db,grant,3,'recharge','topup','Fictif');process(self.db,self.database_path,smtp_sender=lambda _:None)
        m.adjust(self.db,grant,-3,'correction','empty2','Fictif')
        def unavailable(_):raise OSError('Mocked transport, never real')
        process(self.db,self.database_path,smtp_sender=unavailable)
        self.assertEqual(process(self.db,self.database_path,smtp_sender=lambda _:self.fail('No ambiguous retry')),0)

    def test_preferences_profile_round_trip(self):
        from profile_archive import build_profile,parse_profile
        values={'module_memberships':'1','kiosk_sound_enabled':'1','kiosk_sound_volume':'19','membership_notice_days':'7',
            'membership_mail_body':'Bonjour : {nom_formule}','discord_sync_delay_minutes':'14'}
        raw=build_profile(values,[],{})
        parsed=parse_profile(raw)
        self.assertEqual(parsed['settings'],values)
    def test_suspension_expiration_exemption_and_disable(self):
        grant=self.grant(start='2025-01-01')
        self.set(module_memberships='1',membership_require_period='1',membership_control='strict')
        self.assertFalse(m.access(self.db,self.user)['allowed'])
        m.select_credit(self.db,self.user,'',True,'Exemption individuelle fictive')
        self.assertTrue(m.access(self.db,self.user)['allowed'])
        m.select_credit(self.db,self.user,'',False,'Fin exemption')
        category=self.db.execute('SELECT category FROM users WHERE id=?',(self.user,)).fetchone()[0]
        self.set(membership_exempt_categories=json.dumps([category]))
        self.assertTrue(m.access(self.db,self.user)['allowed'])
        self.set(module_memberships='0');record_user_presence(self.db,self.user);record_quick_departure(self.db,self.user)
        self.assertEqual(self.db.execute('SELECT balance FROM membership_grants').fetchone()[0],10)
        m.state_change(self.db,grant,'suspended','suspend','Suspension fictive')
        self.assertEqual(self.db.execute('SELECT status FROM membership_grants').fetchone()[0],'suspended')
        m.state_change(self.db,grant,'active','resume','Réactivation fictive')
    def test_visitor_receipt_error_and_replay_payload(self):
        self.set(kiosk_sound_enabled='1')
        settings=json.loads(re.search(r'id="kiosk-audio">(.*?)</script>',self.client.get('/').get_data(as_text=True))[1])
        before=self.db.execute('SELECT COUNT(*) FROM visitors').fetchone()[0]
        for i in range(2):
            result=self.client.post('/visiteurs',data={'kiosk_action':settings['token']},headers={'X-OFL-Kiosk':'1'})
            self.assertEqual(result.json['event'],'visitor' if i==0 else '')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM visitors').fetchone()[0],before+1)
        invalid=self.client.post('/identification',data={'kiosk_action':settings['token'],'public_id':'0101'},headers={'X-OFL-Kiosk':'1'})
        self.assertEqual(invalid.status_code,400)
        settings=json.loads(re.search(r'id="kiosk-audio">(.*?)</script>',self.client.get('/identification').get_data(as_text=True))[1])
        result=self.client.post('/identification',data={'kiosk_action':settings['token'],'public_id':'9998'},headers={'X-OFL-Kiosk':'1'})
        self.assertEqual(result.json['event'],'error')
    def test_automatic_theme_fallbacks(self):
        self.set(kiosk_sound_ambience='auto')
        for theme,expected in [('halloween','halloween'),('christmas','christmas'),('steampunk','classic'),('classic','classic')]:
            with self.subTest(theme=theme):
                self.set(home_theme=theme)
                settings=json.loads(re.search(r'id="kiosk-audio">(.*?)</script>',self.client.get('/').get_data(as_text=True))[1])
                self.assertEqual(settings['ambience'],expected)
    def test_actual_application_restart_preserves_preferences(self):
        from app import create_app
        self.set(module_memberships='1',kiosk_sound_enabled='1',kiosk_sound_volume='23',kiosk_sound_ambience='christmas',discord_sync_delay_minutes='17')
        before=[tuple(row) for row in self.db.execute('SELECT id,public_id,first_name,last_name FROM users ORDER BY id')]
        restarted=create_app(dict(TESTING=True,DATABASE=self.database_path,SECRET_KEY='fictional-restart-key',
            ADMIN_PIN=None,MODERATOR_PIN=None,SEED_DEMO_USERS=False,WEATHER_ENABLED=False,AUTO_CLOSURE_WORKER=False))
        html=restarted.test_client().get('/').get_data(as_text=True)
        settings=json.loads(re.search(r'id="kiosk-audio">(.*?)</script>',html)[1])
        self.assertTrue(settings['enabled']);self.assertEqual(settings['volume'],23);self.assertEqual(settings['ambience'],'christmas')
        self.assertEqual(m.setting(self.db,'discord_sync_delay_minutes'),'17')
        self.assertEqual(before,[tuple(row) for row in self.db.execute('SELECT id,public_id,first_name,last_name FROM users ORDER BY id')])
    def test_timezone_boundaries_and_real_dst_duration(self):
        self.grant(self.plan(kind='period',unit='none',validity_unit='days'),start='2026-10-18')
        self.set(module_memberships='1',membership_require_period='1',membership_control='strict',structure_timezone='Asia/Tokyo')
        self.assertFalse(m.access(self.db,self.user,datetime.fromisoformat('2026-10-17T14:59:00+00:00'))['allowed'])
        self.assertTrue(m.access(self.db,self.user,datetime.fromisoformat('2026-10-17T15:01:00+00:00'))['allowed'])
        plan=self.plan(unit='hour');grant=self.grant(plan,key='dst-credit')
        self.set(structure_timezone='Europe/Paris',membership_require_period='0')
        for begin,end,seconds in [('2026-03-29T01:30:00+01:00','2026-03-29T03:30:00+02:00',3600),('2026-10-25T01:30:00+02:00','2026-10-25T03:30:00+01:00',10800)]:
            with m.atomic(self.db):
                cursor=self.db.execute("INSERT INTO sessions(user_id,check_in,check_out,entry_method,exit_method) VALUES(?,?,?,'id','id')",(self.user,begin,end))
                m.on_entry(self.db,self.user,cursor.lastrowid,datetime.fromisoformat(begin));m.on_exit(self.db,cursor.lastrowid)
                self.assertEqual(self.db.execute('SELECT requested FROM membership_consumptions WHERE session_id=?',(cursor.lastrowid,)).fetchone()[0],seconds)
    def test_full_backup_restore_includes_grants_and_settings(self):
        import private_backup
        import tempfile
        from pathlib import Path
        self.grant();self.set(module_memberships='1',kiosk_sound_volume='22')
        temporary=tempfile.TemporaryDirectory(prefix='membership-backup-');self.addCleanup(temporary.cleanup)
        folder=Path(temporary.name)/'isolated-restore';folder.mkdir()
        archive=Path(temporary.name)/'full.zip';private_backup.create_backup(self.database_path,archive)
        private_backup.restore_backup(archive,folder/'openfablab.db',secret_key='fictional-only')
        with sqlite3.connect(folder/'openfablab.db') as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],21)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM membership_grants').fetchone()[0],1)
            self.assertEqual(m.setting(db,'kiosk_sound_volume'),'22')
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())
    def test_refund_shortage_not_debited_again(self):
        self.grant(self.plan(unit='hour',quantity=1),start=date.today().isoformat());self.set(module_memberships='1');record_user_presence(self.db,self.user)
        session=self.db.execute('SELECT id FROM sessions WHERE user_id=?',(self.user,)).fetchone()[0];now=datetime.now(timezone.utc)
        with self.db:self.db.execute("UPDATE sessions SET check_in=?,check_out=?,exit_method='id' WHERE id=?",((now-timedelta(hours=2)).isoformat(),now.isoformat(),session))
        with m.atomic(self.db):m.on_exit(self.db,session)
        debit=self.db.execute("SELECT * FROM membership_ledger WHERE kind='consumption'").fetchone()
        m.reverse(self.db,debit['operation_key'],'waive','Heure offerte explicitement')
        m.reconcile(self.db,session,'settle-remainder','Vérification après compensation')
        c=self.db.execute('SELECT * FROM membership_consumptions').fetchone()
        self.assertEqual((c['settled'],c['waived'],c['remaining']),(3600,3600,0))

if __name__=='__main__':unittest.main()


class CalendarNotePermissionsTest(unittest.TestCase):
    setUp=MembershipTest.setUp;tearDown=MembershipTest.tearDown
    database=MembershipTest.database;login_admin=MembershipTest.login_admin;_login_token=MembershipTest._login_token
    set=MembershipTest.set
    def token(self,path):
        return re.search(r'name="evolution_csrf" value="([^"]+)"',self.client.get(path).get_data(as_text=True))[1]
    def login(self,role):
        self.client.post('/admin/connexion',data=dict(access_role=role,pin='1379' if role=='admin' else '8642',csrf_token=self._login_token()))
        with self.client.session_transaction() as session:self.assertEqual(session['access_role'],role)
    def post_note(self,note,day='2026-10-23',csrf=None):
        return self.client.post('/admin/calendrier/note',data=dict(evolution_csrf=self.token('/admin/calendrier?date='+day) if csrf is None else csrf,kind='openlab',key=day,day=day,date=day,note=note),follow_redirects=False)
    def check_crud_scope(self,role):
        self.login(role)
        for note in ['Note fictive ajoutée','Note fictive modifiée']:
            self.assertEqual(self.post_note(note).status_code,302)
            self.assertEqual(self.db.execute("SELECT note FROM calendar_notes WHERE occurrence_date='2026-10-23'").fetchone()[0],note)
            self.assertIn(note,self.client.get('/admin/calendrier?date=2026-10-23').get_data(as_text=True))
            self.assertNotIn(note,self.client.get('/admin/calendrier?date=2026-10-30').get_data(as_text=True))
        self.assertEqual(self.post_note('Autre occurrence fictive','2026-10-30').status_code,302)
        self.assertEqual(self.post_note('').status_code,302)
        self.assertEqual([tuple(r) for r in self.db.execute('SELECT occurrence_date,note FROM calendar_notes')],[('2026-10-30','Autre occurrence fictive')])
    def test_admin_crud_occurrence(self):self.check_crud_scope('admin')
    def test_moderator_crud_occurrence(self):self.check_crud_scope('moderator')
    def test_moderator_requires_valid_csrf(self):
        self.login('moderator')
        for invalid in ['','invalid-token']:
            self.assertEqual(self.post_note('Refusé',csrf=invalid).status_code,400)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM calendar_notes').fetchone()[0],0)
    def test_nonteam_direct_get_post_denied_no_note_exposure(self):
        with self.db:self.db.execute("INSERT INTO calendar_notes VALUES('openlab','2026-10-23','2026-10-23','Sentinelle privée fictive','2026-10-17T00:00:00+00:00')")
        before=[tuple(r) for r in self.db.execute('SELECT * FROM calendar_notes')]
        for role in [None,'user','visitor']:
            with self.client.session_transaction() as session:
                session.clear()
                if role:session['access_role']=role
            response=self.client.get('/admin/calendrier?date=2026-10-23')
            self.assertIn(response.status_code,(302,403));self.assertNotIn('Sentinelle privée fictive',response.get_data(as_text=True))
            response=self.client.post('/admin/calendrier/note',data=dict(note='Attaque fictive',kind='openlab',key='2026-10-23',day='2026-10-23',evolution_csrf='forged',access_role='admin'))
            self.assertIn(response.status_code,(302,403))
            self.assertEqual(before,[tuple(r) for r in self.db.execute('SELECT * FROM calendar_notes')])
    def test_moderator_has_no_new_sensitive_rights(self):
        self.login('moderator');token=self.token('/admin/calendrier?date=2026-10-23')
        before=[tuple(r) for r in self.db.execute('SELECT * FROM app_settings ORDER BY key')]
        for path in ['/admin/reglages/structure','/admin/reglages/donnees','/admin/reglages/notifications','/admin/abonnements']:
            self.assertIn(self.client.get(path).status_code,(302,403,404),path)
        for section in ['sound','sync']:
            self.assertIn(self.client.post('/admin/reglages/2-10/'+section,data=dict(evolution_csrf=token,kiosk_sound_enabled='0',discord_sync_delay_minutes='0')).status_code,(302,403))
        self.assertEqual(before,[tuple(r) for r in self.db.execute('SELECT * FROM app_settings ORDER BY key')])
    def test_disabled_calendar_blocks_note_endpoint(self):
        self.login('moderator');token=self.token('/admin/calendrier?date=2026-10-23');self.set(module_activities='0')
        self.assertEqual(self.client.get('/admin/calendrier?date=2026-10-23').status_code,404)
        self.assertEqual(self.post_note('Refusé',csrf=token).status_code,404)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM calendar_notes').fetchone()[0],0)
    def test_note_does_not_enter_public_catalogues_or_notifications(self):
        self.login('moderator');before=self.db.execute('SELECT COUNT(*) FROM reservation_discord_events').fetchone()[0]
        self.post_note('Sentinelle interne fictive')
        from outbound_actions import public_catalogue
        for environment in ['production','test']:
            self.assertNotIn('Sentinelle interne fictive',json.dumps(public_catalogue(self.db,environment,include_information=True,include_limits=True),ensure_ascii=False))
        for route in ['/','/etat-accueil','/usagers','/identification']:
            response=self.client.get(route);self.assertEqual(response.status_code,200)
            self.assertNotIn('Sentinelle interne fictive',response.get_data(as_text=True))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM reservation_discord_events').fetchone()[0],before)
