"""Fictional data only; real SQLite, Flask and generators' download headers."""
import json,sqlite3,unittest
from datetime import date,datetime,timedelta,timezone
from unittest.mock import patch
from pathlib import Path
from zoneinfo import ZoneInfo
from tests import test_v214_core as core
import app,family_model,resource_booking as bookings,resource_lifecycle as life,machine_maintenance as machines
import public_calendar_history as history,public_snapshot

class Lifecycle(unittest.TestCase):
    setUp=core.NewVersion.setUp
    login=core.NewVersion.login
    def resource(self):
        key=bookings.save_resource(self.db,dict(name='Ressource fictive créée par erreur',type_key='machine',active='1'),'admin');self.db.commit();return key
    def change(self,key,action,confirmation='',role='admin'):
        self.db.commit()
        with self.db:
            self.db.execute('BEGIN IMMEDIATE');return life.change(self.db,key,action,role,confirmation)
    def test_archive_restore_retains_settings_and_private_history(self):
        key=self.resource();machines.set_condition(self.db,key,dict(status='out_of_service',visibility_controls='1',public_visible='1',public_reason='Panne fictive'),'admin','admin');self.db.commit()
        before=tuple(self.db.execute('SELECT * FROM machine_condition WHERE resource_uuid=?',(key,)).fetchone())
        self.assertIn(key,[r['id'] for r in machines.public_machines(self.db)])
        self.change(key,'archive');self.assertTrue(life.resource(self.db,key)['archived_at']);self.assertEqual(life.resource(self.db,key)['active'],1)
        self.assertNotIn(key,[r['id'] for r in machines.public_machines(self.db)]);self.assertNotIn(key,[r['id'] for r in machines.public_machines(self.db,True)])
        self.assertNotIn(key,[r['resource_uuid'] for r in machines.directory(self.db)]);self.assertFalse(machines.technically_available(self.db,key))
        self.change(key,'restore');self.assertIsNone(life.resource(self.db,key)['archived_at']);self.assertEqual(tuple(self.db.execute('SELECT * FROM machine_condition WHERE resource_uuid=?',(key,)).fetchone()),before)
        self.assertIn(key,[r['id'] for r in machines.public_machines(self.db)])
    def test_archive_distinct_from_temporarily_out_of_service(self):
        key=self.resource();machines.set_condition(self.db,key,dict(status='out_of_service'),'admin','admin');self.db.commit()
        self.assertIn(key,[r['resource_uuid'] for r in machines.directory(self.db)]);self.assertIsNone(life.resource(self.db,key)['archived_at'])
    def test_future_or_overdue_pending_reminder_blocks_without_mutation(self):
        key=self.resource();machines.reminder(self.db,key,dict(due_on='2020-01-01',subject='Rappel fictif'),'admin','admin');self.db.commit()
        before=[tuple(r) for r in self.db.execute('SELECT * FROM machine_reminders')]
        with self.assertRaisesRegex(ValueError,'Archivage impossible'):self.change(key,'archive')
        self.assertIsNone(life.resource(self.db,key)['archived_at']);self.assertEqual(before,[tuple(r) for r in self.db.execute('SELECT * FROM machine_reminders')])
    def test_future_booking_blocks_then_cancel_allows_archive_but_not_deletion(self):
        key=self.resource();start=datetime.now(timezone.utc)+timedelta(days=10);end=start+timedelta(hours=2)
        booking=bookings.book(self.db,key,self.f.a,start.isoformat(),end.isoformat(),'admin');self.db.commit()
        with self.assertRaises(ValueError):self.change(key,'archive')
        bookings.transition(self.db,booking,'cancelled','admin');self.db.commit();self.change(key,'archive')
        with self.assertRaisesRegex(ValueError,'Suppression impossible'):self.change(key,'delete',key)
        self.assertEqual(self.db.execute('SELECT status FROM resource_bookings WHERE booking_uuid=?',(booking,)).fetchone()[0],'cancelled')
    def test_archived_resource_refuses_new_booking_even_module_disabled(self):
        key=self.resource();self.change(key,'archive');app.write_setting(self.db,'module_maintenance','0')
        with self.assertRaises(ValueError):bookings.book(self.db,key,self.f.a,'2029-01-01T12:00:00Z','2029-01-01T13:00:00Z','admin')
    def test_empty_record_delete_requires_confirmation_and_admin(self):
        key=self.resource()
        for role in ('moderator','user'):
            with self.assertRaises(PermissionError):self.change(key,'delete',key,role)
        with self.assertRaises(ValueError):self.change(key,'delete','wrong')
        self.change(key,'delete',key);self.assertFalse(self.db.execute('SELECT 1 FROM resources WHERE resource_uuid=?',(key,)).fetchone())
    def test_history_intervention_reminder_and_unknown_fk_block_delete(self):
        for kind in ('intervention','reminder','condition','unknown'):
            key=self.resource()
            if kind=='intervention':machines.intervention(self.db,key,dict(performed_on='2020-01-01',kind='care',description='Nettoyage fictif'),'admin','admin')
            elif kind=='reminder':machines.reminder(self.db,key,dict(due_on='2030-01-01',subject='Fictif'),'admin','admin')
            elif kind=='condition':machines.set_condition(self.db,key,dict(status='operational'),'admin','admin')
            else:
                self.db.execute('CREATE TABLE fictional_child(resource TEXT REFERENCES resources(resource_uuid) ON DELETE CASCADE)');self.db.execute('INSERT INTO fictional_child VALUES(?)',(key,))
            self.db.commit()
            with self.assertRaises(ValueError):self.change(key,'delete',key)
            self.assertTrue(life.resource(self.db,key))
    def test_legacy_catalogue_not_deleted_or_recreated(self):
        key=self.key;before=tuple(self.db.execute('SELECT * FROM rental_catalog WHERE machine_key=?',(life.resource(self.db,key)['legacy_machine_key'],)).fetchone())
        with self.assertRaises(ValueError):self.change(key,'delete',key)
        self.change(key,'archive');machines.directory(self.db);self.db.commit()
        self.assertTrue(life.resource(self.db,key)['archived_at']);self.assertEqual(tuple(self.db.execute('SELECT * FROM rental_catalog WHERE machine_key=?',(life.resource(self.db,key)['legacy_machine_key'],)).fetchone()),before)
        self.assertNotIn(life.resource(self.db,key)['legacy_machine_key'],app.load_rental_catalog(self.db))
    def test_future_rental_blocks_archival_and_old_invoice_stays_untouched(self):
        self.login();machine=life.resource(self.db,self.key)['legacy_machine_key']
        response=self.client.post('/admin/facturation/nouveau',data=dict(billing_type='rental',quote_date='2026-11-03',client_contact='Camille Fictif',client_structure='Structure fictive',address_line='1 rue Exemple',postal_code='00000',city='Ville Fictive',email='camille@example.invalid',phone='0600000000',title='Location fictive',description='Test de conservation',activity_date='2030-01-01',activity_start_time='10:00',activity_end_time='10:30',activity_time_details='10:00–10:30',rental_machine_key=machine,rental_months='1',rental_end_date='2030-02-01'))
        record=self.db.execute('SELECT * FROM billing_records WHERE rental_machine_key=?',(machine,)).fetchone();self.assertIsNotNone(record,response.text)
        before=tuple(record)
        with self.assertRaises(ValueError):self.change(self.key,'archive')
        self.assertEqual(before,tuple(self.db.execute('SELECT * FROM billing_records WHERE id=?',(record['id'],)).fetchone()))
        self.db.execute("UPDATE billing_records SET activity_date='2020-01-01',rental_end_date='2020-02-01' WHERE id=?",(record['id'],));self.db.commit()
        before=tuple(self.db.execute('SELECT * FROM billing_records WHERE id=?',(record['id'],)).fetchone());self.change(self.key,'archive');self.assertEqual(before,tuple(self.db.execute('SELECT * FROM billing_records WHERE id=?',(record['id'],)).fetchone()))
    def test_archived_resource_cannot_reopen_completed_reminder(self):
        key=self.resource();reminder=machines.reminder(self.db,key,dict(due_on='2020-01-01',subject='Contrôle fictif'),'admin','admin');self.db.commit()
        machines.reminder_action(self.db,key,dict(identifier=reminder,action='reminder_close',revision='1'),'admin','admin');self.db.commit();self.change(key,'archive')
        with self.assertRaises(ValueError):machines.reminder(self.db,key,dict(due_on='2030-01-01',subject='Contrôle fictif',state='pending',revision='2'),'admin','admin',reminder)
    def test_http_permissions_csrf_filter_and_restore(self):
        key=self.resource();token=self.login('moderator')
        self.assertEqual(self.client.post('/admin/ressources',data=dict(action='archive',key=key,evolution_csrf=token)).status_code,403)
        with self.client.session_transaction() as session:session.clear()
        token=self.login('admin');self.assertEqual(self.client.post('/admin/ressources',data=dict(action='archive',key=key)).status_code,400)
        self.assertEqual(self.client.post('/admin/ressources',data=dict(action='archive',key=key,evolution_csrf=token)).status_code,302)
        self.assertNotIn(key,self.client.get('/admin/ressources').text);self.assertIn(key,self.client.get('/admin/ressources?archived=1').text)
        self.assertEqual(self.client.post('/admin/ressources',data=dict(action='restore',key=key,evolution_csrf=token)).status_code,302)
        self.assertIn(key,self.client.get('/admin/ressources').text)
    def test_legacy_visibility_text_removed_without_changing_flags(self):
        machines.set_condition(self.db,self.key,dict(status='maintenance',announce='1',public_listed='0'),'admin','admin');self.db.commit();self.login()
        before=tuple(self.db.execute('SELECT * FROM machine_condition WHERE resource_uuid=?',(self.key,)).fetchone())
        self.assertNotIn('Ancienne visibilité limitée',self.client.get('/admin/ressources/'+self.key+'/maintenance').text)
        self.assertEqual(before,tuple(self.db.execute('SELECT * FROM machine_condition WHERE resource_uuid=?',(self.key,)).fetchone()))
    def test_filenames_iso_for_quote_invoice_pdf_docx_content_unchanged(self):
        self.login();record=dict(quote_number='2026-7',quote_date='2026-10-23',invoice_number='2026-8',invoice_date='2026-11-03',client_structure='Structure fictive')
        with patch.object(app,'load_billing_record',return_value=record),patch.object(app,'document_brand_assets',return_value=({},None,None,None)),patch.object(app,'generate_document_pdf',return_value=b'FICTIONAL_PDF_BYTES'),patch.object(app,'generate_document_docx',return_value=b'FICTIONAL_DOCX_BYTES'):
            for kind,prefix in [('devis','20261023_Devis'),('facture','20261103_Facture')]:
                for ext in ('pdf','docx'):
                    response=self.client.get('/admin/facturation/1/'+kind+'.'+ext)
                    self.assertEqual(response.status_code,200);self.assertIn(prefix+'_StructureFictive_FABLAB_',response.headers['Content-Disposition'])
                    self.assertEqual(response.data,b'FICTIONAL_PDF_BYTES' if ext=='pdf' else b'FICTIONAL_DOCX_BYTES')
        self.assertEqual(app.compact_french_date('2026-10-23'),'20261023');self.assertEqual(__import__('billing').french_date('2026-10-23'),'23/10/2026')

