"""Isolated route tests for the presentation/ownership of existing settings."""
import json
import unittest
from unittest.mock import patch

from tests.test_app import OpenFabLabTestCase
import reservation_notifications as notices
import reservation_email_templates as mail


PORTAL = '/admin/reglages/comptes-en-ligne'
APPEARANCE = '/admin/reglages/affichage'
COMMUNICATION = '/admin/reglages/notifications'
USERS = '/admin/reglages/usagers'
MAIL_MODELS = '/admin/reglages/structure/emails-reservation'
STRUCTURE = '/admin/reglages/structure'
RESOURCES = '/admin/reglages/ressources'
WARNING = 'Pour vos essais, utilisez une installation distincte afin de préserver vos données réelles.'


class OnlineSettings218(unittest.TestCase):
    def setUp(self):
        self.fixture = OpenFabLabTestCase()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.client = self.fixture.client
        self.db = self.fixture.database()
        self.addCleanup(self.db.close)
        self.set_values(setup_completed='1', reservation_wordpress_url='https://atelier.example.invalid',
                        online_account_url='https://atelier.example.invalid/mon-compte/',
                        online_accounts_enabled='1', online_signup_enabled='1',
                        online_approval='manual', online_session_minutes='24',
                        online_ticket_minutes='16', online_mail_signature='L’équipe de l’atelier fictif',
                        online_discord_signup_review='1', online_discord_family_review='1',
                        online_discord_activated='0', online_discord_denied='1')
        outbound = patch('app.post_discord_message', side_effect=AssertionError('No network in this test'))
        outbound.start()
        self.addCleanup(outbound.stop)
        self.fixture.login_admin()

    def set_values(self, **values):
        self.db.executemany('INSERT INTO app_settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                            values.items())
        self.db.commit()

    def value(self, key):
        row = self.db.execute('SELECT value FROM app_settings WHERE key=?', (key,)).fetchone()
        return row[0] if row else None

    def post(self, url, **data):
        with self.client.session_transaction() as session:
            token = session['evolution_csrf']
        return self.client.post(url, data=dict(evolution_csrf=token, **data), follow_redirects=True)

    def test_portal_renders_historical_navigation_and_retains_moved_options(self):
        self.set_values(online_header_tasks='0')
        response = self.client.get(PORTAL)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Navigation des réglages', response.text)
        self.assertIn('href="'+PORTAL+'" aria-current="page">Comptes en ligne', response.text)
        self.assertIn(WARNING, response.text)
        self.assertNotIn('name="online_discord_', response.text)
        self.assertNotIn('name="online_header_tasks"', response.text)
        self.assertNotIn('name="online_mail_signature"', response.text)
        self.assertIn('value="https://atelier.example.invalid/mon-compte/"', response.text)
        result = self.post(PORTAL, online_accounts_enabled='1', online_signup_enabled='1',
                           online_approval='conditional', online_header_tasks='1', online_discord_activated='1')
        self.assertIn('ont été enregistrés', result.text)
        self.assertEqual(self.value('online_approval'), 'conditional')
        self.assertEqual(self.value('online_session_minutes'), '24')
        self.assertEqual(self.value('online_ticket_minutes'), '16')
        self.assertEqual(self.value('online_header_tasks'), '0')
        self.assertEqual(self.value('online_discord_signup_review'), '1')
        self.assertEqual(self.value('online_discord_denied'), '1')
        self.assertEqual(self.value('online_discord_activated'), '0')

    def test_portal_keeps_csrf_and_rolls_back_on_invalid_address_or_environment(self):
        self.assertEqual(self.client.post(PORTAL, data={'online_approval':'automatic'}).status_code,400)
        self.post(PORTAL, online_accounts_enabled='1', online_signup_enabled='1',
                  online_approval='automatic', online_account_url='https://different.example.invalid/mon-compte/')
        self.assertEqual(self.value('online_approval'),'manual')
        self.assertEqual(self.value('online_account_url'),'https://atelier.example.invalid/mon-compte/')
        self.db.execute("INSERT INTO online_requests VALUES('test','signup','{}','pending@example.invalid',NULL,'review',1,2)")
        self.db.commit()
        self.post(PORTAL, online_accounts_enabled='1', online_signup_enabled='1', online_relay_environment='test')
        self.assertEqual(self.value('online_relay_environment'),'production')

    def test_counter_moves_to_appearance_without_writing_borne_options(self):
        self.assertEqual(self.value('online_header_tasks'),'1')
        self.assertIn('name="online_header_tasks" type="checkbox" value="1" checked', self.client.get(APPEARANCE).text)
        self.set_values(openlab_attendance_show_decimals='1')
        self.assertEqual(self.client.post(APPEARANCE+'/enregistrer', data={'admin_task_preferences_present':'1'}).status_code,400)
        self.post(APPEARANCE+'/enregistrer', admin_task_preferences_present='1')
        self.assertEqual(self.value('online_header_tasks'),'0')
        self.assertEqual(self.value('openlab_attendance_show_decimals'),'1')
        self.post(APPEARANCE+'/enregistrer', home_theme='default')
        self.assertEqual(self.value('online_header_tasks'),'0')
        self.post(APPEARANCE+'/enregistrer', admin_task_preferences_present='1', online_header_tasks='1')
        self.assertEqual(self.value('online_header_tasks'),'1')

    def test_discord_reuses_events_without_including_identity_or_changing_webhook(self):
        page = self.client.get(COMMUNICATION).text
        self.assertIn('Comptes et familles',page)
        self.assertIn('name="online_discord_denied" type="checkbox" value="1" checked',page)
        self.assertEqual(self.client.post(COMMUNICATION, data={'online_discord_present':'1'}).status_code,400)
        self.post(COMMUNICATION, online_discord_present='1', online_discord_activated='1',
                  reservation_message_online_activated='Accès confirmé.')
        self.assertEqual(self.value('online_discord_activated'),'1')
        self.assertEqual(self.value('online_discord_denied'),'0')
        self.assertEqual(notices.message(self.db,{'event_type':'online_activated','email':'private@example.invalid'}),
                         'Accès confirmé.')
        self.post(COMMUNICATION, online_discord_present='1', online_discord_denied='1',
                  reservation_message_online_activated='Rendez-vous sur https://exemple.invalid')
        self.assertEqual(self.value('online_discord_denied'),'0')
        self.assertEqual(self.value('discord_reservation_message_online_activated'),'Accès confirmé.')
        self.post(COMMUNICATION, webhook_only='1')
        self.post(COMMUNICATION, enabled='0')
        self.assertEqual(self.value('online_discord_activated'),'1')
        self.assertEqual(self.value('discord_reservation_message_online_activated'),'Accès confirmé.')

    def test_moderator_cannot_save_any_of_the_relocated_preferences(self):
        with self.client.session_transaction() as session:
            session.update(access_role='moderator',admin_authenticated=False)
        self.post(PORTAL, online_approval='automatic')
        self.post(APPEARANCE+'/enregistrer', admin_task_preferences_present='1')
        self.post(COMMUNICATION, online_discord_present='1')
        self.assertEqual(self.value('online_approval'),'manual')
        self.assertEqual(self.value('online_header_tasks'),'1')
        self.assertEqual(self.value('online_discord_denied'),'1')

    def test_nine_discord_events_individually_configurable(self):
        keys=set(notices.ONLINE_DISCORD_EVENTS)
        self.assertEqual(len(keys),9)
        self.assertEqual({key for key in keys if notices.ONLINE_DISCORD_DEFAULTS[key]=='1'},
                         {'created','created_admin','child_created','family_done','creation_volume'})
        page=self.client.get(COMMUNICATION).text
        fields={}
        for index,key in enumerate(sorted(keys)):
            self.assertIn(f'name="online_discord_{key}"',page)
            self.assertIn(f'name="reservation_message_online_{key}"',page)
            fields[f'reservation_message_online_{key}']=f'Texte fictif {index}'
        for checked in ({'created','family_done','denied'}, keys-{'created','family_done','denied'}):
            self.post(COMMUNICATION,online_discord_present='1',
                      **{f'online_discord_{key}':'1' for key in checked},**fields)
            for key in keys:
                self.assertEqual(self.value('online_discord_'+key),str(int(key in checked)))
                self.assertEqual(self.value('discord_reservation_message_online_'+key),
                                 fields['reservation_message_online_'+key])

    def test_editor_adds_all_account_models_and_preserves_reservation_templates(self):
        self.set_values(reservation_email_confirmed_subject='Atelier : {animation}')
        path=MAIL_MODELS+'?kind=online_verify'
        page=self.client.get(path)
        self.assertEqual(page.status_code,200)
        self.assertIn('<optgroup label="Comptes et familles">',page.text)
        for kind in mail.ONLINE_INTRO:
            self.assertIn(f'<option value="{kind}"',page.text)
        self.assertIn('#lien-de-demonstration',page.text)
        self.assertNotIn('#ofl-account=',page.text)
        self.assertNotIn('L’équipe de l’atelier fictif',page.text)
        fields=dict(kind='online_verify',subject='Bienvenue chez {structure}',body='Merci !\n\nL’équipe.')
        preview=self.post(MAIL_MODELS,action='preview',**fields)
        self.assertIn('Bienvenue chez Atelier Exemple',preview.text)
        self.assertIn('#lien-de-demonstration',preview.text)
        self.assertIsNone(self.value('online_email_verify_subject'))
        self.post(MAIL_MODELS,action='save',**fields)
        self.assertEqual(mail.load(self.db,'online_verify'),{'subject':fields['subject'],'body':fields['body']})
        self.assertEqual(mail.load(self.db,'confirmed')['subject'],'Atelier : {animation}')
        self.post(MAIL_MODELS,action='reset',kind='online_verify')
        self.assertEqual(mail.load(self.db,'online_verify'),mail.default('online_verify'))

    def test_account_variable_rules_and_exactly_one_protected_link(self):
        url='https://atelier.example.invalid/mon-compte/#lien-de-demonstration'
        for kind in mail.ACCOUNT_LINK_MODELS:
            for text in ('Texte seul','Cliquez : {lien_compte}','Variable littérale : {{lien_compte}}'):
                subject,plain,html=mail.render_online(kind,{'subject':'Sujet {structure}','body':text},
                    'Atelier <fictif>',url,'0420')
                self.assertEqual(subject,'Sujet Atelier <fictif>')
                self.assertEqual(plain.count(url),1)
                self.assertEqual(html.count(url),1)
                self.assertIn('class="reservation-mail-button"',html)
        for field,kind,value in (
            ('subject','online_verify','{lien_compte}'), ('subject','online_identifier','{identifiant}'),
            ('body','online_family_done','{lien_compte}'), ('body','online_recover','{lien_compte} {lien_compte}'),
            ('body','online_verify','{structure.__class__}'), ('body','online_verify','{animation}'),
        ):
            with self.subTest(field=field,kind=kind,value=value),self.assertRaises(ValueError):
                mail.validate(value,field,kind)
        _,plain,html=mail.render_online('online_identifier',{'subject':'Votre code','body':'Merci <script>'},
                                        'Atelier Exemple',public_id='0420')
        self.assertIn('0420',plain)
        self.assertIn('0420',html)
        self.assertNotIn('<script>',html)

    def test_resources_module_without_redundant_shortcut(self):
        page=self.client.get(STRUCTURE)
        self.assertEqual(page.status_code,200)
        self.assertIn('name="module_resources"',page.text)
        self.assertIn('href="'+RESOURCES+'"',page.text)
        self.assertNotIn('id="resources-options"',page.text)
        self.assertNotIn('Suivi, nom public et fiches QR des ressources',page.text)
        settings=self.client.get(RESOURCES)
        self.assertEqual(settings.status_code,200)
        self.assertIn('id="resources-options"',settings.text)
        self.assertIn('Fiches QR et tutoriels publics',settings.text)


def snapshots():
    case = OnlineSettings218()
    case.setUp()
    try:
        pages = {}
        for key,path in dict(portal=PORTAL,appearance=APPEARANCE,communication=COMMUNICATION,users=USERS,
                             emails=MAIL_MODELS+'?kind=online_verify',structure=STRUCTURE,resources=RESOURCES).items():
            result=case.client.get(path)
            assert result.status_code==200, (key, result.status_code)
            pages[key]=result.text
        pages['counts']=case.client.get('/admin/elements-a-traiter.json').json
        print(json.dumps(pages))
    finally:
        case.doCleanups()


if __name__=='__main__':
    import sys
    snapshots() if '--snapshots' in sys.argv else unittest.main()
