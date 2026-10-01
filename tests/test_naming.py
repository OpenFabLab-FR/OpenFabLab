"""Current OpenFabLab names, safe historical migration and portable deployment."""

import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from werkzeug.test import Client
from werkzeug.wrappers import Response
from tests import test_app as fixtures
from app import (create_app, create_deployment_application, get_database,
                 initialize_database, load_automatic_backup_settings,
                 read_setting, resolve_database_path, run_automatic_backup, write_setting)

ROOT = Path(__file__).resolve().parents[1]
OLD_NAMES = re.compile(r"CompteurPassage|compteur[-_]fablab|CompteurFablab|Compteur Fablab", re.I)


class NamingConsistencyTestCase(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.OpenFabLabTestCase()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def test_new_installation_creates_only_canonical_paths_and_neutral_settings(self):
        from pin_security import has_pin, set_pin
        with tempfile.TemporaryDirectory(prefix="openfablab_new_names_") as directory:
            root = Path(directory)
            path = root / "openfablab.db"
            with mock.patch.dict(os.environ, {"OPENFABLAB_DATABASE": str(path)}):
                self.assertEqual(resolve_database_path(), str(path))
                application = create_app({"TESTING": True, "DATABASE": str(path), "ADMIN_PIN": None,
                                          "MODERATOR_PIN": None, "SEED_DEMO_USERS": False,
                                          "WEATHER_ENABLED": False, "AUTO_CLOSURE_WORKER": False,
                                          "BACKUP_ROOT": str(root / "backups"),
                                          "BACKUP_DISPLAY_ROOT": "/server/backups"})
            self.assertTrue(path.is_file())
            self.assertFalse(has_pin(path, "admin"))
            with application.app_context():
                database = get_database()
                settings = dict(database.execute("SELECT key,value FROM app_settings").fetchall())
                self.assertEqual(settings["automatic_backup_subdirectory"], "OpenFabLab")
                self.assertFalse(OLD_NAMES.search(json.dumps(settings, ensure_ascii=False)))
                self.assertNotIn("FougèresLab", json.dumps(settings, ensure_ascii=False))
                self.assertEqual(database.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(database.execute("PRAGMA foreign_key_check").fetchall(), [])
            set_pin(path, "admin", "1379")  # Explicit fixture choice, never an application default.
            client = application.test_client()
            with client.session_transaction() as session:
                session["access_role"] = "admin"
            page = client.get("/admin/reglages/donnees").get_data(as_text=True)
            self.assertIn("Sous-dossier des sauvegardes NAS", page)
            self.assertIn("/server/backups/OpenFabLab", page)
            self.assertIn("répertoire de sauvegarde monté", page)
            self.assertNotIn("/volume1", page)
            self.assertFalse(OLD_NAMES.search(page))
            self.assertFalse(any(OLD_NAMES.search(str(item.relative_to(root))) for item in root.rglob("*")))

    def test_exact_historical_backup_default_migrates_without_touching_old_files(self):
        root = Path(self.fixture.temporary_directory.name) / "backups"
        historical = root / "CompteurPassage"
        historical.mkdir(parents=True)
        old_file = historical / "compteur-fablab-sauvegarde-2026-09-28_10-30.db"
        with self.fixture.database() as database, sqlite3.connect(old_file) as snapshot:
            database.backup(snapshot)
        before = hashlib.sha256(old_file.read_bytes()).digest()
        with self.fixture.app.app_context():
            database = get_database()
            write_setting(database, "automatic_backup_subdirectory", "CompteurPassage")
            write_setting(database, "automatic_backup_last_filename", old_file.name)
            database.commit()
            volumes = {table: database.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                       for table in ("users", "sessions", "visitors", "billing_records")}
            initialize_database()
            initialize_database()
            self.assertEqual(read_setting(database, "automatic_backup_subdirectory"), "OpenFabLab")
            self.assertEqual(read_setting(database, "automatic_backup_last_filename"), old_file.name)
            self.assertEqual(volumes, {table: database.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                                      for table in volumes})
            self.assertEqual(database.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(database.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(hashlib.sha256(old_file.read_bytes()).digest(), before)
        self.assertTrue(historical.is_dir())
        self.assertFalse((root / "OpenFabLab").exists())  # Migration changes a setting, not directories.

    def test_custom_backup_destinations_are_preserved_exactly(self):
        with self.fixture.app.app_context():
            database = get_database()
            for value in ("AtelierLibre", "CompteurPassage/Essais", "compteurpassage", " CompteurPassage "):
                with self.subTest(value=value):
                    write_setting(database, "automatic_backup_subdirectory", value)
                    database.commit()
                    initialize_database()
                    self.assertEqual(read_setting(database, "automatic_backup_subdirectory"), value)

    def test_new_automatic_and_downloaded_backups_use_openfablab(self):
        self.fixture.login_admin()
        with self.fixture.app.app_context():
            database = get_database()
            write_setting(database, "automatic_backup_enabled", "1")
            database.commit()
            settings = load_automatic_backup_settings(database, self.fixture.app)
            self.assertEqual(settings["subdirectory"], "OpenFabLab")
            backup = run_automatic_backup(database, self.fixture.app,
                                          now=datetime(2026, 9, 30, 8, 30, tzinfo=timezone.utc), force=True)
            self.assertEqual(backup.parent.name, "OpenFabLab")
            self.assertRegex(backup.name, r"^openfablab-sauvegarde-2026-09-30_10-30-V2\.6\.1\.db$")
            self.assertFalse(OLD_NAMES.search(backup.name))
        with sqlite3.connect(backup) as database:
            self.assertEqual(database.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(database.execute("PRAGMA foreign_key_check").fetchall(), [])
        response = self.fixture.client.get("/admin/sauvegarde/exporter")
        self.assertTrue(response.data.startswith(b"SQLite format 3"))
        self.assertIn("openfablab-sauvegarde-", response.headers["Content-Disposition"])
        self.assertFalse(OLD_NAMES.search(response.headers["Content-Disposition"]))

    def test_legacy_named_backup_remains_restorable_and_source_is_unchanged(self):
        self.fixture.login_admin()
        root = Path(self.fixture.temporary_directory.name)
        source = root / "compteur_fablab.db"
        with self.fixture.database() as database, sqlite3.connect(source) as copied:
            database.backup(copied)
            before_users = database.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        with sqlite3.connect(source) as database:
            database.execute("PRAGMA user_version=10")
            database.execute("UPDATE app_settings SET value='CompteurPassage' WHERE key='automatic_backup_subdirectory'")
        original = source.read_bytes()
        response = self.fixture.client.post("/admin/reglages/donnees", data={
            "database_file": (io.BytesIO(original), source.name), "confirmation": "RESTAURER"
        }, content_type="multipart/form-data", follow_redirects=True)
        self.assertIn("La sauvegarde a été restaurée", response.get_data(as_text=True))
        self.assertEqual(source.read_bytes(), original)
        with self.fixture.database() as database:
            self.assertEqual(database.execute("PRAGMA user_version").fetchone()[0], 13)
            self.assertEqual(database.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(database.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(database.execute("SELECT COUNT(*) FROM users").fetchone()[0], before_users)
            self.assertEqual(database.execute("SELECT value FROM app_settings WHERE key='automatic_backup_subdirectory'").fetchone()[0], "OpenFabLab")
        self.assertTrue(list(root.glob("openfablab-avant-restauration-*.db")))

    def test_profile_filename_keeps_openfablab_format(self):
        self.fixture.login_admin()
        with self.fixture.app.app_context():
            database = get_database()
            write_setting(database, "structure_name", "Atelier Libre")
            database.commit()
        response = self.fixture.client.get("/admin/profil/exporter")
        self.assertEqual(response.status_code, 200)
        self.assertIn(".openfablab-profile.zip", response.headers["Content-Disposition"])
        self.assertFalse(OLD_NAMES.search(response.headers["Content-Disposition"]))
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            self.assertEqual(json.loads(archive.read("profile.json"))["format"], "openfablab-profile")

    def test_current_prefix_and_historical_shortcut_redirects_keep_stat(self):
        with mock.patch.dict(os.environ, {"OPENFABLAB_URL_PREFIX": "/stat", "COMPTEUR_URL_PREFIX": "/legacy"}):
            client = Client(create_deployment_application(self.fixture.app), Response)
        self.assertEqual(client.get("/stat/sante").status_code, 200)
        self.assertEqual(client.get("/sante").status_code, 404)
        self.assertEqual(client.get("/legacy/sante").status_code, 404)
        for size in (192, 512):
            response = client.get(f"/stat/static/icons/compteur-fablab-{size}.png")
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers["Location"], f"/stat/static/icons/OpenFabLab-icon-{size}.png")
            icon = client.get(response.headers["Location"])
            try:
                self.assertEqual(icon.status_code, 200)
            finally:
                icon.close()
        self.assertEqual(client.get("/stat/static/icons/compteur-fablab-128.png").status_code, 404)
        manifest = json.loads(client.get("/stat/manifest.webmanifest").data)
        self.assertFalse(OLD_NAMES.search(json.dumps(manifest)))

    def test_compose_is_portable_and_docker_copies_existing_pdf_module(self):
        compose = (ROOT / "compose.yaml").read_text()
        self.assertTrue(compose.startswith("name: openfablab\n"))
        for value in ("image: openfablab:v2.6.1", "container_name: openfablab", '"5080:8000"',
                      "OPENFABLAB_URL_PREFIX: /stat", "OPENFABLAB_DATABASE: /data/openfablab.db",
                      "./data:/data", "${OPENFABLAB_BACKUP_HOST_ROOT:-./backups}:/nas-backups"):
            self.assertIn(value, compose)
        self.assertNotIn("/volume1", compose)
        self.assertFalse(OLD_NAMES.search(compose))
        self.assertIn("animation_report.py", (ROOT / "Dockerfile").read_text())
        documentation = (ROOT / 'docs/installation.md').read_text()
        self.assertIn('./data:/data',documentation)
        self.assertIn('openfablab.db',documentation)
        self.assertNotIn('/volume1',documentation)

    def test_distribution_creates_no_legacy_named_files(self):
        from build_openfablab import build
        with tempfile.TemporaryDirectory(prefix="openfablab_distribution_names_") as directory:
            output = build(Path(directory) / "OpenFabLab-2.6.1.zip")
            with zipfile.ZipFile(output) as archive:
                self.assertIsNone(archive.testzip())
                for name in archive.namelist():
                    self.assertFalse(OLD_NAMES.search(name), name)
                    self.assertNotIn("Ressources/", name)
                    self.assertNotIn("Saves/", name)
                    self.assertNotIn("data/", name)
                self.assertIn("static/icons/OpenFabLab-icon-192.png", archive.namelist())
                self.assertIn("animation_report.py", archive.namelist())