class Migration(unittest.TestCase):
    setUp=core.NewVersion.setUp
    def old(self):
        from tests.schema_fixtures import remove_27
        remove_27(self.db)
        self.db.execute('ALTER TABLE resources DROP COLUMN archived_at');self.db.execute('PRAGMA user_version=24');self.db.commit()
    def test_additive_24_to25_preserves_all_existing_columns_and_settings(self):
        self.old();tables=[r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        before={n:list(map(tuple,self.db.execute('SELECT * FROM '+n))) for n in tables};settings=dict(self.db.execute('SELECT * FROM app_settings'))
        family_model.migrate(self.db);self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],family_model.SCHEMA)
        for n,rows in before.items():
            if n=='app_settings':continue  # existing values are compared below
            columns=[r[1] for r in self.db.execute('PRAGMA table_info('+n+')') if r[1]!='archived_at']
            self.assertEqual(rows,list(map(tuple,self.db.execute('SELECT '+','.join('"'+c+'"' for c in columns)+' FROM '+n))),n)
        self.assertLessEqual(settings.items(),dict(self.db.execute('SELECT * FROM app_settings')).items());self.assertFalse(self.db.execute('SELECT 1 FROM resources WHERE archived_at IS NOT NULL').fetchone())
        self.assertFalse(self.db.execute('PRAGMA foreign_key_check').fetchall());self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
    def test_interruption_rolls_back_column_and_schema(self):
        self.old()
        def fail(db):raise RuntimeError('FICTIONAL_INTERRUPTION')
        with self.assertRaises(RuntimeError):family_model.migrate(self.db,fail)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0],24);self.assertNotIn('archived_at',[r[1] for r in self.db.execute('PRAGMA table_info(resources)')])
    def test_rerun_no_duplicates_or_mutation(self):
        before=list(self.db.iterdump());family_model.migrate(self.db);self.assertEqual(before,list(self.db.iterdump()))
    def test_incompatible_schema_refused(self):
        self.db.execute('PRAGMA user_version='+str(family_model.SCHEMA+1));self.db.commit()
        with self.assertRaises(RuntimeError):family_model.migrate(self.db)
    def test_normal_application_startup_can_migrate24_without_dsm_helper(self):
        self.old();before=[tuple(r) for r in self.db.execute('SELECT * FROM users')];self.db.close()
        application=app.create_app(dict(DATABASE=str(self.path),SECRET_KEY_FILE=str(Path(self.path).parent/'.secret_key'),ADMIN_PIN=None,MODERATOR_PIN=None,SEED_DEMO_USERS=False,TESTING=True,WEATHER_ENABLED=False,AUTO_CLOSURE_WORKER=False))
        self.assertEqual(application.test_client().get('/sante').status_code,200)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],family_model.SCHEMA);self.assertEqual(before,db.execute('SELECT * FROM users').fetchall());self.assertFalse(db.execute('PRAGMA foreign_key_check').fetchall())

