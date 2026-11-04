"""Authorized corrections retain input, never partial users or public ID lookup."""
import concurrent.futures,inspect,json,re,sqlite3,threading,unittest
from unittest.mock import patch
from flask.testing import FlaskClient
from tests import test_enrollment_privacy as privacy
from app import write_setting
import enrollment_feedback

class Enrollment(unittest.TestCase):
    setUp=privacy.EnrollmentPrivacyTests.setUp
    start=privacy.EnrollmentPrivacyTests.start
    no_created=privacy.EnrollmentPrivacyTests.no_created
    def payload(self,token,code='0042',**extra):
        return dict(evolution_csrf=token,public_id=code,first_name='Camille',last_name='EXEMPLE',birth_year='1990',gender='non_binary',city='Ville fictive',postal_code='35000',nationality='Française',email='camille@example.invalid',phone='0600000000',phone_country_code='+33',send_welcome='1',**extra)
    def post(self,values,client=None):
        return (client or self.client).post('/inscription',data=values,headers={'Accept':'application/json','X-OpenFabLab-Enrollment-Form':'1'})
    def test_duplicate_then_correct_only_identifier(self):
        token=self.start();used=self.db.execute('SELECT public_id FROM users LIMIT 1').fetchone()[0];values=self.payload(token,used)
        with patch('evolution_routes.after_creation') as notification:
            result=self.post(values);self.assertEqual(result.status_code,409)
            self.assertEqual(result.json['field_errors']['public_id'],enrollment_feedback.USED_ID)
            self.assertNotIn('proposed_id',result.json);self.assertNotIn('Camille',result.text)
            self.no_created();notification.assert_not_called()
            values.update(public_id='0042',evolution_csrf=result.json['csrf_token'])
            result=self.post(values);self.assertEqual(result.status_code,200);self.assertTrue(result.json['ok']);notification.assert_called_once()
        user=self.db.execute("SELECT * FROM users WHERE public_id='0042'").fetchone()
        self.assertEqual(user['first_name'],'Camille');self.assertEqual(user['email'],'camille@example.invalid')
        self.assertEqual(self.client.get(result.json['redirect']).status_code,200)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users').fetchone()[0],self.before+1)
    def test_html_fallback_has_retained_fields_and_inline_error(self):
        token=self.start();used=self.db.execute('SELECT public_id FROM users LIMIT 1').fetchone()[0]
        response=self.client.post('/inscription',data=self.payload(token,used))
        self.assertEqual(response.status_code,409);self.assertIn('id="public-id-error"',response.text);self.assertIn('aria-invalid="true"',response.text)
        for value in ('Camille','EXEMPLE','camille@example.invalid','non_binary','1990','Ville fictive'):self.assertIn(value,response.text)
        self.assertIn('value="'+used+'"',response.text);self.no_created()
    def test_other_validation_errors_have_correct_fields(self):
        for key,value in [('first_name',''),('email','invalide'),('public_id','abc')]:
            token=self.start();values=self.payload(token);values[key]=value
            response=self.post(values);self.assertEqual(response.status_code,400)
            self.assertIn(key,response.json['field_errors']);self.assertNotIn(enrollment_feedback.USED_ID,response.text);self.no_created()
    def test_unknown_integrity_failure_not_reported_as_identifier_collision(self):
        token=self.start()
        with patch('evolution_routes.create_user',side_effect=sqlite3.IntegrityError('CHECK constraint failed: FAKE_SECRET')),patch('evolution_routes.after_creation') as notify:
            response=self.post(self.payload(token))
        self.assertEqual(response.status_code,503);self.assertNotIn('public_id',response.json['field_errors']);self.assertNotIn('FAKE_SECRET',response.text);notify.assert_not_called();self.no_created()
        self.assertTrue(self.client.get('/inscription/etat',headers={'X-OpenFabLab-Enrollment':response.json['csrf_token']}).json['active'])
    def test_real_unique_constraint_failure_has_explicit_field(self):
        token=self.start()
        def duplicate(db,user,*args):
            row=dict(user);row['public_id']=self.db.execute('SELECT public_id FROM users LIMIT 1').fetchone()[0]
            from evolution_users import create_user
            return create_user(db,row,'kiosk')
        with patch('evolution_routes.create_user',side_effect=duplicate):response=self.post(self.payload(token))
        self.assertEqual(response.status_code,409);self.assertEqual(response.json['field_errors']['public_id'],enrollment_feedback.USED_ID);self.no_created()
    def test_partial_insert_rolled_back_and_no_notification(self):
        token=self.start()
        def fail(db,user,*args):
            from evolution_users import create_user
            create_user(db,user,'kiosk');raise sqlite3.OperationalError('FAKE_PRIVATE_DETAILS')
        with patch('evolution_routes.create_user',side_effect=fail),patch('evolution_routes.after_creation') as notify:response=self.post(self.payload(token))
        self.assertEqual(response.status_code,503);self.assertNotIn('FAKE_PRIVATE_DETAILS',response.text);self.no_created();notify.assert_not_called()
    def test_parallel_distinct_forms_same_identifier_create_once(self):
        clients=[self.app.test_client(),self.app.test_client()];tokens=[self.start(client) for client in clients];gate=threading.Barrier(2)
        def submit(index):gate.wait();return self.post(self.payload(tokens[index]),clients[index]).status_code
        with patch('evolution_routes.after_creation') as notify:
            with concurrent.futures.ThreadPoolExecutor(2) as pool:results=list(pool.map(submit,range(2)))
            notify.assert_called_once()
        self.assertEqual(sorted(results),[200,409]);self.assertEqual(self.db.execute("SELECT COUNT(*) FROM users WHERE public_id='0042'").fetchone()[0],1)
    def test_validation_database_error_is_generic_retryable_and_private(self):
        token=self.start()
        api=inspect.getclosurevars(self.app.view_functions['evolution.enroll']).nonlocals['a']
        with patch.object(api,'validate_user_form',side_effect=sqlite3.OperationalError('PRIVATE_DETAIL')):
            response=self.post(self.payload(token))
        self.assertEqual(response.status_code,503);self.assertEqual(response.json['field_errors'],{})
        self.assertNotIn('PRIVATE_DETAIL',response.text);self.assertNotIn('Camille',response.text);self.no_created()
        result=self.post(self.payload(response.json['csrf_token']));self.assertEqual(result.status_code,200)
    def test_json_is_not_csrf_bypass_and_does_not_add_id_lookup(self):
        self.start();response=self.post(self.payload('invalid'))
        self.assertEqual(response.status_code,400);self.no_created()
        self.assertEqual(self.client.get('/inscription?public_id=0042',headers={'Accept':'application/json','X-OpenFabLab-Enrollment-Form':'1'}).mimetype,'text/html')
    def test_required_contact_errors_are_attached_to_actual_fields(self):
        self.assertEqual(set(enrollment_feedback.field_errors(['Coordonnées obligatoires : e-mail, téléphone.'])),{'email','phone'})
    def test_departure_template_uses_native_modal_and_preserves_two_actions(self):
        body=self.client.get('/').text
        self.assertIn('<dialog class="departure-dialog-backdrop"',body)
        self.assertIn('aria-labelledby="departure-dialog-title"',body)
        self.assertEqual(body.count('data-departure-cancel'),1);self.assertEqual(body.count('data-departure-confirm'),1)
    def test_enhanced_response_preserves_replay_and_cancel_guards(self):
        token=self.start();used=self.db.execute('SELECT public_id FROM users LIMIT 1').fetchone()[0];result=self.post(self.payload(token,used));new=result.json['csrf_token']
        self.assertNotEqual(token,new)
        self.assertEqual(self.post(self.payload(token)).status_code,303)
        self.client.post('/inscription/annuler',data={'evolution_csrf':new})
        self.assertEqual(self.post(self.payload(new)).status_code,400);self.no_created()
    def test_all_manual_modes_omit_machine_information_but_home_and_identification_keep_it(self):
        from tests.test_v214_core import NewVersion
        import machine_maintenance as machines
        write_setting(self.db,'module_maintenance','1');key=machines.directory(self.db)[0]['resource_uuid']
        machines.set_condition(self.db,key,dict(status='maintenance',visibility_controls='1',public_visible='1'),'admin','admin')
        for mode in ('both','home','identification','none'):
            write_setting(self.db,'kiosk_machine_information',mode);self.db.commit()
            body=self.client.get('/usagers').text
            self.assertNotIn('data-machine-dialog',body);self.assertNotIn('machine-information',body);self.assertIn('data-user-search',body)
            self.assertEqual('data-machine-dialog' in self.client.get('/').text,mode in ('both','home'))
            self.assertEqual('data-machine-dialog' in self.client.get('/identification').text,mode in ('both','identification'))
