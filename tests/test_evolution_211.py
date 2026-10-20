"""Fictional-only 2.11 attendance, compatibility, capacities and privacy tests."""
import json,re,secrets,sqlite3,unittest
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from unittest import mock
from tests import test_families as fixtures
import animation_attendance as attendance
import family_model as family
import family_reservations as engine
from app import write_setting,record_user_presence,record_quick_departure
from reservations_sync import booking_counts,booking_capacity_used


class AttendanceTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.FamilyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db=self.f.db;self.client=self.f.client;self.service=self.f.service
        self.zone=ZoneInfo('Europe/Paris')
        self.now=self.at('10:15')
        with self.db:
            write_setting(self.db,'animation_auto_presence_since',self.at('00:00').isoformat())
            self.db.execute('UPDATE animation_reservation_config SET capacity=6 WHERE service_id=?',(self.service,))

    def at(self,hour,day=None):
        return datetime.fromisoformat((day or self.f.day)+'T'+hour).replace(tzinfo=self.zone).astimezone(timezone.utc)

    def book(self,people=None,**kwargs):
        return self.f.book(people or [self.f.a],**kwargs)['booking_uuids'][0]

    def passage(self,user=None,start='10:05',end=None):
        with self.db:
            return self.db.execute('INSERT INTO sessions(user_id,check_in,check_out,entry_method) VALUES(?,?,?,?)',
                (user or self.f.a,self.at(start).isoformat(),self.at(end).isoformat() if end else None,'id')).lastrowid

    def process(self,now=None,**kwargs):return attendance.process(self.db,now=now or self.now,**kwargs)

    def booking(self,key):return self.db.execute('SELECT * FROM animation_bookings WHERE external_uuid=?',(key,)).fetchone()

    def test_six_confirmed_only_no_openlab_reservations(self):
        self.f.book(self.f.people[:6],staff=True);self.passage(self.f.other)
        for user in self.f.people[:6]:self.passage(user)
        before=booking_capacity_used(self.db,self.service)
        self.assertEqual(self.process(),6)
        self.assertEqual(booking_counts(self.db.execute('SELECT * FROM animation_bookings').fetchall())['present'],6)
        self.assertEqual(booking_capacity_used(self.db,self.service),before)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_bookings').fetchone()[0],6)

    def test_current_arrival_and_closed_passage_overlap(self):
        key=self.book();self.passage(start='10:05',end='10:10')
        self.assertEqual(self.process(),1);self.assertEqual(self.booking(key)['is_present'],1)

    def test_arrival_exactly_now_is_not_lost(self):
        self.book();self.passage(start='10:15')
        self.assertEqual(self.process(),1)

    def test_arrived_before_start_still_open_detected_without_admin_get(self):
        self.book();self.passage(start='09:45')
        self.assertEqual(self.process(self.at('10:00:01')),1)

    def test_departed_before_start_not_detected(self):
        self.book();self.passage(start='09:00',end='09:30');self.assertEqual(self.process(),0)

    def test_departed_exactly_start_no_overlap(self):
        self.book();self.passage(start='09:00',end='10:00');self.assertEqual(self.process(),0)

    def test_arrival_at_or_after_end_no_overlap(self):
        self.book()
        for hour in ('12:00','12:15'):
            with self.db:self.db.execute('DELETE FROM sessions')
            self.passage(start=hour);self.assertEqual(self.process(self.at('12:30')),0)

    def test_family_parent_does_not_mark_children(self):
        self.f.book([self.f.a,self.f.c,self.f.d]);self.passage(self.f.a)
        self.assertEqual(self.process(),1)
        self.assertEqual({r['user_id'] for r in self.db.execute('SELECT * FROM animation_bookings WHERE is_present=1')},{self.f.a})

    def test_waitlisted_cancelled_guest_or_unverified_never_auto(self):
        key=self.book();self.passage()
        for status,link in [('waitlisted','registered'),('cancelled','registered'),('offer_pending','registered'),('confirmed','candidate')]:
            with self.db:self.db.execute('UPDATE animation_bookings SET status=?,link_status=? WHERE external_uuid=?',(status,link,key))
            self.assertEqual(self.process(),0)
        with self.db:self.db.execute("UPDATE animation_bookings SET status='confirmed',user_id=NULL,link_status='visitor' WHERE external_uuid=?",(key,))
        self.assertEqual(self.process(),0)

    def test_wordpress_verified_identity_and_no_notifications(self):
        value=engine.reserve(self.db,self.f.a,[self.f.a],self.service,None,secrets.token_urlsafe(32),source='wordpress')
        self.passage()
        tables=('reservation_outbox','family_mail_outbox','reservation_discord_outbox')
        tables=[t for t in tables if self.db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(t,)).fetchone()]
        before={t:self.db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in tables}
        self.assertEqual(self.process(),1)
        self.assertEqual(before,{t:self.db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in tables})
        self.assertEqual(engine.result(self.db,value['group_uuid'])['status'],'confirmed')

    def test_manual_absent_present_and_unknown_are_authoritative(self):
        key=self.book();self.passage()
        for action,value in [('absent',0),('present',1),('unknown',None)]:
            attendance.manual(self.db,self.service,key,action,'moderator')
            self.assertEqual(self.process(),0);self.assertEqual(self.booking(key)['is_present'],value)

    def test_legacy_explicit_presence_remains_authoritative(self):
        key=self.book();self.passage()
        for value in (0,1):
            with self.db:self.db.execute('UPDATE animation_bookings SET is_present=? WHERE external_uuid=?',(value,key))
            self.assertEqual(self.process(),0)

    def test_ambiguous_two_animations_not_marked(self):
        self.book();self.passage()
        with self.db:
            other=self.db.execute("INSERT INTO fablab_services(service_type,title,service_date,start_time,end_time,minimum_age,created_at,updated_at) VALUES('animation','Autre atelier fictif',?,'10:30','11:30',0,?,?)",(self.f.day,family.timestamp(),family.timestamp())).lastrowid
            self.db.execute("INSERT INTO animation_reservation_config(service_id,enabled,environment,capacity,updated_at) VALUES(?,1,'production',6,?)",(other,family.timestamp()))
        engine.reserve(self.db,self.f.a,[self.f.a],other,None,secrets.token_urlsafe(32))
        self.assertEqual(self.process(self.at('10:45')),0)

    def test_two_successive_nonoverlapping_slots_allowed(self):
        from animation_slots import save_slots
        with self.db:
            self.db.execute("UPDATE animation_reservation_config SET booking_mode='slots',slot_duration_minutes=60,slot_capacity=2 WHERE service_id=?",(self.service,))
            slots=save_slots(self.db,self.db.execute('SELECT * FROM fablab_services WHERE id=?',(self.service,)).fetchone(),self.db.execute('SELECT * FROM animation_reservation_config WHERE service_id=?',(self.service,)).fetchone(),'Europe/Paris')
        first=self.book(slot=slots[0]['slot_uuid']);second=self.book(slot=slots[1]['slot_uuid']);self.passage(start='10:05',end='10:55')
        self.assertEqual(self.process(self.at('11:15')),1)
        self.assertEqual(self.booking(first)['is_present'],1);self.assertIsNone(self.booking(second)['is_present'])

    def test_disabled_option_modules_and_test_environment(self):
        key=self.book();self.passage()
        for key_name in ('animation_auto_presence_enabled','module_frequency','module_activities','module_users'):
            with self.db:write_setting(self.db,key_name,'0')
            self.assertEqual(self.process(),0)
            with self.db:write_setting(self.db,key_name,'1')
        with self.db:self.db.execute("UPDATE animation_bookings SET environment='test' WHERE external_uuid=?",(key,))
        self.assertEqual(self.process(),0)

    def test_reenable_is_prospective_and_keeps_prior_presences(self):
        self.book();self.passage(start='10:05',end='10:10')
        attendance.configure(self.db,False)
        with mock.patch.object(attendance,'stamp',return_value=self.at('10:14').isoformat()):attendance.configure(self.db,True)
        self.assertEqual(self.process(),0)
        self.passage(start='10:15');self.assertEqual(self.process(),1)
        attendance.configure(self.db,False);self.assertEqual(self.db.execute('SELECT is_present FROM animation_bookings').fetchone()[0],1)

    def test_idempotent_no_extra_writes(self):
        self.book();self.passage();self.assertEqual(self.process(),1)
        before=self.db.total_changes
        for _ in range(3):self.assertEqual(self.process(),0)
        self.assertEqual(self.db.total_changes,before)

    def test_parallel_detection_is_single_validation(self):
        from concurrent.futures import ThreadPoolExecutor
        self.book();self.passage()
        def detect(_):
            db=sqlite3.connect(self.f.f.database_path,timeout=30);db.row_factory=sqlite3.Row
            try:return attendance.process(db,now=self.now)
            finally:db.close()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(detect,range(2)))
        self.assertEqual(sorted(results),[0,1])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_attendance_origin').fetchone()[0],1)

    def test_real_kiosk_entry_and_quick_departure_hooks(self):
        key=self.book()
        with self.f.f.app.app_context(),mock.patch('app.utc_now_iso',return_value=self.at('10:15').isoformat()),mock.patch.object(attendance,'datetime',wraps=datetime) as clock:
            clock.now.return_value=self.at('10:15');record_user_presence(self.db,self.f.a,'id')
            self.assertEqual(self.booking(key)['is_present'],1)
            record_quick_departure(self.db,self.f.a)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM animation_attendance_origin').fetchone()[0],1)

    def test_installation_no_replay_older_animation(self):
        self.book();self.passage()
        with self.db:write_setting(self.db,'animation_auto_presence_since',self.at('12:30').isoformat())
        self.assertEqual(self.process(self.at('13:00')),0)

    def test_dst_ambiguous_and_nonexistent_refused(self):
        row=dict(slot_uuid=None,service_date='2026-10-25',start_time='02:15',end_time='03:15')
        self.assertIsNone(attendance.interval(row,self.zone))
        row.update(service_date='2027-03-28');self.assertIsNone(attendance.interval(row,self.zone))

    def test_foreign_timezone_utc_overlap(self):
        key=self.book();self.passage(start='10:05',end='10:10')
        self.assertEqual(self.process(self.now.astimezone(ZoneInfo('Pacific/Auckland'))),1)
        self.assertEqual(self.booking(key)['is_present'],1)

    def test_anonymous_add_correct_remove_no_booking_session_or_mail(self):
        self.book();self.passage();self.process()
        before={t:self.db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('users','sessions','animation_bookings','visitors','reservation_outbox')}
        for quantity in (1,3,2,0):
            attendance.set_walkins(self.db,self.service,quantity,'moderator')
            self.assertEqual(self.db.execute('SELECT actual_participants FROM fablab_services WHERE id=?',(self.service,)).fetchone()[0],quantity+1)
        self.assertEqual(before,{t:self.db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in before})

    def test_anonymous_exceed_capacity_and_negative_refused(self):
        attendance.set_walkins(self.db,self.service,8,'admin')
        self.assertEqual(self.db.execute('SELECT quantity FROM animation_walkins WHERE service_id=?',(self.service,)).fetchone()[0],8)
        self.assertEqual(booking_capacity_used(self.db,self.service),0)
        for quantity in ('-1','1.5','100001','x'):
            with self.assertRaises(ValueError):attendance.set_walkins(self.db,self.service,quantity,'admin')

    def test_expected_excludes_manual_absent_present_cancelled_and_waiting(self):
        self.f.book([self.f.a,self.f.b,self.f.c,self.f.d]);rows=self.db.execute('SELECT * FROM animation_bookings').fetchall()
        attendance.manual(self.db,self.service,rows[0]['external_uuid'],'present','admin')
        attendance.manual(self.db,self.service,rows[1]['external_uuid'],'absent','moderator')
        self.assertEqual(attendance.summary(self.db,self.service,self.db.execute('SELECT * FROM animation_bookings').fetchall()),dict(expected=2,anonymous=0,actual=1))

    def test_cancellation_clears_presence_total_not_seats_extra(self):
        key=self.book();self.passage();self.process();attendance.set_walkins(self.db,self.service,2,'admin')
        engine.team_action(self.db,self.service,key,'cancel','admin')
        self.assertEqual(self.db.execute('SELECT actual_participants FROM fablab_services WHERE id=?',(self.service,)).fetchone()[0],2)
        self.assertEqual(self.process(),0)

    def test_permissions_csrf_and_no_public_directory(self):
        key=self.book();url=f'/admin/animations/{self.service}/non-inscrits'
        self.assertEqual(self.client.post(url,data={'quantity':'3'}).status_code,302)
        for role,pin in [('admin','1379'),('moderator','8642')]:
            with self.client.session_transaction() as session:session.clear()
            token=self.f.f._login_token()
            self.client.post('/admin/connexion',data={'access_role':role,'pin':pin,'csrf_token':token},follow_redirects=True)
            page=self.client.get(f'/admin/animations/{self.service}/inscriptions').get_data(as_text=True)
            token=re.search(r'name="evolution_csrf" value="([^"]+)"',page)[1]
            self.assertEqual(self.client.post(url,data={'quantity':'3'}).status_code,400)
            self.assertEqual(self.client.post(url,data={'quantity':'3','evolution_csrf':token}).status_code,302)
            csrf=re.search(r'name="csrf_token" value="([^"]+)"',page)[1]
            self.client.post(f'/admin/animations/{self.service}/inscriptions/{key}/action',data={'action':'absent','csrf_token':csrf})
            self.assertEqual(self.booking(key)['is_present'],0)

    def test_internal_animation_without_public_reservation_module(self):
        self.book()
        self.f.f.login_admin()
        with self.db:write_setting(self.db,'module_public_reservations','0')
        page=self.client.get(f'/admin/animations/{self.service}/inscriptions')
        self.assertEqual(page.status_code,200);self.assertIn('Participants non inscrits',page.get_data(as_text=True))
        self.assertNotIn('Inscrire les personnes sélectionnées',page.get_data(as_text=True))
        self.assertNotIn('Annuler l’inscription',page.get_data(as_text=True))

    def test_general_preference_persists_and_exports(self):
        self.f.f.login_admin();url='/admin/reglages/presences-animations'
        page=self.client.get('/admin/reglages/structure').get_data(as_text=True)
        token=re.search(r'name="evolution_csrf" value="([^"]+)"',page)[1]
        for enabled in (False,True):
            response=self.client.post(url,data={'evolution_csrf':token,**({'enabled':'1'} if enabled else {})})
            self.assertEqual(response.status_code,302)
            other=sqlite3.connect(self.f.f.database_path)
            self.assertEqual(other.execute("SELECT value FROM app_settings WHERE key='animation_auto_presence_enabled'").fetchone()[0],str(int(enabled)));other.close()
        from profile_archive import allowed_setting
        self.assertTrue(allowed_setting('animation_auto_presence_enabled'))

    def test_new_preferences_profile_round_trip_without_internal_horizon(self):
        from profile_archive import build_profile,parse_profile
        for ambience in ('easter','valentine'):
            values={'animation_auto_presence_enabled':'0','kiosk_sound_ambience':ambience,'kiosk_sound_volume':'37'}
            profile=parse_profile(build_profile(dict(values,animation_auto_presence_since='private runtime horizon'),[],{}))
            self.assertEqual(profile['settings'],values)


