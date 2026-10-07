"""Tests automatisés des parcours essentiels d'OpenFabLab."""

import os
import io
import json
import re
import sqlite3
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree
from unittest import mock
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from werkzeug.test import Client
from werkzeug.wrappers import Response
from flask.testing import FlaskClient


class BrowserClient(FlaskClient):
    """Legacy browser scenarios submit the hidden token rendered by the form.

    Security-negative tests explicitly use an unwrapped FlaskClient instead.
    """
    def post(self, path, *args, **kwargs):
        if path=='/admin/usagers/nouveau' or (path.startswith('/admin/usagers/') and path.endswith('/modifier')):
            page=self.get(path).get_data(as_text=True)
            token=re.search(r'name="evolution_csrf" value="([^"]+)"',page)
            if token and isinstance(kwargs.get('data'),dict):
                kwargs['data']=dict(kwargs['data'],evolution_csrf=token[1])
        return super().post(path,*args,**kwargs)

# L'instance Flask globale créée lors de l'import utilise elle aussi une base
# temporaire : la suite de tests ne doit jamais ouvrir la base locale réelle.
_import_database_directory = tempfile.TemporaryDirectory(prefix="openfablab_import_test_")
_previous_database_path = os.environ.get("COMPTEUR_DATABASE")
_previous_secret_path = os.environ.get('COMPTEUR_SECRET_KEY_FILE')
os.environ["COMPTEUR_DATABASE"] = str(Path(_import_database_directory.name) / "import.db")
os.environ['COMPTEUR_SECRET_KEY_FILE']=str(Path(_import_database_directory.name)/'import.secret')
from app import (
    collect_openlab_weather_snapshot,
    create_app,
    create_deployment_application,
    current_id_lock,
    get_database,
    normalize_first_name,
    record_invalid_user_id,
    run_invoice_payment_reminders,
    run_monthly_animation_reminder,
)
if _previous_database_path is None:
    os.environ.pop("COMPTEUR_DATABASE", None)
else:
    os.environ["COMPTEUR_DATABASE"] = _previous_database_path
if _previous_secret_path is None:
    os.environ.pop('COMPTEUR_SECRET_KEY_FILE',None)
else:
    os.environ['COMPTEUR_SECRET_KEY_FILE']=_previous_secret_path


# Explicitly fictional examples; never application defaults.
DEMO_CATALOG = {
    key: {'name': 'Machine fictive ' + str(index), 'monthly_cents': monthly, 'deposit_cents': deposit}
    for index,(key,monthly,deposit) in enumerate((
        ('prusa_mk39',7500,90000),('dagoma_sigma',5000,60000),('formbox',5000,80000),
        ('oculus_quest_1',2500,30000),('cameo_3',2500,30000),('mbot2',2500,30000)),1)
}
DEMO_SETTINGS = {
    'structure_name':'Atelier Exemple','structure_short_name':'Atelier Exemple',
    'structure_description':'FabLab de démonstration',
    'structure_legal_entity':'Association Exemple', 'structure_address':'1 voie Fictive',
    'structure_data_controller':'Association Exemple', 'structure_data_controller_address':'1 voie Fictive',
    'structure_email':'privacy@example.invalid','structure_website':'https://example.invalid',
    'structure_privacy_policy_url':'https://example.invalid/privacy',
    'billing_rate_normal_hourly_cents':'6000','billing_rate_normal_half_day_cents':'12000',
    'billing_rate_reduced_hourly_cents':'3000','billing_rate_reduced_half_day_cents':'6000',
    'billing_travel_unit_cents':'6000','billing_consumable_unit_cents':'3000',
    'billing_rental_contract_fee_cents':'2500','billing_rental_delivery_fee_cents':'3000',
    'structure_payment_days':'30', 'structure_payment_terms':'Conditions fictives de test.',
    'structure_rental_terms':'Conditions de location fictives. À adapter avant utilisation.',
    'structure_main_logo':'main.png', 'structure_institution_logo':'institution.png',
    'structure_signature':'signature.png',
}


