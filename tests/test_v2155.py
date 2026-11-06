"""Narrow V2.15.5 regressions; all resources and identifications are fictitious."""
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
import unittest
import admin_summary
import app
import machine_maintenance as machines
from tests import test_v214_core as core
from tests import test_v2154 as previous


class Identifications(HTMLParser):
    """Read only the dashboard's identification table, not the activity list."""
    def __init__(self,html):
        super().__init__()
        self.inside=False
        self.extended=False
        self.capture=False
        self.headers=0
        self.rows=[[],[]]
        self.feed(html)

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='table' and 'overview-history-table' in attrs.get('class','').split():self.inside=True
        if not self.inside:return
        if tag=='thead':self.headers+=1
        if tag=='tbody':self.extended=attrs.get('id')=='identifications-more'
        if tag=='td' and attrs.get('data-label')=='Arrivée':
            self.capture=True
            self.rows[self.extended].append('')

    def handle_endtag(self,tag):
        if tag=='table':self.inside=False
        if tag=='td':self.capture=False

    def handle_data(self,value):
        if self.inside and self.capture:self.rows[self.extended][-1]+=value


class FinalCorrections(unittest.TestCase):
    setUp=core.NewVersion.setUp
    login=core.NewVersion.login
    calendar=previous.Corrections.calendar
    plan=previous.Corrections.plan

    def set_condition(self,since,estimate=None,state='maintenance'):
        app.write_setting(self.db,'structure_timezone','Europe/Paris')
        machines.set_condition(self.db,self.key,dict(status=state,return_estimate=estimate),'admin','admin')
        self.db.execute('UPDATE machine_condition SET status_since=? WHERE resource_uuid=?',(since,self.key))
        self.db.commit()

    def refs(self,view,key):
        return [e for day in view['days'] for e in day['events'] if e['key']==key]

    def test_return_day_is_not_a_second_full_day(self):
        self.set_condition('2026-11-04T08:00:00+00:00','2026-11-07')
        snapshot=tuple(self.db.execute('SELECT * FROM machine_condition WHERE resource_uuid=?',(self.key,)).fetchone())
        week=self.calendar('2026-11-06')
        self.assertEqual(len(week['week_maintenance']),1)
        bar=week['week_maintenance'][0]
        self.assertEqual((bar['start'],bar['end']),(2,5))
        self.assertEqual(bar['event']['estimated_return'],date(2026,11,7))
        self.assertFalse([e for e in week['days'][5]['events'] if e['kind']=='maintenance'])
        self.assertEqual(tuple(self.db.execute('SELECT * FROM machine_condition WHERE resource_uuid=?',(self.key,)).fetchone()),snapshot)

    def test_extended_estimate_across_week_and_month_is_one_continuous_key(self):
        self.set_condition('2026-10-28T08:00:00+00:00','2026-11-05','unavailable')
        now=datetime(2026,10,30,11,tzinfo=timezone.utc)
        for day,span in [('2026-10-30',(2,7)),('2026-11-02',(0,3))]:
            bands=self.calendar(day,current=now)['week_maintenance']
            self.assertEqual(len(bands),1)
            self.assertEqual((bands[0]['start'],bands[0]['end']),span)
            self.assertEqual(bands[0]['event']['key'],self.key)
        month=self.calendar('2026-11-03',view='month',current=now)
        refs=self.refs(month,self.key)
        self.assertEqual([r['day'] for r in refs],[date(2026,10,28)+timedelta(days=i) for i in range(8)])
        self.assertEqual(sum(r['event']['key']==self.key for w in month['month_weeks'] for r in w['maintenance']),2)

    def test_no_estimate_and_passed_estimate_keep_observed_state_only(self):
        for estimate in (None,'2026-11-05'):
            with self.subTest(estimate=estimate):
                self.set_condition('2026-11-04T08:00:00+00:00',estimate,'out_of_service')
                week=self.calendar('2026-11-06')
                self.assertEqual([r['day'].day for r in self.refs(week,self.key)],[4,5,6])
                self.assertEqual(len(week['week_maintenance']),1)
                self.assertTrue(week['week_maintenance'][0]['event']['condition_ongoing'])

    def test_real_planning_and_reminders_keep_separate_links(self):
        self.set_condition('2026-11-04T08:00:00+00:00','2026-11-07')
        planned=self.plan('2026-11-05','2026-11-08')
        short=self.plan('2026-11-06','2026-11-06',starts_time='14:00',ends_time='15:00')
        reminder=machines.reminder(self.db,self.key,dict(due_on='2026-11-06',subject='Rappel fictif'),'admin','admin')
        self.db.commit()
        week=self.calendar('2026-11-06')
        self.assertEqual({r['event']['key'] for r in week['week_maintenance']},{self.key,'planned-'+planned})
        self.assertTrue(self.refs(week,'planned-'+planned)[0]['url'].endswith('#maintenance-'+planned))
        self.assertEqual(self.refs(week,'planned-'+short)[0]['time'],'14:00–15:00')
        self.assertEqual(len(self.refs(week,reminder)),1)
        self.assertTrue(self.refs(week,reminder)[0]['url'].endswith('#reminder-'+reminder))
        self.assertEqual(self.calendar('2026-11-06',maintenance='0')['week_maintenance'],[])

    def test_dashboard_event_pool_caps_at_fifteen_in_chronological_order(self):
        self.db.execute('DELETE FROM animation_reservation_config')
        self.db.execute('DELETE FROM fablab_services')
        now=datetime(2026,11,6,6,tzinfo=timezone.utc)
        enabled={'activities':True}
        modules={key:enabled.get(key,False) for key in app.load_modules(self.db)}
        app.write_setting(self.db,'module_maintenance','0')
        with self.f.f.app.test_request_context('/admin'):
            for count in (0,3,6,10,20):
                self.db.execute('DELETE FROM fablab_services')
                for offset in reversed(range(count)):
                    stamp=(now+timedelta(minutes=60+offset)).astimezone(timezone.utc)
                    self.db.execute("""INSERT INTO fablab_services(service_type,title,service_date,start_time,created_at,updated_at)
                         VALUES('animation',?,?,?,?,?)""",
                         ('Échéance '+str(offset),str(stamp.date()),stamp.strftime('%H:%M'),now.isoformat(),now.isoformat()))
                value=admin_summary.build(self.db,modules,'admin',now)['upcoming']
                self.assertEqual([e['title'] for e in value],['Échéance '+str(i) for i in range(min(count,15))])

    def test_identifications_one_header_and_bounds_for_short_and_long_history(self):
        self.login('moderator')
        with self.client.session_transaction() as s:s['admin_language']='fr'
        for total in (0,5,8,15,60):
            with self.subTest(total=total):
                self.db.execute('DELETE FROM sessions');self.db.execute('DELETE FROM visitors')
                now=datetime(2026,11,6,10,tzinfo=timezone.utc)
                for i in range(total):
                    stamp=(now-timedelta(minutes=i)).isoformat()
                    if i%2:
                        self.db.execute('INSERT INTO sessions(user_id,check_in,check_out) VALUES(?,?,?)',
                            (self.f.a,stamp,(now-timedelta(minutes=i)+timedelta(seconds=30)).isoformat()))
                    else:
                        self.db.execute('INSERT INTO visitors(created_at) VALUES(?)',(stamp,))
                self.db.commit()
                page=self.client.get('/admin')
                self.assertEqual(page.status_code,200)
                table=Identifications(page.text)
                self.assertEqual(table.headers,int(total>0))
                self.assertEqual(list(map(len,table.rows)),[min(8,total),max(0,min(40,total)-8)])
                self.assertEqual(table.rows[0]+table.rows[1],
                    ['06/11/2026 à '+(now+timedelta(hours=1,minutes=-i)).strftime('%H:%M') for i in range(min(total,40))])
                self.assertEqual('data-overview-identifications-toggle' in page.text,total>8)
        self.assertNotEqual(self.f.f.app.test_client().get('/admin').status_code,200)
