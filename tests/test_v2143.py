"""Real runtime, fictional SQLite and injected Discord sender only."""
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tests import test_v214_core as core
from app import write_setting
import automatic_reminders as reminders,machine_maintenance as machines

class Presentation(unittest.TestCase):
    def setUp(self):
        core.NewVersion.setUp(self);context=self.f.f.app.app_context();context.push();self.addCleanup(context.pop)
        for key,value in dict(maintenance_discord_enabled='1',module_discord='1',module_public_reservations='0',structure_timezone='Europe/Paris').items():write_setting(self.db,key,value)
        self.db.commit()
    def create(self,day):
        key=machines.reminder(self.db,self.key,dict(due_on=day,subject='Vérification fictive'),'moderator','moderator');self.db.commit();return key
    def test_french_date_only_message_changes(self):
        key=self.create('2026-11-03');before=tuple(self.db.execute('SELECT * FROM machine_reminders WHERE reminder_uuid=?',(key,)).fetchone());sent=[]
        settings=dict(self.db.execute('SELECT key,value FROM app_settings'))
        reminders.process(self.db,self.path,datetime(2026,11,3,8,tzinfo=timezone.utc),discord_sender=sent.append)
        self.assertEqual(len(sent),1);self.assertTrue(sent[0].endswith(' · 03/11/2026'));self.assertNotIn('2026-11-03',sent[0])
        self.assertEqual(before,tuple(self.db.execute('SELECT * FROM machine_reminders WHERE reminder_uuid=?',(key,)).fetchone()))
        self.assertEqual(settings,dict(self.db.execute('SELECT key,value FROM app_settings')))
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],24)
    def test_english_uses_primary_language_not_process_locale(self):
        write_setting(self.db,'kiosk_language','en');self.db.commit();self.create('2026-11-03');sent=[]
        reminders.process(self.db,self.path,datetime(2026,11,3,8,tzinfo=timezone.utc),discord_sender=sent.append)
        self.assertTrue(sent[0].endswith(' · 3 Nov 2026'))
    def test_date_is_not_shifted_from_local_midnight(self):
        write_setting(self.db,'structure_timezone','America/New_York');self.db.commit();self.create('2026-11-03');sent=[]
        reminders.process(self.db,self.path,datetime(2026,11,4,0,30,tzinfo=timezone.utc),discord_sender=sent.append)
        self.assertTrue(sent[0].endswith(' · 03/11/2026'))
    def test_paris_date_ahead_of_utc(self):
        write_setting(self.db,'maintenance_reminder_hour','0');self.db.commit();self.create('2026-11-04');sent=[]
        reminders.process(self.db,self.path,datetime(2026,11,3,23,30,tzinfo=timezone.utc),discord_sender=sent.append)
        self.assertTrue(sent[0].endswith(' · 04/11/2026'))
    def test_dst_spring_and_autumn_keep_scheduled_hour_and_deduplication(self):
        for day,instant,expected in [('2026-03-29',datetime(2026,3,29,7,tzinfo=timezone.utc),'29/03/2026'),('2026-10-25',datetime(2026,10,25,8,tzinfo=timezone.utc),'25/10/2026')]:
            with self.subTest(day=day):
                self.create(day);sent=[]
                reminders.process(self.db,self.path,instant-timedelta(seconds=1),discord_sender=sent.append);self.assertFalse(sent)
                reminders.process(self.db,self.path,instant,discord_sender=sent.append)
                reminders.process(self.db,self.path,instant+timedelta(minutes=1),discord_sender=sent.append)
                self.assertEqual(len(sent),1);self.assertTrue(sent[0].endswith(expected))
    def test_uncertain_delivery_is_not_repeated(self):
        key=self.create('2026-11-03');calls=[]
        def fail(text):calls.append(text);raise RuntimeError('FICTIONAL_PRIVATE_TOKEN')
        for _ in range(2):reminders.process(self.db,self.path,datetime(2026,11,3,8,tzinfo=timezone.utc),discord_sender=fail)
        self.assertEqual(len(calls),1)
        self.assertEqual(tuple(self.db.execute('SELECT state,error_code FROM automatic_deliveries WHERE delivery_key=?',('maintenance/'+key,)).fetchone()),('uncertain','RuntimeError'))
    def test_disabled_discord_still_sends_nothing(self):
        write_setting(self.db,'maintenance_discord_enabled','0');self.db.commit();self.create('2026-11-03');sent=[]
        reminders.process(self.db,self.path,datetime(2026,11,3,8,tzinfo=timezone.utc),discord_sender=sent.append)
        self.assertFalse(sent);self.assertFalse(self.db.execute('SELECT * FROM automatic_deliveries').fetchall())
    def test_existing_intervention_link_and_state_preserved(self):
        intervention=machines.intervention(self.db,self.key,dict(performed_on='2026-11-02',kind='care',description='Nettoyage fictif'),'moderator','moderator')
        key=machines.reminder(self.db,self.key,dict(due_on='2026-11-03',subject='Contrôle fictif'),'moderator','moderator',intervention_id=intervention);self.db.commit()
        before=tuple(self.db.execute('SELECT * FROM machine_reminders WHERE reminder_uuid=?',(key,)).fetchone())
        reminders.process(self.db,self.path,datetime(2026,11,3,8,tzinfo=timezone.utc),discord_sender=lambda text:True)
        self.assertEqual(before,tuple(self.db.execute('SELECT * FROM machine_reminders WHERE reminder_uuid=?',(key,)).fetchone()))
        self.assertEqual(machines.machine(self.db,self.key)['status'],'operational')
    def test_english_months_are_unambiguous_and_locale_independent(self):
        write_setting(self.db,'kiosk_language','en')
        self.assertEqual(reminders.maintenance_due_label(self.db,'2026-03-04'),'4 Mar 2026')
        self.assertEqual(reminders.maintenance_due_label(self.db,'2028-02-29'),'29 Feb 2028')
    def test_calendar_hints_filters_and_permissions_unchanged(self):
        core.NewVersion.login(self)
        for view in ('week','month'):
            body=self.client.get('/admin/calendrier?view='+view+'&maintenance=0&hidden=1').text
            self.assertIn('Afficher entretiens et rappels',body);self.assertIn('Afficher les événements masqués',body)
            self.assertNotIn('Étendue pour montrer',body)
        self.assertNotEqual(self.f.f.app.test_client().get('/admin/calendrier').status_code,200)
