"""V2.15.3 cross-feature tests, with fictitious data and no outbound delivery."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import admin_summary
import app
import fablab_calendar
import family_model
from flask import session
import machine_maintenance as machines
import public_snapshot
import resource_booking as booking
import resource_loans as loans
from tests import test_v214_core as core
from tests.schema_fixtures import remove_27
from updater_agent.data_checks import snapshot,compare_before_open
from v2153_schema import TABLES,SETTINGS


class ReleaseFeatures(unittest.TestCase):
    setUp=core.NewVersion.setUp
    login=core.NewVersion.login

    @property
    def qr(self): return '/r/'+self.key

    @property
    def page(self): return '/admin/ressources/'+self.key+'/fiche'

    def publish(self, enabled=True):
        for k,v in {'resource_public_pages_enabled':'1','resource_public_base_url':'https://fablab.example/stat',
                    'resource_reports_enabled':str(int(enabled))}.items():
            app.write_setting(self.db,k,v)
        machines.set_condition(self.db,self.key,{'status':'operational','visibility_controls':'1','public_visible':'1'},'admin','admin')
        self.db.commit()

    def token(self):
        self.assertEqual(self.client.get(self.qr).status_code,200)
        with self.client.session_transaction() as s:return s.get('evolution_csrf')

    def submit(self, description, token=None, **extra):
        return self.client.post(self.qr, data=dict(description=description,evolution_csrf=token or self.token(),**extra))

    def test_schema_26_transaction_and_agent_historical_evidence(self):
        machines.set_condition(self.db,self.key,{'status':'out_of_service','announce':'1','public_reason':'Fiction'},'admin','admin')
        remove_27(self.db);self.db.commit()
        baseline=snapshot(self.path,26)
        ddl=list(self.db.iterdump())
        with self.assertRaisesRegex(RuntimeError,'fictional'):
            family_model.migrate(self.db, lambda _: (_ for _ in ()).throw(RuntimeError('fictional interruption')))
        self.assertEqual(ddl,list(self.db.iterdump()))
        family_model.migrate(self.db)
        from maintenance_planning import TABLES as NEW_TABLES
        compare_before_open(self.path,baseline,dict(schema=family_model.SCHEMA,new_tables=TABLES+NEW_TABLES,new_settings=SETTINGS))
        self.assertEqual(machines.machine(self.db,self.key)['status'],'out_of_service')
        self.assertFalse(self.db.execute('PRAGMA foreign_key_check').fetchall())

    def test_public_unavailable_and_loan_precedence_and_negotiated_fallback(self):
        self.publish()
        start=datetime.now(timezone.utc)+timedelta(days=2)
        key=booking.book(self.db,self.key,self.f.a,start.isoformat(),(start+timedelta(hours=1)).isoformat(),'admin')
        self.db.execute("UPDATE resource_bookings SET status='confirmed' WHERE booking_uuid=?",(key,));self.db.commit()
        self.assertEqual(loans.availability(self.db,self.key)['status'],'operational')
        loans.transition(self.db,'booking',key,'handover','admin',current=start)
        machines.set_condition(self.db,self.key,{'status':'unavailable','public_reason':'Atelier extérieur'},'admin','admin');self.db.commit()
        self.assertEqual(loans.availability(self.db,self.key,start)['status'],'loaned')
        self.assertEqual(loans.availability(self.db,self.key,start+timedelta(days=1))['status'],'overdue')
        loans.transition(self.db,'booking',key,'return','admin',current=start+timedelta(hours=2))
        for environment in ('production','test'):
            old=public_snapshot.build(self.db,environment,machines=True,availability=True)['machines'][0]
            new=public_snapshot.build(self.db,environment,machines=True,availability=True,unavailable=True)['machines'][0]
            self.assertEqual((old['status'],new['status']),('out_of_service','unavailable'))
            self.assertIn('Atelier extérieur',new['reason'])
        self.assertIn('data-resource-status="unavailable"',self.client.get(self.qr).text)

    def test_qr_opt_in_csrf_limit_duplicate_and_no_state_change(self):
        self.publish(False)
        self.assertNotIn('Signaler un problème',self.client.get(self.qr).text)
        self.assertEqual(self.client.post(self.qr,data={'description':'refus'}).status_code,404)
        self.publish()
        token=self.token()
        self.assertEqual(self.client.post(self.qr,data={'description':'sans jeton'}).status_code,400)
        self.assertEqual(self.submit('a'*501,token).status_code,400)
        self.assertEqual(self.submit('<script>Exemple</script>',token).status_code,303)
        self.assertEqual(self.submit('<SCRIPT>EXEMPLE</SCRIPT>',token).status_code,303)
        self.assertEqual(self.submit('Honeypot',token,website='fictif').status_code,303)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM resource_problem_reports').fetchone()[0],1)
        for n in range(3):self.assertEqual(self.submit(f'Description fictive {n}',token).status_code,303)
        self.assertEqual(self.submit('Fréquence maximale',token).status_code,429)
        self.assertEqual(machines.machine(self.db,self.key)['status'],'operational')
        self.assertNotIn('<script>Exemple</script>',self.client.get(self.qr).text)
        self.assertNotEqual(self.client.get(self.page).status_code,200)
        self.login('moderator')
        self.assertIn('&lt;script&gt;Exemple&lt;/script&gt;',self.client.get(self.page).text)

    def test_moderator_take_convert_resolve_and_private_audit(self):
        self.publish();self.assertEqual(self.submit('Bruit fictif').status_code,303)
        identifier=self.db.execute('SELECT report_id FROM resource_problem_reports').fetchone()[0]
        token=self.login('moderator')
        values=dict(action='report',report_id=identifier,evolution_csrf=token)
        for decision in ('assign','intervention','resolve'):
            response=self.client.post(self.page,data=values|{'decision':decision,'reason':'Note fictive'})
            self.assertEqual(response.status_code,302)
        self.assertEqual(self.db.execute('SELECT state FROM resource_problem_reports').fetchone()[0],'resolved')
        self.assertEqual(self.db.execute('SELECT count(*) FROM machine_interventions').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM resource_problem_decisions').fetchone()[0],3)
        self.assertNotIn('Note fictive',self.client.get(self.qr).text)
        self.assertNotIn('Bruit fictif',str(public_snapshot.build(self.db,'production',machines=True)))
        self.assertEqual(machines.machine(self.db,self.key)['status'],'operational')

    def test_discord_opt_in_follows_existing_preferences_and_sends_once(self):
        self.publish()
        for k in ('module_discord','discord_notifications_enabled','resource_reports_discord'):
            app.write_setting(self.db,k,'1')
        self.db.commit()
        with self.f.f.app.app_context():
            app.write_discord_webhook('https://discord.com/api/webhooks/123456/FAKE_TEST_ONLY')
        with patch.object(app,'post_discord_message') as send:
            for _ in range(2):self.assertEqual(self.submit('Réglage à vérifier').status_code,303)
        send.assert_called_once()
        message=send.call_args.args[1]
        self.assertIn('Réglage à vérifier',message)
        self.assertIn('https://fablab.example/stat/admin/ressources/'+self.key,message)
        self.assertNotIn('webhook',message)

    def test_task_count_reminder_overdue_and_report_share_one_resource(self):
        self.publish()
        self.submit('Fiction à traiter')
        reminder=machines.reminder(self.db,self.key,dict(due_on='2026-11-03',subject='Rappel fictif'),'admin','admin')
        machines.set_condition(self.db,self.key,{'status':'maintenance'},'admin','admin');self.db.commit()
        with self.f.f.app.test_request_context('/admin'):
            data=admin_summary.build(self.db,app.load_modules(self.db),'admin',datetime(2026,11,6,10,tzinfo=timezone.utc))
        group=next(item for item in data['actions'] if any(reminder in child['url'] for child in item.get('tasks',())))
        self.assertEqual(group['count'],3)
        self.assertEqual(group['tasks'][0]['hint'],'Rappel fictif')
        self.assertTrue(group['tasks'][0]['late'])
        self.assertEqual(data['action_count'],sum(item['count'] for item in data['actions']))
        self.login()
        self.assertIn('3 actions',self.client.get('/admin').text)

    def test_planned_quote_is_private_timed_and_not_duplicated_by_linked_animation(self):
        self.db.execute("""INSERT INTO billing_records(quote_number,quote_date,client_contact,client_structure,address_line,
            postal_code,city,title,description,activity_date,activity_start_time,activity_end_time,rate_category,rate_unit,created_at,updated_at)
            VALUES('DEV-FICTIF','2026-10-10','Contact fictif','Structure fictive','','','','Séance de démonstration','',
            '2026-11-09','09:00','12:00','normal','hourly','2026-10-10','2026-10-10')""")
        self.db.commit()
        ns=SimpleNamespace(**vars(app))
        with self.f.f.app.test_request_context('/admin/calendrier'):
            def events(role):
                session['access_role']=role
                return [e for day in fablab_calendar.calendar_view(self.db,{'date':'2026-11-09'},ns)['days'] for e in day['events']]
            items=[e for e in events('admin') if e['title']=='Séance de démonstration']
            self.assertEqual(len(items),1)
            self.assertTrue(items[0]['tentative'])
            self.assertEqual(items[0]['time'],'09:00–12:00')
            self.assertFalse(any(e['title']=='Séance de démonstration' for e in events('moderator')))
            self.db.execute("UPDATE billing_records SET service_id=? WHERE quote_number='DEV-FICTIF'",(self.f.service,));self.db.commit()
            self.assertFalse(any(e['title']=='Séance de démonstration' for e in events('admin')))
        self.assertNotIn('Séance de démonstration',str(public_snapshot.build(self.db,'production',calendar=True)))

    def test_recent_profile_modification_not_recorded_for_noop_or_page_visit(self):
        from admin_activity import record_user_change,journal
        before=self.db.execute('SELECT * FROM users WHERE id=?',(self.f.a,)).fetchone()
        record_user_change(self.db,before,self.f.a,'2026-11-06T10:00:00+00:00')
        self.assertFalse(self.db.execute('SELECT 1 FROM user_profile_activity').fetchone())
        self.db.execute('UPDATE users SET first_name=? WHERE id=?',('Nom fictif modifié',self.f.a))
        record_user_change(self.db,before,self.f.a,'2026-11-06T10:00:00+00:00')
        self.db.commit()
        self.login()
        self.client.get('/admin/usagers/'+str(self.f.a)+'/modifier')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM user_profile_activity').fetchone()[0],1)
        with self.f.f.app.test_request_context('/admin'):
            result=journal(self.db,app.load_modules(self.db),'admin')
        update=next(item for item in result if item['detail']=='Compte usager modifié')
        self.assertEqual(update['kind'],'people')
        self.assertNotIn(before['first_name'],update['title'])