class OpenFabLabTestCase(unittest.TestCase):
    def setUp(self):
        self._catalog_patch = mock.patch('app.DEFAULT_RENTAL_CATALOG', DEMO_CATALOG)
        self._billing_catalog_patch = mock.patch('billing.RENTAL_CATALOG', DEMO_CATALOG)
        self._catalog_patch.start()
        self._billing_catalog_patch.start()
        self.addCleanup(self._catalog_patch.stop)
        self.addCleanup(self._billing_catalog_patch.stop)
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="openfablab_test_"
        )
        self.database_path = str(
            Path(self.temporary_directory.name) / "openfablab_test.db"
        )
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.database_path,
                "SECRET_KEY": "test-secret-key",
                "ADMIN_PIN": "1379",
                "MODERATOR_PIN": "8642",
                "WEATHER_ENABLED": False,
                "BACKUP_ROOT": str(Path(self.temporary_directory.name) / "backups"),
                "BACKUP_DISPLAY_ROOT": "/server/backups",
            }
        )
        with sqlite3.connect(self.database_path) as database:
            database.executemany('UPDATE app_settings SET value=? WHERE key=?',
                                 [(value,key) for key,value in DEMO_SETTINGS.items()])
        from PIL import Image
        branding = Path(self.database_path).parent / 'branding'
        branding.mkdir()
        # Geometric placeholders only: no actual logo or handwritten signature.
        for name in ('main', 'institution', 'signature'):
            Image.new('RGB', (120, 40), '#307b9a').save(branding / (name + '.png'))
        self.app.test_client_class = BrowserClient
        self.client = self.app.test_client()

    def tearDown(self):
        self._catalog_patch.stop()
        self._billing_catalog_patch.stop()
        self.temporary_directory.cleanup()

    def database(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _login_token(self):
        page = self.client.get("/admin/connexion").get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)

    def login_admin(self, pin="1379"):
        return self.client.post(
            "/admin/connexion", data={"pin": pin, "csrf_token": self._login_token()}, follow_redirects=True
        )

    def test_main_pages_respond(self):
        for route in ("/", "/sante", "/identification", "/usagers", "/gestion-des-donnees", "/admin/connexion"):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)

        self.assertEqual(self.client.get("/sante").get_data(as_text=True), "OK\n")

        home_page = self.client.get("/").get_data(as_text=True)
        self.assertIn("Aujourd’hui au FabLab", home_page)
        self.assertNotIn("Compteur passage", home_page)
        self.assertIn("Atelier Exemple", home_page)
        self.assertNotIn("Bienvenue", home_page)
        self.assertNotIn("actuellement présent", home_page)
        self.assertIn("Aucun usager présent.", home_page)
        self.assertNotIn("Personne n'est encore enregistrée", home_page)
        self.assertNotIn(">Verrouiller</button>", home_page)

        identification_page = self.client.get("/identification").get_data(as_text=True)
        self.assertIn("Scanner mon QR code", identification_page)
        self.assertIn('data-qr-scanner', identification_page)
        self.assertIn('/static/vendor/jsQR-1.4.0.js', identification_page)
        self.assertIn('/static/qr-scanner.js', identification_page)
        self.assertIn("Ouverture automatique de la caméra avant", identification_page)
        self.assertNotIn("Présentez votre QR code.", identification_page)
        self.assertNotIn("Placez le QR code au centre du cadre", identification_page)
        self.assertNotIn("Utiliser plutôt la saisie manuelle", identification_page)
        self.assertNotIn(">\n            Ouvrir la caméra\n", identification_page)
        self.assertIn("Je n'ai pas mon badge ou mon identifiant", identification_page)
        self.assertIn('aria-label="Identifiant à 4 chiffres"', identification_page)

        data_page = self.client.get("/gestion-des-donnees").get_data(as_text=True)
        self.assertIn("Association Exemple", data_page)
        self.assertNotIn("mailto:privacy@example.invalid", data_page)
        self.assertIn("serveur de Atelier Exemple", data_page)
        self.assertIn("Une solution suivie et évolutive", data_page)
        self.assertIn("utilisé en situation réelle", data_page)
        self.assertIn("sécurité du logiciel restent des priorités", data_page)
        self.assertNotIn("remise à zéro de la base", data_page)
        self.assertIn("après 5 ans sans passage", data_page)
        self.assertIn("code source est ouvert sous licence MIT", data_page)
        self.assertIn("responsable de traitement", data_page)
        self.assertIn("agents expressément habilités", data_page)

        application_script = (Path(__file__).parents[1] / "static" / "app.js").read_text()
        application_styles = (Path(__file__).parents[1] / "static" / "style.css").read_text()
        self.assertIn("(min-height: 621px)", application_script)
        self.assertIn(
            "(orientation: landscape) and (min-width: 761px) and (min-height: 621px)",
            application_styles,
        )

        manifest_response = self.client.get("/manifest.webmanifest")
        self.assertEqual(manifest_response.status_code, 200)
        manifest = json.loads(manifest_response.get_data(as_text=True))
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["display"], "fullscreen")
        self.assertEqual(manifest["orientation"], "landscape")
        self.assertEqual(len(manifest["icons"]), 2)
        self.assertTrue(all("OpenFabLab-icon-" in icon["src"] for icon in manifest["icons"]))
        self.assertIn("OpenFabLab-logo-horizontal.svg", home_page)
        self.assertIn("OpenFabLab-icon.svg", home_page)

        service_worker = self.client.get("/service-worker.js")
        self.assertEqual(service_worker.status_code, 200)
        self.assertIn("self.addEventListener", service_worker.get_data(as_text=True))
        self.assertEqual(service_worker.headers["Service-Worker-Allowed"], "/")

        self.assertEqual(self.client.get("/admin").status_code, 302)
        self.login_admin()
        self.assertEqual(self.client.get("/admin").status_code, 200)
        self.assertEqual(self.client.get("/admin/usagers").status_code, 200)
        self.assertEqual(self.client.get("/admin/frequentation/statistiques").status_code, 200)
        closure_redirect = self.client.get("/admin/fermeture")
        self.assertEqual(closure_redirect.status_code, 302)
        self.assertIn("/admin/reglages", closure_redirect.headers["Location"])
        self.assertEqual(self.client.get("/admin/reglages").status_code, 302)
        backup_page = self.client.get("/admin/reglages/borne").get_data(as_text=True)
        self.assertIn("Heure d'éjection quotidienne", backup_page)
        self.assertEqual(self.client.get("/admin/animations").status_code, 200)
        self.assertEqual(self.client.get("/admin/facturation").status_code, 200)
        self.assertEqual(self.client.get("/admin/reglages/notifications").status_code, 200)
        self.assertEqual(self.client.get("/admin/usagers/nouveau").status_code, 200)

    def test_nas_prefix_hides_root_and_preserves_navigation(self):
        mounted_application = create_deployment_application(self.app, "/stat")
        mounted_client = Client(mounted_application, Response)

        root_response = mounted_client.get("/")
        self.assertEqual(root_response.status_code, 404)
        self.assertNotIn("Compteur passage", root_response.get_data(as_text=True))

        short_address = mounted_client.get("/stat")
        self.assertEqual(short_address.status_code, 308)
        self.assertEqual(short_address.headers["Location"], "/stat/")

        home_response = mounted_client.get("/stat/")
        self.assertEqual(home_response.status_code, 200)
        home_page = home_response.get_data(as_text=True)
        self.assertNotIn("Compteur passage", home_page)
        self.assertIn("Atelier Exemple", home_page)
        self.assertIn('href="/stat/identification"', home_page)
        self.assertIn('action="/stat/visiteurs"', home_page)
        self.assertIn('href="/stat/static/style.css"', home_page)
        self.assertIn('/stat/static/brand/OpenFabLab-logo-horizontal.svg', home_page)
        logo_response = mounted_client.get("/stat/static/brand/OpenFabLab-logo-horizontal.svg")
        self.assertEqual(logo_response.status_code, 200)
        logo_response.close()

        self.assertEqual(mounted_client.get("/stat/sante").status_code, 200)
        manifest_response = mounted_client.get("/stat/manifest.webmanifest")
        manifest = json.loads(manifest_response.get_data(as_text=True))
        self.assertEqual(manifest["start_url"], "/stat/")
        self.assertEqual(manifest["scope"], "/stat/")
        self.assertTrue(manifest["icons"][0]["src"].startswith("/stat/static/icons/OpenFabLab-icon-"))
        self.assertEqual(
            mounted_client.get("/stat/service-worker.js").headers[
                "Service-Worker-Allowed"
            ],
            "/stat/",
        )
        admin_redirect = mounted_client.get("/stat/admin")
        self.assertEqual(admin_redirect.status_code, 302)
        self.assertTrue(admin_redirect.headers["Location"].endswith("/stat/admin/connexion"))

    def test_admin_pin_rejects_wrong_code_and_can_lock_again(self):
        wrong_pin = self.login_admin("0000")
        self.assertIn("code PIN est incorrect", wrong_pin.get_data(as_text=True))
        self.assertEqual(self.client.get("/admin").status_code, 302)

        self.assertIn("Administration", self.login_admin().get_data(as_text=True))
        logout = self.client.post("/admin/deconnexion", follow_redirects=True)
        self.assertIn("administration a été verrouillée", logout.get_data(as_text=True))
        self.assertEqual(self.client.get("/admin").status_code, 302)

    def test_demo_users_have_short_codes_and_categories(self):
        with self.database() as database:
            users = database.execute(
                """
                SELECT public_id, first_name, category
                FROM users ORDER BY id
                """
            ).fetchall()

        self.assertEqual(
            [(user["public_id"], user["first_name"], user["category"]) for user in users],
            [
                ("1001", "Victor", "fabmanager"),
                ("1002", "Clara", "user"),
                ("1003", "Jean", "user"),
                ("1004", "Alice", "user"),
                ("1005", "Marie", "user"),
            ],
        )

    def test_identifier_records_arrival_then_departure(self):
        arrival = self.client.post(
            "/identification",
            data={"public_id": "1001"},
            follow_redirects=True,
        )
        self.assertIn("votre arrivée a bien été enregistrée", arrival.get_data(as_text=True))

        with self.database() as database:
            open_sessions = database.execute(
                "SELECT COUNT(*) FROM sessions WHERE check_out IS NULL"
            ).fetchone()[0]
        self.assertEqual(open_sessions, 1)

        departure = self.client.post(
            "/identification",
            data={"public_id": "1001"},
            follow_redirects=True,
        )
        self.assertIn("votre départ a bien été enregistré", departure.get_data(as_text=True))

        with self.database() as database:
            session = database.execute(
                """
                SELECT check_in, check_out, entry_method, exit_method
                FROM sessions
                """
            ).fetchone()
        self.assertIsNotNone(session["check_in"])
        self.assertIsNotNone(session["check_out"])
        self.assertEqual(session["entry_method"], "id")
        self.assertEqual(session["exit_method"], "id")

    def test_quick_departure_requires_an_open_presence(self):
        self.client.post("/identification", data={"public_id": "1001"})
        with self.database() as database:
            victor_id = database.execute(
                "SELECT id FROM users WHERE public_id = '1001'"
            ).fetchone()[0]

        home_page = self.client.get("/").get_data(as_text=True)
        self.assertIn("data-quick-departure", home_page)
        self.assertIn("vous partez", home_page)
        self.assertIn("Finalement, je reste", home_page)
        self.assertIn('class="departure-user-line"', home_page)
        self.assertIn('class="departure-question-line"', home_page)
        self.assertIn("data-departure-confirm", home_page)
        self.assertIn(">Je pars</button>", home_page)
        self.assertIn(f'/usagers/{victor_id}/depart-rapide', home_page)

        departure = self.client.post(
            f"/usagers/{victor_id}/depart-rapide", follow_redirects=True
        )
        self.assertIn("votre départ a bien été enregistré", departure.get_data(as_text=True))
        second_departure = self.client.post(
            f"/usagers/{victor_id}/depart-rapide", follow_redirects=True
        )
        self.assertIn("n&#39;est plus enregistrée", second_departure.get_data(as_text=True))

        with self.database() as database:
            session = database.execute(
                "SELECT check_out, exit_method FROM sessions WHERE user_id = ?",
                (victor_id,),
            ).fetchone()
        self.assertIsNotNone(session["check_out"])
        self.assertEqual(session["exit_method"], "departure")

    def test_manual_identifier_is_numeric_and_auto_submits_after_four_digits(self):
        page = self.client.get("/identification").get_data(as_text=True)
        self.assertIn('inputmode="numeric"', page)
        self.assertIn('pattern="[0-9]{4}"', page)
        self.assertIn('maxlength="4"', page)
        self.assertIn('placeholder="0101"', page)
        self.assertIn("data-identifier-form", page)
        javascript_response = self.client.get("/static/app.js")
        javascript = javascript_response.get_data(as_text=True)
        javascript_response.close()
        self.assertIn('replace(/\\D/g, "")', javascript)
        self.assertIn("requestSubmit(submitButton)", javascript)
        self.assertIn('form.dataset.submitting === "1"', javascript)

    def test_qr_identifier_records_arrival_then_departure_as_qr(self):
        arrival = self.client.post(
            "/identification",
            data={"public_id": "1002", "identification_method": "qr"},
            follow_redirects=True,
        )
        self.assertIn("votre arrivée a bien été enregistrée", arrival.get_data(as_text=True))

        departure = self.client.post(
            "/identification",
            data={"public_id": "1002", "identification_method": "qr"},
            follow_redirects=True,
        )
        self.assertIn("votre départ a bien été enregistré", departure.get_data(as_text=True))

        with self.database() as database:
            session = database.execute(
                """
                SELECT entry_method, exit_method
                FROM sessions
                WHERE user_id = (SELECT id FROM users WHERE public_id = '1002')
                """
            ).fetchone()
        self.assertEqual(session["entry_method"], "qr")
        self.assertEqual(session["exit_method"], "qr")

    def test_admin_displays_and_downloads_user_qr_codes(self):
        with self.database() as database:
            victor_id = database.execute(
                "SELECT id FROM users WHERE public_id = '1001'"
            ).fetchone()[0]

        protected_response = self.client.get(
            f"/admin/usagers/{victor_id}/qr.svg"
        )
        self.assertEqual(protected_response.status_code, 302)

        self.login_admin()
        admin_page = self.client.get("/admin/usagers").get_data(as_text=True)
        self.assertIn(f'/admin/usagers/{victor_id}/qr.svg', admin_page)
        self.assertIn(f'/admin/usagers/{victor_id}/qr.png?telecharger=1', admin_page)
        self.assertIn("QR Code :", admin_page)
        self.assertIn("data-qr-preview", admin_page)
        self.assertIn("Retour au répertoire", admin_page)

        svg = self.client.get(f"/admin/usagers/{victor_id}/qr.svg")
        self.assertEqual(svg.status_code, 200)
        self.assertEqual(svg.mimetype, "image/svg+xml")
        self.assertIn(b"<svg", svg.data)
        self.assertTrue(svg.headers["Content-Disposition"].startswith("inline;"))
        self.assertEqual(svg.headers["Cache-Control"], "private, no-store")

        png = self.client.get(
            f"/admin/usagers/{victor_id}/qr.png?telecharger=1"
        )
        self.assertEqual(png.status_code, 200)
        self.assertEqual(png.mimetype, "image/png")
        self.assertTrue(png.data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertTrue(png.headers["Content-Disposition"].startswith("attachment;"))
        self.assertIn("atelier-exemple-identifiant-1001.png", png.headers["Content-Disposition"])

        self.assertEqual(
            self.client.get(f"/admin/usagers/{victor_id}/qr.pdf").status_code,
            404,
        )

    def test_user_directory_can_be_searched_and_sorted(self):
        self.login_admin()
        page = self.client.get("/admin/usagers?tri=duration").get_data(as_text=True)
        self.assertIn("Répertoire des usagers", page)
        self.assertIn(">Usagers</a>", page)
        self.assertIn("5 comptes usagers", page)
        self.assertNotIn('<h2 id="users-title">Usagers</h2>', page)
        self.assertIn("Prénom, nom, identifiant ou catégorie", page)
        self.assertIn('value="duration" selected', page)
        self.assertIn("Durée cumulée", page)
        self.assertIn("Date de création", page)
        self.assertIn("data-user-card", page)

    def test_wake_lock_option_is_persistent_and_safe(self):
        self.login_admin()
        response = self.client.post(
            "/admin/reglages/borne/enregistrer",
            data={
                "keep_screen_awake": "1",
                "wake_lock_start": "09:00",
                "wake_lock_end": "17:00",
            },
            follow_redirects=True,
        )
        self.assertIn("Les options ont été enregistrées", response.get_data(as_text=True))
        self.assertIn('data-option-enabled="1"', response.get_data(as_text=True))
        self.assertIn('data-keep-screen-awake="1"', self.client.get("/").get_data(as_text=True))
        javascript_response = self.client.get("/static/app.js")
        javascript = javascript_response.get_data(as_text=True)
        javascript_response.close()
        self.assertIn('navigator.wakeLock.request("screen")', javascript)
        self.assertIn('document.visibilityState === "visible"', javascript)

    def test_automatic_backup_is_configurable_and_stays_in_allowed_root(self):
        self.login_admin()
        response = self.client.post(
            "/admin/reglages/donnees/enregistrer",
            data={
                "contact_years": "1",
                "deactivation_years": "3",
                "deletion_years": "5",
                "automatic_backup_enabled": "1",
                "automatic_backup_interval_days": "7",
                "automatic_backup_subdirectory": "CompteurPassage/Essais",
            },
            follow_redirects=True,
        )
        page = response.get_data(as_text=True)
        self.assertIn("Les options ont été enregistrées", page)
        self.assertIn("/server/backups/CompteurPassage/Essais", page)
        backup_directory = Path(self.temporary_directory.name) / "backups" / "CompteurPassage" / "Essais"
        backups = list(backup_directory.glob("openfablab-sauvegarde-*.db"))
        self.assertEqual(len(backups), 1)
        with sqlite3.connect(backups[0]) as backup_database:
            self.assertEqual(
                backup_database.execute("PRAGMA integrity_check").fetchone()[0],
                "ok",
            )

        rejected = self.client.post(
            "/admin/reglages/donnees/enregistrer",
            data={
                "contact_years": "1",
                "deactivation_years": "3",
                "deletion_years": "5",
                "automatic_backup_enabled": "1",
                "automatic_backup_interval_days": "1",
                "automatic_backup_subdirectory": "../ailleurs",
            },
            follow_redirects=True,
        )
        self.assertIn("chemin non autorisé", rejected.get_data(as_text=True))

    def test_retention_clears_deactivates_and_anonymizes(self):
        now = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)
        with self.database() as database:
            users = database.execute(
                "SELECT id, public_id FROM users ORDER BY public_id LIMIT 3"
            ).fetchall()
            ages = (2, 4, 6)
            for age, user in zip(ages, users):
                database.execute(
                    "UPDATE users SET email = ?, phone = ? WHERE id = ?",
                    (f"test{age}@example.org", "0102030405", user["id"]),
                )
                passage = now.replace(year=now.year - age).isoformat()
                database.execute(
                    """
                    INSERT INTO sessions (user_id, check_in, check_out, entry_method, exit_method)
                    VALUES (?, ?, ?, 'manual', 'manual')
                    """,
                    (user["id"], passage, passage),
                )
            database.commit()

        with self.app.app_context():
            from app import get_database, run_data_retention

            report = run_data_retention(get_database(), now=now, force=True)

        self.assertEqual(report, {"contacts_cleared": 2, "deactivated": 1, "deleted": 1})
        with self.database() as database:
            contact_user = database.execute(
                "SELECT active, email, phone FROM users WHERE public_id = ?",
                (users[0]["public_id"],),
            ).fetchone()
            deactivated_user = database.execute(
                "SELECT active FROM users WHERE public_id = ?", (users[1]["public_id"],)
            ).fetchone()
            deleted_user = database.execute(
                "SELECT id FROM users WHERE public_id = ?", (users[2]["public_id"],)
            ).fetchone()
            anonymous_session = database.execute(
                "SELECT user_id, statistical_user_key FROM sessions WHERE check_in = ?",
                (now.replace(year=now.year - 6).isoformat(),),
            ).fetchone()
        self.assertEqual((contact_user["active"], contact_user["email"], contact_user["phone"]), (1, None, None))
        self.assertEqual(deactivated_user["active"], 0)
        self.assertIsNone(deleted_user)
        self.assertIsNone(anonymous_session["user_id"])
        self.assertTrue(anonymous_session["statistical_user_key"])

    def test_admin_generates_badges_in_svg_and_png(self):
        with self.database() as database:
            victor_id = database.execute(
                "SELECT id FROM users WHERE public_id = '1001'"
            ).fetchone()[0]

        self.assertEqual(
            self.client.get(f"/admin/usagers/{victor_id}/badge.svg").status_code,
            302,
        )
        self.login_admin()
        svg = self.client.get(f"/admin/usagers/{victor_id}/badge.svg")
        self.assertEqual(svg.status_code, 200)
        self.assertEqual(svg.mimetype, "image/svg+xml")
        self.assertIn(b"ID 1001", svg.data)
        self.assertIn(b">Victor</text>", svg.data)
        self.assertNotIn(b"Victor Exemple", svg.data)
        self.assertIn(b"Fabmanager", svg.data)
        self.assertNotIn(b'id="card-background"', svg.data)
        self.assertIn(b"#ff0000", svg.data)
        self.assertNotIn(b">ID 1001</text>", svg.data.split(b'id="user-id"', 1)[0])

        from app import generate_badge_svg

        long_name_svg = generate_badge_svg(
            {
                "public_id": "1999",
                "first_name": "Marie-Christine",
                "last_name": "NomNonImprimé",
                "category": "volunteer",
            }
        )
        self.assertIn(b'textLength="45"', long_name_svg)
        self.assertNotIn(b"NomNonImprim", long_name_svg)

        png = self.client.get(f"/admin/usagers/{victor_id}/badge.png")
        self.assertEqual(png.status_code, 200)
        self.assertEqual(png.mimetype, "image/png")
        self.assertTrue(png.data.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIn("badge-atelier-exemple-1001-victor.png", png.headers["Content-Disposition"])

        from PIL import Image

        badge_image = Image.open(io.BytesIO(png.data)).convert("RGBA")
        self.assertEqual(badge_image.size, (1913, 3047))
        self.assertEqual(badge_image.getpixel((0, 0))[3], 0)
        opaque_colors = {
            pixel[:3]
            for pixel in badge_image.getdata()
            if pixel[3] > 32
        }
        self.assertTrue(any(red > 200 and green < 80 and blue < 80 for red, green, blue in opaque_colors))

    def test_reset_today_removes_only_today_data_and_open_presence(self):
        self.login_admin()
        old_check_in = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        with self.database() as database:
            victor_id = database.execute(
                "SELECT id FROM users WHERE public_id = '1001'"
            ).fetchone()[0]
            jean_id = database.execute(
                "SELECT id FROM users WHERE public_id = '1003'"
            ).fetchone()[0]
            database.execute(
                "INSERT INTO sessions (user_id, check_in, check_out, entry_method, exit_method) VALUES (?, ?, ?, 'manual', 'manual')",
                (victor_id, old_check_in, old_check_in),
            )
            database.execute(
                "INSERT INTO sessions (user_id, check_in, entry_method) VALUES (?, ?, 'manual')",
                (jean_id, datetime.now(timezone.utc).isoformat()),
            )
            database.execute(
                "INSERT INTO visitors (created_at) VALUES (?)",
                (datetime.now(timezone.utc).isoformat(),),
            )
            database.commit()

        rejected = self.client.post(
            "/admin/journee/reinitialiser",
            data={"confirmation": "EFFACER"},
            follow_redirects=True,
        )
        self.assertIn("EFFACER AUJOURD&#39;HUI", rejected.get_data(as_text=True))

        reset = self.client.post(
            "/admin/journee/reinitialiser",
            data={"confirmation": "EFFACER AUJOURD'HUI"},
            follow_redirects=True,
        )
        self.assertIn("remis à zéro", reset.get_data(as_text=True))
        with self.database() as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 1)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM visitors").fetchone()[0], 0)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM sessions WHERE check_out IS NULL").fetchone()[0], 0)
        self.assertTrue(list(Path(self.temporary_directory.name).glob("*-avant-reset-journee-*.db")))

    def test_full_reset_keeps_database_empty_after_reinitialization(self):
        self.login_admin()
        rejected = self.client.post(
            "/admin/sauvegarde/reinitialiser",
            data={"confirmation": "SUPPRIMER"},
            follow_redirects=True,
        )
        self.assertIn("TOUT SUPPRIMER", rejected.get_data(as_text=True))

        reset = self.client.post(
            "/admin/sauvegarde/reinitialiser",
            data={"confirmation": "TOUT SUPPRIMER"},
            follow_redirects=True,
        )
        self.assertIn("base a été remise à zéro", reset.get_data(as_text=True))
        with self.database() as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM visitors").fetchone()[0], 0)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM billing_records").fetchone()[0], 0)
        with self.app.app_context():
            from app import initialize_database

            initialize_database()
        with self.database() as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)
        self.assertTrue(list(Path(self.temporary_directory.name).glob("*-avant-remise-a-zero-*.db")))

    def test_automatic_and_manual_closure_of_open_sessions(self):
        self.login_admin()
        now_local = datetime.now().astimezone()
        weekday_names = [
            "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday",
        ]
        form = {name: "" for name in weekday_names}
        form["enabled"] = "1"
        form[weekday_names[now_local.weekday()]] = now_local.strftime("%H:%M")
        response = self.client.post("/admin/fermeture", data=form, follow_redirects=True)
        self.assertIn("horaires de clôture", response.get_data(as_text=True))

        with self.database() as database:
            user_id = database.execute(
                "SELECT id FROM users WHERE public_id = '1001'"
            ).fetchone()[0]
            database.execute(
                "INSERT INTO sessions (user_id, check_in, entry_method) VALUES (?, ?, 'manual')",
                (user_id, (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()),
            )
            database.commit()
        with self.app.app_context():
            from app import get_database, run_automatic_closure
            closed = run_automatic_closure(get_database())
        self.assertEqual(closed, 1)
        with self.database() as database:
            session_row = database.execute(
                "SELECT check_out, exit_method FROM sessions ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertIsNotNone(session_row["check_out"])
        self.assertEqual(session_row["exit_method"], "automatic")

        self.client.post("/identification", data={"public_id": "1002"})
        manual = self.client.post("/admin/fermeture/maintenant", follow_redirects=True)
        self.assertIn("1 session ouverte a été clôturée", manual.get_data(as_text=True))
        with self.database() as database:
            exit_method = database.execute(
                "SELECT exit_method FROM sessions ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        self.assertEqual(exit_method, "admin")

        paused = self.client.post("/admin/fermeture/basculer", follow_redirects=True)
        self.assertIn("mise en pause", paused.get_data(as_text=True))

    def test_automatic_closure_does_not_close_a_late_arrival(self):
        with self.database() as database:
            user_id = database.execute(
                "SELECT id FROM users WHERE public_id = '1001'"
            ).fetchone()[0]
            database.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                ("automatic_closure_enabled", "1"),
            )
            database.execute(
                "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
                ("automatic_closure_monday", "18:00"),
            )
            late_arrival = datetime(2026, 8, 10, 19, 0).astimezone(timezone.utc)
            database.execute(
                "INSERT INTO sessions (user_id, check_in, entry_method) VALUES (?, ?, 'manual')",
                (user_id, late_arrival.isoformat()),
            )
            database.commit()

        with self.app.app_context():
            from app import get_database, run_automatic_closure

            closed = run_automatic_closure(
                get_database(), datetime(2026, 8, 10, 20, 0).astimezone()
            )
        self.assertEqual(closed, 0)
        with self.database() as database:
            self.assertIsNone(
                database.execute(
                    "SELECT check_out FROM sessions ORDER BY id DESC LIMIT 1"
                ).fetchone()[0]
            )

    def test_complete_database_can_be_exported_and_restored(self):
        self.login_admin()
        exported = self.client.get("/admin/sauvegarde/exporter")
        self.assertEqual(exported.status_code, 200)
        self.assertTrue(exported.data.startswith(b"SQLite format 3"))

        with self.database() as database:
            database.execute("UPDATE users SET first_name = 'Modifié' WHERE public_id = '1001'")
            database.commit()

        restored = self.client.post(
            "/admin/reglages",
            data={
                "database_file": (io.BytesIO(exported.data), "sauvegarde.db"),
                "confirmation": "RESTAURER",
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn("sauvegarde a été restaurée", restored.get_data(as_text=True))
        with self.database() as database:
            first_name = database.execute(
                "SELECT first_name FROM users WHERE public_id = '1001'"
            ).fetchone()[0]
        self.assertEqual(first_name, "Victor")

        rejected = self.client.post(
            "/admin/reglages",
            data={
                "database_file": (io.BytesIO(b"not a database"), "mauvais.db"),
                "confirmation": "RESTAURER",
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertIn("base SQLite valide", rejected.get_data(as_text=True))

    def test_unknown_identifier_does_not_create_session(self):
        response = self.client.post(
            "/identification",
            data={"public_id": "9999"},
            follow_redirects=True,
        )
        self.assertIn("Cet identifiant est inconnu", response.get_data(as_text=True))

        with self.database() as database:
            session_count = database.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        self.assertEqual(session_count, 0)

    def test_manual_selection_still_records_presence(self):
        with self.database() as database:
            jean_id = database.execute(
                "SELECT id FROM users WHERE public_id = '1003'"
            ).fetchone()[0]

        self.assertEqual(
            self.client.post(f"/usagers/{jean_id}/presence").status_code,
            302,
        )
        self.assertEqual(
            self.client.post(f"/usagers/{jean_id}/presence").status_code,
            302,
        )

        with self.database() as database:
            session = database.execute(
                "SELECT entry_method, exit_method FROM sessions ORDER BY id DESC LIMIT 1"
            ).fetchone()
            open_sessions = database.execute(
                "SELECT COUNT(*) FROM sessions WHERE check_out IS NULL"
            ).fetchone()[0]
        self.assertEqual(open_sessions, 0)
        self.assertEqual(session["entry_method"], "list")
        self.assertEqual(session["exit_method"], "list")

    def test_anonymous_visitor_is_counted(self):
        response = self.client.post("/visiteurs", follow_redirects=True)
        self.assertIn("Votre visite a été comptabilisée", response.get_data(as_text=True))

        with self.database() as database:
            visitor_count = database.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]
        self.assertEqual(visitor_count, 1)

    def test_capacity_gauge_is_informative_and_does_not_block_presence(self):
        now = datetime.now(timezone.utc).isoformat()
        with self.database() as database:
            for position in range(10):
                cursor = database.execute(
                    """
                    INSERT INTO users (
                        public_id, first_name, last_name, active, category, created_at
                    ) VALUES (?, ?, 'Jauge', 1, 'user', ?)
                    """,
                    (str(2000 + position), f"Test{position}", now),
                )
                database.execute(
                    """
                    INSERT INTO sessions (user_id, check_in, entry_method)
                    VALUES (?, ?, 'manual')
                    """,
                    (cursor.lastrowid, now),
                )

        full_page = self.client.get("/").get_data(as_text=True)
        self.assertIn("Complet · 10/10", full_page)
        self.assertIn('aria-valuenow="10"', full_page)
        self.assertIn("level-full", full_page)
        self.assertIn('class="compact-occupancy present-occupancy"', full_page)
        self.assertNotIn('class="compact-occupancy header-occupancy"', full_page)
        self.assertIn('class="present-occupancy-value"', full_page)
        self.assertNotIn("Je n'ai pas mon badge ou mon identifiant", full_page)

        # La jauge est informative : Victor peut toujours pointer et devient
        # la onzième personne présente.
        self.client.post("/identification", data={"public_id": "1001"})
        with self.database() as database:
            present_count = database.execute(
                "SELECT COUNT(*) FROM sessions WHERE check_out IS NULL"
            ).fetchone()[0]
        self.assertEqual(present_count, 11)

        over_capacity_page = self.client.get("/").get_data(as_text=True)
        self.assertIn("Complet · 11/10", over_capacity_page)
        self.assertIn('aria-valuenow="10"', over_capacity_page)

    def test_admin_can_create_and_edit_user(self):
        self.login_admin()
        form_page = self.client.get("/admin/usagers/nouveau").get_data(as_text=True)
        self.assertIn('data-communes-url="/admin/api/communes"', form_page)
        self.assertIn('list="city-suggestions"', form_page)
        self.assertIn('list="country-suggestions"', form_page)
        self.assertIn('<option value="Belgique"></option>', form_page)
        self.assertIn('name="phone_country_code"', form_page)
        self.assertIn('value="+33"', form_page)

        creation = self.client.post(
            "/admin/usagers/nouveau",
            data={
                "public_id": "1006",
                "first_name": "Camille",
                "last_name": "robert",
                "birth_year": "1992",
                "gender": "non_binary",
                "city": "Ville Fictive",
                "postal_code": "00000",
                "nationality": "Française",
                "email": "camille@example.fr",
                "phone_country_code": "0033",
                "phone": "0612345678",
                "category": "intern",
                "active": "1",
            },
            follow_redirects=True,
        )
        self.assertIn("a été créé", creation.get_data(as_text=True))

        with self.database() as database:
            created_user = database.execute(
                """
                SELECT id, first_name, last_name, birth_year, gender, city, city_normalized,
                       postal_code, nationality, nationality_normalized,
                       email, phone_country_code, phone, category
                FROM users WHERE public_id = '1006'
                """
            ).fetchone()

        self.assertEqual(created_user["birth_year"], 1992)
        self.assertEqual(created_user["last_name"], "ROBERT")
        self.assertEqual(created_user["gender"], "non_binary")
        self.assertEqual(created_user["city"], "Ville Fictive")
        self.assertEqual(created_user["city_normalized"], "ville fictive")
        self.assertEqual(created_user["nationality"], "France")
        self.assertEqual(created_user["nationality_normalized"], "france")
        self.assertEqual(created_user["email"], "camille@example.fr")
        self.assertEqual(created_user["phone_country_code"], "+33")
        self.assertEqual(created_user["phone"], "06 12 34 56 78")
        self.assertEqual(created_user["category"], "intern")

        edition = self.client.post(
            f"/admin/usagers/{created_user['id']}/modifier",
            data={
                "public_id": "1010",
                "first_name": "Camille",
                "last_name": "dupré",
                "birth_year": "1993",
                "gender": "",
                "city": "Commune Fictive",
                "postal_code": "35133",
                "nationality": "Belge",
                "email": "",
                "phone_country_code": "+32",
                "phone": "0470123456",
                "category": "voluntary",
                "active": "1",
            },
            follow_redirects=True,
        )
        self.assertIn("a été mise à jour", edition.get_data(as_text=True))

        with self.database() as database:
            edited_user = database.execute(
                """
                SELECT public_id, first_name, last_name, birth_year, gender,
                       city, category, nationality, nationality_normalized,
                       phone_country_code, phone
                FROM users WHERE id = ?
                """,
                (created_user["id"],),
            ).fetchone()
        self.assertEqual(
            tuple(edited_user),
            (
                "1010", "Camille", "DUPRÉ", 1993, None, "Commune Fictive",
                "voluntary", "Belgique", "belgique", "+32",
                "04 70 12 34 56",
            ),
        )
        edited_form = self.client.get(
            f"/admin/usagers/{created_user['id']}/modifier"
        ).get_data(as_text=True)
        self.assertIn('name="last_name"', edited_form)
        self.assertIn('value="DUPRÉ"', edited_form)

    def test_admin_commune_suggestions_use_postal_code_and_allow_fallback(self):
        self.assertEqual(
            self.client.get("/admin/api/communes?code_postal=00000").status_code,
            302,
        )
        self.login_admin()
        with mock.patch(
            "app.load_communes_by_postal_code",
            return_value=(["Ville Fictive", "Commune Fictive"], True),
        ):
            response = self.client.get("/admin/api/communes?code_postal=00000")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"available": True, "communes": ["Ville Fictive", "Commune Fictive"]},
        )

        with mock.patch(
            "app.load_communes_by_postal_code", return_value=([], False)
        ):
            unavailable = self.client.get(
                "/admin/api/communes?code_postal=00000"
            ).get_json()
        self.assertEqual(unavailable, {"available": False, "communes": []})

        javascript_response = self.client.get("/static/app.js")
        javascript = javascript_response.get_data(as_text=True)
        javascript_response.close()
        self.assertIn("configureCommuneSuggestions", javascript)
        self.assertIn("encodeURIComponent", javascript)

    def test_admin_can_delete_user_without_history(self):
        self.login_admin()
        self.client.post(
            "/admin/usagers/nouveau",
            data={
                "public_id": "1006",
                "first_name": "Sans",
                "last_name": "Historique",
                "category": "user",
                "active": "1",
                "birth_year": "1990", "city": "Ville Fictive", "nationality": "France",
                "email": "sans.historique@example.invalid", "phone": "0611223344",
            },
        )
        with self.database() as database:
            user_id = database.execute(
                "SELECT id FROM users WHERE public_id = '1006'"
            ).fetchone()[0]

        deletion = self.client.post(
            f"/admin/usagers/{user_id}/supprimer", follow_redirects=True
        )
        self.assertIn("a été supprimé", deletion.get_data(as_text=True))

        with self.database() as database:
            remaining = database.execute(
                "SELECT COUNT(*) FROM users WHERE id = ?", (user_id,)
            ).fetchone()[0]
        self.assertEqual(remaining, 0)

    def test_admin_cannot_delete_user_with_history(self):
        self.login_admin()
        self.client.post("/identification", data={"public_id": "1001"})
        with self.database() as database:
            victor_id = database.execute(
                "SELECT id FROM users WHERE public_id = '1001'"
            ).fetchone()[0]

        deletion = self.client.post(
            f"/admin/usagers/{victor_id}/supprimer", follow_redirects=True
        )
        self.assertIn("possède un historique", deletion.get_data(as_text=True))

        with self.database() as database:
            remaining = database.execute(
                "SELECT COUNT(*) FROM users WHERE id = ?", (victor_id,)
            ).fetchone()[0]
        self.assertEqual(remaining, 1)

    def test_admin_rejects_duplicate_identifier(self):
        self.login_admin()
        response = self.client.post(
            "/admin/usagers/nouveau",
            data={
                "public_id": "1001",
                "first_name": "Code",
                "last_name": "Dupliqué",
                "category": "user",
                "active": "1",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("déjà utilisé", response.get_data(as_text=True))

    def test_manual_list_pins_present_users_and_sorts_by_last_visit(self):
        now = datetime.now(ZoneInfo("Europe/Paris"))
        with self.database() as database:
            ids = {
                row["first_name"]: row["id"]
                for row in database.execute(
                    "SELECT id, first_name FROM users"
                ).fetchall()
            }
            database.executemany(
                """
                INSERT INTO sessions (user_id, check_in, check_out, entry_method, exit_method)
                VALUES (?, ?, ?, 'manual', 'manual')
                """,
                [
                    (
                        ids["Jean"],
                        (now - timedelta(days=8)).isoformat(),
                        (now - timedelta(days=8) + timedelta(hours=1)).isoformat(),
                    ),
                    (
                        ids["Alice"],
                        (now - timedelta(days=2)).isoformat(),
                        (now - timedelta(days=2) + timedelta(hours=1)).isoformat(),
                    ),
                ],
            )
            database.execute(
                """
                INSERT INTO sessions (user_id, check_in, entry_method)
                VALUES (?, ?, 'manual')
                """,
                (ids["Victor"], now.isoformat()),
            )

        page = self.client.get("/usagers").get_data(as_text=True)
        self.assertIn("Actuellement présent", page)
        self.assertNotIn("Épinglé", page)
        self.assertIn("Il y a 8 jours", page)
        self.assertLess(page.index("Victor EXEMPLE"), page.index("Alice MARTIN"))
        self.assertLess(page.index("Alice MARTIN"), page.index("Jean DUPONT"))

    def test_statistics_group_demographics_and_keep_year_history(self):
        current_year = datetime.now(timezone.utc).year
        previous_year = current_year - 1
        with self.database() as database:
            users = {
                row["first_name"]: row["id"]
                for row in database.execute(
                    "SELECT id, first_name FROM users"
                ).fetchall()
            }
            database.execute(
                """
                UPDATE users
                SET birth_year = 1985, gender = 'male', city = 'Ville Fictive',
                    city_normalized = 'ville fictive', nationality = 'Français',
                    nationality_normalized = 'france'
                WHERE id = ?
                """,
                (users["Victor"],),
            )
            database.execute(
                """
                UPDATE users
                SET birth_year = 1990, gender = 'female', city = 'VILLE FICTIVE',
                    city_normalized = 'ville fictive', nationality = 'Française',
                    nationality_normalized = 'france'
                WHERE id = ?
                """,
                (users["Clara"],),
            )
            current_start = datetime(current_year, 3, 10, 9, tzinfo=timezone.utc)
            previous_start = datetime(previous_year, 4, 5, 13, tzinfo=timezone.utc)
            database.executemany(
                """
                INSERT INTO sessions (
                    user_id, check_in, check_out, entry_method, exit_method
                ) VALUES (?, ?, ?, 'manual', 'manual')
                """,
                [
                    (
                        users["Victor"],
                        current_start.isoformat(),
                        (current_start + timedelta(hours=2)).isoformat(),
                    ),
                    (
                        users["Clara"],
                        (current_start + timedelta(days=1)).isoformat(),
                        (current_start + timedelta(days=1, hours=1)).isoformat(),
                    ),
                    (
                        users["Victor"],
                        previous_start.isoformat(),
                        (previous_start + timedelta(hours=3)).isoformat(),
                    ),
                ],
            )
            database.executemany(
                "INSERT INTO visitors (created_at) VALUES (?)",
                [
                    ((current_start + timedelta(days=2)).isoformat(),),
                    ((previous_start + timedelta(days=2)).isoformat(),),
                ],
            )

        self.login_admin()
        response = self.client.get(f"/admin/frequentation/statistiques?year={current_year}")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Statistiques", page)
        self.assertIn("Genre renseigné", page)
        self.assertIn("Ville Fictive", page)
        self.assertIn("France", page)
        self.assertIn(str(previous_year), page)
        self.assertIn("3,0 h", page)
        self.assertIn("Filtres croisés", page)
        self.assertIn("data-statistics-filters", page)
        self.assertIn('data-dimension="gender"', page)
        self.assertIn('data-dimension="age_group"', page)
        self.assertIn('data-dimension="city"', page)
        self.assertIn('data-dimension="nationality"', page)
        self.assertIn("data-stat-bar", page)
        self.assertIn('"gender": "male"', page)
        self.assertIn("OpenLabs les plus fréquentés", page)
        self.assertIn("Temps moyen par session", page)
        self.assertIn("OpenLabs effectués", page)
        self.assertIn(">120 min<", page)
        self.assertLess(page.index('id="nationality-title"'), page.index("data-statistics-filters"))

        total_response = self.client.get("/admin/frequentation/statistiques?year=total")
        total_page = total_response.get_data(as_text=True)
        self.assertEqual(total_response.status_code, 200)
        self.assertIn('<option value="total" selected>Total</option>', total_page)
        self.assertIn("Résumé cumulé", total_page)
        self.assertIn("Toutes les années", total_page)
        self.assertIn(
            "<article><strong>5</strong><span>Passages totaux</span></article>",
            total_page,
        )
        self.assertIn(
            "<article><strong>2</strong><span>Usagers uniques</span></article>",
            total_page,
        )

        total_export = self.client.get(
            "/admin/exports/statistiques.csv?year=total"
        ).get_data(as_text=True)
        self.assertIn("Total;Passages totaux;5", total_export)
        self.assertIn("Total;Usagers uniques;2", total_export)

        application_script = (Path(__file__).parents[1] / "static" / "app.js").read_text()
        self.assertIn("configureDemographicStatisticsFilters", application_script)
        self.assertIn("ignoredDimension", application_script)

        stylesheet = (Path(__file__).parents[1] / "static" / "style.css").read_text()
        self.assertIn(".distribution-track {\n    width: 100%;\n    height: 9px;", stylesheet)
        self.assertIn("grid-row: 2;\n    display: block;", stylesheet)
        self.assertIn("grid-column: 1 / -1;", stylesheet)
        self.assertIn(".distribution-label {\n    min-width: 0;\n    grid-column: 2;\n    grid-row: 1;", stylesheet)

    def test_statistics_follow_current_user_profile_after_edit(self):
        current_year = datetime.now(timezone.utc).year
        with self.database() as database:
            victor = database.execute(
                "SELECT id FROM users WHERE public_id = '1001'"
            ).fetchone()
            database.execute(
                """
                UPDATE users
                SET birth_year = ?, gender = 'male', city = 'Ville Fictive',
                    city_normalized = 'ville fictive', nationality = 'France',
                    nationality_normalized = 'france'
                WHERE id = ?
                """,
                (current_year - 45, victor["id"]),
            )
            check_in = datetime(current_year, 3, 10, 9, tzinfo=timezone.utc)
            database.execute(
                """
                INSERT INTO sessions (
                    user_id, check_in, check_out, entry_method, exit_method
                ) VALUES (?, ?, ?, 'manual', 'manual')
                """,
                (
                    victor["id"],
                    check_in.isoformat(),
                    (check_in + timedelta(hours=1)).isoformat(),
                ),
            )
            # Le déclencheur conserve bien l'ancien instantané pour le jour où
            # le compte devra être anonymisé.
            snapshot = database.execute(
                """
                SELECT statistical_birth_year, statistical_gender,
                       statistical_city_normalized,
                       statistical_nationality_normalized
                FROM sessions WHERE user_id = ?
                """,
                (victor["id"],),
            ).fetchone()
            self.assertEqual(
                tuple(snapshot),
                (current_year - 45, "male", "ville fictive", "france"),
            )
            database.execute(
                """
                UPDATE users
                SET birth_year = ?, gender = 'non_binary', city = 'Commune Fictive',
                    city_normalized = 'lecousse', nationality = 'Belgique',
                    nationality_normalized = 'belgique'
                WHERE id = ?
                """,
                (current_year - 20, victor["id"]),
            )
            database.commit()

        self.login_admin()
        page = self.client.get(
            f"/admin/frequentation/statistiques?year={current_year}"
        ).get_data(as_text=True)
        data_match = re.search(
            r'<script id="demographic-statistics-data" type="application/json">(.*?)</script>',
            page,
            re.DOTALL,
        )
        self.assertIsNotNone(data_match)
        demographic_users = json.loads(data_match.group(1))
        self.assertEqual(
            demographic_users,
            [
                {
                    "age": 20,
                    "age_group": "18_25",
                    "city": "lecousse",
                    "city_label": "Commune Fictive",
                    "gender": "non_binary",
                    "nationality": "belgique",
                    "nationality_label": "Belgique",
                }
            ],
        )

        # Modifier une fiche existante ne réécrit pas l'instantané historique :
        # il reste disponible si le compte est ensuite supprimé par conservation.
        with self.database() as database:
            snapshot = database.execute(
                """
                SELECT statistical_birth_year, statistical_gender,
                       statistical_city_normalized,
                       statistical_nationality_normalized
                FROM sessions WHERE user_id = ?
                """,
                (victor["id"],),
            ).fetchone()
        self.assertEqual(
            tuple(snapshot),
            (current_year - 45, "male", "ville fictive", "france"),
        )

    def test_statistics_limit_origins_and_rank_openlab_weekdays(self):
        current_year = datetime.now(timezone.utc).year
        first_day = datetime(current_year, 1, 1, 13, tzinfo=timezone.utc)
        first_tuesday = first_day + timedelta(
            days=(1 - first_day.weekday()) % 7
        )
        first_wednesday = first_tuesday.replace(hour=8) + timedelta(days=1)
        second_tuesday = first_tuesday + timedelta(days=7)
        visitor_only_thursday = first_wednesday + timedelta(days=1)

        with self.database() as database:
            user_ids = []
            for position in range(12):
                cursor = database.execute(
                    """
                    INSERT INTO users (
                        public_id, first_name, last_name, active, category,
                        city, city_normalized, nationality,
                        nationality_normalized, created_at
                    ) VALUES (?, ?, 'STATISTIQUE', 1, 'user', ?, ?, ?, ?, ?)
                    """,
                    (
                        str(3000 + position),
                        f"Profil{position}",
                        f"Commune {position:02d}",
                        f"commune_{position:02d}",
                        f"Pays {position:02d}",
                        f"pays_{position:02d}",
                        first_tuesday.isoformat(),
                    ),
                )
                user_ids.append(cursor.lastrowid)
                database.execute(
                    """
                    INSERT INTO sessions (
                        user_id, check_in, check_out, entry_method, exit_method
                    ) VALUES (?, ?, ?, 'manual', 'manual')
                    """,
                    (
                        cursor.lastrowid,
                        first_tuesday.isoformat(),
                        (first_tuesday + timedelta(hours=1)).isoformat(),
                    ),
                )

            database.executemany(
                """
                INSERT INTO sessions (
                    user_id, check_in, check_out, entry_method, exit_method
                ) VALUES (?, ?, ?, 'manual', 'manual')
                """,
                [
                    (
                        user_ids[0],
                        second_tuesday.isoformat(),
                        (second_tuesday + timedelta(minutes=30)).isoformat(),
                    ),
                    (
                        user_ids[1],
                        first_wednesday.isoformat(),
                        (first_wednesday + timedelta(minutes=90)).isoformat(),
                    ),
                ],
            )
            database.executemany(
                "INSERT INTO visitors (created_at) VALUES (?)",
                [
                    ((first_tuesday + timedelta(minutes=10)).isoformat(),),
                    ((second_tuesday + timedelta(minutes=10)).isoformat(),),
                    ((second_tuesday + timedelta(minutes=20)).isoformat(),),
                    ((second_tuesday + timedelta(minutes=30)).isoformat(),),
                    ((first_wednesday + timedelta(minutes=10)).isoformat(),),
                    ((first_wednesday + timedelta(minutes=20)).isoformat(),),
                    (visitor_only_thursday.isoformat(),),
                ],
            )

        self.login_admin()
        page = self.client.get(
            f"/admin/frequentation/statistiques?year={current_year}"
        ).get_data(as_text=True)
        self.assertEqual(page.count('data-dimension="city"'), 11)
        self.assertEqual(page.count('data-dimension="nationality"'), 11)
        self.assertGreaterEqual(page.count('data-key="__other__"'), 2)
        self.assertIn(
            'data-openlab-weekday="1" data-average-users="6.5" '
            'data-average-visitors="2.0"',
            page,
        )
        self.assertNotIn('data-openlab-weekday="3"', page)
        self.assertIn("OpenLabs effectués", page)
        self.assertIn(">Affluence</h2>", page)
        self.assertIn("Comparer les jours ensemble", page)
        self.assertIn("Arrivées par quart d’heure", page)
        self.assertIn("personnes au pic", page)
        self.assertIn("entre 14h00 et 14h15", page)
        self.assertIn('data-traffic-weekday="1"', page)
        self.assertIn(
            'data-traffic-start="14:00" data-traffic-average="6.5"', page
        )
        self.assertIn('data-traffic-average-visitors="1.0"', page)
        self.assertIn('data-traffic-average-people="7.5"', page)
        self.assertIn('data-traffic-weekday="1" data-traffic-slots="12"', page)
        self.assertIn('data-traffic-weekday="2" data-traffic-slots="12"', page)
        self.assertIn('data-traffic-weekday="5" data-traffic-slots="14"', page)
        wednesday_card = page.split('data-traffic-weekday="2"', 1)[1].split(
            "</article>", 1
        )[0]
        day_color = re.search(r"--traffic-day-color: (#[0-9a-f]{6})", wednesday_card).group(1)
        week_color = re.search(r"--traffic-week-color: (#[0-9a-f]{6})", wednesday_card).group(1)
        self.assertEqual(day_color, week_color)
        self.assertIn("1 usa.", wednesday_card)
        self.assertIn("data-attendance-scale-toggle", page)
        self.assertIn("data-attendance-visitors-toggle checked", page)
        self.assertIn("Inclure les visiteurs", page)
        self.assertIn("1 vis.", page)
        self.assertIn("Échelle propre à chaque jour", page)
        self.assertIn("Journée record d’affluence", page)
        self.assertIn('data-record-includes-visitors="0"', page)
        self.assertIn('data-record-includes-visitors="1"', page)
        expected_record_date = first_tuesday.astimezone(ZoneInfo("Europe/Paris")).date()
        self.assertIn(f'data-record-date="{expected_record_date.isoformat()}"', page)
        self.assertIn(
            'traffic-visitor-average"><strong>2</strong> visiteurs en moyenne',
            page,
        )
        self.assertNotIn("Chaque barre représente le nombre moyen", page)

        with self.database() as database:
            database.execute(
                """
                INSERT INTO app_settings (key, value)
                VALUES ('openlab_attendance_show_decimals', '1')
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """
            )
        decimal_page = self.client.get(
            f"/admin/frequentation/statistiques?year={current_year}"
        ).get_data(as_text=True)
        decimal_wednesday_card = decimal_page.split(
            'data-traffic-weekday="2"', 1
        )[1].split("</article>", 1)[0]
        self.assertIn("1,0 usa.", decimal_wednesday_card)
        self.assertIn("1,0 vis.", decimal_page)

        statistics_export = self.client.get(
            f"/admin/exports/statistiques.csv?year={current_year}"
        ).get_data(as_text=True)
        self.assertIn("Commune 11", statistics_export)
        self.assertIn("Pays 11", statistics_export)
        self.assertIn("Temps moyen par catégorie", statistics_export)
        self.assertIn("Jours d'OpenLab les plus fréquentés", statistics_export)
        self.assertIn("Affluence par quart d'heure · Mardi", statistics_export)
        self.assertIn("OpenLabs effectués;3", statistics_export)

    def test_attendance_record_changes_when_visitors_are_included(self):
        current_year = datetime.now(timezone.utc).year
        paris = ZoneInfo("Europe/Paris")
        first_day = datetime(current_year, 1, 1, tzinfo=paris)
        first_tuesday = first_day + timedelta(
            days=(1 - first_day.weekday()) % 7
        )
        first_tuesday = first_tuesday.replace(hour=14)
        second_tuesday = first_tuesday + timedelta(days=7)

        with self.database() as database:
            user_ids = [
                row["id"]
                for row in database.execute(
                    "SELECT id FROM users ORDER BY id LIMIT 2"
                ).fetchall()
            ]
            database.executemany(
                """
                INSERT INTO sessions (
                    user_id, check_in, check_out, entry_method, exit_method
                ) VALUES (?, ?, ?, 'manual', 'manual')
                """,
                [
                    (
                        user_ids[0],
                        first_tuesday.isoformat(),
                        (first_tuesday + timedelta(hours=1)).isoformat(),
                    ),
                    (
                        user_ids[1],
                        first_tuesday.isoformat(),
                        (first_tuesday + timedelta(hours=1)).isoformat(),
                    ),
                    (
                        user_ids[0],
                        second_tuesday.isoformat(),
                        (second_tuesday + timedelta(hours=1)).isoformat(),
                    ),
                ],
            )
            database.executemany(
                "INSERT INTO visitors (created_at) VALUES (?)",
                [
                    ((second_tuesday + timedelta(minutes=3)).isoformat(),),
                    ((second_tuesday + timedelta(minutes=6)).isoformat(),),
                    ((second_tuesday + timedelta(minutes=9)).isoformat(),),
                ],
            )
            database.commit()

        self.login_admin()
        page = self.client.get(
            f"/admin/frequentation/statistiques?year={current_year}"
        ).get_data(as_text=True)
        user_record = page.split(
            'class="openlab-traffic-card traffic-record-card traffic-record-users"',
            1,
        )[1].split("</article>", 1)[0]
        combined_record = page.split(
            'class="openlab-traffic-card traffic-record-card traffic-record-combined"',
            1,
        )[1].split("</article>", 1)[0]
        self.assertIn(
            f'data-record-date="{first_tuesday.date().isoformat()}"', user_record
        )
        self.assertIn(
            f'data-record-date="{second_tuesday.date().isoformat()}"',
            combined_record,
        )
        self.assertIn(">4</strong> personnes au pic", combined_record)

    def test_admin_exports_are_excel_compatible_and_protected(self):
        current_year = datetime.now(timezone.utc).year
        self.assertEqual(self.client.get("/admin/exports/usagers.csv").status_code, 302)

        with self.database() as database:
            database.execute(
                """
                UPDATE users SET category = 'volunteer', city = 'Ville Fictive'
                WHERE public_id = '1002'
                """
            )

        self.login_admin()
        export_urls = (
            "/admin/exports/usagers.csv",
            "/admin/exports/benevoles.csv",
            f"/admin/exports/presences.csv?year={current_year}",
            f"/admin/exports/statistiques.csv?year={current_year}",
            "/admin/exports/presences.csv?year=total",
            "/admin/exports/statistiques.csv?year=total",
            "/admin/exports/animations.csv?year=total",
            "/admin/exports/reservations-locations.csv?year=total",
        )
        for url in export_urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertIn("text/csv", response.content_type)
                self.assertTrue(response.data.startswith(b"\xef\xbb\xbf"))
                self.assertIn(b";", response.data)

        users_export = self.client.get("/admin/exports/usagers.csv")
        self.assertIn("Ville Fictive", users_export.get_data(as_text=True))
        volunteers_export = self.client.get("/admin/exports/benevoles.csv")
        self.assertIn("Clara", volunteers_export.get_data(as_text=True))

    def test_presence_methods_are_humanized_consistently(self):
        from app import presence_method_label

        expected_labels = {
            "manual": "ID",
            "id": "ID",
            "qr": "QR",
            "automatic": "Auto",
            "admin": "Admin",
            "list": "Liste",
            "departure": "Départ",
            "anonymous": "Anonyme",
            None: "—",
        }
        for method, label in expected_labels.items():
            with self.subTest(method=method):
                self.assertEqual(presence_method_label(method), label)
        self.assertEqual(presence_method_label("legacy-import"), "Legacy import")

        self.client.post("/identification", data={"public_id": "1001"})
        self.client.post("/identification", data={"public_id": "1001"})
        self.client.post("/visiteurs")
        self.login_admin()
        overview = self.client.get("/admin").get_data(as_text=True)
        self.assertIn('data-label="Méthode">ID / ID</td>', overview)
        self.assertIn("<strong>Visiteur</strong>", overview)
        self.assertIn('data-label="Méthode">Anonyme</td>', overview)
        self.assertNotIn(">None<", overview)

        selected_day = datetime.now(ZoneInfo("Europe/Paris")).strftime("%Y-%m-%d")
        day_page = self.client.get(
            f"/admin/frequentation/journee?date={selected_day}"
        ).get_data(as_text=True)
        self.assertIn('data-label="Méthode">ID / ID</td>', day_page)
        self.assertIn('data-label="Méthode">Anonyme</td>', day_page)
        self.assertNotIn(">None<", day_page)

        current_year = datetime.now(ZoneInfo("Europe/Paris")).year
        presence_export = self.client.get(
            f"/admin/exports/presences.csv?year={current_year}"
        ).get_data(as_text=True)
        self.assertIn(";ID;ID", presence_export)
        self.assertNotIn(";id;id", presence_export)

    def test_home_state_refresh_is_anonymous_and_changes_after_a_passage(self):
        home_response = self.client.get("/")
        home_page = home_response.get_data(as_text=True)
        self.assertIn('class="home-document home-scroll-locked"', home_page)
        self.assertIn('data-home-live-state', home_page)

        first_state = self.client.get("/etat-accueil")
        self.assertEqual(first_state.status_code, 200)
        self.assertEqual(set(first_state.get_json()), {"signature"})
        first_signature = first_state.get_json()["signature"]

        self.client.post("/visiteurs")
        second_state = self.client.get("/etat-accueil")
        self.assertNotEqual(first_signature, second_state.get_json()["signature"])
        self.assertEqual(second_state.headers["Cache-Control"], "no-store")

        javascript_response = self.client.get("/static/app.js")
        javascript = javascript_response.get_data(as_text=True)
        javascript_response.close()
        self.assertIn("10000", javascript)
        self.assertIn("10 * 60 * 1000", javascript)
        self.assertIn("stateUrl", javascript)
        stylesheet_response = self.client.get("/static/style.css")
        stylesheet = stylesheet_response.get_data(as_text=True)
        stylesheet_response.close()
        self.assertIn("html.home-document", stylesheet)
        self.assertIn("overflow: hidden", stylesheet)

    def test_home_scroll_lock_is_enabled_by_default_and_configurable(self):
        home_page = self.client.get("/").get_data(as_text=True)
        self.assertIn('data-lock-home-scroll="1"', home_page)
        self.assertIn("home-scroll-locked", home_page)

        self.login_admin()
        options_page = self.client.get("/admin/reglages/borne").get_data(as_text=True)
        self.assertIn('name="lock_home_scroll"', options_page)
        self.assertIn('name="lock_home_scroll" type="checkbox" value="1" checked', options_page)

        response = self.client.post(
            "/admin/reglages/borne/enregistrer",
            data={
                "wake_lock_start": "09:00",
                "wake_lock_end": "17:00",
            },
            follow_redirects=True,
        )
        self.assertIn("Les options ont été enregistrées", response.get_data(as_text=True))
        unlocked_home = self.client.get("/").get_data(as_text=True)
        self.assertIn('data-lock-home-scroll="0"', unlocked_home)
        self.assertNotIn("home-scroll-locked", unlocked_home)

        response = self.client.post(
            "/admin/reglages/borne/enregistrer",
            data={
                "lock_home_scroll": "1",
                "wake_lock_start": "09:00",
                "wake_lock_end": "17:00",
            },
            follow_redirects=True,
        )
        self.assertIn("Les options ont été enregistrées", response.get_data(as_text=True))
        self.assertIn(
            'name="lock_home_scroll" type="checkbox" value="1" checked',
            response.get_data(as_text=True),
        )
        locked_home = self.client.get("/").get_data(as_text=True)
        self.assertIn('data-lock-home-scroll="1"', locked_home)
        self.assertIn("home-scroll-locked", locked_home)

        javascript_response = self.client.get("/static/app.js")
        javascript = javascript_response.get_data(as_text=True)
        javascript_response.close()
        self.assertIn("configureHomeScrollLock", javascript)
        self.assertIn("visualViewport", javascript)
        self.assertIn("touchmove", javascript)

    def test_home_theme_is_classic_by_default_and_configurable(self):
        home_page = self.client.get("/").get_data(as_text=True)
        self.assertIn("home-theme-classic", home_page)
        self.assertIn("home-theme-scene", home_page)

        self.login_admin()
        options_page = self.client.get("/admin/reglages/affichage").get_data(as_text=True)
        self.assertIn("Thème de la page d’accueil", options_page)
        self.assertIn(
            'name="home_theme" type="radio" value="classic" checked',
            options_page,
        )
        self.assertIn('value="dark"', options_page)
        self.assertIn('value="halloween"', options_page)
        self.assertIn('value="christmas"', options_page)
        self.assertIn('value="easter"', options_page)
        self.assertIn('value="valentine"', options_page)
        self.assertIn('value="summer"', options_page)
        self.assertIn('value="steampunk"', options_page)

        first_signature = self.client.get("/etat-accueil").get_json()["signature"]
        response = self.client.post(
            "/admin/reglages/affichage/enregistrer",
            data={
                "home_theme": "christmas",
            },
            follow_redirects=True,
        )
        page = response.get_data(as_text=True)
        self.assertIn("Les options ont été enregistrées", page)
        self.assertIn(
            'name="home_theme" type="radio" value="christmas" checked',
            page,
        )
        themed_home = self.client.get("/").get_data(as_text=True)
        self.assertIn("home-theme-christmas", themed_home)
        self.assertIn("departure-theme-fill", themed_home)
        self.assertIn("departure-snowfall", themed_home)
        self.assertIn("departure-theme-actor", themed_home)
        self.assertIn("theme-crosser", themed_home)
        self.assertIn("theme-workshop", themed_home)
        self.assertIn("theme-workshop-tools", themed_home)
        self.assertNotIn("boat-waves", themed_home)
        themed_identification = self.client.get("/identification").get_data(
            as_text=True
        )
        self.assertIn("identification-page home-theme-christmas", themed_identification)
        self.assertIn("home-theme-scene", themed_identification)
        second_signature = self.client.get("/etat-accueil").get_json()["signature"]
        self.assertNotEqual(first_signature, second_signature)

        steampunk_response = self.client.post(
            "/admin/reglages/affichage/enregistrer",
            data={
                "home_theme": "steampunk",
            },
            follow_redirects=True,
        )
        self.assertIn(
            'name="home_theme" type="radio" value="steampunk" checked',
            steampunk_response.get_data(as_text=True),
        )
        self.assertIn("home-theme-steampunk", self.client.get("/").get_data(as_text=True))
        self.assertIn(
            "identification-page home-theme-steampunk",
            self.client.get("/identification").get_data(as_text=True),
        )

        javascript_response = self.client.get("/static/app.js")
        javascript = javascript_response.get_data(as_text=True)
        javascript_response.close()
        stylesheet_response = self.client.get("/static/style.css")
        stylesheet = stylesheet_response.get_data(as_text=True)
        stylesheet_response.close()
        self.assertIn("--departure-progress", javascript)
        self.assertIn("requestAnimationFrame", javascript)
        self.assertIn("countdown-snow-fall", stylesheet)
        self.assertIn("home-theme-halloween", stylesheet)
        self.assertIn("home-theme-christmas", stylesheet)
        self.assertIn("home-theme-easter", stylesheet)
        self.assertIn("home-theme-dark", stylesheet)
        self.assertIn("home-theme-valentine", stylesheet)
        self.assertIn("home-theme-summer", stylesheet)
        self.assertIn("home-theme-steampunk", stylesheet)
        self.assertIn("bat-curve-flight", stylesheet)
        self.assertIn("rabbit-ground-run", stylesheet)
        self.assertIn("summer-horizon-sail", stylesheet)
        self.assertIn("valentine-background-pulse", stylesheet)
        self.assertIn("airship-cruise", stylesheet)
        self.assertIn("summer-wave-roll", stylesheet)
        self.assertIn("summer-wall-splash", stylesheet)
        self.assertIn("summer-rays-turn", stylesheet)
        self.assertIn("summer-rays-turn 52s linear infinite", stylesheet)
        self.assertIn('content: "⛱️"', stylesheet)
        self.assertNotIn('content: "🏖️"', stylesheet)
        self.assertIn("vintage-wrench-body", themed_home)
        self.assertIn("workshop-tools-bob", stylesheet)
        self.assertIn("boat-flag-wave", stylesheet)
        self.assertIn("steampunk-dial-hand", stylesheet)
        self.assertIn(".crosser-heart .heart-glow { display: none; }", stylesheet)
        self.assertIn("spider-descend", stylesheet)
        self.assertIn("crosser-airship", themed_home)

    def test_wake_lock_can_follow_a_daily_schedule(self):
        self.login_admin()
        response = self.client.post(
            "/admin/reglages/borne/enregistrer",
            data={
                "keep_screen_awake": "1",
                "wake_lock_start": "08:30",
                "wake_lock_end": "19:15",
            },
            follow_redirects=True,
        )
        page = response.get_data(as_text=True)
        self.assertIn('value="08:30"', page)
        self.assertIn('value="19:15"', page)
        home_page = self.client.get("/").get_data(as_text=True)
        self.assertIn('data-wake-lock-start="08:30"', home_page)
        self.assertIn('data-wake-lock-end="19:15"', home_page)
        javascript_response = self.client.get("/static/app.js")
        javascript = javascript_response.get_data(as_text=True)
        javascript_response.close()
        self.assertIn("wakeLockScheduleIsActive", javascript)
        self.assertIn("Europe/Paris", javascript)

        rejected = self.client.post(
            "/admin/reglages/borne/enregistrer",
            data={
                "wake_lock_start": "25:70",
                "wake_lock_end": "17:00",
            },
            follow_redirects=True,
        )
        self.assertIn("heure de début", rejected.get_data(as_text=True))

    def test_openlab_schedule_is_configurable_by_quarter_hours(self):
        self.login_admin()
        display_page = self.client.get("/admin/reglages/affichage").get_data(as_text=True)
        options_page = self.client.get("/admin/reglages/borne").get_data(as_text=True)
        self.assertIn(
            'name="openlab_attendance_monday_start" type="time" step="900" value=""',
            options_page,
        )
        self.assertIn(
            'name="openlab_attendance_tuesday_start" type="time" step="900" value="14:00"',
            options_page,
        )
        self.assertIn(
            'name="openlab_attendance_wednesday_end" type="time" step="900" value="12:00"',
            options_page,
        )
        self.assertIn(
            'name="openlab_attendance_saturday_start" type="time" step="900" value="09:30"',
            options_page,
        )
        self.assertIn(
            'name="openlab_attendance_show_decimals" type="checkbox" value="1"',
            display_page,
        )
        self.assertNotIn(
            'name="openlab_attendance_show_decimals" type="checkbox" value="1" checked',
            display_page,
        )
        self.assertIn("calculs de fréquentation par quarts d’heure", options_page)
        self.assertIn("Thème de la page d’accueil", display_page)
        self.assertIn('name="home_theme"', display_page)
        self.assertIn('name="openlab_attendance_show_decimals"', display_page)
        self.assertNotIn('name="openlab_attendance_tuesday_start"', display_page)
        self.assertIn('name="openlab_attendance_tuesday_start"', options_page)
        self.assertNotIn('name="home_theme"', options_page)
        self.assertGreaterEqual(display_page.count('name="home_theme"'), 8)
        self.assertEqual(display_page.count('name="openlab_attendance_show_decimals"'), 1)

        response = self.client.post(
            "/admin/reglages/borne/enregistrer",
            data={
                "wake_lock_start": "09:00",
                "wake_lock_end": "17:00",
                "openlab_attendance_tuesday_start": "13:45",
                "openlab_attendance_tuesday_end": "17:15",
            },
            follow_redirects=True,
        )
        page = response.get_data(as_text=True)
        self.assertIn("Les options ont été enregistrées", page)
        self.assertIn(
            'name="openlab_attendance_tuesday_start" type="time" step="900" value="13:45"',
            page,
        )
        self.assertIn(
            'name="openlab_attendance_tuesday_end" type="time" step="900" value="17:15"',
            page,
        )
        display_response = self.client.post(
            "/admin/reglages/affichage/enregistrer",
            data={"home_theme": "classic", "openlab_attendance_show_decimals": "1"},
            follow_redirects=True,
        )
        self.assertIn(
            'name="openlab_attendance_show_decimals" type="checkbox" value="1" checked',
            display_response.get_data(as_text=True),
        )

        rejected = self.client.post(
            "/admin/reglages/borne/enregistrer",
            data={
                "wake_lock_start": "09:00",
                "wake_lock_end": "17:00",
                "openlab_attendance_tuesday_start": "09:10",
                "openlab_attendance_tuesday_end": "17:00",
            },
            follow_redirects=True,
        )
        self.assertIn(
            "doivent utiliser des quarts d&#39;heure complets",
            rejected.get_data(as_text=True),
        )

    def test_admin_can_manage_animations_and_export_annual_results(self):
        self.login_admin()
        current_year = datetime.now(timezone.utc).year
        service_date = f"{current_year}-06-15"
        response = self.client.post(
            "/admin/animations/nouveau",
            data={
                "service_type": "animation",
                "title": "Initiation découpe laser",
                "service_date": service_date,
                "start_time": "14:00",
                "end_time": "16:00",
                "minimum_age": "10",
                "description": "Découverte de la découpe laser.",
                "expected_participants": "12",
                "actual_participants": "9",
            },
            follow_redirects=True,
        )
        self.assertIn("enregistrement a été ajouté", response.get_data(as_text=True))

        history = self.client.get(
            f"/admin/animations?year={current_year}&q=Initiation"
        ).get_data(as_text=True)
        self.assertIn("Initiation découpe laser", history)
        animation_history = self.client.get(
            f"/admin/animations?year={current_year}&type=animation"
        ).get_data(as_text=True)
        self.assertIn("12 places / 0 inscrits / 9 présents", animation_history)
        self.assertIn("service-type-animation", animation_history)

        form_page = self.client.get("/admin/animations/nouveau").get_data(as_text=True)
        self.assertIn("Places maximum", form_page)
        self.assertIn("Participants sur place", form_page)
        self.assertNotIn("Créneau réservable", form_page)
        self.assertNotIn("Location de machine", form_page)

        statistics = self.client.get(
            f"/admin/frequentation/statistiques?year={current_year}"
        ).get_data(as_text=True)
        self.assertIn("Animations effectuées", statistics)
        self.assertIn("Participants aux animations", statistics)
        self.assertIn("Participants aux réservations", statistics)
        self.assertIn("Recettes des réservations et locations", statistics)

        animations_export = self.client.get(
            f"/admin/exports/animations.csv?year={current_year}"
        )
        self.assertEqual(animations_export.status_code, 200)
        self.assertIn("Initiation découpe laser", animations_export.get_data(as_text=True))
        self.assertIn("Places maximum", animations_export.get_data(as_text=True))

        with self.database() as database:
            service_id = database.execute(
                "SELECT id FROM fablab_services WHERE service_type = 'animation'"
            ).fetchone()[0]
        updated = self.client.post(
            f"/admin/animations/{service_id}/modifier",
            data={
                "service_type": "animation",
                "title": "Initiation laser mise à jour",
                "service_date": service_date,
                "start_time": "14:00",
                "end_time": "16:30",
                "minimum_age": "10",
                "description": "Animation mise à jour.",
                "expected_participants": "10",
                "actual_participants": "10",
            },
            follow_redirects=True,
        )
        self.assertIn("mise à jour", updated.get_data(as_text=True))
        refused = self.client.post(
            f"/admin/animations/{service_id}/supprimer",
            data={"confirmation": "non"},
            follow_redirects=True,
        )
        self.assertIn("SUPPRIMER", refused.get_data(as_text=True))
        deleted = self.client.post(
            f"/admin/animations/{service_id}/supprimer",
            data={"confirmation": "SUPPRIMER"},
            follow_redirects=True,
        )
        self.assertIn("enregistrement a été supprimé", deleted.get_data(as_text=True))

    def test_admin_can_complete_billing_cycle_and_export_documents(self):
        self.login_admin()
        current_year = datetime.now(timezone.utc).year
        payload = {
            "quote_date": f"{current_year}-08-24",
            "client_contact": "Camille Durand",
            "client_structure": "Association Test",
            "address_line": "10 rue des Ateliers",
            "postal_code": "00000",
            "city": "Ville Fictive",
            "phone": "02 99 00 00 00",
            "email": "camille@example.fr",
            "title": "Atelier prototypage",
            "description": "Découverte des outils de fabrication numérique.",
            "activity_date": f"{current_year}-09-15",
            "activity_time_details": "9 h à 12 h",
            "participants": "8",
            "rate_category": "normal",
            "rate_unit": "hourly",
            "rate_quantity": "2",
            "travel_quantity": "1",
            "consumable_mode": "billed",
            "consumable_quantity": "2",
            "notes": "Dossier de test automatisé",
        }
        created = self.client.post(
            "/admin/facturation/nouveau", data=payload, follow_redirects=True
        )
        created_page = created.get_data(as_text=True)
        self.assertIn(f"devis {current_year}.1 a été créé", created_page)
        self.assertIn("240,00", created_page)

        with self.database() as database:
            record = database.execute(
                "SELECT * FROM billing_records ORDER BY id DESC LIMIT 1"
            ).fetchone()
        record_id = record["id"]
        self.assertEqual(record["quote_number"], f"{current_year}.1")
        self.assertEqual(record["amount_cents"], 24000)

        quote_pdf = self.client.get(f"/admin/facturation/{record_id}/devis.pdf")
        self.assertEqual(quote_pdf.status_code, 200)
        self.assertTrue(quote_pdf.data.startswith(b"%PDF"))
        expected_quote_name = (
            f"2408{current_year}_Devis_AssociationTest_FABLAB_1.pdf"
        )
        self.assertIn(
            expected_quote_name,
            quote_pdf.headers.get("Content-Disposition", ""),
        )
        quote_docx = self.client.get(f"/admin/facturation/{record_id}/devis.docx")
        self.assertEqual(quote_docx.status_code, 200)
        self.assertTrue(quote_docx.data.startswith(b"PK"))
        self.assertIn(
            expected_quote_name.removesuffix(".pdf") + ".docx",
            quote_docx.headers.get("Content-Disposition", ""),
        )

        unsigned_invoice = self.client.post(
            f"/admin/facturation/{record_id}/creer-facture", follow_redirects=True
        )
        self.assertIn("doit être marqué comme signé", unsigned_invoice.get_data(as_text=True))
        signed = self.client.post(
            f"/admin/facturation/{record_id}/signer", follow_redirects=True
        )
        signed_page = signed.get_data(as_text=True)
        self.assertIn("marqué comme signé", signed_page)
        self.assertIn("Signé le", signed_page)
        self.assertNotRegex(signed_page, r"Signé le \d{4}-\d{2}-\d{2}T")
        invoiced = self.client.post(
            f"/admin/facturation/{record_id}/creer-facture", follow_redirects=True
        )
        self.assertIn(f"facture {current_year}.1 est prête", invoiced.get_data(as_text=True))

        with self.database() as database:
            invoiced_record = database.execute(
                "SELECT * FROM billing_records WHERE id = ?", (record_id,)
            ).fetchone()
            service = database.execute(
                "SELECT * FROM fablab_services WHERE id = ?",
                (invoiced_record["service_id"],),
            ).fetchone()
        self.assertEqual(invoiced_record["invoice_number"], f"{current_year}.1")
        self.assertEqual(service["service_type"], "reservation")
        self.assertEqual(service["invoice_reference"], f"{current_year}.1")
        self.assertEqual(service["amount_cents"], 24000)
        self.assertEqual(service["participants"], 8)

        invoice_pdf = self.client.get(f"/admin/facturation/{record_id}/facture.pdf")
        self.assertEqual(invoice_pdf.status_code, 200)
        self.assertTrue(invoice_pdf.data.startswith(b"%PDF"))
        invoice_date = datetime.strptime(
            invoiced_record["invoice_date"], "%Y-%m-%d"
        ).strftime("%d%m%Y")
        expected_invoice_name = (
            f"{invoice_date}_Facture_AssociationTest_FABLAB_1.pdf"
        )
        self.assertIn(
            expected_invoice_name,
            invoice_pdf.headers.get("Content-Disposition", ""),
        )
        invoice_docx = self.client.get(f"/admin/facturation/{record_id}/facture.docx")
        self.assertEqual(invoice_docx.status_code, 200)
        self.assertTrue(invoice_docx.data.startswith(b"PK"))
        self.assertIn(
            expected_invoice_name.removesuffix(".pdf") + ".docx",
            invoice_docx.headers.get("Content-Disposition", ""),
        )

        sent = self.client.post(
            f"/admin/facturation/{record_id}/envoyer", follow_redirects=True
        )
        self.assertIn("marquée comme envoyée", sent.get_data(as_text=True))
        first_reminder = self.client.post(
            f"/admin/facturation/{record_id}/relance/1", follow_redirects=True
        )
        self.assertIn("relance n° 1", first_reminder.get_data(as_text=True))
        second_reminder = self.client.post(
            f"/admin/facturation/{record_id}/relance/2", follow_redirects=True
        )
        self.assertIn("relance n° 2", second_reminder.get_data(as_text=True))
        paid = self.client.post(
            f"/admin/facturation/{record_id}/payer", follow_redirects=True
        )
        self.assertIn("règlement est enregistré", paid.get_data(as_text=True))

        paid_invoice = self.client.get(f"/admin/facturation/{record_id}/facture.docx")
        with zipfile.ZipFile(io.BytesIO(paid_invoice.data)) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")
        self.assertIn("FACTURE PAYÉE", document_xml)
        unpaid = self.client.post(
            f"/admin/facturation/{record_id}/payer", follow_redirects=True
        )
        self.assertIn("règlement a été retiré", unpaid.get_data(as_text=True))
        self.client.post(f"/admin/facturation/{record_id}/payer")

        facdepot_pdf = self.client.get(
            f"/admin/facturation/facdepot/{current_year}.pdf"
        )
        self.assertEqual(facdepot_pdf.status_code, 200)
        self.assertTrue(facdepot_pdf.data.startswith(b"%PDF"))
        annual_export_prefix = datetime.now().strftime("%m%d%Y")
        self.assertIn(
            f"{annual_export_prefix}_BilanFacturation{current_year}.pdf",
            facdepot_pdf.headers.get("Content-Disposition", ""),
        )
        facdepot_xlsx = self.client.get(
            f"/admin/facturation/facdepot/{current_year}.xlsx"
        )
        self.assertEqual(facdepot_xlsx.status_code, 200)
        self.assertTrue(facdepot_xlsx.data.startswith(b"PK"))
        self.assertIn(
            f"{annual_export_prefix}_BilanFacturation{current_year}.xlsx",
            facdepot_xlsx.headers.get("Content-Disposition", ""),
        )
        with zipfile.ZipFile(io.BytesIO(facdepot_xlsx.data)) as archive:
            styles_xml = archive.read("xl/styles.xml")
            sheet_xml = archive.read("xl/worksheets/sheet1.xml")
            archive_names = set(archive.namelist())
        ElementTree.fromstring(styles_xml)
        ElementTree.fromstring(sheet_xml)
        self.assertLess(sheet_xml.index(b"<autoFilter"), sheet_xml.index(b"<mergeCells"))
        self.assertIn("xl/media/signature.png", archive_names)
        self.assertIn(b"fitToPage", sheet_xml)
        self.assertNotIn(b"Dossier de test automatise", sheet_xml)

        services_page = self.client.get("/admin/animations").get_data(as_text=True)
        self.assertIn("Voir la facturation", services_page)
        blocked_delete = self.client.post(
            f"/admin/animations/{service['id']}/supprimer",
            data={"confirmation": "SUPPRIMER"},
            follow_redirects=True,
        )
        self.assertIn("gérés depuis Facturation", blocked_delete.get_data(as_text=True))

    def test_billing_record_can_be_renamed_redated_and_invoice_only_deleted(self):
        self.login_admin()
        current_year = datetime.now(timezone.utc).year
        payload = {
            "quote_date": f"{current_year}-08-20",
            "client_contact": "Camille Durand",
            "client_structure": "Association Test",
            "address_line": "10 rue des Ateliers",
            "postal_code": "00000",
            "city": "Ville Fictive",
            "phone": "02 99 00 00 00",
            "email": "camille@example.fr",
            "title": "Atelier prototypage",
            "description": "Découverte des outils de fabrication numérique.",
            "activity_date": f"{current_year}-09-15",
            "activity_time_details": "9 h à 12 h",
            "participants": "8",
            "rate_category": "normal",
            "rate_unit": "hourly",
            "rate_quantity": "2",
            "travel_quantity": "0",
            "consumable_mode": "included",
            "consumable_quantity": "0",
            "notes": "",
        }
        self.client.post(
            "/admin/facturation/nouveau", data=payload, follow_redirects=True
        )
        with self.database() as database:
            record = database.execute(
                "SELECT * FROM billing_records ORDER BY id DESC LIMIT 1"
            ).fetchone()
        record_id = record["id"]
        with self.database() as database:
            database.execute(
                """
                INSERT INTO billing_clients (
                    contact_name, contact_name_normalized, structure_name,
                    address_line, postal_code, city, phone, email,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Deuxième Client", "deuxieme client", "Structure secondaire",
                    "2 rue des Tests", "00000", "Ville Fictive", "0200000000",
                    "second@example.fr", "2026-09-14T10:00:00+00:00",
                    "2026-09-14T10:00:00+00:00",
                ),
            )
            database.commit()

        edit_page = self.client.get(
            f"/admin/facturation/{record_id}/modifier"
        ).get_data(as_text=True)
        self.assertNotIn(">None</textarea>", edit_page)
        self.assertIn("clients-facturation", edit_page)
        clients = self.client.get("/admin/api/clients-facturation").get_json()["clients"]
        self.assertEqual(clients[0]["contact"], "Camille Durand")
        self.assertEqual(clients[0]["email"], "camille@example.fr")
        directory_page = self.client.get("/admin/facturation").get_data(as_text=True)
        self.assertIn("Annuaire des clients", directory_page)
        self.assertIn("Camille Durand", directory_page)
        self.assertIn("clients/export.xlsx", directory_page)
        self.assertIn("clients/export.pdf", directory_page)

        client_directory_pdf = self.client.get(
            "/admin/facturation/clients/export.pdf"
        )
        self.assertEqual(client_directory_pdf.status_code, 200)
        self.assertTrue(client_directory_pdf.data.startswith(b"%PDF"))
        self.assertIn(
            "_AnnuaireClients_AtelierExemple.pdf",
            client_directory_pdf.headers.get("Content-Disposition", ""),
        )
        self.assertIn(
            datetime.now().strftime("%Y%m%d") + "_AnnuaireClients_AtelierExemple.pdf",
            client_directory_pdf.headers.get("Content-Disposition", ""),
        )
        client_directory_xlsx = self.client.get(
            "/admin/facturation/clients/export.xlsx"
        )
        self.assertEqual(client_directory_xlsx.status_code, 200)
        self.assertTrue(client_directory_xlsx.data.startswith(b"PK"))
        self.assertIn(
            "_AnnuaireClients_AtelierExemple.xlsx",
            client_directory_xlsx.headers.get("Content-Disposition", ""),
        )
        self.assertIn(
            datetime.now().strftime("%Y%m%d") + "_AnnuaireClients_AtelierExemple.xlsx",
            client_directory_xlsx.headers.get("Content-Disposition", ""),
        )
        with zipfile.ZipFile(io.BytesIO(client_directory_xlsx.data)) as archive:
            client_sheet_xml = archive.read("xl/worksheets/sheet1.xml")
            client_styles_xml = archive.read("xl/styles.xml")
        ElementTree.fromstring(client_sheet_xml)
        ElementTree.fromstring(client_styles_xml)
        self.assertIn("Camille Durand".encode(), client_sheet_xml)
        self.assertIn("camille@example.fr".encode(), client_sheet_xml)
        self.assertIn("Atelier prototypage".encode(), client_sheet_xml)
        self.assertIn(f"Devis {record['quote_number']}".encode(), client_sheet_xml)
        with self.database() as database:
            stored_client = database.execute(
                "SELECT * FROM billing_clients WHERE id = ?", (record["client_id"],)
            ).fetchone()
        self.assertIsNotNone(stored_client)
        self.assertEqual(stored_client["email"], "camille@example.fr")

        client_update = dict(payload)
        client_update["email"] = "annuaire@example.fr"
        client_update["phone"] = "0200000000"
        updated_client_page = self.client.post(
            f"/admin/facturation/clients/{stored_client['id']}/modifier",
            data=client_update,
            follow_redirects=True,
        )
        self.assertIn("fiche client a été mise à jour", updated_client_page.get_data(as_text=True))
        clients = self.client.get("/admin/api/clients-facturation").get_json()["clients"]
        self.assertEqual(clients[0]["email"], "annuaire@example.fr")

        self.client.post(f"/admin/facturation/{record_id}/signer")
        self.client.post(f"/admin/facturation/{record_id}/creer-facture")
        edit_payload = dict(payload)
        edit_payload.update(
            {
                "quote_number": f"DEVIS SPECIAL {current_year}",
                "invoice_number": f"FACTURE SPECIAL {current_year}",
                "quote_signed_date": f"{current_year}-08-21",
                "invoice_date": f"{current_year}-08-22",
                "invoice_sent_date": f"{current_year}-08-23",
                "reminder_one_date": f"{current_year}-09-22",
                "reminder_two_date": f"{current_year}-10-02",
                "paid_date": f"{current_year}-10-03",
                "email": "devis-actualise@example.fr",
            }
        )
        edited = self.client.post(
            f"/admin/facturation/{record_id}/modifier",
            data=edit_payload,
            follow_redirects=True,
        )
        edited_page = edited.get_data(as_text=True)
        self.assertIn(f"DEVIS SPECIAL {current_year}", edited_page)
        self.assertNotIn("Note interne", edited_page)

        with self.database() as database:
            updated = database.execute(
                "SELECT * FROM billing_records WHERE id = ?", (record_id,)
            ).fetchone()
            service_id = updated["service_id"]
            updated_client = database.execute(
                "SELECT * FROM billing_clients WHERE id = ?", (updated["client_id"],)
            ).fetchone()
        self.assertEqual(updated["invoice_number"], f"FACTURE SPECIAL {current_year}")
        self.assertTrue(updated["quote_signed_at"].startswith(f"{current_year}-08-21"))
        self.assertTrue(updated["invoice_sent_at"].startswith(f"{current_year}-08-23"))
        self.assertTrue(updated["reminder_one_at"].startswith(f"{current_year}-09-22"))
        self.assertTrue(updated["reminder_two_at"].startswith(f"{current_year}-10-02"))
        self.assertTrue(updated["paid_at"].startswith(f"{current_year}-10-03"))
        self.assertEqual(updated_client["email"], "devis-actualise@example.fr")

        deleted = self.client.post(
            f"/admin/facturation/{record_id}/supprimer-facture",
            data={"confirmation": "SUPPRIMER"},
            follow_redirects=True,
        )
        self.assertIn("facture a été supprimée", deleted.get_data(as_text=True))
        with self.database() as database:
            preserved_quote = database.execute(
                "SELECT * FROM billing_records WHERE id = ?", (record_id,)
            ).fetchone()
            linked_service = database.execute(
                "SELECT id FROM fablab_services WHERE id = ?", (service_id,)
            ).fetchone()
        self.assertEqual(preserved_quote["quote_number"], f"DEVIS SPECIAL {current_year}")
        self.assertIsNone(preserved_quote["invoice_number"])
        self.assertIsNone(preserved_quote["invoice_sent_at"])
        self.assertIsNone(preserved_quote["paid_at"])
        self.assertIsNone(preserved_quote["service_id"])
        self.assertIsNone(linked_service)

    def test_quote_cancellation_is_reversible_and_preserves_signature(self):
        self.login_admin()
        current_year = datetime.now(timezone.utc).year
        payload = {
            "quote_date": f"{current_year}-08-28",
            "client_contact": "Louise Martin",
            "client_structure": "Structure Annulation",
            "address_line": "5 rue du Test",
            "postal_code": "00000",
            "city": "Ville Fictive",
            "phone": "",
            "email": "louise@example.fr",
            "title": "Créneau susceptible d'être annulé",
            "description": "Dossier conservé même en cas d'annulation.",
            "activity_date": f"{current_year}-10-10",
            "activity_time_details": "14 h à 16 h",
            "participants": "4",
            "rate_category": "normal",
            "rate_unit": "hourly",
            "rate_quantity": "2",
            "travel_quantity": "0",
            "consumable_mode": "included",
            "consumable_quantity": "0",
            "notes": "",
        }
        self.client.post(
            "/admin/facturation/nouveau", data=payload, follow_redirects=True
        )
        with self.database() as database:
            record_id = database.execute(
                "SELECT id FROM billing_records ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]

        cancelled = self.client.post(
            f"/admin/facturation/{record_id}/annulation", follow_redirects=True
        )
        cancelled_page = cancelled.get_data(as_text=True)
        self.assertIn("devis est annulé", cancelled_page)
        self.assertIn("Devis annulé", cancelled_page)
        self.assertIn("Réouvrir le devis", cancelled_page)
        self.assertIn("Annulé le", cancelled_page)
        with self.database() as database:
            cancelled_record = database.execute(
                "SELECT * FROM billing_records WHERE id = ?", (record_id,)
            ).fetchone()
        self.assertIsNotNone(cancelled_record["quote_cancelled_at"])
        self.assertIsNone(cancelled_record["quote_signed_at"])

        quote_list = self.client.get(
            "/admin/facturation?status=quote"
        ).get_data(as_text=True)
        cancelled_list = self.client.get(
            "/admin/facturation?status=cancelled"
        ).get_data(as_text=True)
        self.assertNotIn("Créneau susceptible d'être annulé", quote_list)
        self.assertIn("Structure Annulation", cancelled_list)
        self.assertIn("billing-status-cancelled", cancelled_list)

        refused_signature = self.client.post(
            f"/admin/facturation/{record_id}/signer", follow_redirects=True
        ).get_data(as_text=True)
        self.assertIn("Réouvrez le devis", refused_signature)
        refused_invoice = self.client.post(
            f"/admin/facturation/{record_id}/creer-facture", follow_redirects=True
        ).get_data(as_text=True)
        self.assertIn("doit être réouvert", refused_invoice)

        self.client.post(f"/admin/facturation/{record_id}/annulation")
        self.client.post(f"/admin/facturation/{record_id}/signer")
        self.client.post(f"/admin/facturation/{record_id}/annulation")
        with self.database() as database:
            signed_cancelled = database.execute(
                "SELECT * FROM billing_records WHERE id = ?", (record_id,)
            ).fetchone()
        self.assertIsNotNone(signed_cancelled["quote_signed_at"])
        self.assertIsNotNone(signed_cancelled["quote_cancelled_at"])
        signed_list = self.client.get(
            "/admin/facturation?status=signed"
        ).get_data(as_text=True)
        self.assertNotIn("Créneau susceptible d'être annulé", signed_list)

        reopened = self.client.post(
            f"/admin/facturation/{record_id}/annulation", follow_redirects=True
        ).get_data(as_text=True)
        self.assertIn("réouvert dans son état précédent", reopened)
        with self.database() as database:
            reopened_record = database.execute(
                "SELECT * FROM billing_records WHERE id = ?", (record_id,)
            ).fetchone()
        self.assertIsNone(reopened_record["quote_cancelled_at"])
        self.assertIsNotNone(reopened_record["quote_signed_at"])
        invoiced = self.client.post(
            f"/admin/facturation/{record_id}/creer-facture", follow_redirects=True
        )
        self.assertIn("est prête", invoiced.get_data(as_text=True))

    def test_admin_can_create_and_invoice_a_machine_rental(self):
        self.login_admin()
        current_year = datetime.now(timezone.utc).year
        rental_form = self.client.get(
            "/admin/facturation/nouveau?type=rental"
        ).get_data(as_text=True)
        self.assertIn("Date du début de la location *", rental_form)
        self.assertIn("Heure du rdv *", rental_form)
        self.assertIn("Heure estimée de la fin du rdv *", rental_form)
        self.assertIn(
            "La durée, possible de 15 minutes à 8 heures, alimente les statistiques.",
            rental_form,
        )
        self.assertNotIn("Modifiable pour reprendre un ancien dossier.", rental_form)
        payload = {
            "billing_type": "rental",
            "quote_date": f"{current_year}-08-24",
            "client_contact": "Morgan Martin",
            "client_structure": "Atelier partenaire",
            "address_line": "4 rue de la Machine",
            "postal_code": "00000",
            "city": "Ville Fictive",
            "phone": "02 99 00 00 01",
            "email": "morgan@example.fr",
            "title": "Location de la Prusa",
            "description": "Mise à disposition pour un projet de prototypage.",
            "activity_date": f"{current_year}-09-01",
            "activity_time_details": "Remise à 10 h",
            "rental_machine_key": "prusa_mk39",
            "rental_months": "2",
            "rental_end_date": f"{current_year}-11-01",
            "rental_delivery": "1",
            "notes": "Appeler avant la remise.",
        }
        created = self.client.post(
            "/admin/facturation/nouveau", data=payload, follow_redirects=True
        )
        page = created.get_data(as_text=True)
        self.assertIn(f"devis {current_year}.L1 a été créé", page)
        self.assertIn("205,00", page)
        self.assertIn("Appeler avant la remise", page)

        with self.database() as database:
            record = database.execute(
                "SELECT * FROM billing_records WHERE quote_number = ?",
                (f"{current_year}.L1",),
            ).fetchone()
        self.assertEqual(record["billing_type"], "rental")
        self.assertEqual(record["rental_machine_name"], "Machine fictive 1")
        self.assertEqual(record["rental_months"], 2)
        self.assertEqual(record["amount_cents"], 20500)

        record_id = record["id"]
        self.client.post(f"/admin/facturation/{record_id}/signer")
        invoiced = self.client.post(
            f"/admin/facturation/{record_id}/creer-facture", follow_redirects=True
        )
        self.assertIn(f"facture {current_year}.L1 est prête", invoiced.get_data(as_text=True))
        with self.database() as database:
            updated = database.execute(
                "SELECT * FROM billing_records WHERE id = ?", (record_id,)
            ).fetchone()
            service = database.execute(
                "SELECT * FROM fablab_services WHERE id = ?", (updated["service_id"],)
            ).fetchone()
        self.assertEqual(service["service_type"], "rental")
        self.assertEqual(service["amount_cents"], 20500)

        rental_pdf = self.client.get(f"/admin/facturation/{record_id}/facture.pdf")
        rental_docx = self.client.get(f"/admin/facturation/{record_id}/facture.docx")
        self.assertTrue(rental_pdf.data.startswith(b"%PDF"))
        self.assertTrue(rental_docx.data.startswith(b"PK"))
        with zipfile.ZipFile(io.BytesIO(rental_docx.data)) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")
        self.assertIn("Conditions particulières de location", document_xml)
        self.assertIn("Devis d’origine", document_xml)

        edit_payload = dict(payload)
        edit_payload.update({
            "quote_signed_date": f"{current_year}-08-27",
            "invoice_date": f"{current_year}-11-02",
        })
        edited = self.client.post(
            f"/admin/facturation/{record_id}/modifier",
            data=edit_payload,
            follow_redirects=True,
        )
        self.assertIn("mis à jour", edited.get_data(as_text=True))
        with self.database() as database:
            edited_record = database.execute(
                "SELECT quote_signed_at, invoice_date FROM billing_records WHERE id = ?",
                (record_id,),
            ).fetchone()
        self.assertTrue(edited_record["quote_signed_at"].startswith(f"{current_year}-08-27"))
        self.assertEqual(edited_record["invoice_date"], f"{current_year}-11-02")

    def test_agglo_invoice_is_free_and_payment_reminder_is_sent_once(self):
        self.login_admin()
        current_year = datetime.now(timezone.utc).year
        payload = {
            "quote_date": f"{current_year}-08-24",
            "client_contact": "Agent Agglo",
            "client_structure": "Association Exemple",
            "address_line": "Parc de l'Aumaillerie",
            "postal_code": "35133",
            "city": "La Selle-en-Luitré",
            "phone": "02 99 00 00 00",
            "email": "agent@example.fr",
            "title": "Créneau interne",
            "description": "Accompagnement d'un service de l'Agglomération.",
            "activity_date": f"{current_year}-09-15",
            "activity_time_details": "10 h à 12 h",
            "participants": "4",
            "rate_category": "agglo",
            "rate_unit": "hourly",
            "rate_quantity": "2",
            "travel_quantity": "0",
            "consumable_mode": "included",
            "consumable_quantity": "0",
            "notes": "",
        }
        self.client.post(
            "/admin/facturation/nouveau", data=payload, follow_redirects=True
        )
        with self.database() as database:
            free_record = database.execute(
                "SELECT * FROM billing_records ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(free_record["rate_is_agglo"], 1)
        self.assertEqual(free_record["amount_cents"], 0)
        record_id = free_record["id"]
        self.client.post(f"/admin/facturation/{record_id}/signer")
        created_invoice = self.client.post(
            f"/admin/facturation/{record_id}/creer-facture", follow_redirects=True
        )
        self.assertIn("enregistrée comme offerte", created_invoice.get_data(as_text=True))
        with self.database() as database:
            free_invoice = database.execute(
                "SELECT * FROM billing_records WHERE id = ?", (record_id,)
            ).fetchone()
        self.assertIsNotNone(free_invoice["invoice_sent_at"])
        self.assertIsNotNone(free_invoice["paid_at"])

        overdue_sent_at = datetime.now(timezone.utc) - timedelta(days=31)
        with self.database() as database:
            database.execute(
                """
                UPDATE billing_records
                SET amount_cents = 12000, paid_at = NULL,
                    invoice_sent_at = ?, payment_overdue_notified_at = NULL
                WHERE id = ?
                """,
                (overdue_sent_at.isoformat(), record_id),
            )
            database.commit()
            with mock.patch("app.send_discord_notification", return_value=True) as send:
                self.assertEqual(
                    run_invoice_payment_reminders(database, datetime.now(timezone.utc)),
                    1,
                )
                self.assertEqual(
                    run_invoice_payment_reminders(database, datetime.now(timezone.utc)),
                    0,
                )
        send.assert_called_once()
        self.assertEqual(send.call_args.args[1], "invoice_overdue")
        self.assertEqual(send.call_args.kwargs["client"], "Association Exemple")

    def test_monthly_animation_reminder_is_customizable_and_sent_once(self):
        fake_webhook = (
            "https://discord.com/api/webhooks/123456789012345678/"
            "monthly_test_secret_ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        )
        self.app.config["DISCORD_SYNCHRONOUS"] = True
        self.login_admin()
        configured = self.client.post(
            "/admin/reglages/notifications",
            data={
                "webhook_url": fake_webhook,
                "enabled": "1",
                "monthly_animations": "1",
                "bot_name": "Compteur",
                "monthly_animations_message": "📅 Animations de {month} à renseigner.",
            },
            follow_redirects=True,
        )
        notification_page = configured.get_data(as_text=True)
        self.assertIn("Rappel mensuel des animations", notification_page)
        self.assertIn(
            "Le 1er de chaque mois, rappel de renseigner les animations réalisées le mois précédent.",
            notification_page,
        )

        first_of_month = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
        with mock.patch("app.post_discord_message", return_value=None) as post_message:
            with self.app.app_context():
                with self.database() as database:
                    self.assertTrue(
                        run_monthly_animation_reminder(database, first_of_month)
                    )
                    self.assertFalse(
                        run_monthly_animation_reminder(database, first_of_month)
                    )
                    self.assertEqual(
                        database.execute(
                            "SELECT value FROM app_settings "
                            "WHERE key = 'discord_monthly_animations_last_period'"
                        ).fetchone()[0],
                        "2026-08",
                    )
        post_message.assert_called_once_with(
            fake_webhook,
            "📅 Animations de août 2026 à renseigner.",
            "Compteur",
        )
        with self.app.app_context():
            with self.database() as database:
                self.assertFalse(
                    run_monthly_animation_reminder(
                        database, datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)
                    )
                )

    def test_discord_configuration_keeps_secret_out_of_database_and_notifies(self):
        fake_webhook = (
            "https://discord.com/api/webhooks/123456789012345678/"
            "test_secret_token_ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        )
        self.app.config["DISCORD_SYNCHRONOUS"] = True
        self.login_admin()
        configured = self.client.post(
            "/admin/reglages/notifications",
            data={
                "webhook_url": fake_webhook,
                "enabled": "1",
                "arrivals": "1",
                "departures": "1",
                "visitors": "1",
                "retention": "1",
                "bot_name": "Compteur test",
                "arrival_message": "🟢 {name} arrive.",
                "departure_message": "🔴 {name} part.",
                "visitor_message": "🟡 Visiteur présent.",
                "retention_message": "🟠 {name} : {action} le {date}.",
            },
            follow_redirects=True,
        )
        page = configured.get_data(as_text=True)
        self.assertIn("Webhook enregistré", page)
        self.assertNotIn(fake_webhook, page)
        self.assertTrue(Path(self.app.config["DISCORD_WEBHOOK_FILE"]).exists())
        self.assertNotIn(fake_webhook, Path(self.database_path).read_bytes().decode("latin-1"))

        with mock.patch("app.post_discord_message") as post_message:
            self.client.post(
                "/identification", data={"public_id": "1001"},
                follow_redirects=True,
            )
            self.client.post(
                "/identification", data={"public_id": "1001"},
                follow_redirects=True,
            )
            self.client.post("/visiteurs", follow_redirects=True)
        self.assertEqual(post_message.call_count, 3)
        messages = [call.args[1] for call in post_message.call_args_list]
        self.assertEqual(
            messages,
            [
                "🟢 Victor E. arrive.",
                "🔴 Victor E. part.",
                "🟡 Visiteur présent.",
            ],
        )
        self.assertTrue(
            all(call.args[2] == "Compteur test" for call in post_message.call_args_list)
        )

    def test_retention_warning_is_sent_once_before_each_deadline(self):
        fake_webhook = (
            "https://discord.com/api/webhooks/123456789012345678/"
            "retention_test_secret_ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        )
        self.app.config["DISCORD_SYNCHRONOUS"] = True
        self.login_admin()
        self.client.post(
            "/admin/reglages/notifications",
            data={
                "webhook_url": fake_webhook,
                "enabled": "1",
                "retention": "1",
                "bot_name": "Compteur",
                "arrival_message": "🟢 {name} arrive au fablab.",
                "departure_message": "🔴 {name} quitte le fablab.",
                "visitor_message": "🟡 Un visiteur est au fablab.",
                "retention_message": "🟠 {name} : {action} le {date}.",
            },
        )
        now = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)
        with self.database() as database:
            database.execute(
                """
                UPDATE users
                SET email = 'victor@example.org', phone = '0102030405',
                    created_at = ?
                WHERE public_id = '1001'
                """,
                (datetime(2024, 8, 28, 10, 0, tzinfo=timezone.utc).isoformat(),),
            )
            database.commit()

        with mock.patch("app.post_discord_message", return_value=None) as post_message:
            with self.app.app_context():
                from app import get_database, run_data_retention

                run_data_retention(get_database(), now=now, force=True)
                run_data_retention(get_database(), now=now, force=True)

        post_message.assert_called_once_with(
            fake_webhook,
            "🟠 Victor E. : effacement de l’e-mail et du téléphone le 28/08/2026.",
            "Compteur",
        )
        with self.database() as database:
            warning = database.execute(
                """
                SELECT warning_type, deadline FROM retention_warnings
                WHERE user_id = (SELECT id FROM users WHERE public_id = '1001')
                """
            ).fetchone()
        self.assertEqual(tuple(warning), ("contact", "2026-08-28"))


    def test_structured_service_fields_and_calendar_export(self):
        self.login_admin()
        response = self.client.post(
            "/admin/animations/nouveau",
            data={
                "service_type": "animation",
                "title": "Robotique familiale",
                "service_date": "2026-10-03",
                "start_time": "14:30",
                "end_time": "16:00",
                "minimum_age": "12",
                "description": "Découverte des robots et programmation en équipe.",
                "expected_participants": "10",
                "actual_participants": "8",
            },
            follow_redirects=True,
        )
        self.assertIn("enregistrement a été ajouté", response.get_data(as_text=True))
        with self.database() as database:
            service = database.execute(
                "SELECT * FROM fablab_services WHERE title = 'Robotique familiale'"
            ).fetchone()
        self.assertEqual(service["duration_minutes"], 90)
        self.assertEqual(service["minimum_age"], 12)
        self.assertIn("programmation", service["description"])
        calendar = self.client.get(
            f"/admin/animations/{service['id']}/calendrier.ics"
        )
        content = calendar.get_data(as_text=True)
        self.assertEqual(calendar.status_code, 200)
        self.assertIn("text/calendar", calendar.content_type)
        self.assertIn("BEGIN:VTIMEZONE", content)
        self.assertIn("TZID:Europe/Paris", content)
        self.assertIn("DTSTART;TZID=Europe/Paris:20261003T143000", content)
        self.assertIn("DTEND;TZID=Europe/Paris:20261003T160000", content)
        self.assertIn("SUMMARY:Animation : Robotique familiale", content)
        self.assertIn("Âge minimum : 12 ans", content)

    def test_editable_tariffs_are_snapshotted_in_new_quotes(self):
        self.login_admin()
        configured = self.client.post(
            "/admin/options/tarifs",
            data={
                "normal_hourly": "70", "normal_half_day": "140",
                "reduced_hourly": "35", "reduced_half_day": "70",
                "travel": "80", "consumable": "40",
                "rental_contract": "28", "rental_delivery": "32",
            },
            follow_redirects=True,
        )
        self.assertIn("tarifs des prochains devis", configured.get_data(as_text=True))
        self.client.post(
            "/admin/facturation/nouveau",
            data={
                "billing_type": "reservation", "quote_date": "2026-09-01",
                "client_contact": "Zoé Test", "client_structure": "Atelier Z",
                "address_line": "1 rue Test", "postal_code": "00000", "city": "Ville Fictive",
                "title": "Créneau sur mesure", "description": "Accompagnement.",
                "activity_date": "2026-09-15", "activity_start_time": "09:00",
                "activity_end_time": "11:00", "participants": "4",
                "rate_category": "normal", "rate_unit": "hourly", "rate_quantity": "2",
                "travel_quantity": "1", "consumable_mode": "billed",
                "consumable_quantity": "1",
            },
        )
        with self.database() as database:
            record = database.execute(
                "SELECT * FROM billing_records ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(record["rate_unit_cents"], 7000)
        self.assertEqual(record["travel_unit_cents"], 8000)
        self.assertEqual(record["consumable_unit_cents"], 4000)
        self.assertEqual(record["amount_cents"], 26000)
        self.assertEqual(record["activity_duration_minutes"], 120)

        calendar = self.client.get(
            f"/admin/facturation/{record['id']}/calendrier.ics"
        )
        calendar_text = calendar.get_data(as_text=True)
        self.assertEqual(calendar.status_code, 200)
        self.assertIn("SUMMARY:Créneau réservable : Créneau sur mesure", calendar_text)
        self.assertIn("DTSTART;TZID=Europe/Paris:20260915T090000", calendar_text)
        self.assertIn("Dossier : 2026.", calendar_text)

        # Les changements ultérieurs ne réécrivent pas le prix du dossier.
        self.client.post(
            "/admin/options/tarifs",
            data={
                "normal_hourly": "95", "normal_half_day": "190",
                "reduced_hourly": "47.50", "reduced_half_day": "95",
                "travel": "100", "consumable": "50",
                "rental_contract": "40", "rental_delivery": "45",
            },
        )
        self.client.post(
            f"/admin/facturation/{record['id']}/modifier",
            data={
                "billing_type": "reservation", "quote_number": record["quote_number"],
                "quote_date": "2026-09-01", "client_contact": "Zoé Test",
                "client_structure": "Atelier Z", "address_line": "1 rue Test",
                "postal_code": "00000", "city": "Ville Fictive",
                "title": "Créneau sur mesure", "description": "Accompagnement.",
                "activity_date": "2026-09-15", "activity_start_time": "09:00",
                "activity_end_time": "11:00", "participants": "4",
                "rate_category": "normal", "rate_unit": "hourly",
                "rate_quantity": "3", "travel_quantity": "1",
                "consumable_mode": "billed", "consumable_quantity": "1",
            },
        )
        with self.database() as database:
            updated = database.execute(
                "SELECT * FROM billing_records WHERE id = ?", (record["id"],)
            ).fetchone()
        self.assertEqual(updated["rate_unit_cents"], 7000)
        self.assertEqual(updated["travel_unit_cents"], 8000)
        self.assertEqual(updated["consumable_unit_cents"], 4000)
        self.assertEqual(updated["amount_cents"], 33000)

    def test_moderator_access_is_restricted_and_can_download_badges(self):
        login = self.login_admin("8642")
        self.assertIn("Accès modérateur activé", login.get_data(as_text=True))
        dashboard = self.client.get("/admin").get_data(as_text=True)
        self.assertIn(">Verrouiller</button>", dashboard)
        users_page = self.client.get("/admin/usagers").get_data(as_text=True)
        self.assertIn("Ajouter un usager", users_page)
        self.assertNotIn(">Modifier</a>", users_page)
        self.assertIn("QR Code :", users_page)
        self.assertIn("Badge :", users_page)
        self.assertIn(">Verrouiller</button>", users_page)
        with self.database() as database:
            victor_id = database.execute(
                "SELECT id FROM users WHERE public_id = '1001'"
            ).fetchone()[0]
        self.assertEqual(
            self.client.get(f"/admin/usagers/{victor_id}/qr.svg").status_code, 200
        )
        self.assertEqual(
            self.client.get(f"/admin/usagers/{victor_id}/badge.png").status_code, 200
        )
        statistics_page = self.client.get("/admin/frequentation/statistiques").get_data(as_text=True)
        self.assertNotIn('id="exports-title"', statistics_page)
        self.assertIn(">Statistiques</a>", statistics_page)
        self.assertNotIn(">Statistiques et exports</a>", statistics_page)
        self.assertNotIn("Durée cumulée des animations", statistics_page)
        self.assertNotIn("Durée cumulée des réservations", statistics_page)
        self.assertIn(">Verrouiller</button>", statistics_page)
        services_page = self.client.get("/admin/animations").get_data(as_text=True)
        self.assertIn("<th>Actions</th>", services_page)
        self.assertNotIn(">Modifier</a>", services_page)
        self.assertNotIn("Voir la facturation</a>", services_page)
        self.assertNotIn("Ajouter une animation</a>", services_page)
        self.assertIn(">Verrouiller</button>", services_page)
        self.assertEqual(self.client.get("/admin/animations/nouveau").status_code, 302)
        self.assertEqual(self.client.get("/admin/animations/1/modifier").status_code, 302)
        self.assertEqual(self.client.get("/admin/facturation").status_code, 302)
        self.assertEqual(self.client.get("/admin/reglages").status_code, 302)
        self.assertEqual(self.client.get("/admin/reglages/notifications").status_code, 302)
        self.assertEqual(self.client.get("/admin/exports/usagers.csv").status_code, 302)

    def test_rental_catalog_is_editable_and_used_by_new_quotes(self):
        self.login_admin()
        existing = {
            "prusa_mk39": ("Imprimante 3D Prusa MK3.9", "75", "900"),
            "dagoma_sigma": ("Imprimante 3D Dagoma SIGMA", "50", "600"),
            "formbox": ("Thermoformeuse FormBox", "50", "800"),
            "oculus_quest_1": ("Casque Oculus Quest 1", "25", "300"),
            "cameo_3": ("Découpeuse vinyle Cameo 3", "25", "300"),
            "mbot2": ("Robot mBot2 et kit Automotive", "25", "300"),
        }
        catalog_form = {}
        for key, (name, monthly, deposit) in existing.items():
            catalog_form.update({
                f"machine_active_{key}": "1",
                f"machine_name_{key}": name,
                f"machine_monthly_{key}": monthly,
                f"machine_deposit_{key}": deposit,
            })
        catalog_form.update({
            "new_machine_name": "Découpeuse plasma mobile",
            "new_machine_monthly": "88",
            "new_machine_deposit": "750",
        })
        saved = self.client.post(
            "/admin/options/catalogue-location",
            data=catalog_form,
            follow_redirects=True,
        )
        self.assertIn("catalogue de location a été enregistré", saved.get_data(as_text=True))
        with self.database() as database:
            machine = database.execute(
                "SELECT * FROM rental_catalog WHERE name = ?",
                ("Découpeuse plasma mobile",),
            ).fetchone()
        self.assertEqual(machine["monthly_cents"], 8800)
        self.assertEqual(machine["deposit_cents"], 75000)

        self.client.post(
            "/admin/facturation/nouveau",
            data={
                "billing_type": "rental", "quote_date": "2026-09-02",
                "client_contact": "Alex Démo", "client_structure": "Atelier mobile",
                "address_line": "2 rue Test", "postal_code": "00000",
                "city": "Ville Fictive", "title": "Location plasma",
                "description": "Location et formation de prise en main.",
                "activity_date": "2026-09-10", "activity_start_time": "14:00",
                "activity_end_time": "16:00", "rental_machine_key": machine["machine_key"],
                "rental_months": "2", "rental_end_date": "2026-11-10",
                "rental_delivery": "1",
            },
        )
        with self.database() as database:
            record = database.execute(
                "SELECT * FROM billing_records ORDER BY id DESC LIMIT 1"
            ).fetchone()
        self.assertEqual(record["rental_machine_name"], "Découpeuse plasma mobile")
        self.assertEqual(record["rental_monthly_cents"], 8800)
        self.assertEqual(record["rental_deposit_cents"], 75000)
        self.assertEqual(record["amount_cents"], 23100)

    def test_annual_activity_report_can_be_edited_and_exported(self):
        self.login_admin()
        saved = self.client.post(
            "/admin/rapport-activite/2026/modifier",
            data={
                "introduction": "Le Atelier Exemple accompagne les habitants du territoire.",
                "highlights": "Organisation du RepairLab et animations itinérantes.",
                "new_equipment": "Une nouvelle imprimante 3D.",
                "changes": "Déploiement du compteur de passage.",
                "partnerships": "Projet commun avec Made In Roch.",
                "additional_notes": "Perspectives pour 2027.",
            },
            follow_redirects=True,
        )
        self.assertIn("rapport d&#39;activité 2026 a été enregistré", saved.get_data(as_text=True))
        pdf = self.client.get("/admin/rapport-activite/2026.pdf")
        docx = self.client.get("/admin/rapport-activite/2026.docx")
        self.assertTrue(pdf.data.startswith(b"%PDF"))
        self.assertTrue(docx.data.startswith(b"PK"))
        export_prefix = datetime.now(ZoneInfo("Europe/Paris")).strftime("%m%d%Y")
        self.assertIn(
            f'{export_prefix}_RapportActivite2026.pdf',
            pdf.headers["Content-Disposition"],
        )
        self.assertIn(
            f'{export_prefix}_RapportActivite2026.docx',
            docx.headers["Content-Disposition"],
        )
        with zipfile.ZipFile(io.BytesIO(docx.data)) as archive:
            document_xml = archive.read("word/document.xml").decode("utf-8")
        self.assertIn("Rapport d’activité 2026", document_xml)
        self.assertIn("RepairLab", document_xml)
        self.assertNotIn("Généré le", document_xml)


    def test_v240_navigation_canonical_routes_and_legacy_redirects(self):
        self.login_admin()
        overview = self.client.get("/admin")
        self.assertEqual(overview.status_code, 200)
        overview_page = overview.get_data(as_text=True)
        self.assertEqual(overview_page.count('<a class="admin-tab'), 6)
        for label in ("Fréquentation", "Usagers", "Activités", "Facturation", "Réglages"):
            self.assertIn(f">{label}</a>", overview_page)
        for label in ("Aperçu", "Journée", "Statistiques", "Exports"):
            self.assertIn(f">{label}</a>", overview_page)
        self.assertIn("HISTORIQUE DES 30 IDENTIFICATIONS PRÉCÉDENTES", overview_page)
        self.assertNotIn("Historique récent", overview_page)

        canonical_routes = (
            "/admin/frequentation/journee",
            "/admin/frequentation/statistiques",
            "/admin/frequentation/exports",
            "/admin/animations",
            "/admin/reglages/affichage",
            "/admin/reglages/borne",
            "/admin/reglages/tarifs",
            "/admin/reglages/donnees",
            "/admin/reglages/notifications",
        )
        for route in canonical_routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)

        redirects = {
            "/admin/statistiques": "/admin/frequentation/statistiques",
            "/admin/activites": "/admin/animations",
            "/admin/activites/nouveau": "/admin/animations/nouveau",
            "/admin/reglages": "/admin/reglages/affichage",
            "/admin/sauvegarde": "/admin/reglages/donnees",
            "/admin/notifications": "/admin/reglages/notifications",
        }
        for old_route, canonical_path in redirects.items():
            with self.subTest(old_route=old_route):
                response = self.client.get(old_route)
                self.assertIn(response.status_code, (301, 302, 307, 308))
                self.assertIn(canonical_path, response.headers["Location"])

        settings_page = self.client.get("/admin/reglages/affichage").get_data(as_text=True)
        self.assertIn(">Affichage</a>", settings_page)
        tabs = re.search(r'<nav class="admin-subtabs settings-subtabs"[^>]*>(.*?)</nav>', settings_page, re.S).group(1)
        self.assertEqual(re.findall(r'>([^<>]+)</a>', tabs), [
            "Affichage", "Usagers", "Borne", "Notifications", "Tarifs", "Données", "Structure",
        ])
        self.assertIn('class="admin-subtab active" href="/admin/reglages/affichage"', tabs)
        self.assertIn('href="/admin/reglages">Réglages</a>', settings_page)
        self.assertIn("Thème de la page d’accueil", settings_page)
        self.assertIn(">Borne</a>", settings_page)
        self.assertIn(">Tarifs</a>", settings_page)
        self.assertIn(">Données</a>", settings_page)
        self.assertIn(">Notifications</a>", settings_page)
        schedule_settings = self.client.get(
            "/admin/reglages/borne"
        ).get_data(as_text=True)
        self.assertIn(
            'class="admin-subtab active" href="/admin/reglages/borne"',
            schedule_settings,
        )

        mounted = Client(create_deployment_application(self.app, "/stat"), Response)
        mounted.post("/stat/admin/connexion", data={"pin": "1379", "csrf_token": re.search(r'name="csrf_token" value="([^"]+)"', mounted.get("/stat/admin/connexion").get_data(as_text=True)).group(1)})
        self.assertEqual(
            mounted.get("/stat/admin/frequentation/journee?date=2026-09-15").status_code,
            200,
        )

    def test_settings_are_split_into_dedicated_views(self):
        self.login_admin()
        pages = {
            name: self.client.get(f"/admin/reglages/{name}").get_data(as_text=True)
            for name in ("affichage", "borne", "tarifs", "donnees", "structure", "notifications")
        }
        for page in pages.values():
            for label in (
                "Affichage",
                ">Borne</a>",
                ">Tarifs</a>",
                ">Données</a>",
                ">Structure</a>",
                "Notifications",
            ):
                self.assertIn(label, page)

        self.assertIn('name="home_theme"', pages["affichage"])
        self.assertIn('name="openlab_attendance_show_decimals"', pages["affichage"])
        self.assertNotIn("Tablette d’accueil", pages["affichage"])
        self.assertNotIn('name="wake_lock_start"', pages["affichage"])
        self.assertNotIn('name="normal_hourly"', pages["affichage"])

        self.assertIn('name="wake_lock_start"', pages["borne"])
        self.assertIn('name="openlab_attendance_tuesday_start"', pages["borne"])
        self.assertNotIn('name="home_theme"', pages["borne"])
        self.assertNotIn('name="contact_years"', pages["borne"])

        self.assertIn('name="normal_hourly"', pages["tarifs"])
        self.assertIn('name="machine_name_', pages["tarifs"])
        self.assertNotIn('name="wake_lock_start"', pages["tarifs"])

        self.assertIn('name="contact_years"', pages["donnees"])
        self.assertIn('name="automatic_backup_enabled"', pages["donnees"])
        self.assertNotIn('name="home_theme"', pages["donnees"])

        self.assertIn('name="logo_wordmark"', pages["structure"])
        self.assertIn('id="reservations"', pages["structure"])
        self.assertIn('action="/admin/reglages/structure/reservations"', pages["structure"])
        self.assertIn('class="admin-subtab active" href="/admin/reglages/structure"', pages["structure"])

        self.assertIn("Activer les notifications Discord", pages["notifications"])
        self.assertNotIn('name="home_theme"', pages["notifications"])

    def test_frequency_overview_merges_thirty_latest_identifications(self):
        with self.database() as database:
            user_id = database.execute(
                "SELECT id FROM users WHERE public_id = '1001'"
            ).fetchone()[0]
            base = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
            for index in range(35):
                check_in = base + timedelta(minutes=index)
                database.execute(
                    """
                    INSERT INTO sessions (
                        user_id, check_in, check_out, entry_method, exit_method
                    ) VALUES (?, ?, ?, ?, 'admin')
                    """,
                    (
                        user_id,
                        check_in.isoformat(),
                        (check_in + timedelta(minutes=20)).isoformat(),
                        f"overview-{index:02d}",
                    ),
                )
            database.executemany(
                "INSERT INTO visitors (created_at) VALUES (?)",
                [
                    ((base + timedelta(minutes=30)).isoformat(),),
                    ((base + timedelta(minutes=31)).isoformat(),),
                ],
            )
            database.commit()
        self.login_admin()
        page = self.client.get("/admin").get_data(as_text=True)
        for index in range(7, 35):
            self.assertIn(f"Overview {index:02d}", page)
        for index in range(7):
            self.assertNotIn(f"Overview {index:02d}", page)
        self.assertEqual(page.count("<strong>Visiteur</strong>"), 2)
        self.assertIn("HISTORIQUE DES 30 IDENTIFICATIONS PRÉCÉDENTES", page)
        self.assertNotIn("Historique récent", page)

    def test_moderator_can_change_only_the_home_theme(self):
        self.login_admin("8642")
        page = self.client.get("/admin/themes").get_data(as_text=True)
        self.assertIn("<h1>Thèmes</h1>", page)
        self.assertEqual(page.count('name="home_theme" type="radio"'), 8)
        self.assertNotIn('name="openlab_attendance_show_decimals"', page)
        self.assertNotIn('name="wake_lock_start"', page)
        self.assertNotIn('name="normal_hourly"', page)

        saved = self.client.post(
            "/admin/themes",
            data={"home_theme": "summer"},
            follow_redirects=True,
        ).get_data(as_text=True)
        self.assertIn("Les options ont été enregistrées", saved)
        self.assertIn('value="summer" checked', saved)
        self.assertIn("home-theme-summer", self.client.get("/").get_data(as_text=True))
        self.assertEqual(self.client.get("/admin/reglages/affichage").status_code, 302)
        self.assertEqual(self.client.get("/admin/facturation").status_code, 302)

    def test_day_view_corrections_update_data_and_create_audit_trail(self):
        self.login_admin()
        selected_day = "2026-09-15"
        with self.database() as database:
            users = database.execute(
                "SELECT id FROM users ORDER BY id LIMIT 2"
            ).fetchall()
        first_id, second_id = users[0]["id"], users[1]["id"]

        first = self.client.post(
            "/admin/frequentation/journee/sessions/ajouter",
            data={
                "date": selected_day,
                "user_id": str(first_id),
                "check_in_time": "10:00",
                "check_out_date": selected_day,
                "check_out_time": "11:30",
            },
            follow_redirects=True,
        )
        self.assertIn("session usager a été ajoutée", first.get_data(as_text=True))
        second = self.client.post(
            "/admin/frequentation/journee/sessions/ajouter",
            data={
                "date": selected_day,
                "user_id": str(second_id),
                "check_in_time": "10:30",
                "check_out_date": selected_day,
                "check_out_time": "11:00",
            },
            follow_redirects=True,
        )
        self.assertIn("session usager a été ajoutée", second.get_data(as_text=True))
        visitor = self.client.post(
            "/admin/frequentation/journee/visiteurs/ajouter",
            data={"date": selected_day, "time": "10:45"},
            follow_redirects=True,
        )
        visitor_page = visitor.get_data(as_text=True)
        self.assertIn("visiteur anonyme a été ajouté", visitor_page)
        self.assertIn("Pic simultané d’usagers", visitor_page)
        self.assertRegex(visitor_page, r"<strong>2</strong><span>Pic simultané d’usagers")

        with self.database() as database:
            before_overlap = database.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        overlap = self.client.post(
            "/admin/frequentation/journee/sessions/ajouter",
            data={
                "date": selected_day,
                "user_id": str(first_id),
                "check_in_time": "10:15",
                "check_out_date": selected_day,
                "check_out_time": "10:45",
            },
            follow_redirects=True,
        )
        self.assertIn("déjà une session", overlap.get_data(as_text=True))
        with self.database() as database:
            self.assertEqual(
                database.execute("SELECT COUNT(*) FROM sessions").fetchone()[0],
                before_overlap,
            )
            session_rows = database.execute(
                "SELECT id FROM sessions ORDER BY id"
            ).fetchall()
            visitor_id = database.execute("SELECT id FROM visitors").fetchone()[0]
            first_session_id = session_rows[0]["id"]
            second_session_id = session_rows[1]["id"]

        with self.app.app_context():
            from app import get_database, load_statistics
            before_update_statistics = load_statistics(get_database(), 2026)
            self.assertEqual(
                sum(item["duration_seconds"] or 0 for item in before_update_statistics["selected_sessions"]),
                7200,
            )

        updated = self.client.post(
            f"/admin/frequentation/journee/sessions/{first_session_id}/modifier",
            data={
                "return_date": selected_day,
                "date": selected_day,
                "check_in_time": "09:45",
                "check_out_date": selected_day,
                "check_out_time": "11:30",
            },
            follow_redirects=True,
        )
        self.assertIn("session a été corrigée", updated.get_data(as_text=True))
        with self.app.app_context():
            from app import get_database, load_statistics
            after_update_statistics = load_statistics(get_database(), 2026)
            self.assertEqual(
                sum(item["duration_seconds"] or 0 for item in after_update_statistics["selected_sessions"]),
                8100,
            )
        self.client.post(
            f"/admin/frequentation/journee/sessions/{second_session_id}/supprimer",
            data={"date": selected_day, "confirmation": "SUPPRIMER"},
        )
        self.client.post(
            f"/admin/frequentation/journee/visiteurs/{visitor_id}/supprimer",
            data={"date": selected_day, "confirmation": "SUPPRIMER"},
        )
        with self.database() as database:
            actions = database.execute(
                "SELECT action_type, record_type FROM attendance_corrections ORDER BY id"
            ).fetchall()
            self.assertEqual(len(actions), 6)
            self.assertEqual(
                [(row["action_type"], row["record_type"]) for row in actions],
                [
                    ("add", "session"), ("add", "session"), ("add", "visitor"),
                    ("update", "session"), ("delete", "session"), ("delete", "visitor"),
                ],
            )
            self.assertEqual(database.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        with self.app.app_context():
            from app import get_database, load_statistics
            after_delete_statistics = load_statistics(get_database(), 2026)
            self.assertEqual(
                sum(item["duration_seconds"] or 0 for item in after_delete_statistics["selected_sessions"]),
                6300,
            )

    def test_day_graph_reuses_quarter_hour_visitors_and_updates_after_corrections(self):
        self.login_admin()
        selected_day = "2026-09-15"
        with self.database() as database:
            user_ids = [
                row["id"]
                for row in database.execute(
                    "SELECT id FROM users ORDER BY id LIMIT 2"
                ).fetchall()
            ]

        for user_id, start, end in (
            (user_ids[0], "14:00", "14:30"),
            (user_ids[1], "14:15", "14:45"),
        ):
            self.client.post(
                "/admin/frequentation/journee/sessions/ajouter",
                data={
                    "date": selected_day,
                    "user_id": str(user_id),
                    "check_in_time": start,
                    "check_out_date": selected_day,
                    "check_out_time": end,
                },
            )
        self.client.post(
            "/admin/frequentation/journee/visiteurs/ajouter",
            data={"date": selected_day, "time": "14:20"},
        )

        page = self.client.get(
            f"/admin/frequentation/journee?date={selected_day}"
        ).get_data(as_text=True)
        self.assertIn("Fréquentation de la journée", page)
        self.assertIn("Nombre de personnes présentes par quart d’heure", page)
        self.assertIn("data-attendance-visitors-toggle checked", page)
        self.assertLess(
            page.index("Fréquentation de la journée"),
            page.index("Ajouter un passage"),
        )
        self.assertIn(
            'data-traffic-start="14:15" data-traffic-average="2.0" '
            'data-traffic-average-users="2.0" data-traffic-average-visitors="1.0" '
            'data-traffic-average-people="3.0"',
            page,
        )
        self.assertIn(">3</strong> personnes au pic", page)
        self.assertIn('class="traffic-visitor-count">1 vis.', page)

        with self.database() as database:
            second_session_id = database.execute(
                "SELECT id FROM sessions ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
            visitor_id = database.execute(
                "SELECT id FROM visitors ORDER BY id DESC LIMIT 1"
            ).fetchone()[0]
        updated = self.client.post(
            f"/admin/frequentation/journee/sessions/{second_session_id}/modifier",
            data={
                "return_date": selected_day,
                "date": selected_day,
                "check_in_time": "14:30",
                "check_out_date": selected_day,
                "check_out_time": "14:45",
            },
            follow_redirects=True,
        ).get_data(as_text=True)
        self.assertIn(
            'data-traffic-start="14:15" data-traffic-average="1.0" '
            'data-traffic-average-users="1.0" data-traffic-average-visitors="1.0" '
            'data-traffic-average-people="2.0"',
            updated,
        )
        self.assertIn(
            'data-traffic-start="14:30" data-traffic-average="1.0"',
            updated,
        )

        without_visitor = self.client.post(
            f"/admin/frequentation/journee/visiteurs/{visitor_id}/supprimer",
            data={"date": selected_day, "confirmation": "SUPPRIMER"},
            follow_redirects=True,
        ).get_data(as_text=True)
        self.assertIn(
            'data-traffic-start="14:15" data-traffic-average="1.0" '
            'data-traffic-average-users="1.0" data-traffic-average-visitors="0.0" '
            'data-traffic-average-people="1.0"',
            without_visitor,
        )

        after_delete = self.client.post(
            f"/admin/frequentation/journee/sessions/{second_session_id}/supprimer",
            data={"date": selected_day, "confirmation": "SUPPRIMER"},
            follow_redirects=True,
        ).get_data(as_text=True)
        self.assertIn(
            'data-traffic-start="14:30" data-traffic-average="0.0"',
            after_delete,
        )
        empty_day = self.client.get(
            "/admin/frequentation/journee?date=2026-09-16"
        ).get_data(as_text=True)
        self.assertIn("Aucune fréquentation enregistrée pour cette journée", empty_day)
        application_script = (Path(__file__).parents[1] / "static" / "app.js").read_text()
        self.assertIn(
            'querySelectorAll("[data-openlab-attendance]")', application_script
        )

    def test_attendance_color_scale_has_distinct_sober_levels(self):
        from app import (
            ATTENDANCE_PEAK_COLOR,
            attendance_graph_color,
            attendance_heat_color,
        )

        colors = [attendance_heat_color(value) for value in (0, 2.5, 5, 7.5, 10)]
        self.assertEqual(len(set(colors)), 5)
        self.assertTrue(all(re.fullmatch(r"#[0-9a-f]{6}", color) for color in colors))
        minimum = tuple(int(colors[0][index:index + 2], 16) for index in (1, 3, 5))
        maximum = tuple(int(colors[-1][index:index + 2], 16) for index in (1, 3, 5))
        self.assertGreater(sum(minimum), sum(maximum))
        self.assertGreater(maximum[0], maximum[1])
        self.assertEqual(attendance_graph_color(4, [1, 2, 3, 4]), ATTENDANCE_PEAK_COLOR)
        self.assertNotEqual(attendance_graph_color(3, [1, 2, 3, 4]), ATTENDANCE_PEAK_COLOR)
        self.assertNotEqual(attendance_graph_color(4, [4, 4, 4]), ATTENDANCE_PEAK_COLOR)
        self.assertEqual(attendance_graph_color(4, [1, 4, 4]), ATTENDANCE_PEAK_COLOR)

    def test_peak_time_card_uses_first_user_peak_and_matching_weather(self):
        selected_day = "2026-09-16"
        paris = ZoneInfo("Europe/Paris")
        with self.database() as database:
            user_ids = [
                row[0]
                for row in database.execute(
                    "SELECT id FROM users ORDER BY id LIMIT 2"
                ).fetchall()
            ]
            for start_hour, start_minute in ((9, 45), (11, 45)):
                start = datetime(
                    2026, 9, 16, start_hour, start_minute, tzinfo=paris
                ).astimezone(timezone.utc)
                end = start + timedelta(minutes=15)
                for user_id in user_ids:
                    database.execute(
                        """
                        INSERT INTO sessions (
                            user_id, check_in, check_out, entry_method, exit_method
                        ) VALUES (?, ?, ?, 'admin', 'admin')
                        """,
                        (user_id, start.isoformat(), end.isoformat()),
                    )
            for minute in (45, 46, 47):
                visitor_at = datetime(
                    2026, 9, 16, 11, minute, tzinfo=paris
                ).astimezone(timezone.utc)
                database.execute(
                    "INSERT INTO visitors (created_at) VALUES (?)",
                    (visitor_at.isoformat(),),
                )
            weather_quarter = datetime(
                2026, 9, 16, 9, 45, tzinfo=paris
            ).astimezone(timezone.utc)
            database.execute(
                """
                INSERT INTO weather_snapshots (
                    quarter_start, temperature_c, apparent_temperature_c,
                    weather_code, precipitation_mm, created_at
                ) VALUES (?, 14.2, 13.1, 61, 0.4, ?)
                """,
                (weather_quarter.isoformat(timespec="seconds"), datetime.now(timezone.utc).isoformat()),
            )
            database.commit()

        self.login_admin()
        page = self.client.get(
            f"/admin/frequentation/journee?date={selected_day}"
        ).get_data(as_text=True)
        summary = page.split('<section class="day-summary-grid"', 1)[1].split(
            "</section>", 1
        )[0]
        self.assertEqual(summary.count("<article"), 8)
        self.assertIn("<strong>2</strong><span>Pic simultané d’usagers", summary)
        self.assertIn("09h45–10h00", summary)
        self.assertIn("Horaire de pointe", summary)
        self.assertIn("14 °C · Pluie", summary)
        self.assertNotIn("11h45–12h00", summary)

        with self.database() as database:
            database.execute("DELETE FROM weather_snapshots")
            database.commit()
        without_weather = self.client.get(
            f"/admin/frequentation/journee?date={selected_day}"
        ).get_data(as_text=True)
        self.assertIn("Météo non enregistrée", without_weather)

        empty_page = self.client.get(
            "/admin/frequentation/journee?date=2026-09-17"
        ).get_data(as_text=True)
        empty_summary = empty_page.split(
            '<section class="day-summary-grid"', 1
        )[1].split("</section>", 1)[0]
        self.assertIn("<strong>—</strong><span>Horaire de pointe", empty_summary)
        self.assertNotIn("Météo non enregistrée", empty_summary)

    def test_weather_snapshots_are_quarterly_non_blocking_and_openlab_only(self):
        paris = ZoneInfo("Europe/Paris")
        weather = {
            "temperature": 18,
            "temperature_c": 17.6,
            "apparent_temperature_c": 16.9,
            "weather_code": 2,
            "precipitation_mm": 0.2,
            "description": "Éclaircies",
            "icon": "🌤️",
            "location": "Ville Fictive",
        }
        with self.database() as database, mock.patch(
            "app.get_current_weather", return_value=weather
        ) as weather_provider:
            tuesday = datetime(2026, 9, 22, 14, 7, tzinfo=paris)
            first = collect_openlab_weather_snapshot(database, self.app, tuesday)
            second = collect_openlab_weather_snapshot(
                database, self.app, tuesday + timedelta(minutes=3)
            )
            monday = datetime(2026, 9, 21, 14, 7, tzinfo=paris)
            outside = collect_openlab_weather_snapshot(database, self.app, monday)
            rows = database.execute(
                "SELECT * FROM weather_snapshots ORDER BY quarter_start"
            ).fetchall()

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertIsNone(outside)
        self.assertEqual(weather_provider.call_count, 1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["temperature_c"], 17.6)
        self.assertEqual(rows[0]["apparent_temperature_c"], 16.9)
        self.assertEqual(rows[0]["weather_code"], 2)
        self.assertEqual(rows[0]["precipitation_mm"], 0.2)

        with self.database() as database:
            with self.assertRaises(sqlite3.IntegrityError):
                database.execute(
                    """
                    INSERT INTO weather_snapshots (
                        quarter_start, temperature_c, weather_code, created_at
                    ) VALUES (?, 19, 1, ?)
                    """,
                    (rows[0]["quarter_start"], datetime.now(timezone.utc).isoformat()),
                )
            database.rollback()
            with mock.patch("app.get_current_weather", return_value=None):
                failed = collect_openlab_weather_snapshot(
                    database,
                    self.app,
                    datetime(2026, 9, 22, 14, 16, tzinfo=paris),
                )
            self.assertIsNone(failed)
            self.assertEqual(
                database.execute("SELECT COUNT(*) FROM weather_snapshots").fetchone()[0],
                1,
            )

    def test_day_corrections_validate_times_open_sessions_and_paris_timezone(self):
        self.login_admin()
        selected_day = "2026-09-15"
        with self.database() as database:
            user_id = database.execute(
                "SELECT id FROM users WHERE public_id = '1001'"
            ).fetchone()[0]

        backwards = self.client.post(
            "/admin/frequentation/journee/sessions/ajouter",
            data={
                "date": selected_day,
                "user_id": str(user_id),
                "check_in_time": "10:00",
                "check_out_date": selected_day,
                "check_out_time": "09:59",
            },
            follow_redirects=True,
        )
        self.assertIn("ne peut pas précéder", backwards.get_data(as_text=True))

        nonexistent_dst_time = self.client.post(
            "/admin/frequentation/journee/sessions/ajouter",
            data={
                "date": "2026-03-29",
                "user_id": str(user_id),
                "check_in_time": "02:30",
                "check_out_date": "2026-03-29",
                "check_out_time": "03:30",
            },
            follow_redirects=True,
        )
        self.assertIn("n&#39;existe pas dans le fuseau Europe/Paris", nonexistent_dst_time.get_data(as_text=True))

        created = self.client.post(
            "/admin/frequentation/journee/sessions/ajouter",
            data={
                "date": selected_day,
                "user_id": str(user_id),
                "check_in_time": "10:00",
                "check_out_date": selected_day,
                "check_out_time": "",
            },
            follow_redirects=True,
        )
        self.assertIn("session usager a été ajoutée", created.get_data(as_text=True))
        duplicate_open = self.client.post(
            "/admin/frequentation/journee/sessions/ajouter",
            data={
                "date": selected_day,
                "user_id": str(user_id),
                "check_in_time": "10:30",
                "check_out_date": selected_day,
                "check_out_time": "",
            },
            follow_redirects=True,
        )
        self.assertIn("déjà une session", duplicate_open.get_data(as_text=True))
        with self.database() as database:
            rows = database.execute(
                "SELECT check_in, check_out, entry_method FROM sessions"
            ).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["check_in"], "2026-09-15T08:00:00+00:00")
            self.assertIsNone(rows[0]["check_out"])
            self.assertEqual(rows[0]["entry_method"], "admin")
            self.assertEqual(
                database.execute("SELECT COUNT(*) FROM attendance_corrections").fetchone()[0],
                1,
            )

    def test_day_view_is_read_only_for_moderator_and_peak_excludes_visitors(self):
        selected_day = "2026-09-16"
        with self.database() as database:
            user_ids = [row[0] for row in database.execute(
                "SELECT id FROM users ORDER BY id LIMIT 2"
            ).fetchall()]
            for user_id, start, end in (
                (user_ids[0], "2026-09-16T08:00:00+00:00", "2026-09-16T09:30:00+00:00"),
                (user_ids[1], "2026-09-16T08:30:00+00:00", "2026-09-16T09:00:00+00:00"),
            ):
                database.execute(
                    "INSERT INTO sessions (user_id, check_in, check_out, entry_method, exit_method) VALUES (?, ?, ?, 'admin', 'admin')",
                    (user_id, start, end),
                )
            for minute in (35, 40, 45):
                database.execute(
                    "INSERT INTO visitors (created_at) VALUES (?)",
                    (f"2026-09-16T08:{minute}:00+00:00",),
                )
            database.commit()
        self.login_admin("8642")
        page = self.client.get(
            f"/admin/frequentation/journee?date={selected_day}"
        ).get_data(as_text=True)
        self.assertRegex(page, r"<strong>2</strong><span>Pic simultané d’usagers")
        self.assertRegex(page, r"<strong>3</strong><span>Visiteurs anonymes")
        self.assertNotIn("Ajouter un passage", page)
        self.assertNotIn("Dernières corrections administratives", page)
        with self.database() as database:
            before = database.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]
        denied = self.client.post(
            "/admin/frequentation/journee/visiteurs/ajouter",
            data={"date": selected_day, "time": "11:00"},
        )
        self.assertEqual(denied.status_code, 302)
        self.assertIn("/admin", denied.headers["Location"])
        with self.database() as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM visitors").fetchone()[0], before)

    def test_animations_reject_direct_paid_service_creation(self):
        self.login_admin()
        response = self.client.post(
            "/admin/animations/nouveau",
            data={
                "service_type": "reservation",
                "title": "Créneau forgé",
                "service_date": "2026-09-20",
                "start_time": "10:00",
                "end_time": "11:00",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("se créent depuis Facturation", response.get_data(as_text=True))
        with self.database() as database:
            self.assertEqual(
                database.execute(
                    "SELECT COUNT(*) FROM fablab_services WHERE service_type != 'animation'"
                ).fetchone()[0],
                0,
            )

    def test_moderator_sees_frequency_but_not_exports_or_settings(self):
        self.login_admin("8642")
        dashboard = self.client.get("/admin").get_data(as_text=True)
        self.assertEqual(dashboard.count('<a class="admin-tab'), 5)
        self.assertIn(">Fréquentation</a>", dashboard)
        self.assertIn(">Usagers</a>", dashboard)
        self.assertIn(">Activités</a>", dashboard)
        self.assertIn(">Thèmes</a>", dashboard)
        self.assertNotIn(">Facturation</a>", dashboard)
        self.assertNotIn(">Réglages</a>", dashboard)
        self.assertNotIn(">Exports</a>", dashboard)
        self.assertEqual(self.client.get("/admin/frequentation/statistiques").status_code, 200)
        for route in (
            "/admin/frequentation/exports",
            "/admin/reglages",
            "/admin/reglages/notifications",
        ):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 302)



    def test_v244_age_is_admin_only_and_never_stored(self):
        with self.database() as database:
            user_id = database.execute("SELECT id FROM users WHERE public_id = '1001'").fetchone()[0]
            database.execute("UPDATE users SET birth_year = 1990 WHERE id = ?", (user_id,))
        self.login_admin()
        page = self.client.get(f"/admin/usagers/{user_id}/modifier").get_data(as_text=True)
        year = datetime.now(ZoneInfo("Europe/Paris")).year
        self.assertIn(f"Âge en {year}", page)
        self.assertIn(f"{year - 1990} ans", page)
        with self.database() as database:
            database.execute("UPDATE users SET birth_year = NULL WHERE id = ?", (user_id,))
            columns = [row["name"] for row in database.execute("PRAGMA table_info(users)")]
        self.assertNotIn("age", columns)
        self.assertIn("Non renseigné", self.client.get(f"/admin/usagers/{user_id}/modifier").get_data(as_text=True))
        self.client.post("/admin/deconnexion")
        self.login_admin("8642")
        self.assertEqual(self.client.get(f"/admin/usagers/{user_id}/modifier").status_code, 302)
        self.assertNotIn("Âge en", self.client.get("/").get_data(as_text=True))

    def test_v244_first_name_normalization_on_create_and_edit(self):
        for source, expected in (("victor", "Victor"), ("VICTOR", "Victor"),
                                 ("jean-baptiste", "Jean-Baptiste"),
                                 ("  anne   sophie  ", "Anne Sophie"),
                                 ("léa", "Léa"), ("d'ARTAGNAN", "D'Artagnan")):
            self.assertEqual(normalize_first_name(source), expected)
        self.login_admin()
        self.client.post("/admin/usagers/nouveau", data={"public_id": "1006", "first_name": "  anne   sophie  ",
                                                        "last_name": "test", "active": "1", "birth_year": "1990",
                                                        "city": "Ville Fictive", "nationality": "France", "email": "anne@example.invalid",
                                                        "phone": "0611223344"})
        with self.database() as database:
            row = database.execute("SELECT id, first_name FROM users WHERE public_id = '1006'").fetchone()
        self.assertEqual(row["first_name"], "Anne Sophie")
        self.client.post(f"/admin/usagers/{row['id']}/modifier", data={"public_id": "1006", "first_name": "GUILLAUME-MARIE",
                                                                       "last_name": "test", "category": "user", "active": "1"})
        with self.database() as database:
            self.assertEqual(database.execute("SELECT first_name FROM users WHERE id = ?", (row["id"],)).fetchone()[0], "Guillaume-Marie")

    def test_v244_invalid_id_counts_only_complete_manual_codes(self):
        self.client.post("/identification", data={"public_id": "9999"})
        self.client.post("/identification", data={"public_id": "99"})
        self.client.post("/identification", data={"public_id": "9999", "identification_method": "qr"})
        self.client.get("/usagers")
        self.client.post("/visiteurs")
        with self.database() as database:
            rows = database.execute("SELECT event_type, details_json FROM security_events").fetchall()
        self.assertEqual([row["event_type"] for row in rows], ["invalid_user_id"])
        self.assertNotIn("9999", rows[0]["details_json"])

    def test_v244_sliding_window_and_success_do_not_reset_errors(self):
        self.client.post("/identification", data={"public_id": "9999"})
        for _ in range(3):
            self.client.post("/identification", data={"public_id": "9999"})
        self.client.post("/identification", data={"public_id": "1001"})
        self.client.post("/identification", data={"public_id": "9999"})
        with self.database() as database:
            counts = {row["event_type"]: row["n"] for row in database.execute(
                "SELECT event_type, COUNT(*) n FROM security_events GROUP BY event_type"
            )}
        self.assertEqual(counts["invalid_user_id"], 5)
        self.assertEqual(counts["invalid_id_alert"], 1)

    def test_v244_window_expiry_and_new_sequence(self):
        base = datetime.now(timezone.utc) - timedelta(minutes=20)
        with self.app.app_context():
            database = get_database()
            for index in range(4):
                record_invalid_user_id(database, base + timedelta(seconds=index))
            self.assertEqual(database.execute("SELECT COUNT(*) FROM security_events WHERE event_type='invalid_id_alert'").fetchone()[0], 0)
            for index in range(5):
                record_invalid_user_id(database, base + timedelta(minutes=6, seconds=index))
            self.assertEqual(database.execute("SELECT COUNT(*) FROM security_events WHERE event_type='invalid_id_alert'").fetchone()[0], 1)

    def test_v244_discord_alert_is_anonymous_configurable_and_not_spammed(self):
        self.app.config["DISCORD_SYNCHRONOUS"] = True
        with self.app.app_context(), mock.patch("app.read_discord_webhook", return_value="https://example.invalid/webhook"), \
                mock.patch("app.post_discord_message") as post:
            database = get_database()
            from app import write_setting
            write_setting(database, "discord_notifications_enabled", "1")
            write_setting(database, "invalid_id_threshold", "3")
            write_setting(database, "invalid_id_window_minutes", "2")
            database.commit()
            base = datetime.now(timezone.utc)
            for index in range(5):
                record_invalid_user_id(database, base + timedelta(seconds=index))
            self.assertEqual(post.call_count, 1)
            message = post.call_args.args[1]
            self.assertIn("3 tentatives", message)
            self.assertIn("2 minutes", message)
            self.assertNotIn("9999", message)
            self.assertNotIn("Victor", message)
            for index in range(3):
                record_invalid_user_id(database, base + timedelta(minutes=3, seconds=index))
            self.assertEqual(post.call_count, 2)
            write_setting(database, "discord_notify_invalid_ids", "0")
            database.commit()
            for index in range(3):
                record_invalid_user_id(database, base + timedelta(minutes=6, seconds=index))
            self.assertEqual(post.call_count, 2)

    def test_v244_optional_id_lock_is_server_side_and_other_paths_work(self):
        from app import write_setting
        with self.app.app_context():
            database = get_database()
            self.assertIsNone(current_id_lock(database))
            write_setting(database, "invalid_id_lock_enabled", "1")
            database.commit()
        for _ in range(5):
            self.client.post("/identification", data={"public_id": "9999"})
        locked = self.client.get("/identification").get_data(as_text=True)
        self.assertIn("temporairement indisponible", locked)
        self.assertNotIn('data-identifier-form', locked)
        denied = self.client.post("/identification", data={"public_id": "1001"}, follow_redirects=True)
        self.assertIn("temporairement indisponible", denied.get_data(as_text=True))
        with self.database() as database:
            before = database.execute("SELECT COUNT(*) FROM security_events WHERE event_type='invalid_user_id'").fetchone()[0]
        self.client.post("/identification", data={"public_id": "9999"})
        with self.database() as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM security_events WHERE event_type='invalid_user_id'").fetchone()[0], before)
        self.assertEqual(self.client.post("/identification", data={"public_id": "1001", "identification_method": "qr"}).status_code, 302)
        self.assertEqual(self.client.get("/usagers").status_code, 200)
        self.assertEqual(self.client.post("/visiteurs").status_code, 302)
        self.assertEqual(self.client.post("/usagers/1/depart-rapide").status_code, 302)
        self.assertEqual(self.client.get("/admin/connexion").status_code, 200)
        with self.app.app_context():
            database = get_database()
            self.assertIsNone(current_id_lock(database, datetime.now(timezone.utc) + timedelta(minutes=11)))

    def test_v244_duplicate_warning_is_overrideable_and_role_safe(self):
        self.login_admin("8642")
        form = {"public_id": "1006", "first_name": "  VICTOR ", "last_name": "exemple", "category": "user", "active": "1",
                "birth_year": "1990", "city": "Ville Fictive", "nationality": "France", "email": "new@example.invalid", "phone": "0611223344"}
        warning = self.client.post("/admin/usagers/nouveau", data=form).get_data(as_text=True)
        self.assertIn("Un usager similaire existe déjà", warning)
        self.assertIn("ID 1001", warning)
        self.assertIn("Créer quand même", warning)
        self.assertNotIn("victor@example", warning)
        self.assertNotIn("Âge en", warning)
        with self.database() as database:
            self.assertIsNone(database.execute("SELECT id FROM users WHERE public_id='1006'").fetchone())
        form["confirm_duplicates"] = "1"
        self.client.post("/admin/usagers/nouveau", data=form)
        with self.database() as database:
            self.assertEqual(database.execute("SELECT first_name FROM users WHERE public_id='1006'").fetchone()[0], "Victor")

    def test_v244_security_settings_and_role_limited_journal(self):
        self.login_admin()
        page = self.client.get("/admin/reglages/borne").get_data(as_text=True)
        self.assertIn("Sécurité de l’identification", page)
        self.assertIn('name="invalid_id_threshold"', page)
        saved = self.client.post("/admin/reglages/borne/enregistrer", data={
            "invalid_id_threshold": "7", "invalid_id_window_minutes": "8",
            "invalid_id_lock_enabled": "1", "invalid_id_lock_minutes": "12",
            "wake_lock_start": "09:00", "wake_lock_end": "17:00",
        }, follow_redirects=True).get_data(as_text=True)
        self.assertIn("Les options ont été enregistrées", saved)
        with self.database() as database:
            self.assertEqual(database.execute("SELECT value FROM app_settings WHERE key='invalid_id_threshold'").fetchone()[0], "7")
        self.assertIn("Alerte Discord en cas de tentatives", self.client.get("/admin/reglages/notifications").get_data(as_text=True))
        self.client.post("/admin/deconnexion")
        self.login_admin("8642")
        self.assertEqual(self.client.get("/admin/reglages/borne").status_code, 302)
        self.assertEqual(self.client.post("/admin/reglages/borne/enregistrer").status_code, 302)

    def test_v244_login_journal_has_roles_but_no_pin(self):
        self.client.post("/admin/connexion", data={"access_role": "admin", "pin": "0000", "csrf_token": self._login_token()})
        self.client.post("/admin/connexion", data={"access_role": "moderator", "pin": "0000", "csrf_token": self._login_token()})
        self.client.post("/admin/connexion", data={"access_role": "moderator", "pin": "8642", "csrf_token": self._login_token()})
        self.client.post("/admin/deconnexion")
        self.client.post("/admin/connexion", data={"access_role": "admin", "pin": "1379", "csrf_token": self._login_token()})
        with self.database() as database:
            rows = database.execute("SELECT event_type, details_json FROM security_events ORDER BY id").fetchall()
        self.assertEqual([row["event_type"] for row in rows], ["admin_login_failed", "moderator_login_failed", "moderator_login_success", "admin_login_success"])
        self.assertNotIn("0000", str([row["details_json"] for row in rows]))
        self.assertNotIn("1379", str([row["details_json"] for row in rows]))

    def test_v244_duplicate_email_and_phone_are_warnings_not_constraints(self):
        with self.database() as database:
            database.execute("UPDATE users SET email='Contact@Example.org', phone_country_code='+33', phone='06 10 10 10 10' WHERE public_id='1001'")
        self.login_admin()
        email_form = {"public_id": "1006", "first_name": "Autre", "last_name": "Personne", "email": "contact@example.org", "active": "1",
                      "birth_year": "1990", "city": "Ville Fictive", "nationality": "France", "phone": "0611223344"}
        self.assertIn("ID 1001", self.client.post("/admin/usagers/nouveau", data=email_form).get_data(as_text=True))
        phone_form = {"public_id": "1006", "first_name": "Autre", "last_name": "Personne", "phone": "0610101010", "phone_country_code": "+33", "active": "1",
                      "birth_year": "1990", "city": "Ville Fictive", "nationality": "France", "email": "other@example.invalid"}
        self.assertIn("ID 1001", self.client.post("/admin/usagers/nouveau", data=phone_form).get_data(as_text=True))
        clean_form = {"public_id": "1006", "first_name": "Nouvelle", "last_name": "Personne", "active": "1",
                      "birth_year": "1990", "city": "Ville Fictive", "nationality": "France", "email": "new@example.invalid", "phone": "0611223344"}
        self.assertIn("a été créé", self.client.post("/admin/usagers/nouveau", data=clean_form, follow_redirects=True).get_data(as_text=True))

    def test_v244_missing_webhook_and_disabled_alert_are_harmless(self):
        self.app.config["DISCORD_SYNCHRONOUS"] = True
        with self.app.app_context(), mock.patch("app.read_discord_webhook", return_value=None), \
                mock.patch("app.post_discord_message") as post:
            database = get_database()
            from app import write_setting
            write_setting(database, "discord_notifications_enabled", "1")
            database.commit()
            for _ in range(5):
                record_invalid_user_id(database)
            post.assert_not_called()
            self.assertEqual(database.execute("SELECT COUNT(*) FROM security_events WHERE event_type='invalid_id_alert'").fetchone()[0], 1)

    def test_v244_security_retention_keeps_only_thirty_days(self):
        from app import log_security_event
        with self.app.app_context():
            database = get_database()
            old = datetime.now(timezone.utc) - timedelta(days=31)
            log_security_event(database, "admin_login_failed", now=old)
            log_security_event(database, "admin_login_success")
            database.commit()
            self.assertEqual([row[0] for row in database.execute("SELECT event_type FROM security_events")], ["admin_login_success"])

    def test_v244_expired_lock_restores_public_id_form(self):
        from app import write_setting
        with self.app.app_context():
            database = get_database()
            write_setting(database, "invalid_id_lock_enabled", "1")
            database.execute("INSERT INTO security_events (event_type, created_at, details_json) VALUES ('id_lock_started', ?, ?)",
                             ((datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat(timespec="seconds"),
                              json.dumps({"until": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")})))
            database.commit()
        self.assertIn('data-identifier-form', self.client.get("/identification").get_data(as_text=True))
        self.assertEqual(self.client.post("/identification", data={"public_id": "1001"}).status_code, 302)

    def test_v250_private_pin_files_and_required_new_user_fields(self):
        from pin_security import credential_path, check_pin
        self.assertTrue(check_pin(self.database_path, "admin", "1379"))
        self.assertTrue(check_pin(self.database_path, "moderator", "8642"))
        self.assertNotIn("1379", credential_path(self.database_path, "admin").read_text())
        with self.database() as database:
            self.assertIsNone(database.execute(
                "SELECT value FROM app_settings WHERE key = 'moderator_pin'"
            ).fetchone())
        self.login_admin("8642")
        invalid = self.client.post("/admin/usagers/nouveau", data={
            "public_id": "1006", "first_name": "Nouvelle", "last_name": "Personne", "active": "1"
        }).get_data(as_text=True)
        self.assertIn("année de naissance", invalid)
        with self.database() as database:
            self.assertIsNone(database.execute("SELECT 1 FROM users WHERE public_id='1006'").fetchone())

    def test_v250_animation_publication_and_booking_actions_remain_local(self):
        from app import write_setting
        from reservations_sync import import_events
        with self.app.app_context():
            database = get_database()
            write_setting(database, "module_public_reservations", "1")
            database.commit()
        self.login_admin()
        page = self.client.get("/admin/animations/nouveau").get_data(as_text=True)
        self.assertIn("Publier cette animation", page)
        self.client.post("/admin/animations/nouveau", data={
            "title": "Atelier test", "service_date": "2026-11-12",
            "start_time": "14:00", "end_time": "15:00", "minimum_age": "10",
            "expected_participants": "8", "actual_participants": "0",
            "online_enabled": "1", "online_environment": "test", "online_audience": "all",
            "capacity": "8", "close_minutes": "60", "accompaniment_under_age": "15",
            "waitlist_enabled": "1", "reminder_one_hours": "24", "reminder_two_hours": "0",
        })
        with self.database() as database:
            service_id = database.execute("SELECT id FROM fablab_services WHERE title='Atelier test'").fetchone()[0]
            self.assertEqual(database.execute(
                "SELECT enabled FROM animation_reservation_config WHERE service_id=?", (service_id,)
            ).fetchone()[0], 1)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM reservation_outbox").fetchone()[0], 1)
            publication = json.loads(database.execute(
                "SELECT payload_json FROM reservation_outbox ORDER BY id DESC LIMIT 1"
            ).fetchone()[0])
            self.assertEqual(publication["animation"]["privacy_policy_url"],
                             "https://example.invalid/privacy")
        changed = self.client.post("/admin/reglages/structure", data={
            "csrf_token": re.search(r'name="csrf_token" value="([^"]+)"', self.client.get('/admin/reglages/structure').get_data(as_text=True)).group(1),
            "name": "Atelier Exemple", "short_name": "Atelier Exemple",
            "timezone": "Europe/Paris",
            "privacy_policy_url": "https://example.invalid/gestion-des-donnees/",
            **{f"module_{module}": "1" for module in (
                "frequency", "users", "activities", "public_reservations",
                "booking_slots", "rentals", "billing", "weather", "discord",
            )},
        })
        self.assertEqual(changed.status_code, 302)
        with self.database() as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM reservation_outbox").fetchone()[0], 2)
            changed_publication = json.loads(database.execute(
                "SELECT payload_json FROM reservation_outbox ORDER BY id DESC LIMIT 1"
            ).fetchone()[0])
            self.assertEqual(changed_publication["animation"]["privacy_policy_url"],
                             "https://example.invalid/gestion-des-donnees/")
        with self.app.app_context():
            database = get_database()
            event = {"id": "1", "booking": {"uuid": "00000000-0000-4000-8000-000000000001",
                "service_id": service_id, "environment": "test", "first_name": "Ana", "last_name": "TEST",
                "birth_year": 1999, "email": "ana@example.invalid", "phone": "+33600000000",
                "status": "confirmed", "link_status": "visitor", "source": "online",
                "updated_at": "2026-11-01T10:00:00+00:00", "created_at": "2026-11-01T10:00:00+00:00"}}
            self.assertEqual(import_events(database, "test", [event]), 1)
            self.assertEqual(import_events(database, "test", [event]), 0)
            database.commit()
        self.client.post("/admin/deconnexion")
        self.login_admin("8642")
        booking_page = self.client.get(f"/admin/animations/{service_id}/inscriptions").get_data(as_text=True)
        self.assertIn("Ana TEST", booking_page)
        self.assertIn("Exporter les inscriptions CSV", booking_page)
        token = re.search(r'name="csrf_token" value="([^"]+)"', booking_page).group(1)
        response = self.client.post(
            f"/admin/animations/{service_id}/inscriptions/00000000-0000-4000-8000-000000000001/action",
            data={"csrf_token": token, "action": "present"}, follow_redirects=True,
        )
        self.assertIn("Inscription mise à jour", response.get_data(as_text=True))
        with self.database() as database:
            self.assertEqual(database.execute(
                "SELECT actual_participants FROM fablab_services WHERE id=?", (service_id,)
            ).fetchone()[0], 1)
            self.assertEqual(database.execute(
                "SELECT command_type FROM reservation_outbox ORDER BY id DESC LIMIT 1"
            ).fetchone()[0], "booking")
        self.assertEqual(self.client.get(f"/admin/animations/{service_id}/inscriptions.csv").status_code, 200)
        self.assertEqual(self.client.get("/admin/reglages/reservations").status_code, 302)

    def test_v250_sync_has_no_network_without_explicit_site_configuration(self):
        from reservations_sync import (WordPressClient, build_directory,
                                       contact_fingerprint, normalize_phone,
                                       run_sync_cycle, signed_headers)
        import hashlib, hmac
        body = b'{"environment":"test"}'
        headers = signed_headers(b"fictional-secret", "POST", "/openfablab/v1/heartbeat", body,
                                 timestamp=100, nonce="nonce-for-test-only-123456")
        canonical = f"100\nnonce-for-test-only-123456\nPOST\n/openfablab/v1/heartbeat\n{hashlib.sha256(body).hexdigest()}"
        self.assertEqual(headers["X-OpenFabLab-Signature"],
                         hmac.new(b"fictional-secret", canonical.encode(), hashlib.sha256).hexdigest())
        with self.app.app_context(), mock.patch("reservations_sync.urllib.request.urlopen") as transport:
            database = get_database()
            self.assertFalse(run_sync_cycle(database, self.database_path, "")["configured"])
            self.assertTrue(build_directory(database, b"fictional-secret"))
            transport.assert_not_called()
        for address in ("http://example.invalid", "https://user@example.invalid",
                        "https://example.invalid/?secret=hidden",
                        "https://example.invalid/#fragment"):
            with self.assertRaises(ValueError):
                WordPressClient(address, b"fictional-secret")
        self.assertEqual(WordPressClient("https://example.invalid/wordpress", b"fictional-secret").site_url,
                         "https://example.invalid/wordpress")
        self.assertEqual(normalize_phone("+33", "06 12 34 56 78"), "+33612345678")
        self.assertEqual(contact_fingerprint(b"fictional-secret", "phone", "+33612345678"),
                         contact_fingerprint(b"fictional-secret", "phone", normalize_phone("0033", "06 12 34 56 78")))

    def test_v250_structure_and_reservations_settings_are_admin_only(self):
        self.login_admin()
        self.assertIn("Structure et modules", self.client.get("/admin/reglages/structure").get_data(as_text=True))
        self.assertIn("Réservations publiques", self.client.get("/admin/reglages/structure").get_data(as_text=True))
        self.assertEqual(self.client.get("/admin/reglages/reservations").headers["Location"],
                         "/admin/reglages/structure#reservations")
        self.client.post("/admin/deconnexion")
        self.login_admin("8642")
        self.assertEqual(self.client.get("/admin/reglages/structure").status_code, 302)
        self.assertEqual(self.client.get("/admin/reglages/reservations").status_code, 302)

    def test_v250_local_server_starts_worker(self):
        from app import run_local_server
        with mock.patch("app.start_local_reservation_sync_worker") as start, mock.patch.object(self.app, "run") as serve:
            run_local_server(self.app, 5011)
        start.assert_called_once_with(self.app)
        serve.assert_called_once_with(host="0.0.0.0", port=5011, debug=False)

    def test_v250_local_server_does_not_duplicate_enabled_scheduler(self):
        from app import run_local_server
        self.app.config["AUTO_CLOSURE_WORKER"] = True
        with mock.patch("app.start_local_reservation_sync_worker") as start, mock.patch.object(self.app, "run") as serve:
            run_local_server(self.app, 5011)
        start.assert_not_called()
        serve.assert_called_once_with(host="0.0.0.0", port=5011, debug=False)

    def test_v250_local_worker_is_started_once_per_application(self):
        from app import start_local_reservation_sync_worker
        with mock.patch("app.threading.Thread") as thread:
            start_local_reservation_sync_worker(self.app)
            start_local_reservation_sync_worker(self.app)
        thread.assert_called_once()
        thread.return_value.start.assert_called_once()

    def test_v250_local_worker_success_interval_and_network_error(self):
        import urllib.error
        from app import start_local_reservation_sync_worker, write_setting
        from reservations_sync import save_sync_secret

        class StopWorker(BaseException):
            pass

        with self.app.app_context():
            database = get_database()
            write_setting(database, "module_public_reservations", "1")
            write_setting(database, "reservation_wordpress_url", "https://example.invalid")
            write_setting(database, "reservation_sync_interval_minutes", "5")
            # Conserver la couverture du worker historique, réservé aux schémas antérieurs.
            database.execute("PRAGMA user_version=15")
            database.commit()
        save_sync_secret(self.database_path, "fictional-secret-" + "x" * 48)
        with mock.patch("app.threading.Thread") as thread:
            start_local_reservation_sync_worker(self.app)
        worker = thread.call_args.kwargs["target"]
        with mock.patch("app.run_sync_cycle", return_value={"configured": True, "imported": 0}) as sync, \
                mock.patch("app.notify_sync_events") as notifications, \
                mock.patch("app.time.sleep", side_effect=StopWorker):
            with self.assertRaises(StopWorker):
                worker()
            sync.assert_called_once()
            notifications.assert_called_once()
            with self.assertRaises(StopWorker):
                worker()
            sync.assert_called_once()  # La tentative précédente est trop récente.

            with self.app.app_context():
                database = get_database()
                write_setting(database, "reservation_sync_last_attempt", "")
                database.commit()
            sync.side_effect = urllib.error.URLError("offline")
            with mock.patch.object(self.app.logger, "warning"):
                with self.assertRaises(StopWorker):
                    worker()
            self.assertEqual(sync.call_count, 2)
        with self.database() as database:
            self.assertEqual(database.execute(
                "SELECT last_error FROM reservation_sync_state WHERE environment='test'"
            ).fetchone()[0], "Connexion HTTPS indisponible")
            self.assertEqual(database.execute(
                "SELECT last_error FROM reservation_sync_state WHERE environment='production'"
            ).fetchone()[0], "Connexion HTTPS indisponible")

    def test_v250_worker_does_not_send_when_module_disabled(self):
        from app import start_local_reservation_sync_worker
        class StopWorker(BaseException):
            pass
        with mock.patch("app.threading.Thread") as thread:
            start_local_reservation_sync_worker(self.app)
        with mock.patch("app.run_sync_cycle") as sync, mock.patch("app.time.sleep", side_effect=StopWorker):
            with self.assertRaises(StopWorker):
                thread.call_args.kwargs["target"]()
            sync.assert_not_called()

    def test_v271_reservation_sync_default_ninety_seconds_new_and_v244(self):
        with tempfile.TemporaryDirectory(prefix="openfablab_sync_default_") as directory:
            path = str(Path(directory) / "openfablab.db")
            config = {"TESTING": True, "DATABASE": path, "SEED_DEMO_USERS": False,
                      "WEATHER_ENABLED": False}
            create_app(config)
            with sqlite3.connect(path) as database:
                self.assertEqual(database.execute(
                    "SELECT value FROM app_settings WHERE key='reservation_sync_interval_minutes'"
                ).fetchone()[0], "1.5")
                # Une V2.4.4 ne possède pas encore ce réglage de réservation.
                database.execute("DELETE FROM app_settings WHERE key='reservation_sync_interval_minutes'")
                database.execute("PRAGMA user_version = 10")
                before = database.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]
            create_app(config)
            with sqlite3.connect(path) as database:
                self.assertEqual(database.execute(
                    "SELECT value FROM app_settings WHERE key='reservation_sync_interval_minutes'"
                ).fetchone()[0], "1.5")
                self.assertEqual(database.execute("SELECT COUNT(*) FROM visitors").fetchone()[0], before)
                self.assertEqual(database.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(database.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_v250_reservation_sync_preserves_explicit_interval(self):
        from app import initialize_database, read_setting, write_setting
        with self.app.app_context():
            database = get_database()
            for interval in ("5", "17"):
                with self.subTest(interval=interval):
                    write_setting(database, "reservation_sync_interval_minutes", interval)
                    database.commit()
                    initialize_database()
                    self.assertEqual(read_setting(database, "reservation_sync_interval_minutes"), interval)
        self.login_admin()
        page = self.client.get("/admin/reglages/structure").get_data(as_text=True)
        self.assertRegex(page, r'name="sync_interval_minutes"[^>]*value="17"')

    def test_v271_local_worker_respects_ninety_second_default_and_light_poll(self):
        from app import start_local_reservation_sync_worker, write_setting
        from reservations_sync import save_sync_secret
        class StopWorker(BaseException):
            pass
        now = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
        class FixedDateTime(datetime):
            current = None
            @classmethod
            def now(cls, tz=None):
                return cls.current
        FixedDateTime.current = now
        with self.app.app_context():
            database = get_database()
            write_setting(database, "module_public_reservations", "1")
            write_setting(database, "reservation_wordpress_url", "https://example.invalid")
            write_setting(database, "reservation_sync_last_attempt", (now - timedelta(seconds=89)).isoformat())
            database.execute("PRAGMA user_version=15")
            database.commit()
        save_sync_secret(self.database_path, "fictional-secret-" + "x" * 48)
        with mock.patch("app.threading.Thread") as thread:
            start_local_reservation_sync_worker(self.app)
        worker = thread.call_args.kwargs["target"]
        with mock.patch("app.datetime", FixedDateTime), \
                mock.patch("app.run_sync_cycle", return_value={"configured": True, "imported": 0}) as sync, \
                mock.patch("app.notify_sync_events"), \
                mock.patch("app.time.sleep", side_effect=StopWorker) as sleep:
            with self.assertRaises(StopWorker):
                worker()
            sync.assert_not_called()
            sleep.assert_called_with(30)
            FixedDateTime.current = now + timedelta(seconds=1)
            with self.assertRaises(StopWorker):
                worker()
            sync.assert_called_once()
            sleep.assert_called_with(30)

    def test_v250_new_animation_defaults_to_normal_without_reclassifying_existing_test(self):
        from app import write_setting
        self.login_admin()
        with self.app.app_context():
            database = get_database()
            write_setting(database, "module_public_reservations", "1")
            database.commit()
        page = self.client.get("/admin/animations/nouveau").get_data(as_text=True)
        self.assertRegex(page, r'<option value="production"\s+selected[^>]*>Normal</option>')
        self.assertIn('>Test</option>', page)
        self.assertNotIn('>Production</option>', page)
        values = {"title": "Défaut Normal", "service_date": "2026-11-12", "start_time": "14:00",
                  "end_time": "15:00", "minimum_age": "10", "expected_participants": "5",
                  "actual_participants": "", "online_enabled": "1", "capacity": "5"}
        self.assertEqual(self.client.post("/admin/animations/nouveau", data=values).status_code, 302)
        with self.database() as database:
            row = database.execute("SELECT service_id, environment FROM animation_reservation_config").fetchone()
            self.assertEqual(row["environment"], "production")
            self.assertEqual(database.execute("SELECT environment FROM reservation_outbox").fetchone()[0], "production")
            database.execute("UPDATE animation_reservation_config SET environment='test' WHERE service_id=?", (row["service_id"],))
        edit_path = f"/admin/animations/{row['service_id']}/modifier"
        self.assertRegex(self.client.get(edit_path).get_data(as_text=True), r'<option value="test"\s+selected[^>]*>Test</option>')
        self.assertEqual(self.client.post(edit_path, data=values).status_code, 302)
        with self.database() as database:
            self.assertEqual(database.execute("SELECT environment FROM animation_reservation_config").fetchone()[0], "test")
        settings = self.client.get("/admin/reglages/structure").get_data(as_text=True)
        self.assertIn('<strong>Normal</strong>', settings)
        self.assertIn('<strong>Test</strong>', settings)
        self.assertNotIn('<strong>Production</strong>', settings)

    def test_v250_private_directory_prefill_includes_only_active_users(self):
        from reservations_sync import build_directory, contact_fingerprint, normalize_phone
        with self.database() as database:
            database.execute("UPDATE users SET active=0 WHERE public_id='1002'")
            original = dict(database.execute("SELECT * FROM users WHERE public_id='1001'").fetchone())
            directory = build_directory(database, b"fictional-test-secret")
            self.assertNotIn("1002", [user["public_id"] for user in directory])
            user = next(user for user in directory if user["public_id"] == "1001")
            for key in ("first_name", "last_name", "birth_year", "category"):
                self.assertEqual(user[key], original[key])
            self.assertEqual(user["email_hmac"], contact_fingerprint(b"fictional-test-secret", "email", user["email"]))
            self.assertEqual(user["phone"], normalize_phone(original["phone_country_code"], original["phone"]))
            self.assertEqual(user["phone_hmac"], contact_fingerprint(b"fictional-test-secret", "phone", user["phone"]))
            self.assertEqual(dict(database.execute("SELECT * FROM users WHERE public_id='1001'").fetchone()), original)

    def test_v250_sync_failure_does_not_overwrite_other_environment_success(self):
        from reservations_sync import run_sync_cycle, save_sync_secret
        save_sync_secret(self.database_path, "fictional-secret-" + "x" * 48)
        class Client:
            def post(self, route, payload):
                if payload["environment"] == "production":
                    raise OSError("offline details must never appear")
                return {"ok": True, "protocol_version":4, "relay_revision":3, "outbound_actions_v1":True, "actions":[]}
        with self.database() as database:
            result = run_sync_cycle(database, self.database_path, "https://example.invalid", client=Client())
            self.assertEqual([r['environment'] for r in result['errors']], ['production'])
            self.assertNotIn('offline details',str(result))
            test = database.execute("SELECT * FROM reservation_sync_state WHERE environment='test'").fetchone()
            normal = database.execute("SELECT * FROM reservation_sync_state WHERE environment='production'").fetchone()
            self.assertIsNotNone(test["last_success_at"])
            self.assertIsNone(test["last_error"])
            self.assertIsNone(normal["last_success_at"])
            self.assertIn('Connexion sortante non vérifiée', normal['last_error'])

    def test_v250_online_reservation_edits_do_not_change_master_user(self):
        from reservations_sync import import_events
        service_id, _token = self._animation_booking_fixture()
        with self.database() as database:
            original = dict(database.execute("SELECT * FROM users WHERE public_id='1001'").fetchone())
            booking = {"uuid": "00000000-0000-4000-8000-000000000999", "service_id": service_id,
                       "environment": "test", "first_name": "Réservation seulement", "last_name": "AUTRE",
                       "birth_year": 1990, "email": "changed@example.invalid", "phone": "+33611111111",
                       "public_id": "1001", "status": "confirmed", "link_status": "matched", "source": "online",
                       "created_at": "2026-09-29T12:00:00+00:00", "updated_at": "2026-09-29T12:00:00+00:00"}
            self.assertEqual(import_events(database, "test", [{"id": "999", "type": "reservation_confirmed", "booking": booking}]), 1)
            self.assertEqual(dict(database.execute("SELECT * FROM users WHERE public_id='1001'").fetchone()), original)
            self.assertEqual(database.execute("SELECT email FROM animation_bookings").fetchone()[0], "changed@example.invalid")

    def test_v250_animation_walkin_count_empty_zero_and_negative_rejected(self):
        from app import write_setting
        with self.app.app_context():
            database = get_database()
            write_setting(database, "module_public_reservations", "1")
            database.commit()
        self.login_admin()
        values = {"title": "Atelier zéro", "service_date": "2026-11-12",
                  "start_time": "14:00", "end_time": "15:00", "minimum_age": "10",
                  "expected_participants": "5", "actual_participants": "",
                  "online_enabled": "1", "online_environment": "test", "capacity": "5"}
        self.assertEqual(self.client.post("/admin/animations/nouveau", data=values).status_code, 302)
        with self.database() as database:
            row = database.execute("SELECT id, actual_participants FROM fablab_services WHERE title='Atelier zéro'").fetchone()
            self.assertEqual(row["actual_participants"], 0)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM reservation_outbox WHERE environment='test'").fetchone()[0], 1)
        values["actual_participants"] = "0"
        self.assertEqual(self.client.post(f"/admin/animations/{row['id']}/modifier", data=values).status_code, 302)
        values["actual_participants"] = "-1"
        self.assertEqual(self.client.post(f"/admin/animations/{row['id']}/modifier", data=values).status_code, 400)
        with self.database() as database:
            self.assertEqual(database.execute("SELECT actual_participants FROM fablab_services WHERE id=?", (row["id"],)).fetchone()[0], 0)

    def test_v250_manual_sync_uses_normal_and_test_without_extra_activation(self):
        from app import write_setting
        from reservations_sync import save_sync_secret
        self.login_admin()
        with self.app.app_context():
            database = get_database()
            write_setting(database, "module_public_reservations", "1")
            write_setting(database, "reservation_wordpress_url", "https://example.invalid")
            database.commit()
        save_sync_secret(self.database_path, "fictional-secret-" + "x" * 48)
        page = self.client.get("/admin/reglages/structure").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        with mock.patch("outbound_sync.OutboundClient") as client_class:
            client_class.return_value.post.return_value = {"ok": True, "protocol_version":4, "relay_revision":3, "outbound_actions_v1":True, "actions":[]}
            response = self.client.post("/admin/reglages/structure/synchroniser",
                                        data={"csrf_token": token}, follow_redirects=True)
        self.assertIn("Synchronisation réussie", response.get_data(as_text=True))
        calls = client_class.return_value.post.call_args_list
        self.assertTrue(calls)
        self.assertEqual({call.args[1]["environment"] for call in calls}, {"test", "production"})
        with self.database() as database:
            self.assertIsNotNone(database.execute(
                "SELECT last_attempt_at FROM reservation_sync_state WHERE environment='test'"
            ).fetchone()[0])
            self.assertIsNotNone(database.execute(
                "SELECT last_attempt_at FROM reservation_sync_state WHERE environment='production'"
            ).fetchone()[0])
        import urllib.error
        with mock.patch("outbound_sync.OutboundClient") as failing_client:
            failing_client.return_value.post.side_effect = urllib.error.HTTPError(
                "https://example.invalid", 403, "refused", {}, None
            )
            failed = self.client.post("/admin/reglages/structure/synchroniser",
                                      data={"csrf_token": token}, follow_redirects=True)
        self.assertIn("Synchronisation impossible", failed.get_data(as_text=True))
        self.assertIn("Connexion sortante non vérifiée", failed.get_data(as_text=True))
        with self.database() as database:
            self.assertEqual(database.execute(
                "SELECT last_error FROM reservation_sync_state WHERE environment='test'"
            ).fetchone()[0], "Connexion sortante non vérifiée. Vérifiez les versions, HTTPS et le secret partagé.")
        self.client.post("/admin/deconnexion")
        self.login_admin("8642")
        self.assertEqual(self.client.post("/admin/reglages/structure/synchroniser",
                                          data={"csrf_token": token}).status_code, 302)

    def test_v250_walkin_prefill_is_admin_only_and_read_only(self):
        from app import write_setting
        self.login_admin()
        with self.app.app_context():
            database = get_database()
            write_setting(database, "module_public_reservations", "1")
            database.execute("INSERT INTO fablab_services(service_type,title,service_date,start_time,end_time,"
                             "duration_minutes,minimum_age,created_at,updated_at) VALUES"
                             "('animation','Préremplissage','2026-11-12','14:00','15:00',60,10,'2026-09-29','2026-09-29')")
            service_id = database.execute("SELECT last_insert_rowid()").fetchone()[0]
            database.execute("INSERT INTO animation_reservation_config(service_id,enabled,environment,capacity,updated_at) "
                             "VALUES (?,1,'test',5,'2026-09-29')", (service_id,))
            database.commit()
        path = f"/admin/animations/{service_id}/inscriptions/usager/1001"
        with self.database() as database:
            original_name = database.execute("SELECT first_name FROM users WHERE public_id='1001'").fetchone()[0]
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["first_name"], original_name)
        self.assertIn("birth_year", response.json)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        with self.database() as database:
            self.assertEqual(database.execute("SELECT first_name FROM users WHERE public_id='1001'").fetchone()[0], original_name)
        self.client.post("/admin/deconnexion")
        self.login_admin("8642")
        self.assertNotEqual(self.client.get(path).status_code, 200)

    def test_v250_disabled_modules_hide_direct_business_routes_without_erasing_data(self):
        from app import get_current_weather, get_database, write_setting
        self.login_admin()
        with self.app.app_context():
            database = get_database()
            original_users = database.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            for module in ("frequency", "users", "activities", "public_reservations", "billing"):
                write_setting(database, f"module_{module}", "0")
            write_setting(database, "module_weather", "0")
            database.commit()
            with mock.patch("app.urllib.request.urlopen") as weather_request:
                self.app.config["TESTING"] = False
                try:
                    self.assertIsNone(get_current_weather(self.app))
                finally:
                    self.app.config["TESTING"] = True
                weather_request.assert_not_called()
        self.assertEqual(self.client.get("/admin").status_code, 302)
        self.assertIn("/admin/reglages/structure", self.client.get("/admin").headers["Location"])
        for route in ("/admin/frequentation/journee", "/admin/usagers",
                      "/admin/animations", "/admin/facturation",
                      "/admin/animations/1/inscriptions"):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 404)
        self.assertEqual(self.client.get("/admin/reglages/structure").status_code, 200)
        self.assertIn("Le module de fréquentation est désactivé", self.client.get("/").get_data(as_text=True))
        self.assertEqual(self.client.get("/identification").status_code, 404)
        self.assertEqual(self.client.get("/usagers").status_code, 404)
        self.assertEqual(self.client.post("/visiteurs").status_code, 404)
        with self.app.app_context():
            database = get_database()
            write_setting(database, "module_frequency", "1")
            database.commit()
        home_without_users = self.client.get("/").get_data(as_text=True)
        self.assertNotIn("Je suis usager", home_without_users)
        self.assertIn("Je suis visiteur", home_without_users)
        with self.database() as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM users").fetchone()[0], original_users)

    def test_v250_weather_uses_only_configured_structure_coordinates(self):
        from app import get_current_weather, get_database, write_setting
        with self.app.app_context():
            database = get_database()
            write_setting(database, "structure_latitude", "")
            write_setting(database, "structure_longitude", "")
            database.commit()
            with mock.patch("app.urllib.request.urlopen") as request_weather:
                self.app.config.update(TESTING=False, WEATHER_ENABLED=True)
                try:
                    self.assertIsNone(get_current_weather(self.app))
                    request_weather.assert_not_called()
                    write_setting(database, "structure_latitude", "47.123")
                    write_setting(database, "structure_longitude", "6.789")
                    database.commit()
                    request_weather.side_effect = OSError("réseau de test désactivé")
                    self.assertIsNone(get_current_weather(self.app))
                    url = request_weather.call_args.args[0].full_url
                    self.assertIn("latitude=47.123", url)
                    self.assertIn("longitude=6.789", url)
                    self.assertNotIn("48.351", url)
                finally:
                    self.app.config.update(TESTING=True, WEATHER_ENABLED=False)

    def test_v250_structure_coordinates_and_privacy_url_are_private_profile_fields(self):
        from profile_archive import build_profile, parse_profile
        profile = parse_profile(build_profile({
            "structure_name": "Atelier Libre", "structure_latitude": "47.123",
            "structure_longitude": "6.789",
            "structure_privacy_policy_url": "https://example.invalid/donnees/",
        }, [], {}))
        self.assertEqual(profile["settings"]["structure_latitude"], "47.123")
        self.assertEqual(profile["settings"]["structure_privacy_policy_url"],
                         "https://example.invalid/donnees/")
        for settings in (
            {"structure_latitude": "91", "structure_longitude": "1"},
            {"structure_latitude": "1"},
            {"structure_privacy_policy_url": "javascript:alert(1)"},
        ):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                parse_profile(build_profile(settings, [], {}))

    def test_v250_rental_module_disables_new_rental_but_preserves_billing(self):
        from app import get_database, write_setting
        self.login_admin()
        created = self.client.post("/admin/facturation/nouveau", data={
            "billing_type": "rental", "quote_date": "2026-09-20",
            "client_contact": "Client Test", "client_structure": "Entreprise Exemple",
            "address_line": "1 rue Test", "postal_code": "75001", "city": "Paris",
            "title": "Location Prusa", "description": "Location de machine",
            "activity_date": "2026-10-15", "activity_start_time": "10:00",
            "activity_end_time": "11:00", "rental_machine_key": "prusa_mk39",
            "rental_months": "1", "rental_end_date": "2026-11-15",
        }, follow_redirects=True)
        self.assertIn("a été créé", created.get_data(as_text=True))
        with self.app.app_context():
            database = get_database()
            record_id = database.execute("SELECT MAX(id) FROM billing_records").fetchone()[0]
            write_setting(database, "module_rentals", "0")
            database.commit()
        listing = self.client.get("/admin/facturation").get_data(as_text=True)
        self.assertNotIn("Nouvelle location", listing)
        self.assertIn("Nouveau créneau", listing)
        self.assertEqual(self.client.get("/admin/facturation/nouveau?type=rental").status_code, 404)
        self.assertEqual(self.client.post("/admin/facturation/nouveau", data={"billing_type": "rental"}).status_code, 404)
        self.assertEqual(self.client.get("/admin/facturation/nouveau?type=reservation").status_code, 200)
        historical = self.client.get(f"/admin/facturation/{record_id}")
        self.assertEqual(historical.status_code, 200)
        self.assertNotIn("Modifier le dossier", historical.get_data(as_text=True))
        self.assertEqual(self.client.get(f"/admin/facturation/{record_id}/modifier").status_code, 404)
        self.assertEqual(self.client.post(f"/admin/facturation/{record_id}/signer").status_code, 404)
        self.assertEqual(self.client.get(f"/admin/facturation/{record_id}/devis.pdf").status_code, 200)

    def test_v250_admin_pin_change_and_recovery_are_one_time(self):
        from pin_security import (check_pin, consume_recovery_token,
                                  issue_recovery_token, token_status)
        self.login_admin()
        token = re.search(r'name="csrf_token" value="([^"]+)"',
                          self.client.get("/admin/reglages/borne").get_data(as_text=True)).group(1)
        self.client.post("/admin/options/pin-administrateur", data={
            "csrf_token": token, "current_pin": "1379", "new_pin": "2468", "confirm_pin": "2468"
        })
        self.assertFalse(check_pin(self.database_path, "admin", "1379"))
        self.assertTrue(check_pin(self.database_path, "admin", "2468"))
        first = issue_recovery_token(self.database_path, now=100)
        second = issue_recovery_token(self.database_path, now=101)
        self.assertEqual(token_status(self.database_path, first, now=102), "invalid")
        self.assertEqual(token_status(self.database_path, second, now=702), "expired")
        third = issue_recovery_token(self.database_path, now=800)
        self.assertEqual(consume_recovery_token(self.database_path, third, "9753", now=801), "valid")
        self.assertEqual(consume_recovery_token(self.database_path, third, "1357", now=802), "invalid")
        self.assertTrue(check_pin(self.database_path, "admin", "9753"))
        self.assertFalse(check_pin(self.database_path, "admin", "2468"))

    def test_v250_legacy_admin_pin_is_derived_from_backup_without_executing_code(self):
        from pin_security import check_pin, has_pin, migrate_legacy_admin_pin
        with tempfile.TemporaryDirectory(prefix="openfablab_legacy_pin_") as directory:
            old_database = Path(directory) / "compteur_fablab.db"
            old_database.touch()
            archive_path = Path(directory) / "historical.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("app.py", 'ADMIN_PIN=os.environ.get("COMPTEUR_ADMIN_PIN", "1357")\n')
            migrate_legacy_admin_pin(old_database, archive_path)
            self.assertTrue(has_pin(old_database, "admin"))
            self.assertTrue(check_pin(old_database, "admin", "1357"))
            self.assertFalse(check_pin(old_database, "admin", "0000"))
            with self.assertRaises(ValueError):
                migrate_legacy_admin_pin(old_database, archive_path)

    def test_v250_new_installation_has_generic_identity(self):
        with tempfile.TemporaryDirectory(prefix="openfablab_generic_") as directory:
            path = str(Path(directory) / "openfablab.db")
            app = create_app({"TESTING": True, "DATABASE": path, "ADMIN_PIN": None,
                              "MODERATOR_PIN": None, "WEATHER_ENABLED": False,
                              "SEED_DEMO_USERS": False})
            client = app.test_client()
            page = client.get("/").get_data(as_text=True)
            self.assertIn("Mon FabLab", page)
            self.assertNotIn("atelier-exemple-wordmark.png", page)
            self.assertNotIn("ville fictive-agglomeration.jpg", page)
            self.assertEqual(client.get("/manifest.webmanifest").json["short_name"], "FabLab")
            privacy = client.get("/gestion-des-donnees").get_data(as_text=True)
            self.assertNotIn("Contact pour les données personnelles", privacy)
            self.assertNotIn("Délégué à la protection des données", privacy)
            self.assertIn("responsable de traitement", privacy)
            with sqlite3.connect(path) as database:
                self.assertEqual(database.execute("SELECT COUNT(*) FROM rental_catalog").fetchone()[0], 0)
                self.assertEqual(database.execute("SELECT COUNT(*) FROM billing_tariff_catalog").fetchone()[0], 0)
                self.assertEqual(database.execute("SELECT value FROM app_settings WHERE key='billing_rate_normal_hourly_cents'").fetchone()[0], "0")
                self.assertEqual(database.execute("SELECT value FROM app_settings WHERE key='structure_iban'").fetchone()[0], "")
                self.assertEqual(database.execute("SELECT value FROM app_settings WHERE key='structure_latitude'").fetchone()[0], "")
                self.assertEqual(database.execute("SELECT value FROM app_settings WHERE key='structure_longitude'").fetchone()[0], "")
                self.assertEqual(database.execute("SELECT value FROM app_settings WHERE key='structure_privacy_policy_url'").fetchone()[0], "")
                self.assertEqual(database.execute("PRAGMA user_version").fetchone()[0],17)
            create_app({"TESTING": True, "DATABASE": path, "ADMIN_PIN": None,
                        "MODERATOR_PIN": None, "SEED_DEMO_USERS": False})
            with sqlite3.connect(path) as database:
                self.assertEqual(database.execute("SELECT value FROM app_settings WHERE key='structure_latitude'").fetchone()[0], "")
            from app import generate_badge_svg
            badge = generate_badge_svg(
                {"public_id": "4321", "first_name": "Alex", "category": "user"},
                {"name": "Mon FabLab", "short_name": "FabLab"},
            ).decode("utf-8")
            self.assertIn("Alex", badge)
            self.assertNotIn("Atelier Exemple", badge)
            from calendar_export import build_ics_event
            calendar = build_ics_event({
                "id": 1, "service_type": "animation", "title": "Atelier test",
                "service_date": "2026-10-03", "start_time": "14:00", "end_time": "15:00",
            }, structure={"name": "Atelier Nord", "address": "1 rue de l'Atelier",
                          "website": "https://atelier.example.org", "timezone": "Europe/Brussels"}).decode("utf-8")
            self.assertIn("LOCATION:Atelier Nord\\, 1 rue de l'Atelier", calendar)
            self.assertIn("@atelier.example.org", calendar)
            self.assertIn("DTSTART:20261003T120000Z", calendar)
            self.assertNotIn("Atelier Exemple", calendar)

    def test_v250_new_installation_requires_local_pin_setup(self):
        with tempfile.TemporaryDirectory(prefix="openfablab_new_install_") as directory:
            path = str(Path(directory) / "openfablab.db")
            app = create_app({"TESTING": True, "DATABASE": path, "ADMIN_PIN": None,
                              "MODERATOR_PIN": None, "WEATHER_ENABLED": False,
                              "SEED_DEMO_USERS": False})
            client = app.test_client()
            self.assertEqual(client.get("/admin/frequentation").status_code, 302)
            page = client.get("/admin/initialisation").get_data(as_text=True)
            self.assertIn("Créer le PIN administrateur", page)
            csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
            client.post("/admin/initialisation", data={"new_pin": "1357",
                "confirm_pin": "1357", "csrf_token": csrf})
            from pin_security import check_pin
            self.assertTrue(check_pin(path, "admin", "1357"))
            self.assertEqual(client.get("/admin/initialisation").status_code, 302)
            with sqlite3.connect(path) as database:
                self.assertEqual(database.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)

    def test_v250_sync_retries_and_imports_once_with_mock_client(self):
        # Historical protocol-2 replay on its original schema; never used by 2.8's worker.
        with self.database() as database:
            database.execute('PRAGMA user_version=14')
        from tests.historical_reservations_sync import (enqueue_booking_command, run_sync_cycle,
                                       save_sync_secret)
        with self.app.app_context():
            database = get_database()
            service_id = database.execute(
                "INSERT INTO fablab_services(service_type,title,service_date,created_at,updated_at) "
                "VALUES('animation','Essai synchronisation','2026-11-12',?,?)",
                ("2026-09-28T10:00:00+00:00", "2026-09-28T10:00:00+00:00")
            ).lastrowid
            uuid = "00000000-0000-4000-8000-000000000002"
            enqueue_booking_command(database, "test", uuid, "verify")
            database.commit()
            save_sync_secret(self.database_path, "a" * 64)
            event = {"id": "1", "type": "reservation_confirmed", "booking": {
                "uuid": uuid, "service_id": service_id, "environment": "test",
                "first_name": "Ana", "last_name": "TEST", "birth_year": 1999,
                "email": "ana@example.invalid", "phone": "+33600000000",
                "status": "confirmed", "link_status": "visitor", "source": "online",
                "created_at": "2026-11-01T10:00:00+00:00", "updated_at": "2026-11-01T10:00:00+00:00"}}

            class MockClient:
                def __init__(self, fail=False):
                    self.fail = fail
                    self.calls = []

                def post(self, route, payload):
                    self.calls.append((route, payload))
                    if self.fail and route == "/sync/commands":
                        raise OSError("offline")
                    if route == "/sync/events":
                        return {"events": [event] if payload["environment"] == "test" and not payload["cursor"] else [],
                                "cursor": "1" if payload["environment"] == "test" else ""}
                    return {"ok": True}

            failed = run_sync_cycle(database, self.database_path, "https://example.invalid", client=MockClient(True))
            self.assertEqual(failed["errors"], [{"environment": "test", "error": "OSError"}])
            self.assertIsNotNone(database.execute("SELECT last_success_at FROM reservation_sync_state WHERE environment='production'").fetchone()[0])
            self.assertIsNone(database.execute("SELECT sent_at FROM reservation_outbox").fetchone()[0])
            client = MockClient()
            result = run_sync_cycle(database, self.database_path, "https://example.invalid", client=client)
            self.assertEqual(result["imported"], 1)
            self.assertEqual({payload["environment"] for _, payload in client.calls}, {"test", "production"})
            self.assertEqual(result["notifications"][0]["type"], "reservation_confirmed")
            self.assertTrue(database.execute("SELECT sent_at FROM reservation_outbox").fetchone()[0])
            self.assertEqual(run_sync_cycle(database, self.database_path, "https://example.invalid", client=MockClient())["imported"], 0)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM animation_bookings").fetchone()[0], 1)
            with self.assertRaises(ValueError):
                run_sync_cycle(database, self.database_path, "https://example.invalid",
                               client=MockClient(), environments=("unknown",))
            invalid_client = MockClient()
            with self.assertRaises(ValueError):
                run_sync_cycle(database, self.database_path, "http://example.invalid",
                               client=invalid_client)
            self.assertEqual(invalid_client.calls, [])

    def test_v250_discord_reservations_are_optional_and_do_not_include_contacts(self):
        from app import notify_reservation_discord, send_discord_notification, write_setting
        with self.app.app_context(), mock.patch("app.read_discord_webhook", return_value="https://example.invalid/hook"), \
                mock.patch("app.post_discord_message") as post:
            database = get_database()
            service_id = database.execute(
                "INSERT INTO fablab_services(service_type,title,service_date,created_at,updated_at) "
                "VALUES('animation','Atelier dessin','2026-11-12',?,?)",
                ("2026-09-28T10:00:00+00:00", "2026-09-28T10:00:00+00:00")
            ).lastrowid
            write_setting(database, "discord_notifications_enabled", "1")
            self.assertTrue(notify_reservation_discord(database, "reservation_confirmed", service_id))
            message = post.call_args.args[1]
            self.assertIn("Atelier dessin", message)
            self.assertNotIn("@", message)
            self.assertNotIn("example.invalid", message)
            write_setting(database, "discord_reservation_new_booking", "0")
            self.assertFalse(notify_reservation_discord(database, "reservation_confirmed", service_id))
            self.assertEqual(post.call_count, 1)
            write_setting(database, "module_discord", "0")
            post.reset_mock()
            self.assertFalse(notify_reservation_discord(database, "reservation_confirmed", service_id))
            self.assertFalse(send_discord_notification(database, "visitor"))
            post.assert_not_called()

    def _animation_booking_fixture(self, capacity=3):
        from app import write_setting
        self.login_admin()
        with self.app.app_context():
            database = get_database()
            write_setting(database, "module_public_reservations", "1")
            service_id = database.execute(
                "INSERT INTO fablab_services(service_type,title,service_date,start_time,end_time,"
                "duration_minutes,minimum_age,created_at,updated_at) VALUES"
                "('animation','Atelier organisation','2026-11-12','14:00','16:00',120,10,'2026-09-29','2026-09-29')"
            ).lastrowid
            database.execute("INSERT INTO animation_reservation_config(service_id,enabled,environment,capacity,updated_at) "
                             "VALUES (?,1,'test',?,'2026-09-29')", (service_id, capacity))
            database.commit()
        page = self.client.get(f"/admin/animations/{service_id}/inscriptions").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        return service_id, token

    def _animation_booking_row(self, service_id, status="confirmed", group=None, presence=None):
        from uuid import uuid4
        booking_id = str(uuid4())
        with self.database() as database:
            database.execute("INSERT INTO animation_bookings(external_uuid,service_id,environment,"
                             "first_name,last_name,birth_year,email,phone,status,link_status,group_uuid,"
                             "source,is_present,created_at,updated_at) VALUES"
                             "(?,?,'test','Anne','TEST',1990,'anne@example.invalid','0600000000',?,'visitor',?,'online',?,'2026-09-29','2026-09-29')",
                             (booking_id, service_id, status, group, presence))
        return booking_id

    def _animation_booking_action(self, service_id, booking_id, token, action, **values):
        response = self.client.post(f"/admin/animations/{service_id}/inscriptions/{booking_id}/action",
                                    data={"csrf_token": token, "action": action, **values}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        return response

    def test_v250_participants_group_linkage_and_separate_cancellation(self):
        service_id, _token = self._animation_booking_fixture()
        booking_id = self._animation_booking_row(service_id)
        with self.database() as database:
            user = database.execute("SELECT id FROM users WHERE public_id='1001'").fetchone()
            database.execute("UPDATE animation_bookings SET user_id=?,public_id='1001',link_status='matched' WHERE external_uuid=?",
                             (user[0], booking_id))
        for pin in ("1379", "8642"):
            with self.subTest(pin=pin):
                self.client.post("/admin/deconnexion")
                self.login_admin(pin)
                page = self.client.get(f"/admin/animations/{service_id}/inscriptions").get_data(as_text=True)
                cells = dict(re.findall(r'<td data-label="([^"]+)"[^>]*>(.*?)</td>', page, re.S))
                self.assertIn("<th>Identifiant</th>", page)
                self.assertNotIn('<td data-label="Type">', page)
                self.assertIn("Usager #1001", cells["Identifiant"])
                linkage = cells["Rattachement"]
                for text in ("Coordonnées concordantes", "Rattacher à un usager", "Rattacher", "Détacher", "Vérifié manuellement"):
                    self.assertIn(text, linkage)
                self.assertIn('class="reservation-linkage-form"', linkage)
                self.assertIn('name="csrf_token"', linkage)
                actions = cells["Actions"]
                self.assertNotIn('name="public_id"', actions)
                self.assertNotIn('value="verify"', actions)
                presence_form = re.search(r'<form class="reservation-booking-actions".*?</form>', actions, re.S).group(0)
                self.assertIn('value="present"', presence_form)
                self.assertIn('value="absent"', presence_form)
                self.assertNotIn('value="cancel"', presence_form)
                cancel_form = re.search(r'<form class="reservation-cancel-form".*?</form>', actions, re.S).group(0)
                self.assertIn("Annuler l’inscription", cancel_form)
                self.assertIn('class="admin-button danger compact"', cancel_form)
                self.assertIn('onsubmit="return confirm(', cancel_form)
                self.assertIn('name="csrf_token"', cancel_form)
                self.assertIn("Réservation :", cells["Réservation / présence"])
                self.assertIn("Présence :", cells["Réservation / présence"])
                self.assertEqual(list(cells), ["Personne", "Âge", "Identifiant", "Rattachement",
                                              "Réservation / présence", "Contact", "Actions"])

    def test_v250_split_participant_forms_preserve_moderator_workflow(self):
        service_id, _token = self._animation_booking_fixture()
        booking_id = self._animation_booking_row(service_id)
        self.client.post("/admin/deconnexion")
        self.login_admin("8642")
        path = f"/admin/animations/{service_id}/inscriptions"
        page = self.client.get(path).get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        self._animation_booking_action(service_id, booking_id, token, "link", public_id="1001")
        self._animation_booking_action(service_id, booking_id, token, "verify")
        with self.database() as database:
            self.assertEqual(database.execute("SELECT link_status FROM animation_bookings WHERE external_uuid=?",
                                              (booking_id,)).fetchone()[0], "manual")
        self._animation_booking_action(service_id, booking_id, token, "unlink")
        for action, presence in (("present", 1), ("absent", 0)):
            self._animation_booking_action(service_id, booking_id, token, action)
            with self.database() as database:
                row = database.execute("SELECT status,is_present,user_id FROM animation_bookings WHERE external_uuid=?",
                                       (booking_id,)).fetchone()
                self.assertEqual(tuple(row), ("confirmed", presence, None))
        self.assertEqual(self.client.get(f"/admin/animations/{service_id}/modifier").status_code, 302)

    def test_v250_activities_inscriptions_in_actions_and_permissions(self):
        service_id, _token = self._animation_booking_fixture()
        inscriptions = f"/admin/animations/{service_id}/inscriptions"
        modification = f"/admin/animations/{service_id}/modifier"
        for pin in ("1379", "8642"):
            with self.subTest(pin=pin):
                self.client.post("/admin/deconnexion")
                self.login_admin(pin)
                page = self.client.get("/admin/activites", follow_redirects=True).get_data(as_text=True)
                title_cell = re.search(r'<td data-label="Animation ou réservation">(.*?)</td>', page, re.S).group(1)
                self.assertNotIn("Inscriptions", title_cell)
                self.assertNotIn("Voir les inscriptions", page)
                actions = re.search(r'<td data-label="Actions"[^>]*>(.*?)</td>', page, re.S).group(1)
                self.assertIn(f'href="{inscriptions}">Inscriptions</a>', actions)
                self.assertIn("Calendrier Apple / Outlook", actions)
                if pin == "1379":
                    self.assertLess(actions.index("Inscriptions</a>"), actions.index("Modifier</a>"))
                    self.assertLess(actions.index("Modifier</a>"), actions.index("Calendrier Apple"))
                    self.assertEqual(self.client.get(modification).status_code, 200)
                else:
                    self.assertNotIn(modification, actions)
                    self.assertNotIn("Modifier", actions)
                    self.assertEqual(self.client.get(modification).status_code, 302)
                calendar = re.search(r'href="([^"]+)">Calendrier Apple', actions).group(1)
                self.assertEqual(self.client.get(calendar).status_code, 200)

    def test_v250_bookings_header_modifier_only_for_admin(self):
        service_id, _token = self._animation_booking_fixture()
        for pin in ("1379", "8642"):
            with self.subTest(pin=pin):
                self.client.post("/admin/deconnexion")
                self.login_admin(pin)
                page = self.client.get(f"/admin/animations/{service_id}/inscriptions").get_data(as_text=True)
                controls = re.search(r'<div class="form-actions reservation-export-actions">(.*?)</div>', page, re.S).group(1)
                self.assertLess(controls.index("Exporter les inscriptions CSV"), controls.index("Exporter les inscriptions PDF"))
                if pin == "1379":
                    self.assertIn(f'href="/admin/animations/{service_id}/modifier"', controls)
                    self.assertLess(controls.index("Modifier"), controls.index("Exporter les inscriptions CSV"))
                else:
                    self.assertNotIn("Modifier", controls)
                    self.assertEqual(self.client.post(f"/admin/animations/{service_id}/modifier",
                                                       data={"title": "Forbidden"}).status_code, 302)
                    with self.database() as database:
                        self.assertEqual(database.execute("SELECT title FROM fablab_services WHERE id=?",
                                                          (service_id,)).fetchone()[0], "Atelier organisation")

    def test_v250_footer_uses_structure_name_and_description(self):
        from html import unescape
        from app import write_setting
        page = self.client.get("/").get_data(as_text=True)
        footer = re.search(r'<footer class="site-footer">(.*?)</footer>', page, re.S).group(1)
        self.assertIn("Atelier Exemple - FabLab de démonstration", footer)
        with self.app.app_context():
            database = get_database()
            write_setting(database, "structure_name", "Atelier & Libre")
            write_setting(database, "structure_description", "Makerspace municipal")
            database.commit()
        self.login_admin()
        for path in ("/", "/admin/activites", "/gestion-des-donnees"):
            with self.subTest(path=path):
                page = self.client.get(path, follow_redirects=True).get_data(as_text=True)
                footer = re.search(r'<footer class="site-footer">(.*?)</footer>', page, re.S).group(1)
                self.assertIn("Atelier &amp; Libre", footer)
                self.assertIn("Atelier & Libre - Makerspace municipal", unescape(footer))
                self.assertNotIn("Atelier Exemple", footer)

    def test_v250_animation_pdf_multipage_and_permissions(self):
        service_id, token = self._animation_booking_fixture(80)
        for _ in range(55):
            self._animation_booking_row(service_id)
        route = f"/admin/animations/{service_id}/inscriptions.pdf"
        response = self.client.get(route)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b"%PDF"))
        self.assertGreater(len(re.findall(rb"/Type /Page\b", response.data)), 1)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.assertIn("20261112_Inscriptions", response.headers["Content-Disposition"])
        self.assertEqual(self.client.get(f"/admin/animations/{service_id}/inscriptions.csv").status_code, 200)
        self.client.post("/admin/deconnexion")
        self.assertEqual(self.client.get(route).status_code, 302)
        self.login_admin("8642")
        self.assertEqual(self.client.get(route).status_code, 200)
        self.assertEqual(self.client.get("/admin/animations/999999/inscriptions.pdf").status_code, 404)
        with self.app.app_context():
            from app import write_setting
            database = get_database()
            write_setting(database, "module_public_reservations", "0")
            database.commit()
        self.assertEqual(self.client.get(route).status_code, 404)

    def test_v250_animation_pdf_empty_and_custom_structure(self):
        from animation_report import generate_animation_bookings_pdf
        service_id, _token = self._animation_booking_fixture()
        with self.database() as database:
            service = database.execute("SELECT * FROM fablab_services WHERE id=?", (service_id,)).fetchone()
            config = database.execute("SELECT * FROM animation_reservation_config WHERE service_id=?", (service_id,)).fetchone()
        output = generate_animation_bookings_pdf(service, config, [], {"name": "Atelier Libre", "color": "#20556a"}, {})
        self.assertEqual(len(re.findall(rb"/Type /Page\b", output)), 1)
        self.assertIn(b"/Author (Atelier Libre)", output)

    def test_v250_animation_reservation_and_presence_are_separate(self):
        from reservations_sync import booking_capacity_used, booking_counts
        service_id, token = self._animation_booking_fixture(1)
        booking_id = self._animation_booking_row(service_id)
        for action, presence in (("present", 1), ("absent", 0), ("present", 1)):
            response = self._animation_booking_action(service_id, booking_id, token, action)
            self.assertIn("Réservation :", response.get_data(as_text=True))
            self.assertIn("Présence :", response.get_data(as_text=True))
            with self.database() as database:
                row = database.execute("SELECT * FROM animation_bookings WHERE external_uuid=?", (booking_id,)).fetchone()
                self.assertEqual(row["status"], "confirmed")
                self.assertEqual(row["is_present"], presence)
                self.assertEqual(booking_capacity_used(database, service_id), 1)
                self.assertEqual(booking_counts([row])["confirmed"], 1)
                self.assertEqual(database.execute("SELECT actual_participants FROM fablab_services WHERE id=?", (service_id,)).fetchone()[0], presence)

    def test_v250_animation_confirmation_allowed_transitions(self):
        service_id, token = self._animation_booking_fixture(1)
        waiting = self._animation_booking_row(service_id, "waitlisted")
        self._animation_booking_action(service_id, waiting, token, "present")
        with self.database() as database:
            self.assertEqual(database.execute("SELECT status FROM animation_bookings WHERE external_uuid=?", (waiting,)).fetchone()[0], "waitlisted")
        self._animation_booking_action(service_id, waiting, token, "confirm")
        with self.database() as database:
            row = database.execute("SELECT status,is_present FROM animation_bookings WHERE external_uuid=?", (waiting,)).fetchone()
            self.assertEqual(tuple(row), ("confirmed", None))
            actions = database.execute("SELECT COUNT(*) FROM reservation_actions").fetchone()[0]
        for status in ("cancelled", "expired", "confirmed"):
            incompatible = self._animation_booking_row(service_id, status)
            self._animation_booking_action(service_id, incompatible, token, "confirm", capacity_override="1")
            with self.database() as database:
                self.assertEqual(database.execute("SELECT status FROM animation_bookings WHERE external_uuid=?", (incompatible,)).fetchone()[0], status)
                self.assertEqual(database.execute("SELECT COUNT(*) FROM reservation_actions").fetchone()[0], actions)

    def test_v250_animation_confirmation_group_capacity_and_override(self):
        from reservations_sync import booking_capacity_used
        service_id, token = self._animation_booking_fixture(1)
        pair = [self._animation_booking_row(service_id, "waitlisted", "pair") for _ in range(2)]
        self._animation_booking_action(service_id, pair[0], token, "confirm")
        with self.database() as database:
            self.assertEqual(booking_capacity_used(database, service_id), 0)
        self.client.post("/admin/deconnexion")
        self.login_admin("8642")
        page = self.client.get(f"/admin/animations/{service_id}/inscriptions").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        self._animation_booking_action(service_id, pair[0], token, "confirm", capacity_override="1")
        with self.database() as database:
            self.assertEqual(booking_capacity_used(database, service_id), 0)
        self.client.post("/admin/deconnexion")
        self.login_admin()
        page = self.client.get(f"/admin/animations/{service_id}/inscriptions").get_data(as_text=True)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        self._animation_booking_action(service_id, pair[0], token, "confirm", capacity_override="1")
        with self.database() as database:
            self.assertEqual(booking_capacity_used(database, service_id), 2)
            self.assertTrue(all(row[0] == "confirmed" for row in database.execute("SELECT status FROM animation_bookings")))
            command = json.loads(database.execute("SELECT payload_json FROM reservation_outbox ORDER BY id DESC LIMIT 1").fetchone()[0])
            self.assertEqual(set(command["members"]), set(pair))
            self.assertTrue(command["capacity_override"])

    def test_v250_animation_offer_confirmation_does_not_consume_extra_place(self):
        from reservations_sync import booking_capacity_used
        service_id, token = self._animation_booking_fixture(1)
        booking_id = self._animation_booking_row(service_id, "offer_pending")
        self._animation_booking_action(service_id, booking_id, token, "confirm")
        with self.database() as database:
            self.assertEqual(database.execute("SELECT status FROM animation_bookings WHERE external_uuid=?", (booking_id,)).fetchone()[0], "confirmed")
            self.assertEqual(booking_capacity_used(database, service_id), 1)

    def test_v250_animation_incompatible_group_cannot_be_confirmed(self):
        service_id, token = self._animation_booking_fixture(2)
        waiting = self._animation_booking_row(service_id, "waitlisted", "pair")
        self._animation_booking_row(service_id, "cancelled", "pair", presence=0)
        page = self.client.get(f"/admin/animations/{service_id}/inscriptions").get_data(as_text=True)
        self.assertNotIn('value="confirm"', page)
        self._animation_booking_action(service_id, waiting, token, "confirm", capacity_override="1")
        with self.database() as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM reservation_actions").fetchone()[0], 0)
            self.assertEqual(database.execute("SELECT status FROM animation_bookings WHERE external_uuid=?", (waiting,)).fetchone()[0], "waitlisted")

    def test_v250_animation_cancelled_group_has_no_attendance_or_reserved_places(self):
        from reservations_sync import booking_capacity_used, booking_counts
        service_id, token = self._animation_booking_fixture(2)
        first = self._animation_booking_row(service_id, "confirmed", "pair", presence=1)
        self._animation_booking_row(service_id, "confirmed", "pair", presence=1)
        self._animation_booking_action(service_id, first, token, "cancel")
        with self.database() as database:
            rows = database.execute("SELECT * FROM animation_bookings WHERE service_id=?", (service_id,)).fetchall()
            self.assertTrue(all(row["status"] == "cancelled" for row in rows))
            self.assertEqual(booking_capacity_used(database, service_id), 0)
            self.assertEqual(booking_counts(rows)["present"], 0)
            self.assertEqual(booking_counts(rows)["absent"], 0)

    def test_v250_animation_remote_confirmation_waits_for_authoritative_sync(self):
        # Historical rows retain their original protocol-2 semantics in this fixture.
        with self.database() as database:
            database.execute('PRAGMA user_version=14')
        from app import write_setting
        from tests.historical_reservations_sync import save_sync_secret, run_sync_cycle, booking_capacity_used
        service_id, token = self._animation_booking_fixture(1)
        waiting = self._animation_booking_row(service_id, "waitlisted")
        extra = self._animation_booking_row(service_id, "waitlisted")
        with self.app.app_context():
            database = get_database()
            write_setting(database, "reservation_wordpress_url", "https://example.invalid")
            database.commit()
        save_sync_secret(self.database_path, "fictional-secret-" + "x"*48)
        response = self._animation_booking_action(service_id, waiting, token, "confirm")
        self.assertIn("Confirmation en attente", response.get_data(as_text=True))
        self._animation_booking_action(service_id, extra, token, "confirm")
        with self.database() as database:
            self.assertEqual(booking_capacity_used(database, service_id), 1)
            self.assertEqual(database.execute("SELECT COUNT(*) FROM reservation_outbox").fetchone()[0], 1)
            booking = dict(database.execute("SELECT * FROM animation_bookings WHERE external_uuid=?", (waiting,)).fetchone())
            self.assertEqual(booking["status"], "waitlisted")
        booking.update(uuid=waiting, status="confirmed", updated_at="2026-09-29T18:00:00+00:00")
        class Client:
            def post(_self, route, payload):
                return {"events": [{"id": "1", "booking": booking}], "cursor": "1"} if route == "/sync/events" else {"ok": True}
        with self.app.app_context():
            run_sync_cycle(get_database(), self.database_path, "https://example.invalid", client=Client())
        with self.database() as database:
            self.assertEqual(database.execute("SELECT status FROM animation_bookings WHERE external_uuid=?", (waiting,)).fetchone()[0], "confirmed")
            self.assertEqual(booking_capacity_used(database, service_id), 1)

    def test_v250_animation_remote_capacity_refusal_is_visible_and_retryable(self):
        # Compatibility helper tested independently of the schema-15 family engine.
        with self.database() as database:
            database.execute('PRAGMA user_version=14')
        from app import write_setting
        from tests.historical_reservations_sync import save_sync_secret, run_sync_cycle, pending_confirmation_ids
        service_id, token = self._animation_booking_fixture(1)
        waiting = self._animation_booking_row(service_id, "waitlisted")
        with self.app.app_context():
            database = get_database()
            write_setting(database, "reservation_wordpress_url", "https://example.invalid")
            database.commit()
        save_sync_secret(self.database_path, "fictional-secret-" + "x"*48)
        self._animation_booking_action(service_id, waiting, token, "confirm")
        class Client:
            def post(_self, route, payload):
                if route == "/sync/commands": return {"ok": True, "confirmation": "refused", "reason": "capacity"}
                if route == "/sync/events": return {"events": [], "cursor": ""}
                return {"ok": True}
        with self.app.app_context():
            database = get_database()
            result = run_sync_cycle(database, self.database_path, "https://example.invalid", client=Client())
            self.assertEqual(len(result["rejected"]), 1)
            self.assertEqual(pending_confirmation_ids(database, service_id), set())
        page = self.client.get(f"/admin/animations/{service_id}/inscriptions").get_data(as_text=True)
        self.assertIn("Confirmation refusée : capacité atteinte", page)
        self.assertIn('value="confirm"', page)
        with self.database() as database:
            self.assertEqual(database.execute("SELECT status FROM animation_bookings WHERE external_uuid=?", (waiting,)).fetchone()[0], "waitlisted")

    def test_v250_animation_user_choice_first_and_sorted_by_given_name(self):
        service_id, token = self._animation_booking_fixture()
        with self.database() as database:
            ids = [row[0] for row in database.execute("SELECT id FROM users ORDER BY id LIMIT 3")]
            database.execute("UPDATE users SET active=0")
            for user_id, first, last in zip(ids, ("Éloi", "Anne", "Anne"), ("TEST", "ZED", "AUBE")):
                database.execute("UPDATE users SET active=1,first_name=?,last_name=? WHERE id=?", (first, last, user_id))
        page = self.client.get(f"/admin/animations/{service_id}/inscriptions").get_data(as_text=True)
        walkin = page[page.index("Ajouter des participants"):]
        self.assertIn('name="person_ids"', walkin)
        self.assertNotIn('name="first_name"', walkin)
        self.assertLess(walkin.index("Anne AUBE"), walkin.index("Anne ZED"))
        self.assertLess(walkin.index("Anne ZED"), walkin.index("Éloi TEST"))

    def test_v250_animation_walkin_edits_do_not_change_user_or_forward_moderator_override(self):
        service_id, token = self._animation_booking_fixture(3)
        with self.database() as database:
            database.execute("UPDATE users SET birth_year=1990,email='account@example.invalid' WHERE public_id='1001'")
            original = tuple(database.execute("SELECT first_name,last_name,birth_year,email,phone FROM users WHERE public_id='1001'").fetchone())
        values = {"public_id": "1001", "first_name": "Réservation", "last_name": "LOCALE",
                  "birth_year": "1990", "email": "reservation@example.invalid", "phone": "0600000000"}
        for role_pin in ("1379", "8642"):
            self.client.post("/admin/deconnexion")
            self.login_admin(role_pin)
            page = self.client.get(f"/admin/animations/{service_id}/inscriptions").get_data(as_text=True)
            token = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
            response = self.client.post(f"/admin/animations/{service_id}/inscriptions/sur-place",
                                        data={**values, "csrf_token": token, "capacity_override": "1"}, follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            with self.database() as database:
                self.assertEqual(tuple(database.execute("SELECT first_name,last_name,birth_year,email,phone FROM users WHERE public_id='1001'").fetchone()), original)
                booking=database.execute("SELECT * FROM animation_bookings WHERE source='family_administration'").fetchone()
                self.assertIsNotNone(booking)
                self.assertIsNotNone(booking['user_id'])
                self.assertEqual(database.execute("SELECT COUNT(*) FROM reservation_outbox WHERE command_type='booking'").fetchone()[0],0)

    def test_v250_plugin_zip_contains_only_wordpress_code(self):
        from build_wordpress_plugin import build, INCLUDED
        with tempfile.TemporaryDirectory(prefix="openfablab_plugin_zip_") as directory:
            path = build(Path(directory) / "plugin.zip")
            with zipfile.ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                names = archive.namelist()
                current_script = archive.read("openfablab-reservations/assets/family.js").decode("utf-8")
                booking_script = Path("tests/historical-wordpress/assets/reservations.js").read_text()
                logo = archive.read("openfablab-reservations/assets/OpenFabLab-logo-horizontal.svg")
                archive_header = archive.read("openfablab-reservations/openfablab-reservations.php")
            self.assertEqual(len(names), len(INCLUDED))
            self.assertIn("openfablab-reservations/includes/class-openfablab-admin.php", names)
            self.assertFalse(any('bookings' in name or 'test-maintenance' in name or 'slots.php' in name for name in names))
            self.assertIn('request_key', current_script)
            self.assertIn(b"Version: 2.8.2", archive_header)
            self.assertTrue(all(name.startswith("openfablab-reservations/") for name in names))
            self.assertFalse(any(name.endswith((".db", ".sqlite", ".png")) for name in names))
            self.assertEqual(logo, Path("static/brand/OpenFabLab-logo-horizontal.svg").read_bytes())
            self.assertIn("En savoir plus sur la gestion de vos données", booking_script)
            self.assertNotIn("privacy || '#'", booking_script)
            self.assertNotIn("privacy_accepted", booking_script)
            self.assertNotIn("privacyBox", booking_script)
            self.assertIn("Les informations demandées sont utilisées pour gérer votre réservation ou vous contacter à ce sujet.", booking_script)
            self.assertNotIn("Une réservation = une place = une personne.", booking_script)
            self.assertIn("Réservation conseillée avec votre identifiant usager, mais possibilité de réserver sans cela", booking_script)
            self.assertLess(booking_script.index("fields.appendChild(emailField)"), booking_script.index("fields.appendChild(field('first_name'"))
            self.assertIn("if (!get('email') && !get('phone'))", booking_script)
            self.assertIn("fields.appendChild(field('first_name', 'Prénom', 'text', true))", booking_script)
            self.assertIn("const phoneField = field('phone', 'Téléphone de contact', 'tel', true)", booking_script)
            booking_server = Path("tests/historical-wordpress/includes/class-openfablab-bookings.php").read_text()
            self.assertNotIn("privacy_accepted", booking_server)
            self.assertNotIn("privacy_required", booking_server)
            self.assertIn("!is_email($email)", booking_server)
            self.assertIn("strlen(preg_replace('/\\D/', '', $phone)) < 8", booking_server)
            self.assertIn("|| $year < 1900", booking_server)
            self.assertNotIn("$allow_registered_year", booking_server)
            self.assertIn("self::validate_person($companion_data)", booking_server)
            self.assertLess(booking_server.index("!self::token_row($uuid, $token, $type)"),
                            booking_server.index("$booking = $wpdb->get_row", booking_server.index("private static function action_page")))
            self.assertIn("status_header(403)", booking_server)
            self.assertIn("esc_html($person)", booking_server)
            self.assertIn("esc_html($animation['title'])", booking_server)
            self.assertIn("self::render_action_page($type, null, null, 'Ce lien est invalide ou expiré.', true)", booking_server)
            self.assertIn("$failed ? null : $booking", booking_server)
            self.assertIn("Referrer-Policy: no-referrer", booking_server)
            bootstrap = Path("wordpress/openfablab-reservations/openfablab-reservations.php").read_text()
            self.assertIn("hash_file('sha256'", bootstrap)
            self.assertIn("$style_version = substr(hash_file('sha256'", bootstrap)

    def test_v250_reservation_copy_and_structure_spacing(self):
        from app import write_setting
        with self.app.app_context():
            database = get_database()
            write_setting(database, "module_public_reservations", "1")
            database.commit()
        privacy = self.client.get("/gestion-des-donnees").get_data(as_text=True)
        self.assertIn("Pour réserver en ligne, un plugin sur le site WordPress", privacy)
        self.assertNotIn("Pour une réservation en ligne, un composant", privacy)
        self.login_admin()
        animation = self.client.get("/admin/animations/nouveau").get_data(as_text=True)
        self.assertIn("Une personne sélectionnée = une place", animation)
        self.assertNotIn("Tous, y compris les visiteurs", animation)
        structure = self.client.get("/admin/reglages/structure").get_data(as_text=True)
        self.assertIn("structure-settings-form", structure)
        self.assertIn("structure-save-actions", structure)
        self.assertNotIn("connexion WordPress et règles ci-dessous", structure)
        self.assertIn('id="reservations"', structure)

    def test_v250_application_zip_is_reproducible_and_excludes_private_data(self):
        from build_openfablab import build
        with tempfile.TemporaryDirectory(prefix="openfablab_app_zip_") as directory:
            first = build(Path(directory) / "first.zip")
            second = build(Path(directory) / "second.zip")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertIsNone(archive.testzip())
                names = archive.namelist()
            self.assertIn("Dockerfile", names)
            self.assertIn("profile_archive.py", names)
            for asset in ("static/brand/OpenFabLab-logo-horizontal.svg",
                          "static/brand/OpenFabLab-logo-complet.svg",
                          "static/icons/OpenFabLab-icon.svg",
                          "static/icons/OpenFabLab-icon-192.png",
                          "static/icons/OpenFabLab-icon-512.png",
                          "static/icons/OpenFabLab-favicon.ico"):
                self.assertIn(asset, names)
            self.assertFalse(any(name.startswith("Ressources/") for name in names))
            self.assertFalse(any(name.endswith((".db", ".sqlite", ".sqlite3", ".pyc")) for name in names))
            self.assertFalse(any(name.startswith(("Saves/", "data/", "branding/", "wordpress/")) for name in names))
            self.assertFalse(any("secret" in name.lower() or "pin" in name.lower() and name.startswith(".") for name in names))

    def test_v261_wordmark_is_an_uploaded_private_structure_resource(self):
        from app import STRUCTURE_FIELDS, load_modules, load_structure_settings
        from PIL import Image
        self.login_admin()
        with self.database() as database:
            self.assertEqual(database.execute("SELECT value FROM app_settings WHERE key='structure_wordmark_logo'").fetchone()[0], '')
        self.assertEqual(self.client.get('/media/structure/wordmark.png').status_code,404)
        self.assertIn('/static/brand/OpenFabLab-logo-horizontal.svg',self.client.get('/').get_data(as_text=True))
        with self.app.app_context():
            database=get_database()
            structure=load_structure_settings(database)
            modules=load_modules(database)
        form={key:structure[key] for key in STRUCTURE_FIELDS}
        form.update({f'module_{key}':'1' for key,enabled in modules.items() if enabled})
        picture=io.BytesIO()
        Image.new('RGB',(100,30),'white').save(picture,'PNG')
        picture.seek(0)
        form['logo_wordmark']=(picture,'fictional-wordmark.png')
        form['csrf_token']=re.search(r'name="csrf_token" value="([^"]+)"',self.client.get('/admin/reglages/structure').get_data(as_text=True)).group(1)
        self.client.post("/admin/reglages/structure", data=form, content_type="multipart/form-data")
        with self.database() as database:
            self.assertEqual(database.execute(
                "SELECT value FROM app_settings WHERE key='structure_wordmark_logo'"
            ).fetchone()[0], "wordmark.png")
        response = self.client.get("/media/structure/wordmark.png")
        self.assertEqual(response.status_code, 200)
        response.close()
        self.assertIn("/media/structure/wordmark.png", self.client.get("/").get_data(as_text=True))
        token = re.search(r'name="csrf_token" value="([^"]+)"',
                          self.client.get("/admin/reglages/structure").get_data(as_text=True)).group(1)
        self.client.post("/admin/reglages/structure/logo-openfablab", data={"csrf_token": token})
        self.assertIn("/static/brand/OpenFabLab-logo-horizontal.svg", self.client.get("/").get_data(as_text=True))

    def test_v250_private_profile_roundtrip_without_business_data_or_secrets(self):
        from app import get_database, write_setting
        from profile_archive import parse_profile
        self.login_admin()
        with self.app.app_context():
            database = get_database()
            write_setting(database, "reservation_wordpress_url", "https://secret.example.invalid")
            write_setting(database, "private_auth_token", "DO_NOT_EXPORT_TOKEN")
            database.execute("INSERT INTO billing_tariff_catalog "
                "(tariff_key,name,unit,cents,active,archived,sort_order,created_at,updated_at) "
                "VALUES ('profile_tariff','Tarif profil','hourly',1900,1,0,1,'2026-09-28','2026-09-28')")
            database.commit()
        exported = self.client.get("/admin/profil/exporter")
        self.assertEqual(exported.status_code, 200)
        self.assertIn(".openfablab-profile.zip", exported.headers["Content-Disposition"])
        archive_bytes = exported.data
        profile = parse_profile(archive_bytes)
        self.assertEqual(profile["settings"]["structure_name"], "Atelier Exemple")
        self.assertTrue(profile["machines"])
        self.assertEqual(profile["tariffs"][0]["name"], "Tarif profil")
        self.assertIn("assets/main.png", profile["assets"])
        self.assertNotIn("assets/wordmark.png", profile["assets"])
        for forbidden in (b"DO_NOT_EXPORT_TOKEN", b"secret.example.invalid", b"Victor", b"1379"):
            self.assertNotIn(forbidden, archive_bytes)
        with self.app.app_context():
            database = get_database()
            original_users = database.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            write_setting(database, "structure_name", "Temporaire")
            database.commit()
        page = self.client.get("/admin/reglages/structure").get_data(as_text=True)
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
        preview = self.client.post("/admin/profil/importer", data={
            "csrf_token": csrf, "step": "preview",
            "profile_file": (io.BytesIO(archive_bytes), "profil.zip"),
        }, follow_redirects=True)
        self.assertIn("Profil vérifié", preview.get_data(as_text=True))
        applied = self.client.post("/admin/profil/importer", data={
            "csrf_token": csrf, "step": "apply", "confirmation": "IMPORTER LE PROFIL",
            "profile_file": (io.BytesIO(archive_bytes), "profil.zip"),
        }, follow_redirects=True)
        self.assertIn("Profil importé", applied.get_data(as_text=True))
        with self.database() as database:
            self.assertEqual(database.execute("SELECT COUNT(*) FROM users").fetchone()[0], original_users)
            self.assertEqual(database.execute("SELECT value FROM app_settings WHERE key='structure_name'").fetchone()[0], "Atelier Exemple")
            self.assertNotEqual(database.execute("SELECT value FROM app_settings WHERE key='structure_wordmark_logo'").fetchone()[0], "wordmark.png")
            self.assertEqual(database.execute("SELECT value FROM app_settings WHERE key='reservation_wordpress_url'").fetchone()[0], "")
            self.assertEqual(database.execute("SELECT cents FROM billing_tariff_catalog WHERE tariff_key='profile_tariff'").fetchone()[0], 1900)

    def test_v250_private_profile_rejects_invalid_and_incompatible_files(self):
        from profile_archive import allowed_setting, build_profile, parse_profile
        self.login_admin()
        self.assertFalse(allowed_setting("discord_message_webhook"))
        self.assertFalse(allowed_setting("discord_notify_secret"))
        self.assertFalse(allowed_setting("discord_reservation_token"))
        self.assertTrue(allowed_setting("discord_reservation_new_booking"))
        with self.assertRaises(ValueError):
            parse_profile(b"not-a-zip")
        with self.assertRaises(ValueError):
            build_profile({}, [], {"../secret": b"x"})
        valid = build_profile({"structure_name": "Autre FabLab"}, [], {})
        with zipfile.ZipFile(io.BytesIO(valid)) as archive:
            manifest = json.loads(archive.read("profile.json"))
        manifest["version"] = 999
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("profile.json", json.dumps(manifest))
        with self.assertRaises(ValueError):
            parse_profile(output.getvalue())
        invalid_modules = build_profile({
            "module_public_reservations": "1", "module_activities": "0",
        }, [], {})
        with self.assertRaisesRegex(ValueError, "nécessitent le module Activités"):
            parse_profile(invalid_modules)
        with self.assertRaisesRegex(ValueError, "nécessitent le module Facturation"):
            parse_profile(build_profile({"module_booking_slots": "1", "module_billing": "0"}, [], {}))
        for bad_settings in (
            {"module_activities": "maybe"},
            {"reservation_offer_hours": "999"},
            {"structure_timezone": "Mars/Phobos"},
            {"structure_website": "javascript:alert(1)"},
        ):
            with self.subTest(bad_settings=bad_settings), self.assertRaises(ValueError):
                parse_profile(build_profile(bad_settings, [], {}))

    def test_v250_custom_tariff_is_snapshotted_and_archived_without_history_loss(self):
        self.login_admin()
        self.client.get("/admin/reglages/structure")
        with self.client.session_transaction() as browser_session:
            csrf = browser_session["pin_csrf"]
        created = self.client.post("/admin/options/tarifs-personnalises", data={
            "csrf_token": csrf, "new_tariff_name": "Atelier spécial",
            "new_tariff_unit": "hourly", "new_tariff_amount": "22.50",
        }, follow_redirects=True)
        self.assertIn("Tarifs personnalisés enregistrés", created.get_data(as_text=True))
        with self.database() as database:
            tariff = database.execute("SELECT * FROM billing_tariff_catalog").fetchone()
        self.assertEqual(tariff["cents"], 2250)
        payload = {
            "quote_date": "2026-09-20", "client_contact": "Camille Durand",
            "client_structure": "Association Test", "address_line": "10 rue des Ateliers",
            "postal_code": "00000", "city": "Ville Fictive", "title": "Atelier spécial",
            "description": "Accompagnement ponctuel", "activity_date": "2026-10-15",
            "activity_start_time": "10:00", "activity_end_time": "11:00",
            "participants": "2", "rate_category": "normal", "rate_unit": "hourly",
            "custom_tariff_key": tariff["tariff_key"], "rate_quantity": "2",
            "travel_quantity": "0", "consumable_mode": "client", "consumable_quantity": "0",
        }
        saved = self.client.post("/admin/facturation/nouveau", data=payload, follow_redirects=True)
        self.assertIn("a été créé", saved.get_data(as_text=True))
        with self.database() as database:
            record = database.execute("SELECT * FROM billing_records ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual(record["amount_cents"], 4500)
        self.assertEqual(record["custom_tariff_name"], "Atelier spécial")
        self.client.post("/admin/options/tarifs-personnalises", data={
            "csrf_token": csrf, f"tariff_name_{tariff['tariff_key']}": "Nouveau nom",
            f"tariff_unit_{tariff['tariff_key']}": "hourly",
            f"tariff_amount_{tariff['tariff_key']}": "30",
            f"tariff_archived_{tariff['tariff_key']}": "1",
        })
        with self.database() as database:
            snapshot = database.execute("SELECT * FROM billing_records WHERE id=?", (record["id"],)).fetchone()
        self.assertEqual(snapshot["amount_cents"], 4500)
        self.assertEqual(snapshot["rate_unit_cents"], 2250)
        self.assertEqual(snapshot["custom_tariff_name"], "Atelier spécial")
        refused = self.client.post(
            f"/admin/options/tarifs-personnalises/{tariff['tariff_key']}/supprimer",
            data={"csrf_token": csrf}, follow_redirects=True,
        )
        self.assertIn("désactivez-le ou archivez-le", refused.get_data(as_text=True))
        quote = self.client.get(f"/admin/facturation/{record['id']}/devis.docx")
        with zipfile.ZipFile(io.BytesIO(quote.data)) as archive:
            self.assertIn("Atelier spécial", archive.read("word/document.xml").decode())

    def test_v250_documents_use_configured_identity_without_historical_brand(self):
        from app import get_database, write_setting
        self.login_admin()
        payload = {
            "quote_date": "2026-09-20", "client_contact": "Client Test",
            "client_structure": "Entreprise Exemple", "address_line": "1 rue Test",
            "postal_code": "75001", "city": "Paris", "title": "Atelier numérique",
            "description": "Accompagnement", "activity_date": "2026-10-15",
            "activity_start_time": "10:00", "activity_end_time": "11:00",
            "participants": "1", "rate_category": "normal", "rate_unit": "hourly",
            "rate_quantity": "1", "travel_quantity": "0", "consumable_mode": "client",
            "consumable_quantity": "0",
        }
        self.client.post("/admin/facturation/nouveau", data=payload)
        with self.app.app_context():
            database = get_database()
            record_id = database.execute("SELECT MAX(id) FROM billing_records").fetchone()[0]
            for key, value in {
                "name": "Atelier Libre", "short_name": "AtelierLibre",
                "description": "FabLab associatif", "address": "8 rue du Test, Paris",
                "legal_entity": "Association Atelier Libre", "billing_address": "8 rue du Test, Paris",
                "siret": "12345678901234", "iban": "FR7612345678901234567890123",
                "bic": "TESTFRPP", "account_holder": "Association Atelier Libre",
                "payment_terms": "Paiement sous 15 jours.",
            }.items():
                write_setting(database, f"structure_{key}", value)
            database.commit()
        quote = self.client.get(f"/admin/facturation/{record_id}/devis.docx")
        self.assertEqual(quote.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(quote.data)) as archive:
            document_xml = archive.read("word/document.xml").decode()
            footer_xml = "".join(archive.read(name).decode() for name in archive.namelist()
                                 if name.startswith("word/footer") and name.endswith(".xml"))
        self.assertIn("Atelier Libre", document_xml)
        self.assertIn("Association Atelier Libre", footer_xml)
        self.assertNotIn("Association Exemple", document_xml + footer_xml)
        self.assertEqual(self.client.get(f"/admin/facturation/{record_id}/devis.pdf").status_code, 200)
        directory = self.client.get("/admin/facturation/clients/export.xlsx")
        with zipfile.ZipFile(io.BytesIO(directory.data)) as archive:
            sheet = archive.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("Atelier Libre", sheet)
        self.assertNotIn("Atelier Exemple - Annuaire", sheet)

    def test_v250_rental_machine_cannot_be_deleted_after_quote(self):
        self.login_admin()
        self.client.get("/admin/reglages/structure")
        with self.client.session_transaction() as browser_session:
            csrf = browser_session["pin_csrf"]
        with self.database() as database:
            database.execute("INSERT INTO rental_catalog "
                "(machine_key,name,monthly_cents,deposit_cents,active,sort_order,created_at,updated_at) "
                "VALUES ('unused_machine','Machine libre',1000,5000,1,99,'2026-09-28','2026-09-28')")
        response = self.client.post("/admin/options/catalogue-location/unused_machine/supprimer",
                                    data={"csrf_token": csrf}, follow_redirects=True)
        self.assertIn("Machine sans historique supprimée", response.get_data(as_text=True))
        self.client.post("/admin/facturation/nouveau", data={
            "billing_type": "rental", "quote_date": "2026-09-20",
            "client_contact": "Client Test", "client_structure": "Entreprise Exemple",
            "address_line": "1 rue Test", "postal_code": "75001", "city": "Paris",
            "title": "Location Prusa", "description": "Location de machine",
            "activity_date": "2026-10-15", "activity_start_time": "10:00",
            "activity_end_time": "11:00", "rental_machine_key": "prusa_mk39",
            "rental_months": "1", "rental_end_date": "2026-11-15",
        })
        response = self.client.post("/admin/options/catalogue-location/prusa_mk39/supprimer",
                                    data={"csrf_token": csrf}, follow_redirects=True)
        self.assertIn("archivez-la", response.get_data(as_text=True))
        with self.database() as database:
            self.assertIsNotNone(database.execute("SELECT 1 FROM rental_catalog WHERE machine_key='prusa_mk39'").fetchone())


class DatabaseMigrationTestCase(unittest.TestCase):
    def test_v250_legacy_database_is_copied_before_migration(self):
        from app import resolve_database_path
        with tempfile.TemporaryDirectory(prefix="openfablab_v250_migration_") as directory:
            old_path = Path(directory) / "compteur_fablab.db"
            app = create_app({"TESTING": True, "DATABASE": str(old_path), "WEATHER_ENABLED": False})
            self.assertIsNotNone(app)
            with sqlite3.connect(old_path) as legacy:
                legacy.execute("PRAGMA user_version = 10")
                legacy.execute("INSERT INTO visitors(created_at) VALUES ('2026-09-28T10:00:00+00:00')")
            with mock.patch.dict(os.environ, {"OPENFABLAB_DATABASE": str(old_path)}):
                resolved = Path(resolve_database_path())
            self.assertEqual(resolved.name, "openfablab.db")
            self.assertTrue(old_path.exists())
            self.assertEqual(len(list(Path(directory).glob("openfablab-avant-migration-*.db"))), 1)
            with sqlite3.connect(resolved) as copied, sqlite3.connect(old_path) as original:
                self.assertEqual(copied.execute("SELECT COUNT(*) FROM visitors").fetchone()[0], 1)
                self.assertEqual(original.execute("SELECT COUNT(*) FROM visitors").fetchone()[0], 1)
                self.assertEqual(copied.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_v250_empty_canonical_file_cannot_hide_populated_legacy_database(self):
        from app import resolve_database_path
        with tempfile.TemporaryDirectory(prefix="openfablab_legacy_guard_") as directory:
            old = Path(directory) / "compteur_fablab.db"
            new = Path(directory) / "openfablab.db"
            create_app({"TESTING": True, "DATABASE": str(old), "WEATHER_ENABLED": False})
            sqlite3.connect(new).close()
            with mock.patch.dict(os.environ, {"OPENFABLAB_DATABASE": str(new)}):
                with self.assertRaisesRegex(RuntimeError, "ancienne base contient des données"):
                    resolve_database_path()
            with sqlite3.connect(old) as database:
                self.assertGreater(database.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)

    def test_v243_schema_nine_adds_only_security_events_and_is_replayable(self):
        with tempfile.TemporaryDirectory(prefix="compteur_fablab_migration_v244_") as directory:
            database_path = str(Path(directory) / "v243.db")
            config = {"TESTING": True, "DATABASE": database_path, "WEATHER_ENABLED": False}
            create_app(config)
            with sqlite3.connect(database_path) as database:
                database.execute("INSERT INTO visitors (created_at) VALUES (?)", (datetime.now(timezone.utc).isoformat(),))
                before = {table: database.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                          for table in ("users", "sessions", "visitors", "fablab_services", "billing_records", "billing_clients", "weather_snapshots")}
                database.execute("DROP TABLE security_events")
                database.execute("PRAGMA user_version = 9")
                database.commit()
            create_app(config)
            create_app(config)
            with sqlite3.connect(database_path) as database:
                after = {table: database.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in before}
                self.assertEqual(database.execute("PRAGMA user_version").fetchone()[0],17)
                self.assertEqual(database.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(database.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertTrue(database.execute("SELECT 1 FROM sqlite_master WHERE name='security_events'").fetchone())
                self.assertEqual(before, after)

    def test_existing_v01_database_is_migrated_without_data_loss(self):
        with tempfile.TemporaryDirectory(prefix="compteur_fablab_migration_") as directory:
            database_path = str(Path(directory) / "old_v01.db")
            database = sqlite3.connect(database_path)
            database.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    check_in TEXT NOT NULL,
                    check_out TEXT,
                    entry_method TEXT NOT NULL DEFAULT 'manual',
                    exit_method TEXT
                );
                CREATE TABLE visitors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL
                );
                """
            )
            database.execute(
                """
                INSERT INTO users (first_name, last_name, active, created_at)
                VALUES (?, ?, 1, ?)
                """,
                ("Victor", "Exemple", datetime.now(timezone.utc).isoformat()),
            )
            database.commit()
            database.close()

            create_app({"TESTING": True, "DATABASE": database_path})

            database = sqlite3.connect(database_path)
            migrated_user = database.execute(
                """
                SELECT public_id, first_name, last_name, category, gender,
                       city_normalized, nationality_normalized,
                       phone_country_code, phone
                FROM users
                """
            ).fetchone()
            schema_version = database.execute("PRAGMA user_version").fetchone()[0]
            database.close()

            self.assertEqual(
                migrated_user,
                ("1001", "Victor", "EXEMPLE", "user", None, None,
                 None, "+33", None),
            )
            self.assertEqual(schema_version,17)


    def test_v23_schema_migrates_to_v240_without_losing_rows(self):
        with tempfile.TemporaryDirectory(prefix="compteur_fablab_v23_migration_") as directory:
            database_path = str(Path(directory) / "v23.db")
            create_app({"TESTING": True, "DATABASE": database_path})
            with sqlite3.connect(database_path) as database:
                database.execute("DROP TABLE attendance_corrections")
                database.execute("PRAGMA user_version = 7")
                before = {
                    table: database.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "users", "sessions", "visitors", "fablab_services",
                        "billing_records", "billing_clients", "rental_catalog",
                    )
                }
                database.commit()

            create_app({"TESTING": True, "DATABASE": database_path})
            with sqlite3.connect(database_path) as database:
                after = {
                    table: database.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in before
                }
                schema_version = database.execute("PRAGMA user_version").fetchone()[0]
                audit_table = database.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'attendance_corrections'"
                ).fetchone()
                integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
                foreign_keys = database.execute("PRAGMA foreign_key_check").fetchall()
            self.assertEqual(after, before)
            self.assertEqual(schema_version,17)
            self.assertIsNotNone(audit_table)
            self.assertEqual(integrity, "ok")
            self.assertEqual(foreign_keys, [])

            # La migration doit être rejouable sur une base déjà au schéma 8.
            create_app({"TESTING": True, "DATABASE": database_path})
            with sqlite3.connect(database_path) as database:
                self.assertEqual(database.execute("PRAGMA user_version").fetchone()[0],17)
                self.assertEqual(
                    database.execute("SELECT COUNT(*) FROM attendance_corrections").fetchone()[0],
                    0,
                )

    def test_v242_schema_adds_weather_snapshots_without_losing_rows(self):
        with tempfile.TemporaryDirectory(
            prefix="compteur_fablab_v242_migration_"
        ) as directory:
            database_path = str(Path(directory) / "v242.db")
            create_app({"TESTING": True, "DATABASE": database_path})
            with sqlite3.connect(database_path) as database:
                database.execute("DROP TABLE weather_snapshots")
                database.execute("PRAGMA user_version = 8")
                before = {
                    table: database.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                    for table in (
                        "users", "sessions", "visitors", "fablab_services",
                        "billing_records", "billing_clients", "rental_catalog",
                    )
                }
                database.commit()

            create_app({"TESTING": True, "DATABASE": database_path})
            with sqlite3.connect(database_path) as database:
                after = {
                    table: database.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                    for table in before
                }
                table = database.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table' AND name = 'weather_snapshots'
                    """
                ).fetchone()
                columns = {
                    row[1]
                    for row in database.execute(
                        "PRAGMA table_info(weather_snapshots)"
                    ).fetchall()
                }
                schema_version = database.execute("PRAGMA user_version").fetchone()[0]
                integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
                foreign_keys = database.execute("PRAGMA foreign_key_check").fetchall()

            self.assertEqual(after, before)
            self.assertIsNotNone(table)
            self.assertEqual(
                columns,
                {
                    "id", "quarter_start", "temperature_c",
                    "apparent_temperature_c", "weather_code",
                    "precipitation_mm", "created_at",
                },
            )
            self.assertEqual(schema_version,17)
            self.assertEqual(integrity, "ok")
            self.assertEqual(foreign_keys, [])


class NasDeploymentTestCase(unittest.TestCase):
    def test_container_paths_and_secret_are_persistent(self):
        with tempfile.TemporaryDirectory(prefix="openfablab_nas_") as directory:
            data_directory = Path(directory) / "data"
            database_path = data_directory / "openfablab.db"
            secret_path = data_directory / ".secret_key"
            previous_values = {
                name: os.environ.get(name)
                for name in (
                    "COMPTEUR_DATABASE",
                    "COMPTEUR_SECRET_KEY",
                    "COMPTEUR_SECRET_KEY_FILE",
                )
            }
            os.environ["COMPTEUR_DATABASE"] = str(database_path)
            os.environ["COMPTEUR_SECRET_KEY"] = ""
            os.environ["COMPTEUR_SECRET_KEY_FILE"] = str(secret_path)
            try:
                first_app = create_app({"TESTING": True})
                first_client = first_app.test_client()
                self.assertEqual(first_client.get("/sante").status_code, 200)
                first_client.post("/visiteurs")

                second_app = create_app({"TESTING": True})
                self.assertEqual(first_app.config["SECRET_KEY"], second_app.config["SECRET_KEY"])
            finally:
                for name, value in previous_values.items():
                    if value is None:
                        os.environ.pop(name, None)
                    else:
                        os.environ[name] = value

            self.assertTrue(database_path.exists())
            self.assertTrue(secret_path.exists())
            with sqlite3.connect(database_path) as database:
                visitor_count = database.execute(
                    "SELECT COUNT(*) FROM visitors"
                ).fetchone()[0]
            self.assertEqual(visitor_count, 1)

    def test_v04_database_adds_voluntary_category_without_history_loss(self):
        with tempfile.TemporaryDirectory(prefix="compteur_fablab_v04_") as directory:
            database_path = str(Path(directory) / "old_v04.db")
            database = sqlite3.connect(database_path)
            database.executescript(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    public_id TEXT NOT NULL,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    category TEXT NOT NULL DEFAULT 'user'
                        CHECK (category IN ('user', 'volunteer', 'fabmanager', 'intern', 'staff')),
                    birth_year INTEGER,
                    gender TEXT,
                    city TEXT,
                    city_normalized TEXT,
                    postal_code TEXT,
                    nationality TEXT,
                    nationality_normalized TEXT,
                    email TEXT,
                    phone TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    check_in TEXT NOT NULL,
                    check_out TEXT,
                    entry_method TEXT NOT NULL DEFAULT 'manual',
                    exit_method TEXT
                );
                CREATE TABLE visitors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL
                );
                CREATE TRIGGER sessions_statistics_after_insert
                AFTER INSERT ON sessions
                BEGIN
                    UPDATE sessions
                    SET user_id = (SELECT id FROM users WHERE id = NEW.user_id)
                    WHERE id = NEW.id;
                END;
                PRAGMA user_version = 4;
                """
            )
            created_at = datetime.now(timezone.utc).isoformat()
            cursor = database.execute(
                """
                INSERT INTO users (
                    public_id, first_name, last_name, active, category, phone,
                    created_at
                ) VALUES ('1001', 'Camille', 'Test', 1, 'volunteer',
                          '+33 6 10 10 10 10', ?)
                """,
                (created_at,),
            )
            database.execute(
                """
                INSERT INTO sessions (user_id, check_in, entry_method)
                VALUES (?, ?, 'manual')
                """,
                (cursor.lastrowid, created_at),
            )
            database.commit()
            database.close()

            create_app({"TESTING": True, "DATABASE": database_path})

            database = sqlite3.connect(database_path)
            migrated_user = database.execute(
                """
                SELECT last_name, category, phone_country_code, phone
                FROM users WHERE public_id = '1001'
                """
            ).fetchone()
            session_count = database.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            schema_version = database.execute("PRAGMA user_version").fetchone()[0]
            database.execute(
                """
                INSERT INTO users (
                    public_id, first_name, last_name, active, category, created_at
                ) VALUES ('1002', 'Alex', 'Volontaire', 1, 'voluntary', ?)
                """,
                (created_at,),
            )
            database.commit()
            database.close()

            self.assertEqual(
                migrated_user,
                ("TEST", "volunteer", "+33", "06 10 10 10 10"),
            )
            self.assertEqual(session_count, 1)
            self.assertEqual(schema_version,17)


if __name__ == "__main__":
    unittest.main()
