"""2.7 candidate: fictional databases, no SMTP/Discord/WordPress network calls."""
import io
import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from datetime import datetime, timezone
from flask.testing import FlaskClient
from PIL import Image
from tests import test_app as fixtures
import app as application
import evolution_schema as schema
import resource_booking as resources
import welcome_mail as mail
from evolution_users import creation_message
from profile_archive import build_profile, parse_profile


class EvolutionTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.OpenFabLabTestCase();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.f.app.test_client_class=FlaskClient
        self.client=self.f.app.test_client()
        with self.client.session_transaction() as s:s['access_role']='admin';s['admin_authenticated']=True

    def db(self):return self.f.database()

    def post(self,path,values):
        page=self.client.get(path).get_data(as_text=True)
        match=re.search(r'name="evolution_csrf" value="([^"]+)"',page)
        self.assertIsNotNone(match,page[:200])
        return self.client.post(path,data=dict(values,evolution_csrf=match[1]))

    def set(self,**values):
        with self.db() as db:
            for key,value in values.items():application.write_setting(db,key,value)

    def values(self):
        return dict(public_id='7998',first_name='Éloïse-Exemple',last_name='FICTIF',birth_year='1990',
                    nationality='Française',city='Ville Exemple',email='camille@example.invalid',phone='0600000000',
                    phone_country_code='+33',category='user',active='1')

    def config(self):
        return dict(host='smtp.example.invalid',port=587,security='starttls',username='fictif',password='fictional-only',
                    sender_name='Atelier Exemple',sender_email='atelier@example.invalid',reply_to='reply@example.invalid')

    def resource(self,db,**extra):
        return resources.save_resource(db,dict(name='Machine Exemple',type_key='machine',active=True,
                                             price_cents=0,approval_required=False,**extra),'admin')

    def user(self,db):return db.execute('SELECT id FROM users WHERE active=1 LIMIT 1').fetchone()[0]

    def auth(self,db):
        db.execute("INSERT INTO authorizations VALUES('training-example','Initiation fictive','',1,'2026-01-01')")
        return 'training-example'

    def test_new_registry_default_and_generic_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'db'
            a=application.create_app(dict(TESTING=True,DATABASE=str(path),SECRET_KEY='fictional',SEED_DEMO_USERS=False,
                                          ADMIN_PIN=None,MODERATOR_PIN=None,WEATHER_ENABLED=False,AUTO_CLOSURE_WORKER=False))
            with a.app_context():
                db=application.get_database()
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],17)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM users').fetchone()[0],0)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM resources').fetchone()[0],0)
                self.assertEqual(schema.default_category(db),'user')
                self.assertEqual([r['type_key'] for r in db.execute('SELECT * FROM resource_types')],['machine'])
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertFalse(mail.path_for(path).exists())

    def test_category_rename_keeps_key_users_and_permissions(self):
        with self.db() as db:
            before=[tuple(r) for r in db.execute('SELECT id,category FROM users')]
            schema.save_category(db,'Membre & bénévole','#aabbcc',True,True,'user')
            self.assertEqual(before,[tuple(r) for r in db.execute('SELECT id,category FROM users')])
            self.assertEqual(schema.category_label(db,'user'),'Membre & bénévole')
        with self.client.session_transaction() as s:self.assertEqual(s['access_role'],'admin')

    def test_category_default_unique_active_and_no_duplicate_names(self):
        with self.db() as db:
            key=schema.save_category(db,'Équipe Exemple','#123456',True,True)
            self.assertEqual(schema.default_category(db),key)
            self.assertEqual(db.execute('SELECT SUM(is_default) FROM user_categories').fetchone()[0],1)
            with self.assertRaises(ValueError):schema.save_category(db,'Équipe Exemple','#123456',False,True,key)
            with self.assertRaises(sqlite3.IntegrityError):schema.save_category(db,'équipe exemple','#123456')

    def test_hide_delete_and_reassign_preserves_statistical_history(self):
        with self.db() as db:
            user=self.user(db);key=schema.save_category(db,'Projet Exemple','#123456')
            db.execute('UPDATE users SET category=? WHERE id=?',(key,user))
            db.execute("INSERT INTO sessions(user_id,check_in,check_out,statistical_category) VALUES(?,'2026-01-01T10:00:00','2026-01-01T11:00:00',?)",(user,key))
            with self.assertRaises(ValueError):schema.remove_category(db,key)
            self.assertEqual(schema.remove_category(db,key,'user'),'archived')
            self.assertEqual(db.execute('SELECT category FROM users WHERE id=?',(user,)).fetchone()[0],'user')
            self.assertTrue(db.execute('SELECT 1 FROM sessions WHERE statistical_category=?',(key,)).fetchone())
            unused=schema.save_category(db,'Inutilisée','#123456')
            self.assertEqual(schema.remove_category(db,unused),'deleted')
            with self.assertRaises(ValueError):schema.remove_category(db,'user')

    def test_custom_category_persists_after_initialize_and_badge(self):
        with self.f.app.app_context():
            db=application.get_database();key=schema.save_category(db,'Équipe café','#123456');db.commit()
            application.initialize_database();application.initialize_database()
            svg=application.generate_badge_svg(dict(first_name='Anne-Lise',public_id='7999',category=key))
            self.assertIn('Équipe café',svg.decode())
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_controlled_category_select_new_user_source(self):
        with self.db() as db:key=schema.save_category(db,'Projet Exemple','#123456')
        response=self.post('/admin/usagers/nouveau',dict(self.values(),category=key))
        self.assertEqual(response.status_code,302)
        with self.db() as db:
            row=db.execute("SELECT * FROM users WHERE public_id='7998'").fetchone()
            self.assertEqual((row['category'],row['created_source'],row['created_by_role']),(key,'admin','admin'))
        self.assertEqual(self.post('/admin/usagers/nouveau',dict(self.values(),category='arbitrary')).status_code,400)

    def test_user_form_csrf_not_bypassed_in_testing(self):
        self.assertEqual(self.client.post('/admin/usagers/nouveau',data=self.values()).status_code,400)
        self.assertEqual(self.client.post('/admin/reglages/usagers',data={'action':'category','name':'No CSRF'}).status_code,400)

    def test_moderator_provenance_not_admin(self):
        with self.client.session_transaction() as s:s['access_role']='moderator';s.pop('admin_authenticated',None)
        self.assertEqual(self.post('/admin/usagers/nouveau',self.values()).status_code,302)
        with self.db() as db:self.assertEqual(db.execute("SELECT created_source FROM users WHERE public_id='7998'").fetchone()[0],'moderator')
        self.assertIn(self.client.get('/admin/reglages/usagers').status_code,(302,403))

    def test_kiosk_opt_in_and_no_role_escalation_or_incoming_id(self):
        self.assertEqual(self.client.get('/inscription').status_code,404)
        self.set(self_enrollment_enabled='1')
        page=self.client.get('/inscription')
        self.assertEqual(page.status_code,200)
        with self.client.session_transaction() as s:self.assertNotIn('access_role',s);self.assertNotIn('admin_authenticated',s)
        self.assertEqual(self.post('/inscription',dict(first_name='Camille',last_name='Exemple',public_id='7998',category='staff',active='0',birth_year='1990',email='camille@example.invalid',phone='0600000000')).status_code,302)
        with self.db() as db:
            user=db.execute("SELECT * FROM users WHERE created_source='kiosk'").fetchone()
            self.assertNotEqual(user['public_id'],'7998');self.assertEqual(user['category'],'user');self.assertEqual(user['active'],1)
            self.assertEqual(user['email'],'camille@example.invalid')
        self.assertEqual(self.client.get('/inscription/qr.png').status_code,200)
        self.assertIn('no-store',self.client.get('/inscription/terminee').headers['Cache-Control'])
        self.assertEqual(self.client.get('/admin/ressources').status_code,302)

    def test_kiosk_timeout_csrf_receipt_and_rate_limit(self):
        self.set(self_enrollment_enabled='1');self.client.get('/inscription')
        self.assertEqual(self.client.post('/inscription',data={'first_name':'Camille','last_name':'Exemple'}).status_code,400)
        with self.client.session_transaction() as s:s['enrollment_started']=1;token=s['evolution_csrf']
        self.assertEqual(self.client.post('/inscription',data={'evolution_csrf':token}).status_code,400)
        for i in range(5):self.assertEqual(self.post('/inscription',{}).status_code,400)
        self.assertEqual(self.post('/inscription',{}).status_code,429)
        with self.client.session_transaction() as s:s['enrollment_receipt']={'id':1,'until':1}
        self.assertEqual(self.client.get('/inscription/qr.png').status_code,404)

    def test_smtp_failure_never_rolls_back_created_user(self):
        with mock.patch('welcome_mail.send_welcome',return_value=False):
            self.assertEqual(self.post('/admin/usagers/nouveau',dict(self.values(),send_welcome='1')).status_code,302)
        with self.db() as db:self.assertIsNotNone(db.execute("SELECT id FROM users WHERE public_id='7998'").fetchone())

    def test_welcome_private_config_and_qr_inline_attachment(self):
        mail.save_config(self.f.database_path,self.config())
        self.assertEqual(mail.path_for(self.f.database_path).stat().st_mode&0o777,0o600)
        values=dict(structure_name='Atelier <fictif>',first_name='Éloïse',last_name='EXEMPLE',public_id='7998',contact='',website='')
        message=mail.build_message(self.config(),'camille@example.invalid',values)
        self.assertIn('Bienvenue à Atelier',message['Subject'])
        png=[p for p in message.walk() if p.get_content_type()=='image/png']
        self.assertEqual(len(png),1);self.assertEqual(png[0].get_filename(),'OpenFabLab-QR.png')
        self.assertNotIn('inline',[p.get_content_disposition() for p in png]);self.assertIn('attachment',[p.get_content_disposition() for p in png])
        Image.open(io.BytesIO(png[0].get_payload(decode=True))).verify()
        with self.db() as db:self.assertNotIn('fictional-only','\n'.join(db.iterdump()))

    def test_template_validation_unicode_and_header_injection(self):
        with self.assertRaises(ValueError):mail.validate_template('{{unknown}}','Body')
        with self.assertRaises(ValueError):mail.validate_template('Bad\nheader','Body')
        with self.assertRaises(ValueError):mail.validate_config(dict(self.config(),sender_name='bad\r\nBcc: a@b.invalid'))
        self.assertEqual(mail.render('Bonjour {{ first_name }}',{'first_name':'Éloïse'}),'Bonjour Éloïse')
        with self.assertRaises(ValueError):mail.build_message(self.config(),None,{})

    def test_smtp_tls_and_starttls_transport(self):
        for kind,factory in [('starttls','SMTP'),('tls','SMTP_SSL')]:
            with mock.patch('welcome_mail.smtplib.'+factory) as smtp:
                smtp.return_value.__enter__.return_value.send_message.return_value={}
                mail.send(dict(self.config(),security=kind),'fake-message')
                instance=smtp.return_value.__enter__.return_value
                instance.login.assert_called_once();instance.send_message.assert_called_once()
                self.assertEqual(instance.starttls.call_count,1 if kind=='starttls' else 0)

    def test_resend_requires_confirmation_and_reports_failure(self):
        with self.db() as db:user=self.user(db)
        path='/admin/usagers/'+str(user)+'/bienvenue'
        self.client.get('/admin/usagers/'+str(user)+'/modifier')
        with self.client.session_transaction() as s:token=s['evolution_csrf']
        self.assertEqual(self.client.post(path,data={'evolution_csrf':token}).status_code,400)
        with mock.patch('welcome_mail.send_welcome',return_value=True) as send:
            self.assertEqual(self.client.post(path,data={'evolution_csrf':token,'confirmation':'ENVOYER'}).status_code,302)
            send.assert_called_once()

    def test_discord_disabled_and_strict_privacy_fields(self):
        with self.db() as db:
            user=dict(db.execute('SELECT * FROM users LIMIT 1').fetchone())
            user.update(first_name='Éloïse',last_name='EXEMPLE',email='PRIVATE@example.invalid',phone='PRIVATEPHONE',public_id='7998')
            self.assertIsNone(creation_message(db,user))
            for key in ('enabled','first_name','last_initial','source','time','category','age'):application.write_setting(db,'discord_new_user_'+key,'1')
            message=creation_message(db,user)
            self.assertIn('Éloïse E.',message)
            for forbidden in ('PRIVATE','7998','QR','EXEMPLE'):self.assertNotIn(forbidden,message)

    def test_resource_machine_import_idempotence_and_type(self):
        with self.db() as db:
            schema.sync_legacy_machines(db);before=[tuple(r) for r in db.execute('SELECT * FROM resources')]
            schema.sync_legacy_machines(db);self.assertEqual(before,[tuple(r) for r in db.execute('SELECT * FROM resources')])
            self.assertGreater(len(before),0)
            key=resources.save_type(db,'Salle Exemple','#123456')
            with self.assertRaises(sqlite3.IntegrityError):resources.save_type(db,'salle exemple','#123456')
            self.assertTrue(key.startswith('type_'))

    def test_masked_type_keeps_existing_resource_but_not_new_choices(self):
        with self.db() as db:
            key=resources.save_type(db,'Salle Exemple','#123456')
            values=dict(name='Salle Exemple',type_key=key,active=True,price_cents=0)
            resource=resources.save_resource(db,values,'admin')
            resources.save_type(db,'Salle Exemple','#123456',False,key,4)
            resources.save_resource(db,dict(values,name='Salle renommée'),'admin',resource)
            with self.assertRaises(ValueError):resources.save_resource(db,values,'admin')
            self.assertEqual(db.execute('SELECT type_key FROM resources WHERE resource_uuid=?',(resource,)).fetchone()[0],key)

    def test_resource_quote_uses_existing_billing_and_no_duplicate_dossier(self):
        with self.db() as db:
            r=self.resource(db);db.execute('UPDATE resources SET price_cents=1200 WHERE resource_uuid=?',(r,))
            key=resources.book(db,r,self.user(db),'2099-10-08T10:00+02:00','2099-10-08T11:00+02:00','admin')
        path='/admin/facturation/nouveau?resource_booking='+key
        page=self.client.get(path).get_data(as_text=True)
        token=re.search(r'name="evolution_csrf" value="([^"]+)"',page)[1]
        self.assertIn('name="resource_booking" value="'+key+'"',page)
        values=dict(resource_booking=key,evolution_csrf=token,billing_type='reservation',quote_date='2099-10-01',
                    client_contact='Camille Exemple',client_structure='Association Exemple',address_line='1 voie Fictive',
                    postal_code='00000',city='Ville Exemple',email='client@example.invalid',phone='',title='Machine Exemple',
                    description='Réservation fictive',activity_date='2099-10-08',activity_start_time='10:00',activity_end_time='11:00',
                    participants='1',rate_category='normal',rate_unit='hourly',rate_quantity='1',
                    travel_quantity='0',consumable_mode='included',consumable_quantity='0')
        response=self.client.post('/admin/facturation/nouveau',data=values)
        self.assertEqual(response.status_code,302,response.get_data(as_text=True)[:600])
        with self.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM billing_records').fetchone()[0],1)
            booking=db.execute('SELECT billing_record_id FROM resource_bookings WHERE booking_uuid=?',(key,)).fetchone()
            self.assertTrue(booking[0])
            self.assertEqual(db.execute('SELECT amount_cents FROM billing_records').fetchone()[0],1200)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM billing_clients').fetchone()[0],1)
        self.assertEqual(self.client.post('/admin/facturation/nouveau',data=values).status_code,409)

    def test_resource_booking_serialized_against_second_connection(self):
        import threading
        with self.db() as db:r=self.resource(db);user=self.user(db)
        first_ready=threading.Event();results=[]
        def attempt(first):
            connection=self.db()
            try:
                if not first:first_ready.wait(5)
                connection.execute('BEGIN IMMEDIATE')
                if first:first_ready.set()
                resources.book(connection,r,user,'2099-01-01T10:00+01:00','2099-01-01T11:00+01:00','admin')
                connection.commit();results.append('confirmed')
            except ValueError:connection.rollback();results.append('refused')
            finally:connection.close()
        a=threading.Thread(target=attempt,args=(True,));b=threading.Thread(target=attempt,args=(False,));a.start();b.start();a.join(10);b.join(10)
        self.assertEqual(sorted(results),['confirmed','refused'])

    def test_smtp_success_and_failure_status_time_persist(self):
        mail.save_config(self.f.database_path,self.config())
        with self.db() as db:
            db.execute("UPDATE users SET email='camille@example.invalid' WHERE id=(SELECT MIN(id) FROM users)")
            user=db.execute('SELECT * FROM users LIMIT 1').fetchone()
            with mock.patch('welcome_mail.send'):
                self.assertTrue(mail.send_welcome(db,self.f.database_path,user))
            before=db.execute('SELECT welcome_sent_at FROM users WHERE id=?',(user['id'],)).fetchone()[0]
            with mock.patch('welcome_mail.send',side_effect=OSError('fake outage')):
                self.assertFalse(mail.send_welcome(db,self.f.database_path,user))
            row=db.execute('SELECT welcome_status,welcome_sent_at FROM users WHERE id=?',(user['id'],)).fetchone()
            self.assertEqual(row[:],('failed',before))

    def test_profile_import_registries_through_preview_and_confirmation(self):
        entries=[dict(category_key='user',name='Membre Exemple',color='#123456',active=1,sort_order=0,is_default=1)]
        raw=build_profile({'self_enrollment_enabled':'1','welcome_default':'0'},[],{},[],entries,[])
        with self.client.session_transaction() as s:s['pin_csrf']='fixture-profile-token'
        data=dict(csrf_token='fixture-profile-token',step='preview',profile_file=(io.BytesIO(raw),'fictional.openfablab-profile.zip'))
        self.assertEqual(self.client.post('/admin/profil/importer',data=data).status_code,302)
        data.update(step='apply',confirmation='IMPORTER LE PROFIL',profile_file=(io.BytesIO(raw),'fictional.openfablab-profile.zip'))
        self.assertEqual(self.client.post('/admin/profil/importer',data=data).status_code,302)
        with self.db() as db:
            self.assertEqual(schema.category_label(db,'user'),'Membre Exemple')
            self.assertEqual(schema.default_category(db),'user')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_future_schema_refused_before_any_write(self):
        with self.db() as db:
            db.execute('PRAGMA user_version=99');db.commit()
            with self.assertRaises(RuntimeError):schema.backup_before_evolution(db,self.f.database_path)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],99)

    def test_resource_free_auto_and_paid_approval_transitions(self):
        with self.db() as db:
            user=self.user(db);r=self.resource(db)
            booking=resources.book(db,r,user,'2099-01-01T10:00:00+01:00','2099-01-01T11:00:00+01:00','moderator')
            self.assertEqual(db.execute('SELECT status,amount_cents FROM resource_bookings WHERE booking_uuid=?',(booking,)).fetchone()[:],('confirmed',0))
            resources.transition(db,booking,'performed','moderator')
            with self.assertRaises(ValueError):resources.transition(db,booking,'confirmed','admin')
            db.execute('UPDATE resources SET price_cents=1200,approval_required=1 WHERE resource_uuid=?',(r,))
            b=resources.book(db,r,user,'2099-01-02T10:00:00+01:00','2099-01-02T11:00:00+01:00','admin')
            self.assertEqual(db.execute('SELECT status,amount_cents FROM resource_bookings WHERE booking_uuid=?',(b,)).fetchone()[:],('requested',1200))
            resources.transition(db,b,'confirmed','admin');resources.transition(db,b,'cancelled','moderator')

    def test_resource_overlap_offsets_independent_other_and_cancellation(self):
        with self.db() as db:
            r=self.resource(db);other=self.resource(db);user=self.user(db)
            b=resources.book(db,r,user,'2099-01-01T10:00:00+01:00','2099-01-01T11:00:00+01:00','admin')
            with self.assertRaises(ValueError):resources.book(db,r,user,'2099-01-01T09:30:00+00:00','2099-01-01T10:30:00+00:00','admin')
            resources.book(db,other,user,'2099-01-01T10:00:00+01:00','2099-01-01T11:00:00+01:00','admin')
            resources.transition(db,b,'cancelled','admin')
            resources.book(db,r,user,'2099-01-01T10:00:00+01:00','2099-01-01T11:00:00+01:00','admin')

    def test_permissions_checked_inside_resource_mutations(self):
        with self.db() as db:
            with self.assertRaises(ValueError):resources.save_resource(db,dict(name='Denied'),'moderator')
            r=self.resource(db);user=self.user(db)
            with self.assertRaises(ValueError):resources.book(db,r,user,'2099-01-01T10:00+01:00','2099-01-01T11:00+01:00','public')
            b=resources.book(db,r,user,'2099-01-01T10:00+01:00','2099-01-01T11:00+01:00','admin')
            with self.assertRaises(ValueError):resources.transition(db,b,'cancelled','public')

    def test_training_required_permanent_expired_revoked_and_override(self):
        with self.db() as db:
            user=self.user(db);auth=self.auth(db);r=self.resource(db,required_authorization=auth)
            args=(db,r,user,'2099-01-01T10:00+01:00','2099-01-01T11:00+01:00')
            with self.assertRaises(ValueError):resources.book(*args,'moderator')
            with self.assertRaises(ValueError):resources.book(*args,'admin')
            override=resources.book(*args,'admin','Encadrement explicite fictif')
            resources.transition(db,override,'cancelled','admin')
            grant=resources.grant(db,user,auth,'2026-10-01','Équipe Exemple','moderator')
            self.assertTrue(resources.authorization_valid(db,user,auth,'2099-01-01'))
            resources.book(*args,'moderator')
            resources.revoke(db,grant,'admin','Renouvellement nécessaire')
            self.assertFalse(resources.authorization_valid(db,user,auth,'2099-01-01'))
            resources.grant(db,user,auth,'2026-10-01','Équipe Exemple','admin','2027-01-01')
            self.assertFalse(resources.authorization_valid(db,user,auth,'2099-01-01'))
            self.assertGreater(db.execute('SELECT COUNT(*) FROM evolution_audit').fetchone()[0],4)

    def test_authorization_covers_whole_range(self):
        with self.db() as db:
            user=self.user(db);auth=self.auth(db)
            resources.grant(db,user,auth,'2026-10-01','Équipe Exemple','admin','2027-01-01')
            self.assertTrue(resources.authorization_valid(db,user,auth,'2027-01-01','2027-01-01'))
            self.assertFalse(resources.authorization_valid(db,user,auth,'2027-01-01','2027-01-02'))

    def test_profile_transports_registries_preferences_not_smtp(self):
        with self.db() as db:
            schema.save_category(db,'Projet Exemple','#123456',True,True)
            settings={'structure_name':'Atelier Exemple','self_enrollment_enabled':'1','discord_new_user_enabled':'0','welcome_subject':mail.SUBJECT,'welcome_body':mail.BODY}
            entries=[{k:r[k] for k in ('category_key','name','color','active','sort_order','is_default')} for r in schema.categories(db,True)]
            types=[{k:r[k] for k in ('type_key','name','color','active','sort_order')} for r in db.execute('SELECT * FROM resource_types')]
            parsed=parse_profile(build_profile(settings,[],{},[],entries,types))
            self.assertEqual(parsed['categories'],entries);self.assertEqual(parsed['resource_types'],types)
            self.assertEqual(parsed['settings']['self_enrollment_enabled'],'1')
            self.assertNotIn('password',json.dumps(parsed))
            self.assertEqual(parse_profile(build_profile({},[],{}))['categories'],[])

    def test_calendar_overlap_placement_touching_and_read_only(self):
        from fablab_calendar import position_overlaps
        events=[dict(start_minute=600,end_minute=660),dict(start_minute=630,end_minute=690),dict(start_minute=690,end_minute=720)]
        arranged=position_overlaps(events)
        self.assertEqual([e['width'] for e in arranged],[50,50,100])
        self.assertNotEqual(arranged[0]['left'],arranged[1]['left'])
        with self.db() as db:before=db.total_changes
        for view in ('week','month'):
            response=self.client.get('/admin/calendrier?view='+view+'&date=2099-01-01')
            self.assertEqual(response.status_code,200)
            self.assertIn('Aujourd’hui',response.get_data(as_text=True))
        self.assertEqual(self.client.get('/admin/calendrier?view=bad').status_code,400)
        self.assertEqual(self.client.get('/admin/calendrier?date=bad').status_code,400)

    def test_calendar_rental_started_before_visible_week_is_not_lost(self):
        with self.db() as db:
            timestamp='2099-09-01T00:00:00+00:00'
            service=db.execute("INSERT INTO fablab_services(service_type,title,service_date,created_at,updated_at) VALUES('rental','Location Exemple longue','2099-09-01',?,?)",(timestamp,timestamp)).lastrowid
            db.execute('''INSERT INTO billing_records(quote_number,quote_date,client_contact,client_structure,address_line,postal_code,city,title,description,activity_date,rate_category,rate_unit,rental_end_date,service_id,created_at,updated_at)
                VALUES('2099.1','2099-09-01','Camille Exemple','Atelier Exemple','Voie fictive','00000','Ville Exemple','Location Exemple longue','Fictive','2099-09-01','normal','hourly','2099-10-31',?,?,?)''',(service,timestamp,timestamp))
        page=self.client.get('/admin/calendrier?date=2099-10-08').get_data(as_text=True)
        self.assertEqual(len(re.findall(r'class="calendar-month-event"[^>]*>[^<]*Location Exemple longue</a>',page)),7)
        self.assertNotRegex(page,r'class="calendar-event"[^>]*>[\s\S]*?<strong>Location Exemple longue</strong>')

    def test_new_pages_render_admin_and_calendar_moderator(self):
        for path in ('/admin/reglages/usagers','/admin/reglages/structure','/admin/ressources','/admin/ressources/reservations','/admin/habilitations','/admin/calendrier'):
            with self.subTest(path=path):self.assertEqual(self.client.get(path).status_code,200)
        with self.client.session_transaction() as s:s['access_role']='moderator';s.pop('admin_authenticated',None)
        self.assertEqual(self.client.get('/admin/calendrier').status_code,200)
        self.assertIn(self.client.get('/admin/reglages/integrations').status_code,(302,403))


