"""Regression tests for 2.15.4: real SQLite and admin views, fictitious data."""
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo
from flask import session
import admin_activity
import admin_summary
import app
import automatic_reminders
import fablab_calendar
import family_model
import machine_maintenance as machines
import maintenance_planning as plans
import public_snapshot
from localized_formats import calendar_moment, event_display
from memberships import atomic
from tests import test_v214_core as core
from updater_agent.data_checks import compare_before_open, snapshot


class Corrections(unittest.TestCase):
    setUp=core.NewVersion.setUp
    login=core.NewVersion.login

    def calendar(self, day, **kwargs):
        current=kwargs.pop('current',datetime(2026,11,6,10,tzinfo=timezone.utc))
        with self.f.f.app.test_request_context('/admin/calendrier'):
            session['access_role']='admin'
            return fablab_calendar.calendar_view(self.db,dict(date=day,**kwargs),SimpleNamespace(**vars(app)),current=current)

    def test_transactional_migration_and_unchanged_data(self):
        self.db.execute('DROP TABLE machine_maintenance_slots')
        self.db.execute('PRAGMA user_version=27');self.db.commit()
        before=snapshot(self.path,27)
        def interrupt(db):raise RuntimeError('fictional interruption')
        with self.assertRaisesRegex(RuntimeError,'interruption'):family_model.migrate(self.db,interrupt)
        self.assertEqual(snapshot(self.path,27),before)
        family_model.migrate(self.db)
        compare_before_open(self.path,before,dict(schema=28,new_tables=plans.TABLES,new_settings={}))
        family_model.migrate(self.db)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM machine_maintenance_slots').fetchone()[0],0)

    def test_real_summary_times_do_not_treat_wall_clock_as_utc(self):
        now=datetime(2026,11,6,12,tzinfo=timezone.utc)
        app.write_setting(self.db,'structure_timezone','Europe/Paris')
        for day,start,end in [('2026-11-07','09:30','11:30'),('2026-11-10','14:00','16:00')]:
            self.db.execute('INSERT INTO openlab_exceptions VALUES(?,?,?,?,?,?,?,?)',(day,'extra',start,end,'',1,'admin',now.isoformat()))
        app.write_setting(self.db,'openlab_public_enabled','1')
        self.db.execute("UPDATE fablab_services SET title='Gravure fictive',service_date='2026-11-19',start_time='14:00',end_time='16:00' WHERE id=?",(self.f.service,))
        self.db.commit();self.login()
        original=tuple(self.db.execute('SELECT service_date,start_time,end_time FROM fablab_services WHERE id=?',(self.f.service,)).fetchone())
        empty_schedule=[dict(active=False,start=None,end=None) for _ in range(7)]
        with patch.object(admin_summary,'datetime',wraps=datetime) as clock,patch.object(app,'load_openlab_schedule',return_value=empty_schedule):
            clock.now.return_value=now
            html=self.client.get('/admin').text
            self.assertIn('07/11/2026 à 09:30',html)
            self.assertIn('10/11/2026 à 14:00',html)
            self.assertIn('19/11/2026 à 14:00',html)
            for env in ('production','test'):
                events=public_snapshot.build(self.db,env,calendar=True,now=now)['calendar']
                e=next(e for e in events if e['id']=='openlab-2026-11-07')
                self.assertEqual(e['start'],'2026-11-07T09:30:00+01:00')
            events=self.calendar('2026-11-19')['days']
            self.assertTrue(any(e['time']=='14:00–16:00' and e['title']=='Gravure fictive' for d in events for e in d['events']))
        self.assertEqual(original,tuple(self.db.execute('SELECT service_date,start_time,end_time FROM fablab_services WHERE id=?',(self.f.service,)).fetchone()))

    def test_dst_two_folds_midnight_and_other_zones(self):
        paris=ZoneInfo('Europe/Paris')
        self.assertEqual(event_display('2026-03-29T09:30',paris),'29/03/2026 à 09:30')
        self.assertEqual(event_display('2026-03-29T07:30:00+00:00',paris),'29/03/2026 à 09:30')
        self.assertEqual(event_display('2026-10-25T08:30:00+00:00',paris),'25/10/2026 à 09:30')
        self.assertEqual(event_display('2026-11-06T23:30:00Z',paris),'07/11/2026 à 00:30')
        self.assertEqual(event_display('2026-11-07',paris),'07/11/2026')
        self.assertEqual(event_display('2026-11-07T09:30',ZoneInfo('America/Montreal')),'07/11/2026 à 09:30')
        stamps=[calendar_moment('2026-10-25T0'+str(hour)+':30:00+00:00',paris) for hour in (0,1)]
        self.assertEqual([stamp.hour for stamp in stamps],[2,2])
        self.assertEqual([stamp.fold for stamp in stamps],[0,1])
        from resource_booking import book
        key=book(self.db,self.key,self.f.a,'2030-10-27T00:30:00+00:00','2030-10-27T01:15:00+00:00','admin')
        result=self.calendar('2030-10-27')
        row=next(e for d in result['days'] for e in d['events'] if e['key']==key)
        self.assertEqual((row['start_minute'],row['end_minute']),(150,195))
        self.assertEqual(row['time'],'02:30 CEST–02:15 CET')

    def test_overnight_and_day_only(self):
        self.db.execute("UPDATE fablab_services SET service_date='2026-11-08',start_time='23:30',end_time='01:30' WHERE id=?",(self.f.service,))
        self.db.commit()
        for day,hours in [('2026-11-08','23:30–00:00'),('2026-11-09','00:00–01:30')]:
            row=next(e for d in self.calendar(day)['days'] for e in d['events'] if e['key']==str(self.f.service))
            self.assertEqual(row['time'],hours)
        self.db.execute('UPDATE fablab_services SET start_time=NULL,end_time=NULL WHERE id=?',(self.f.service,))
        row=next(e for d in self.calendar('2026-11-08')['days'] for e in d['events'] if e['key']==str(self.f.service))
        self.assertTrue(row['all_day'])

    def plan(self, start, end, **extra):
        with atomic(self.db):
            return plans.save(self.db,self.key,dict(title='Contrôle fictif',starts_on=start,ends_on=end,**extra),'moderator')

    def test_maintenance_bands_weeks_month_single_timed_and_remains_private(self):
        long=self.plan('2026-11-06','2026-11-11')
        single=self.plan('2026-11-07','2026-11-07',tentative='1')
        short=self.plan('2026-11-09','2026-11-09',starts_time='10:00',ends_time='11:30')
        for week,length in [('2026-11-06',3),('2026-11-09',3)]:
            result=self.calendar(week)
            runs=[r for r in result['week_maintenance'] if r['event']['key']=='planned-'+long]
            self.assertEqual(len(runs),1);self.assertEqual(runs[0]['end']-runs[0]['start'],length)
            self.assertTrue(runs[0]['event']['url'].endswith('#maintenance-'+long))
        month=self.calendar('2026-11-06',view='month')
        self.assertEqual(sum(r['event']['key']=='planned-'+long for w in month['month_weeks'] for r in w['maintenance']),2)
        events=[e for d in month['days'] for e in d['events']]
        self.assertEqual([(e['all_day'],e['tentative']) for e in events if e['key']=='planned-'+single],[(True,True)])
        self.assertEqual([(e['all_day'],e['time']) for e in events if e['key']=='planned-'+short],[(False,'10:00–11:30')])
        self.assertFalse(self.calendar('2026-11-06',maintenance='0')['week_maintenance'])
        self.assertEqual(machines.machine(self.db,self.key)['status'],'operational')
        for env in ('production','test'):
            self.assertNotIn('Contrôle fictif',str(public_snapshot.build(self.db,env,calendar=True)))

    def test_condition_no_invented_end_and_estimated_return_separate(self):
        machines.set_condition(self.db,self.key,{'status':'maintenance'},'admin','admin')
        self.db.execute("UPDATE machine_condition SET status_since='2026-11-02T08:00:00+00:00' WHERE resource_uuid=?",(self.key,))
        runs=self.calendar('2026-11-06')['week_maintenance']
        self.assertEqual(len(runs),1);self.assertEqual((runs[0]['start'],runs[0]['end']),(0,5))
        self.assertIsNone(runs[0]['event']['estimated_return'])
        self.assertEqual(runs[0]['event']['time'],'')
        self.db.execute("UPDATE machine_condition SET return_estimate='2026-11-09' WHERE resource_uuid=?",(self.key,))
        runs=self.calendar('2026-11-06')['week_maintenance']
        self.assertEqual(len(runs),1)
        self.assertEqual(runs[0]['event']['estimated_return'],date(2026,11,9))
        self.assertEqual(runs[0]['end'],7)

    def test_plan_permissions_validation_and_no_business_change(self):
        route='/admin/ressources/'+self.key+'/fiche'
        payload=dict(action='maintenance_slot',title='Nettoyage fictif',starts_on='2026-11-06',ends_on='2026-11-07')
        self.assertNotEqual(self.client.post(route,data=payload).status_code,200)
        token=self.login('moderator')
        self.assertEqual(self.client.post(route,data=payload).status_code,400)
        created=self.client.post(route,data=payload|dict(evolution_csrf=token))
        self.assertEqual(created.status_code,302)
        self.assertIn('Nettoyage fictif',self.client.get(route).text)
        key=created.location.split('#maintenance-')[1]
        self.assertIn('id="maintenance-'+key+'"',self.client.get(route).text)
        app.write_setting(self.db,'structure_timezone','Europe/Paris');self.db.commit()
        for day in ('2026-03-29','2026-10-25'):
            with self.assertRaisesRegex(ValueError,'changement'):self.plan(day,day,starts_time='02:30',ends_time='03:30')
        with self.assertRaisesRegex(ValueError,'a changé'):
            with atomic(self.db):plans.save(self.db,self.key,dict(identifier=key,revision='0'),'moderator',cancel=True)
        with atomic(self.db):plans.save(self.db,self.key,dict(identifier=key,revision='1'),'moderator',cancel=True)
        self.assertFalse(plans.visible(self.db,date(2026,11,6),date(2026,11,9)))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM machine_maintenance_slots').fetchone()[0],1)

    def test_reminder_qualification_and_no_late_discord_backfill(self):
        now=datetime(2026,11,6,10,tzinfo=timezone.utc)
        states={}
        for day,name in [('2026-11-03','overdue'),('2026-11-06','today'),('2026-11-07','upcoming'),('2026-11-08','done')]:
            key=machines.reminder(self.db,self.key,dict(due_on=day,subject='Fictif '+name),'moderator','moderator')
            if name=='done':self.db.execute("UPDATE machine_reminders SET state='done' WHERE reminder_uuid=?",(key,))
            states[key]=name
        self.db.commit()
        actual={e['key']:e['reminder_state'] for d in self.calendar('2026-11-06')['days'] for e in d['events'] if 'reminder_state' in e}
        self.assertEqual(actual,states)
        self.login('moderator')
        done=next(k for k,state in states.items() if state=='done')
        self.assertIn('id="reminder-'+done+'"',self.client.get('/admin/ressources/'+self.key+'/fiche').text)
        app.write_setting(self.db,'maintenance_discord_enabled','1');self.db.commit();sent=[]
        with self.f.f.app.app_context():
            automatic_reminders.process(self.db,self.path,now,discord_sender=sent.append)
        self.assertEqual(len(sent),1);self.assertIn('Fictif today',sent[0])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM machine_reminders WHERE state='pending'").fetchone()[0],3)

    def test_distinct_anim_bookings_person_roles_and_summary_pool(self):
        self.f.book([self.f.a],staff=True);self.f.book([self.f.b],owner=self.f.b,staff=True)
        self.db.execute("UPDATE animation_bookings SET created_at='2026-11-06T19:57:00+00:00'");self.db.commit()
        modules=app.load_modules(self.db)
        with self.f.f.app.test_request_context('/admin'):
            for role in ('admin','moderator'):
                people=[r['person'] for r in admin_activity.journal(self.db,modules,role) if r['kind']=='calendar']
                self.assertEqual(set(people),{'Fictif0 EXEMPLE','Fictif1 EXEMPLE'})
            self.assertEqual(admin_activity.journal(self.db,modules,None),[])
            start=datetime(2026,11,6,9,tzinfo=timezone.utc)
            schedule=[dict(active=True,start='14:00',end='17:00') for _ in range(7)]
            initial=admin_summary.build(self.db,modules,'admin',start,schedule)
            self.assertEqual(len(initial['upcoming']),15)
            from resource_booking import save_resource
            for i in range(8):
                key=save_resource(self.db,dict(name='Fictif '+str(i),type_key='machine'),'admin')
                machines.set_condition(self.db,key,{'status':'maintenance'},'admin','admin')
            self.assertEqual(admin_summary.build(self.db,modules,'admin',start,schedule)['upcoming'],initial['upcoming'])