class History(unittest.TestCase):
    setUp=core.NewVersion.setUp
    def seed(self,day='2026-10-10',env='production',actual=2,enabled=1):
        row=self.db.execute("SELECT s.*,c.* FROM fablab_services s JOIN animation_reservation_config c ON c.service_id=s.id LIMIT 1").fetchone();self.assertIsNotNone(row)
        key=row['service_id'];self.db.execute('UPDATE fablab_services SET service_date=?,start_time=?,end_time=?,actual_participants=?,description=? WHERE id=?',(day,'10:00','12:00',actual,'DESCRIPTION PUBLIQUE FICTIVE',key));self.db.execute("UPDATE animation_reservation_config SET environment=?,enabled=?,booking_mode='whole',signup_open_at=NULL WHERE service_id=?",(env,enabled,key));self.db.commit();return key
    def snapshot(self,env='production',day=datetime(2026,11,3,12,tzinfo=timezone.utc),history_enabled=True):
        return public_snapshot.build(self.db,env,True,False,now=day,details=True,display_options=True,history=history_enabled)
    def test_calendar_month_clamps_month_ends_leap_year_and_year_change(self):
        for value,expected in [('2026-11-03','2026-10-03'),('2026-03-31','2026-02-28'),('2028-03-31','2028-02-29'),('2026-01-31','2025-12-31')]:self.assertEqual(str(history.month_before(date.fromisoformat(value))),expected)
    def test_past_over24h_visible_only_calendar_with_observed_presence(self):
        key=self.seed();result=self.snapshot();items=[e for e in result['calendar'] if e['kind']=='animation'];self.assertEqual(len(items),1);self.assertTrue(items[0]['history_eligible']);self.assertEqual(items[0]['availability_state'],'ended');self.assertEqual(result['history_start'],'2026-10-03');self.assertEqual(result['coverage_start'],'2026-09-28')
        from outbound_actions import public_catalogue
        self.assertNotIn(key,[r['service_id'] for r in public_catalogue(self.db,'production',True,True,True,current=datetime(2026,11,3,tzinfo=timezone.utc))])
        raw=json.dumps(result)
        for value in ('first_name','last_name','email','phone','notes','manage_token','internal_note','is_present'):self.assertNotIn(value,raw)
    def test_hidden_disabled_wrong_environment_unknown_attendance_excluded(self):
        key=self.seed(actual=0);self.assertFalse([e for e in self.snapshot()['calendar'] if e['kind']=='animation'])
        self.seed(actual=2,enabled=0);self.assertFalse([e for e in self.snapshot()['calendar'] if e['kind']=='animation'])
        self.seed(env='test');self.assertFalse([e for e in self.snapshot()['calendar'] if e['kind']=='animation']);self.assertTrue([e for e in self.snapshot('test')['calendar'] if e['kind']=='animation'])
        self.seed();self.db.execute("INSERT INTO calendar_visibility VALUES('animation',?,'2026-10-10',1,'FICTIONAL')",(str(key),));self.db.commit();self.assertFalse([e for e in self.snapshot()['calendar'] if e['kind']=='animation'])
    def test_week_overlap_does_not_publish_before_exact_month_boundary(self):
        self.seed(day='2026-10-02');self.assertFalse([e for e in self.snapshot()['calendar'] if e['kind']=='animation'])
        self.seed(day='2026-10-03');self.assertTrue([e for e in self.snapshot()['calendar'] if e['kind']=='animation'])
    def test_old_plugin_projection_unchanged_no_new_fields(self):
        self.seed();result=self.snapshot(history_enabled=False);self.assertNotIn('history_start',result);self.assertFalse([e for e in result['calendar'] if e['kind']=='animation'])
    def test_history_capability_optional_boolean_and_protocol_independent_of_version(self):
        from outbound_sync import negotiate
        from types import SimpleNamespace
        base=dict(protocol_version=4,relay_revision=3,outbound_actions_v1=True,plugin_version='2.14.3')
        self.assertEqual(negotiate(SimpleNamespace(post=lambda *args:base),'production'),base)
        for flag in (True,False):self.assertEqual(negotiate(SimpleNamespace(post=lambda *args:dict(base,public_calendar_history_v1=flag)),'test')['public_calendar_history_v1'],flag)
        with self.assertRaises(ValueError):negotiate(SimpleNamespace(post=lambda *args:dict(base,public_calendar_history_v1='1')),'production')
    def test_dst_window_and_schema_unchanged_by_projection(self):
        self.seed(day='2026-10-25');before=list(self.db.iterdump());self.snapshot(day=datetime(2026,11,25,23,tzinfo=timezone.utc));self.assertEqual(before,list(self.db.iterdump()))

if __name__=='__main__':unittest.main()
