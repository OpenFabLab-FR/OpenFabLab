"""Unified resource/publication rules, exclusively fictional records."""
import unittest
import re
from datetime import datetime,timedelta,timezone
from tests import test_v214_core as core
from app import write_setting
import machine_maintenance as machines
import resource_booking as bookings
import resource_loans as loans

class Visibility(unittest.TestCase):
    setUp=core.NewVersion.setUp
    login=core.NewVersion.login
    def test_legacy_unchecked_checkbox_does_not_publish_on_either_channel(self):
        for announce,listed in ((0,1),(1,0),(0,0)):
            machines.set_condition(self.db,self.key,dict(status='operational',announce=str(announce),public_listed=str(listed)),'admin','admin');self.db.commit()
            self.assertNotIn(self.key,[r['id'] for r in machines.public_machines(self.db)],'unchecked legacy resource must not appear on WordPress')
            self.assertNotIn(self.key,[r['id'] for r in machines.public_machines(self.db,True)])
    def test_public_choice_is_independent_of_technical_changes_and_reminders(self):
        machines.set_condition(self.db,self.key,dict(status='operational',visibility_controls='1',public_visible='1'),'admin','admin')
        for state in ('maintenance','out_of_service','operational'):
            machines.set_condition(self.db,self.key,dict(status=state),'moderator','moderator')
            self.assertTrue(machines.machine(self.db,self.key)['public_visible'])
        machines.set_condition(self.db,self.key,dict(status='operational',visibility_controls='1'),'admin','admin')
        machines.intervention(self.db,self.key,dict(performed_on='2020-01-01',kind='care',description='Entretien fictif'),'moderator','moderator')
        machines.reminder(self.db,self.key,dict(due_on='2099-01-01',subject='Rappel fictif'),'moderator','moderator')
        self.assertFalse(machines.machine(self.db,self.key)['public_visible'])
        self.assertNotIn(self.key,[r['id'] for r in machines.public_machines(self.db)])
    def test_new_resource_defaults_private_even_when_reservable(self):
        key=bookings.save_resource(self.db,dict(name='Nouvelle machine fictive',type_key='machine',active='1'),'admin')
        self.assertFalse(machines.machine(self.db,key)['public_visible'])
        self.assertNotIn(key,[r['id'] for r in machines.public_machines(self.db)])
    def test_migration_preserves_legacy_flags_without_widening_and_reopen_is_consistent(self):
        from tests.test_v215_core import Migration
        import family_model,sqlite3
        machines.set_condition(self.db,self.key,dict(status='operational',announce='0',public_listed='1'),'admin','admin');self.db.commit()
        Migration.source25(self);family_model.migrate(self.db);self.db.commit()
        with sqlite3.connect(self.path) as reopened:
            reopened.row_factory=sqlite3.Row
            self.assertEqual(tuple(reopened.execute('SELECT announce,public_listed FROM machine_condition WHERE resource_uuid=?',(self.key,)).fetchone()),(0,1))
            self.assertFalse(machines.machine(reopened,self.key)['public_visible'])
            self.assertNotIn(self.key,[r['id'] for r in machines.public_machines(reopened)])
            self.assertEqual(machines.machine(reopened,self.key)['availability_mode'],'on_site')

class Availability(unittest.TestCase):
    setUp=core.NewVersion.setUp
    def test_rental_mode_independent_of_reservations_prices_and_publication(self):
        key=bookings.save_resource(self.db,dict(name='Découpeuse fictive à prêter',type_key='machine',availability_mode='rental',active='0',price_cents='0'),'admin')
        row=machines.machine(self.db,key)
        self.assertEqual(row['availability']['status'],'rental_available');self.assertTrue(row['availability']['available'])
        self.assertFalse(row['active']);self.assertEqual(row['price_cents'],0);self.assertFalse(row['public_visible'])
        self.assertFalse(machines.public_machines(self.db,True))
    def test_handover_overdue_return_and_breakdown_preserve_intended_use(self):
        machines.set_condition(self.db,self.key,dict(status='operational',availability_mode='rental',visibility_controls='1',public_visible='1'),'admin','admin')
        begin=datetime(2030,6,4,10,tzinfo=timezone.utc);end=begin+timedelta(hours=2)
        booking=bookings.book(self.db,self.key,self.f.a,begin.isoformat(),end.isoformat(),'admin');self.db.commit()
        if self.db.execute('SELECT status FROM resource_bookings WHERE booking_uuid=?',(booking,)).fetchone()[0]=='requested':bookings.transition(self.db,booking,'confirmed','admin');self.db.commit()
        self.assertEqual(loans.availability(self.db,self.key,begin-timedelta(days=1))['status'],'rental_available')
        self.assertIn(self.key,[r['id'] for r in machines.public_machines(self.db)])
        self.assertNotIn(self.key,[r['id'] for r in machines.public_machines(self.db,True)])
        loans.transition(self.db,'booking',booking,'handover','moderator',current=begin)
        self.assertEqual(loans.availability(self.db,self.key,begin)['status'],'loaned')
        self.assertEqual(loans.availability(self.db,self.key,end+timedelta(minutes=1))['status'],'overdue')
        machines.set_condition(self.db,self.key,dict(status='maintenance'),'moderator','moderator')
        loans.transition(self.db,'booking',booking,'return','moderator',current=end+timedelta(hours=1))
        self.assertEqual(loans.availability(self.db,self.key)['status'],'maintenance')
        machines.set_condition(self.db,self.key,dict(status='operational'),'moderator','moderator')
        self.assertEqual(loans.availability(self.db,self.key)['status'],'rental_available')
        self.assertTrue(machines.machine(self.db,self.key)['public_visible'])
        self.assertEqual(machines.public_machines(self.db,effective=False)[0]['status'],'operational')
    def test_existing_reservable_machine_defaults_to_regular_availability(self):
        self.assertTrue(machines.machine(self.db,self.key)['active'])
        self.assertEqual(machines.machine(self.db,self.key)['availability_mode'],'on_site')
        machines.set_condition(self.db,self.key,dict(status='maintenance'),'moderator','moderator')
        machines.set_condition(self.db,self.key,dict(status='operational'),'moderator','moderator')
        self.assertEqual(loans.availability(self.db,self.key)['status'],'operational')

