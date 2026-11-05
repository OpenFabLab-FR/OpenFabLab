"""Local-only universal search, permissions, wildcard escaping and deployment prefix."""
import unittest
from tests import test_v214_core as core
from app import write_setting
from admin_search import search


class Search(unittest.TestCase):
    setUp=core.NewVersion.setUp
    login=core.NewVersion.login
    def test_no_role_or_csrf_bypass_and_no_private_contacts(self):
        route='/admin/recherche'
        self.assertNotEqual(self.client.post(route,data={'q':'Fictif'}).status_code,200)
        token=self.login('moderator')
        self.assertEqual(self.client.post(route,data={'q':'Fictif'}).status_code,400)
        response=self.client.post(route,data={'q':'Fictif','evolution_csrf':token})
        self.assertEqual(response.status_code,200)
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertIn('Usagers',str(response.json))
        self.assertNotIn('@example',response.text)
        self.assertNotIn('phone',response.text)
        self.assertNotIn('facturation',response.text)
    def test_disabled_modules_not_queried_or_disclosed(self):
        self.login()
        for key in ('users','resources','activities','billing'):
            write_setting(self.db,'module_'+key,'0')
        write_setting(self.db,'module_maintenance','0');self.db.commit()
        with self.client.session_transaction() as s:token=s['evolution_csrf']
        self.assertEqual(self.client.post('/admin/recherche',data={'q':'Fictif','evolution_csrf':token}).json,{'groups':[]})
    def test_wildcards_are_literals_and_results_bounded(self):
        modules=dict(users=True)
        self.assertFalse(search(self.db,'%%','admin',modules))
        self.assertFalse(search(self.db,'__','admin',modules))
        self.assertFalse(search(self.db,'x','admin',modules))
        self.assertFalse(search(self.db,'x'*81,'admin',modules))
        groups=search(self.db,'Fictif','admin',modules)
        self.assertTrue(groups)
        self.assertTrue(all(len(g['items'])<=8 for g in groups))
        with self.assertRaises(PermissionError):search(self.db,'Fictif','public',modules)
    def test_script_prefix_preserved_in_http_results(self):
        token=self.login()
        response=self.client.post('/admin/recherche',data={'q':'Fictif','evolution_csrf':token},environ_overrides={'SCRIPT_NAME':'/stat'})
        items=[i for g in response.json['groups'] for i in g['items']]
        self.assertTrue(items)
        self.assertTrue(all(i['url'].startswith('/stat/admin/') for i in items))

    def test_unicode_names_case_and_accents_without_persistent_index_or_writes(self):
        self.db.execute("UPDATE users SET first_name='Élodie',last_name='Äänekoski Straße' WHERE id=(SELECT MIN(id) FROM users)")
        self.db.commit();before=self.db.total_changes
        for query in ('elodie','ÉLODIE','AANEKOSKI','STRASSE'):
            with self.subTest(query=query):
                self.assertTrue(search(self.db,query,'admin',dict(users=True)))
        self.assertEqual(self.db.total_changes,before)

    def test_client_links_use_foreign_keys_and_are_not_disclosed_to_moderator(self):
        from datetime import datetime,timedelta,timezone
        import resource_booking
        stamp=datetime.now(timezone.utc);day=str(stamp.date())
        client=self.db.execute("""INSERT INTO billing_clients(contact_name,contact_name_normalized,structure_name,address_line,postal_code,city,created_at,updated_at)
            VALUES('Contact fictif','contact fictif','École des possibles','1 rue fictive','00000','Ville fictive',?,?)""",(stamp.isoformat(),stamp.isoformat())).lastrowid
        def record(title,relation,quote):
            return self.db.execute("""INSERT INTO billing_records(quote_number,quote_date,client_contact,client_structure,address_line,postal_code,city,title,description,activity_date,rate_category,rate_unit,created_at,updated_at,client_id)
                VALUES(?,?,'Autre contact fictif','Autre structure fictive','1 rue fictive','00000','Ville fictive',?,'',?,'normal','hourly',?,?,?)""",
                (quote,day,title,day,stamp.isoformat(),stamp.isoformat(),relation)).lastrowid
        real=record('Dossier associé',client,'DEV-FICTIF-1')
        unrelated=record('École des possibles dans un titre',None,'DEV-FICTIF-2')
        booking=resource_booking.book(self.db,self.key,self.f.a,(stamp+timedelta(days=1)).isoformat(),(stamp+timedelta(days=2)).isoformat(),'admin')
        self.db.execute('UPDATE resource_bookings SET billing_record_id=? WHERE booking_uuid=?',(real,booking));self.db.commit()
        token=self.login();route='/admin/facturation/clients/'+str(client)+'/modifier'
        groups=self.client.post('/admin/recherche',data=dict(q='ECOLE',evolution_csrf=token)).json['groups']
        self.assertIn(route,str(groups));self.assertIn('reservation-'+booking,str(groups))
        page=self.client.get(route);self.assertEqual(page.status_code,200)
        self.assertIn('Dossier associé',page.text);self.assertNotIn('dans un titre',page.text)
        self.assertIn('reservation-'+booking,page.text)
        self.assertIn('Devis en attente de signature',self.client.get('/admin').text)
        self.db.execute('UPDATE billing_records SET quote_signed_at=? WHERE id=?',(stamp.isoformat(),real));self.db.commit()
        self.assertIn('Devis signé · facture à établir',self.client.get('/admin').text)
        self.db.execute("UPDATE billing_records SET invoice_number='FACT-FICTIVE',invoice_date=?,invoice_sent_at=? WHERE id=?",
            (day,(stamp-timedelta(days=31)).isoformat(),real));self.db.commit()
        self.assertIn('Relance : facture envoyée depuis au moins 30 jours',self.client.get('/admin').text)
        self.db.execute('UPDATE billing_records SET paid_at=? WHERE id=?',(stamp.isoformat(),real));self.db.commit()
        self.assertNotIn('Relance : facture envoyée depuis au moins 30 jours',self.client.get('/admin').text)
        with self.client.session_transaction() as session:
            session['access_role']='moderator';session['admin_authenticated']=False
        self.assertNotEqual(self.client.get(route).status_code,200)
        self.assertNotIn('École des possibles',self.client.post('/admin/recherche',data=dict(q='ECOLE',evolution_csrf=token)).text)

if __name__=='__main__':unittest.main()