class CapacityMigrationTests(AttendanceTests):
    # unittest inheritance would repeat every attendance case. Defined below via
    # a separate factory in load_tests so only methods declared here are selected.
    def edit(self,**values):
        with self.client.session_transaction() as session:session.clear()
        self.f.f.login_admin()
        data=dict(service_type='animation',title='Atelier fictif corrigé',service_date=self.f.day,start_time='10:00',end_time='12:00',minimum_age='0',expected_participants='6',online_enabled='1',online_environment='production',online_audience='all',booking_mode='whole',slot_duration_minutes='60',slot_gap_minutes='0',slot_capacity='2',close_minutes='0',waitlist_enabled='1')
        data.update(values)
        return self.client.post(f'/admin/animations/{self.service}/modifier',data=data)

    def test_single_capacity_and_removed_fields(self):
        self.f.f.login_admin();page=self.client.get(f'/admin/animations/{self.service}/modifier').get_data(as_text=True)
        self.assertEqual(page.count('name="expected_participants"'),1)
        self.assertNotIn('name="capacity"',page);self.assertNotIn('name="actual_participants"',page)
        self.assertNotIn('Une personne sélectionnée = une place',page)
        response=self.edit(expected_participants='8',capacity='999',actual_participants='99')
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.db.execute('SELECT capacity FROM animation_reservation_config WHERE service_id=?',(self.service,)).fetchone()[0],8)
        self.assertIsNone(self.db.execute('SELECT actual_participants FROM fablab_services WHERE id=?',(self.service,)).fetchone()[0])

    def test_capacity_cannot_silently_shrink_below_confirmed(self):
        self.f.book([self.f.a,self.f.b,self.f.c,self.f.d]);self.assertEqual(self.edit(expected_participants='2').status_code,400)
        self.assertEqual(booking_capacity_used(self.db,self.service),4)

    def test_historical_mismatch_displays_booking_authority_preserves_walkins(self):
        with self.db:
            self.db.execute('UPDATE fablab_services SET expected_participants=3,actual_participants=7 WHERE id=?',(self.service,))
            self.db.execute('UPDATE animation_reservation_config SET walkin_count=7 WHERE service_id=?',(self.service,))
            self.db.execute('DELETE FROM animation_walkins WHERE service_id=?',(self.service,))
            attendance.ensure(self.db)
        self.f.f.login_admin();page=self.client.get(f'/admin/animations/{self.service}/modifier').get_data(as_text=True)
        self.assertRegex(page,r'name="expected_participants"[^>]+value="6"')
        self.assertEqual(self.edit().status_code,302)
        self.assertEqual(self.db.execute('SELECT actual_participants FROM fablab_services WHERE id=?',(self.service,)).fetchone()[0],7)

    def test_slot_exceptions_survive_edit(self):
        from animation_slots import save_slots
        with self.db:
            self.db.execute("UPDATE animation_reservation_config SET booking_mode='slots',slot_duration_minutes=60,slot_capacity=2 WHERE service_id=?",(self.service,))
            slots=save_slots(self.db,self.db.execute('SELECT * FROM fablab_services WHERE id=?',(self.service,)).fetchone(),self.db.execute('SELECT * FROM animation_reservation_config WHERE service_id=?',(self.service,)).fetchone(),'Europe/Paris')
            self.db.execute('UPDATE animation_slots SET capacity=5 WHERE slot_uuid=?',(slots[0]['slot_uuid'],))
        self.assertEqual(self.edit(booking_mode='slots',expected_participants='7').status_code,302)
        self.assertEqual([r[0] for r in self.db.execute('SELECT capacity FROM animation_slots WHERE service_id=? ORDER BY starts_at',(self.service,))],[5,2])
        self.assertEqual(self.db.execute('SELECT capacity FROM animation_reservation_config WHERE service_id=?',(self.service,)).fetchone()[0],7)

    def test_schema22_additive_atomic_no_historical_changes(self):
        key=self.book();self.passage();attendance.set_walkins(self.db,self.service,3,'admin')
        tables=('users','sessions','animation_bookings','fablab_services','animation_reservation_config','membership_ledger','calendar_notes')
        before={t:[tuple(r) for r in self.db.execute('SELECT * FROM '+t)] for t in tables}
        with self.db:
            for suffix in ('insert','update','delete'):self.db.execute('DROP TRIGGER attendance_total_'+suffix)
            self.db.execute('DROP TABLE animation_walkins');self.db.execute('DROP TABLE animation_attendance_origin')
            self.db.execute('DROP INDEX animation_attendance_users')
            self.db.execute("DELETE FROM app_settings WHERE key LIKE 'animation_auto_presence_%'")
            self.db.execute('PRAGMA user_version=21')
        with self.assertRaises(RuntimeError):family.migrate(self.db,fail_after=lambda db:(_ for _ in ()).throw(RuntimeError('simulated')))
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],21)
        self.assertFalse(self.db.execute("SELECT 1 FROM sqlite_master WHERE name='animation_walkins'").fetchone())
        family.migrate(self.db)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],22)
        self.assertEqual(before,{t:[tuple(r) for r in self.db.execute('SELECT * FROM '+t)] for t in tables})
        with self.db:self.db.execute('PRAGMA user_version=21')
        with self.assertRaises(RuntimeError):family.migrate(self.db,fail_after=lambda db:(_ for _ in ()).throw(RuntimeError('simulated')))
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],21)

    def test_disabled_public_module_preserves_capacity(self):
        with self.db:write_setting(self.db,'module_public_reservations','0')
        self.assertEqual(self.edit(expected_participants='2').status_code,400)
        self.assertEqual(self.db.execute('SELECT capacity FROM animation_reservation_config WHERE service_id=?',(self.service,)).fetchone()[0],6)

    def test_legacy_walkins_without_public_booking_retained(self):
        with self.db:
            self.db.execute('DELETE FROM animation_walkins')
            self.db.execute('UPDATE animation_reservation_config SET enabled=0,walkin_count=0')
            self.db.execute('UPDATE fablab_services SET actual_participants=5 WHERE id=?',(self.service,))
            attendance.ensure(self.db)
        self.assertEqual(attendance.summary(self.db,self.service,[])['anonymous'],5)
        self.assertEqual(self.db.execute('SELECT actual_participants FROM fablab_services WHERE id=?',(self.service,)).fetchone()[0],5)


def load_tests(loader,suite,pattern):
    result=unittest.TestSuite([loader.loadTestsFromTestCase(AttendanceTests)])
    result.addTests(CapacityMigrationTests(name) for name in CapacityMigrationTests.__dict__ if name.startswith('test_'))
    result.addTests(loader.loadTestsFromTestCase(PackagingTests))
    return result


class PackagingTests(unittest.TestCase):
    def test_docker_copies_every_runtime_module(self):
        import shlex,build_openfablab
        root=build_openfablab.ROOT;copied=set()
        for line in (root/'Dockerfile').read_text().splitlines():
            if line.startswith('COPY '):copied.update(shlex.split(line)[1:-1])
        runtime=[p.name for p in build_openfablab.included_paths() if p.parent==root and p.suffix=='.py' and not p.name.startswith('build_')]
        self.assertTrue(set(runtime)<=copied,set(runtime)-copied)
