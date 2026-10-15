"""Own-address opt-in notices, entirely simulated SMTP and fictitious data."""
import json,re,unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from tests import test_families as fixtures
from app import write_setting,run_data_retention
import retention_notices as notices
import welcome_mail
from profile_archive import build_profile,parse_profile

class RetentionNoticeTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.FamilyTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.db=self.f.db
        self.now=datetime(2026,10,14,10,tzinfo=timezone.utc)
        self.db.execute("UPDATE users SET created_at='2024-10-21T12:00:00+00:00' WHERE id=?",(self.f.a,))
        write_setting(self.db,'retention_contact_notice_enabled','1');self.db.commit()
        self.config=dict(host='smtp.example.invalid',port=587,security='starttls',username='fictional',password='fictional-local-only',sender_name='Atelier Exemple',sender_email='privacy@example.invalid',reply_to='')
        welcome_mail.save_config(self.f.f.database_path,self.config)
    def process(self,sender=None,now=None):
        self.sent=[] if sender is None else None
        return notices.process(self.db,self.f.f.database_path,now or self.now,sender or self.sent.append)
    def test_J7_once_restart_no_contact_or_content_copy(self):
        self.assertEqual(self.process(),1);message=self.sent[0];self.assertEqual(str(message['To']),'person0@example.invalid')
        body=message.get_body(preferencelist=('plain',)).get_content();self.assertIn('21/10/2026',body);self.assertNotIn('Fictif0',body)
        self.assertFalse(list(message.iter_attachments()));self.assertEqual(self.process(),0)
        rows=[tuple(row) for row in self.db.execute('SELECT * FROM retention_contact_notices')]
        for forbidden in ('@','Fictif','060000','Bonjour','fictional-local-only'):self.assertNotIn(forbidden,str(rows))
    def test_default_disabled_and_no_record_or_send(self):
        self.db.execute("DELETE FROM app_settings WHERE key='retention_contact_notice_enabled'");self.db.commit()
        self.assertFalse(notices.preferences(self.db)['enabled']);self.assertEqual(self.process(),0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM retention_contact_notices').fetchone()[0],0)
    def test_no_address_and_no_smtp(self):
        self.db.execute('UPDATE users SET email=NULL WHERE id=?',(self.f.a,));self.db.commit();self.assertEqual(self.process(),0)
        self.db.execute("UPDATE users SET email='person0@example.invalid' WHERE id=?",(self.f.a,));self.db.commit()
        with patch('welcome_mail.load_config',return_value={}):self.assertEqual(self.process(),0)
        self.assertEqual(self.db.execute('SELECT state FROM retention_contact_notices').fetchone()[0],'pending')
    def test_policy_change_cancels_old_deadline_preserves_contact(self):
        notices.reconcile(self.db,self.now);write_setting(self.db,'retention_contact_years','3');self.db.commit()
        self.assertEqual(self.process(),0);self.assertEqual(self.db.execute('SELECT state FROM retention_contact_notices').fetchone()[0],'cancelled')
        self.assertIsNotNone(self.db.execute('SELECT email FROM users WHERE id=?',(self.f.a,)).fetchone()[0])
    def test_activity_change_cancels_and_recomputes(self):
        notices.reconcile(self.db,self.now)
        self.db.execute('INSERT INTO sessions(user_id,check_in,check_out) VALUES(?,?,?)',(self.f.a,self.now.isoformat(),self.now.isoformat()));self.db.commit()
        self.assertEqual(self.process(),0);self.assertEqual(self.db.execute('SELECT state FROM retention_contact_notices').fetchone()[0],'cancelled')
    def test_transport_failure_never_blocks_purge_and_no_exception_text_logged(self):
        def bad(_message):raise OSError('DO_NOT_LOG_THIS_PRIVATE_CONTACT')
        self.assertEqual(self.process(bad),0);self.assertEqual(self.process(bad),0)
        row=self.db.execute('SELECT * FROM retention_contact_notices').fetchone();self.assertEqual(row['state'],'uncertain');self.assertEqual(row['last_error'],'OSError');self.assertNotIn('DO_NOT_LOG',str(tuple(row)))
        with self.f.f.app.app_context(),patch('app.warn_before_retention_action',return_value=False):
            report=run_data_retention(__import__('app').get_database(),now=self.now+timedelta(days=8),force=True)
        self.assertEqual(report['contacts_cleared'],1);self.assertIsNone(self.db.execute('SELECT email FROM users WHERE id=?',(self.f.a,)).fetchone()[0])
        self.assertEqual(self.process(now=self.now+timedelta(days=9)),0)
    def test_no_late_send_on_or_after_erasure_deadline(self):
        self.assertEqual(self.process(now=datetime(2026,10,21,12,tzinfo=timezone.utc)),0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM retention_contact_notices').fetchone()[0],0)
    def test_leap_day_matches_existing_actual_purge(self):
        activity=datetime(2024,2,29,12,tzinfo=timezone.utc);due=notices.deadline(activity,2)
        self.assertEqual(due.astimezone(notices.PARIS).date().isoformat(),'2026-03-01')
        from app import years_ago
        self.assertLessEqual(activity.astimezone(notices.PARIS),years_ago(due.astimezone(notices.PARIS),2))
        self.assertGreater(activity.astimezone(notices.PARIS),years_ago((due-timedelta(seconds=1)).astimezone(notices.PARIS),2))
    def test_minor_only_own_address_no_responsible_fallback(self):
        self.db.execute("UPDATE users SET created_at='2024-10-21T12:00:00+00:00',email=NULL WHERE id=?",(self.f.c,));self.db.commit()
        self.process();self.assertEqual([str(message['To']) for message in self.sent],['person0@example.invalid'])
    def test_crashed_claim_not_replayed(self):
        notices.reconcile(self.db,self.now);self.db.execute("UPDATE retention_contact_notices SET state='sending',claimed_at=?",((self.now-timedelta(minutes=11)).isoformat(),));self.db.commit()
        self.assertEqual(self.process(),0);self.assertEqual(self.db.execute('SELECT state FROM retention_contact_notices').fetchone()[0],'uncertain')
    def test_template_validation_and_profile_roundtrip(self):
        notices.validate(notices.SUBJECT,notices.BODY)
        for subject,body in [('bad\nsubject',notices.BODY),(notices.SUBJECT,'No date'),(notices.SUBJECT,'{date_suppression} {user.email}'),(notices.SUBJECT,'{date_suppression!r}'),(notices.SUBJECT,'{date_suppression} {unknown}')]:
            with self.assertRaises(ValueError):notices.validate(subject,body)
        values=dict(retention_contact_notice_enabled='1',retention_contact_notice_days='14',retention_contact_notice_subject=notices.SUBJECT,retention_contact_notice_body=notices.BODY)
        self.assertEqual(parse_profile(build_profile(values,[],{}))['settings'],values)
        with self.assertRaises(ValueError):parse_profile(build_profile(dict(values,retention_contact_notice_days='91'),[],{}))
    def test_settings_permissions_csrf_and_existing_years_preserved(self):
        client=self.f.client;path='/admin/reglages/donnees/preavis';self.f.f.login_admin()
        page=client.get('/admin/reglages/donnees').get_data(as_text=True);token=re.search('name="evolution_csrf" value="([^"]+)"',page)[1]
        data=dict(enabled='1',days='14',subject=notices.SUBJECT,body=notices.BODY,evolution_csrf=token)
        before=list(self.db.execute("SELECT key,value FROM app_settings WHERE key IN('retention_contact_years','retention_deactivation_years','retention_deletion_years')"))
        self.assertEqual(client.post(path,data=data).status_code,302)
        self.assertEqual([tuple(row) for row in before],[tuple(row) for row in self.db.execute("SELECT key,value FROM app_settings WHERE key IN('retention_contact_years','retention_deactivation_years','retention_deletion_years')")])
        self.assertEqual(client.post(path,data=dict(data,evolution_csrf='bad')).status_code,400)
        with client.session_transaction() as state:state['access_role']='moderator'
        self.assertEqual(client.post(path,data=data).status_code,302)
        self.assertNotIn('préavis envoyés',client.get('/donnees').get_data(as_text=True))
    def test_batch_bound_and_remaining_pending(self):
        for index in range(54):
            self.db.execute("INSERT INTO users(public_id,first_name,last_name,category,email,created_at) VALUES(?,?,'EXEMPLE','user',?,'2024-10-21T12:00:00+00:00')",(str(6000+index),'Fictif'+str(index),'fictional'+str(index)+'@example.invalid'))
        self.db.commit();self.assertEqual(self.process(),1)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM retention_contact_notices WHERE state='pending'").fetchone()[0],54)
        for _ in range(54):self.assertEqual(self.process(),1)
        self.assertEqual(self.process(),0)

