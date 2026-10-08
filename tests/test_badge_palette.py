"""Pastel rendering and display-only visitor preference; fictional data only."""
import io
import re
import unittest
from app import create_app
from badge_palette import DEFAULT_REFERENCE, contrast, normalize_color, pastel_palette, validate_color
from profile_archive import build_profile, parse_profile
from tests import test_app as fixtures


class PaletteTests(unittest.TestCase):
    def test_reference_is_preserved_not_used_as_background(self):
        for color in ('#008cad', '#527a27', '#ff8844', '#ffbb00', '#b31800', '#72828a', '#ffee44', '#112233'):
            palette = pastel_palette(color)
            self.assertEqual(palette['reference'], color)
            self.assertNotEqual(palette['background'], color)
            self.assertGreaterEqual(contrast(palette['background'], palette['ink']), 4.5)

    def test_deterministic_rounding(self):
        self.assertEqual(pastel_palette('#112233'), {'reference': '#112233', 'background': '#e7e9eb', 'ink': '#070e14', 'border': '#dbdee0'})
        self.assertEqual(pastel_palette('#112233'), pastel_palette('#112233'))

    def test_light_dark_and_rgb_grid_accessibility(self):
        for r in range(0, 256, 17):
            for g in range(0, 256, 17):
                for b in range(0, 256, 17):
                    palette = pastel_palette(f'#{r:02x}{g:02x}{b:02x}')
                    self.assertGreaterEqual(contrast(palette['background'], palette['ink']), 4.5)
                    self.assertTrue(all(int(palette['background'][i:i+2], 16) >= 230 for i in (1, 3, 5)))

    def test_invalid_values_have_safe_neutral_fallback(self):
        for value in ('red', '#abc', '#abcdeF00', '#ffffff;}body{color:red', None, {}, ''):
            self.assertEqual(pastel_palette(value), pastel_palette(DEFAULT_REFERENCE))

    def test_validation_does_not_accept_css_or_coerce_values(self):
        self.assertEqual(validate_color('#AbCdEf'), '#abcdef')
        for value in (' red ', 123456, '#abcdef\n', '#fff', '#ffffff00'):
            with self.assertRaises(ValueError): validate_color(value)
        self.assertEqual(normalize_color(None), DEFAULT_REFERENCE)