class Unified(unittest.TestCase):
    setUp=core.NewVersion.setUp
    login=core.NewVersion.login
    def route(self,key=None):return '/admin/ressources/'+(key or self.key)+'/fiche'
    def test_one_page_and_old_get_post_routes_preserve_permissions(self):
        csrf=self.login('moderator');page=self.client.get(self.route())
        self.assertEqual(page.status_code,200)
        for section in ('general','availability','interventions','reminders','bookings','documents','qr','advanced'):
            self.assertIn('id="'+section+'"',page.text)
        self.assertNotIn('>Maintenance</a>',page.text)
        self.assertNotIn('name="price_euros"',page.text)
        self.assertNotIn('name="confirm_delete"',page.text)
        for legacy in ('/admin/maintenance/'+self.key,'/admin/ressources/'+self.key+'/maintenance'):
            result=self.client.get(legacy);self.assertEqual(result.status_code,308);self.assertTrue(result.location.endswith(self.route()))
        denied=self.client.post(self.route(),data=dict(action='general',name='NE DOIT PAS CHANGER',evolution_csrf=csrf));self.assertEqual(denied.status_code,403)
        self.assertEqual(self.client.post(self.route(),data=dict(action='condition',status='maintenance')).status_code,400)
        before=self.db.execute('SELECT COUNT(*) FROM machine_history').fetchone()[0]
        saved=self.client.post('/admin/ressources/'+self.key+'/maintenance',data=dict(action='condition',status='maintenance',evolution_csrf=csrf),follow_redirects=True)
        self.assertEqual(saved.status_code,200,saved.text[:1600]);self.assertEqual(machines.machine(self.db,self.key)['status'],'maintenance')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM machine_history').fetchone()[0],before+1)
    def test_general_validation_keeps_input_and_does_not_change_other_fields(self):
        csrf=self.login();before=dict(self.db.execute('SELECT * FROM resources WHERE resource_uuid=?',(self.key,)).fetchone())
        result=self.client.post(self.route(),data=dict(action='general',name='',type_key='machine',description='À conserver <exemple>',color_default='1',evolution_csrf=csrf))
        self.assertEqual(result.status_code,400);self.assertIn('À conserver &lt;exemple&gt;',result.text)
        self.assertEqual(dict(self.db.execute('SELECT * FROM resources WHERE resource_uuid=?',(self.key,)).fetchone()),before)
        result=self.client.post(self.route(),data=dict(action='general',name='Ressource renommée fictive',type_key='machine',description='Description conservée',color_default='1',evolution_csrf=csrf))
        self.assertEqual(result.status_code,302);after=machines.machine(self.db,self.key)
        self.assertEqual(after['name'],'Ressource renommée fictive')
        self.assertEqual(after['price_cents'],before['price_cents']);self.assertEqual(after['active'],before['active'])
    def test_intervention_validation_retains_description_and_date(self):
        csrf=self.login('moderator')
        result=self.client.post(self.route(),data=dict(action='intervention',performed_on='2099-01-01',kind='repair',description='Détail fictif à conserver',evolution_csrf=csrf))
        self.assertEqual(result.status_code,400);self.assertIn('Détail fictif à conserver',result.text);self.assertIn('value="2099-01-01"',result.text)
        self.assertFalse(self.db.execute('SELECT 1 FROM machine_interventions').fetchone())
    def test_new_resource_and_reminder_errors_keep_input(self):
        csrf=self.login()
        response=self.client.post('/admin/ressources',data=dict(action='resource',name='Création fictive à garder',type_key='machine',description='Description fictive',price_euros='invalide',availability_mode='rental',evolution_csrf=csrf))
        self.assertEqual(response.status_code,400);self.assertIn('Création fictive à garder',response.text)
        self.assertIn('value="invalide"',response.text)
        self.assertFalse(self.db.execute("SELECT 1 FROM resources WHERE name='Création fictive à garder'").fetchone())
        response=self.client.post(self.route(),data=dict(action='reminder',due_on='invalide',subject='Objet fictif à garder',evolution_csrf=csrf))
        self.assertEqual(response.status_code,400);self.assertIn('Objet fictif à garder',response.text)
        self.assertIn('Choisissez une date valide.',response.text)
    def test_reminder_intervention_link_and_trace_are_preserved(self):
        csrf=self.login('moderator')
        response=self.client.post(self.route(),data=dict(action='reminder',due_on='2099-01-01',subject='Contrôle fictif',evolution_csrf=csrf))
        self.assertEqual(response.status_code,302)
        row=self.db.execute('SELECT * FROM machine_reminders WHERE resource_uuid=?',(self.key,)).fetchone()
        response=self.client.post(self.route(),data=dict(action='intervention',reminder_id=row['reminder_uuid'],reminder_revision=row['revision'],performed_on='2020-01-01',kind='inspection',description='Vérification fictive',evolution_csrf=csrf))
        self.assertEqual(response.status_code,302)
        row=self.db.execute('SELECT * FROM machine_reminders WHERE resource_uuid=?',(self.key,)).fetchone()
        self.assertEqual(row['state'],'done');self.assertTrue(row['intervention_uuid'])
        self.assertIn('id="intervention-'+row['intervention_uuid']+'"',self.client.get(self.route()).text)
        self.assertFalse(machines.machine(self.db,self.key)['public_visible'])
    def test_lifecycle_requires_administrator_and_keeps_history(self):
        csrf=self.login('moderator')
        self.assertEqual(self.client.post(self.route(),data=dict(action='archive',evolution_csrf=csrf)).status_code,403)
        with self.client.session_transaction() as session:session['access_role']='admin';session['admin_authenticated']=True
        self.assertEqual(self.client.post(self.route(),data=dict(action='archive',evolution_csrf=csrf)).status_code,302)
        archived=self.client.get(self.route());self.assertEqual(archived.status_code,200)
        self.assertNotIn('data-machine-condition',archived.text)
        self.assertEqual(self.client.post(self.route(),data=dict(action='restore',evolution_csrf=csrf)).status_code,302)
        self.assertIn('data-machine-condition',self.client.get(self.route()).text)
        blocked=self.client.post(self.route(),data=dict(action='delete',confirm_delete=self.key,evolution_csrf=csrf))
        self.assertEqual(blocked.status_code,400);self.assertTrue(machines.machine(self.db,self.key))

