"""Consolidation contracts; no external services and only fictional data."""
from datetime import date
import json
from pathlib import Path
import re
import tempfile
import unittest

import app
import billing
import machine_maintenance as machines
import private_backup
from tests import test_v214_core as fixture
from updater_agent.installation import setup_target
from updater_agent.security import Refused


class Consolidation(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.NewVersion()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.db, self.client, self.key = self.fixture.db, self.fixture.client, self.fixture.key
        self.route = '/admin/ressources/' + self.key + '/fiche'

    def test_all_direct_transitions_and_stale_unavailability_fields(self):
        for source in machines.STATES:
            for target in machines.STATES:
                with self.subTest(source=source, target=target), self.db:
                    machines.set_condition(self.db, self.key, dict(status=source, availability_mode='rental',
                                           visibility_controls='1', public_visible='1'), 'admin', 'fiction')
                    fields = dict(status=target, return_estimate='date héritée' if target == 'operational' else '2026-11-12',
                                  public_reason='x' * 501 if target == 'operational' else 'Réglage fictif')
                    machines.set_condition(self.db, self.key, fields, 'moderator', 'fiction')
                    item = machines.machine(self.db, self.key)
                    self.assertEqual(item['status'], target)
                    self.assertEqual(item['availability_mode'], 'rental')
                    self.assertEqual(item['public_listed'], 1)
                    if target == 'operational':
                        self.assertEqual((item['return_estimate'], item['public_reason']), (None, ''))
                    self.assertEqual(len(machines.public_machines(self.db, unavailable_only=True)), int(target != 'operational'))

    def test_complete_maintenance_is_explicit_and_links_one_reminder(self):
        token = self.fixture.login('moderator')
        with self.db:
            machines.set_condition(self.db, self.key, {'status':'maintenance'}, 'admin', 'fiction')
            ids = [machines.reminder(self.db, self.key, {'due_on':'2099-01-01','subject':subject},
                                    'admin', 'fiction') for subject in ('Contrôle fictif','Autre rappel')]
        form = dict(action='finish_maintenance', performed_on=date.today().isoformat(), kind='care',
                    description='Nettoyage fictif', evolution_csrf=token, linked_reminder=ids[0]+':1')
        self.assertEqual(self.client.post(self.route, data=form).status_code, 400)
        self.assertEqual(machines.machine(self.db, self.key)['status'], 'maintenance')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM machine_interventions').fetchone()[0], 0)
        self.assertEqual(self.client.post(self.route, data=dict(form, confirm_operational='1')).status_code, 302)
        rows = {r['reminder_uuid']: (r['state'],r['intervention_uuid']) for r in self.db.execute('SELECT * FROM machine_reminders')}
        self.assertEqual(rows[ids[1]], ('pending', None))
        self.assertEqual(rows[ids[0]][0], 'done')
        self.assertTrue(rows[ids[0]][1])
        self.assertEqual(machines.machine(self.db, self.key)['status'], 'operational')
        self.assertEqual(self.client.get(self.route).status_code, 200)

    def quote(self, **changes):
        return dict(dict(quote_date='2026-11-11', client_contact='Camille FICTIF',
            client_structure='Association fictive', address_line='1 voie fictive', postal_code='00000',
            city='Ville fictive', phone='0000000000', email='test@example.invalid', title='Atelier fictif',
            description='Essai', activity_date='2026-11-20', participants='8', rate_category='normal',
            rate_unit='half_day', rate_quantity='2', travel_quantity='0', consumable_mode='included',
            consumable_quantity='0', inline_tariff_name='Découverte fictive', inline_tariff_amount='12.35'), **changes)

    def test_inline_prices_and_signed_document_snapshot(self):
        self.fixture.login()
        url = '/admin/facturation/nouveau'
        page = self.client.get(url)
        self.assertIn('Créer un tarif permanent', page.text)
        with self.client.session_transaction() as session:
            csrf = session['pin_csrf']
        self.assertEqual(self.client.post(url,data=self.quote(custom_tariff_key='@catalogue')).status_code, 400)
        self.assertEqual(self.client.post(url,data=self.quote(custom_tariff_key='@catalogue', csrf_token=csrf,
                                                             inline_tariff_amount='-1')).status_code, 400)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM billing_tariff_catalog').fetchone()[0], 0)
        for key, price, total in (('@catalogue', '12.35', 2470),('@exception','0',0)):
            data = self.quote(custom_tariff_key=key, csrf_token=csrf, inline_tariff_amount=price)
            self.assertEqual(self.client.post(url, data=data).status_code, 302)
            record = dict(self.db.execute('SELECT * FROM billing_records ORDER BY id DESC LIMIT 1').fetchone())
            self.assertEqual(record['amount_cents'], total)
            self.assertEqual(record['custom_tariff_name'], data['inline_tariff_name'])
            self.assertIn(data['inline_tariff_name'], str(billing.line_items(record)))
        row = self.db.execute('SELECT name,cents,unit FROM billing_tariff_catalog').fetchone()
        self.assertEqual(tuple(row), ('Découverte fictive',1235,'half_day'))
        edit = '/admin/facturation/'+str(record['id'])
        self.assertEqual(self.client.post(edit+'/signer').status_code, 302)
        for suffix in ('/modifier','/edit'):
            edit_form = self.client.get(edit+suffix)
            if edit_form.status_code == 200:
                break
        self.assertEqual(edit_form.status_code, 200)
        altered = self.client.post(edit_form.request.path,data=dict(data,inline_tariff_amount='5.10'))
        self.assertEqual(altered.status_code, 400)
        self.assertIn('dossier signé ou facturé', altered.text)
        self.assertEqual(self.db.execute('SELECT amount_cents FROM billing_records WHERE id=?',(record['id'],)).fetchone()[0], 0)

    def test_local_voice_opt_in_and_no_replay(self):
        with self.db:
            app.write_setting(self.db, 'kiosk_sound_enabled', '0')
        def token(path='/'):
            return json.loads(re.search(r'id="kiosk-audio">(.*?)</script>',self.client.get(path).text)[1])
        def visitor(value):
            return self.client.post('/visiteurs',data={'kiosk_action':value},headers={'X-OFL-Kiosk':'1'}).json
        disabled = token()
        self.assertFalse(disabled['voice']['enabled'])
        self.assertNotIn('voice', visitor(disabled['token']))
        with self.db:
            app.write_setting(self.db, 'kiosk_voice_enabled', '1')
        enabled = token()
        self.assertEqual(visitor(enabled['token'])['voice'], dict(event='visitor', first=''))
        self.assertNotIn('voice', visitor(enabled['token']))
        identified = token('/identification')
        user = self.db.execute('SELECT first_name,public_id FROM users WHERE id=?',(self.fixture.f.a,)).fetchone()
        response = self.client.post('/identification', data=dict(kiosk_action=identified['token'], public_id=user[1]),
                                    headers={'X-OFL-Kiosk':'1'})
        self.assertEqual(response.json['voice'], dict(event='arrival', first=user[0].split()[0]))
        self.assertNotIn('voice', self.client.post('/identification', data=dict(kiosk_action=identified['token'], public_id=user[1]),
                                                   headers={'X-OFL-Kiosk':'1'}).json)

    def test_native_backup_accepts_216_without_a_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / 'fictional.zip'
            private_backup.create_backup(self.fixture.path, package, kind='complete')
            target = Path(directory) / 'restored.db'
            private_backup.restore_backup(package, target)
            import sqlite3
            with sqlite3.connect(target) as restored:
                self.assertEqual(restored.execute('PRAGMA user_version').fetchone()[0], 28)
                self.assertEqual(restored.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_setup_version_schema_and_protocol_are_independent(self):
        baseline = dict(version='2.16.0', schema=28, agent_protocol=1)
        self.assertEqual(setup_target(baseline), ('2.16.0', 28))
        for change in (dict(schema=27), dict(agent_protocol=2), dict(version='2.16.1'), dict(version=[])):
            with self.assertRaisesRegex(Refused, 'SUPPORTED_VERSION_SCHEMA_AND_PROTOCOL'):
                setup_target(dict(baseline, **change))
