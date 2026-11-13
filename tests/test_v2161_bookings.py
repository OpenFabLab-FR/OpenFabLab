"""Exercise the shared footer and the real animation bookings page, offline."""
from datetime import date, timedelta
import re
import unittest

from tests import test_app as fixture


class BookingsHotfix(unittest.TestCase):
    setUp = fixture.OpenFabLabTestCase.setUp
    tearDown = fixture.OpenFabLabTestCase.tearDown
    database = fixture.OpenFabLabTestCase.database
    login_admin = fixture.OpenFabLabTestCase.login_admin
    _login_token = fixture.OpenFabLabTestCase._login_token
    _animation_booking_row = fixture.OpenFabLabTestCase._animation_booking_row

    def animation(self, title, *, capacity=3, configured=True, past=False):
        day = (date.today() + timedelta(days=-14 if past else 30)).isoformat()
        with self.database() as db:
            db.execute("UPDATE app_settings SET value='1' WHERE key='module_public_reservations'")
            service = db.execute(
                "INSERT INTO fablab_services(service_type,title,service_date,start_time,end_time,"
                "duration_minutes,expected_participants,created_at,updated_at) "
                "VALUES('animation',?,?,'14:00','16:00',120,?,?,?)",
                (title, day, capacity, day, day),
            ).lastrowid
            if configured:
                db.execute(
                    "INSERT INTO animation_reservation_config(service_id,enabled,environment,capacity,updated_at) "
                    "VALUES(?,1,'test',?,?)", (service, capacity, day),
                )
        return service

    @staticmethod
    def url(service):
        return f"/admin/animations/{service}/inscriptions"

    def assert_version(self, response, technical="V2.16.1"):
        self.assertIn('<span class="footer-version">V2.16</span>', response.text)
        self.assertIn(f'data-runtime-version="{technical}"', response.text)

    def test_bookings_render_for_both_roles_on_schema_28_without_rewriting_history(self):
        from tests.test_families import FamilyTests

        empty = self.animation("Atelier fictif sans inscrit")
        no_config = self.animation("Animation fictive hors ligne", configured=False)
        future = self.animation("Animation fictive avec inscrit")
        full = self.animation("Animation fictive complète", capacity=1)
        waitlist = self.animation("Animation fictive liste attente", capacity=1)
        past = self.animation("Animation fictive passée", past=True)
        self._animation_booking_row(future)
        self._animation_booking_row(full)
        self._animation_booking_row(waitlist)
        self._animation_booking_row(waitlist, "waitlisted")
        self._animation_booking_row(past, presence=1)
        self._animation_booking_row(past, presence=0)
        self._animation_booking_row(past, "cancelled")
        demo = FamilyTests()
        demo.setUp()
        self.addCleanup(demo.doCleanups)
        result = demo.book([demo.a, demo.c], staff=True)
        self.assertEqual(result["status"], "confirmed")
        with self.database() as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 28)
            before = [tuple(row) for row in db.execute("SELECT * FROM animation_bookings ORDER BY external_uuid")]

        for pin, role in (("1379", "admin"), ("8642", "moderator")):
            self.client.post("/admin/deconnexion")
            self.login_admin(pin)
            with self.client.session_transaction() as session:
                self.assertEqual(session["access_role"], role)
            listing = self.client.get("/admin/activites", follow_redirects=True)
            self.assertIn(f'href="{self.url(future)}"', listing.text)
            for service_id, content in (
                (empty, ("Aucun participant dans ce groupe.", "Ajouter des participants")),
                (no_config, ("Aucun participant dans ce groupe.",)),
                (future, ("Anne TEST", 'value="present"', 'value="absent"')),
                (full, ("Anne TEST", "<strong>0</strong><span>Places disponibles")),
                (waitlist, ("booking-waitlisted", "Liste d’attente")),
                (past, ("presence-present", "presence-absent", "Annulée")),
            ):
                with self.subTest(role=role, service=service_id):
                    response = self.client.get(self.url(service_id))
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("Suivi de l’animation", response.text)
                    for marker in content:
                        self.assertIn(marker, response.text)
                    self.assertEqual(">Modifier</a>" in response.text, role == "admin")
                    self.assert_version(response)
            demo.f.client.post("/admin/deconnexion")
            demo.f.login_admin(pin)
            page = demo.f.client.get(self.url(demo.service))
            self.assertEqual(page.status_code, 200)
            self.assertIn("Même demande · 2 participants", page.text)
            self.assertIn("Responsable :", page.text)
            self.assert_version(page)
        with self.database() as db:
            self.assertEqual([tuple(row) for row in db.execute("SELECT * FROM animation_bookings ORDER BY external_uuid")], before)
        self.client.post("/admin/deconnexion")
        self.assertTrue(self.client.get(self.url(future)).location.endswith("/admin/connexion"))

    def test_staff_presence_and_cancellation_forms_keep_history(self):
        service = self.animation("Animation fictive de suivi", capacity=2, past=True)
        person = self._animation_booking_row(service)
        other = self._animation_booking_row(service)
        for pin, booking, action, css, expected in (
            ("8642", person, "present", "presence-present", ("confirmed", 1)),
            ("1379", other, "absent", "presence-absent", ("confirmed", 0)),
            ("1379", other, "cancel", "booking-closed", ("cancelled", 0)),
        ):
            self.client.post("/admin/deconnexion")
            self.login_admin(pin)
            url = self.url(service)
            page = self.client.get(url)
            self.assertIn(f'value="{action}"', page.text)
            token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)[1]
            self.assertEqual(self.client.post(url + f"/{booking}/action", data={"action": action}).status_code, 400)
            page = self.client.post(url + f"/{booking}/action", data={"action": action, "csrf_token": token},
                                    follow_redirects=True)
            self.assertEqual(page.status_code, 200)
            self.assertIn(css, page.text)
            with self.database() as db:
                self.assertEqual(tuple(db.execute("SELECT status,is_present FROM animation_bookings WHERE external_uuid=?",
                                                  (booking,)).fetchone()), expected)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM animation_bookings WHERE service_id=?", (service,)).fetchone()[0], 2)
        with self.database() as db:
            self.assertEqual(db.execute("SELECT actual_participants FROM fablab_services WHERE id=?", (service,)).fetchone()[0], 1)

    def test_kiosk_admin_public_error_and_technical_versions(self):
        for route, status in (("/", 200), ("/gestion-des-donnees", 200), ("/fictional-not-found", 404)):
            page = self.client.get(route, follow_redirects=True)
            self.assertEqual(page.status_code, status)
            self.assert_version(page)
        self.login_admin()
        for route in ("/admin/activites", "/admin/reglages/systeme/mises-a-jour"):
            page = self.client.get(route, follow_redirects=True)
            self.assertEqual(page.status_code, 200)
            self.assert_version(page)
        self.assertIn("2.16.1", self.client.get("/admin/reglages/systeme/mises-a-jour").text)
        self.assertIn('<span data-update-installed>V2.16.1</span>',
                      self.client.get("/admin/reglages/systeme/mises-a-jour").text)
        for version in ("V2.16.0", "V2.16.42"):
            with self.subTest(version=version):
                self.app.config["APP_VERSION"] = version
                self.assert_version(self.client.get("/"), version)

    def test_create_edit_and_render_calendar_resources_statistics(self):
        self.login_admin()
        day = (date.today() - timedelta(days=1)).isoformat()
        form = dict(title="Atelier fictif initial", service_date=day, start_time="14:00",
                    end_time="16:00", expected_participants="4", minimum_age="10")
        self.assertIn('name="title"', self.client.get("/admin/animations/nouveau").text)
        created = self.client.post("/admin/animations/nouveau", data=form, follow_redirects=True)
        self.assertIn(form["title"], created.text)
        with self.database() as db:
            service = db.execute("SELECT id FROM fablab_services WHERE title=?", (form["title"],)).fetchone()[0]
        title = "Atelier fictif modifié"
        edit = f"/admin/animations/{service}/modifier"
        self.assertIn(form["title"], self.client.get(edit).text)
        self.assertIn(title, self.client.post(edit, data=dict(form, title=title), follow_redirects=True).text)
        booking = self._animation_booking_row(service)
        page = self.client.get(self.url(service))
        self.assertIn(title, page.text)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)[1]
        self.assertIn("presence-present", self.client.post(self.url(service) + f"/{booking}/action",
                      data=dict(csrf_token=token, action="present"), follow_redirects=True).text)
        calendar = self.client.get(f"/admin/calendrier?view=month&date={day}")
        self.assertIn(title, calendar.text)
        resources = self.client.get("/admin/ressources/reservations", follow_redirects=True)
        self.assertIn("Réserver une ressource", resources.text)
        stats = self.client.get(f"/admin/frequentation/statistiques?year={day[:4]}", follow_redirects=True)
        self.assertIn("<strong>1</strong><span>Participations renseignées aux animations passées", stats.text)
        self.assertIn(title, self.client.get(f"/admin/exports/animations.csv?year={day[:4]}").text)
