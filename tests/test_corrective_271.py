"""Corrective 2.7.1: fictional data, denied external actions, exact amounts."""
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from flask.testing import FlaskClient
from tests import test_app as fixtures
import app
import evolution_schema as schema
import resource_booking as resources
import private_backup
import welcome_mail
from profile_archive import build_profile, parse_profile


class CorrectiveTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.OpenFabLabTestCase(); self.f.setUp(); self.addCleanup(self.f.tearDown)
        self.f.app.test_client_class = FlaskClient
        self.client = self.f.app.test_client()
        with self.client.session_transaction() as s:
            s.update(access_role='admin',admin_authenticated=True)

    def token(self, page='/admin/reglages/usagers'):
        return re.search(r'name="evolution_csrf" value="([^"]+)"', self.client.get(page).get_data(as_text=True))[1]

    def post(self, route, values, page='/admin/reglages/usagers', **kw):
        return self.client.post(route, data=dict(values,evolution_csrf=self.token(page)), **kw)

    def auth(self, db, name='Initiation Exemple'):
        return resources.save_definition(db,name,'Description fictive','admin')

    def test_default_logo_shadow_class_and_unchanged_asset(self):
        import hashlib
        root=Path(__file__).resolve().parents[1]
        self.assertEqual(hashlib.sha256((root/'static/brand/OpenFabLab-logo-horizontal.svg').read_bytes()).hexdigest(),
            'd783e61ce5ceef0c351519c38884943000a4cc0aefedea7ed196064b5f30771e')
        for route in ('/','/admin/connexion','/admin/usagers','/admin/calendrier'):
            client=self.f.app.test_client() if route=='/admin/connexion' else self.client
            page=client.get(route).get_data(as_text=True)
            self.assertIn('class="brand-wordmark brand-wordmark--openfablab"',page)
            self.assertEqual(page.count('brand-wordmark--openfablab'),1)
        css=(root/'static/style.css').read_text()
        block=re.search(r'\.site-header \.brand-wordmark--openfablab\s*\{([^}]+)\}',css)[1]
        self.assertEqual(re.sub(r'\s+',' ',block).strip(),
            'filter: drop-shadow(0 1px 1px rgba(20, 35, 40, 0.14)) drop-shadow(0 3px 5px rgba(20, 35, 40, 0.12));')

    def test_custom_header_logo_has_no_openfablab_shadow_class(self):
        branding=Path(self.f.database_path).parent/'branding'
        for kind in ('wordmark','header_institution','network'):
            (branding/(kind+'.png')).write_bytes((branding/'main.png').read_bytes())
        with self.f.database() as db:
            for kind in ('wordmark','header_institution','network'):
                app.write_setting(db,'structure_'+kind+'_logo',kind+'.png')
                app.write_setting(db,'structure_show_'+kind+'_logo','1')
        for route in ('/','/admin/connexion','/admin/usagers','/admin/calendrier'):
            client=self.f.app.test_client() if route=='/admin/connexion' else self.client
            page=client.get(route).get_data(as_text=True)
            self.assertIn('class="brand-wordmark"',page)
            self.assertNotIn('brand-wordmark--openfablab',page)
            self.assertIn('/media/structure/wordmark.png',page)
            self.assertIn('/media/structure/header_institution.png',page)
            self.assertIn('/media/structure/network.png',page)

    def test_category_new_at_end_and_edit_keeps_position(self):
        with self.f.database() as db:
            before = schema.ordered_keys(db,'categories')
            key = schema.save_category(db,'Équipe Exemple','#123456')
            self.assertEqual(schema.ordered_keys(db,'categories'),before+[key])
            schema.save_category(db,'Équipe modifiée','#654321',key=key)
            self.assertEqual(schema.ordered_keys(db,'categories'),before+[key])

    def test_category_reorder_exact_and_normalized(self):
        with self.f.database() as db:
            keys = schema.ordered_keys(db,'categories')[::-1]
            schema.reorder(db,'categories',keys)
            self.assertEqual(schema.ordered_keys(db,'categories'),keys)
            self.assertEqual([r[0] for r in db.execute('SELECT sort_order FROM user_categories ORDER BY sort_order')],list(range(len(keys))))
            for invalid in (keys[:-1],keys+[keys[0]],keys[:-1]+['forged'],{},[None]):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    schema.reorder(db,'categories',invalid)

    def test_category_remove_and_reactivate_stable(self):
        with self.f.database() as db:
            one = schema.save_category(db,'Une','#123456')
            two = schema.save_category(db,'Deux','#123456')
            schema.save_category(db,'Deux','#123456',False,key=two)
            before = schema.ordered_keys(db,'categories')
            schema.save_category(db,'Deux','#123456',True,key=two)
            self.assertEqual(schema.ordered_keys(db,'categories'),before)
            schema.remove_category(db,one)
            self.assertEqual([r['sort_order'] for r in schema.categories(db,True)],list(range(len(before)-1)))

    def test_resource_type_order_new_at_end(self):
        with self.f.database() as db:
            a = resources.save_type(db,'Espace Exemple','#123456')
            b = resources.save_type(db,'Matériel Exemple','#654321')
            keys = schema.ordered_keys(db,'resource_types')
            self.assertEqual(keys[-2:],[a,b])
            schema.reorder(db,'resource_types',keys[::-1])
            self.assertEqual(schema.ordered_keys(db,'resource_types'),keys[::-1])

    def test_order_endpoint_csrf_roles_and_stale_list(self):
        with self.f.database() as db: keys = schema.ordered_keys(db,'categories')
        route='/admin/reglages/ordre/categories'
        self.assertEqual(self.client.post(route,data={'keys':json.dumps(keys)}).status_code,400)
        self.assertEqual(self.post(route,{'keys':json.dumps(keys[::-1])}).json['keys'],keys[::-1])
        self.assertEqual(self.post(route,{'keys':json.dumps(keys[:-1])}).status_code,400)
        self.assertEqual(self.post('/admin/reglages/ordre/arbitrary',{'keys':'[]'}).status_code,400)
        with self.client.session_transaction() as s:s['access_role']='moderator'
        self.assertIn(self.client.post(route,data={'keys':json.dumps(keys)}).status_code,(302,403))

    def test_autosave_category_and_resource_type(self):
        headers={'X-OpenFabLab-Autosave':'1'}
        response=self.post('/admin/reglages/usagers',{'action':'category','name':'Fictif café','color':'#123456','active':'1'},headers=headers)
        self.assertEqual(response.json,{'ok':True})
        response=self.post('/admin/ressources',{'action':'type','name':'Espace fictif','color':'#654321','active':'1'},headers=headers)
        self.assertEqual(response.json,{'ok':True})
        self.assertEqual(self.post('/admin/reglages/usagers',{'action':'category','name':'','color':'#123456'},headers=headers).status_code,400)

    def test_dynamic_color_all_pages_and_css_injection_refused(self):
        with self.f.database() as db:
            schema.save_category(db,'Personnel','#147a39',key='staff')
        for route in ('/','/usagers','/admin/usagers','/admin/frequentation/statistiques?year=total','/admin/frequentation/journee?date=2026-10-03'):
            with self.subTest(route=route):
                page=self.client.get(route,follow_redirects=True).get_data(as_text=True)
                self.assertIn('.category-badge.category-staff{--category-color:#147a39',page)
        with self.f.database() as db:
            with self.assertRaises(ValueError):schema.save_category(db,'Injecté','#fff;}body{}',key='staff')

    def test_inactive_statistics_toggle_and_totals_preserved(self):
        with self.f.database() as db:
            schema.save_category(db,'Stagiaire','#123456',False,key='intern')
        hidden=self.client.get('/admin/frequentation/statistiques?year=total').get_data(as_text=True)
        shown=self.client.get('/admin/frequentation/statistiques?year=total&show_inactive=1').get_data(as_text=True)
        self.assertNotIn('class="category-badge category-intern"',hidden)
        self.assertIn('class="category-badge category-intern"',shown)
        self.assertIn('Afficher les catégories inactives',hidden)
        with self.f.database() as db:
            before=app.load_statistics(db,'total')['selected_summary']
            self.client.get('/admin/frequentation/statistiques?year=total')
            self.assertEqual(before,app.load_statistics(db,'total')['selected_summary'])

    def test_legacy_creation_provenance_not_in_directory(self):
        page=self.client.get('/admin/usagers').get_data(as_text=True)
        self.assertNotIn('Historique / inconnue',page)
        with self.f.database() as db:user=db.execute('SELECT id FROM users LIMIT 1').fetchone()[0]
        detail=self.client.get(f'/admin/usagers/{user}/modifier').get_data(as_text=True)
        self.assertIn('Création antérieure au suivi de provenance',detail)

    def test_euros_exact_examples_and_invalid(self):
        for text,cents in [('0',0),('5',500),('5,5',550),('5,50',550),('5.5',550),('5.50',550),('0,01',1),('999999,99',99999999)]:
            self.assertEqual(resources.euros_to_cents(text),cents)
        for text in ('NaN','inf','-5','5,001','1e2','','1 000','1000001'):
            with self.subTest(text=text),self.assertRaises(ValueError):resources.euros_to_cents(text)

    def test_resource_euros_route_stores_integer_without_changing_booking(self):
        response=self.post('/admin/ressources',dict(action='resource',name='Ressource tarifée fictive',type_key='machine',active='1',price_euros='5,50'))
        self.assertEqual(response.status_code,302)
        with self.f.database() as db:
            row=db.execute("SELECT * FROM resources WHERE name='Ressource tarifée fictive'").fetchone()
            self.assertEqual(row['price_cents'],550)
            self.assertIsInstance(row['price_cents'],int)
            user=db.execute('SELECT id FROM users LIMIT 1').fetchone()[0]
            key=resources.book(db,row['resource_uuid'],user,'2099-10-08T09:00:00+02:00','2099-10-08T10:00:00+02:00','admin')
            self.assertEqual(db.execute('SELECT amount_cents FROM resource_bookings WHERE booking_uuid=?',(key,)).fetchone()[0],550)

    def test_definition_edit_reorder_no_schema_change(self):
        with self.f.database() as db:
            a=self.auth(db,'Laser fictif');b=self.auth(db,'Broderie fictive')
            schema.reorder(db,'authorizations',[b,a])
            resources.save_definition(db,'Laser modifié','Accent é & ponctuation','admin',a)
            self.assertEqual([r['authorization_uuid'] for r in resources.definitions(db)],[b,a])
            self.assertEqual(resources.definitions(db)[1]['description'],'Accent é & ponctuation')
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],17)
            db.commit()
            with self.f.app.app_context():app.initialize_database()
            self.assertEqual(schema.ordered_keys(db,'authorizations'),[b,a])

    def test_unused_definition_can_delete_and_normalize(self):
        with self.f.database() as db:
            a=self.auth(db,'Une');b=self.auth(db,'Deux')
            resources.change_definition(db,a,'delete','admin')
            self.assertEqual(schema.ordered_keys(db,'authorizations'),[b])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_history_blocks_definition_delete_archiving_preserves_grant(self):
        with self.f.database() as db:
            key=self.auth(db);user=db.execute('SELECT id FROM users LIMIT 1').fetchone()[0]
            grant=resources.grant(db,user,key,'2026-01-01','Équipe Exemple','admin')
            with self.assertRaises(ValueError):resources.change_definition(db,key,'delete','admin')
            resources.change_definition(db,key,'archive','admin')
            self.assertEqual(resources.definitions(db),[])
            self.assertEqual(resources.grants_for_user(db,user)[0]['grant_uuid'],grant)
            resources.change_definition(db,key,'reactivate','admin')
            self.assertEqual(len(resources.definitions(db)),1)

    def test_active_resource_blocks_archive_any_resource_blocks_delete(self):
        with self.f.database() as db:
            key=self.auth(db)
            resource=resources.save_resource(db,dict(name='Machine fictive',active=True,type_key='machine',required_authorization=key),'admin')
            with self.assertRaises(ValueError):resources.change_definition(db,key,'archive','admin')
            with self.assertRaises(ValueError):resources.change_definition(db,key,'delete','admin')
            db.execute('UPDATE resources SET active=0 WHERE resource_uuid=?',(resource,))
            resources.change_definition(db,key,'archive','admin')
            with self.assertRaises(ValueError):resources.change_definition(db,key,'delete','admin')

    def test_moderator_cannot_manage_definitions_can_revoke_with_reason(self):
        with self.f.database() as db:
            key=self.auth(db);user=db.execute('SELECT id FROM users LIMIT 1').fetchone()[0]
            grant=resources.grant(db,user,key,'2026-01-01','Formateur fictif','moderator')
            for action in ('archive','delete','reactivate'):
                with self.assertRaises(ValueError):resources.change_definition(db,key,action,'moderator')
            with self.assertRaises(ValueError):resources.save_definition(db,'Interdit','','moderator',key)
            with self.assertRaises(ValueError):resources.revoke(db,grant,'moderator',' ')
            resources.revoke(db,grant,'moderator','À revoir – exemple fictif')
            row=resources.grants_for_user(db,user)[0]
            self.assertEqual((row['state'],row['validated_by'],row['revoked_by']),('Révoquée','Formateur fictif','moderator'))
            self.assertFalse(resources.authorization_valid(db,user,key,'2026-01-02'))

    def test_grant_states_and_user_detail(self):
        with self.f.database() as db:
            key=self.auth(db);user=db.execute('SELECT id FROM users LIMIT 1').fetchone()[0]
            resources.grant(db,user,key,'2020-01-01','Formateur fictif','admin','2020-02-01')
            resources.grant(db,user,key,'2020-01-01','Formateur fictif','admin')
            resources.grant(db,user,key,'2099-01-01','Formateur fictif','admin')
            self.assertEqual({r['state'] for r in resources.grants_for_user(db,user)},{'Permanente','Expirée','À venir'})
        page=self.client.get(f'/admin/usagers/{user}/modifier').get_data(as_text=True)
        for text in ('Formations et habilitations','Permanente','Expirée','À venir','Formateur fictif'):
            self.assertIn(text,page)

    def test_definition_delete_requires_confirmation(self):
        with self.f.database() as db:key=self.auth(db)
        self.post('/admin/habilitations',{'action':'delete','key':key})
        with self.f.database() as db:self.assertTrue(db.execute('SELECT 1 FROM authorizations WHERE authorization_uuid=?',(key,)).fetchone())
        self.post('/admin/habilitations',{'action':'delete','key':key,'confirmation':'SUPPRIMER'})
        with self.f.database() as db:self.assertFalse(db.execute('SELECT 1 FROM authorizations WHERE authorization_uuid=?',(key,)).fetchone())

    def test_smtp_simple_test_no_qr_attachment_or_fake_user(self):
        config=dict(host='smtp.example.invalid',port=587,security='starttls',sender_email='smtp@example.invalid')
        message=welcome_mail.build_smtp_test(config,'recipient@example.invalid','Structure de test','https://site.example.invalid')
        self.assertEqual(message['Subject'],'Test de configuration e-mail OpenFabLab')
        self.assertFalse(message.is_multipart())
        self.assertEqual(list(message.iter_attachments()),[])
        text=message.get_content()
        self.assertNotIn('Camille',text);self.assertNotIn('QR',text)
        self.assertIn('Structure de test',text)

    def test_smtp_route_two_tests_configured_welcome_template(self):
        config=dict(host='smtp.example.invalid',port=587,security='starttls',sender_email='smtp@example.invalid')
        welcome_mail.save_config(self.f.database_path,config)
        with self.f.database() as db:
            app.write_setting(db,'welcome_subject','Bienvenue chez {{structure_name}}')
            app.write_setting(db,'welcome_body','Bonjour {{first_name}}, ID {{public_id}}')
        with mock.patch('welcome_mail.send') as send:
            self.post('/admin/reglages/integrations',{'action':'test','recipient':'recipient@example.invalid'})
            self.assertFalse(send.call_args.args[1].is_multipart())
            self.post('/admin/reglages/integrations',{'action':'welcome_test','recipient':'recipient@example.invalid'})
            message=send.call_args.args[1]
            self.assertTrue(message.is_multipart())
            self.assertIn('[EXEMPLE FICTIF]',message['Subject'])
            self.assertIn('Camille',message.get_body(preferencelist=('plain',)).get_content())

    def test_smtp_test_blocked_by_private_copy_policy(self):
        config=dict(host='smtp.example.invalid',port=587,security='starttls',sender_email='smtp@example.invalid')
        message=welcome_mail.build_smtp_test(config,'recipient@example.invalid','Exemple')
        from runtime_policy import TEST_MARKER
        (Path(self.f.database_path).parent/TEST_MARKER).write_text('{}')
        with self.f.app.app_context(), mock.patch('welcome_mail.smtplib.SMTP') as transport:
            self.f.app.config['EXTERNAL_ACTIONS']=False
            with self.assertRaises(OSError):welcome_mail.send(config,message)
            transport.assert_not_called()

    def test_webhook_form_preserves_other_preferences(self):
        with self.f.database() as db:app.write_setting(db,'discord_notify_arrivals','1')
        response=self.post('/admin/reglages/notifications',{'webhook_only':'1'})
        self.assertEqual(response.status_code,302)
        with self.f.database() as db:self.assertEqual(app.read_setting(db,'discord_notify_arrivals'),'1')

    def test_notifications_sections_order_and_homogeneous_labels(self):
        page=self.client.get('/admin/reglages/notifications').get_data(as_text=True)
        self.assertLess(page.index('Webhook du salon'),page.index('Notifications à la création'))
        self.assertLess(page.index('Notifications à la création'),page.index('Événements notifiés'))
        self.assertIn('Décochez l’événement pour désactiver cette notification.',page)
        self.assertNotIn('Aucun e-mail, téléphone, adresse, identifiant ou QR Code',page)
        self.assertIn("La sauvegarde complète privée l'inclut",page)
        self.assertNotIn("la base SQLite ou ses sauvegardes",page)

    def test_login_segmented_pin_masked_and_error(self):
        with self.client.session_transaction() as s:s.clear()
        page=self.client.get('/admin/connexion').get_data(as_text=True)
        self.assertEqual(page.count('type="radio" name="access_role"'),2)
        self.assertIn('maxlength="4"',page)
        self.assertNotIn('<select',page)
        token=re.search(r'name="csrf_token" value="([^"]+)"',page)[1]
        response=self.client.post('/admin/connexion',data={'pin':'0000','access_role':'moderator','csrf_token':token})
        self.assertIn('role="alert"',response.get_data(as_text=True))
        self.assertIn('value="moderator" checked',response.get_data(as_text=True))

    def test_order_backup_restore_preserves_pin_and_state(self):
        with self.f.database() as db:
            keys=schema.ordered_keys(db,'categories')[::-1];schema.reorder(db,'categories',keys)
            key=self.auth(db);db.commit()
        with tempfile.TemporaryDirectory() as folder:
            archive=Path(folder)/'private.zip'
            manifest=private_backup.create_backup(self.f.database_path,archive,kind='test')
            self.assertEqual(manifest['openfablab_version'],'2.8.2')
            target=Path(folder)/'restored/openfablab.db'
            private_backup.restore_backup(archive,target)
            from pin_security import check_pin
            self.assertTrue(check_pin(target,'admin','1379'))
            import sqlite3
            with sqlite3.connect(target) as db:
                db.row_factory=sqlite3.Row
                self.assertEqual(schema.ordered_keys(db,'categories'),keys)
                self.assertEqual(schema.ordered_keys(db,'authorizations'),[key])
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],17)

    def test_inactive_resource_keeps_archived_requirement(self):
        with self.f.database() as db:
            key=self.auth(db)
            values=dict(name='Machine fictive',type_key='machine',active=False,required_authorization=key)
            machine=resources.save_resource(db,values,'admin')
            resources.change_definition(db,key,'archive','admin')
            resources.save_resource(db,dict(values,name='Machine fictive modifiée'),'admin',machine)
            self.assertEqual(db.execute('SELECT required_authorization FROM resources WHERE resource_uuid=?',(machine,)).fetchone()[0],key)
            with self.assertRaises(ValueError):
                resources.save_resource(db,dict(values,active=True),'admin',machine)

    def test_profile_preserves_category_and_type_order(self):
        with self.f.database() as db:
            keys=schema.ordered_keys(db,'categories')[::-1];schema.reorder(db,'categories',keys)
            registry=[{k:r[k] for k in ('category_key','name','color','active','sort_order','is_default')} for r in schema.categories(db,True)]
        parsed=parse_profile(build_profile({},[],{},categories=registry))
        self.assertEqual([r['category_key'] for r in parsed['categories']],keys)

    def test_idempotent_271_initialization_keeps_business_tables(self):
        with self.f.app.app_context():
            db=app.get_database()
            app.initialize_database()
            tables=('users','sessions','visitors','fablab_services','billing_records','rental_catalog')
            before={t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables}
            app.initialize_database();app.initialize_database()
            self.assertEqual({t:[tuple(r) for r in db.execute('SELECT * FROM '+t)] for t in tables},before)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],17)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])


if __name__=='__main__': unittest.main()