class NaturalOrder(unittest.TestCase):
    setUp=core.NewVersion.setUp
    login=core.NewVersion.login
    def test_names_not_creation_or_status_determine_all_resource_lists(self):
        expected=['Équipement 2','équipement 10','Imprimante 3D 2','Imprimante 3D 10','Machine 2','machine 10']
        created={}
        for index,name in enumerate(reversed(expected)):
            key=bookings.save_resource(self.db,dict(name=name,type_key='machine',active='1'),'admin');created[key]=name
            machines.set_condition(self.db,key,dict(status='maintenance' if index%2 else 'out_of_service',visibility_controls='1',public_visible='1'),'admin','admin')
        self.db.commit()
        for rows in (machines.directory(self.db),machines.public_machines(self.db),machines.public_machines(self.db,True)):
            self.assertEqual([r['name'] for r in rows if r.get('resource_uuid',r.get('id')) in created],expected)
        self.db.commit();self.login();html=self.client.get('/admin/ressources').text
        order=re.findall(r'id="resource-([a-f0-9-]+)"',html)
        self.assertEqual([created[k] for k in order if k in created],expected)
        key=next(k for k,v in created.items() if v=='Machine 2')
        from resource_lifecycle import change
        self.db.execute('BEGIN IMMEDIATE');change(self.db,key,'archive','admin');self.db.commit()
        self.assertNotIn(key,[r['resource_uuid'] for r in machines.directory(self.db)])
        self.db.commit();self.db.execute('BEGIN IMMEDIATE');change(self.db,key,'restore','admin');self.db.commit()
        self.assertEqual([r['name'] for r in machines.directory(self.db) if r['resource_uuid'] in created],expected)
        self.db.commit()
        import resource_editor
        from app import load_modules,load_rental_catalog,available_rental_catalog
        resource_editor.save_fields(self.db,key,dict(name='A machine 2',type_key='machine',description='',color_default='1'),'admin','general',load_modules(self.db));self.db.commit()
        renamed=['A machine 2']+[v for v in expected if v!='Machine 2']
        self.assertEqual([r['name'] for r in machines.public_machines(self.db) if r['id'] in created],renamed)
        from resource_sort import name_key
        for catalog in (load_rental_catalog(self.db),available_rental_catalog(self.db)):
            names=[r['name'] for r in catalog.values()];self.assertEqual(names,sorted(names,key=name_key))

if __name__=='__main__':unittest.main()