class VisitorDisplayTests(unittest.TestCase):
    endpoint = '/admin/reglages/affichage/visiteurs'

    def setUp(self):
        self.f = fixtures.OpenFabLabTestCase(); self.f.setUp(); self.addCleanup(self.f.tearDown)
        self.client = self.f.client
        self.db = self.f.database(); self.addCleanup(self.db.close)

    def value(self):
        return self.db.execute("SELECT value FROM app_settings WHERE key='anonymous_visitor_color'").fetchone()[0]

    def token(self):
        page = self.client.get('/admin/reglages/affichage').get_data(as_text=True)
        return re.search(r'name="evolution_csrf" value="([^"]+)"', page).group(1)

    def save(self, value, token=None):
        return self.client.post(self.endpoint, data={'anonymous_visitor_color': value, 'evolution_csrf': token or self.token()})

    def import_profile(self, raw):
        page = self.client.get('/admin/reglages/structure').get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        for step in ('preview', 'apply'):
            response = self.client.post('/admin/profil/importer', data={'csrf_token': token, 'step': step,
                'confirmation': 'IMPORTER LE PROFIL', 'profile_file': (io.BytesIO(raw), 'example-profile.zip')})
            self.assertEqual(response.status_code, 302)

    def test_default_is_soft_blue_grey_schema_stays_17(self):
        self.assertEqual(self.value(), DEFAULT_REFERENCE)
        self.assertEqual(self.db.execute('PRAGMA user_version').fetchone()[0], 18)
        self.assertEqual(pastel_palette(self.value())['background'], '#f1f3f3')

    def test_setting_creates_no_category_or_user(self):
        self.f.login_admin()
        before = [tuple(row) for row in self.db.execute('SELECT * FROM user_categories')]
        users = [tuple(row) for row in self.db.execute('SELECT * FROM users')]
        self.assertEqual(self.save('#8844CC').status_code, 302)
        self.assertEqual(self.value(), '#8844cc')
        self.assertEqual([tuple(row) for row in self.db.execute('SELECT * FROM user_categories')], before)
        self.assertEqual([tuple(row) for row in self.db.execute('SELECT * FROM users')], users)

    def test_restart_preserves_color_and_existing_settings(self):
        self.f.login_admin(); self.save('#225577')
        before = dict(self.db.execute('SELECT key,value FROM app_settings'))
        restarted = create_app(dict(self.f.app.config))
        with restarted.app_context():
            from app import get_database
            db = get_database()
            self.assertEqual(dict(db.execute('SELECT key,value FROM app_settings')), before)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 18)

    def test_existing_schema17_gets_default_without_changing_business_rows(self):
        self.db.execute("DELETE FROM app_settings WHERE key='anonymous_visitor_color'"); self.db.commit()
        before = [tuple(row) for row in self.db.execute('SELECT * FROM users')]
        create_app(dict(self.f.app.config))
        self.assertEqual(self.value(), DEFAULT_REFERENCE)
        self.assertEqual([tuple(row) for row in self.db.execute('SELECT * FROM users')], before)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_server_rejects_invalid_color_without_changing_settings(self):
        self.f.login_admin()
        before = dict(self.db.execute('SELECT key,value FROM app_settings'))
        for value in ('red', '#abc', '#123456;}bad', '#12345600', ''):
            self.assertEqual(self.save(value).status_code, 400)
        self.assertEqual(dict(self.db.execute('SELECT key,value FROM app_settings')), before)

    def test_csrf_rejected_without_write(self):
        self.f.login_admin()
        self.assertEqual(self.save('#123456', 'invalid').status_code, 400)
        self.assertEqual(self.value(), DEFAULT_REFERENCE)

    def test_moderator_cannot_change_display_color(self):
        self.f.login_admin(); token = self.token()
        with self.client.session_transaction() as session:
            session['access_role'] = 'moderator'
        response = self.save('#123456', token)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/admin')
        self.assertEqual(self.value(), DEFAULT_REFERENCE)

    def test_anonymous_cannot_change_display_color(self):
        self.assertIn(self.save('#123456', 'invalid').status_code, (302, 403))
        self.assertEqual(self.value(), DEFAULT_REFERENCE)

    def test_get_has_no_side_effect(self):
        self.f.login_admin()
        self.assertEqual(self.client.get(self.endpoint).status_code, 405)
        self.assertEqual(self.value(), DEFAULT_REFERENCE)

    def test_real_profile_export_import_roundtrip(self):
        self.f.login_admin(); self.save('#aa55bb')
        raw = self.client.get('/admin/profil/exporter').data
        self.assertEqual(parse_profile(raw)['settings']['anonymous_visitor_color'], '#aa55bb')
        self.save('#556677'); self.import_profile(raw)
        self.assertEqual(self.value(), '#aa55bb')

    def test_old_profile_preserves_visitor_preference(self):
        self.f.login_admin(); self.save('#aa55bb')
        self.import_profile(build_profile({'home_title': 'Accueil exemple'}, [], {}))
        self.assertEqual(self.value(), '#aa55bb')

    def test_profile_rejects_invalid_visitor_color(self):
        for color in ('red', '#abc', '#ffffff;}bad'):
            with self.assertRaises(ValueError):
                parse_profile(build_profile({'anonymous_visitor_color': color}, [], {}))

    def test_visitor_styles_use_setting_but_do_not_enter_registry(self):
        self.f.login_admin(); self.save('#8844cc')
        self.db.execute("INSERT INTO visitors(created_at) VALUES('2026-10-06T12:00:00+00:00')"); self.db.commit()
        page = self.client.get('/admin').get_data(as_text=True)
        self.assertIn('category-visitor anonymous-visitor-badge', page)
        self.assertIn('.category-badge.anonymous-visitor-badge{--category-color:#8844cc;', page)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM user_categories WHERE category_key='visitor'").fetchone()[0], 0)
        self.assertNotIn('anonymous-visitor-badge">Visiteur', self.client.get('/').get_data(as_text=True))

    def test_visitor_preference_does_not_change_calendar_or_reservations(self):
        self.f.login_admin()
        before = dict(self.db.execute("SELECT key,value FROM app_settings WHERE key LIKE 'calendar_%' OR key LIKE 'reservation_%'"))
        self.save('#cceeaa')
        self.assertEqual(dict(self.db.execute("SELECT key,value FROM app_settings WHERE key LIKE 'calendar_%' OR key LIKE 'reservation_%'")), before)

    def test_display_form_is_separate_and_preview_present(self):
        self.f.login_admin()
        page = self.client.get('/admin/reglages/affichage').get_data(as_text=True)
        self.assertIn('Visiteur anonyme', page)
        self.assertIn('id="anonymous-visitor-color"', page)
        self.assertIn('action="' + self.endpoint + '"', page)
        self.assertIn('anonymous-visitor-badge">Visiteur', page)

    def test_custom_account_category_named_visitor_is_independent(self):
        stamp = '2026-10-06T12:00:00+00:00'
        self.db.execute('INSERT INTO user_categories VALUES(?,?,?,?,?,?,?,?,?)', ('visitor', 'Catégorie fictive', 'categorie fictive', '#aa22bb', 1, 99, 0, stamp, stamp))
        self.db.commit(); self.f.login_admin(); self.save('#225588')
        page = self.client.get('/admin').get_data(as_text=True)
        self.assertIn('.category-badge.category-visitor{--category-color:#aa22bb;', page)
        self.assertIn('.category-badge.anonymous-visitor-badge{--category-color:#225588;', page)

    def test_save_preserves_installation_url_prefix(self):
        self.f.login_admin(); token = self.token()
        response = self.client.post(self.endpoint, data={'anonymous_visitor_color': '#225588',
            'evolution_csrf': token}, environ_overrides={'SCRIPT_NAME': '/stat'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers['Location'], '/stat/admin/reglages/affichage#anonymous-visitor-color')
        self.assertEqual(self.value(), '#225588')
