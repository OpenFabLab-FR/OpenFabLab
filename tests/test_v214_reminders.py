"""No real SMTP/Discord; deterministic due windows and one durable claim."""
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from tests.test_v214_core import NewVersion
from app import write_setting
from automatic_reminders import process
from welcome_mail import save_config
import machine_maintenance as machines
import reservation_calendar

class ReminderTests(NewVersion):
    def setUp(self):
        super().setUp();context=self.f.f.app.app_context();context.push();self.addCleanup(context.pop)
    # Inherit the established fixtures, not its unrelated core tests.
    def ready(self):
        self.now=datetime(2026,12,1,9,tzinfo=timezone.utc)
        self.config=dict(host='smtp.example.invalid',port=587,security='starttls',username='fictitious',password='not-real',sender_name='Atelier Exemple',sender_email='team@example.invalid',reply_to='')
        save_config(self.path,self.config)
        self.db.execute("UPDATE fablab_services SET service_date='2026-12-03',start_time='10:00',end_time='12:00' WHERE id=?",(self.f.service,))
        for key,value in dict(reservation_reminder_enabled='1',reservation_reminder_hours='48',
            reservation_link_mode='local',reservation_public_url='https://example.invalid',
            v214_reminders_available_since='2026-11-01T00:00:00+00:00').items():write_setting(self.db,key,value)
        self.db.commit();self.f.book([self.f.a,self.f.c]);self.db.commit()
    def test_one_family_reminder_exact_due(self):
        self.ready();sent=[]
        process(self.db,self.path,self.now-timedelta(seconds=1),mail_sender=sent.append)
        self.assertFalse(sent)
        process(self.db,self.path,self.now,mail_sender=sent.append)
        process(self.db,self.path,self.now+timedelta(seconds=30),mail_sender=sent.append)
        self.assertEqual(len(sent),1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM automatic_deliveries WHERE state='sent'").fetchone()[0],1)
    def test_cancelled_and_test_never_reminded(self):
        self.ready()
        for field,value in [('status','cancelled'),('environment','test')]:
            with self.subTest(field=field):
                self.db.execute("UPDATE family_booking_groups SET status='confirmed',environment='production'")
                self.db.execute('UPDATE family_booking_groups SET '+field+'=?',(value,));self.db.commit();sent=[]
                process(self.db,self.path,self.now,mail_sender=sent.append);self.assertFalse(sent)
    def test_no_retrospective_reminder_on_upgrade(self):
        self.ready();write_setting(self.db,'v214_reminders_available_since',(self.now+timedelta(seconds=1)).isoformat());self.db.commit();sent=[]
        process(self.db,self.path,self.now+timedelta(minutes=5),mail_sender=sent.append);self.assertFalse(sent)
    def test_uncertain_delivery_not_replayed_or_logged(self):
        self.ready();calls=[]
        def fail(message):calls.append(1);raise RuntimeError('SENSITIVE_FAKE_VALUE')
        process(self.db,self.path,self.now,mail_sender=fail);process(self.db,self.path,self.now+timedelta(minutes=1),mail_sender=fail)
        self.assertEqual(len(calls),1)
        row=self.db.execute('SELECT state,error_code FROM automatic_deliveries').fetchone()
        self.assertEqual(tuple(row),('uncertain','RuntimeError'))
    def test_maintenance_once_without_changing_status(self):
        self.now=datetime(2026,12,1,9,tzinfo=timezone.utc)
        write_setting(self.db,'maintenance_discord_enabled','1');self.db.commit()
        machines.reminder(self.db,self.key,dict(due_on='2026-12-01',subject='Vérifier le circuit'),'moderator','moderator');self.db.commit();sent=[]
        process(self.db,self.path,self.now,discord_sender=sent.append);process(self.db,self.path,self.now,discord_sender=sent.append)
        self.assertEqual(len(sent),1);self.assertEqual(machines.machine(self.db,self.key)['status'],'operational')
        self.assertFalse(self.db.execute('SELECT 1 FROM machine_interventions').fetchone())
    def test_email_calendar_independent_of_custom_template(self):
        self.ready();from reservation_email_templates import build_message
        row=dict(self.db.execute('SELECT * FROM family_booking_emails LIMIT 1').fetchone())
        write_setting(self.db,'reservation_email_confirmed_body','MON TEXTE PERSONNALISÉ\n{lien_reservation}')
        message=build_message(self.config,row,'https://example.invalid',db=self.db)
        self.assertIn('MON TEXTE PERSONNALISÉ',message.get_body(preferencelist=('plain',)).get_content())
        attachments=list(message.iter_attachments());self.assertEqual(len(attachments),1)
        self.assertEqual(attachments[0].get_filename(),'animation.ics')
        self.assertNotIn(b'Fictif',attachments[0].get_payload(decode=True))
    def test_health_is_read_only_and_does_not_claim_delivery(self):
        self.ready();from installation_health import diagnostic
        self.db.commit();before=self.db.total_changes
        result=diagnostic(self.db,self.now,self.path)
        self.assertEqual(before,self.db.total_changes)
        smtp=next(item for item in result['panels'] if item['key']=='smtp')
        self.assertEqual(smtp['state'],'unknown')
        self.assertNotIn('not-real',str(result));self.assertNotIn('smtp.example.invalid',str(result))

# Do not duplicate inherited core methods in this targeted run.
for _name in list(vars(NewVersion)):
    if _name.startswith('test_'):setattr(ReminderTests,_name,None)
