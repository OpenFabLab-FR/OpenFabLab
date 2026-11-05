"""New views: rights, CSRF, calendar placement and public loan privacy."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from tests import test_v214_core as core
import app
import fablab_calendar
import machine_maintenance as machines
import resource_booking as bookings
import resource_loans as loans
import public_snapshot


class Views(unittest.TestCase):
    setUp=core.NewVersion.setUp
    login=core.NewVersion.login

    def make_booking(self,begin=None,end=None):
        begin=begin or datetime.now(timezone.utc)+timedelta(days=10)
        end=end or begin+timedelta(hours=2)
        key=bookings.book(self.db,self.key,self.f.a,begin.isoformat(),end.isoformat(),'admin')
        self.db.commit()
        return key,begin,end

    def test_team_handover_and_return_route_csrf_and_no_general_rights(self):
        key,_,_=self.make_booking()
        route='/admin/locations/booking/'+key+'/materiel'
        self.assertNotEqual(self.client.post(route,data=dict(action='handover')).status_code,200)
        token=self.login('moderator')
        self.assertEqual(self.client.post(route,data=dict(action='handover')).status_code,400)
        self.assertEqual(self.client.post(route,data=dict(action='handover',evolution_csrf=token)).status_code,302)
        self.assertTrue(loans.outstanding(self.db,self.key))
        self.assertEqual(self.client.post(route,data=dict(action='return',evolution_csrf=token)).status_code,302)
        self.assertFalse(loans.outstanding(self.db,self.key))
        self.assertNotEqual(self.client.get('/admin/reglages/systeme/mises-a-jour').status_code,200)

    def test_user_history_view_access_mod_and_admin_without_user_edit_permissions(self):
        self.make_booking()
        self.login('moderator')
        route='/admin/usagers/'+str(self.f.a)+'/suivi'
        page=self.client.get(route)
        self.assertEqual(page.status_code,200)
        self.assertIn('Locations et prêts',page.text)
        self.assertNotIn('Suspendre les nouvelles réservations',page.text)
        self.assertNotEqual(self.client.get('/admin/usagers/'+str(self.f.a)+'/modifier').status_code,200)

    def test_admin_user_edit_and_resource_forms_render(self):
        self.make_booking();self.login()
        for route in ('/admin/usagers/'+str(self.f.a)+'/modifier','/admin/ressources/reservations',
                      '/admin/ressources','/admin/ressources/maintenance'):
            with self.subTest(route=route):self.assertEqual(self.client.get(route,follow_redirects=True).status_code,200)

    def test_multiday_and_midnight_crossing_stay_in_upper_band_same_business_key(self):
        self.login()
        for begin,end in [(datetime(2030,6,4,20,tzinfo=timezone.utc),datetime(2030,6,5,6,tzinfo=timezone.utc)),
                          (datetime(2030,6,4,12,tzinfo=timezone.utc),datetime(2030,6,7,12,tzinfo=timezone.utc))]:
            key,_,_=self.make_booking(begin,end)
            with self.f.f.app.test_request_context('/admin/calendrier'):
                from flask import session
                session['access_role']='admin'
                result=fablab_calendar.calendar_view(self.db,{'date':str(begin.date()),'view':'week'},SimpleNamespace(**vars(app)))
            references=[e for day in result['days'] for e in day['events'] if e['key']==key]
            self.assertGreaterEqual(len(references),2)
            self.assertTrue(all(e['all_day'] for e in references))
            self.assertEqual(len({e['key'] for e in references}),1)
            self.assertTrue(all(e['span_start'] and e['span_end'] for e in references))
            bars=[bar for bar in result['week_rentals'] if bar['event']['key']==key]
            self.assertEqual(len(bars),1)
            self.assertEqual(bars[0]['end']-bars[0]['start'],len(references))
            self.assertIn('Location · ',bars[0]['event']['title'])
            self.assertIn('Remise non enregistrée',bars[0]['event']['details'])
            page=self.client.get('/admin/calendrier?date='+str(begin.date()))
            self.assertEqual(page.status_code,200)
            self.assertEqual(page.text.count('data-key="'+key+'"'),1)
            self.assertNotEqual(result['visible_start'],'00:00')
            self.assertNotEqual(result['visible_end'],'24:00')
            self.db.execute('DELETE FROM resource_bookings WHERE booking_uuid=?',(key,));self.db.commit()

    def test_same_day_remains_timed_and_booking_is_not_rewritten(self):
        self.login();key,begin,_=self.make_booking(datetime(2030,6,4,10,tzinfo=timezone.utc),datetime(2030,6,4,12,tzinfo=timezone.utc))
        before=tuple(self.db.execute('SELECT * FROM resource_bookings WHERE booking_uuid=?',(key,)).fetchone())
        with self.f.f.app.test_request_context('/admin/calendrier'):
            result=fablab_calendar.calendar_view(self.db,{'date':str(begin.date())},SimpleNamespace(**vars(app)))
        events=[e for day in result['days'] for e in day['events'] if e['key']==key]
        self.assertEqual(len(events),1);self.assertFalse(events[0]['all_day'])
        self.assertEqual(before,tuple(self.db.execute('SELECT * FROM resource_bookings WHERE booking_uuid=?',(key,)).fetchone()))

    def test_free_booking_and_handover_count_once_and_never_change_availability_early(self):
        import admin_summary
        self.login()
        key,begin,end=self.make_booking(datetime(2030,6,4,10,tzinfo=timezone.utc),datetime(2030,6,4,12,tzinfo=timezone.utc))
        self.db.execute("UPDATE resource_bookings SET amount_cents=0,status='confirmed' WHERE booking_uuid=?",(key,))
        self.db.commit()
        def card(when):
            with self.f.f.app.test_request_context('/admin'):
                return next(c for c in admin_summary.build(self.db,app.load_modules(self.db),'admin',when)['cards'] if c['icon']=='↔')
        self.assertEqual(card(begin-timedelta(seconds=1))['count'],0)
        self.assertEqual(card(begin)['count'],1)
        self.assertIn('0 avec remise',card(begin)['detail'])
        self.assertTrue(loans.availability(self.db,self.key,begin)['available'])
        loans.transition(self.db,'booking',key,'handover','admin',current=begin)
        self.assertEqual(card(end+timedelta(hours=2))['count'],1)
        self.assertIn('1 avec remise',card(end)['detail'])
        loans.transition(self.db,'booking',key,'return','admin',current=end+timedelta(hours=2))
        self.assertEqual(card(end+timedelta(hours=2))['count'],0)

    def test_effective_public_status_preserves_visibility_never_borrower(self):
        key,begin,_=self.make_booking()
        machines.set_condition(self.db,self.key,dict(status='operational',visibility_controls='1',public_visible='1'),'admin','admin')
        self.db.commit();loans.transition(self.db,'booking',key,'handover','admin',current=begin)
        values=machines.public_machines(self.db,True)
        self.assertEqual(values[0]['status'],'loaned')
        self.assertEqual(set(values[0]),{'id','name','status','reason','return_estimate'})
        self.assertNotIn('Fictif',str(values));self.assertNotIn('email',str(values))
        old=public_snapshot.build(self.db,'production',machines=True)
        new=public_snapshot.build(self.db,'production',machines=True,availability=True)
        self.assertEqual(old['machines'][0]['status'],'out_of_service')
        self.assertEqual(new['machines'][0]['status'],'loaned')
        machines.set_condition(self.db,self.key,dict(status='operational',visibility_controls='1',public_visible='0'),'admin','admin')
        self.db.commit();self.assertFalse(machines.public_machines(self.db))

if __name__=='__main__':unittest.main()