class EvolutionMigrationTests(unittest.TestCase):
    def test_realistic_schema13_migration_backup_preserves_business_and_private_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'openfablab.db'
            config=dict(TESTING=True,DATABASE=str(path),SECRET_KEY='fictional',SEED_DEMO_USERS=False,ADMIN_PIN=None,
                        MODERATOR_PIN=None,WEATHER_ENABLED=False,AUTO_CLOSURE_WORKER=False)
            with mock.patch.object(application,'migrate_evolution',lambda db, **kwargs:None):application.create_app(config)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],13)
                db.execute("INSERT INTO users(public_id,first_name,last_name,category,created_at) VALUES('7999','Ancienne','FICTIVE','user','2026-01-01')")
                db.execute("INSERT INTO sessions(user_id,check_in,check_out) VALUES(1,'2026-01-01T10:00:00','2026-01-01T11:00:00')")
                db.execute("INSERT INTO visitors(created_at) VALUES('2026-01-01T10:00:00')")
                db.execute("UPDATE app_settings SET value='Atelier Exemple configuré' WHERE key='structure_name'")
                db.execute("INSERT INTO rental_catalog(machine_key,name,monthly_cents,deposit_cents,created_at,updated_at) VALUES('example','Machine Exemple',1200,2000,'2026-01-01','2026-01-01')")
                db.execute("UPDATE sqlite_sequence SET seq=999 WHERE name='users'")
            # Complete existing normalization without enabling schema 14 yet.
            with mock.patch.object(application,'migrate_evolution',lambda db, **kwargs:None):application.create_app(config)
            with sqlite3.connect(path) as db:
                names=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                before={t:db.execute('SELECT * FROM '+t).fetchall() for t in names}
                columns=[r[1] for r in db.execute('PRAGMA table_info(users)')]
            private=Path(folder)/'branding';private.mkdir();(private/'fictive.txt').write_bytes(b'private fictional resource')
            previous_backups=set((Path(folder)/'migration-backups').glob('*.db'))
            app=application.create_app(config)
            with app.app_context():
                db=application.get_database()
                for table,rows in before.items():
                    if table=='users':actual=db.execute('SELECT '+','.join(columns)+' FROM users').fetchall()
                    elif table=='app_settings':continue
                    else:actual=db.execute('SELECT * FROM '+table).fetchall()
                    self.assertEqual([tuple(r) for r in actual],rows,table)
                self.assertEqual(db.execute("SELECT created_source FROM users").fetchone()[0],'historical')
                self.assertEqual(db.execute("SELECT value FROM app_settings WHERE key='structure_name'").fetchone()[0],'Atelier Exemple configuré')
                self.assertEqual(db.execute("SELECT seq FROM sqlite_sequence WHERE name='users'").fetchone()[0],999)
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],17)
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                application.initialize_database();self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            backups=list(set((Path(folder)/'migration-backups').glob('*.db'))-previous_backups);self.assertEqual(len(backups),1)
            with sqlite3.connect(backups[0]) as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],13)
            self.assertEqual((private/'fictive.txt').read_bytes(),b'private fictional resource')

    def test_unknown_legacy_constraint_refuses_without_partial_schema(self):
        with sqlite3.connect(':memory:') as db:
            db.row_factory=sqlite3.Row
            db.execute('CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT,category TEXT)');db.commit()
            with self.assertRaises(RuntimeError):schema.migrate(db)
            self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='user_categories'").fetchone())
            self.assertEqual(db.execute('PRAGMA foreign_keys').fetchone()[0],1)


if __name__=='__main__':unittest.main()
