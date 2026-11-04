"""New integration edges; fictional data and injected transports only."""
import json,sqlite3,threading
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from tests.test_v214_reminders import ReminderTests
from tests.test_v214_core import NewVersion
from app import write_setting
import automatic_reminders as reminders,machine_maintenance as machines,public_snapshot,outbound_actions as relay

class Edges(ReminderTests):
    def test_simultaneous_workers_send_one_family_reminder(self):
        self.ready();sent=[];errors=[];start=threading.Barrier(2)
        def work():
            db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
            try:
                with self.f.f.app.app_context():
                    start.wait();reminders.process(db,self.path,self.now,mail_sender=sent.append)
            except BaseException as error:errors.append(type(error).__name__)
            finally:db.close()
        threads=[threading.Thread(target=work) for _ in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(15);self.assertFalse(thread.is_alive())
        self.assertFalse(errors,errors);self.assertEqual(len(sent),1)
    def test_discord_false_is_uncertain_and_never_repeated(self):
        now=datetime(2026,12,1,9,tzinfo=timezone.utc);write_setting(self.db,'maintenance_discord_enabled','1')
        key=machines.reminder(self.db,self.key,dict(due_on='2026-12-01',subject='Fictional check'),'moderator','moderator');self.db.commit();calls=[]
        def reject(text):calls.append(text);return False
        for _ in range(2):self.assertEqual(reminders.process(self.db,self.path,now,discord_sender=reject)['sent'],0)
        self.assertEqual(len(calls),1);self.assertEqual(self.db.execute('SELECT state FROM automatic_deliveries').fetchone()[0],'uncertain')
        machines.reminder(self.db,self.key,dict(due_on='2026-12-02',subject='Rescheduled',state='pending',revision='1'),'moderator','moderator',key);self.db.commit()
        reminders.process(self.db,self.path,now+timedelta(days=1),discord_sender=reject);self.assertEqual(len(calls),1)
    def test_postponed_before_due_sends_only_on_new_date(self):
        write_setting(self.db,'maintenance_discord_enabled','1')
        key=machines.reminder(self.db,self.key,dict(due_on='2026-12-01',subject='Fictional check'),'moderator','moderator')
        machines.reminder(self.db,self.key,dict(due_on='2026-12-02',subject='Rescheduled',state='pending',revision='1'),'moderator','moderator',key);self.db.commit();sent=[]
        reminders.process(self.db,self.path,datetime(2026,12,1,9,tzinfo=timezone.utc),discord_sender=sent.append);self.assertFalse(sent)
        reminders.process(self.db,self.path,datetime(2026,12,2,9,tzinfo=timezone.utc),discord_sender=sent.append);self.assertEqual(len(sent),1)
    def test_real_receipt_and_management_offer_calendar_only_after_confirmation(self):
        self.f.book([self.f.a]);group=dict(self.db.execute('SELECT * FROM family_booking_groups').fetchone());self.db.commit()
        with self.client.session_transaction() as s:s['family_receipt']=dict(group_uuid=group['group_uuid'],status='confirmed',title='Fictional',count=1,until=__import__('time').time()+1200)
        response=self.client.get('/animations/confirmation');self.assertEqual(response.status_code,200)
        self.assertIn('/calendrier.ics',response.text);self.assertIn('calendar.google.com',response.text)
        link=relay.issue_link(b'fictitious',group['manage_token'],'production','manage')
        write_setting(self.db,'reservation_participant_calendar_production','1');self.db.commit()
        value=relay.dispatch(self.db,dict(environment='production',link=link),'view','production',b'fictitious','unused')
        self.assertIn('calendar',value);self.assertNotIn(group['manage_token'],value['calendar']['ics'])
        self.db.execute("UPDATE family_booking_groups SET status='waitlisted'");self.db.commit()
        value=relay.dispatch(self.db,dict(environment='production',link=link),'view','production',b'fictitious','unused');self.assertNotIn('calendar',value)
    def test_public_projection_excludes_notes_families_and_secrets(self):
        machines.set_condition(self.db,self.key,dict(status='maintenance',announce='1',public_listed='1',public_reason='PUBLIC REASON'),'admin','admin')
        machines.intervention(self.db,self.key,dict(performed_on='2026-10-01',kind='care',description='PRIVATE NOTE MARKER'),'moderator','moderator')
        write_setting(self.db,'openlab_public_enabled','1');self.db.commit()
        value=public_snapshot.build(self.db,'production',True,True)
        raw=json.dumps(value)
        self.assertIn('PUBLIC REASON',raw)
        for forbidden in ('PRIVATE NOTE MARKER','person0@example.invalid','Fictif0','participants','contact_email','manage_token','author','billing'):
            self.assertNotIn(forbidden,raw)
        with self.assertRaises(ValueError):public_snapshot.build(self.db,'unknown',False,True)
    def test_health_distinguishes_active_claim_and_uncertainty_read_only(self):
        from installation_health import diagnostic
        now=datetime(2026,12,1,9,tzinfo=timezone.utc)
        self.db.execute("INSERT INTO automatic_deliveries VALUES('fictional','maintenance','claimed',?,NULL,NULL)",(now.isoformat(),));self.db.commit()
        before=self.db.total_changes
        active=next(p for p in diagnostic(self.db,now,self.path)['panels'] if p['key']=='jobs')
        stale=next(p for p in diagnostic(self.db,now+timedelta(minutes=11),self.path)['panels'] if p['key']=='jobs')
        self.assertEqual(active['state'],'unknown');self.assertIn('en cours',active['evidence']);self.assertEqual(stale['state'],'attention');self.assertEqual(before,self.db.total_changes)

for base in (ReminderTests,NewVersion):
    for name in vars(base):
        if name.startswith('test_'):setattr(Edges,name,None)
def load_tests(loader,suite,pattern):return loader.loadTestsFromTestCase(Edges)
