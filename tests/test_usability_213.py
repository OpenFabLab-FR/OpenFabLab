"""2.13: fictional fixtures, deterministic UTC boundaries and real HTTP saves."""
import json,re,unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from html.parser import HTMLParser
from tests import test_families as families
from app import write_setting,read_setting,available_rental_catalog,parse_billing_form
from tablet_reservations import local_catalogue
from animation_publication import clock,visibility_key
from booking_presentation import sections
from reservations_sync import booking_reservation_status
import outbound_actions


class Forms(HTMLParser):
    def __init__(self):super().__init__();self.depth=0;self.nested=False
    def handle_starttag(self,tag,attrs):
        if tag=='form':self.depth+=1;self.nested|=self.depth>1
    def handle_endtag(self,tag):
        if tag=='form':self.depth-=1


class UsabilityTests(unittest.TestCase):
    def setUp(self):
        self.f=families.FamilyTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.db=self.f.db;self.client=self.f.client;self.service=self.f.service
    def configure(self,day='2026-10-25',start='10:00',end='12:00',opening=None):
        self.db.execute('UPDATE fablab_services SET service_date=?,start_time=?,end_time=? WHERE id=?',(day,start,end,self.service))
        self.db.execute('UPDATE animation_reservation_config SET signup_open_at=? WHERE service_id=?',(opening,self.service));self.db.commit()
    def catalogue(self,now,**kwargs):return local_catalogue(self.db,read_setting,now,include_closed=True,**kwargs)
    def service_dict(self):return dict(self.db.execute('SELECT s.*,c.* FROM fablab_services s JOIN animation_reservation_config c ON c.service_id=s.id WHERE s.id=?',(self.service,)).fetchone())
    def login(self):
        self.f.f.login_admin();self.client.get('/admin/reglages/affichage')
    def token(self):
        with self.client.session_transaction() as s:return s['pin_csrf']
    def save_animation(self,**extra):
        row=self.db.execute('SELECT * FROM fablab_services WHERE id=?',(self.service,)).fetchone()
        data=dict(service_type='animation',title=row['title'],service_date=row['service_date'],start_time=row['start_time'],end_time=row['end_time'],minimum_age='0',expected_participants='6',online_enabled='1',waitlist_enabled='1',signup_open_at='',csrf_token=self.token())
        data.update(extra);return self.client.post(f'/admin/animations/{self.service}/modifier',data=data,follow_redirects=True)
    def test_visible_before_opening_default_but_server_refuses_booking(self):
        self.configure(opening='2026-10-25T08:00:00+00:00');now=datetime(2026,10,24,10,tzinfo=timezone.utc)
        self.assertEqual(self.catalogue(now)[0]['availability_state'],'not_open')
        self.assertFalse(self.db.execute('SELECT 1 FROM app_settings WHERE key=?',(visibility_key(self.service),)).fetchone())
        import family_reservations as engine
        with patch.object(engine,'datetime') as dt:
            dt.now.return_value=now;dt.fromisoformat=datetime.fromisoformat
            with self.assertRaises(ValueError):engine.effective_service(self.db,self.service)
    def test_hidden_then_exact_opening(self):
        self.configure(opening='2026-10-25T07:00:00+00:00');write_setting(self.db,visibility_key(self.service),'1');self.db.commit()
        opening=datetime(2026,10,25,7,tzinfo=timezone.utc)
        self.assertFalse(self.catalogue(opening-timedelta(microseconds=1)))
        self.assertEqual(self.catalogue(opening)[0]['availability_state'],'available')
        self.assertTrue(self.catalogue(opening-timedelta(seconds=1),include_hidden=True))
    def test_unpublished_never_visible(self):
        self.configure();self.db.execute('UPDATE animation_reservation_config SET enabled=0');self.db.commit()
        self.assertFalse(self.catalogue(datetime(2026,10,24,tzinfo=timezone.utc)))
    def test_opening_dst_roundtrip_and_nonexistent_local_hour(self):
        from animation_publication import opening_value
        self.assertEqual(opening_value('2026-10-25T02:30','Europe/Paris','2026-10-25T01:30:00+00:00'),'2026-10-25T01:30:00+00:00')
        with self.assertRaises(ValueError):opening_value('2026-03-29T02:30','Europe/Paris')
        self.assertEqual(opening_value('2026-10-25T02:30','Europe/Paris'),'2026-10-25T00:30:00+00:00')
    def test_exact_end_and_24h_boundaries_including_dst(self):
        for day in ('2026-03-28','2026-10-24'):
            self.configure(day,end='23:00')
            info=clock(self.db,self.service_dict());end=datetime.fromisoformat(info['ends_at'])
            self.assertNotEqual(self.catalogue(end-timedelta(microseconds=1))[0]['availability_state'],'ended')
            self.assertEqual(self.catalogue(end)[0]['availability_state'],'ended')
            self.assertEqual(self.catalogue(end+timedelta(hours=24,microseconds=-1))[0]['availability_state'],'ended')
            self.assertFalse(self.catalogue(end+timedelta(hours=24)))
            self.assertFalse(self.catalogue(end+timedelta(hours=24,microseconds=1)))
    def test_last_active_slot_end_not_service_end(self):
        self.configure();self.db.execute("UPDATE animation_reservation_config SET booking_mode='slots'")
        for key,start,end,active in [('first','08:00','09:00',1),('last','09:30','10:00',1),('old','14:00','15:00',0)]:
            self.db.execute('INSERT INTO animation_slots VALUES(?,?,?,?,?,?)',(key,self.service,'2026-10-25T'+start+':00+00:00','2026-10-25T'+end+':00+00:00',4,active))
        self.db.commit();end=datetime(2026,10,25,10,tzinfo=timezone.utc)
        self.assertEqual(self.catalogue(end)[0]['ends_at'],end.isoformat())
        self.assertFalse(self.catalogue(end+timedelta(hours=24)))
    def test_publication_capability_keeps_old_plugin_payload_compatible(self):
        new=outbound_actions.public_catalogue(self.db,'production',True,True,True)[0]
        old=outbound_actions.public_catalogue(self.db,'production',True,True)[0]
        self.assertIn('publication',new);self.assertNotIn('publication',old)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],22)
    def test_incoherent_publication_capability_refused_before_catalogue(self):
        from outbound_sync import negotiate
        from unittest.mock import Mock
        client=Mock();client.post.return_value=dict(protocol_version=4,relay_revision=3,outbound_actions_v1=True,publication_visibility_v1=True)
        with self.assertRaises(ValueError):negotiate(client,'production')
    def test_visibility_saved_and_opening_local_roundtrip(self):
        self.login();response=self.save_animation(hide_before_opening='1',signup_open_at='2027-01-15T10:00')
        self.assertEqual(response.status_code,200)
        self.assertEqual(read_setting(self.db,visibility_key(self.service),'0'),'1')
        page=self.client.get(f'/admin/animations/{self.service}/modifier').get_data(as_text=True)
        self.assertIn('2027-01-15T10:00',page)
        self.save_animation(hide_before_opening='0');self.assertEqual(read_setting(self.db,visibility_key(self.service),'1'),'0')
    def test_status_groups_family_and_unknown_presence(self):
        import animation_attendance as attendance
        self.f.book([self.f.a,self.f.c]);rows=[dict(r,offer_expires_at=None) for r in self.db.execute('SELECT * FROM animation_bookings')]
        groups,offers=sections(rows,booking_reservation_status)
        self.assertEqual(groups[0]['count'],2);self.assertEqual(len(groups[0]['groups']),1);self.assertFalse(offers)
        self.assertEqual(attendance.summary(self.db,self.service,rows)['expected'],2)
        attendance.manual(self.db,self.service,rows[0]['external_uuid'],'absent','moderator')
        self.assertEqual(attendance.summary(self.db,self.service,self.db.execute('SELECT * FROM animation_bookings').fetchall())['expected'],1)
        self.assertEqual(booking_reservation_status(dict(self.db.execute('SELECT * FROM animation_bookings WHERE external_uuid=?',(rows[0]['external_uuid'],)).fetchone())),'confirmed')
    def test_offer_context_only_actual_pending_count_and_expiry(self):
        now=datetime.now(timezone.utc);expiry=(now+timedelta(hours=3)).isoformat()
        rows=[dict(external_uuid=str(i),group_uuid='family',status='offer_pending',offer_expires_at=expiry) for i in range(3)]
        groups,offers=sections(rows,booking_reservation_status,now)
        self.assertEqual(groups[1]['count'],3);self.assertEqual(offers,[dict(count=3,expires=expiry)])
        self.assertFalse(sections(rows,booking_reservation_status,now+timedelta(hours=4))[1])
    def test_available_seats_include_held_offer_without_changing_capacity_rules(self):
        from reservations_sync import booking_capacity_used
        self.f.book([self.f.a,self.f.b,self.f.c,self.f.d],staff=True)
        self.f.book([self.f.teen],owner=self.f.teen,staff=True)
        group=self.db.execute('SELECT group_uuid FROM animation_bookings WHERE user_id=?',(self.f.teen,)).fetchone()[0]
        expiry=(datetime.now(timezone.utc)+timedelta(hours=3)).isoformat()
        self.db.execute("UPDATE animation_bookings SET status='offer_pending' WHERE group_uuid=?",(group,))
        self.db.execute("UPDATE family_booking_groups SET status='offer_pending',offer_expires_at=? WHERE group_uuid=?",(expiry,group))
        self.db.execute('UPDATE animation_reservation_config SET capacity=5 WHERE service_id=?',(self.service,));self.db.commit()
        self.assertEqual(booking_capacity_used(self.db,self.service),5)
        self.login();page=self.client.get(f'/admin/animations/{self.service}/inscriptions').get_data(as_text=True)
        self.assertIn('Places disponibles',page);self.assertIn('1 place temporairement proposée',page);self.assertIn('incluse dans les places occupées',page)
        self.assertEqual(self.db.execute("SELECT count(*) FROM animation_bookings WHERE status='confirmed'").fetchone()[0],4)
    def test_rental_fields_are_unique_even_with_mobile_summaries(self):
        self.login();page=self.client.get('/admin/reglages/tarifs').get_data(as_text=True)
        for key, in self.db.execute('SELECT machine_key FROM rental_catalog WHERE archived=0'):
            for kind in ('name','active','monthly','deposit'):self.assertEqual(page.count('name="machine_'+kind+'_'+key+'"'),1)
        self.assertIn('aria-expanded="false"',page)
    def test_relay_error_opens_structure_panel_and_is_visible_above_it(self):
        self.login();self.db.execute("INSERT INTO wordpress_relay_state(environment,last_error) VALUES('test','Erreur fictive') ON CONFLICT(environment) DO UPDATE SET last_error='Erreur fictive'");self.db.commit()
        page=self.client.get('/admin/reglages/structure').get_data(as_text=True)
        self.assertIn('id="wordpress-settings" open',page);self.assertIn('Synchronisation WordPress à vérifier',page)
    def test_completed_negative_booking_result_is_not_a_sync_failure(self):
        self.login();self.db.execute("INSERT INTO wordpress_relay_state(environment,failed,retrying,last_error) VALUES('test',2,0,NULL) ON CONFLICT(environment) DO UPDATE SET failed=2,retrying=0,last_error=NULL");self.db.commit()
        page=self.client.get('/admin/reglages/structure').get_data(as_text=True)
        self.assertNotIn('id="wordpress-settings" open',page)
        self.assertNotIn('Synchronisation WordPress à vérifier',page)
    def test_settings_and_booking_forms_not_nested_and_renderable(self):
        self.login();self.f.book([self.f.a,self.f.c])
        for url in ['/admin/reglages/'+v for v in ('structure','affichage','donnees','tarifs','borne')]+[f'/admin/animations/{self.service}/inscriptions',f'/admin/animations/{self.service}/modifier']:
            page=self.client.get(url);self.assertEqual(page.status_code,200,url)
            parser=Forms();parser.feed(page.get_data(as_text=True));self.assertFalse(parser.nested,url);self.assertEqual(parser.depth,0,url)
    def test_display_common_save_preserves_calendar_and_validates_all(self):
        self.login();self.client.get('/admin/reglages/affichage')
        data=dict(csrf_token=self.token(),attendance_display='1',anonymous_visitor_color='#123456',attendance_reference='17',openlab_attendance_show_decimals='1',calendar_display_start='08:00',calendar_display_end='20:00')
        self.client.post('/admin/reglages/affichage/enregistrer',data=data)
        for key,val in [('anonymous_visitor_color','#123456'),('attendance_reference','17'),('calendar_display_start','08:00'),('openlab_attendance_show_decimals','1')]:self.assertEqual(read_setting(self.db,key),val)
        self.client.post('/admin/reglages/affichage/enregistrer',data=dict(data,anonymous_visitor_color='invalid',attendance_reference='22'))
        self.assertEqual(read_setting(self.db,'attendance_reference'),'17')
    def test_catalogue_active_inactive_and_reactivation(self):
        self.login();self.client.get('/admin/reglages/tarifs')
        rows=self.db.execute('SELECT * FROM rental_catalog').fetchall();data={'csrf_token':self.token()}
        for row in rows:
            k=row['machine_key'];data.update({f'machine_name_{k}':row['name'],f'machine_monthly_{k}':str(row['monthly_cents']/100),f'machine_deposit_{k}':str(row['deposit_cents']/100)})
        key=rows[0]['machine_key'];self.client.post('/admin/options/catalogue-location',data=data)
        self.assertFalse(available_rental_catalog(self.db))
        data['machine_active_'+key]='1';self.client.post('/admin/options/catalogue-location',data=data)
        self.assertIn(key,available_rental_catalog(self.db))
    def test_dossier_snapshot_name_and_prices_survive_catalogue_changes(self):
        key=self.db.execute('SELECT machine_key FROM rental_catalog LIMIT 1').fetchone()[0]
        record=dict(rental_machine_key=key,rental_machine_name='Ancienne machine fictive',rental_monthly_cents=1250,rental_deposit_cents=9500)
        self.db.execute('UPDATE rental_catalog SET name=?,monthly_cents=88800,deposit_cents=99900,active=0,archived=1 WHERE machine_key=?',('Nouveau nom',key));self.db.commit()
        machine=available_rental_catalog(self.db,record)[key]
        self.assertEqual((machine['name'],machine['monthly_cents'],machine['deposit_cents']),('Ancienne machine fictive',1250,9500))
    def test_legacy_dossier_missing_catalogue_never_switches_machine(self):
        record=dict(rental_machine_key='ancienne-reference-fictive',rental_machine_name='Machine historique fictive',rental_monthly_cents=1250,rental_deposit_cents=9500)
        self.assertNotIn(record['rental_machine_key'],available_rental_catalog(self.db))
        machine=available_rental_catalog(self.db,record)[record['rental_machine_key']]
        self.assertEqual((machine['name'],machine['monthly_cents'],machine['deposit_cents']),('Machine historique fictive',1250,9500))
    def test_moderator_and_unauthenticated_settings_refused(self):
        url='/admin/reglages/affichage/enregistrer'
        self.assertIn(self.client.post(url,data={'attendance_display':'1'}).status_code,(302,403))
        self.login()
        with self.client.session_transaction() as s:s['access_role']='moderator'
        self.assertIn(self.client.post(url,data={'csrf_token':self.token(),'attendance_display':'1'}).status_code,(302,403))

    def rental_payload(self):
        return dict(billing_type='rental',quote_date='2026-10-01',client_contact='Client FICTIF',client_structure='Association Exemple',address_line='1 voie Fictive',postal_code='00000',city='Commune Exemple',title='Location fictive',description='Exemple de location',activity_date='2026-11-01',activity_start_time='10:00',activity_end_time='11:00',rental_machine_key='prusa_mk39',rental_months='1',rental_end_date='2026-12-01',csrf_token=self.token())
    def test_referenced_machine_removal_keeps_quote_and_invoice_snapshot(self):
        self.login();payload=self.rental_payload()
        self.client.post('/admin/facturation/nouveau',data=payload)
        row=dict(self.db.execute('SELECT * FROM billing_records ORDER BY id DESC LIMIT 1').fetchone())
        key=row['rental_machine_key'];before=tuple(row[k] for k in ('rental_machine_name','rental_monthly_cents','rental_deposit_cents','amount_cents'))
        self.db.execute('UPDATE rental_catalog SET name=?,monthly_cents=99999,deposit_cents=88888 WHERE machine_key=?',('Nom modifié fictif',key));self.db.commit()
        response=self.client.post('/admin/options/catalogue-location/'+key+'/supprimer',data={'csrf_token':self.token()},follow_redirects=True)
        self.assertIn('Machine retirée du catalogue',response.get_data(as_text=True))
        self.assertNotIn(key,available_rental_catalog(self.db))
        self.assertEqual(self.db.execute('SELECT active,archived FROM rental_catalog WHERE machine_key=?',(key,)).fetchone()[:],(0,1))
        self.client.post(f"/admin/facturation/{row['id']}/modifier",data=dict(payload,quote_number=row['quote_number']))
        current=self.db.execute('SELECT * FROM billing_records WHERE id=?',(row['id'],)).fetchone()
        self.assertEqual(tuple(current[k] for k in ('rental_machine_name','rental_monthly_cents','rental_deposit_cents','amount_cents')),before)
        self.db.execute("UPDATE billing_records SET invoice_number='FACTURE-FICTIVE' WHERE id=?",(row['id'],));self.db.commit()
        page=self.client.get(f"/admin/facturation/{row['id']}").get_data(as_text=True)
        self.assertIn(row['rental_machine_name'],page)
        self.assertEqual(self.db.execute('SELECT amount_cents FROM billing_records WHERE id=?',(row['id'],)).fetchone()[0],before[-1])
    def test_unused_machine_physically_deleted_and_csrf_required(self):
        self.login();key='prusa_mk39';url='/admin/options/catalogue-location/'+key+'/supprimer'
        self.assertEqual(self.client.post(url,data={}).status_code,400)
        self.assertIsNotNone(self.db.execute('SELECT 1 FROM rental_catalog WHERE machine_key=?',(key,)).fetchone())
        self.client.post(url,data={'csrf_token':self.token()})
        self.assertIsNone(self.db.execute('SELECT 1 FROM rental_catalog WHERE machine_key=?',(key,)).fetchone())
    def test_independent_pin_forms_preserve_other_role(self):
        from pin_security import check_pin
        self.login();token=self.token()
        self.client.post('/admin/options/moderateur',data={'csrf_token':token,'moderator_pin':'9753'})
        self.assertTrue(check_pin(self.f.f.database_path,'moderator','9753'))
        self.assertTrue(check_pin(self.f.f.database_path,'admin','1379'))
        self.client.post('/admin/options/pin-administrateur',data={'csrf_token':token,'current_pin':'1379','new_pin':'2468','confirm_pin':'2468'})
        self.assertTrue(check_pin(self.f.f.database_path,'admin','2468'))
        self.assertTrue(check_pin(self.f.f.database_path,'moderator','9753'))
    def test_notice_save_keeps_retention_and_custom_model(self):
        self.login();self.client.get('/admin/reglages/donnees')
        with self.client.session_transaction() as s:token=s['evolution_csrf']
        before={k:v for k,v in self.db.execute("SELECT key,value FROM app_settings WHERE key LIKE 'retention_%'") if not k.startswith('retention_contact_notice_')}
        response=self.client.post('/admin/reglages/donnees/preavis',data={'evolution_csrf':token,'enabled':'1','days':'14','subject':'Information fictive','body':'Effacement prévu le {date_suppression}.'},follow_redirects=True)
        self.assertEqual(response.status_code,200)
        self.assertEqual(read_setting(self.db,'retention_contact_notice_days'),'14')
        self.assertEqual(read_setting(self.db,'retention_contact_notice_subject'),'Information fictive')
        for key,value in before.items():self.assertEqual(read_setting(self.db,key),value)
