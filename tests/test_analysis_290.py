"""Fictional sessions: history, DST, privacy, snapshots and mature cohorts."""
import unittest
from datetime import datetime, timedelta, timezone
from tests import test_families as fixtures
import attendance_analysis as analysis
from app import write_setting

class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.FamilyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db=self.f.db;self.now=datetime(2026,10,14,12,tzinfo=timezone.utc)
        self.values=dict(mode='user',user_id=str(self.f.a),period='custom',start='2026-09-01',end='2026-09-30')
    def passage(self,user,begin,end=None,category='user'):
        self.db.execute('INSERT INTO sessions(user_id,check_in,check_out,statistical_user_key,statistical_category) VALUES(?,?,?,?,?)',
            (user,begin,end,'fictitious-'+str(user),category));self.db.commit()
    def get(self,**values):return analysis.analyse(self.db,dict(self.values,**values),self.now)
    def test_one_session_not_two_movements_actual_duration(self):
        self.passage(self.f.a,'2026-09-01T08:00:00+00:00','2026-09-01T10:30:00+00:00')
        result=self.get();m=result['metrics'];self.assertEqual((m['visits'],m['seconds'],m['mean_seconds']),(1,9000,9000))
        self.assertEqual(sum(m['hourly']),9000);self.assertEqual(sum(map(sum,m['heat'])),9000)
    def test_open_session_no_invented_duration(self):
        self.passage(self.f.a,'2026-09-02T08:00:00+00:00')
        value=self.get();self.assertEqual(value['metrics']['open'],1);self.assertEqual(value['metrics']['seconds'],0)
        self.assertIsNone(value['history']['passages'][0]['departure'])
    def test_category_snapshot_not_current_category(self):
        self.passage(self.f.a,'2026-09-01T08:00:00Z','2026-09-01T09:00:00Z','user')
        self.db.execute("UPDATE users SET category='volunteer' WHERE id=?",(self.f.a,));self.db.commit()
        self.assertEqual(self.get(mode='category',category='user')['metrics']['visits'],1)
        self.assertEqual(self.get(mode='category',category='volunteer')['metrics']['visits'],0)
    def test_keyset_pages_ten_and_filter_reset(self):
        for index in range(23):
            begin=datetime(2026,9,1,tzinfo=timezone.utc)+timedelta(days=index)
            self.passage(self.f.a,begin.isoformat(),(begin+timedelta(hours=1)).isoformat())
        clause,params,_=analysis.scope(self.db,self.values);start,end=analysis.period(self.db,self.values,clause,params,self.now)
        pages=[];cursor=None
        for _ in range(3):
            value=analysis.history(self.db,clause,params,start,end,analysis.zone(self.db),cursor);pages.extend(value['passages']);cursor=value['cursor']
        self.assertEqual(len(pages),23);self.assertEqual(len({r['arrival'] for r in pages}),23);self.assertIsNone(cursor)
        self.assertEqual(self.get(start='2026-09-22')['metrics']['visits'],2)
    def test_invalid_cursor_and_filter_rejected(self):
        with self.assertRaises(ValueError):analysis.history(self.db,'user_id=?',[self.f.a],self.now-timedelta(days=10),self.now,analysis.zone(self.db),'broken')
        for values in (dict(mode='guest'),dict(mode='category',category='unknown'),dict(start='2026-12-01')):
            with self.assertRaises(ValueError):self.get(**values)
    def test_empty_and_zero_previous_percentage(self):
        value=self.get();self.assertEqual(value['metrics']['visits'],0);self.assertIsNone(value['comparison']['visits']['percent'])
        self.assertEqual(value['history']['passages'],[])
    def test_equal_duration_previous_period_and_regular_users(self):
        for day in (1,2):self.passage(self.f.a,f'2026-09-0{day}T10:00:00Z',f'2026-09-0{day}T11:00:00Z')
        value=self.get(mode='all');self.assertEqual(value['metrics']['regular'],1)
        self.assertEqual(analysis.instant(value['end'])-analysis.instant(value['start']),analysis.instant(value['start'])-analysis.instant(value['previous_start']))
    def test_small_collective_no_name_or_granular_graph(self):
        self.passage(self.f.a,'2026-09-01T08:00:00Z','2026-09-01T09:00:00Z')
        value=self.get(mode='all');self.assertTrue(value['small_collective']);self.assertEqual(value['metrics']['heat'],[])
        self.assertIsNone(value['history']);self.assertNotIn('Fictif0',str(value));self.assertNotIn('person0',str(value))
    def test_mature_cohorts_first_visit_not_signup(self):
        for user in (self.f.a,self.f.b,self.f.other):
            for day in (1,3,6,9):self.passage(user,f'2026-09-{day:02}T08:00:00Z',f'2026-09-{day:02}T09:00:00Z')
        value=self.get(mode='all');cohort=value['cohorts'];self.assertEqual((cohort[0]['eligible'],cohort[0]['returned'],cohort[0]['repeated']),(3,3,3))
        self.assertEqual(cohort[1]['eligible'],0);self.assertEqual(cohort[1]['immature'],3)
    def test_earlier_visit_excludes_new_cohort(self):
        self.passage(self.f.a,'2026-08-01T08:00:00Z','2026-08-01T09:00:00Z');self.passage(self.f.a,'2026-09-01T08:00:00Z','2026-09-01T09:00:00Z')
        self.assertEqual(self.get(mode='all')['cohorts'][0]['eligible'],0)
    def test_summer_winter_hour_actual_seconds(self):
        tz=analysis.zone(self.db)
        for begin,end,seconds in [('2026-03-29T00:30:00Z','2026-03-29T02:30:00Z',7200),('2026-10-25T00:30:00Z','2026-10-25T02:30:00Z',7200)]:
            self.db.execute('DELETE FROM sessions');self.passage(self.f.a,begin,end)
            start=analysis.instant(begin)-timedelta(hours=1);finish=analysis.instant(end)+timedelta(hours=1)
            value=analysis.totals(self.db,'user_id=?',[self.f.a],start,finish,tz)
            self.assertEqual(value['seconds'],seconds);self.assertEqual(sum(value['hourly']),seconds)
    def test_boundary_clips_time_without_extra_visit(self):
        self.passage(self.f.a,'2026-08-31T21:00:00Z','2026-09-01T01:00:00Z')
        value=self.get();self.assertEqual(value['metrics']['visits'],0);self.assertEqual(value['metrics']['seconds'],10800)
    def test_anonymized_history_collective_only(self):
        self.passage(self.f.a,'2026-09-01T08:00:00Z','2026-09-01T09:00:00Z')
        self.db.execute('DELETE FROM user_family_links WHERE member_id=? OR responsible_id=?',(self.f.a,self.f.a));self.db.execute('DELETE FROM users WHERE id=?',(self.f.a,));self.db.commit()
        self.assertEqual(self.get(mode='all')['metrics']['distinct'],1)
        with self.assertRaises(ValueError):self.get()
    def test_animation_presence_not_inferred_from_session(self):
        self.f.book([self.f.a]);self.db.execute('UPDATE fablab_services SET service_date=\'2026-09-15\'');self.db.commit()
        self.passage(self.f.a,'2026-09-15T08:00:00Z','2026-09-15T11:00:00Z')
        self.assertEqual(self.get()['animations']['present'],0)
        self.db.execute('UPDATE animation_bookings SET is_present=1');self.db.commit()
        self.assertEqual(self.get()['animations']['present'],1)
    def test_routes_roles_no_store_empty_search_and_accents(self):
        client=self.f.client;path='/admin/frequentation/usagers'
        self.assertEqual(client.get(path).status_code,302)
        self.f.f.login_admin();response=client.get(path);self.assertEqual(response.status_code,200);self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertEqual(client.get(path+'/recherche?q=').json,dict(users=[],more=False))
        self.db.execute("UPDATE users SET first_name='Élise' WHERE id=?",(self.f.a,));self.db.commit()
        self.assertEqual(client.get(path+'/recherche?q=ELI').json['users'][0]['id'],self.f.a)
        with client.session_transaction() as state:state['access_role']='moderator'
        self.assertEqual(client.get(path).status_code,200)
        write_setting(self.db,'module_frequency','0');self.db.commit();self.assertEqual(client.get(path).status_code,404)
    def test_large_history_bounded_response(self):
        rows=[(self.f.a,'2025-01-01T08:00:00Z','2025-01-01T09:00:00Z','fictitious-'+str(self.f.a),'user') for _ in range(10000)]
        self.db.executemany('INSERT INTO sessions(user_id,check_in,check_out,statistical_user_key,statistical_category) VALUES(?,?,?,?,?)',rows);self.db.commit()
        value=self.get(period='all');self.assertEqual(value['metrics']['visits'],10000);self.assertEqual(len(value['history']['passages']),10)

