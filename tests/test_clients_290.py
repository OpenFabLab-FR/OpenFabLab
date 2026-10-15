"""Existing directory only: optional labels, no document/right mutation."""
import io,re,sqlite3,threading,unittest
from tests import test_families as fixtures
from app import upsert_billing_client
import client_categories as categories
from profile_archive import build_profile,parse_profile

class ClientCategoryTests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.FamilyTests();self.f.setUp();self.addCleanup(self.f.doCleanups);self.db=self.f.db
        self.values=dict(client_contact='Camille EXEMPLE',client_structure='Structure Fictive',address_line='1 voie Fictive',postal_code='00000',city='Ville Fictive',email='',phone='')
    def make(self,**fields):
        with self.db:return upsert_billing_client(self.db,dict(self.values,**fields))
    def test_existing_client_optional_category_not_auto_inferred(self):
        key=self.make();self.assertIsNone(self.db.execute('SELECT category_key FROM billing_clients WHERE id=?',(key,)).fetchone()[0])
        self.assertEqual(len(categories.registry(self.db)),7)
    def test_select_modify_remove_and_preserve_on_billing_form(self):
        key=self.make(client_category='company');self.make(client_structure='Nouveau nom fictif')
        self.assertEqual(self.db.execute('SELECT category_key FROM billing_clients WHERE id=?',(key,)).fetchone()[0],'company')
        self.make(client_category='association');self.make(client_category='')
        self.assertIsNone(self.db.execute('SELECT category_key FROM billing_clients WHERE id=?',(key,)).fetchone()[0])
    def test_archive_used_category_keeps_client_and_affiliation(self):
        key=self.make(client_category='company');self.db.execute('UPDATE users SET affiliation_client_id=? WHERE id=?',(key,self.f.a))
        categories.import_registry(self.db,[dict(category_key='company',name='Entreprise locale',active=0,sort_order=0)]);self.db.commit()
        self.assertEqual(categories.selected(self.db,'company','company'),'company')
        with self.assertRaises(ValueError):categories.selected(self.db,'company')
        self.assertEqual(self.db.execute('SELECT affiliation_client_id FROM users WHERE id=?',(self.f.a,)).fetchone()[0],key)
        self.assertEqual(self.db.execute('SELECT category FROM users WHERE id=?',(self.f.a,)).fetchone()[0],'user')
    def test_multiple_clients_same_category_no_contract(self):
        self.make(client_category='association');self.make(client_contact='Alex EXEMPLE',client_category='association')
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM billing_clients WHERE category_key='association'").fetchone()[0],2)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM billing_records').fetchone()[0],0)
    def test_add_rename_uniqueness_and_validation(self):
        entry=dict(category_key='custom_lab',name='Collectif créatif',active=1,sort_order=9);categories.import_registry(self.db,[entry]);self.db.commit()
        entry['name']='Collectif renommé';categories.import_registry(self.db,[entry]);self.db.commit()
        self.assertEqual(self.db.execute("SELECT name FROM client_categories WHERE category_key='custom_lab'").fetchone()[0],'Collectif renommé')
        for field,value in [('name',''),('name','X'*81),('name','bad\nname'),('active',2),('category_key','../file')]:
            with self.assertRaises(ValueError):categories.validate_entry(dict(entry,**{field:value}))
        with self.assertRaises(sqlite3.IntegrityError):categories.import_registry(self.db,[dict(entry,category_key='duplicate')])
        self.db.rollback()
    def test_profile_roundtrip_and_old_profile_supported(self):
        entries=[{key:row[key] for key in ('category_key','name','active','sort_order')} for row in categories.registry(self.db)]
        raw=build_profile({},[],{},client_categories=entries);self.assertEqual(parse_profile(raw)['client_categories'],entries)
        self.assertEqual(parse_profile(build_profile({},[],{}))['client_categories'],[])
        with self.assertRaises(ValueError):parse_profile(build_profile({},[],{},client_categories=entries+[entries[0]]))
    def test_server_filters_and_permissions(self):
        self.make(client_category='company');self.make(client_contact='Alex AUTRE',client_category='association')
        self.f.f.login_admin();response=self.f.client.get('/admin/facturation?client_category=company&client_q=camille')
        self.assertEqual(response.status_code,200);text=response.get_data(as_text=True);self.assertIn('Camille EXEMPLE',text);self.assertNotIn('Alex AUTRE',text)
        with self.f.client.session_transaction() as state:state['access_role']='moderator'
        self.assertEqual(self.f.client.get('/admin/facturation/clients/nouveau').status_code,302)
    def test_create_csrf_required_and_no_duplicate_overwrite(self):
        self.f.f.login_admin();path='/admin/facturation/clients/nouveau';self.assertEqual(self.f.client.post(path,data=self.values).status_code,400)
        text=self.f.client.get(path).get_data(as_text=True);token=re.search('name="evolution_csrf" value="([^"]+)"',text)[1]
        values=dict(self.values,evolution_csrf=token,client_category='company')
        self.assertEqual(self.f.client.post(path,data=values).status_code,302)
        self.assertEqual(self.f.client.post(path,data=dict(values,client_structure='Should not overwrite')).status_code,400)
        self.assertEqual(self.db.execute('SELECT structure_name FROM billing_clients').fetchone()[0],'Structure Fictive')
    def test_concurrent_create_same_contact_never_overwrites_winner(self):
        barrier=threading.Barrier(2);results=[]
        def create(name):
            client=self.f.f.app.test_client()
            with client.session_transaction() as session:
                session['access_role']='admin';session['admin_authenticated']=True;session['evolution_csrf']='fictional-csrf'
            barrier.wait()
            response=client.post('/admin/facturation/clients/nouveau',data=dict(self.values,client_structure=name,evolution_csrf='fictional-csrf',client_category='company'))
            results.append((response.status_code,name))
        workers=[threading.Thread(target=create,args=(name,)) for name in ('Structure fictive A','Structure fictive B')]
        for worker in workers:worker.start()
        for worker in workers:worker.join(15)
        self.assertEqual(sorted(status for status,_ in results),[302,400])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM billing_clients').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT structure_name FROM billing_clients').fetchone()[0],next(name for status,name in results if status==302))

