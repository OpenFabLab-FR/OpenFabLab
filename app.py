"""Application locale OpenFabLab de suivi et de gestion de fablab."""

import csv
import hashlib
import hmac
import html
import io
import json
import os
import re
import secrets
import shutil
import sqlite3
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo
from uuid import uuid4
from PIL import Image, UnidentifiedImageError

import resvg_py
import segno
from openfablab import __version__
from evolution_schema import (backup_before_evolution, migrate as migrate_evolution,
                              categories, default_category, category_label as dynamic_category_label)

from flask import (
    Flask,
    Response,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from billing import (
    RENTAL_CATALOG as DEFAULT_RENTAL_CATALOG,
    compute_total_cents,
    generate_client_directory_pdf,
    generate_client_directory_xlsx,
    generate_document_docx,
    generate_document_pdf,
    generate_facdepot_pdf,
    generate_facdepot_xlsx,
    status_label as billing_status_label,
)
from calendar_export import build_ics_event
from annual_report import generate_activity_report_docx, generate_activity_report_pdf
from animation_report import generate_animation_bookings_pdf
from animation_slots import generate_slots, save_slots, slots_summary, slot_label
from pin_security import (check_pin, consume_recovery_token, credential_path,
                          has_pin, issue_recovery_token, set_pin, token_status,
                          valid_pin)
from profile_archive import (MAX_ARCHIVE_BYTES, build_profile, parse_profile)
from reservations_sync import (enqueue_animation, enqueue_booking_command, load_sync_secret,
                               run_sync_cycle, save_sync_secret, sync_secret_path,
                               sync_error_label, booking_counts, booking_presence,
                               booking_reservation_status, booking_capacity_used,
                               pending_confirmation_ids, sync_interval_seconds)


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "openfablab.db"
PARIS_TIMEZONE = ZoneInfo("Europe/Paris")
ALLOWED_GENDERS = {"female", "male", "non_binary"}
CATEGORY_LABELS = {
    "user": "Usager",
    "volunteer": "Bénévole",
    "voluntary": "Volontaire",
    "fabmanager": "Fabmanager",
    "intern": "Stagiaire",
    "staff": "Personnel",
}
PRESENCE_METHOD_LABELS = {
    "manual": "ID",
    "id": "ID",
    "qr": "QR",
    "automatic": "Auto",
    "admin": "Admin",
    "list": "Liste",
    "departure": "Départ",
    "anonymous": "Anonyme",
}
GENDER_LABELS = {
    "female": "Femme",
    "male": "Homme",
    "non_binary": "Non-binaire",
    None: "Inconnu",
}
ALLOWED_CATEGORIES = set(CATEGORY_LABELS)
DISPLAY_CAPACITY = 10
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_PATTERN = re.compile(r"^[0-9+().\-\s]+$")
PHONE_COUNTRY_CODE_PATTERN = re.compile(r"^(?:\+|00)\d{1,4}$")
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
WEEKDAYS = (
    ("monday", "Lundi"),
    ("tuesday", "Mardi"),
    ("wednesday", "Mercredi"),
    ("thursday", "Jeudi"),
    ("friday", "Vendredi"),
    ("saturday", "Samedi"),
    ("sunday", "Dimanche"),
)
DEFAULT_OPENLAB_SCHEDULE = {
    "monday": ("", ""),
    "tuesday": ("14:00", "17:00"),
    "wednesday": ("09:00", "12:00"),
    "thursday": ("", ""),
    "friday": ("14:00", "17:00"),
    "saturday": ("09:30", "13:00"),
    "sunday": ("", ""),
}
HOME_THEMES = {
    "classic": {
        "label": "Classique",
        "description": "L’interface claire et sobre utilisée actuellement.",
    },
    "dark": {
        "label": "Dark",
        "description": "Une interface noire à faible luminosité, adaptée aux écrans OLED.",
    },
    "halloween": {
        "label": "Halloween",
        "description": "Une nuit violette animée, avec lune, chauves-souris et citrouilles.",
    },
    "christmas": {
        "label": "Noël",
        "description": "Une ambiance chaleureuse rouge et sapin, avec neige animée.",
    },
    "easter": {
        "label": "Pâques",
        "description": "Des couleurs printanières, des œufs décorés et des fleurs animées.",
    },
    "valentine": {
        "label": "St Valentin",
        "description": "Une ambiance tendre rose et bordeaux, animée de cœurs et de messages.",
    },
    "summer": {
        "label": "Summer",
        "description": "Une escapade estivale entre ciel bleu, sable chaud et bord de mer.",
    },
    "steampunk": {
        "label": "Steampunk",
        "description": "Un atelier mécanique haut de gamme, entre cuivre, laiton et engrenages animés.",
    },
}
MODULE_LABELS = {
    "frequency": "Fréquentation",
    "users": "Usagers",
    "activities": "Activités",
    "resources": "Ressources",
    "authorizations": "Formations et habilitations",
    "public_reservations": "Réservations publiques",
    "booking_slots": "Créneaux réservables",
    "rentals": "Locations de machines",
    "billing": "Facturation",
    "weather": "Météo",
    "discord": "Notifications Discord",
}
from branding import (LOGO_KINDS, VISIBILITY_KEYS, RESOURCE_USAGE_KEYS, BADGE_FILENAME, validate_badge_template,
                      badge_source, outline_private_text, migrate_branding_settings, logo_status)

STRUCTURE_FIELDS = {
    "name": ("Nom de la structure", 120),
    "short_name": ("Nom court", 60),
    "description": ("Description", 240),
    "address": ("Adresse", 240),
    "city": ("Commune", 120),
    "postal_code": ("Code postal", 20),
    "email": ("E-mail", 254),
    "phone": ("Téléphone", 40),
    "website": ("Site web", 240),
    "privacy_policy_url": ("Page de gestion des données", 240),
    "country": ("Pays", 80),
    "timezone": ("Fuseau horaire", 80),
    "latitude": ("Latitude de la structure", 24),
    "longitude": ("Longitude de la structure", 24),
    "color": ("Couleur principale", 7),
    "legal_entity": ("Entité juridique", 180),
    "data_controller": ("Responsable du traitement (personne morale)", 180),
    "data_controller_address": ("Adresse du responsable du traitement", 500),
    "data_controller_representative": ("Représentant", 180),
    "data_controller_representative_role": ("Fonction du représentant", 240),
    "dpo": ("DPO / délégué à la protection des données", 500),
    "dpo_email": ("E-mail du DPO", 254),
    "dpo_phone": ("Téléphone du DPO", 40),
    "billing_address": ("Adresse de facturation", 500),
    "siret": ("SIRET", 14),
    "vat_number": ("Numéro de TVA", 40),
    "vat_note": ("Mention de TVA sur les documents", 240),
    "iban": ("IBAN", 60),
    "bic": ("BIC", 20),
    "account_holder": ("Titulaire du compte / régie", 180),
    "payment_terms": ("Conditions de règlement", 600),
    "payment_days": ("Délai de règlement en jours", 3),
    "regie_contact": ("Coordonnées de la régie", 240),
    "signer_name": ("Nom du signataire des bilans", 120),
    "rental_terms": ("Conditions particulières de location", 8000),
}
DATABASE_MAINTENANCE_LOCK = threading.Lock()
RESERVATION_SYNC_LOCK = threading.Lock()
BADGE_TEMPLATE_SVG = BASE_DIR / "badge_templates" / "OpenFabLab-template.svg"
INITIAL_DEMO_SETTING = "initial_demo_users_created"
WEATHER_CACHE_LOCK = threading.Lock()
WEATHER_CACHE = {"expires_at": 0.0, "value": None}
COMMUNE_CACHE_LOCK = threading.Lock()
COMMUNE_CACHE = {}
WEATHER_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
ATTENDANCE_PEAK_COLOR = "#c14962"
ENGRAVING_COLOR = "#ff0000"
DISCORD_DEFAULTS = {
    "bot_name": "OpenFabLab",
    "arrival_message": "🟢 {name} est là.",
    "departure_message": "🔴 {name} s'en va.",
    "visitor_message": "🟡 Un visiteur est là.",
    "retention_message": "🟠 {name} : {action} prévue le {date}.",
    "invoice_overdue_message": (
        "🔔 La facture {invoice_number} de {client}, envoyée le {sent_date}, "
        "attend son règlement depuis 30 jours."
    ),
    "monthly_animations_message": (
        "📅 Pensez à renseigner les animations réalisées en {month} et à exporter la base de données ailleurs."
    ),
}
RESERVATION_DISCORD_OPTIONS = {
    "reservation_confirmed": ("new_booking", "Nouvelle réservation"),
    "reservation_waitlisted": ("waitlist_entry", "Nouvelle entrée en liste d’attente"),
    "reservation_cancelled": ("cancellation", "Réservation annulée"),
    "offer_pending": ("offer_proposed", "Place proposée"),
    "offer_accepted": ("offer_accepted", "Place acceptée"),
    "email_failed": ("email_error", "Erreur d’envoi d’un e-mail de réservation"),
}
RESERVATION_DISCORD_FLAGS = (
    "new_booking", "waitlist_entry", "cancellation", "offer_proposed",
    "offer_accepted", "link_review", "animation_full", "email_error", "sync_error",
)
FRENCH_MONTH_NAMES = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)
COUNTRY_NAMES = (
    "Afghanistan", "Afrique du Sud", "Albanie", "Algérie", "Allemagne",
    "Andorre", "Angola", "Antigua-et-Barbuda", "Arabie saoudite", "Argentine",
    "Arménie", "Australie", "Autriche", "Azerbaïdjan", "Bahamas", "Bahreïn",
    "Bangladesh", "Barbade", "Belgique", "Belize", "Bénin", "Bhoutan",
    "Biélorussie", "Birmanie", "Bolivie", "Bosnie-Herzégovine", "Botswana",
    "Brésil", "Brunei", "Bulgarie", "Burkina Faso", "Burundi", "Cambodge",
    "Cameroun", "Canada", "Cap-Vert", "Chili", "Chine", "Chypre", "Colombie",
    "Comores", "Corée du Nord", "Corée du Sud", "Costa Rica", "Côte d’Ivoire",
    "Croatie", "Cuba", "Danemark", "Djibouti", "Dominique", "Égypte",
    "Émirats arabes unis", "Équateur", "Érythrée", "Espagne", "Estonie",
    "Eswatini", "États-Unis", "Éthiopie", "Fidji", "Finlande", "France",
    "Gabon", "Gambie", "Géorgie", "Ghana", "Grèce", "Grenade", "Guatemala",
    "Guinée", "Guinée-Bissau", "Guinée équatoriale", "Guyana", "Haïti",
    "Honduras", "Hongrie", "Îles Marshall", "Îles Salomon", "Inde", "Indonésie",
    "Irak", "Iran", "Irlande", "Islande", "Israël", "Italie", "Jamaïque",
    "Japon", "Jordanie", "Kazakhstan", "Kenya", "Kirghizistan", "Kiribati",
    "Koweït", "Laos", "Lesotho", "Lettonie", "Liban", "Liberia", "Libye",
    "Liechtenstein", "Lituanie", "Luxembourg", "Macédoine du Nord", "Madagascar",
    "Malaisie", "Malawi", "Maldives", "Mali", "Malte", "Maroc", "Maurice",
    "Mauritanie", "Mexique", "Micronésie", "Moldavie", "Monaco", "Mongolie",
    "Monténégro", "Mozambique", "Namibie", "Nauru", "Népal", "Nicaragua",
    "Niger", "Nigeria", "Norvège", "Nouvelle-Zélande", "Oman", "Ouganda",
    "Ouzbékistan", "Pakistan", "Palaos", "Palestine", "Panama",
    "Papouasie-Nouvelle-Guinée", "Paraguay", "Pays-Bas", "Pérou", "Philippines",
    "Pologne", "Portugal", "Qatar", "République centrafricaine",
    "République démocratique du Congo", "République dominicaine",
    "République du Congo", "Roumanie", "Royaume-Uni", "Russie", "Rwanda",
    "Saint-Christophe-et-Niévès", "Sainte-Lucie", "Saint-Marin",
    "Saint-Vincent-et-les-Grenadines", "Salvador", "Samoa", "São Tomé-et-Principe",
    "Sénégal", "Serbie", "Seychelles", "Sierra Leone", "Singapour", "Slovaquie",
    "Slovénie", "Somalie", "Soudan", "Soudan du Sud", "Sri Lanka", "Suède",
    "Suisse", "Suriname", "Syrie", "Tadjikistan", "Tanzanie", "Tchad",
    "Tchéquie", "Thaïlande", "Timor oriental", "Togo", "Tonga",
    "Trinité-et-Tobago", "Tunisie", "Turkménistan", "Turquie", "Tuvalu",
    "Ukraine", "Uruguay", "Vanuatu", "Vatican", "Venezuela", "Viêt Nam",
    "Yémen", "Zambie", "Zimbabwe",
)
# Les libellés saisis spontanément sont ramenés vers le nom du pays. Les clés
# sont volontairement sans accent, comme celles produites par normalize_text_key.
COUNTRY_ALIASES = {
    "afghan": "Afghanistan", "afghane": "Afghanistan",
    "algerien": "Algérie", "algerienne": "Algérie",
    "allemand": "Allemagne", "allemande": "Allemagne",
    "americain": "États-Unis", "americaine": "États-Unis",
    "argentin": "Argentine", "argentine": "Argentine",
    "australien": "Australie", "australienne": "Australie",
    "autrichien": "Autriche", "autrichienne": "Autriche",
    "belge": "Belgique",
    "bresilien": "Brésil", "bresilienne": "Brésil",
    "britannique": "Royaume-Uni", "anglais": "Royaume-Uni", "anglaise": "Royaume-Uni",
    "bulgare": "Bulgarie",
    "camerounais": "Cameroun", "camerounaise": "Cameroun",
    "canadien": "Canada", "canadienne": "Canada",
    "chinois": "Chine", "chinoise": "Chine",
    "colombien": "Colombie", "colombienne": "Colombie",
    "coreen": "Corée du Sud", "coreenne": "Corée du Sud",
    "croate": "Croatie",
    "danois": "Danemark", "danoise": "Danemark",
    "espagnol": "Espagne", "espagnole": "Espagne",
    "estonien": "Estonie", "estonienne": "Estonie",
    "francais": "France", "francaise": "France",
    "grec": "Grèce", "grecque": "Grèce",
    "guineen": "Guinée", "guineenne": "Guinée",
    "hongrois": "Hongrie", "hongroise": "Hongrie",
    "indien": "Inde", "indienne": "Inde",
    "indonesien": "Indonésie", "indonesienne": "Indonésie",
    "irakien": "Irak", "irakienne": "Irak",
    "iranien": "Iran", "iranienne": "Iran",
    "irlandais": "Irlande", "irlandaise": "Irlande",
    "israelien": "Israël", "israelienne": "Israël",
    "italien": "Italie", "italienne": "Italie",
    "ivoirien": "Côte d’Ivoire", "ivoirienne": "Côte d’Ivoire",
    "japonais": "Japon", "japonaise": "Japon",
    "libanais": "Liban", "libanaise": "Liban",
    "luxembourgeois": "Luxembourg", "luxembourgeoise": "Luxembourg",
    "malien": "Mali", "malienne": "Mali",
    "marocain": "Maroc", "marocaine": "Maroc",
    "mexicain": "Mexique", "mexicaine": "Mexique",
    "neerlandais": "Pays-Bas", "neerlandaise": "Pays-Bas",
    "hollandais": "Pays-Bas", "hollandaise": "Pays-Bas",
    "neo zelandais": "Nouvelle-Zélande", "neo zelandaise": "Nouvelle-Zélande",
    "pakistanais": "Pakistan", "pakistanaise": "Pakistan",
    "palestinien": "Palestine", "palestinienne": "Palestine",
    "polonais": "Pologne", "polonaise": "Pologne",
    "portugais": "Portugal", "portugaise": "Portugal",
    "roumain": "Roumanie", "roumaine": "Roumanie",
    "russe": "Russie",
    "senegalais": "Sénégal", "senegalaise": "Sénégal",
    "suedois": "Suède", "suedoise": "Suède",
    "suisse": "Suisse",
    "syrien": "Syrie", "syrienne": "Syrie",
    "tunisien": "Tunisie", "tunisienne": "Tunisie",
    "turc": "Turquie", "turque": "Turquie",
    "ukrainien": "Ukraine", "ukrainienne": "Ukraine",
    "vietnamien": "Viêt Nam", "vietnamienne": "Viêt Nam",
}


def load_secret_key():
    """Charge la clé Flask ou en crée une persistante pour le conteneur."""
    configured_key = os.environ.get("OPENFABLAB_SECRET_KEY") or os.environ.get("COMPTEUR_SECRET_KEY")
    if configured_key:
        return configured_key

    secret_file = (os.environ.get("OPENFABLAB_SECRET_KEY_FILE")
                   or os.environ.get("COMPTEUR_SECRET_KEY_FILE")
                   or str(Path(resolve_database_path()).with_name(".openfablab_flask_secret")))

    secret_path = Path(secret_file)
    if secret_path.exists():
        saved_key = secret_path.read_text(encoding="utf-8").strip()
        if saved_key:
            return saved_key

    secret_path.parent.mkdir(parents=True, exist_ok=True)
    generated_key = secrets.token_urlsafe(48)
    secret_path.write_text(generated_key, encoding="utf-8")
    try:
        secret_path.chmod(0o600)
    except OSError:
        # Certains volumes réseau ne permettent pas de modifier les permissions.
        pass
    return generated_key


def resolve_database_path():
    """Prefer the new database and safely copy a legacy database before use."""
    configured = os.environ.get("OPENFABLAB_DATABASE") or os.environ.get("COMPTEUR_DATABASE")
    requested = Path(configured) if configured else DATABASE_PATH
    target = (requested.with_name("openfablab.db")
              if requested.name == "compteur_fablab.db" else requested)
    old = target.with_name("compteur_fablab.db")
    if target.exists() and old.exists() and target != old:
        # A previous aborted setup may have created an empty canonical file.
        # Never hide the populated historical database behind it.
        try:
            def business_rows(connection):
                available = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )}
                return sum(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                           for table in ("users", "sessions", "visitors", "fablab_services",
                                         "billing_records", "billing_clients") if table in available)
            with sqlite3.connect(f"file:{urllib.parse.quote(str(target))}?mode=ro", uri=True) as current:
                target_rows = business_rows(current)
            with sqlite3.connect(f"file:{urllib.parse.quote(str(old))}?mode=ro", uri=True) as previous:
                old_rows = business_rows(previous)
            if old_rows and not target_rows:
                raise RuntimeError("Base OpenFabLab vide alors que l'ancienne base contient des données : migration manuelle nécessaire.")
        except sqlite3.DatabaseError as error:
            raise RuntimeError("Impossible de comparer les deux bases SQLite avant démarrage.") from error
    if target.exists() or not old.exists() or target == old:
        return str(target)
    source = sqlite3.connect(f"file:{urllib.parse.quote(str(old))}?mode=ro", uri=True)
    try:
        if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("L'ancienne base SQLite n'est pas saine.")
        if source.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("L'ancienne base contient des liens invalides.")
        timestamp = datetime.now(PARIS_TIMEZONE).strftime("%Y%m%d-%H%M%S")
        backup = old.with_name(f"openfablab-avant-migration-{timestamp}.db")
        backup_connection = sqlite3.connect(str(backup))
        try:
            source.backup(backup_connection)
        finally:
            backup_connection.close()
        temporary = target.with_name(f".{target.name}.{secrets.token_hex(6)}.tmp")
        destination = sqlite3.connect(str(temporary))
        try:
            source.backup(destination)
        finally:
            destination.close()
        os.replace(temporary, target)
    finally:
        source.close()
    return str(target)


def initialize_pin_credentials(application):
    """Migrate configured legacy PINs once, never storing clear PINs in SQLite."""
    path = application.config["DATABASE"]
    admin_candidate = application.config.pop("ADMIN_PIN", None)
    moderator_candidate = application.config.pop("MODERATOR_PIN", None)
    if not has_pin(path, "admin") and valid_pin(admin_candidate):
        set_pin(path, "admin", admin_candidate)
    database = get_database()
    old_moderator = database.execute(
        "SELECT value FROM app_settings WHERE key = 'moderator_pin'"
    ).fetchone()
    if not has_pin(path, "moderator"):
        candidate = old_moderator[0] if old_moderator else moderator_candidate
        if valid_pin(candidate):
            set_pin(path, "moderator", candidate)
    if old_moderator:
        database.execute("DELETE FROM app_settings WHERE key = 'moderator_pin'")
        database.commit()


def create_app(test_config=None):
    """Crée et configure l'application Flask."""
    application = Flask(__name__)
    database_location = (test_config["DATABASE"] if test_config and "DATABASE" in test_config
                         else resolve_database_path())
    application.config.from_mapping(
        DATABASE=database_location,
        SECRET_KEY=(test_config or {}).get('SECRET_KEY') or load_secret_key(),
        PRIVATE_SECRET_PATH=(str(Path(database_location).with_name('.openfablab_flask_secret'))
                             if (test_config or {}).get('SECRET_KEY') else
                             (os.environ.get('OPENFABLAB_SECRET_KEY_FILE') or os.environ.get('COMPTEUR_SECRET_KEY_FILE')
                              or str(Path(database_location).with_name('.openfablab_flask_secret')))),
        ADMIN_PIN=os.environ.get("OPENFABLAB_ADMIN_PIN") or os.environ.get("COMPTEUR_ADMIN_PIN"),
        APP_VERSION=f"V{__version__}",
        MAX_CONTENT_LENGTH=100 * 1024 * 1024,
        AUTO_CLOSURE_WORKER=(os.environ.get("OPENFABLAB_ENABLE_SCHEDULER") or os.environ.get("COMPTEUR_ENABLE_SCHEDULER")) == "1",
        WEATHER_ENABLED=(os.environ.get("OPENFABLAB_ENABLE_WEATHER") or os.environ.get("COMPTEUR_ENABLE_WEATHER", "1")) == "1",
        DISCORD_SYNCHRONOUS=False,
        BACKUP_ROOT=os.environ.get(
            "OPENFABLAB_BACKUP_ROOT", os.environ.get("COMPTEUR_BACKUP_ROOT", str(BASE_DIR / "Saves"))
        ),
        BACKUP_DISPLAY_ROOT=os.environ.get(
            "OPENFABLAB_BACKUP_DISPLAY_ROOT", os.environ.get("COMPTEUR_BACKUP_DISPLAY_ROOT", str(BASE_DIR / "Saves"))
        ),
        DISCORD_WEBHOOK_FILE=os.environ.get("OPENFABLAB_DISCORD_WEBHOOK_FILE") or os.environ.get("COMPTEUR_DISCORD_WEBHOOK_FILE"),
    )

    if test_config:
        application.config.update(test_config)

    if not application.config["DISCORD_WEBHOOK_FILE"]:
        application.config["DISCORD_WEBHOOK_FILE"] = str(
            Path(application.config["DATABASE"]).with_name(".discord_webhook_url")
        )

    from runtime_policy import install_network_guard, is_test_instance, register_storage
    install_network_guard()
    if is_test_instance(application.config['DATABASE']):
        application.config.update(EXTERNAL_ACTIONS=False, AUTO_CLOSURE_WORKER=False, WEATHER_ENABLED=False)
    if os.environ.get('OPENFABLAB_EXTERNAL_ACTIONS') == '0':
        application.config.update(EXTERNAL_ACTIONS=False, AUTO_CLOSURE_WORKER=False, WEATHER_ENABLED=False)
    if Path(application.config['DATABASE']).with_name('.openfablab-restore-in-progress.json').exists():
        raise RuntimeError('Restauration interrompue : récupération privée hors ligne requise.')
    register_storage(application)

    application.teardown_appcontext(close_database)
    register_template_helpers(application)
    register_admin_protection(application)
    register_routes(application)
    from evolution_routes import register as register_evolution
    register_evolution(application, globals())
    from tablet_reservations import register as register_tablet_reservations
    register_tablet_reservations(application, globals())
    from family_routes import register as register_family
    register_family(application, globals())
    register_error_handlers(application)

    from runtime_policy import storage_guard
    with storage_guard(application.config['DATABASE']), application.app_context():
        initialize_database()
        initialize_pin_credentials(application)

    if application.config["AUTO_CLOSURE_WORKER"]:
        start_automatic_closure_worker(application)
    elif (not application.config.get('TESTING') and application.config.get('EXTERNAL_ACTIONS') is not False
          and os.environ.get('OPENFABLAB_ENABLE_SCHEDULER') != '0'):
        from family_waitlist import start_worker
        start_worker(application,get_database,load_modules)

    return application


def create_deployment_application(application, url_prefix=None):
    """Monte Flask sous un chemin dédié lors du déploiement sur le NAS."""
    configured_prefix = url_prefix
    if configured_prefix is None:
        configured_prefix = os.environ.get(
            "OPENFABLAB_URL_PREFIX", os.environ.get("COMPTEUR_URL_PREFIX", "")
        )

    normalized_prefix = "/" + configured_prefix.strip("/")
    if normalized_prefix == "/":
        return application

    def page_not_found(_environment, start_response):
        response = Response(
            "Page introuvable.\n",
            status=404,
            mimetype="text/plain",
        )
        return response(_environment, start_response)

    mounted_application = DispatcherMiddleware(
        page_not_found,
        {normalized_prefix: application},
    )

    def deployment_entry(environment, start_response):
        # Une redirection relative conserve le HTTPS terminé par le proxy DSM.
        if environment.get("PATH_INFO") == normalized_prefix:
            response = Response(
                status=308,
                headers={"Location": f"{normalized_prefix}/"},
            )
            return response(environment, start_response)
        return mounted_application(environment, start_response)

    return deployment_entry


def get_database():
    """Ouvre une connexion SQLite pour la requête en cours."""
    if "database" not in g:
        database_path = Path(current_database_path())
        database_path.parent.mkdir(parents=True, exist_ok=True)
        g.database = sqlite3.connect(
            database_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=10,
        )
        g.database.row_factory = sqlite3.Row
        g.database.execute("PRAGMA foreign_keys = ON")
        g.database.execute("PRAGMA busy_timeout = 10000")
    return g.database


def current_database_path():
    """Retourne le chemin configuré, y compris pour les tests."""
    from flask import current_app

    return current_app.config["DATABASE"]


def close_database(_exception=None):
    """Ferme proprement la connexion à la fin d'une requête."""
    database = g.pop("database", None)
    if database is not None:
        database.close()


def initialize_database():
    """Crée les tables et ajoute les comptes de démonstration une seule fois."""
    database = get_database()
    from family_model import backup_before as backup_before_family
    backup_before_family(database, current_database_path())
    backup_before_evolution(database, current_database_path())
    legacy_installation = database.execute("PRAGMA user_version").fetchone()[0] > 0
    existing_users_table = database.execute("SELECT 1 FROM sqlite_master WHERE name='users'").fetchone() is not None
    database.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            public_id TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
            category TEXT NOT NULL DEFAULT 'user'
                CHECK (category IN ('user', 'volunteer', 'voluntary', 'fabmanager', 'intern', 'staff')),
            birth_year INTEGER,
            gender TEXT CHECK (
                gender IS NULL OR
                gender IN ('female', 'male', 'non_binary')
            ),
            city TEXT,
            city_normalized TEXT,
            postal_code TEXT,
            nationality TEXT,
            nationality_normalized TEXT,
            email TEXT,
            phone_country_code TEXT NOT NULL DEFAULT '+33',
            phone TEXT,
            statistics_key TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            check_in TEXT NOT NULL,
            check_out TEXT,
            entry_method TEXT NOT NULL DEFAULT 'manual',
            exit_method TEXT,
            statistical_user_key TEXT,
            statistical_category TEXT NOT NULL DEFAULT 'user',
            statistical_birth_year INTEGER,
            statistical_gender TEXT,
            statistical_city TEXT,
            statistical_city_normalized TEXT,
            statistical_postal_code TEXT,
            statistical_nationality TEXT,
            statistical_nationality_normalized TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS visitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS attendance_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_at TEXT NOT NULL,
            action_type TEXT NOT NULL
                CHECK (action_type IN ('add', 'update', 'delete')),
            record_type TEXT NOT NULL
                CHECK (record_type IN ('session', 'visitor')),
            record_id INTEGER,
            old_values_json TEXT,
            new_values_json TEXT
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fablab_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_type TEXT NOT NULL
                CHECK (service_type IN ('animation', 'reservation', 'rental')),
            title TEXT NOT NULL,
            service_date TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            duration_minutes INTEGER,
            minimum_age INTEGER NOT NULL DEFAULT 10,
            description TEXT,
            expected_participants INTEGER,
            actual_participants INTEGER,
            participants INTEGER,
            invoice_reference TEXT,
            client_name TEXT,
            amount_cents INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS retention_warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            warning_type TEXT NOT NULL
                CHECK (warning_type IN ('contact', 'deactivation', 'deletion')),
            deadline TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            UNIQUE (user_id, warning_type, deadline),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS billing_clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_name TEXT NOT NULL,
            contact_name_normalized TEXT NOT NULL UNIQUE,
            structure_name TEXT NOT NULL,
            address_line TEXT NOT NULL,
            postal_code TEXT NOT NULL,
            city TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS billing_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            billing_type TEXT NOT NULL DEFAULT 'reservation'
                CHECK (billing_type IN ('reservation', 'rental')),
            quote_number TEXT NOT NULL UNIQUE,
            quote_date TEXT NOT NULL,
            quote_signed_at TEXT,
            quote_cancelled_at TEXT,
            invoice_number TEXT UNIQUE,
            invoice_date TEXT,
            invoice_sent_at TEXT,
            paid_at TEXT,
            reminder_one_at TEXT,
            reminder_two_at TEXT,
            client_id INTEGER,
            client_contact TEXT NOT NULL,
            client_structure TEXT NOT NULL,
            address_line TEXT NOT NULL,
            postal_code TEXT NOT NULL,
            city TEXT NOT NULL,
            phone TEXT,
            email TEXT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            activity_date TEXT NOT NULL,
            activity_time_details TEXT,
            activity_start_time TEXT,
            activity_end_time TEXT,
            activity_duration_minutes INTEGER,
            participants INTEGER NOT NULL DEFAULT 0,
            rate_category TEXT NOT NULL
                CHECK (rate_category IN ('normal', 'reduced')),
            rate_is_agglo INTEGER NOT NULL DEFAULT 0
                CHECK (rate_is_agglo IN (0, 1)),
            rate_unit TEXT NOT NULL
                CHECK (rate_unit IN ('hourly', 'half_day')),
            rate_quantity INTEGER NOT NULL DEFAULT 1,
            rate_unit_cents INTEGER NOT NULL DEFAULT 0,
            travel_quantity INTEGER NOT NULL DEFAULT 0,
            travel_unit_cents INTEGER NOT NULL DEFAULT 6000,
            consumable_mode TEXT NOT NULL DEFAULT 'included'
                CHECK (consumable_mode IN ('included', 'client', 'billed')),
            consumable_quantity INTEGER NOT NULL DEFAULT 0,
            consumable_unit_cents INTEGER NOT NULL DEFAULT 3000,
            amount_cents INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            rental_machine_key TEXT,
            rental_machine_name TEXT,
            rental_months INTEGER NOT NULL DEFAULT 1,
            rental_monthly_cents INTEGER NOT NULL DEFAULT 0,
            rental_deposit_cents INTEGER NOT NULL DEFAULT 0,
            rental_delivery INTEGER NOT NULL DEFAULT 0 CHECK (rental_delivery IN (0, 1)),
            rental_contract_fee_cents INTEGER NOT NULL DEFAULT 2500,
            rental_delivery_fee_cents INTEGER NOT NULL DEFAULT 3000,
            rental_deposit_exempt INTEGER NOT NULL DEFAULT 0 CHECK (rental_deposit_exempt IN (0, 1)),
            rental_end_date TEXT,
            payment_overdue_notified_at TEXT,
            service_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (client_id) REFERENCES billing_clients(id) ON DELETE SET NULL,
            FOREIGN KEY (service_id) REFERENCES fablab_services(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS rental_catalog (
            machine_key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            monthly_cents INTEGER NOT NULL DEFAULT 0,
            deposit_cents INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS annual_activity_reports (
            year INTEGER PRIMARY KEY,
            introduction TEXT,
            highlights TEXT,
            new_equipment TEXT,
            changes TEXT,
            partnerships TEXT,
            additional_notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE UNIQUE INDEX IF NOT EXISTS one_open_session_per_user
            ON sessions(user_id)
            WHERE check_out IS NULL;

        CREATE INDEX IF NOT EXISTS sessions_check_in_index ON sessions(check_in);
        CREATE INDEX IF NOT EXISTS visitors_created_at_index ON visitors(created_at);
        CREATE INDEX IF NOT EXISTS attendance_corrections_action_at_index
            ON attendance_corrections(action_at);
        CREATE INDEX IF NOT EXISTS fablab_services_date_index
            ON fablab_services(service_date);
        CREATE INDEX IF NOT EXISTS fablab_services_type_index
            ON fablab_services(service_type);
        CREATE INDEX IF NOT EXISTS retention_warnings_user_index
            ON retention_warnings(user_id);
        CREATE INDEX IF NOT EXISTS billing_records_activity_date_index
            ON billing_records(activity_date);
        CREATE INDEX IF NOT EXISTS billing_records_invoice_date_index
            ON billing_records(invoice_date);
        """
    )

    # Do not replay historical migrations against an already current database.
    if database.execute('PRAGMA user_version').fetchone()[0] < 14:
        migrate_users_schema(database)
        migrate_sessions_schema(database)
        migrate_billing_schema(database)
        migrate_services_schema(database)
        migrate_attendance_corrections_schema(database)
        migrate_weather_snapshots_schema(database)
        migrate_security_events_schema(database)
        migrate_reservations_schema(database)
        migrate_catalog_schema(database)
        migrate_animation_slots_schema(database)
        migrate_evolution(database, new_installation=not legacy_installation and not existing_users_table
                          and not (current_app.config.get('TESTING') and current_app.config.get('SEED_DEMO_USERS', True)))
    create_statistics_triggers(database)

    # Existing installation settings win; only missing keys receive neutral defaults.
    migrate_branding_settings(database, Path(current_database_path()).parent)
    default_settings = default_application_settings()
    database.executemany(
        "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
        default_settings,
    )
    # One-time, requested 2.7.1 adjustment of the former two-minute default.
    # Other intervals and subsequent explicit selections are preserved.
    if read_setting(database, 'reservation_sync_90s_initialized', '') != '1':
        if read_setting(database, 'reservation_sync_interval_minutes', '') == '2':
            write_setting(database, 'reservation_sync_interval_minutes', '1.5')
        write_setting(database, 'reservation_sync_90s_initialized', '1')
    # Convert only the exact historical default; never rename directories or
    # touch a custom destination (including nested historical directories).
    if read_setting(database, "automatic_backup_subdirectory") == "CompteurPassage":
        write_setting(database, "automatic_backup_subdirectory", "OpenFabLab")
    if read_setting(database, "retention_v25_policy_applied") != "1":
        if read_setting(database, "retention_contact_years") == "1":
            write_setting(database, "retention_contact_years", "2")
        write_setting(database, "retention_v25_policy_applied", "1")
    # Met à niveau uniquement les anciens textes fournis par l'application.
    # Toute autre formulation personnalisée reste donc strictement intacte.
    standard_message_migrations = (
        (
            "discord_message_arrival", DISCORD_DEFAULTS["arrival_message"],
            ("🟢 {name} arrive au fablab.", "🟢 {name} vient d'enregistrer son arrivée au FougèresLab."),
        ),
        (
            "discord_message_departure", DISCORD_DEFAULTS["departure_message"],
            ("🔴 {name} quitte le fablab.", "🔵 {name} vient d'enregistrer son départ du FougèresLab."),
        ),
        (
            "discord_message_visitor", DISCORD_DEFAULTS["visitor_message"],
            ("🟡 Un visiteur est au fablab.", "🟡 Un visiteur anonyme vient d'être comptabilisé au FougèresLab."),
        ),
        (
            "discord_message_monthly_animations",
            DISCORD_DEFAULTS["monthly_animations_message"],
            ("📅 Pensez à renseigner les animations réalisées en {month}.", "📅 Animations de {month} à renseigner."),
        ),
    )
    for setting_key, replacement, previous_values in standard_message_migrations:
        placeholders = ", ".join("?" for _ in previous_values)
        database.execute(
            f"UPDATE app_settings SET value = ? WHERE key = ? AND value IN ({placeholders})",
            (replacement, setting_key, *previous_values),
        )
    if current_app.config.get("TESTING") and current_app.config.get("SEED_DEMO_USERS", True):
        seed_rental_catalog(database)

    seed_was_already_handled = database.execute(
        "SELECT 1 FROM app_settings WHERE key = ?", (INITIAL_DEMO_SETTING,)
    ).fetchone()
    if seed_was_already_handled is None:
        user_count = database.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        # Demonstration identities belong exclusively to isolated automated tests.
        # A new FabLab installation must start with an empty real directory.
        if user_count == 0 and current_app.config.get("TESTING") and current_app.config.get("SEED_DEMO_USERS", True):
            created_at = utc_now_iso()
            demo_users = [
                ("1001", "Victor", "EXEMPLE", 1, "fabmanager", secrets.token_hex(16), created_at),
                ("1002", "Clara", "FICTIVE", 1, "user", secrets.token_hex(16), created_at),
                ("1003", "Jean", "DUPONT", 1, "user", secrets.token_hex(16), created_at),
                ("1004", "Alice", "MARTIN", 1, "user", secrets.token_hex(16), created_at),
                ("1005", "Marie", "BERNARD", 1, "user", secrets.token_hex(16), created_at),
            ]
            database.executemany(
                """
                INSERT INTO users
                    (public_id, first_name, last_name, active, category,
                     statistics_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                demo_users,
            )
        database.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, '1')",
            (INITIAL_DEMO_SETTING,),
        )

    database.commit()
    from family_model import migrate as migrate_family
    migrate_family(database)


def default_application_settings(_legacy_installation=False):
    """Retourne les réglages initiaux sans réactiver les comptes de démo."""
    settings = [
        ("automatic_closure_enabled", "0"),
        ("keep_screen_awake", "0"),
        ("lock_home_scroll", "1"),
        ("home_theme", "classic"),
        ("wake_lock_start", "09:00"),
        ("wake_lock_end", "17:00"),
        ("openlab_attendance_show_decimals", "0"),
        ("retention_contact_years", "2"),
        ("retention_deactivation_years", "3"),
        ("retention_deletion_years", "5"),
        ("retention_last_run_date", ""),
        ("retention_last_report", ""),
        ("automatic_backup_enabled", "0"),
        ("automatic_backup_interval_days", "1"),
        ("automatic_backup_subdirectory", "OpenFabLab"),
        ("automatic_backup_last_attempt", ""),
        ("automatic_backup_last_success", ""),
        ("automatic_backup_last_filename", ""),
        ("automatic_backup_last_error", ""),
        ("discord_notifications_enabled", "0"),
        ("discord_notify_arrivals", "1"),
        ("discord_notify_departures", "1"),
        ("discord_notify_visitors", "1"),
        ("discord_notify_retention", "1"),
        ("discord_notify_invoice_overdue", "1"),
        ("discord_notify_monthly_animations", "1"),
        ("discord_notify_invalid_ids", "1"),
        ("invalid_id_threshold", "5"),
        ("invalid_id_window_minutes", "5"),
        ("invalid_id_lock_enabled", "0"),
        ("invalid_id_lock_minutes", "10"),
        ("discord_monthly_animations_last_period", ""),
        ("discord_bot_name", "OpenFabLab"),
        ("discord_message_arrival", DISCORD_DEFAULTS["arrival_message"]),
        ("discord_message_departure", DISCORD_DEFAULTS["departure_message"]),
        ("discord_message_visitor", DISCORD_DEFAULTS["visitor_message"]),
        (
            "discord_message_retention",
            "🟠 {name} : {action} prévue le {date}.",
        ),
        (
            "discord_message_invoice_overdue",
            "🔔 La facture {invoice_number} de {client}, envoyée le {sent_date}, attend son règlement depuis 30 jours.",
        ),
        (
            "discord_message_monthly_animations",
            "📅 Pensez à renseigner les animations réalisées en {month} et à exporter la base de données ailleurs.",
        ),
        ('billing_rate_normal_hourly_cents', '0'),
        ('billing_rate_normal_half_day_cents', '0'),
        ('billing_rate_reduced_hourly_cents', '0'),
        ('billing_rate_reduced_half_day_cents', '0'),
        ('billing_travel_unit_cents', '0'),
        ('billing_consumable_unit_cents', '0'),
        ('billing_rental_contract_fee_cents', '0'),
        ('billing_rental_delivery_fee_cents', '0'),
        ('structure_name', 'Mon FabLab'),
        ('structure_short_name', 'FabLab'),
        ('structure_description', 'Espace de fabrication numérique'),
        ('structure_address', ''),
        ('structure_city', ''),
        ('structure_postal_code', ''),
        ('structure_email', ''),
        ('structure_phone', ''),
        ('structure_website', ''),
        ('structure_privacy_policy_url', ''),
        ('structure_country', 'France'),
        ('structure_timezone', 'Europe/Paris'),
        ('structure_latitude', ''),
        ('structure_longitude', ''),
        ('structure_color', '#307b9a'),
        ('structure_legal_entity', ''),
        ('structure_billing_address', ''),
        ('structure_siret', ''),
        ('structure_vat_number', ''),
        ('structure_vat_note', ''),
        ('structure_iban', ''),
        ('structure_bic', ''),
        ('structure_account_holder', ''),
        ('structure_payment_terms', ''),
        ('structure_payment_days', ''),
        ('structure_regie_contact', ''),
        ('structure_signer_name', ''),
        ('structure_rental_terms', ''),
        ('structure_main_logo', ''),
        ('structure_wordmark_logo', ''),
        ('structure_institution_logo', ''),
        ('structure_signature', ''),
        ('structure_header_institution_logo', ''),
        ('structure_network_logo', ''),
        ('structure_badge_template', ''),
        ('structure_show_wordmark_logo', '1'),
        ('structure_show_header_institution_logo', '1'),
        ('structure_show_network_logo', '1'),
        ('structure_data_controller', ''),
        ('structure_data_controller_address', ''),
        ('structure_data_controller_representative', ''),
        ('structure_data_controller_representative_role', ''),
        ('structure_dpo', ''),
        ('structure_dpo_email', ''),
        ('structure_dpo_phone', ''),
        ('structure_use_main_logo', '1'),
        ('structure_use_signature', '1'),
        ('structure_use_badge_template', '1'),
        ("module_frequency", "1"),
        ("module_users", "1"),
        ("module_activities", "1"),
        ("module_resources", "1"),
        ("module_authorizations", "1"),
        ("calendar_display_start", "09:00"),
        ("calendar_display_end", "19:00"),
        ("module_public_reservations", "0"),
        ("module_booking_slots", "1"),
        ("module_rentals", "1"),
        ("module_billing", "1"),
        ("module_weather", "1"),
        ("module_discord", "1"),
        ("reservation_minimum_age", "10"),
        ("reservation_accompaniment_under_age", "15"),
        ("reservation_waitlist_enabled", "1"),
        ("reservation_offer_hours", "24"),
        ("reservation_last_offer_hours", "24"),
        ("reservation_close_minutes", "60"),
        ("reservation_reminder_one_hours", "24"),
        ("reservation_reminder_two_hours", "0"),
        ("reservation_sync_interval_minutes", "1.5"),
        ('tablet_reservations_enabled', '0'),
        ("reservation_wordpress_url", ""),
    ]
    settings.extend((f"discord_reservation_{name}", "1") for name in RESERVATION_DISCORD_FLAGS)
    settings.extend(
        (f"automatic_closure_{weekday}", "") for weekday, _label in WEEKDAYS
    )
    for weekday_key, _weekday_label in WEEKDAYS:
        start, end = DEFAULT_OPENLAB_SCHEDULE[weekday_key]
        settings.extend(
            [
                (f"openlab_attendance_{weekday_key}_start", start),
                (f"openlab_attendance_{weekday_key}_end", end),
            ]
        )
    return settings


def migrate_users_schema(database):
    """Met à niveau les anciennes fiches usagers sans perdre leur historique."""
    existing_columns = {
        row["name"] for row in database.execute("PRAGMA table_info(users)").fetchall()
    }

    # Les premières versions n'avaient pas d'identifiant public. On les attribue
    # avant de reconstruire la table avec les contraintes du schéma actuel.
    if "public_id" not in existing_columns:
        database.execute("ALTER TABLE users ADD COLUMN public_id TEXT")
        existing_columns.add("public_id")

    # Les codes commencent à 1001 : quatre chiffres simples à saisir et une
    # capacité très supérieure au besoin annoncé de moins de 1 000 usagers.
    used_codes = {
        row["public_id"]
        for row in database.execute(
            "SELECT public_id FROM users WHERE public_id IS NOT NULL"
        ).fetchall()
        if row["public_id"]
    }
    next_code = 1001
    users_without_code = database.execute(
        """
        SELECT id FROM users
        WHERE public_id IS NULL OR TRIM(public_id) = ''
        ORDER BY id
        """
    ).fetchall()
    for user in users_without_code:
        while str(next_code) in used_codes:
            next_code += 1
        if next_code > 9999:
            raise RuntimeError("Aucun identifiant public à quatre chiffres disponible")
        public_id = str(next_code)
        database.execute(
            "UPDATE users SET public_id = ? WHERE id = ?",
            (public_id, user["id"]),
        )
        used_codes.add(public_id)
        next_code += 1

    schema_version = database.execute("PRAGMA user_version").fetchone()[0]
    required_columns = {
        "category",
        "birth_year",
        "gender",
        "city",
        "city_normalized",
        "postal_code",
        "nationality",
        "nationality_normalized",
        "email",
        "phone_country_code",
        "phone",
        "statistics_key",
    }
    if schema_version < 7 or not required_columns.issubset(existing_columns):
        rebuild_users_table(database, existing_columns)

    # Les clés de regroupement permettent aux statistiques de compter ensemble
    # les différences d'accents, de casse et les adjectifs de nationalité.
    for user in database.execute(
        "SELECT id, last_name, city, nationality, phone_country_code, phone FROM users"
    ).fetchall():
        country_name = canonical_country_name(user["nationality"])
        phone_country_code, phone_number = normalize_user_phone(
            user["phone_country_code"], user["phone"]
        )
        database.execute(
            """
            UPDATE users
            SET last_name = ?, city_normalized = ?, nationality = ?,
                nationality_normalized = ?, phone_country_code = ?, phone = ?
            WHERE id = ?
            """,
            (
                normalize_last_name(user["last_name"]),
                normalize_text_key(user["city"]),
                country_name,
                normalize_nationality(country_name),
                phone_country_code,
                phone_number or None,
                user["id"],
            ),
        )

    database.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS users_public_id_unique ON users(public_id)"
    )
    database.execute(
        "CREATE INDEX IF NOT EXISTS users_city_normalized_index ON users(city_normalized)"
    )
    database.execute(
        "CREATE INDEX IF NOT EXISTS users_nationality_normalized_index ON users(nationality_normalized)"
    )
    database.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS users_statistics_key_unique ON users(statistics_key)"
    )


def rebuild_users_table(database, existing_columns):
    """Reconstruit uniquement la table users pour moderniser ses contraintes."""

    def source(column_name, fallback="NULL"):
        return column_name if column_name in existing_columns else fallback

    category_source = source("category", "'user'")
    gender_source = source("gender")
    database.commit()
    database.execute("PRAGMA foreign_keys = OFF")
    try:
        database.execute("BEGIN IMMEDIATE")
        # Les versions précédentes pouvaient déjà avoir installé ces
        # déclencheurs. Celui des sessions référence ``users`` : SQLite refuse
        # alors de renommer la table reconstruite pendant le bref intervalle où
        # l'ancienne table n'existe plus. Ils sont recréés après les migrations.
        database.execute("DROP TRIGGER IF EXISTS sessions_statistics_after_insert")
        database.execute("DROP TRIGGER IF EXISTS users_statistics_key_after_insert")
        database.execute("DROP TABLE IF EXISTS users_new")
        database.execute(
            """
            CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_id TEXT NOT NULL,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                category TEXT NOT NULL DEFAULT 'user'
                    CHECK (category IN ('user', 'volunteer', 'voluntary', 'fabmanager', 'intern', 'staff')),
                birth_year INTEGER,
                gender TEXT CHECK (
                    gender IS NULL OR gender IN ('female', 'male', 'non_binary')
                ),
                city TEXT,
                city_normalized TEXT,
                postal_code TEXT,
                nationality TEXT,
                nationality_normalized TEXT,
                email TEXT,
                phone_country_code TEXT NOT NULL DEFAULT '+33',
                phone TEXT,
                statistics_key TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        database.execute(
            f"""
            INSERT INTO users_new (
                id, public_id, first_name, last_name, active, category,
                birth_year, gender, city, city_normalized, postal_code,
                nationality, nationality_normalized, email,
                phone_country_code, phone,
                statistics_key, created_at
            )
            SELECT
                id, public_id, first_name, last_name, active,
                CASE
                    WHEN {category_source} IN ('user', 'volunteer', 'voluntary', 'fabmanager', 'intern', 'staff')
                        THEN {category_source}
                    WHEN {category_source} = 'team' THEN 'volunteer'
                    ELSE 'user'
                END,
                {source('birth_year')},
                CASE WHEN {gender_source} IN ('female', 'male', 'non_binary')
                    THEN {gender_source} ELSE NULL END,
                {source('city')}, {source('city_normalized')},
                {source('postal_code')}, {source('nationality')},
                {source('nationality_normalized')}, {source('email')},
                COALESCE(NULLIF(TRIM({source('phone_country_code', "''")}), ''), '+33'),
                {source('phone')},
                COALESCE(NULLIF(TRIM({source('statistics_key', "''")}), ''), LOWER(HEX(RANDOMBLOB(16)))),
                created_at
            FROM users
            """
        )
        database.execute("DROP TABLE users")
        database.execute("ALTER TABLE users_new RENAME TO users")
        database.commit()
    except Exception:
        database.rollback()
        raise
    finally:
        database.execute("PRAGMA foreign_keys = ON")


def migrate_sessions_schema(database):
    """Conserve des statistiques anonymes même après suppression d'un compte."""
    existing_columns = {
        row["name"] for row in database.execute("PRAGMA table_info(sessions)").fetchall()
    }
    required_columns = {
        "statistical_user_key",
        "statistical_category",
        "statistical_birth_year",
        "statistical_gender",
        "statistical_city",
        "statistical_city_normalized",
        "statistical_postal_code",
        "statistical_nationality",
        "statistical_nationality_normalized",
    }
    user_id_info = next(
        (row for row in database.execute("PRAGMA table_info(sessions)") if row["name"] == "user_id"),
        None,
    )
    needs_rebuild = (
        not required_columns.issubset(existing_columns)
        or user_id_info is None
        or user_id_info["notnull"] == 1
    )
    if not needs_rebuild:
        database.execute("PRAGMA user_version = 7")
        canonicalize_session_nationalities(database)
        return

    def old(column, fallback="NULL"):
        return f"s.{column}" if column in existing_columns else fallback

    def user(column, fallback="NULL"):
        return f"COALESCE((SELECT u.{column} FROM users u WHERE u.id = s.user_id), {fallback})"

    database.commit()
    database.execute("PRAGMA foreign_keys = OFF")
    try:
        database.execute("BEGIN IMMEDIATE")
        database.execute("DROP TABLE IF EXISTS sessions_new")
        database.execute(
            """
            CREATE TABLE sessions_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                check_in TEXT NOT NULL,
                check_out TEXT,
                entry_method TEXT NOT NULL DEFAULT 'manual',
                exit_method TEXT,
                statistical_user_key TEXT,
                statistical_category TEXT NOT NULL DEFAULT 'user',
                statistical_birth_year INTEGER,
                statistical_gender TEXT,
                statistical_city TEXT,
                statistical_city_normalized TEXT,
                statistical_postal_code TEXT,
                statistical_nationality TEXT,
                statistical_nationality_normalized TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        database.execute(
            f"""
            INSERT INTO sessions_new (
                id, user_id, check_in, check_out, entry_method, exit_method,
                statistical_user_key, statistical_category,
                statistical_birth_year, statistical_gender,
                statistical_city, statistical_city_normalized,
                statistical_postal_code, statistical_nationality,
                statistical_nationality_normalized
            )
            SELECT
                s.id, s.user_id, s.check_in, s.check_out, s.entry_method, s.exit_method,
                COALESCE({old('statistical_user_key')}, {user('statistics_key')}, LOWER(HEX(RANDOMBLOB(16)))),
                COALESCE({old('statistical_category')}, {user('category', "'user'")}, 'user'),
                COALESCE({old('statistical_birth_year')}, {user('birth_year')}),
                COALESCE({old('statistical_gender')}, {user('gender')}),
                COALESCE({old('statistical_city')}, {user('city')}),
                COALESCE({old('statistical_city_normalized')}, {user('city_normalized')}),
                COALESCE({old('statistical_postal_code')}, {user('postal_code')}),
                COALESCE({old('statistical_nationality')}, {user('nationality')}),
                COALESCE({old('statistical_nationality_normalized')}, {user('nationality_normalized')})
            FROM sessions s
            """
        )
        database.execute("DROP TABLE sessions")
        database.execute("ALTER TABLE sessions_new RENAME TO sessions")
        database.execute(
            "CREATE UNIQUE INDEX one_open_session_per_user ON sessions(user_id) "
            "WHERE check_out IS NULL AND user_id IS NOT NULL"
        )
        database.execute("CREATE INDEX sessions_check_in_index ON sessions(check_in)")
        database.execute("CREATE INDEX sessions_statistics_key_index ON sessions(statistical_user_key)")
        database.execute("PRAGMA user_version = 7")
        database.commit()
    except Exception:
        database.rollback()
        raise
    finally:
        database.execute("PRAGMA foreign_keys = ON")
    canonicalize_session_nationalities(database)


def migrate_billing_schema(database):
    """Ajoute les champs de facturation récents sans altérer les devis existants."""
    existing_columns = {
        row["name"]
        for row in database.execute("PRAGMA table_info(billing_records)").fetchall()
    }
    additions = {
        "rental_machine_key": "TEXT",
        "rental_machine_name": "TEXT",
        "rental_months": "INTEGER NOT NULL DEFAULT 1",
        "rental_monthly_cents": "INTEGER NOT NULL DEFAULT 0",
        "rental_deposit_cents": "INTEGER NOT NULL DEFAULT 0",
        "rental_delivery": "INTEGER NOT NULL DEFAULT 0",
        "rental_deposit_exempt": "INTEGER NOT NULL DEFAULT 0",
        "rental_end_date": "TEXT",
        # Le booléen évite de modifier l'ancienne contrainte SQLite du tarif.
        "rate_is_agglo": "INTEGER NOT NULL DEFAULT 0",
        "payment_overdue_notified_at": "TEXT",
        "client_id": "INTEGER",
        "quote_cancelled_at": "TEXT",
        "activity_start_time": "TEXT",
        "activity_end_time": "TEXT",
        "activity_duration_minutes": "INTEGER",
        "rate_unit_cents": "INTEGER NOT NULL DEFAULT 0",
        "travel_unit_cents": "INTEGER NOT NULL DEFAULT 6000",
        "consumable_unit_cents": "INTEGER NOT NULL DEFAULT 3000",
        "rental_contract_fee_cents": "INTEGER NOT NULL DEFAULT 2500",
        "rental_delivery_fee_cents": "INTEGER NOT NULL DEFAULT 3000",
    }
    for column, definition in additions.items():
        if column not in existing_columns:
            database.execute(
                f"ALTER TABLE billing_records ADD COLUMN {column} {definition}"
            )

    database.execute(
        "CREATE INDEX IF NOT EXISTS billing_records_client_index "
        "ON billing_records(client_id)"
    )
    # Les premières versions déduisaient l'annuaire du dernier devis connu.
    # La migration transforme ces coordonnées en fiches clients persistantes.
    rows = database.execute(
        """
        SELECT id, client_contact, client_structure, address_line, postal_code,
               city, phone, email, created_at, updated_at
        FROM billing_records
        ORDER BY updated_at ASC, id ASC
        """
    ).fetchall()
    for row in rows:
        client_id = upsert_billing_client(
            database,
            {
                "client_contact": row["client_contact"],
                "client_structure": row["client_structure"],
                "address_line": row["address_line"],
                "postal_code": row["postal_code"],
                "city": row["city"],
                "phone": row["phone"] or "",
                "email": row["email"] or "",
            },
            timestamp=row["updated_at"] or row["created_at"] or utc_now_iso(),
        )
        database.execute(
            "UPDATE billing_records SET client_id = ? WHERE id = ?",
            (client_id, row["id"]),
        )

    # Conserve les montants historiques dans chaque dossier afin qu'une future
    # modification des tarifs ne réécrive jamais un devis ou une facture.
    database.execute(
        """
        UPDATE billing_records
        SET rate_unit_cents = CASE
                WHEN rate_is_agglo = 1 THEN 0
                WHEN rate_category = 'reduced' AND rate_unit = 'hourly' THEN 3000
                WHEN rate_category = 'reduced' AND rate_unit = 'half_day' THEN 6000
                WHEN rate_unit = 'half_day' THEN 12000
                ELSE 6000 END
        WHERE rate_unit_cents = 0 AND rate_is_agglo = 0
        """
    )
    for row in database.execute(
        "SELECT id, activity_time_details FROM billing_records "
        "WHERE activity_start_time IS NULL AND activity_time_details IS NOT NULL"
    ).fetchall():
        parsed = parse_legacy_time_range(row["activity_time_details"])
        if parsed:
            start_time, end_time, duration_minutes = parsed
            database.execute(
                "UPDATE billing_records SET activity_start_time = ?, "
                "activity_end_time = ?, activity_duration_minutes = ? WHERE id = ?",
                (start_time, end_time, duration_minutes, row["id"]),
            )


def migrate_services_schema(database):
    """Ajoute les informations de programmation sans perdre les animations."""
    existing_columns = {
        row["name"]
        for row in database.execute("PRAGMA table_info(fablab_services)").fetchall()
    }
    additions = {
        "start_time": "TEXT",
        "end_time": "TEXT",
        "duration_minutes": "INTEGER",
        "minimum_age": "INTEGER NOT NULL DEFAULT 10",
        "description": "TEXT",
    }
    for column, definition in additions.items():
        if column not in existing_columns:
            database.execute(
                f"ALTER TABLE fablab_services ADD COLUMN {column} {definition}"
            )


def migrate_attendance_corrections_schema(database):
    """Ajoute le journal minimal des corrections sans toucher à l'historique."""
    database.executescript(
        """
        CREATE TABLE IF NOT EXISTS attendance_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action_at TEXT NOT NULL,
            action_type TEXT NOT NULL
                CHECK (action_type IN ('add', 'update', 'delete')),
            record_type TEXT NOT NULL
                CHECK (record_type IN ('session', 'visitor')),
            record_id INTEGER,
            old_values_json TEXT,
            new_values_json TEXT
        );
        CREATE INDEX IF NOT EXISTS attendance_corrections_action_at_index
            ON attendance_corrections(action_at);
        PRAGMA user_version = 8;
        """
    )


def migrate_weather_snapshots_schema(database):
    """Ajoute les relevés météo trimestriels sans toucher aux données existantes."""
    database.executescript(
        """
        CREATE TABLE IF NOT EXISTS weather_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quarter_start TEXT NOT NULL UNIQUE,
            temperature_c REAL NOT NULL,
            apparent_temperature_c REAL,
            weather_code INTEGER NOT NULL,
            precipitation_mm REAL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS weather_snapshots_quarter_start_index
            ON weather_snapshots(quarter_start);
        PRAGMA user_version = 9;
        """
    )


def migrate_security_events_schema(database):
    """Schéma 10 : journal technique court, sans code ni identité."""
    database.executescript(
        """
        CREATE TABLE IF NOT EXISTS security_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            details_json TEXT
        );
        CREATE INDEX IF NOT EXISTS security_events_type_date_index
            ON security_events(event_type, created_at);
        PRAGMA user_version = 10;
        """
    )


def migrate_reservations_schema(database):
    """Schema 11: publication settings and an idempotent booking mirror."""
    columns = {row["name"] for row in database.execute("PRAGMA table_info(users)")}
    if "updated_at" not in columns:
        database.execute("ALTER TABLE users ADD COLUMN updated_at TEXT")
        database.execute("UPDATE users SET updated_at = created_at WHERE updated_at IS NULL")
    database.executescript(
        """
        CREATE TABLE IF NOT EXISTS animation_reservation_config (
            service_id INTEGER PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
            environment TEXT NOT NULL DEFAULT 'test' CHECK (environment IN ('test', 'production')),
            audience TEXT NOT NULL DEFAULT 'all' CHECK (audience IN ('all', 'registered')),
            capacity INTEGER NOT NULL DEFAULT 0 CHECK (capacity >= 0),
            signup_open_at TEXT,
            close_minutes INTEGER NOT NULL DEFAULT 60,
            accompaniment_under_age INTEGER NOT NULL DEFAULT 15,
            waitlist_enabled INTEGER NOT NULL DEFAULT 1 CHECK (waitlist_enabled IN (0, 1)),
            reminder_one_hours INTEGER,
            reminder_two_hours INTEGER,
            walkin_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (service_id) REFERENCES fablab_services(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS animation_bookings (
            external_uuid TEXT PRIMARY KEY,
            service_id INTEGER NOT NULL,
            environment TEXT NOT NULL CHECK (environment IN ('test', 'production')),
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            birth_year INTEGER,
            email TEXT,
            phone TEXT,
            status TEXT NOT NULL,
            link_status TEXT NOT NULL,
            public_id TEXT,
            user_id INTEGER,
            group_uuid TEXT,
            source TEXT NOT NULL DEFAULT 'online',
            is_present INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (service_id) REFERENCES fablab_services(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS animation_bookings_service_index
            ON animation_bookings(service_id, environment, status);
        CREATE TABLE IF NOT EXISTS reservation_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_uuid TEXT NOT NULL,
            action TEXT NOT NULL,
            actor_role TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reservation_sync_events (
            external_event_id TEXT PRIMARY KEY,
            environment TEXT NOT NULL CHECK (environment IN ('test', 'production')),
            received_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS reservation_sync_state (
            environment TEXT PRIMARY KEY CHECK (environment IN ('test', 'production')),
            cursor TEXT NOT NULL DEFAULT '',
            last_success_at TEXT,
            last_error_at TEXT,
            last_error TEXT
        );
        CREATE TABLE IF NOT EXISTS reservation_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            environment TEXT NOT NULL CHECK (environment IN ('test', 'production')),
            command_type TEXT NOT NULL,
            entity_key TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            sent_at TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT
        );
        CREATE INDEX IF NOT EXISTS reservation_outbox_unsent_index
            ON reservation_outbox(sent_at, id);
        PRAGMA user_version = 11;
        """
    )
    config_columns = {row["name"] for row in database.execute(
        "PRAGMA table_info(animation_reservation_config)"
    )}
    if "walkin_count" not in config_columns:
        database.execute("ALTER TABLE animation_reservation_config ADD COLUMN walkin_count INTEGER NOT NULL DEFAULT 0")
    booking_columns = {row["name"] for row in database.execute(
        "PRAGMA table_info(animation_bookings)"
    )}
    if "verified_at" not in booking_columns:
        database.execute("ALTER TABLE animation_bookings ADD COLUMN verified_at TEXT")
    if "verified_by_role" not in booking_columns:
        database.execute("ALTER TABLE animation_bookings ADD COLUMN verified_by_role TEXT")
    sync_columns = {row["name"] for row in database.execute("PRAGMA table_info(reservation_sync_state)")}
    if "last_attempt_at" not in sync_columns:
        database.execute("ALTER TABLE reservation_sync_state ADD COLUMN last_attempt_at TEXT")


def migrate_catalog_schema(database):
    """Schema 12: rental lifecycle and optional reusable custom quote tariffs."""
    columns = {row["name"] for row in database.execute("PRAGMA table_info(rental_catalog)")}
    if "archived" not in columns:
        database.execute("ALTER TABLE rental_catalog ADD COLUMN archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1))")
    for column in ("custom_tariff_key", "custom_tariff_name"):
        record_columns = {row["name"] for row in database.execute("PRAGMA table_info(billing_records)")}
        if column not in record_columns:
            database.execute(f"ALTER TABLE billing_records ADD COLUMN {column} TEXT")
    database.execute("""
        CREATE TABLE IF NOT EXISTS billing_tariff_catalog (
            tariff_key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            unit TEXT NOT NULL CHECK (unit IN ('hourly', 'half_day')),
            cents INTEGER NOT NULL CHECK (cents >= 0),
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
            archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    database.execute("PRAGMA user_version = 12")


def migrate_animation_slots_schema(database):
    """Schema 13: additive slots; every historical animation stays whole."""
    columns = {row["name"] for row in database.execute("PRAGMA table_info(animation_reservation_config)")}
    for name, definition in (
        ("booking_mode", "TEXT NOT NULL DEFAULT 'whole' CHECK(booking_mode IN ('whole','slots'))"),
        ("slot_duration_minutes", "INTEGER NOT NULL DEFAULT 20"),
        ("slot_gap_minutes", "INTEGER NOT NULL DEFAULT 0"),
        ("slot_capacity", "INTEGER NOT NULL DEFAULT 1"),
    ):
        if name not in columns:
            database.execute(f"ALTER TABLE animation_reservation_config ADD COLUMN {name} {definition}")
    database.execute("CREATE TABLE IF NOT EXISTS animation_slots (slot_uuid TEXT PRIMARY KEY, "
                     "service_id INTEGER NOT NULL REFERENCES fablab_services(id) ON DELETE CASCADE, "
                     "starts_at TEXT NOT NULL, ends_at TEXT NOT NULL, capacity INTEGER NOT NULL CHECK(capacity>0), "
                     "active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)))")
    columns = {row["name"] for row in database.execute("PRAGMA table_info(animation_bookings)")}
    if "slot_uuid" not in columns:
        database.execute("ALTER TABLE animation_bookings ADD COLUMN slot_uuid TEXT REFERENCES animation_slots(slot_uuid)")
    database.execute("CREATE INDEX IF NOT EXISTS animation_bookings_slot_index ON animation_bookings(service_id, slot_uuid, status)")
    database.execute("PRAGMA user_version = 13")


def seed_rental_catalog(database):
    """Installe le catalogue initial uniquement si aucune machine n'existe."""
    if database.execute("SELECT 1 FROM rental_catalog LIMIT 1").fetchone():
        return
    timestamp = utc_now_iso()
    database.executemany(
        """
        INSERT INTO rental_catalog (
            machine_key, name, monthly_cents, deposit_cents,
            active, sort_order, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 1, ?, ?, ?)
        """,
        [
            (key, machine["name"], machine["monthly_cents"],
             machine["deposit_cents"], index, timestamp, timestamp)
            for index, (key, machine) in enumerate(DEFAULT_RENTAL_CATALOG.items(), 1)
        ],
    )


def load_rental_catalog(database, include_inactive=False):
    """Retourne le catalogue éditable dans un format compatible avec les vues."""
    condition = "" if include_inactive else "WHERE active = 1 AND archived = 0"
    rows = database.execute(
        "SELECT * FROM rental_catalog " + condition + " ORDER BY sort_order, name"
    ).fetchall()
    return {row["machine_key"]: dict(row) for row in rows}


def available_rental_catalog(database, record=None):
    """Offer active machines plus the historical machine of the edited dossier."""
    catalog = load_rental_catalog(database)
    previous_key = (record or {}).get("rental_machine_key")
    if previous_key and previous_key not in catalog:
        previous = load_rental_catalog(database, include_inactive=True).get(previous_key)
        if previous:
            catalog[previous_key] = previous
    return catalog


def load_custom_tariffs(database, include_inactive=False):
    condition = "" if include_inactive else "WHERE active = 1 AND archived = 0"
    rows = database.execute(
        "SELECT * FROM billing_tariff_catalog " + condition + " ORDER BY sort_order, name"
    ).fetchall()
    return {row["tariff_key"]: dict(row) for row in rows}


def read_cents_setting(database, key, default):
    try:
        return max(0, int(read_setting(database, key, str(default))))
    except (TypeError, ValueError):
        return default


def parse_money_cents(value, label, maximum=1000000):
    """Convertit un tarif éditable en centimes sans flottant."""
    try:
        amount = Decimal((value or "").strip().replace(",", "."))
        if not amount.is_finite() or amount < 0 or amount > Decimal(maximum):
            raise InvalidOperation
        return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)), None
    except (InvalidOperation, ValueError):
        return 0, f"{label} doit être un montant positif valide."


def load_billing_tariffs(database):
    """Centralise les tarifs modifiables utilisés pour les nouveaux dossiers."""
    return {
        "normal_hourly": read_cents_setting(database, "billing_rate_normal_hourly_cents", 6000),
        "normal_half_day": read_cents_setting(database, "billing_rate_normal_half_day_cents", 12000),
        "reduced_hourly": read_cents_setting(database, "billing_rate_reduced_hourly_cents", 3000),
        "reduced_half_day": read_cents_setting(database, "billing_rate_reduced_half_day_cents", 6000),
        "travel": read_cents_setting(database, "billing_travel_unit_cents", 6000),
        "consumable": read_cents_setting(database, "billing_consumable_unit_cents", 3000),
        "rental_contract": read_cents_setting(database, "billing_rental_contract_fee_cents", 2500),
        "rental_delivery": read_cents_setting(database, "billing_rental_delivery_fee_cents", 3000),
    }


def create_statistics_triggers(database):
    """Complète aussi les insertions techniques réalisées hors de l'interface."""
    database.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS users_statistics_key_after_insert
        AFTER INSERT ON users
        WHEN NEW.statistics_key IS NULL OR TRIM(NEW.statistics_key) = ''
        BEGIN
            UPDATE users
            SET statistics_key = LOWER(HEX(RANDOMBLOB(16)))
            WHERE id = NEW.id;
        END;

        CREATE TRIGGER IF NOT EXISTS sessions_statistics_after_insert
        AFTER INSERT ON sessions
        WHEN NEW.statistical_user_key IS NULL OR TRIM(NEW.statistical_user_key) = ''
        BEGIN
            UPDATE sessions
            SET statistical_user_key = COALESCE(
                    (SELECT statistics_key FROM users WHERE id = NEW.user_id),
                    LOWER(HEX(RANDOMBLOB(16)))
                ),
                statistical_category = COALESCE(
                    (SELECT category FROM users WHERE id = NEW.user_id), 'user'
                ),
                statistical_birth_year = (SELECT birth_year FROM users WHERE id = NEW.user_id),
                statistical_gender = (SELECT gender FROM users WHERE id = NEW.user_id),
                statistical_city = (SELECT city FROM users WHERE id = NEW.user_id),
                statistical_city_normalized = (SELECT city_normalized FROM users WHERE id = NEW.user_id),
                statistical_postal_code = (SELECT postal_code FROM users WHERE id = NEW.user_id),
                statistical_nationality = (SELECT nationality FROM users WHERE id = NEW.user_id),
                statistical_nationality_normalized = (SELECT nationality_normalized FROM users WHERE id = NEW.user_id)
            WHERE id = NEW.id;
        END;
        """
    )


def normalize_text_key(value):
    """Crée une clé stable sans accent ni différence de casse."""
    if not value:
        return None
    decomposed = unicodedata.normalize("NFKD", value.strip().casefold())
    without_accents = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    words_only = re.sub(r"[^a-z0-9]+", " ", without_accents)
    return " ".join(words_only.split()) or None


def upsert_billing_client(database, values, existing_client_id=None, timestamp=None):
    """Crée ou actualise la fiche client liée à un devis."""
    normalized_contact = normalize_text_key(values.get("client_contact"))
    if not normalized_contact:
        raise ValueError("Le nom du contact est obligatoire.")
    timestamp = timestamp or utc_now_iso()
    matching_client = database.execute(
        "SELECT id FROM billing_clients WHERE contact_name_normalized = ?",
        (normalized_contact,),
    ).fetchone()
    if matching_client is not None:
        client_id = matching_client["id"]
    elif existing_client_id:
        existing_client = database.execute(
            "SELECT id FROM billing_clients WHERE id = ?", (existing_client_id,)
        ).fetchone()
        client_id = existing_client["id"] if existing_client else None
    else:
        client_id = None

    parameters = (
        values["client_contact"], normalized_contact,
        values["client_structure"], values["address_line"],
        values["postal_code"], values["city"],
        values.get("phone") or None, values.get("email") or None,
        timestamp,
    )
    if client_id is None:
        cursor = database.execute(
            """
            INSERT INTO billing_clients (
                contact_name, contact_name_normalized, structure_name,
                address_line, postal_code, city, phone, email,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*parameters[:-1], timestamp, timestamp),
        )
        return cursor.lastrowid

    database.execute(
        """
        UPDATE billing_clients SET contact_name = ?, contact_name_normalized = ?,
            structure_name = ?, address_line = ?, postal_code = ?, city = ?,
            phone = ?, email = ?, updated_at = ?
        WHERE id = ?
        """,
        (*parameters, client_id),
    )
    return client_id


def country_name_from_key(normalized_key):
    """Retrouve le nom français canonique d'un pays à partir de sa clé."""
    if not normalized_key:
        return None
    alias_name = COUNTRY_ALIASES.get(normalized_key)
    if alias_name:
        return alias_name
    for country_name in COUNTRY_NAMES:
        if normalize_text_key(country_name) == normalized_key:
            return country_name
    return None


def canonical_country_name(value):
    """Transforme une nationalité ou un nom de pays connu en nom de pays."""
    if not value:
        return ""
    stripped_value = value.strip()
    normalized = normalize_text_key(stripped_value)
    return country_name_from_key(normalized) or stripped_value


def normalize_nationality(value):
    """Crée une clé commune pour les adjectifs de nationalité et les pays."""
    return normalize_text_key(canonical_country_name(value))


def normalize_last_name(value):
    """Uniformise un nom de famille en capitales, accents compris."""
    return re.sub(r"\s+", " ", (value or "").strip()).upper()


def normalize_first_name(value):
    """Capitalise chaque segment séparé par espace, tiret ou apostrophe Unicode."""
    cleaned = re.sub(r"\s+", " ", (value or "").strip())
    return "".join(
        segment[:1].upper() + segment[1:].lower()
        if index % 2 == 0 else segment
        for index, segment in enumerate(re.split(r"([ '\u2019-])", cleaned))
    )


def normalize_phone_country_code(value):
    """Conserve un indicatif international sous la forme canonique +NN."""
    compact = re.sub(r"\s+", "", (value or "+33").strip())
    if compact.startswith("00"):
        compact = f"+{compact[2:]}"
    return compact or "+33"


def format_phone_pairs(digits):
    """Présente les chiffres par paires, avec un premier chiffre si nécessaire."""
    if not digits:
        return ""
    first_group_length = 1 if len(digits) % 2 else 2
    groups = [digits[:first_group_length]]
    groups.extend(
        digits[index:index + 2]
        for index in range(first_group_length, len(digits), 2)
    )
    return " ".join(group for group in groups if group)


def normalize_user_phone(country_code, phone_number):
    """Sépare l'indicatif et formate le numéro national d'une fiche usager."""
    normalized_code = normalize_phone_country_code(country_code)
    raw_number = (phone_number or "").strip()
    if not raw_number:
        return normalized_code, ""

    compact_number = re.sub(r"[().\-\s]", "", raw_number)
    canonical_prefix = normalized_code[1:]
    if compact_number.startswith("+"):
        if compact_number[1:].startswith(canonical_prefix):
            compact_number = compact_number[1 + len(canonical_prefix):]
        elif compact_number.startswith("+33"):
            normalized_code = "+33"
            compact_number = compact_number[3:]
    elif compact_number.startswith("00"):
        if compact_number[2:].startswith(canonical_prefix):
            compact_number = compact_number[2 + len(canonical_prefix):]
        elif compact_number.startswith("0033"):
            normalized_code = "+33"
            compact_number = compact_number[4:]

    digits = re.sub(r"\D", "", compact_number)
    if normalized_code == "+33" and len(digits) == 9:
        digits = f"0{digits}"
    return normalized_code, format_phone_pairs(digits)


def canonicalize_session_nationalities(database):
    """Uniformise les pays des copies statistiques déjà anonymisées."""
    session_rows = database.execute(
        """
        SELECT id, statistical_nationality
        FROM sessions
        WHERE statistical_nationality IS NOT NULL
          AND TRIM(statistical_nationality) != ''
        """
    ).fetchall()
    for session_row in session_rows:
        country_name = canonical_country_name(session_row["statistical_nationality"])
        database.execute(
            """
            UPDATE sessions
            SET statistical_nationality = ?,
                statistical_nationality_normalized = ?
            WHERE id = ?
            """,
            (
                country_name,
                normalize_nationality(country_name),
                session_row["id"],
            ),
        )


def next_available_public_id(database):
    """Retourne le premier code à 4 chiffres disponible à partir de 1001."""
    used_codes = {
        row["public_id"]
        for row in database.execute(
            "SELECT public_id FROM users WHERE public_id IS NOT NULL"
        ).fetchall()
    }
    for candidate in range(1001, 10000):
        if str(candidate) not in used_codes:
            return str(candidate)
    raise RuntimeError("Aucun identifiant public à quatre chiffres disponible")


def validate_user_form(form, database, current_user_id=None, public_enrollment=False):
    """Nettoie et valide les données saisies dans une fiche usager."""
    data = {
        "public_id": form.get("public_id", "").strip(),
        "first_name": normalize_first_name(form.get("first_name", "")),
        "last_name": normalize_last_name(form.get("last_name", "")),
        "birth_year": (form.get('birth_date', '')[:4] if form.get('birth_date') else form.get("birth_year", "").strip()),
        "gender": form.get("gender", "").strip(),
        "city": form.get("city", "").strip(),
        "postal_code": form.get("postal_code", "").strip(),
        "nationality": form.get("nationality", "").strip(),
        "email": form.get("email", "").strip(),
        "phone_country_code": form.get("phone_country_code", "+33").strip(),
        "phone": form.get("phone", "").strip(),
        "category": form.get("category", "user").strip(),
        "active": 1 if form.get("active") == "1" else 0,
    }
    errors = []

    if len(data["public_id"]) != 4 or not data["public_id"].isdigit():
        errors.append("L'identifiant doit contenir exactement 4 chiffres.")
    elif int(data["public_id"]) < 1001:
        errors.append("L'identifiant doit être compris entre 1001 et 9999.")
    else:
        duplicate = database.execute(
            """
            SELECT id FROM users
            WHERE public_id = ? AND (? IS NULL OR id != ?)
            """,
            (data["public_id"], current_user_id, current_user_id),
        ).fetchone()
        if duplicate:
            errors.append("Cet identifiant est déjà utilisé par un autre usager.")

    if not data["first_name"]:
        errors.append("Le prénom est obligatoire.")
    if not data["last_name"]:
        errors.append("Le nom est obligatoire.")
    if len(data["first_name"]) > 80 or len(data["last_name"]) > 80:
        errors.append("Le prénom et le nom sont limités à 80 caractères.")

    if data["birth_year"]:
        try:
            birth_year = int(data["birth_year"])
            current_year = datetime.now(PARIS_TIMEZONE).year
            if birth_year < 1900 or birth_year > current_year:
                raise ValueError
            data["birth_year"] = birth_year
        except ValueError:
            errors.append("L'année de naissance n'est pas valide.")
    else:
        data["birth_year"] = None

    if data["gender"] not in ALLOWED_GENDERS and data["gender"]:
        errors.append("La valeur choisie pour le genre n'est pas valide.")
    if not data["gender"]:
        data["gender"] = None

    if current_user_id is None and not public_enrollment:
        for key, label in (("birth_year", "L'année de naissance"),
                           ("city", "La commune"),
                           ("nationality", "La nationalité")):
            if not data[key]:
                errors.append(f"{label} est obligatoire pour un nouvel usager.")

    category_row = database.execute('SELECT active FROM user_categories WHERE category_key=?', (data['category'],)).fetchone()
    existing_category = database.execute('SELECT category FROM users WHERE id=?', (current_user_id,)).fetchone() if current_user_id else None
    if not category_row or (not category_row['active'] and (not existing_category or existing_category[0]!=data['category'])):
        errors.append("La catégorie choisie n'est pas valide.")

    for field_name, label, maximum_length in (
        ("city", "La commune", 100),
        ("postal_code", "Le code postal", 12),
        ("nationality", "La nationalité", 80),
        ("email", "L'adresse e-mail", 254),
        ("phone_country_code", "L'indicatif téléphonique", 7),
        ("phone", "Le numéro de téléphone", 30),
    ):
        if len(data[field_name]) > maximum_length:
            errors.append(f"{label} dépasse la longueur autorisée.")

    if data["email"] and not EMAIL_PATTERN.fullmatch(data["email"]):
        errors.append("L'adresse e-mail n'est pas valide.")
    if data["phone"] and not PHONE_PATTERN.fullmatch(data["phone"]):
        errors.append("Le numéro de téléphone contient des caractères non autorisés.")
    compact_country_code = re.sub(r"\s+", "", data["phone_country_code"])
    if not PHONE_COUNTRY_CODE_PATTERN.fullmatch(compact_country_code):
        errors.append("L'indicatif téléphonique doit commencer par + ou 00, suivi de 1 à 4 chiffres.")
    else:
        data["phone_country_code"] = normalize_phone_country_code(compact_country_code)
    if data["phone"]:
        digits_only = re.sub(r"\D", "", data["phone"])
        if len(digits_only) > 15:
            errors.append("Le numéro de téléphone contient trop de chiffres.")
        data["phone_country_code"], data["phone"] = normalize_user_phone(
            data["phone_country_code"], data["phone"]
        )
    else:
        data["phone"] = ""

    data["city_normalized"] = normalize_text_key(data["city"])
    data["nationality"] = canonical_country_name(data["nationality"])
    data["nationality_normalized"] = normalize_nationality(data["nationality"])

    from family_model import validate_form as validate_family_form
    validate_family_form(database, form, data, errors, current_user_id, public_enrollment)
    return data, errors


def find_possible_user_duplicates(database, user_data):
    """Ne restitue que les données autorisées à la vérification d'un homonyme."""
    matches = []
    wanted_name = (normalize_text_key(user_data["first_name"]), normalize_text_key(user_data["last_name"]))
    wanted_email = (user_data.get("email") or "").casefold()
    wanted_phone = re.sub(r"\D", "", user_data.get("phone") or "")
    wanted_country = user_data.get("phone_country_code") or "+33"
    rows = database.execute(
        "SELECT public_id, first_name, last_name, active, email, phone_country_code, phone FROM users"
    ).fetchall()
    for row in rows:
        same_name = (normalize_text_key(row["first_name"]), normalize_text_key(row["last_name"])) == wanted_name
        same_email = bool(wanted_email and (row["email"] or "").casefold() == wanted_email)
        same_phone = bool(
            wanted_phone and row["phone_country_code"] == wanted_country
            and re.sub(r"\D", "", row["phone"] or "") == wanted_phone
        )
        if same_name or same_email or same_phone:
            matches.append({"public_id": row["public_id"], "first_name": row["first_name"],
                            "last_name": row["last_name"], "active": bool(row["active"])})
    return matches


def utc_now_iso():
    """Produit un horodatage ISO explicite en UTC."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_timestamp(value):
    """Transforme un horodatage ISO ou datetime en valeur consciente de son fuseau."""
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        # Compatibilité défensive avec d'éventuelles anciennes données.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def today_utc_bounds():
    """Retourne les limites UTC de la journée courante en Europe/Paris."""
    now_in_paris = datetime.now(PARIS_TIMEZONE)
    local_start = now_in_paris.replace(hour=0, minute=0, second=0, microsecond=0)
    local_end = local_start + timedelta(days=1)
    return (
        local_start.astimezone(timezone.utc).isoformat(timespec="seconds"),
        local_end.astimezone(timezone.utc).isoformat(timespec="seconds"),
    )


def parse_local_day(value=None):
    """Valide une date d'administration, par défaut celle de Paris."""
    raw_value = (value or "").strip()
    if not raw_value:
        return datetime.now(PARIS_TIMEZONE).date()
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError:
        return datetime.now(PARIS_TIMEZONE).date()


def local_day_utc_bounds(local_day):
    """Convertit les limites d'une journée parisienne vers les valeurs SQLite UTC."""
    local_start = datetime.combine(local_day, datetime.min.time(), PARIS_TIMEZONE)
    local_end = local_start + timedelta(days=1)
    return (
        local_start.astimezone(timezone.utc),
        local_end.astimezone(timezone.utc),
    )


def parse_admin_local_datetime(date_value, time_value, label):
    """Interprète un horaire saisi en Europe/Paris et refuse les heures inexistantes."""
    cleaned_date = (date_value or "").strip()
    cleaned_time = (time_value or "").strip()
    try:
        naive = datetime.strptime(
            f"{cleaned_date} {cleaned_time}", "%Y-%m-%d %H:%M"
        )
    except ValueError:
        return None, f"{label} n'est pas valide."
    local_value = naive.replace(tzinfo=PARIS_TIMEZONE)
    utc_value = local_value.astimezone(timezone.utc)
    round_trip = utc_value.astimezone(PARIS_TIMEZONE)
    if round_trip.replace(tzinfo=None) != naive:
        return None, f"{label} n'existe pas dans le fuseau Europe/Paris."
    return utc_value, None


def attendance_record_values(row, record_type):
    """Limite les valeurs conservées dans l'audit aux champs utiles au diagnostic."""
    if row is None:
        return None
    fields = (
        ("id", "user_id", "check_in", "check_out", "entry_method", "exit_method")
        if record_type == "session"
        else ("id", "created_at")
    )
    return {field: row[field] for field in fields}


def presence_method_label(value):
    """Retourne un libellé métier sûr, y compris pour une ancienne valeur inconnue."""
    normalized = str(value or "").strip().lower()
    if not normalized:
        return "—"
    if normalized in PRESENCE_METHOD_LABELS:
        return PRESENCE_METHOD_LABELS[normalized]
    return normalized.replace("_", " ").replace("-", " ").capitalize()


def humanize_attendance_audit_json(value):
    """Masque les codes techniques de méthode dans le journal affiché."""
    if not value:
        return "—"
    try:
        payload = json.loads(value)
    except (TypeError, ValueError):
        return str(value)
    if isinstance(payload, dict):
        for key in ("entry_method", "exit_method"):
            if key in payload:
                payload[key] = presence_method_label(payload[key])
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def record_attendance_correction(
    database, action_type, record_type, record_id, old_values=None, new_values=None
):
    """Écrit une trace technique compacte d'une correction administrateur."""
    database.execute(
        """
        INSERT INTO attendance_corrections (
            action_at, action_type, record_type, record_id,
            old_values_json, new_values_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            utc_now_iso(),
            action_type,
            record_type,
            record_id,
            json.dumps(old_values, ensure_ascii=False, sort_keys=True)
            if old_values is not None
            else None,
            json.dumps(new_values, ensure_ascii=False, sort_keys=True)
            if new_values is not None
            else None,
        ),
    )


def session_overlaps(database, user_id, check_in, check_out=None, exclude_id=None):
    """Empêche deux sessions du même usager de se chevaucher."""
    far_future = "9999-12-31T23:59:59+00:00"
    parameters = [
        user_id,
        check_out or far_future,
        check_in,
    ]
    exclusion = ""
    if exclude_id is not None:
        exclusion = "AND id != ?"
        parameters.append(exclude_id)
    return database.execute(
        f"""
        SELECT 1 FROM sessions
        WHERE user_id = ?
          AND check_in < ?
          AND COALESCE(check_out, ?) > ?
          {exclusion}
        LIMIT 1
        """,
        (parameters[0], parameters[1], far_future, *parameters[2:]),
    ).fetchone() is not None


def load_day_attendance(database, local_day, start_time=None, end_time=None):
    """Construit les indicateurs et la chronologie d'une journée précise."""
    day_start, day_end = local_day_utc_bounds(local_day)
    if start_time and end_time:
        day_start = datetime.combine(local_day, datetime.strptime(start_time, '%H:%M').time(), PARIS_TIMEZONE).astimezone(timezone.utc)
        day_end = datetime.combine(local_day, datetime.strptime(end_time, '%H:%M').time(), PARIS_TIMEZONE).astimezone(timezone.utc)
    start_iso = day_start.isoformat(timespec="seconds")
    end_iso = day_end.isoformat(timespec="seconds")
    session_rows = database.execute(
        """
        SELECT sessions.*, users.public_id,
               COALESCE(users.first_name, 'Ancien') AS first_name,
               COALESCE(users.last_name, 'usager') AS last_name
        FROM sessions
        LEFT JOIN users ON users.id = sessions.user_id
        WHERE sessions.check_in >= ? AND sessions.check_in < ?
        ORDER BY sessions.check_in, sessions.id
        """,
        (start_iso, end_iso),
    ).fetchall()
    visitor_rows = database.execute(
        """
        SELECT id, created_at FROM visitors
        WHERE created_at >= ? AND created_at < ?
        ORDER BY created_at, id
        """,
        (start_iso, end_iso),
    ).fetchall()

    sessions = []
    completed_durations = []
    distinct_users = set()
    timeline = []
    for row in session_rows:
        check_in = parse_timestamp(row["check_in"])
        check_out = parse_timestamp(row["check_out"]) if row["check_out"] else None
        local_check_in = check_in.astimezone(PARIS_TIMEZONE)
        local_check_out = check_out.astimezone(PARIS_TIMEZONE) if check_out else None
        duration_seconds = (
            max(0, int((check_out - check_in).total_seconds())) if check_out else None
        )
        if duration_seconds is not None:
            completed_durations.append(duration_seconds)
        distinct_users.add(row["statistical_user_key"] or f"session-{row['id']}")
        item = {
            "row": row,
            "id": row["id"],
            "identity": f"{row['first_name']} {row['last_name']}",
            "check_in": check_in,
            "check_out": check_out,
            "check_in_date": local_check_in.strftime("%Y-%m-%d"),
            "check_in_time": local_check_in.strftime("%H:%M"),
            "check_out_date": local_check_out.strftime("%Y-%m-%d") if local_check_out else "",
            "check_out_time": local_check_out.strftime("%H:%M") if local_check_out else "",
            "duration_seconds": duration_seconds,
        }
        sessions.append(item)
        timeline.append({"kind": "session", "at": check_in, "item": item})

    visitors = []
    for row in visitor_rows:
        created_at = parse_timestamp(row["created_at"])
        local_created_at = created_at.astimezone(PARIS_TIMEZONE)
        item = {
            "id": row["id"],
            "created_at": created_at,
            "date": local_created_at.strftime("%Y-%m-%d"),
            "time": local_created_at.strftime("%H:%M"),
        }
        visitors.append(item)
        timeline.append({"kind": "visitor", "at": created_at, "item": item})
    timeline.sort(key=lambda item: (item["at"], item["kind"]))

    overlapping_rows = database.execute(
        """
        SELECT check_in, check_out FROM sessions
        WHERE check_in < ? AND (check_out IS NULL OR check_out > ?)
        """,
        (end_iso, start_iso),
    ).fetchall()
    now_utc = datetime.now(timezone.utc)
    events = []
    for row in overlapping_rows:
        check_in = max(parse_timestamp(row["check_in"]), day_start)
        natural_end = parse_timestamp(row["check_out"]) if row["check_out"] else now_utc
        check_out = min(natural_end, day_end)
        if check_out < check_in:
            continue
        events.append((check_in, 1))
        events.append((check_out, -1))
    simultaneous = peak = 0
    peak_at = None
    for moment, delta in sorted(events, key=lambda event: (event[0], event[1])):
        simultaneous += delta
        if simultaneous > peak:
            peak = simultaneous
            peak_at = moment

    peak_quarter = quarter_start(peak_at) if peak_at is not None else None
    peak_period = None
    peak_weather = None
    if peak_quarter is not None:
        peak_period = (
            f"{peak_quarter.strftime('%Hh%M')}–"
            f"{(peak_quarter + timedelta(minutes=15)).strftime('%Hh%M')}"
        )
        peak_weather = load_weather_snapshot(database, peak_quarter)

    total_duration = sum(completed_durations)
    graph = build_day_attendance_graph(
        database, local_day, overlapping_rows, visitor_rows
    )
    return {
        "date": local_day.isoformat(),
        "sessions": sessions,
        "visitors": visitors,
        "timeline": timeline,
        "graph": graph,
        "summary": {
            "unique_users": len(distinct_users),
            "sessions": len(sessions),
            "visitors": len(visitors),
            "total": len(sessions) + len(visitors),
            "duration_seconds": total_duration,
            "average_seconds": round(total_duration / len(completed_durations))
            if completed_durations
            else 0,
            "peak_users": peak,
            "peak_at": peak_at.astimezone(PARIS_TIMEZONE).strftime('%H:%M') if peak_at else None,
            "peak_period": peak_period,
            "peak_weather": peak_weather,
        },
    }


def get_dashboard_counts(database):
    """Calcule les compteurs communs à l'accueil et à l'administration."""
    day_start, day_end = today_utc_bounds()
    present_count = database.execute(
        "SELECT COUNT(*) FROM sessions WHERE check_out IS NULL"
    ).fetchone()[0]
    visitor_count = database.execute(
        """
        SELECT COUNT(*) FROM visitors
        WHERE created_at >= ? AND created_at < ?
        """,
        (day_start, day_end),
    ).fetchone()[0]
    sessions_today = database.execute(
        """
        SELECT COUNT(*) FROM sessions
        WHERE check_in >= ? AND check_in < ?
        """,
        (day_start, day_end),
    ).fetchone()[0]
    return present_count, visitor_count, sessions_today


def weather_code_display(weather_code):
    """Associe le code météo WMO à une icône courte et compréhensible."""
    if weather_code == 0:
        return "☀️", "Ciel dégagé"
    if weather_code in {1, 2}:
        return "🌤️", "Éclaircies"
    if weather_code == 3:
        return "☁️", "Ciel couvert"
    if weather_code in {45, 48}:
        return "🌫️", "Brouillard"
    if weather_code in {51, 53, 55, 56, 57, 80, 81, 82}:
        return "🌦️", "Averses"
    if weather_code in {61, 63, 65, 66, 67}:
        return "🌧️", "Pluie"
    if weather_code in {71, 73, 75, 77, 85, 86}:
        return "🌨️", "Neige"
    if weather_code in {95, 96, 99}:
        return "⛈️", "Orage"
    return "🌡️", "Météo extérieure"


def get_current_weather(application):
    """Retourne la météo de la structure configurée, mise en cache."""
    if not application.config["WEATHER_ENABLED"] or application.config.get("TESTING"):
        return None
    database = get_database()
    if not load_modules(database)["weather"]:
        return None
    latitude = read_setting(database, "structure_latitude", "").strip()
    longitude = read_setting(database, "structure_longitude", "").strip()
    if not latitude or not longitude:
        return None
    try:
        lat, lon = Decimal(latitude), Decimal(longitude)
        if not lat.is_finite() or not lon.is_finite() or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            return None
        location = read_setting(database, "structure_city", "").strip() or read_setting(database, "structure_name", "FabLab")
        timezone_name = read_setting(database, "structure_timezone", "Europe/Paris")
        ZoneInfo(timezone_name)
    except (InvalidOperation, ValueError, KeyError):
        return None
    weather_url = WEATHER_ENDPOINT + "?" + urllib.parse.urlencode({
        "latitude": latitude, "longitude": longitude,
        "current": "temperature_2m,apparent_temperature,weather_code,precipitation",
        "timezone": timezone_name, "forecast_days": 1,
    })

    current_monotonic_time = time.monotonic()
    with WEATHER_CACHE_LOCK:
        if (current_monotonic_time < WEATHER_CACHE["expires_at"] and
                WEATHER_CACHE.get("url") == weather_url):
            return WEATHER_CACHE["value"]

        value = None
        cache_duration = 5 * 60
        try:
            weather_request = urllib.request.Request(
                weather_url,
                headers={"User-Agent": f"OpenFabLab/{__version__}"},
            )
            with urllib.request.urlopen(weather_request, timeout=3) as response:
                payload = json.load(response)
            current = payload["current"]
            weather_code = int(current["weather_code"])
            temperature_c = float(current["temperature_2m"])
            apparent_temperature = current.get("apparent_temperature")
            precipitation = current.get("precipitation")
            icon, description = weather_code_display(weather_code)
            value = {
                "icon": icon,
                "description": description,
                "temperature": round(temperature_c),
                "temperature_c": temperature_c,
                "apparent_temperature_c": (
                    float(apparent_temperature)
                    if apparent_temperature is not None
                    else None
                ),
                "weather_code": weather_code,
                "precipitation_mm": (
                    float(precipitation) if precipitation is not None else None
                ),
                "location": location,
            }
            cache_duration = 15 * 60
        except (KeyError, TypeError, ValueError, OSError, urllib.error.URLError):
            application.logger.info("Météo temporairement indisponible")

        WEATHER_CACHE["value"] = value
        WEATHER_CACHE["url"] = weather_url
        WEATHER_CACHE["expires_at"] = current_monotonic_time + cache_duration
        return value


def quarter_start(moment):
    """Ramène un instant au début de son quart d'heure en Europe/Paris."""
    local_moment = moment.astimezone(PARIS_TIMEZONE)
    return local_moment.replace(
        minute=(local_moment.minute // 15) * 15,
        second=0,
        microsecond=0,
    )


def weather_snapshot_key(local_quarter):
    """Produit la clé UTC stable d'un quart d'heure local."""
    return local_quarter.astimezone(timezone.utc).isoformat(timespec="seconds")


def load_weather_snapshot(database, local_quarter):
    """Retourne le relevé d'un quart d'heure avec son libellé français."""
    row = database.execute(
        "SELECT * FROM weather_snapshots WHERE quarter_start = ?",
        (weather_snapshot_key(local_quarter),),
    ).fetchone()
    if row is None:
        return None
    snapshot = dict(row)
    icon, description = weather_code_display(snapshot["weather_code"])
    snapshot.update({"icon": icon, "description": description})
    return snapshot


def collect_openlab_weather_snapshot(database, application, now=None):
    """Mémorise au plus un relevé météo par quart d'heure d'OpenLab."""
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    local_time = current_time.astimezone(PARIS_TIMEZONE)
    schedule_day = load_openlab_schedule(database)[local_time.weekday()]
    minute_of_day = local_time.hour * 60 + local_time.minute
    if (
        not schedule_day["active"]
        or minute_of_day < schedule_day["start_minutes"]
        or minute_of_day >= schedule_day["end_minutes"]
    ):
        return None

    local_quarter = quarter_start(current_time)
    key = weather_snapshot_key(local_quarter)
    existing = database.execute(
        "SELECT * FROM weather_snapshots WHERE quarter_start = ?", (key,)
    ).fetchone()
    if existing is not None:
        return existing

    weather = get_current_weather(application)
    if not weather:
        return None
    try:
        temperature_c = float(weather["temperature_c"])
        weather_code = int(weather["weather_code"])
        apparent_temperature = weather.get("apparent_temperature_c")
        precipitation = weather.get("precipitation_mm")
        database.execute(
            """
            INSERT OR IGNORE INTO weather_snapshots (
                quarter_start, temperature_c, apparent_temperature_c,
                weather_code, precipitation_mm, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                key,
                temperature_c,
                float(apparent_temperature)
                if apparent_temperature is not None
                else None,
                weather_code,
                float(precipitation) if precipitation is not None else None,
                utc_now_iso(),
            ),
        )
        database.commit()
    except (KeyError, TypeError, ValueError, sqlite3.Error):
        database.rollback()
        application.logger.info("Instantané météo non enregistré", exc_info=True)
        return None
    return database.execute(
        "SELECT * FROM weather_snapshots WHERE quarter_start = ?", (key,)
    ).fetchone()


def load_communes_by_postal_code(postal_code):
    """Interroge le référentiel officiel français avec un cache local léger."""
    if not re.fullmatch(r"\d{5}", postal_code or ""):
        return [], True

    current_monotonic_time = time.monotonic()
    with COMMUNE_CACHE_LOCK:
        cached = COMMUNE_CACHE.get(postal_code)
        if cached and current_monotonic_time < cached["expires_at"]:
            return cached["communes"], cached["available"]

    query = urllib.parse.urlencode(
        {
            "codePostal": postal_code,
            "fields": "nom,codesPostaux",
            "format": "json",
        }
    )
    communes = []
    available = False
    cache_duration = 5 * 60
    try:
        commune_request = urllib.request.Request(
            f"https://geo.api.gouv.fr/communes?{query}",
            headers={"User-Agent": f"OpenFabLab/{__version__}"},
        )
        with urllib.request.urlopen(commune_request, timeout=4) as response:
            payload = json.load(response)
        if not isinstance(payload, list):
            raise ValueError("Réponse communale inattendue")
        communes = sorted(
            {
                row["nom"].strip()
                for row in payload
                if isinstance(row, dict)
                and isinstance(row.get("nom"), str)
                and row["nom"].strip()
            },
            key=str.casefold,
        )
        available = True
        cache_duration = 24 * 60 * 60
    except (
        json.JSONDecodeError,
        OSError,
        TypeError,
        ValueError,
        urllib.error.URLError,
    ):
        current_app.logger.info("Référentiel des communes temporairement indisponible")

    with COMMUNE_CACHE_LOCK:
        COMMUNE_CACHE[postal_code] = {
            "expires_at": current_monotonic_time + cache_duration,
            "communes": communes,
            "available": available,
        }
    return communes, available


def local_year(value):
    """Retourne l'année Europe/Paris d'un horodatage enregistré en UTC."""
    return parse_timestamp(value).astimezone(PARIS_TIMEZONE).year


def parse_requested_year(value, allow_total=False):
    """Valide l'année demandée, avec une période cumulée si elle est autorisée."""
    current_year = datetime.now(PARIS_TIMEZONE).year
    if allow_total and str(value or "").strip().lower() == "total":
        return "total"
    try:
        selected_year = int(value)
    except (TypeError, ValueError):
        return current_year
    if 2000 <= selected_year <= current_year:
        return selected_year
    return current_year


def hours_label(seconds):
    """Présente une durée statistique en heures avec une décimale."""
    return round(max(0, seconds) / 3600, 1)


def preferred_group_label(labels, fallback):
    """Choisit un libellé lisible parmi les variantes d'une même valeur."""
    cleaned_labels = [label.strip() for label in labels if label and label.strip()]
    if not cleaned_labels:
        return fallback

    counts = Counter(cleaned_labels)

    def label_score(item):
        label, count = item
        # À fréquence égale, une graphie accentuée est généralement plus fidèle.
        has_accent = unicodedata.normalize("NFD", label) != label
        return count, has_accent, len(label)

    return max(counts.items(), key=label_score)[0]


def distribution_rows(items, labels=None, order=None, unknown_label="Inconnu"):
    """Transforme des valeurs en lignes comptées et pourcentées pour l'interface."""
    counts = Counter(items)
    total = sum(counts.values())
    keys = order or sorted(counts, key=lambda key: (-counts[key], str(key)))
    rows = []
    for key in keys:
        count = counts.get(key, 0)
        if count == 0 and order is None:
            continue
        label = labels.get(key, key) if labels else key
        rows.append(
            {
                "key": key or "unknown",
                "label": label or unknown_label,
                "count": count,
                "percentage": round(count / total * 100, 1) if total else 0,
            }
        )
    return rows


def limited_distribution_rows(rows, maximum=10):
    """Limite une répartition aux valeurs principales puis regroupe le reste."""
    if len(rows) <= maximum:
        return rows, {row["key"] for row in rows}

    visible_rows = rows[:maximum]
    visible_keys = {row["key"] for row in visible_rows}
    other_count = sum(row["count"] for row in rows[maximum:])
    total = sum(row["count"] for row in rows)
    return (
        visible_rows
        + [
            {
                "key": "__other__",
                "label": "Autres",
                "count": other_count,
                "percentage": round(other_count / total * 100, 1) if total else 0,
            }
        ],
        visible_keys,
    )


def load_openlab_schedule(database):
    """Retourne les horaires OpenLab hebdomadaires utilisés par les statistiques."""
    schedule = []
    for weekday, (weekday_key, weekday_label) in enumerate(WEEKDAYS):
        default_start, default_end = DEFAULT_OPENLAB_SCHEDULE[weekday_key]
        start = read_setting(
            database,
            f"openlab_attendance_{weekday_key}_start",
            default_start,
        ).strip()
        end = read_setting(
            database,
            f"openlab_attendance_{weekday_key}_end",
            default_end,
        ).strip()

        active = bool(start or end)
        start_minutes = end_minutes = None
        if active:
            valid = bool(
                start
                and end
                and TIME_PATTERN.fullmatch(start)
                and TIME_PATTERN.fullmatch(end)
            )
            if valid:
                start_hour, start_minute = map(int, start.split(":"))
                end_hour, end_minute = map(int, end.split(":"))
                start_minutes = start_hour * 60 + start_minute
                end_minutes = end_hour * 60 + end_minute
                valid = (
                    start_minute % 15 == 0
                    and end_minute % 15 == 0
                    and end_minutes > start_minutes
                )
            if not valid:
                start, end = default_start, default_end
                active = bool(start and end)
                if active:
                    start_hour, start_minute = map(int, start.split(":"))
                    end_hour, end_minute = map(int, end.split(":"))
                    start_minutes = start_hour * 60 + start_minute
                    end_minutes = end_hour * 60 + end_minute
                else:
                    start_minutes = end_minutes = None

        schedule.append(
            {
                "weekday": weekday,
                "key": weekday_key,
                "label": weekday_label,
                "start": start,
                "end": end,
                "start_minutes": start_minutes,
                "end_minutes": end_minutes,
                "active": active,
            }
        )
    return schedule


def attendance_heat_color(attendance, reference=10):
    """Colore une charge réelle de 0 à 10 sans la rendre rouge artificiellement."""
    anchors = (
        (232, 242, 247),
        (173, 205, 226),
        (124, 162, 205),
        (117, 102, 182),
        (151, 76, 154),
    )
    reference = max(float(reference), 1.0)
    ratio = max(0.0, min(float(attendance) / reference, 1.0))
    scaled = ratio * (len(anchors) - 1)
    index = min(int(scaled), len(anchors) - 2)
    fraction = scaled - index
    start = anchors[index]
    end = anchors[index + 1]
    red, green, blue = (
        round(start[channel] + (end[channel] - start[channel]) * fraction)
        for channel in range(3)
    )
    return f"#{red:02x}{green:02x}{blue:02x}"


def attendance_peak_is_distinct(values, value):
    """Vrai lorsque la valeur est un maximum qui ressort des autres barres."""
    positive_values = [float(item) for item in values if float(item) > 0]
    if not positive_values:
        return False
    maximum = max(positive_values)
    return float(value) == maximum and any(item < maximum for item in positive_values)


def attendance_graph_color(value, values):
    """Conserve l'échelle froide et réserve le framboise au pic distinctif."""
    if attendance_peak_is_distinct(values, value):
        return ATTENDANCE_PEAK_COLOR
    return attendance_heat_color(value)


def attendance_display_count(value, show_decimals=False):
    """Arrondit seulement le libellé des pics, sans modifier leurs calculs."""
    decimal_value = Decimal(str(value))
    if show_decimals:
        return float(decimal_value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    return int(decimal_value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build_single_day_attendance_bars(
    local_day,
    session_intervals,
    visitor_times,
    start_minutes,
    end_minutes,
    show_decimals=False,
):
    """Construit le profil d'une journée avec la convention des pics existants."""
    local_day_start = datetime(
        local_day.year,
        local_day.month,
        local_day.day,
        tzinfo=PARIS_TIMEZONE,
    )
    bars = []
    for bucket_start_minutes in range(start_minutes, end_minutes, 15):
        bucket_end_minutes = min(bucket_start_minutes + 15, end_minutes)
        bucket_start = local_day_start + timedelta(minutes=bucket_start_minutes)
        bucket_end = local_day_start + timedelta(minutes=bucket_end_minutes)
        occupied_seconds = 0.0
        for session_start, session_end in session_intervals:
            local_session_start = session_start.astimezone(PARIS_TIMEZONE)
            local_session_end = session_end.astimezone(PARIS_TIMEZONE)
            overlap_start = max(local_session_start, bucket_start)
            overlap_end = min(local_session_end, bucket_end)
            if overlap_end > overlap_start:
                occupied_seconds += (overlap_end - overlap_start).total_seconds()
        visitor_arrivals = sum(
            1
            for created_at in visitor_times
            if bucket_start <= created_at.astimezone(PARIS_TIMEZONE) < bucket_end
        )
        bucket_seconds = (bucket_end_minutes - bucket_start_minutes) * 60
        users = round(occupied_seconds / bucket_seconds, 1) if bucket_seconds else 0.0
        visitors = float(visitor_arrivals)
        people = round(users + visitors, 1)
        start_hour, start_minute = divmod(bucket_start_minutes, 60)
        end_hour, end_minute = divmod(bucket_end_minutes, 60)
        bars.append(
            {
                "start": f"{start_hour:02d}:{start_minute:02d}",
                "end": f"{end_hour:02d}:{end_minute:02d}",
                "label": (
                    f"{start_hour}h"
                    if start_minute == 0
                    else f"{start_hour}h{start_minute:02d}"
                ),
                "average_users": users,
                "average_visitors": visitors,
                "average_people": people,
            }
        )

    user_values = [bar["average_users"] for bar in bars]
    combined_values = [bar["average_people"] for bar in bars]
    user_peak_value = max(user_values, default=0)
    combined_peak_value = max(combined_values, default=0)
    for bar in bars:
        user_ratio = bar["average_users"] / user_peak_value if user_peak_value else 0
        combined_ratio = (
            bar["average_people"] / combined_peak_value
            if combined_peak_value
            else 0
        )
        bar["display_average_users"] = attendance_display_count(
            bar["average_users"], show_decimals
        )
        bar["display_average_visitors"] = attendance_display_count(
            bar["average_visitors"], show_decimals
        )
        bar["display_average_people"] = attendance_display_count(
            bar["average_people"], show_decimals
        )
        bar["daily_height_percentage"] = round(user_ratio * 100, 1)
        bar["weekly_height_percentage"] = bar["daily_height_percentage"]
        bar["daily_color"] = attendance_graph_color(
            bar["average_users"], user_values
        )
        bar["weekly_color"] = bar["daily_color"]
        bar["combined_daily_height_percentage"] = round(combined_ratio * 100, 1)
        bar["combined_weekly_height_percentage"] = bar[
            "combined_daily_height_percentage"
        ]
        bar["combined_daily_color"] = attendance_graph_color(
            bar["average_people"], combined_values
        )
        bar["combined_weekly_color"] = bar["combined_daily_color"]
        bar["is_daily_peak"] = attendance_peak_is_distinct(
            user_values, bar["average_users"]
        )
        bar["is_weekly_peak"] = bar["is_daily_peak"]
        bar["is_combined_daily_peak"] = attendance_peak_is_distinct(
            combined_values, bar["average_people"]
        )
        bar["is_combined_weekly_peak"] = bar["is_combined_daily_peak"]

    peak = max(bars, key=lambda bar: bar["average_users"], default=None)
    combined_peak = max(bars, key=lambda bar: bar["average_people"], default=None)
    return {
        "bars": bars,
        "peak": peak if peak and peak["average_users"] > 0 else None,
        "combined_peak": (
            combined_peak
            if combined_peak and combined_peak["average_people"] > 0
            else None
        ),
    }


def build_day_attendance_graph(database, local_day, session_rows, visitor_rows):
    """Prépare le graphique journalier en conservant la convention des pics."""
    if not session_rows and not visitor_rows:
        return None

    day_start, day_end = local_day_utc_bounds(local_day)
    now_utc = datetime.now(timezone.utc)
    session_intervals = []
    range_starts = []
    range_ends = []
    for row in session_rows:
        session_start = max(parse_timestamp(row["check_in"]), day_start)
        natural_end = parse_timestamp(row["check_out"]) if row["check_out"] else now_utc
        session_end = min(max(natural_end, session_start), day_end)
        if session_end <= session_start:
            continue
        session_intervals.append((session_start, session_end))
        local_start = session_start.astimezone(PARIS_TIMEZONE)
        local_end = session_end.astimezone(PARIS_TIMEZONE)
        start_value = local_start.hour * 60 + local_start.minute
        end_value = local_end.hour * 60 + local_end.minute
        if local_end.second or local_end.microsecond:
            end_value += 1
        range_starts.append((start_value // 15) * 15)
        range_ends.append(min(1440, ((end_value + 14) // 15) * 15))

    visitor_times = [parse_timestamp(row["created_at"]) for row in visitor_rows]
    for created_at in visitor_times:
        local_created_at = created_at.astimezone(PARIS_TIMEZONE)
        visitor_start = (local_created_at.hour * 60 + local_created_at.minute) // 15 * 15
        range_starts.append(visitor_start)
        range_ends.append(min(1440, visitor_start + 15))

    schedule_day = load_openlab_schedule(database)[local_day.weekday()]
    if schedule_day["active"]:
        range_starts.append(schedule_day["start_minutes"])
        range_ends.append(schedule_day["end_minutes"])
    if not range_starts or not range_ends:
        return None

    start_minutes = max(0, min(range_starts))
    end_minutes = min(1440, max(range_ends))
    if end_minutes <= start_minutes:
        end_minutes = min(1440, start_minutes + 15)
    show_decimals = (
        read_setting(database, "openlab_attendance_show_decimals", "0") == "1"
    )
    graph = build_single_day_attendance_bars(
        local_day,
        session_intervals,
        visitor_times,
        start_minutes,
        end_minutes,
        show_decimals,
    )
    start_hour, start_minute = divmod(start_minutes, 60)
    end_hour, end_minute = divmod(end_minutes, 60)
    graph.update(
        {
            "start": f"{start_hour:02d}:{start_minute:02d}",
            "end": f"{end_hour:02d}:{end_minute:02d}",
            "total_visitors": len(visitor_times),
        }
    )
    return graph


def load_service_statistics(database, selected_year):
    """Calcule les indicateurs des animations et services pour la période choisie."""
    rows = database.execute(
        """
        SELECT service_type, service_date, expected_participants,
               actual_participants, participants, amount_cents, duration_minutes
        FROM fablab_services ORDER BY service_date
        """
    ).fetchall()
    selected = (
        rows
        if selected_year == "total"
        else [row for row in rows if int(row["service_date"][:4]) == selected_year]
    )
    animations = [row for row in selected if row["service_type"] == "animation"]
    reservations = [row for row in selected if row["service_type"] == "reservation"]
    rentals = [row for row in selected if row["service_type"] == "rental"]
    return {
        "animations": len(animations),
        "animation_participants": sum(row["actual_participants"] or 0 for row in animations),
        "animation_duration_minutes": sum(row["duration_minutes"] or 0 for row in animations),
        "reservations": len(reservations),
        "reservation_participants": sum(row["participants"] or 0 for row in reservations),
        "reservation_duration_minutes": sum(row["duration_minutes"] or 0 for row in reservations),
        "rentals": len(rentals),
        "rental_duration_minutes": sum(row["duration_minutes"] or 0 for row in rentals),
        "revenue_cents": sum(row["amount_cents"] or 0 for row in reservations + rentals),
        "revenue": f"{sum(row['amount_cents'] or 0 for row in reservations + rentals) / 100:.2f}".replace(".", ","),
        "years": sorted({int(row["service_date"][:4]) for row in rows}, reverse=True),
    }


def load_statistics(database, selected_year):
    """Calcule les répartitions annuelles ou cumulées utiles au bilan du FabLab."""
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(PARIS_TIMEZONE)
    show_attendance_decimals = (
        read_setting(database, "openlab_attendance_show_decimals", "0") == "1"
    )
    is_total_period = selected_year == "total"
    age_reference_year = now_local.year if is_total_period else selected_year
    session_rows = database.execute(
        """
        SELECT sessions.id, sessions.user_id, sessions.check_in, sessions.check_out,
               sessions.entry_method, sessions.exit_method,
               sessions.statistical_user_key,
               COALESCE(users.public_id, '') AS public_id,
               COALESCE(users.first_name, 'Ancien') AS first_name,
               COALESCE(users.last_name, 'usager') AS last_name,
               sessions.statistical_category AS category,
               CASE WHEN users.id IS NOT NULL
                    THEN users.birth_year ELSE sessions.statistical_birth_year END AS birth_year,
               CASE WHEN users.id IS NOT NULL
                    THEN users.gender ELSE sessions.statistical_gender END AS gender,
               CASE WHEN users.id IS NOT NULL
                    THEN users.city ELSE sessions.statistical_city END AS city,
               CASE WHEN users.id IS NOT NULL
                    THEN users.city_normalized ELSE sessions.statistical_city_normalized END AS city_normalized,
               CASE WHEN users.id IS NOT NULL
                    THEN users.nationality ELSE sessions.statistical_nationality END AS nationality,
               CASE WHEN users.id IS NOT NULL
                    THEN users.nationality_normalized ELSE sessions.statistical_nationality_normalized END AS nationality_normalized
        FROM sessions
        LEFT JOIN users ON users.id = sessions.user_id
        ORDER BY sessions.check_in
        """
    ).fetchall()
    visitor_rows = database.execute(
        "SELECT id, created_at FROM visitors ORDER BY created_at"
    ).fetchall()

    parsed_sessions = []
    for row in session_rows:
        check_in = parse_timestamp(row["check_in"])
        check_out = parse_timestamp(row["check_out"]) if row["check_out"] else None
        local_check_in = check_in.astimezone(PARIS_TIMEZONE)
        parsed_sessions.append(
            {
                "row": row,
                "check_in": check_in,
                "check_out": check_out,
                "year": local_check_in.year,
                "local_date": local_check_in.date(),
                "weekday": local_check_in.weekday(),
                # Une session ouverte peut être un oubli de pointage. Son temps
                # ne rejoint le bilan qu'après l'enregistrement du départ.
                "duration_seconds": max(0, (check_out - check_in).total_seconds())
                if check_out
                else None,
            }
        )

    parsed_visitors = [
        {
            "row": row,
            "created_at": parse_timestamp(row["created_at"]),
            "year": local_year(row["created_at"]),
            "local_date": parse_timestamp(row["created_at"])
            .astimezone(PARIS_TIMEZONE)
            .date(),
        }
        for row in visitor_rows
    ]

    week_start = (now_local - timedelta(days=now_local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    year_start = now_local.replace(
        month=1, day=1, hour=0, minute=0, second=0, microsecond=0
    )

    def period_summary(label, start_local):
        start_utc = start_local.astimezone(timezone.utc)
        sessions = [item for item in parsed_sessions if item["check_in"] >= start_utc]
        visitors = [item for item in parsed_visitors if item["created_at"] >= start_utc]
        return {
            "label": label,
            "sessions": len(sessions),
            "visitors": len(visitors),
            "total": len(sessions) + len(visitors),
            "unique_users": len(
                {item["row"]["statistical_user_key"] for item in sessions}
            ),
        }

    current_periods = [
        period_summary("Cette semaine", week_start),
        period_summary("Ce mois", month_start),
        period_summary("Cette année", year_start),
    ]

    selected_sessions = (
        parsed_sessions
        if is_total_period
        else [item for item in parsed_sessions if item["year"] == selected_year]
    )
    selected_visitors = (
        parsed_visitors
        if is_total_period
        else [item for item in parsed_visitors if item["year"] == selected_year]
    )
    visited_users = {}
    for item in selected_sessions:
        visited_users[item["row"]["statistical_user_key"]] = item["row"]

    total_duration_seconds = sum(
        item["duration_seconds"] or 0 for item in selected_sessions
    )
    completed_durations = [
        item["duration_seconds"]
        for item in selected_sessions
        if item["duration_seconds"] is not None
    ]
    selected_summary = {
        "year": selected_year,
        "sessions": len(selected_sessions),
        "visitors": len(selected_visitors),
        "total": len(selected_sessions) + len(selected_visitors),
        "unique_users": len(visited_users),
        "hours": hours_label(total_duration_seconds),
        "average_minutes": round(sum(completed_durations) / len(completed_durations) / 60)
        if completed_durations
        else 0,
    }

    genders = [user["gender"] for user in visited_users.values()]
    gender_rows = distribution_rows(
        genders,
        labels=GENDER_LABELS,
        order=["female", "male", "non_binary", None],
    )

    known_ages = [
        age_reference_year - user["birth_year"]
        for user in visited_users.values()
        if user["birth_year"]
    ]
    mean_age = round(sum(known_ages) / len(known_ages), 1) if known_ages else None
    age_groups = []
    for user in visited_users.values():
        if not user["birth_year"]:
            age_groups.append("unknown")
            continue
        age = age_reference_year - user["birth_year"]
        if age < 18:
            age_groups.append("under_18")
        elif age <= 25:
            age_groups.append("18_25")
        elif age <= 40:
            age_groups.append("26_40")
        elif age <= 60:
            age_groups.append("41_60")
        else:
            age_groups.append("61_plus")
    age_labels = {
        "under_18": "Moins de 18 ans",
        "18_25": "18 à 25 ans",
        "26_40": "26 à 40 ans",
        "41_60": "41 à 60 ans",
        "61_plus": "61 ans et plus",
        "unknown": "Inconnu",
    }
    age_rows = distribution_rows(
        age_groups,
        labels=age_labels,
        order=["under_18", "18_25", "26_40", "41_60", "61_plus", "unknown"],
    )

    def grouped_user_distribution(key_field, label_field, unknown_label):
        keys = []
        variants = defaultdict(list)
        for user in visited_users.values():
            key = user[key_field] or "unknown"
            keys.append(key)
            variants[key].append(user[label_field])
        labels = {
            key: preferred_group_label(values, unknown_label)
            for key, values in variants.items()
        }
        if key_field == "nationality_normalized":
            labels = {
                key: country_name_from_key(key) or label
                for key, label in labels.items()
            }
        return (
            distribution_rows(keys, labels=labels, unknown_label=unknown_label),
            labels,
        )

    city_rows, city_labels = grouped_user_distribution(
        "city_normalized", "city", "Commune inconnue"
    )
    nationality_rows, nationality_labels = grouped_user_distribution(
        "nationality_normalized", "nationality", "Nationalité inconnue"
    )
    city_export_rows = city_rows
    nationality_export_rows = nationality_rows
    city_rows, visible_city_keys = limited_distribution_rows(city_rows)
    nationality_rows, visible_nationality_keys = limited_distribution_rows(
        nationality_rows
    )

    demographic_users = []
    for user in visited_users.values():
        age = age_reference_year - user["birth_year"] if user["birth_year"] else None
        if age is None:
            age_group = "unknown"
        elif age < 18:
            age_group = "under_18"
        elif age <= 25:
            age_group = "18_25"
        elif age <= 40:
            age_group = "26_40"
        elif age <= 60:
            age_group = "41_60"
        else:
            age_group = "61_plus"
        city_key = user["city_normalized"] or "unknown"
        nationality_key = user["nationality_normalized"] or "unknown"
        displayed_city_key = (
            city_key if city_key in visible_city_keys else "__other__"
        )
        displayed_nationality_key = (
            nationality_key
            if nationality_key in visible_nationality_keys
            else "__other__"
        )
        demographic_users.append(
            {
                "gender": user["gender"] or "unknown",
                "age_group": age_group,
                "age": age,
                "city": displayed_city_key,
                "city_label": (
                    city_labels.get(city_key, "Commune inconnue")
                    if displayed_city_key != "__other__"
                    else "Autres"
                ),
                "nationality": displayed_nationality_key,
                "nationality_label": (
                    nationality_labels.get(nationality_key, "Nationalité inconnue")
                    if displayed_nationality_key != "__other__"
                    else "Autres"
                ),
            }
        )

    visited_categories = [user["category"] for user in visited_users.values()]
    category_labels = {row['category_key']:row['name'] for row in categories(database, True)}
    category_rows = distribution_rows(
        visited_categories,
        labels=category_labels,
        order=list(category_labels),
    )
    category_session_counts = Counter(
        item["row"]["category"] for item in selected_sessions
    )
    category_duration_seconds = defaultdict(float)
    category_completed_durations = defaultdict(list)
    for item in selected_sessions:
        category_duration_seconds[item["row"]["category"]] += (
            item["duration_seconds"] or 0
        )
        if item["duration_seconds"] is not None:
            category_completed_durations[item["row"]["category"]].append(
                item["duration_seconds"]
            )
    for row in category_rows:
        row["sessions"] = category_session_counts[row["key"]]
        row["hours"] = hours_label(category_duration_seconds[row["key"]])
        completed = category_completed_durations[row["key"]]
        row["average_minutes"] = (
            round(sum(completed) / len(completed) / 60) if completed else None
        )

    daily_attendance = defaultdict(lambda: {"users": set(), "visitors": 0})
    for item in selected_sessions:
        daily_attendance[item["local_date"]]["users"].add(
            item["row"]["statistical_user_key"]
        )
    for item in selected_visitors:
        daily_attendance[item["local_date"]]["visitors"] += 1

    weekday_attendance = defaultdict(
        lambda: {"open_labs": 0, "users": 0, "visitors": 0}
    )
    for local_date, attendance in daily_attendance.items():
        if not attendance["users"]:
            continue
        weekday = local_date.weekday()
        weekday_attendance[weekday]["open_labs"] += 1
        weekday_attendance[weekday]["users"] += len(attendance["users"])
        weekday_attendance[weekday]["visitors"] += attendance["visitors"]

    weekday_labels = [label for _key, label in WEEKDAYS]
    busiest_weekdays = []
    for weekday, attendance in weekday_attendance.items():
        open_labs = attendance["open_labs"]
        busiest_weekdays.append(
            {
                "weekday": weekday,
                "label": weekday_labels[weekday],
                "open_labs": open_labs,
                "average_users": round(attendance["users"] / open_labs, 1),
                "average_visitors": round(attendance["visitors"] / open_labs, 1),
                "total_users": attendance["users"],
            }
        )
    busiest_weekdays.sort(
        key=lambda row: (
            -row["average_users"],
            -row["total_users"],
            -row["average_visitors"],
            row["weekday"],
        )
    )
    busiest_weekdays = busiest_weekdays[:4]
    selected_summary["open_lab_days"] = sum(
        1 for attendance in daily_attendance.values() if attendance["users"]
    )

    attendance_schedule = load_openlab_schedule(database)
    sessions_by_date = defaultdict(list)
    for item in selected_sessions:
        if item["check_out"] is not None:
            sessions_by_date[item["local_date"]].append(item)
    visitors_by_date = defaultdict(list)
    for item in selected_visitors:
        visitors_by_date[item["local_date"]].append(item["created_at"])

    hourly_attendance_days = []
    for schedule_day in attendance_schedule:
        if not schedule_day["active"]:
            continue
        weekday = schedule_day["weekday"]
        open_lab_dates = [
            local_date
            for local_date, attendance in daily_attendance.items()
            if attendance["users"] and local_date.weekday() == weekday
        ]
        bars = []
        for bucket_start_minutes in range(
            schedule_day["start_minutes"],
            schedule_day["end_minutes"],
            15,
        ):
            bucket_end_minutes = min(
                bucket_start_minutes + 15,
                schedule_day["end_minutes"],
            )
            occupied_seconds = 0.0
            visitor_arrivals = 0
            for local_date in open_lab_dates:
                local_day_start = datetime(
                    local_date.year,
                    local_date.month,
                    local_date.day,
                    tzinfo=PARIS_TIMEZONE,
                )
                bucket_start = local_day_start + timedelta(
                    minutes=bucket_start_minutes
                )
                bucket_end = local_day_start + timedelta(minutes=bucket_end_minutes)
                for item in sessions_by_date[local_date]:
                    session_start = item["check_in"].astimezone(PARIS_TIMEZONE)
                    session_end = item["check_out"].astimezone(PARIS_TIMEZONE)
                    overlap_start = max(session_start, bucket_start)
                    overlap_end = min(session_end, bucket_end)
                    if overlap_end > overlap_start:
                        occupied_seconds += (
                            overlap_end - overlap_start
                        ).total_seconds()
                visitor_arrivals += sum(
                    1
                    for created_at in visitors_by_date[local_date]
                    if bucket_start
                    <= created_at.astimezone(PARIS_TIMEZONE)
                    < bucket_end
                )

            bucket_seconds = (bucket_end_minutes - bucket_start_minutes) * 60
            average_users = (
                round(occupied_seconds / (bucket_seconds * len(open_lab_dates)), 1)
                if open_lab_dates and bucket_seconds
                else 0.0
            )
            average_visitors = (
                round(visitor_arrivals / len(open_lab_dates), 1)
                if open_lab_dates
                else 0.0
            )
            average_people = round(average_users + average_visitors, 1)
            start_hour, start_minute = divmod(bucket_start_minutes, 60)
            end_hour, end_minute = divmod(bucket_end_minutes, 60)
            bars.append(
                {
                    "start": f"{start_hour:02d}:{start_minute:02d}",
                    "end": f"{end_hour:02d}:{end_minute:02d}",
                    "label": (
                        f"{start_hour}h"
                        if start_minute == 0
                        else f"{start_hour}h{start_minute:02d}"
                    ),
                    "average_users": average_users,
                    "average_visitors": average_visitors,
                    "average_people": average_people,
                }
            )
        peak = max(bars, key=lambda bar: bar["average_users"], default=None)
        combined_peak = max(
            bars, key=lambda bar: bar["average_people"], default=None
        )
        average_visitors = (
            round(
                sum(
                    daily_attendance[local_date]["visitors"]
                    for local_date in open_lab_dates
                )
                / len(open_lab_dates),
                1,
            )
            if open_lab_dates
            else 0.0
        )
        hourly_attendance_days.append(
            {
                "weekday": weekday,
                "label": schedule_day["label"],
                "start": schedule_day["start"],
                "end": schedule_day["end"],
                "open_labs": len(open_lab_dates),
                "average_visitors": average_visitors,
                "display_average_visitors": attendance_display_count(
                    average_visitors, show_attendance_decimals
                ),
                "bars": bars,
                "peak": peak if peak and peak["average_users"] > 0 else None,
                "combined_peak": (
                    combined_peak
                    if combined_peak and combined_peak["average_people"] > 0
                    else None
                ),
            }
        )

    weekly_user_values = [
        bar["average_users"]
        for day in hourly_attendance_days
        for bar in day["bars"]
    ]
    weekly_combined_values = [
        bar["average_people"]
        for day in hourly_attendance_days
        for bar in day["bars"]
    ]
    weekly_attendance_peak = max(weekly_user_values, default=0)
    weekly_combined_peak = max(weekly_combined_values, default=0)
    for day in hourly_attendance_days:
        daily_user_values = [bar["average_users"] for bar in day["bars"]]
        daily_combined_values = [bar["average_people"] for bar in day["bars"]]
        daily_attendance_peak = max(daily_user_values, default=0)
        daily_combined_peak = max(daily_combined_values, default=0)
        for bar in day["bars"]:
            bar["display_average_users"] = attendance_display_count(
                bar["average_users"], show_attendance_decimals
            )
            bar["display_average_visitors"] = attendance_display_count(
                bar["average_visitors"], show_attendance_decimals
            )
            bar["display_average_people"] = attendance_display_count(
                bar["average_people"], show_attendance_decimals
            )
            daily_ratio = (
                bar["average_users"] / daily_attendance_peak
                if daily_attendance_peak
                else 0
            )
            weekly_ratio = (
                bar["average_users"] / weekly_attendance_peak
                if weekly_attendance_peak
                else 0
            )
            combined_daily_ratio = (
                bar["average_people"] / daily_combined_peak
                if daily_combined_peak
                else 0
            )
            combined_weekly_ratio = (
                bar["average_people"] / weekly_combined_peak
                if weekly_combined_peak
                else 0
            )
            bar["daily_height_percentage"] = round(daily_ratio * 100, 1)
            bar["weekly_height_percentage"] = round(weekly_ratio * 100, 1)
            bar["daily_color"] = attendance_graph_color(
                bar["average_users"], daily_user_values
            )
            bar["weekly_color"] = attendance_graph_color(
                bar["average_users"], weekly_user_values
            )
            bar["combined_daily_height_percentage"] = round(
                combined_daily_ratio * 100, 1
            )
            bar["combined_weekly_height_percentage"] = round(
                combined_weekly_ratio * 100, 1
            )
            bar["combined_daily_color"] = attendance_graph_color(
                bar["average_people"], daily_combined_values
            )
            bar["combined_weekly_color"] = attendance_graph_color(
                bar["average_people"], weekly_combined_values
            )
            bar["is_daily_peak"] = attendance_peak_is_distinct(
                daily_user_values, bar["average_users"]
            )
            bar["is_weekly_peak"] = attendance_peak_is_distinct(
                weekly_user_values, bar["average_users"]
            )
            bar["is_combined_daily_peak"] = attendance_peak_is_distinct(
                daily_combined_values, bar["average_people"]
            )
            bar["is_combined_weekly_peak"] = attendance_peak_is_distinct(
                weekly_combined_values, bar["average_people"]
            )

    # Conserve le profil réel de chaque OpenLab afin d'identifier la journée
    # ayant atteint le plus haut pic. Le record peut changer lorsque les
    # arrivées de visiteurs sont incluses dans le graphique.
    schedule_by_weekday = {
        day["weekday"]: day for day in attendance_schedule if day["active"]
    }
    record_candidates = []
    for local_date, attendance in daily_attendance.items():
        schedule_day = schedule_by_weekday.get(local_date.weekday())
        if not attendance["users"] or schedule_day is None:
            continue

        profile = build_single_day_attendance_bars(
            local_date,
            [
                (item["check_in"], item["check_out"])
                for item in sessions_by_date[local_date]
            ],
            visitors_by_date[local_date],
            schedule_day["start_minutes"],
            schedule_day["end_minutes"],
            show_attendance_decimals,
        )
        bars = profile["bars"]
        peak = profile["peak"]
        combined_peak = profile["combined_peak"]

        record_candidates.append(
            {
                "date": local_date.isoformat(),
                "date_ordinal": local_date.toordinal(),
                "date_label": (
                    f"{weekday_labels[local_date.weekday()]} {local_date.day} "
                    f"{FRENCH_MONTH_NAMES[local_date.month - 1]} {local_date.year}"
                ),
                "start": schedule_day["start"],
                "end": schedule_day["end"],
                "bars": bars,
                "peak": peak if peak and peak["average_users"] > 0 else None,
                "combined_peak": (
                    combined_peak
                    if combined_peak and combined_peak["average_people"] > 0
                    else None
                ),
                "total_visitors": attendance["visitors"],
                "user_load": round(sum(bar["average_users"] for bar in bars), 1),
                "combined_load": round(
                    sum(bar["average_people"] for bar in bars), 1
                ),
            }
        )

    user_record = max(
        (candidate for candidate in record_candidates if candidate["peak"]),
        key=lambda candidate: (
            candidate["peak"]["average_users"],
            candidate["user_load"],
            candidate["date_ordinal"],
        ),
        default=None,
    )
    combined_record = max(
        (
            candidate
            for candidate in record_candidates
            if candidate["combined_peak"]
        ),
        key=lambda candidate: (
            candidate["combined_peak"]["average_people"],
            candidate["combined_load"],
            candidate["date_ordinal"],
        ),
        default=None,
    )

    annual_data = defaultdict(
        lambda: {
            "sessions": 0,
            "visitors": 0,
            "unique_user_ids": set(),
            "duration_seconds": 0,
            "open_lab_dates": set(),
        }
    )
    annual_data[now_local.year]
    for item in parsed_sessions:
        year_data = annual_data[item["year"]]
        year_data["sessions"] += 1
        year_data["unique_user_ids"].add(item["row"]["statistical_user_key"])
        year_data["duration_seconds"] += item["duration_seconds"] or 0
        year_data["open_lab_dates"].add(item["local_date"])
    for item in parsed_visitors:
        annual_data[item["year"]]["visitors"] += 1

    history = []
    for year in sorted(annual_data, reverse=True):
        data = annual_data[year]
        history.append(
            {
                "year": year,
                "sessions": data["sessions"],
                "visitors": data["visitors"],
                "total": data["sessions"] + data["visitors"],
                "unique_users": len(data["unique_user_ids"]),
                "hours": hours_label(data["duration_seconds"]),
                "open_lab_days": len(data["open_lab_dates"]),
            }
        )

    service_statistics = load_service_statistics(database, selected_year)
    available_years = sorted(
        set(row["year"] for row in history) | set(service_statistics["years"]),
        reverse=True,
    )
    return {
        "selected_year": selected_year,
        "is_total_period": is_total_period,
        "selected_period_label": (
            "Toutes les années" if is_total_period else str(selected_year)
        ),
        "available_years": available_years,
        "current_periods": current_periods,
        "selected_summary": selected_summary,
        "gender_rows": gender_rows,
        "age_rows": age_rows,
        "mean_age": mean_age,
        "city_rows": city_rows,
        "nationality_rows": nationality_rows,
        "city_export_rows": city_export_rows,
        "nationality_export_rows": nationality_export_rows,
        "demographic_users": demographic_users,
        "category_rows": category_rows,
        "busiest_weekdays": busiest_weekdays,
        "openlab_attendance": {
            "days": hourly_attendance_days,
            "record": {
                "users": user_record,
                "combined": combined_record,
            },
        },
        "history": history,
        "selected_sessions": selected_sessions,
        "service_statistics": service_statistics,
    }


def csv_download(filename, headers, rows):
    """Crée un fichier CSV UTF-8 avec séparateur adapté à Excel en français."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerows(rows)
    content = "\ufeff" + output.getvalue()
    return Response(
        content,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def qr_code_response(public_id, image_format, download=False):
    """Génère à la demande le QR d'un identifiant, en SVG ou en PNG."""
    if image_format not in {"svg", "png"}:
        abort(404)

    output = io.BytesIO()
    qr_code = segno.make_qr(public_id, error="h")
    save_options = {
        "kind": image_format,
        "border": 4,
        "dark": "#000000",
        "light": "#ffffff",
    }
    if image_format == "svg":
        save_options.update({"scale": 10, "xmldecl": True})
        mimetype = "image/svg+xml"
    else:
        # Le PNG est volontairement grand et déclaré à 300 dpi pour l'impression.
        save_options.update({"scale": 24, "dpi": 300})
        mimetype = "image/png"

    qr_code.save(output, **save_options)
    brand_slug = safe_filename_part(read_setting(get_database(), "structure_short_name", "OpenFabLab"))
    filename = f"{brand_slug}-identifiant-{public_id}.{image_format}"
    disposition = "attachment" if download else "inline"
    return Response(
        output.getvalue(),
        mimetype=mimetype,
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def read_setting(database, key, default=""):
    """Lit un réglage persistant de l'application."""
    row = database.execute(
        "SELECT value FROM app_settings WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else default


def load_structure_settings(database):
    settings = {key: read_setting(database, f"structure_{key}") for key in STRUCTURE_FIELDS}
    settings["main_logo"] = read_setting(database, "structure_main_logo")
    settings["wordmark_logo"] = read_setting(database, "structure_wordmark_logo")
    settings["institution_logo"] = read_setting(database, "structure_institution_logo")
    settings["signature"] = read_setting(database, "structure_signature")
    settings['header_institution_logo'] = read_setting(database, 'structure_header_institution_logo')
    settings['network_logo'] = read_setting(database, 'structure_network_logo')
    settings['badge_template'] = read_setting(database, 'structure_badge_template')
    for key in VISIBILITY_KEYS + RESOURCE_USAGE_KEYS:
        settings[key] = read_setting(database, 'structure_' + key, '1') == '1'
    settings['logo_status'] = logo_status(Path(current_database_path()).parent, settings)
    return settings


def document_brand_assets(database):
    """Use only the installation-owned persistent images; never bundled institutional assets."""
    structure = load_structure_settings(database)
    branding = Path(current_database_path()).parent / "branding"
    institution = branding / "institution.png" if structure["institution_logo"] == "institution.png" else None
    main = branding / "main.png" if structure["main_logo"] == "main.png" and structure['use_main_logo'] else None
    signature = branding / "signature.png" if structure["signature"] == "signature.png" and structure['use_signature'] else None
    return structure, institution, main, signature


def load_modules(database):
    return {key: read_setting(database, f"module_{key}", "1") == "1"
            for key in MODULE_LABELS}


def write_setting(database, key, value):
    """Crée ou met à jour un réglage persistant."""
    database.execute(
        """
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, str(value)),
    )


def load_id_security_settings(database):
    """Paramètres bornés de la seule identification manuelle par ID."""
    def number(key, default, minimum, maximum):
        try:
            value = int(read_setting(database, key, str(default)))
            return value if minimum <= value <= maximum else default
        except ValueError:
            return default

    return {
        "threshold": number("invalid_id_threshold", 5, 2, 50),
        "window_minutes": number("invalid_id_window_minutes", 5, 1, 60),
        "lock_enabled": read_setting(database, "invalid_id_lock_enabled", "0") == "1",
        "lock_minutes": number("invalid_id_lock_minutes", 10, 1, 120),
    }


def purge_security_events(database, now=None):
    """Conserve trente jours de journal technique, sans toucher aux données métier."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=30)).isoformat(timespec="seconds")
    database.execute("DELETE FROM security_events WHERE created_at < ?", (cutoff,))


def log_security_event(database, event_type, details=None, now=None):
    """N'accepte que les types et métadonnées techniques explicitement prévus."""
    allowed = {
        "invalid_user_id": {"sequence_start"},
        "invalid_id_alert": {"sequence_start", "count"},
        "invalid_id_discord_queued": {"sequence_start"},
        "id_lock_started": {"until"},
        "admin_login_success": set(),
        "moderator_login_success": set(),
        "admin_login_failed": set(),
        "moderator_login_failed": set(),
        "admin_pin_changed": set(),
        "admin_recovery_requested": set(),
        "admin_recovery_success": set(),
        "admin_recovery_expired": set(),
    }
    if event_type not in allowed or set(details or {}) - allowed[event_type]:
        raise ValueError("Événement de sécurité non autorisé")
    now = now or datetime.now(timezone.utc)
    purge_security_events(database, now)
    database.execute(
        "INSERT INTO security_events (event_type, created_at, details_json) VALUES (?, ?, ?)",
        (event_type, now.isoformat(timespec="seconds"), json.dumps(details or {}, ensure_ascii=False)),
    )


def current_id_lock(database, now=None):
    """Renvoie la fin d'un blocage encore actif, sans modifier la durée."""
    settings = load_id_security_settings(database)
    if not settings["lock_enabled"]:
        return None
    row = database.execute(
        "SELECT details_json FROM security_events WHERE event_type = 'id_lock_started' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    until = parse_timestamp(json.loads(row["details_json"])["until"])
    return until if until > (now or datetime.now(timezone.utc)) else None


def security_status(database, now=None):
    now = now or datetime.now(timezone.utc)
    settings = load_id_security_settings(database)
    since = (now - timedelta(minutes=settings["window_minutes"])).isoformat(timespec="seconds")
    count = database.execute(
        "SELECT COUNT(*) FROM security_events WHERE event_type = 'invalid_user_id' AND created_at >= ?",
        (since,),
    ).fetchone()[0]
    last_alert = database.execute(
        "SELECT created_at FROM security_events WHERE event_type = 'invalid_id_discord_queued' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    lock_until = current_id_lock(database, now)
    return {"count": count, "lock_until": lock_until.astimezone(PARIS_TIMEZONE) if lock_until else None,
            "last_alert": parse_timestamp(last_alert["created_at"]).astimezone(PARIS_TIMEZONE) if last_alert else None}


def queue_invalid_id_alert(database, settings, sequence_start, now):
    """Alerte technique sans code, IP, nom ni coordonnée ; au plus une par séquence."""
    discord = load_discord_settings(database)
    webhook = read_discord_webhook()
    if not (discord["enabled"] and discord["invalid_ids"] and webhook):
        return False
    message = (
        f"⚠️ OpenFabLab : {settings['threshold']} tentatives d’identifiant usager "
        f"invalides ont été détectées en moins de {settings['window_minutes']} minutes sur la borne."
    )
    log_security_event(database, "invalid_id_discord_queued", {"sequence_start": sequence_start}, now)
    application = current_app._get_current_object()

    def worker():
        try:
            with application.app_context():
                post_discord_message(webhook, message, discord["bot_name"])
        except (OSError, urllib.error.URLError, ValueError):
            application.logger.warning("Alerte de sécurité Discord indisponible")

    if application.config.get("DISCORD_SYNCHRONOUS"):
        worker()
    else:
        threading.Thread(target=worker, name="openfablab-security-discord", daemon=True).start()
    return True


def record_invalid_user_id(database, now=None):
    """Compte les seuls IDs complets invalides sur une fenêtre glissante."""
    now = now or datetime.now(timezone.utc)
    settings = load_id_security_settings(database)
    window = timedelta(minutes=settings["window_minutes"])
    previous = database.execute(
        "SELECT created_at, details_json FROM security_events WHERE event_type = 'invalid_user_id' "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if previous and now - parse_timestamp(previous["created_at"]) <= window:
        sequence_start = json.loads(previous["details_json"])["sequence_start"]
    else:
        sequence_start = now.isoformat(timespec="seconds")
    log_security_event(database, "invalid_user_id", {"sequence_start": sequence_start}, now)
    since = (now - window).isoformat(timespec="seconds")
    count = database.execute(
        "SELECT COUNT(*) FROM security_events WHERE event_type = 'invalid_user_id' AND created_at >= ?",
        (since,),
    ).fetchone()[0]
    if count >= settings["threshold"]:
        previous_alerts = database.execute(
            "SELECT details_json FROM security_events WHERE event_type = 'invalid_id_alert' "
            "AND created_at >= ?", (sequence_start,)
        ).fetchall()
        if not any(json.loads(row["details_json"])["sequence_start"] == sequence_start for row in previous_alerts):
            log_security_event(database, "invalid_id_alert", {"sequence_start": sequence_start, "count": count}, now)
            if settings["lock_enabled"]:
                until = (now + timedelta(minutes=settings["lock_minutes"])).isoformat(timespec="seconds")
                log_security_event(database, "id_lock_started", {"until": until}, now)
            queue_invalid_id_alert(database, settings, sequence_start, now)
    database.commit()
    return count


def home_state_signature(database):
    """Produit une empreinte anonyme de l'état public de la borne."""
    sessions = database.execute(
        """
        SELECT COALESCE(SUM(CASE WHEN check_out IS NULL THEN 1 ELSE 0 END), 0)
                   AS open_count,
               COALESCE(MAX(id), 0) AS last_id,
               COALESCE(MAX(check_in), '') AS last_check_in,
               COALESCE(MAX(check_out), '') AS last_check_out
        FROM sessions
        """
    ).fetchone()
    day_start, day_end = today_utc_bounds()
    visitors = database.execute(
        """
        SELECT COUNT(*) AS day_count, COALESCE(MAX(id), 0) AS last_id
        FROM visitors WHERE created_at >= ? AND created_at < ?
        """,
        (day_start, day_end),
    ).fetchone()
    return "|".join(
        str(value)
        for value in (
            sessions["open_count"], sessions["last_id"],
            sessions["last_check_in"], sessions["last_check_out"],
            visitors["day_count"], visitors["last_id"],
            load_home_theme(database),
        )
    )


def load_wake_lock_settings(database):
    """Retourne l'activation et la plage quotidienne de la borne."""
    start = read_setting(database, "wake_lock_start", "09:00")
    end = read_setting(database, "wake_lock_end", "17:00")
    if not TIME_PATTERN.fullmatch(start or ""):
        start = "09:00"
    if not TIME_PATTERN.fullmatch(end or ""):
        end = "17:00"
    return {
        "enabled": read_setting(database, "keep_screen_awake", "0") == "1",
        "start": start,
        "end": end,
    }


def home_scroll_lock_enabled(database):
    """Indique si l'accueil doit rester fixe sur la borne en paysage."""
    return read_setting(database, "lock_home_scroll", "1") == "1"


def load_home_theme(database):
    """Retourne un thème d’accueil connu, avec repli sûr sur le classique."""
    theme = read_setting(database, "home_theme", "classic")
    return theme if theme in HOME_THEMES else "classic"


def discord_webhook_path():
    """Retourne le fichier privé qui n'est jamais inclus dans SQLite."""
    return Path(current_app.config["DISCORD_WEBHOOK_FILE"])


def read_discord_webhook():
    """Lit l'URL privée sans jamais la placer dans un rendu ou un journal."""
    path = discord_webhook_path()
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return value if re.fullmatch(
        r"https://(?:canary\.|ptb\.)?discord\.com/api/webhooks/\d+/[A-Za-z0-9._-]+",
        value,
    ) else ""


def write_discord_webhook(value):
    """Écrit atomiquement le secret Discord avec des permissions restreintes."""
    value = (value or "").strip()
    if not re.fullmatch(
        r"https://(?:canary\.|ptb\.)?discord\.com/api/webhooks/\d+/[A-Za-z0-9._-]+",
        value,
    ):
        raise ValueError("L'adresse du webhook Discord n'est pas valide.")
    path = discord_webhook_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        temporary_path.write_text(value, encoding="utf-8")
        try:
            temporary_path.chmod(0o600)
        except OSError:
            pass
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def clear_discord_webhook():
    """Retire le secret configuré sans toucher aux autres options."""
    discord_webhook_path().unlink(missing_ok=True)


def load_discord_settings(database):
    """Retourne uniquement l'état public de la configuration Discord."""
    settings = {
        "enabled": read_setting(database, "discord_notifications_enabled", "0") == "1",
        "configured": bool(read_discord_webhook()),
        "arrivals": read_setting(database, "discord_notify_arrivals", "1") == "1",
        "departures": read_setting(database, "discord_notify_departures", "1") == "1",
        "visitors": read_setting(database, "discord_notify_visitors", "1") == "1",
        "retention": read_setting(database, "discord_notify_retention", "1") == "1",
        "invoice_overdue": read_setting(
            database, "discord_notify_invoice_overdue", "1"
        ) == "1",
        "monthly_animations": read_setting(
            database, "discord_notify_monthly_animations", "1"
        ) == "1",
        "invalid_ids": read_setting(database, "discord_notify_invalid_ids", "1") == "1",
        "bot_name": read_setting(
            database, "discord_bot_name", DISCORD_DEFAULTS["bot_name"]
        ),
        "arrival_message": read_setting(
            database,
            "discord_message_arrival",
            DISCORD_DEFAULTS["arrival_message"],
        ),
        "departure_message": read_setting(
            database,
            "discord_message_departure",
            DISCORD_DEFAULTS["departure_message"],
        ),
        "visitor_message": read_setting(
            database,
            "discord_message_visitor",
            DISCORD_DEFAULTS["visitor_message"],
        ),
        "retention_message": read_setting(
            database,
            "discord_message_retention",
            DISCORD_DEFAULTS["retention_message"],
        ),
        "invoice_overdue_message": read_setting(
            database,
            "discord_message_invoice_overdue",
            DISCORD_DEFAULTS["invoice_overdue_message"],
        ),
        "monthly_animations_message": read_setting(
            database,
            "discord_message_monthly_animations",
            DISCORD_DEFAULTS["monthly_animations_message"],
        ),
    }
    settings["reservations"] = {
        name: read_setting(database, f"discord_reservation_{name}", "1") == "1"
        for name in RESERVATION_DISCORD_FLAGS
    }
    return settings


def notify_reservation_discord(database, event_type, service_id=None):
    """Send only aggregate booking information; never include contact details."""
    if not load_modules(database)["discord"]:
        return False
    option = RESERVATION_DISCORD_OPTIONS.get(event_type)
    if event_type in {"link_review", "animation_full", "sync_error"}:
        option = (event_type, {
            "link_review": "Rattachement à vérifier",
            "animation_full": "Animation complète",
            "sync_error": "Synchronisation WordPress momentanément indisponible",
        }[event_type])
    if option is None:
        return False
    flag, label = option
    settings = load_discord_settings(database)
    webhook = read_discord_webhook()
    if not (settings["enabled"] and settings["reservations"][flag] and webhook):
        return False
    message = label
    if service_id is not None:
        row = database.execute(
            "SELECT s.title, c.capacity, "
            "(SELECT COUNT(*) FROM animation_bookings b WHERE b.service_id = s.id "
            "AND b.status IN ('confirmed', 'offer_pending', 'present', 'absent')) AS occupied "
            "FROM fablab_services s LEFT JOIN animation_reservation_config c "
            "ON c.service_id = s.id WHERE s.id = ?", (service_id,),
        ).fetchone()
        if row:
            title = re.sub(r"[\r\n@]", " ", row["title"] or "Animation")[:100]
            message += f" - {title}"
            if row["capacity"] is not None:
                message += f" · {row['occupied']}/{row['capacity']} places"
    return send_discord_plain(webhook, message, settings["bot_name"])


def send_discord_plain(webhook_url, message, bot_name):
    """Use the existing webhook transport; tests can replace this boundary."""
    try:
        post_discord_message(webhook_url, message, bot_name)
        return True
    except (OSError, urllib.error.URLError, ValueError):
        current_app.logger.warning("Notification de réservation Discord indisponible")
        return False


def validate_discord_text(value, label, maximum, default=None):
    """Valide un libellé Discord sans interpréter de code ou de mentions."""
    cleaned = (value or "").strip()
    if not cleaned and default is not None:
        cleaned = default
    if not cleaned:
        raise ValueError(f"{label} ne peut pas être vide.")
    if len(cleaned) > maximum:
        raise ValueError(f"{label} est limité à {maximum} caractères.")
    return cleaned


def render_discord_message(template, **values):
    """Remplace seulement les variables prévues, sans moteur de gabarit complexe."""
    message = template
    for key, value in values.items():
        message = message.replace("{" + key + "}", str(value or ""))
    return message


def post_discord_message(webhook_url, message, username="Compteur"):
    from runtime_policy import require_external
    require_external()
    """Envoie une notification courte sans divulguer l'URL en cas d'échec."""
    payload = json.dumps(
        {
            "content": message,
            "username": username,
            "allowed_mentions": {"parse": []},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    discord_request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": f"OpenFabLab/{__version__}"},
        method="POST",
    )
    with urllib.request.urlopen(discord_request, timeout=5) as response:
        response.read(1)


def send_discord_notification(
    database,
    event,
    display_name=None,
    action=None,
    deadline=None,
    client=None,
    invoice_number=None,
    sent_date=None,
    month=None,
    wait_for_delivery=False,
):
    """Planifie la notification sans ralentir le pointage sur la tablette."""
    if not load_modules(database)["discord"]:
        return False
    settings = load_discord_settings(database)
    option_key = {
        "arrival": "arrivals",
        "departure": "departures",
        "visitor": "visitors",
        "retention": "retention",
        "invoice_overdue": "invoice_overdue",
        "monthly_animations": "monthly_animations",
    }.get(event)
    webhook_url = read_discord_webhook()
    if not option_key or not settings["enabled"] or not settings[option_key] or not webhook_url:
        return False

    template_key = {
        "arrival": "arrival_message",
        "departure": "departure_message",
        "visitor": "visitor_message",
        "retention": "retention_message",
        "invoice_overdue": "invoice_overdue_message",
        "monthly_animations": "monthly_animations_message",
    }[event]
    message = render_discord_message(
        settings[template_key],
        name=display_name,
        action=action,
        date=deadline,
        client=client,
        invoice_number=invoice_number,
        sent_date=sent_date,
        month=month,
    )

    def worker():
        try:
            post_discord_message(webhook_url, message, settings["bot_name"])
            return True
        except (OSError, urllib.error.URLError, ValueError):
            current_app.logger.warning("Notification Discord temporairement indisponible")
            return False

    # Le journal Flask n'est plus accessible hors du contexte de requête : on
    # capture l'application avant de démarrer le fil très court.
    application = current_app._get_current_object()

    def safe_worker():
        with application.app_context():
            return worker()

    if current_app.config.get("DISCORD_SYNCHRONOUS") or wait_for_delivery:
        return safe_worker()
    else:
        threading.Thread(
            target=safe_worker, name="openfablab-discord", daemon=True
        ).start()
    return True


def parse_non_negative_integer(value, label, required=True):
    """Valide un compteur de participants sans accepter de décimales."""
    cleaned = (value or "").strip()
    if not cleaned and not required:
        return None, None
    try:
        parsed = int(cleaned)
        if parsed < 0 or parsed > 100000:
            raise ValueError
        return parsed, None
    except ValueError:
        return None, f"{label} doit être un nombre entier positif ou nul."


def minutes_between_times(start_time, end_time):
    """Calcule une durée le même jour, en autorisant une fin après minuit."""
    start = datetime.strptime(start_time, "%H:%M")
    end = datetime.strptime(end_time, "%H:%M")
    minutes = int((end - start).total_seconds() // 60)
    if minutes <= 0:
        minutes += 24 * 60
    return minutes


def parse_time_range(start_value, end_value, *, required=False):
    """Valide deux horaires précis et renvoie leur durée en minutes."""
    start_time = (start_value or "").strip()
    end_time = (end_value or "").strip()
    if not start_time and not end_time and not required:
        return None, None, None, None
    if not TIME_PATTERN.fullmatch(start_time) or not TIME_PATTERN.fullmatch(end_time):
        return start_time or None, end_time or None, None, (
            "Indiquez une heure de début et une heure de fin valides."
        )
    duration_minutes = minutes_between_times(start_time, end_time)
    if duration_minutes < 15 or duration_minutes > 8 * 60:
        return start_time, end_time, duration_minutes, (
            "La durée doit être comprise entre 15 minutes et 8 heures."
        )
    return start_time, end_time, duration_minutes, None


def parse_legacy_time_range(value):
    """Interprète les formulations historiques simples sans imposer une migration."""
    text = (value or "").strip().lower()
    if not text:
        return None
    match = re.search(
        r"(\d{1,2})(?:\s*(?:h|:|h\s*))\s*(\d{0,2})\s*(?:à|a|-)\s*"
        r"(\d{1,2})(?:\s*(?:h|:|h\s*))\s*(\d{0,2})",
        text,
    )
    if not match:
        return None
    start_time = f"{int(match.group(1)):02d}:{int(match.group(2) or 0):02d}"
    end_time = f"{int(match.group(3)):02d}:{int(match.group(4) or 0):02d}"
    if not TIME_PATTERN.fullmatch(start_time) or not TIME_PATTERN.fullmatch(end_time):
        return None
    duration_minutes = minutes_between_times(start_time, end_time)
    if not 15 <= duration_minutes <= 8 * 60:
        return None
    return start_time, end_time, duration_minutes


def parse_service_form(form):
    """Normalise le formulaire commun aux trois services du FabLab."""
    service_type = form.get("service_type", "").strip()
    title = form.get("title", "").strip()
    service_date = form.get("service_date", "").strip()
    invoice_reference = form.get("invoice_reference", "").strip()
    client_name = form.get("client_name", "").strip()
    description = form.get("description", "").strip()
    errors = []
    if service_type not in {"animation", "reservation", "rental"}:
        errors.append("Choisissez un type d'enregistrement valide.")
    if not title or len(title) > 160:
        errors.append("Le titre ou le nom de la machine est obligatoire (160 caractères maximum).")
    try:
        datetime.strptime(service_date, "%Y-%m-%d")
    except ValueError:
        errors.append("Indiquez une date valide.")

    if "start_time" not in form and "end_time" not in form:
        # Compatibilité avec les intégrations des versions antérieures. Le
        # formulaire V2 transmet toujours explicitement les deux champs.
        start_time, end_time, duration_minutes, time_error = "09:00", "10:00", 60, None
    else:
        start_time, end_time, duration_minutes, time_error = parse_time_range(
            form.get("start_time"), form.get("end_time"), required=True
        )
    if time_error:
        errors.append(time_error)
    try:
        minimum_age = int((form.get("minimum_age", "10") or "10").strip())
        if minimum_age < 0 or minimum_age > 120:
            raise ValueError
    except ValueError:
        minimum_age = 10
        errors.append("L'âge minimum doit être compris entre 0 et 120 ans.")
    if len(description) > 3000:
        errors.append("La description est limitée à 3 000 caractères.")

    expected = actual = participants = None
    amount_cents = None
    if service_type == "animation":
        expected, error = parse_non_negative_integer(
            form.get("expected_participants"), "Le nombre de places maximum"
        )
        if error:
            errors.append(error)
        actual, error = parse_non_negative_integer(
            form.get("actual_participants") or "0", "Le nombre de participants présents"
        )
        if error:
            errors.append(error)
        invoice_reference = ""
        client_name = ""
    elif service_type in {"reservation", "rental"}:
        if not invoice_reference or len(invoice_reference) > 120:
            errors.append("La référence de facture est obligatoire (120 caractères maximum).")
        if not client_name or len(client_name) > 160:
            errors.append("Le nom de la structure ou de la personne est obligatoire.")
        if service_type == "reservation":
            participants, error = parse_non_negative_integer(
                form.get("participants"), "Le nombre de participants"
            )
            if error:
                errors.append(error)
        try:
            amount = Decimal((form.get("amount", "") or "").strip().replace(",", "."))
            if not amount.is_finite() or amount < 0 or amount > Decimal("1000000"):
                raise InvalidOperation
            amount_cents = int(
                (amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
        except (InvalidOperation, ValueError):
            errors.append("Le tarif doit être un montant positif valide.")

    return {
        "service_type": service_type,
        "title": title,
        "service_date": service_date,
        "start_time": start_time,
        "end_time": end_time,
        "duration_minutes": duration_minutes,
        "minimum_age": minimum_age,
        "description": description or None,
        "expected_participants": expected,
        "actual_participants": actual,
        "participants": participants,
        "invoice_reference": invoice_reference or None,
        "client_name": client_name or None,
        "amount_cents": amount_cents,
    }, errors


def parse_iso_date(value, label):
    """Valide une date de formulaire et conserve son format ISO SQLite."""
    cleaned = (value or "").strip()
    try:
        datetime.strptime(cleaned, "%Y-%m-%d")
        return cleaned, None
    except ValueError:
        return cleaned, f"{label} n'est pas valide."


def timestamp_to_local_date(value):
    """Présente un horodatage de suivi sous forme de date locale éditable."""
    if not value:
        return ""
    try:
        return parse_timestamp(value).astimezone(PARIS_TIMEZONE).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return ""


def local_date_to_utc_iso(value):
    """Convertit une date locale de formulaire en horodatage UTC explicite."""
    local_noon = datetime.strptime(value, "%Y-%m-%d").replace(
        hour=12, tzinfo=PARIS_TIMEZONE
    )
    return local_noon.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_optional_tracking_date(form, field_name, label, existing_value=None):
    """Lit une date facultative, en conservant l'existant si le champ est absent."""
    if field_name not in form:
        return existing_value, None
    raw_value = form.get(field_name, "").strip()
    if not raw_value:
        return None, None
    parsed_date, error = parse_iso_date(raw_value, label)
    if error:
        return existing_value, error
    return local_date_to_utc_iso(parsed_date), None


def validate_billing_reference(value, label):
    """Autorise un libellé court tout en excluant les caractères de contrôle."""
    cleaned = (value or "").strip()
    if not cleaned:
        return cleaned, f"{label} est obligatoire."
    if len(cleaned) > 60 or any(ord(character) < 32 for character in cleaned):
        return cleaned, f"{label} est limité à 60 caractères lisibles."
    return cleaned, None


def next_billing_number(database, field_name, year, rental=False):
    """Attribue le prochain numéro annuel, indépendamment pour devis et factures."""
    if field_name not in {"quote_number", "invoice_number"}:
        raise ValueError("Champ de numérotation inconnu")
    prefix = f"{year}.L" if rental else f"{year}."
    rows = database.execute(
        f"SELECT {field_name} FROM billing_records WHERE {field_name} LIKE ?",
        (f"{prefix}%",),
    ).fetchall()
    sequence = 0
    for row in rows:
        value = row[field_name]
        if not value:
            continue
        suffix = value[len(prefix):]
        if suffix.isdigit():
            sequence = max(sequence, int(suffix))
    return f"{prefix}{sequence + 1}"


def parse_billing_form(form, database, existing_record=None):
    """Valide un devis de réservation ou de location et calcule son total."""
    values = {
        "billing_type": form.get("billing_type", "reservation").strip(),
        "client_contact": form.get("client_contact", "").strip(),
        "client_structure": form.get("client_structure", "").strip(),
        "address_line": form.get("address_line", "").strip(),
        "postal_code": form.get("postal_code", "").strip(),
        "city": form.get("city", "").strip(),
        "phone": form.get("phone", "").strip(),
        "email": form.get("email", "").strip(),
        "title": form.get("title", "").strip(),
        "description": form.get("description", "").strip(),
        "rate_category": form.get("rate_category", "").strip(),
        "custom_tariff_key": form.get("custom_tariff_key", "").strip(),
        "rate_unit": form.get("rate_unit", "").strip(),
        "consumable_mode": form.get("consumable_mode", "").strip(),
        "notes": form.get("notes", "").strip(),
    }
    errors = []
    if values["billing_type"] not in {"reservation", "rental"}:
        errors.append("Choisissez un créneau réservable ou une location de machine.")
        values["billing_type"] = "reservation"
    for key, label, limit in (
        ("client_contact", "Le nom du contact", 160),
        ("client_structure", "Le nom de la structure", 180),
        ("address_line", "L'adresse postale", 220),
        ("postal_code", "Le code postal", 12),
        ("city", "La commune", 160),
        ("title", "Le titre de la prestation", 180),
        ("description", "La description et l'objectif", 3000),
    ):
        if not values[key]:
            errors.append(f"{label} est obligatoire.")
        elif len(values[key]) > limit:
            errors.append(f"{label} est trop long.")
    if values["email"] and not EMAIL_PATTERN.fullmatch(values["email"]):
        errors.append("L'adresse e-mail n'est pas valide.")
    if values["phone"] and not PHONE_PATTERN.fullmatch(values["phone"]):
        errors.append("Le numéro de téléphone n'est pas valide.")
    values["activity_date"], date_error = parse_iso_date(
        form.get("activity_date"),
        "La date de la prestation",
    )
    if date_error:
        errors.append(date_error)
    legacy_time_details = form.get("activity_time_details", "").strip()
    if "activity_start_time" not in form and "activity_end_time" not in form:
        legacy_range = parse_legacy_time_range(legacy_time_details)
        if legacy_range:
            (
                values["activity_start_time"], values["activity_end_time"],
                values["activity_duration_minutes"],
            ) = legacy_range
        else:
            values["activity_start_time"] = None
            values["activity_end_time"] = None
            values["activity_duration_minutes"] = None
        time_error = None
    else:
        (
            values["activity_start_time"],
            values["activity_end_time"],
            values["activity_duration_minutes"],
            time_error,
        ) = parse_time_range(
            form.get("activity_start_time"),
            form.get("activity_end_time"),
            required=True,
        )
    if time_error:
        errors.append(time_error)
    if values["activity_start_time"] and values["activity_end_time"]:
        values["activity_time_details"] = (
            f"{values['activity_start_time'].replace(':', ' h ', 1).rstrip(' 0')} à "
            f"{values['activity_end_time'].replace(':', ' h ', 1).rstrip(' 0')}"
        )
    else:
        values["activity_time_details"] = legacy_time_details

    tariffs = load_billing_tariffs(database)

    if values["billing_type"] == "rental":
        machine_key = form.get("rental_machine_key", "").strip()
        rental_catalog = available_rental_catalog(database, existing_record)
        machine = rental_catalog.get(machine_key)
        if machine is None or ((not machine["active"] or machine["archived"]) and
                               not (existing_record and existing_record.get("rental_machine_key") == machine_key)):
            errors.append("Choisissez une machine disponible à la location.")
            if rental_catalog:
                machine_key, machine = next(iter(rental_catalog.items()))
            else:
                machine_key, machine = "", {
                    "name": "Machine non configurée",
                    "monthly_cents": 0,
                    "deposit_cents": 0,
                }
        values.update({
            "rental_machine_key": machine_key,
            "rental_machine_name": machine["name"],
            "rental_monthly_cents": machine["monthly_cents"],
            "rental_deposit_cents": machine["deposit_cents"],
            "rental_delivery": 1 if form.get("rental_delivery") == "1" else 0,
            "rental_deposit_exempt": 1 if form.get("rental_deposit_exempt") == "1" else 0,
            "participants": 0,
            "rate_category": "normal",
            "rate_is_agglo": 0,
            "rate_unit": "hourly",
            "rate_quantity": 1,
            "travel_quantity": 0,
            "consumable_mode": "client",
            "consumable_quantity": 0,
            "rate_unit_cents": 0,
            "custom_tariff_key": None,
            "custom_tariff_name": None,
            "travel_unit_cents": tariffs["travel"],
            "consumable_unit_cents": tariffs["consumable"],
            "rental_contract_fee_cents": tariffs["rental_contract"],
            "rental_delivery_fee_cents": tariffs["rental_delivery"],
        })
        try:
            values["rental_months"] = int(form.get("rental_months", "1"))
            if not 1 <= values["rental_months"] <= 9:
                raise ValueError
        except ValueError:
            values["rental_months"] = 1
            errors.append("La durée de location doit être comprise entre 1 et 9 mois.")
        values["rental_end_date"], end_error = parse_iso_date(
            form.get("rental_end_date"), "La date de retour"
        )
        if end_error:
            errors.append(end_error)
        elif values["activity_date"] and values["rental_end_date"] < values["activity_date"]:
            errors.append("La date de retour doit être postérieure à la remise du matériel.")
        if (
            existing_record
            and existing_record.get("billing_type") == "rental"
        ):
            # Un changement de tarif ne doit jamais réécrire silencieusement un
            # devis existant. Une nouvelle machine adopte toutefois son tarif
            # courant, tandis que la machine déjà choisie garde son instantané.
            if existing_record.get("rental_machine_key") == machine_key:
                values["rental_monthly_cents"] = (
                    existing_record.get("rental_monthly_cents")
                    if existing_record.get("rental_monthly_cents") is not None
                    else values["rental_monthly_cents"]
                )
                values["rental_deposit_cents"] = (
                    existing_record.get("rental_deposit_cents")
                    if existing_record.get("rental_deposit_cents") is not None
                    else values["rental_deposit_cents"]
                )
            for field_name in (
                "rental_contract_fee_cents", "rental_delivery_fee_cents"
            ):
                if existing_record.get(field_name) is not None:
                    values[field_name] = existing_record[field_name]
    else:
        selected_rate_category = values["rate_category"]
        if selected_rate_category not in {"normal", "reduced", "agglo"}:
            errors.append("Choisissez un tarif normal, réduit ou structure.")
            selected_rate_category = "normal"
        values["rate_is_agglo"] = 1 if selected_rate_category == "agglo" else 0
        # Les bases déjà en service possèdent une contrainte historique limitée
        # à normal/réduit. Le tarif structure est donc conservé dans un booléen dédié.
        values["rate_category"] = (
            "normal" if selected_rate_category == "agglo" else selected_rate_category
        )
        if values["rate_unit"] not in {"hourly", "half_day"} and not values["custom_tariff_key"]:
            errors.append("Choisissez un tarif horaire ou demi-journée.")
        if values["consumable_mode"] not in {"included", "client", "billed"}:
            errors.append("Choisissez le mode de fourniture des consommables.")
        for key, label, minimum, maximum in (
            ("participants", "Le nombre de participants", 0, 100000),
            ("rate_quantity", "La quantité de créneaux", 1, 1000),
            ("travel_quantity", "La quantité de déplacement", 0, 1000),
            ("consumable_quantity", "La quantité de consommables", 0, 1000),
        ):
            try:
                values[key] = int((form.get(key, "") or "0").strip())
                if values[key] < minimum or values[key] > maximum:
                    raise ValueError
            except ValueError:
                errors.append(f"{label} doit être compris entre {minimum} et {maximum}.")
                values[key] = minimum
        if values["consumable_mode"] != "billed":
            values["consumable_quantity"] = 0
        values["rate_unit_cents"] = (
            0 if selected_rate_category == "agglo" else
            tariffs[f"{selected_rate_category}_{values['rate_unit']}"]
            if values["rate_unit"] in {"hourly", "half_day"} else 0
        )
        custom_key = values["custom_tariff_key"]
        values["custom_tariff_name"] = None
        if custom_key:
            custom = load_custom_tariffs(database, include_inactive=True).get(custom_key)
            same_previous = bool(existing_record and existing_record.get("custom_tariff_key") == custom_key)
            if not custom or ((not custom["active"] or custom["archived"]) and not same_previous):
                errors.append("Ce tarif personnalisé n'est plus disponible.")
            else:
                values["rate_category"] = "normal"
                values["rate_is_agglo"] = 0
                values["rate_unit"] = custom["unit"]
                values["rate_unit_cents"] = custom["cents"]
                values["custom_tariff_name"] = custom["name"]
                if same_previous:
                    values["rate_unit_cents"] = existing_record["rate_unit_cents"]
                    values["custom_tariff_name"] = existing_record.get("custom_tariff_name") or custom["name"]
        values["travel_unit_cents"] = tariffs["travel"]
        values["consumable_unit_cents"] = tariffs["consumable"]
        values["rental_contract_fee_cents"] = tariffs["rental_contract"]
        values["rental_delivery_fee_cents"] = tariffs["rental_delivery"]
        values.update({
            "rental_machine_key": None,
            "rental_machine_name": None,
            "rental_months": 1,
            "rental_monthly_cents": 0,
            "rental_deposit_cents": 0,
            "rental_delivery": 0,
            "rental_deposit_exempt": 0,
            "rental_end_date": None,
        })
        if (
            existing_record
            and existing_record.get("billing_type") == "reservation"
        ):
            previous_category = existing_record.get("rate_category") or "normal"
            if (
                previous_category == selected_rate_category
                and existing_record.get("custom_tariff_key") == values["custom_tariff_key"]
                and existing_record.get("rate_unit") == values["rate_unit"]
                and existing_record.get("rate_unit_cents") is not None
            ):
                values["rate_unit_cents"] = existing_record["rate_unit_cents"]
            for field_name in ("travel_unit_cents", "consumable_unit_cents"):
                if existing_record.get(field_name) is not None:
                    values[field_name] = existing_record[field_name]
    values["amount_cents"] = compute_total_cents(values)
    return values, errors


def parse_billing_client_form(form):
    """Valide les coordonnées modifiables depuis l'annuaire client."""
    values = {
        "client_contact": form.get("client_contact", "").strip(),
        "client_structure": form.get("client_structure", "").strip(),
        "address_line": form.get("address_line", "").strip(),
        "postal_code": form.get("postal_code", "").strip(),
        "city": form.get("city", "").strip(),
        "phone": form.get("phone", "").strip(),
        "email": form.get("email", "").strip(),
    }
    errors = []
    for key, label, limit in (
        ("client_contact", "Le nom du contact", 160),
        ("client_structure", "Le nom de la structure", 180),
        ("address_line", "L'adresse postale", 220),
        ("postal_code", "Le code postal", 12),
        ("city", "La commune", 160),
    ):
        if not values[key]:
            errors.append(f"{label} est obligatoire.")
        elif len(values[key]) > limit:
            errors.append(f"{label} est trop long.")
    if values["email"] and not EMAIL_PATTERN.fullmatch(values["email"]):
        errors.append("L'adresse e-mail n'est pas valide.")
    if values["phone"] and not PHONE_PATTERN.fullmatch(values["phone"]):
        errors.append("Le numéro de téléphone n'est pas valide.")
    return values, errors


def billing_record_dict(row):
    """Convertit une ligne SQLite en dictionnaire enrichi pour les documents."""
    record = dict(row)
    if record.get("rate_is_agglo"):
        record["rate_category"] = "agglo"
    if record.get("activity_start_time") and record.get("activity_end_time"):
        record["activity_time_details"] = (
            f"{record['activity_start_time']} à {record['activity_end_time']}"
        )
    record["status_label"] = billing_status_label(record)
    return record


def load_billing_record(database, record_id):
    row = database.execute(
        "SELECT * FROM billing_records WHERE id = ?", (record_id,)
    ).fetchone()
    if row is None:
        abort(404)
    return billing_record_dict(row)


def synchronize_billing_service(database, record):
    """Crée ou actualise la prestation utilisée par les statistiques."""
    now = utc_now_iso()
    reference = record.get("invoice_number") or record["quote_number"]
    service_type = "rental" if record.get("billing_type") == "rental" else "reservation"
    if record.get("service_id"):
        database.execute(
            """
            UPDATE fablab_services SET service_type = ?, title = ?, service_date = ?, participants = ?,
                invoice_reference = ?, client_name = ?, amount_cents = ?,
                start_time = ?, end_time = ?, duration_minutes = ?,
                description = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                service_type, record["title"], record["activity_date"], record["participants"],
                reference, record["client_structure"], record["amount_cents"],
                record.get("activity_start_time"), record.get("activity_end_time"),
                record.get("activity_duration_minutes"), record.get("description"), now,
                record["service_id"],
            ),
        )
        return record["service_id"]
    cursor = database.execute(
        """
        INSERT INTO fablab_services (
            service_type, title, service_date, expected_participants,
            actual_participants, participants, invoice_reference,
            client_name, amount_cents, created_at, updated_at
        ) VALUES (?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?)
        """,
        (
            service_type, record["title"], record["activity_date"], record["participants"],
            reference, record["client_structure"], record["amount_cents"], now, now,
        ),
    )
    database.execute(
        "UPDATE billing_records SET service_id = ? WHERE id = ?",
        (cursor.lastrowid, record["id"]),
    )
    database.execute('UPDATE resource_bookings SET service_id=? WHERE billing_record_id=?', (cursor.lastrowid,record['id']))
    database.execute(
        """
        UPDATE fablab_services SET start_time = ?, end_time = ?,
            duration_minutes = ?, description = ? WHERE id = ?
        """,
        (
            record.get("activity_start_time"), record.get("activity_end_time"),
            record.get("activity_duration_minutes"), record.get("description"),
            cursor.lastrowid,
        ),
    )
    return cursor.lastrowid


def load_automatic_closure_settings(database):
    """Retourne l'état et les sept horaires de clôture automatique."""
    return {
        "enabled": read_setting(database, "automatic_closure_enabled", "0") == "1",
        "days": [
            {
                "key": key,
                "label": label,
                "time": read_setting(database, f"automatic_closure_{key}"),
            }
            for key, label in WEEKDAYS
        ],
    }


def close_all_open_sessions(database, exit_method, closed_at=None):
    """Ferme en une seule transaction toutes les sessions encore ouvertes."""
    with DATABASE_MAINTENANCE_LOCK:
        closure_time = closed_at or utc_now_iso()
        cursor = database.execute(
            """
            UPDATE sessions
            SET check_out = ?, exit_method = ?
            WHERE check_out IS NULL
            """,
            (closure_time, exit_method),
        )
        database.commit()
    return cursor.rowcount


def run_automatic_closure(database, now=None):
    """Applique au plus une fois la clôture prévue pour la journée locale."""
    with DATABASE_MAINTENANCE_LOCK:
        current_local = (now or datetime.now(PARIS_TIMEZONE)).astimezone(PARIS_TIMEZONE)
        if read_setting(database, "automatic_closure_enabled", "0") != "1":
            return 0

        weekday_key = WEEKDAYS[current_local.weekday()][0]
        configured_time = read_setting(database, f"automatic_closure_{weekday_key}")
        if not TIME_PATTERN.fullmatch(configured_time or ""):
            return 0

        hour, minute = map(int, configured_time.split(":"))
        scheduled_local = current_local.replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if current_local < scheduled_local:
            return 0

        day_key = current_local.strftime("%Y-%m-%d")
        if read_setting(database, "automatic_closure_last_date") == day_key:
            return 0

        scheduled_utc = scheduled_local.astimezone(timezone.utc).isoformat(timespec="seconds")
        cursor = database.execute(
            """
            UPDATE sessions
            SET check_out = ?, exit_method = 'automatic'
            WHERE check_out IS NULL AND check_in <= ?
            """,
            (scheduled_utc, scheduled_utc),
        )
        write_setting(database, "automatic_closure_last_date", day_key)
        database.commit()
        return cursor.rowcount


def load_retention_settings(database):
    """Retourne les durées de conservation validées par le DPO."""
    def setting_as_int(key, default):
        try:
            return max(0, int(read_setting(database, key, str(default))))
        except (TypeError, ValueError):
            return default

    last_report = read_setting(database, "retention_last_report", "")
    try:
        report = json.loads(last_report) if last_report else None
    except json.JSONDecodeError:
        report = None
    return {
        "contact_years": setting_as_int("retention_contact_years", 2),
        "deactivation_years": setting_as_int("retention_deactivation_years", 3),
        "deletion_years": setting_as_int("retention_deletion_years", 5),
        "last_run_date": read_setting(database, "retention_last_run_date"),
        "last_report": report,
    }


def years_ago(reference, years):
    """Soustrait des années en gérant proprement le 29 février."""
    try:
        return reference.replace(year=reference.year - years)
    except ValueError:
        return reference.replace(year=reference.year - years, day=28)


def years_after(reference, years):
    """Ajoute des années en gérant proprement le 29 février."""
    try:
        return reference.replace(year=reference.year + years)
    except ValueError:
        return reference.replace(year=reference.year + years, day=28)


def warn_before_retention_action(
    database,
    user,
    warning_type,
    activity_local,
    years,
    action_label,
    current_local,
):
    """Avertit une seule fois dans les sept jours précédant une action RGPD."""
    if not years:
        return False
    deadline = years_after(activity_local, years).date()
    days_until_deadline = (deadline - current_local.date()).days
    if not 1 <= days_until_deadline <= 7:
        return False
    already_sent = database.execute(
        """
        SELECT 1 FROM retention_warnings
        WHERE user_id = ? AND warning_type = ? AND deadline = ?
        """,
        (user["id"], warning_type, deadline.isoformat()),
    ).fetchone()
    if already_sent:
        return False

    last_name = (user["last_name"] or "").strip()
    display_name = user["first_name"].strip()
    if last_name:
        display_name += f" {last_name[0]}."
    delivered = send_discord_notification(
        database,
        "retention",
        display_name=display_name,
        action=action_label,
        deadline=deadline.strftime("%d/%m/%Y"),
        wait_for_delivery=True,
    )
    if not delivered:
        return False
    database.execute(
        """
        INSERT OR IGNORE INTO retention_warnings
            (user_id, warning_type, deadline, sent_at)
        VALUES (?, ?, ?, ?)
        """,
        (user["id"], warning_type, deadline.isoformat(), utc_now_iso()),
    )
    return True


def run_data_retention(database, now=None, force=False):
    """Applique une fois par jour les règles de conservation configurées."""
    with DATABASE_MAINTENANCE_LOCK:
        current_local = (now or datetime.now(PARIS_TIMEZONE)).astimezone(PARIS_TIMEZONE)
        day_key = current_local.strftime("%Y-%m-%d")
        if not force and read_setting(database, "retention_last_run_date") == day_key:
            return None

        settings = load_retention_settings(database)
        users = database.execute(
            """
            SELECT users.id, users.first_name, users.last_name, users.active,
                   users.created_at, users.email, users.phone,
                   MAX(COALESCE(sessions.check_out, sessions.check_in)) AS last_passage
            FROM users
            LEFT JOIN sessions ON sessions.user_id = users.id
            GROUP BY users.id
            """
        ).fetchall()
        report = {"contacts_cleared": 0, "deactivated": 0, "deleted": 0}

        for user in users:
            activity = parse_timestamp(user["last_passage"] or user["created_at"])
            activity_local = activity.astimezone(PARIS_TIMEZONE)

            if user["email"] or user["phone"]:
                warn_before_retention_action(
                    database,
                    user,
                    "contact",
                    activity_local,
                    settings["contact_years"],
                    "effacement de l’e-mail et du téléphone",
                    current_local,
                )
            if user["active"]:
                warn_before_retention_action(
                    database,
                    user,
                    "deactivation",
                    activity_local,
                    settings["deactivation_years"],
                    "désactivation du compte",
                    current_local,
                )
            warn_before_retention_action(
                database,
                user,
                "deletion",
                activity_local,
                settings["deletion_years"],
                "suppression et anonymisation du compte",
                current_local,
            )

            deletion_years = settings["deletion_years"]
            if deletion_years and activity_local <= years_ago(current_local, deletion_years):
                # Une session anormalement restée ouverte est neutralisée : sa
                # durée ne doit pas gonfler artificiellement les statistiques.
                database.execute(
                    """
                    UPDATE sessions
                    SET check_out = check_in, exit_method = 'automatic'
                    WHERE user_id = ? AND check_out IS NULL
                    """,
                    (user["id"],),
                )
                database.execute("DELETE FROM users WHERE id = ?", (user["id"],))
                report["deleted"] += 1
                continue

            deactivation_years = settings["deactivation_years"]
            if (
                deactivation_years
                and user["active"]
                and activity_local <= years_ago(current_local, deactivation_years)
            ):
                database.execute(
                    """
                    UPDATE sessions
                    SET check_out = check_in, exit_method = 'automatic'
                    WHERE user_id = ? AND check_out IS NULL
                    """,
                    (user["id"],),
                )
                database.execute("UPDATE users SET active = 0 WHERE id = ?", (user["id"],))
                report["deactivated"] += 1

            contact_years = settings["contact_years"]
            if (
                contact_years
                and (user["email"] or user["phone"])
                and activity_local <= years_ago(current_local, contact_years)
            ):
                database.execute(
                    "UPDATE users SET email = NULL, phone_country_code = '+33', phone = NULL WHERE id = ?",
                    (user["id"],),
                )
                report["contacts_cleared"] += 1

        write_setting(database, "retention_last_run_date", day_key)
        write_setting(
            database,
            "retention_last_report",
            json.dumps({"date": day_key, **report}, ensure_ascii=False),
        )
        database.commit()
        return report


def run_invoice_payment_reminders(database, now=None):
    """Avertit une seule fois lorsqu'une facture impayée dépasse trente jours."""
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    threshold = current_time.astimezone(timezone.utc) - timedelta(days=30)
    rows = database.execute(
        """
        SELECT id, invoice_number, invoice_sent_at, client_structure
        FROM billing_records
        WHERE invoice_number IS NOT NULL
          AND invoice_sent_at IS NOT NULL
          AND paid_at IS NULL
          AND payment_overdue_notified_at IS NULL
        """
    ).fetchall()
    delivered_count = 0
    for row in rows:
        try:
            sent_at = parse_timestamp(row["invoice_sent_at"])
        except (TypeError, ValueError):
            continue
        if sent_at > threshold:
            continue
        delivered = send_discord_notification(
            database,
            "invoice_overdue",
            client=row["client_structure"],
            invoice_number=row["invoice_number"],
            sent_date=sent_at.astimezone(PARIS_TIMEZONE).strftime("%d/%m/%Y"),
            wait_for_delivery=True,
        )
        if delivered:
            database.execute(
                """
                UPDATE billing_records
                SET payment_overdue_notified_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (utc_now_iso(), utc_now_iso(), row["id"]),
            )
            delivered_count += 1
    if delivered_count:
        database.commit()
    return delivered_count


def run_monthly_animation_reminder(database, now=None):
    """Rappelle une seule fois, le 1er, de saisir les animations du mois passé."""
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_local = current_time.astimezone(PARIS_TIMEZONE)
    if current_local.day != 1:
        return False

    previous_month = current_local.replace(day=1) - timedelta(days=1)
    period_key = previous_month.strftime("%Y-%m")
    if read_setting(database, "discord_monthly_animations_last_period", "") == period_key:
        return False

    month_label = (
        f"{FRENCH_MONTH_NAMES[previous_month.month - 1]} {previous_month.year}"
    )
    delivered = send_discord_notification(
        database,
        "monthly_animations",
        month=month_label,
        wait_for_delivery=True,
    )
    if delivered:
        write_setting(database, "discord_monthly_animations_last_period", period_key)
        database.commit()
    return delivered


def normalize_backup_subdirectory(value):
    """Valide un sous-dossier de sauvegarde sans permettre de sortir du volume monté."""
    normalized = (value or "").strip().replace("\\", "/").strip("/")
    if not normalized:
        raise ValueError("Indiquez un dossier de sauvegarde.")
    parts = normalized.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Le dossier de sauvegarde contient un chemin non autorisé.")
    if len(normalized) > 120 or any(
        not all(character.isalnum() or character in " -_." for character in part)
        for part in parts
    ):
        raise ValueError(
            "Le dossier de sauvegarde peut contenir des lettres, chiffres, espaces, tirets et points."
        )
    return "/".join(parts)


def automatic_backup_directory(application, subdirectory):
    """Résout le dossier réel en restant dans la racine montée par le NAS."""
    root = Path(application.config["BACKUP_ROOT"]).expanduser().resolve()
    candidate = root.joinpath(*subdirectory.split("/")).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Le dossier de sauvegarde n'est pas autorisé.")
    return candidate


def load_automatic_backup_settings(database, application):
    """Retourne les réglages et le dernier état de la sauvegarde automatique."""
    try:
        interval_days = int(read_setting(database, "automatic_backup_interval_days", "1"))
    except (TypeError, ValueError):
        interval_days = 1
    interval_days = min(365, max(1, interval_days))
    subdirectory = read_setting(
        database, "automatic_backup_subdirectory", "OpenFabLab"
    )
    try:
        subdirectory = normalize_backup_subdirectory(subdirectory)
    except ValueError:
        subdirectory = "OpenFabLab"
    display_root = Path(application.config["BACKUP_DISPLAY_ROOT"])
    return {
        "enabled": read_setting(database, "automatic_backup_enabled", "0") == "1",
        "interval_days": interval_days,
        "subdirectory": subdirectory,
        "display_path": str(display_root.joinpath(*subdirectory.split("/"))),
        "last_attempt": read_setting(database, "automatic_backup_last_attempt"),
        "last_success": read_setting(database, "automatic_backup_last_success"),
        "last_filename": read_setting(database, "automatic_backup_last_filename"),
        "last_error": read_setting(database, "automatic_backup_last_error"),
    }


def run_automatic_backup(database, application, now=None, force=False):
    """Crée un instantané SQLite périodique dans le dossier monté du NAS."""
    settings = load_automatic_backup_settings(database, application)
    if not settings["enabled"]:
        return None

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    if not force and settings["last_success"]:
        try:
            last_success = parse_timestamp(settings["last_success"])
            if current_time < last_success + timedelta(days=settings["interval_days"]):
                return None
        except (TypeError, ValueError):
            pass

    # En cas d'erreur de volume, une tentative par heure suffit et évite de
    # remplir les journaux toutes les trente secondes.
    if not force and settings["last_attempt"]:
        try:
            last_attempt = parse_timestamp(settings["last_attempt"])
            if current_time < last_attempt + timedelta(hours=1):
                return None
        except (TypeError, ValueError):
            pass

    attempt_time = current_time.astimezone(timezone.utc).isoformat(timespec="seconds")
    write_setting(database, "automatic_backup_last_attempt", attempt_time)
    database.commit()

    target_directory = automatic_backup_directory(
        application, settings["subdirectory"]
    )
    local_time = current_time.astimezone(PARIS_TIMEZONE)
    filename = (
        "openfablab-sauvegarde-"
        f"{local_time.strftime('%Y-%m-%d_%H-%M')}-{application.config['APP_VERSION']}.db"
    )
    temporary_path = None
    try:
        target_directory.mkdir(parents=True, exist_ok=True)
        temporary_path = target_directory / f".{filename}.tmp-{secrets.token_hex(4)}"
        with DATABASE_MAINTENANCE_LOCK:
            destination = sqlite3.connect(temporary_path)
            try:
                database.backup(destination)
            finally:
                destination.close()
            validate_database_file(temporary_path)
            final_path = target_directory / filename
            os.replace(temporary_path, final_path)
            temporary_path = None
        write_setting(database, "automatic_backup_last_success", attempt_time)
        write_setting(database, "automatic_backup_last_filename", filename)
        write_setting(database, "automatic_backup_last_error", "")
        database.commit()
        return final_path
    except (OSError, sqlite3.Error, ValueError) as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        write_setting(database, "automatic_backup_last_error", str(error))
        database.commit()
        raise


def start_automatic_closure_worker(application):
    """Lance les contrôles périodiques dans l'unique processus Gunicorn."""
    from runtime_policy import external_allowed, storage_guard
    if not external_allowed(application.config['DATABASE']):
        return
    if getattr(application, "_automatic_closure_worker_started", False):
        return
    application._automatic_closure_worker_started = True

    def worker():
        while True:
            try:
                with storage_guard(application.config['DATABASE']), application.app_context():
                    if not external_allowed(application.config['DATABASE']):
                        return
                    database = get_database()
                    run_automatic_closure(database)
                    run_data_retention(database)
                    run_invoice_payment_reminders(database)
                    run_monthly_animation_reminder(database)
                    collect_openlab_weather_snapshot(database, application)
                    run_automatic_backup(database, application)
                    if load_modules(database)["public_reservations"]:
                        from family_waitlist import run as run_family_waitlist
                        run_family_waitlist(database, application.config["DATABASE"])
                        site_url = read_setting(database, "reservation_wordpress_url")
                        secret_set = bool(load_sync_secret(application.config["DATABASE"]))
                        if site_url and secret_set:
                            try:
                                interval = sync_interval_seconds(read_setting(database, "reservation_sync_interval_minutes", "1.5"))
                                last_attempt = read_setting(database, "reservation_sync_last_attempt")
                                due = (not last_attempt or datetime.now(timezone.utc) - parse_timestamp(last_attempt)
                                       >= timedelta(seconds=interval))
                                if due:
                                    write_setting(database, "reservation_sync_last_attempt", utc_now_iso())
                                    database.commit()
                                    with RESERVATION_SYNC_LOCK:
                                        result = run_sync_cycle(database, application.config["DATABASE"], site_url)
                                    notify_sync_events(database, result)
                            except (OSError, ValueError, sqlite3.Error, urllib.error.URLError) as error:
                                database.rollback()
                                application.logger.warning("Synchronisation WordPress différée : %s", type(error).__name__)
                                previous_error = database.execute(
                                    "SELECT last_error FROM reservation_sync_state WHERE environment = 'test'"
                                ).fetchone()
                                for environment in ("test", "production"):
                                    database.execute(
                                        "INSERT INTO reservation_sync_state(environment, cursor, last_error_at, last_error) "
                                        "VALUES (?, '', ?, ?) ON CONFLICT(environment) DO UPDATE SET "
                                        "last_error_at=excluded.last_error_at, last_error=excluded.last_error",
                                        (environment, utc_now_iso(), sync_error_label(error)),
                                    )
                                database.commit()
                                if previous_error is None or not previous_error["last_error"]:
                                    notify_reservation_discord(database, "sync_error")
            except Exception:
                application.logger.exception("Erreur de maintenance automatique")
            time.sleep(30)

    threading.Thread(
        target=worker,
        name="openfablab-maintenance",
        daemon=True,
    ).start()


def notify_sync_events(database, result):
    """Distribue les notifications du même cycle, manuel ou automatique."""
    if result.get("errors"):
        notify_reservation_discord(database, "sync_error")
    for event in result.get("notifications", []):
        notify_reservation_discord(database, event["type"], event["service_id"])
        if event["type"] == "reservation_confirmed":
            occupancy = database.execute(
                "SELECT c.capacity, COUNT(b.external_uuid) AS occupied "
                "FROM animation_reservation_config c "
                "LEFT JOIN animation_bookings b ON b.service_id = c.service_id "
                "AND b.status IN ('confirmed','offer_pending','present','absent') "
                "WHERE c.service_id = ? GROUP BY c.service_id",
                (event["service_id"],),
            ).fetchone()
            if occupancy and occupancy["capacity"] > 0 and occupancy["occupied"] == occupancy["capacity"]:
                notify_reservation_discord(database, "animation_full", event["service_id"])
        if event["type"] == "reservation_confirmed" and event.get("link_status") == "needs_review":
            notify_reservation_discord(database, "link_review", event["service_id"])


def start_local_reservation_sync_worker(application):
    """Synchroniser Normal et Test en local, sans les autres tâches de maintenance."""
    from runtime_policy import external_allowed, storage_guard
    if not external_allowed(application.config['DATABASE']):
        return
    if getattr(application, "_local_reservation_sync_started", False):
        return
    application._local_reservation_sync_started = True

    def worker():
        while True:
            try:
                with storage_guard(application.config['DATABASE']), application.app_context():
                    if not external_allowed(application.config['DATABASE']):
                        return
                    database = get_database()
                    if load_modules(database)["public_reservations"]:
                        site_url = read_setting(database, "reservation_wordpress_url")
                        if site_url and load_sync_secret(application.config["DATABASE"]):
                            interval = sync_interval_seconds(read_setting(database, "reservation_sync_interval_minutes", "1.5"))
                            last = read_setting(database, "reservation_sync_last_attempt")
                            due = not last or datetime.now(timezone.utc) - parse_timestamp(last) >= timedelta(seconds=interval)
                            if due:
                                write_setting(database, "reservation_sync_last_attempt", utc_now_iso())
                                database.commit()
                                try:
                                    with RESERVATION_SYNC_LOCK:
                                        result = run_sync_cycle(database, application.config["DATABASE"], site_url)
                                    notify_sync_events(database, result)
                                except (OSError, ValueError, sqlite3.Error, urllib.error.URLError) as error:
                                    database.rollback()
                                    for environment in ("test", "production"):
                                        database.execute(
                                            "INSERT INTO reservation_sync_state(environment, cursor, last_error_at, last_error) "
                                            "VALUES (?, '', ?, ?) ON CONFLICT(environment) DO UPDATE SET "
                                            "last_error_at=excluded.last_error_at, last_error=excluded.last_error",
                                            (environment, utc_now_iso(), sync_error_label(error)),
                                        )
                                    database.commit()
                                    application.logger.warning("Synchronisation WordPress différée : %s", type(error).__name__)
            except Exception:
                application.logger.exception("Erreur du worker local de réservation")
            time.sleep(30)

    threading.Thread(target=worker, name="openfablab-local-reservations", daemon=True).start()


def safe_filename_part(value):
    """Nettoie un nom destiné à un fichier téléchargé."""
    normalized = normalize_text_key(value) or "usager"
    return normalized.replace(" ", "-")


def compact_filename_part(value, fallback="Document"):
    """Produit un segment ASCII compact tout en conservant les majuscules utiles."""
    ascii_value = unicodedata.normalize("NFKD", str(value or "")).encode(
        "ascii", "ignore"
    ).decode("ascii")
    words = re.findall(r"[A-Za-z0-9]+", ascii_value)
    return "".join(word[:1].upper() + word[1:] for word in words) or fallback


def billing_reference_suffix(value):
    """Isole le numéro utile d'une référence annuelle, par exemple 1 ou L1."""
    normalized = unicodedata.normalize("NFKD", str(value or "")).encode(
        "ascii", "ignore"
    ).decode("ascii")
    match = re.search(r"(?:^|[^A-Za-z0-9])([A-Za-z]?\d+)$", normalized)
    return match.group(1).upper() if match else compact_filename_part(normalized, "1")


def compact_french_date(value):
    """Formate une date ISO en JJMMYYYY pour les documents client."""
    try:
        return datetime.strptime(str(value or "")[:10], "%Y-%m-%d").strftime("%d%m%Y")
    except ValueError:
        return datetime.now(PARIS_TIMEZONE).strftime("%d%m%Y")


def generate_badge_svg(user, structure=None):
    """Adapte le gabarit de gravure rouge avec le QR et le prénom de l'usager."""
    structure = structure or {"name": "Mon FabLab", "short_name": "FabLab"}
    data_directory = Path(current_database_path()).parent if structure.get('badge_template') else None
    template = badge_source(structure, BADGE_TEMPLATE_SVG, data_directory)
    qr_code = segno.make_qr(user["public_id"], error="h")
    matrix = qr_code.matrix
    module_count = len(matrix)
    qr_x, qr_y, qr_size = 5.25, 40.0, 43.5
    module_size = qr_size / module_count
    qr_rectangles = []
    for row_index, row in enumerate(matrix):
        for column_index, dark in enumerate(row):
            if dark:
                qr_rectangles.append(
                    f'<rect x="{qr_x + column_index * module_size:.4f}" '
                    f'y="{qr_y + row_index * module_size:.4f}" '
                    f'width="{module_size:.4f}" height="{module_size:.4f}" />'
                )
    qr_group = '<g id="qr-code">' + "".join(qr_rectangles) + "</g>"

    def replace_text(element_id, value):
        nonlocal template
        escaped = html.escape(value)
        template, count = re.subn(
            rf'(<text\b[^>]*\bid="{element_id}"[^>]*>).*?(</text>)',
            rf'\g<1>{escaped}\g<2>',
            template,
            count=1,
            flags=re.DOTALL,
        )
        if count != 1:
            raise RuntimeError(f"Élément SVG introuvable : {element_id}")

    if re.search(r'<text\b[^>]*\bid="structure-name"', template):
        replace_text("structure-name", structure.get("short_name") or structure.get("name", "FabLab"))
    replace_text("user-id", f"ID {user['public_id']}")
    first_name = user["first_name"].strip()
    replace_text("first-name", first_name)
    # La taille décroît pour les prénoms longs. La largeur est également bornée
    # par textLength afin que les substitutions de police dans xTool restent sûres.
    name_font_size = max(5.0, 10.7 - max(0, len(first_name) - 8) * 0.42)
    template = re.sub(
        r'(<text\b[^>]*\bid="first-name"[^>]*\bfont-size=")[^"]+',
        rf'\g<1>{name_font_size:.1f}',
        template,
        count=1,
    )
    if len(first_name) > 11:
        template = re.sub(
            r'<text\b[^>]*\bid="first-name"[^>]*>',
            lambda match: re.sub(r'\s+(?:textLength|lengthAdjust)="[^"]*"', '', match.group(0)),
            template, count=1,
        )
        template = re.sub(
            r'(<text\b[^>]*\bid="first-name")',
            r'\1 textLength="45" lengthAdjust="spacingAndGlyphs"',
            template,
            count=1,
        )
    # Standalone rendering (CLI/tests) does not require a Flask context.
    from flask import has_app_context
    label = (dynamic_category_label(get_database(), user['category']) if has_app_context()
             else structure.get('category_label') or CATEGORY_LABELS.get(user['category'], user['category']))
    replace_text("category", label)
    template, count = re.subn(
        r'<g\s+id="qr-code">.*?</g>', qr_group, template, count=1, flags=re.DOTALL
    )
    if count != 1:
        raise RuntimeError("Zone QR du gabarit SVG introuvable")

    # Le support est la carte noire photographiée dans xTool : aucun fond ni
    # contour ne doit être exporté. Tout ce qui reste correspond à la gravure.
    template, count = re.subn(
        r'<rect\b[^>]*\bid="card-background"[^>]*(?:/>|>\s*</rect>)',
        "",
        template,
        count=1,
        flags=re.DOTALL,
    )
    # A private engraving template may already have no background.
    template = re.sub(r'fill="#[0-9a-fA-F]{6}"', f'fill="{ENGRAVING_COLOR}"', template)
    template = re.sub(r'stroke="#[0-9a-fA-F]{6}"', f'stroke="{ENGRAVING_COLOR}"', template)
    template = re.sub(r'fill:#[0-9a-fA-F]{6}', f'fill:{ENGRAVING_COLOR}', template)
    template = re.sub(r'stroke:#[0-9a-fA-F]{6}', f'stroke:{ENGRAVING_COLOR}', template)
    # Les guides sont cachés mais restent magenta pour ne jamais être confondus
    # avec les éléments de gravure si l'utilisateur les affiche dans un éditeur.
    template = re.sub(
        r'(<g\b[^>]*\bid="technical-guides".*?</g>)',
        lambda match: match.group(1).replace(ENGRAVING_COLOR, "#ff00ff"),
        template,
        count=1,
        flags=re.DOTALL,
    )
    return outline_private_text(template).encode("utf-8")


def generate_badge_png(user, structure=None):
    """Rend le même badge SVG en PNG transparent à 900 points par pouce."""
    heavy = BASE_DIR / "static" / "fonts" / "LibreFranklin-Bold.ttf"
    book = BASE_DIR / "static" / "fonts" / "LibreFranklin-Regular.ttf"
    svg = generate_badge_svg(user, structure).decode("utf-8")
    return resvg_py.svg_to_bytes(
        svg_string=svg,
        width=1913,
        height=3047,
        dpi=900,
        background=None,
        font_files=[str(heavy), str(book)],
        sans_serif_family="Libre Franklin",
    )


def validate_database_file(path):
    """Vérifie qu'un fichier importé est une base OpenFabLab cohérente."""
    try:
        database = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        integrity = database.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {
            row[0]
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        database.close()
    except sqlite3.Error as error:
        raise ValueError("Le fichier n'est pas une base SQLite valide.") from error
    if integrity != "ok" or not {"users", "sessions", "visitors"}.issubset(tables):
        raise ValueError("La base fournie est incomplète ou endommagée.")


def create_database_safety_copy(database, label):
    """Crée sur le même volume un instantané SQLite cohérent avant une purge."""
    database_path = Path(current_database_path())
    timestamp = datetime.now(PARIS_TIMEZONE).strftime("%Y%m%d-%H%M%S-%f")
    safety_path = database_path.with_name(
        f"{database_path.stem}-{label}-{timestamp}.db"
    )
    destination = sqlite3.connect(safety_path)
    try:
        database.backup(destination)
    finally:
        destination.close()
    validate_database_file(safety_path)
    return safety_path


def record_user_presence(database, user_id, presence_method="manual"):
    """Enregistre l'arrivée ou le départ et retourne le message à afficher."""
    # Seules les valeurs prévues par le modèle de données peuvent être enregistrées.
    if presence_method not in {
        "manual", "id", "qr", "admin", "automatic", "list", "departure"
    }:
        presence_method = "manual"

    # Le verrou évite deux actions simultanées créant deux sessions ouvertes.
    database.execute("BEGIN IMMEDIATE")
    user = database.execute(
        """
        SELECT id, first_name, active, statistics_key, category, birth_year,
               gender, city, city_normalized, postal_code,
               nationality, nationality_normalized
        FROM users WHERE id = ?
        """,
        (user_id,),
    ).fetchone()
    if user is None or not user["active"]:
        database.rollback()
        return None

    open_session = database.execute(
        """
        SELECT id FROM sessions
        WHERE user_id = ? AND check_out IS NULL
        """,
        (user_id,),
    ).fetchone()
    action_time = utc_now_iso()

    if open_session:
        database.execute(
            """
            UPDATE sessions
            SET check_out = ?, exit_method = ?
            WHERE id = ? AND check_out IS NULL
            """,
            (action_time, presence_method, open_session["id"]),
        )
        message = f"À bientôt {user['first_name']}, votre départ a bien été enregistré."
    else:
        database.execute(
            """
            INSERT INTO sessions (
                user_id, check_in, entry_method, statistical_user_key,
                statistical_category, statistical_birth_year, statistical_gender,
                statistical_city, statistical_city_normalized,
                statistical_postal_code, statistical_nationality,
                statistical_nationality_normalized
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, action_time, presence_method, user["statistics_key"],
                user["category"], user["birth_year"], user["gender"],
                user["city"], user["city_normalized"], user["postal_code"],
                user["nationality"], user["nationality_normalized"],
            ),
        )
        message = f"Bonjour {user['first_name']}, votre arrivée a bien été enregistrée."

    database.commit()
    return message


def user_presence_notification_context(database, user_id):
    """Prépare le libellé discret et l'action avant de modifier la session."""
    row = database.execute(
        """
        SELECT users.first_name, users.last_name,
               EXISTS(
                   SELECT 1 FROM sessions
                   WHERE sessions.user_id = users.id AND sessions.check_out IS NULL
               ) AS is_present
        FROM users WHERE users.id = ?
        """,
        (user_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "name": f"{row['first_name']} {row['last_name'][0]}.",
        "event": "departure" if row["is_present"] else "arrival",
    }


def record_quick_departure(database, user_id):
    """Ferme uniquement une présence déjà ouverte depuis l'accueil."""
    database.execute("BEGIN IMMEDIATE")
    user = database.execute(
        "SELECT id, first_name FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if user is None:
        database.rollback()
        return None

    open_session = database.execute(
        "SELECT id FROM sessions WHERE user_id = ? AND check_out IS NULL",
        (user_id,),
    ).fetchone()
    if open_session is None:
        database.rollback()
        return False

    database.execute(
        """
        UPDATE sessions
        SET check_out = ?, exit_method = 'departure'
        WHERE id = ? AND check_out IS NULL
        """,
        (utc_now_iso(), open_session["id"]),
    )
    database.commit()
    return f"À bientôt {user['first_name']}, votre départ a bien été enregistré."


def register_template_helpers(application):
    """Ajoute les petits outils de présentation utilisés par les pages."""

    @application.template_filter("paris_datetime")
    def paris_datetime(value):
        if not value:
            return "—"
        return parse_timestamp(value).astimezone(PARIS_TIMEZONE).strftime(
            "%d/%m/%Y à %H:%M"
        )

    @application.template_filter("duration")
    def duration(check_in, check_out=None):
        start = parse_timestamp(check_in)
        end = parse_timestamp(check_out) if check_out else datetime.now(timezone.utc)
        total_minutes = max(0, int((end - start).total_seconds() // 60))
        if total_minutes == 0:
            return "< 1 min"
        hours, minutes = divmod(total_minutes, 60)
        if hours:
            return f"{hours} h {minutes:02d} min"
        return f"{minutes} min"

    @application.template_filter("last_visit")
    def last_visit(value):
        if not value:
            return "Aucun passage enregistré"
        visit_date = parse_timestamp(value).astimezone(PARIS_TIMEZONE).date()
        today = datetime.now(PARIS_TIMEZONE).date()
        days = max(0, (today - visit_date).days)
        if days == 0:
            return "Aujourd'hui"
        if days == 1:
            return "Hier"
        return f"Il y a {days} jours"

    @application.template_filter("category_label")
    def category_label(value):
        return dynamic_category_label(get_database(), value)

    @application.template_filter("method_label")
    def method_label_filter(value):
        return presence_method_label(value)

    @application.template_filter("audit_json")
    def audit_json_filter(value):
        return humanize_attendance_audit_json(value)

    @application.template_filter("date_fr")
    def date_fr(value):
        if not value:
            return "—"
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return value

    @application.template_filter("duration_seconds")
    def duration_seconds(value):
        total_minutes = max(0, int((value or 0) // 60))
        hours, minutes = divmod(total_minutes, 60)
        if hours:
            return f"{hours} h {minutes:02d} min"
        return f"{minutes} min"

    @application.template_filter("duration_minutes")
    def duration_minutes(value):
        total_minutes = max(0, int(value or 0))
        hours, minutes = divmod(total_minutes, 60)
        if hours:
            return f"{hours} h {minutes:02d} min"
        return f"{minutes} min"

    @application.template_filter("gender_label")
    def gender_label(value):
        return GENDER_LABELS.get(value, "Inconnu")


def register_admin_protection(application):
    """Protège l'administration et limite strictement l'accès modérateur."""

    moderator_endpoints = {
        "admin", "admin_logout", "admin_users_directory", "admin_add_user",
        "admin_user_qr", "admin_user_badge", "admin_statistics",
        "admin_frequency_day", "admin_services", "admin_services_legacy",
        "admin_service_calendar", "admin_service_calendar_legacy",
        "admin_statistics_legacy", "admin_communes_api",
        "admin_moderator_themes",
        "admin_animation_bookings", "admin_animation_bookings_csv", "admin_animation_bookings_pdf",
        "admin_animation_booking_action", "admin_animation_booking_walkin",
        'evolution.calendar', 'evolution.resource_directory', 'evolution.resource_bookings',
        'tablet_reservations.cancel_request',
        'evolution.authorizations', 'evolution.resend_welcome',
    }
    module_endpoints = {
        'resources': {'evolution.resource_directory', 'evolution.resource_bookings'},
        'authorizations': {'evolution.authorizations'},
        "frequency": {
            "admin", "admin_frequency_day", "admin_statistics", "admin_statistics_legacy",
            "admin_frequency_exports", "admin_add_historical_session",
            "admin_add_historical_visitor", "admin_edit_historical_session",
            "admin_delete_historical_session", "admin_delete_historical_visitor",
            "admin_export_users", "admin_export_volunteers", "admin_export_sessions",
            "admin_export_statistics",
        },
        "users": {
            "admin_users_directory", "admin_add_user", "admin_edit_user", "admin_delete_user",
            "admin_user_qr", "admin_user_badge", "admin_communes_api",
            'evolution.resend_welcome', 'family.unlink',
        },
        "activities": {
            "admin_services", "admin_services_legacy", "admin_service_form",
            "admin_service_form_legacy_new", "admin_service_form_legacy_edit",
            "admin_delete_service", "admin_service_calendar", "admin_service_calendar_legacy",
            "admin_export_animations", "admin_export_paid_services",
            "admin_activity_report_form", "admin_activity_report_document",
            'evolution.calendar', 'evolution.resource_directory', 'evolution.resource_bookings', 'evolution.authorizations',
        },
        "public_reservations": {
            "admin_animation_bookings", "admin_animation_bookings_csv", "admin_animation_bookings_pdf",
            "admin_animation_booking_action", "admin_animation_booking_walkin",
            'tablet_reservations.cancel_request',
        },
        "billing": {
            "admin_billing", "admin_billing_calendar", "admin_billing_form",
            "admin_billing_clients_api", "admin_billing_clients_export",
            "admin_billing_client_form", "admin_billing_detail", "admin_billing_sign",
            "admin_billing_create_invoice", "admin_billing_toggle_cancellation",
            "admin_billing_mark_sent", "admin_billing_mark_paid", "admin_billing_reminder",
            "admin_billing_delete", "admin_billing_delete_invoice",
            "admin_billing_document", "admin_billing_facdepot",
        },
    }

    @application.context_processor
    def expose_access_role():
        role = session.get("access_role")
        if role is None and session.get("admin_authenticated"):
            role = "admin"
        database = get_database()
        from runtime_policy import is_test_instance
        return {"admin_access_role": role, 'test_instance': is_test_instance(application.config['DATABASE']),
                "structure": load_structure_settings(database),
                "modules": load_modules(database), 'user_categories': categories(database, True)}

    @application.before_request
    def require_admin_pin():
        if request.endpoint in {"users", "identification", "toggle_presence", "quick_departure"}:
            if not load_modules(get_database())["users"]:
                abort(404)
        if request.endpoint in {"home_state", "add_visitor"}:
            if not load_modules(get_database())["frequency"]:
                abort(404)
        if not request.path.startswith("/admin"):
            return None
        if request.endpoint in {"admin_login", "admin_pin_setup", "admin_pin_recovery"}:
            return None
        if not has_pin(application.config["DATABASE"], "admin"):
            return redirect(url_for("admin_pin_setup"))
        role = session.get("access_role")
        if not role and session.get("admin_authenticated"):
            role = "admin"
            session["access_role"] = role
        if role in {"admin", "moderator"}:
            modules = load_modules(get_database())
            for module, endpoints in module_endpoints.items():
                if request.endpoint not in endpoints or modules[module]:
                    continue
                if request.endpoint == "admin":
                    for fallback_module, fallback_endpoint in (
                        ("users", "admin_users_directory"),
                        ("activities", "admin_services"),
                    ):
                        if modules[fallback_module]:
                            return redirect(url_for(fallback_endpoint))
                    return redirect(url_for("admin_settings_structure" if role == "admin" else "admin_moderator_themes"))
                abort(404)
            if request.endpoint in {
                "admin_billing_form", "admin_billing_calendar", "admin_billing_sign",
                "admin_billing_create_invoice", "admin_billing_toggle_cancellation",
                "admin_billing_mark_sent", "admin_billing_mark_paid",
                "admin_billing_reminder", "admin_billing_delete",
                "admin_billing_delete_invoice",
            } and request.view_args and request.view_args.get("record_id"):
                record_type = get_database().execute(
                    "SELECT billing_type FROM billing_records WHERE id = ?",
                    (request.view_args["record_id"],),
                ).fetchone()
                if record_type and not modules[
                    "rentals" if record_type["billing_type"] == "rental" else "booking_slots"
                ]:
                    abort(404)
        if role == "admin":
            return None
        if role == "moderator":
            if request.endpoint not in moderator_endpoints:
                flash("Cette fonction est réservée au Fabmanager administrateur.", "error")
                return redirect(url_for("admin"))
            return None
        return redirect(url_for("admin_login"))


def register_routes(application):
    """Déclare les pages et les actions de la version actuelle."""

    @application.get("/static/icons/compteur-fablab-<int:size>.png")
    def legacy_pwa_icon(size):
        """Compatibility for old installed shortcuts, without distributing old assets."""
        if size not in (192, 512):
            abort(404)
        return redirect(url_for("static", filename=f"icons/OpenFabLab-icon-{size}.png"))

    @application.get("/manifest.webmanifest")
    def web_app_manifest():
        """Décrit l'application installable en plein écran sur la tablette."""
        application_root = url_for("index")
        structure = load_structure_settings(get_database())
        manifest = {
            "id": application_root,
            "name": f"OpenFabLab · {structure['name']}",
            "short_name": structure["short_name"],
            "description": "Application OpenFabLab de fréquentation et d'activités",
            "lang": "fr",
            "start_url": application_root,
            "scope": application_root,
            "display": "fullscreen",
            "display_override": ["fullscreen", "standalone"],
            "orientation": "landscape",
            "background_color": "#f5f7f6",
            "theme_color": "#ffffff",
            "icons": [
                {"src": url_for("static", filename="icons/OpenFabLab-icon-192.png"), "sizes": "192x192",
                 "type": "image/png", "purpose": "any maskable"},
                {"src": url_for("static", filename="icons/OpenFabLab-icon-512.png"),
                 "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            ],
        }
        return Response(
            json.dumps(manifest, ensure_ascii=False),
            mimetype="application/manifest+json",
            headers={"Cache-Control": "no-cache"},
        )

    @application.get("/service-worker.js")
    def service_worker():
        """Permet au navigateur d'installer l'interface comme application web."""
        script = """
            self.addEventListener("install", () => self.skipWaiting());
            self.addEventListener("activate", (event) => {
                event.waitUntil(self.clients.claim());
            });
        """
        return Response(
            script,
            mimetype="application/javascript",
            headers={
                "Cache-Control": "no-cache",
                "Service-Worker-Allowed": url_for("index"),
            },
        )

    @application.get("/sante")
    def health_check():
        """Permet à Container Manager de vérifier que Flask répond."""
        return Response("OK\n", mimetype="text/plain")

    @application.get("/media/structure/<kind>.png")
    def structure_logo(kind):
        if kind not in {"main", "institution", "wordmark", "header_institution", "network"}:
            abort(404)
        filename = read_setting(get_database(), f"structure_{kind}_logo")
        if filename != f"{kind}.png":
            abort(404)
        path = Path(application.config["DATABASE"]).parent / "branding" / filename
        if not path.is_file() or path.is_symlink():
            abort(404)
        response = send_file(path, mimetype="image/png", max_age=0)
        response.headers['Cache-Control'] = 'no-cache'
        return response

    @application.get("/gestion-des-donnees")
    def data_management():
        """Présente publiquement l'usage et la protection des données."""
        return render_template("data_management.html")

    @application.get("/")
    def index():
        database = get_database()
        if not load_modules(database)["frequency"]:
            return render_template("index_disabled.html")
        present_users = database.execute(
            """
            SELECT users.id, users.first_name, users.last_name, users.category,
                   sessions.check_in
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.check_out IS NULL
            ORDER BY users.first_name COLLATE NOCASE,
                     users.last_name COLLATE NOCASE
            """
        ).fetchall()
        present_count, visitor_count, _sessions_today = get_dashboard_counts(database)
        gauge_value = min(present_count, DISPLAY_CAPACITY)
        if present_count >= DISPLAY_CAPACITY:
            gauge_level = "full"
        elif present_count >= 8:
            gauge_level = "high"
        elif present_count >= 5:
            gauge_level = "medium"
        else:
            gauge_level = "low"
        wake_lock = load_wake_lock_settings(database)
        lock_home_scroll = home_scroll_lock_enabled(database)
        home_theme = load_home_theme(database)
        return render_template(
            "index.html",
            present_users=present_users,
            present_count=present_count,
            visitor_count=visitor_count,
            display_capacity=DISPLAY_CAPACITY,
            gauge_value=gauge_value,
            gauge_percent=round(gauge_value / DISPLAY_CAPACITY * 100),
            gauge_level=gauge_level,
            current_time=datetime.now(PARIS_TIMEZONE),
            weather=get_current_weather(application),
            keep_screen_awake=wake_lock["enabled"],
            wake_lock=wake_lock,
            lock_home_scroll=lock_home_scroll,
            home_theme=home_theme,
            home_state_signature=home_state_signature(database),
        )

    @application.get("/etat-accueil")
    def home_state():
        """Expose une empreinte anonyme pour synchroniser plusieurs écrans."""
        response = jsonify({"signature": home_state_signature(get_database())})
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/usagers")
    def users():
        database = get_database()
        active_users = database.execute(
            """
            SELECT users.id, users.first_name, users.last_name, users.category,
                   MAX(CASE WHEN sessions.check_out IS NULL THEN sessions.id END)
                       AS open_session_id,
                   MAX(sessions.check_in) AS last_check_in
            FROM users
            LEFT JOIN sessions ON sessions.user_id = users.id
            WHERE users.active = 1
            GROUP BY users.id
            ORDER BY open_session_id IS NULL,
                     last_check_in IS NULL,
                     last_check_in DESC,
                     users.first_name COLLATE NOCASE,
                     users.last_name COLLATE NOCASE
            """
        ).fetchall()
        return render_template("users.html", users=active_users)

    @application.route("/identification", methods=["GET", "POST"])
    def identification():
        database = get_database()
        lock_until = current_id_lock(database)
        if request.method == "GET":
            return render_template(
                "identification.html",
                home_theme=load_home_theme(database),
                id_lock_until=lock_until,
                id_lock_minutes=max(1, int((lock_until - datetime.now(timezone.utc)).total_seconds() / 60) + 1) if lock_until else None,
                id_lock_seconds=max(1, int((lock_until - datetime.now(timezone.utc)).total_seconds()) + 1) if lock_until else None,
            )

        public_id = request.form.get("public_id", "").strip()
        presence_method = "qr" if request.form.get("identification_method") == "qr" else "id"
        if presence_method == "id" and lock_until:
            flash("La saisie par identifiant est temporairement indisponible. Utilisez votre QR code ou recherchez votre nom dans la liste.", "error")
            return redirect(url_for("identification"))
        if len(public_id) != 4 or not public_id.isdigit():
            flash("Saisissez votre identifiant à 4 chiffres.", "error")
            return redirect(url_for("identification"))

        user = database.execute(
            """
            SELECT id FROM users
            WHERE public_id = ? AND active = 1
            """,
            (public_id,),
        ).fetchone()
        if user is None:
            if presence_method == "id":
                record_invalid_user_id(database)
            flash(
                "Cet identifiant est inconnu. Vérifiez les 4 chiffres ou utilisez le lien « Je n'ai pas mon badge ou mon identifiant ».",
                "error",
            )
            return redirect(url_for("identification"))

        try:
            notification = user_presence_notification_context(database, user["id"])
            message = record_user_presence(
                database, user["id"], presence_method=presence_method
            )
            if message is None:
                flash("Cet usager n'est pas actif.", "error")
                return redirect(url_for("identification"))
            if notification:
                send_discord_notification(
                    database, notification["event"], notification["name"]
                )
            flash(message, "success")
        except sqlite3.Error:
            database.rollback()
            application.logger.exception(
                "Erreur lors de l'enregistrement par identifiant"
            )
            flash(
                "L'enregistrement n'a pas pu être effectué. Merci de réessayer.",
                "error",
            )
            return redirect(url_for("identification"))

        return redirect(url_for("index"))

    @application.post("/usagers/<int:user_id>/presence")
    def toggle_presence(user_id):
        database = get_database()
        try:
            notification = user_presence_notification_context(database, user_id)
            message = record_user_presence(database, user_id, presence_method="list")
            if message is None:
                abort(404)
            if notification:
                send_discord_notification(
                    database, notification["event"], notification["name"]
                )
            flash(message, "success")
        except sqlite3.Error:
            database.rollback()
            application.logger.exception("Erreur lors de l'enregistrement d'une présence")
            flash(
                "L'enregistrement n'a pas pu être effectué. Merci de réessayer.",
                "error",
            )
            return redirect(url_for("users"))

        return redirect(url_for("index"))

    @application.post("/usagers/<int:user_id>/depart-rapide")
    def quick_departure(user_id):
        """Valide le départ choisi depuis la liste publique des présents."""
        database = get_database()
        try:
            notification = user_presence_notification_context(database, user_id)
            message = record_quick_departure(database, user_id)
            if message is None:
                abort(404)
            if message is False:
                flash("Cette personne n'est plus enregistrée comme présente.", "error")
            else:
                if notification:
                    send_discord_notification(
                        database, "departure", notification["name"]
                    )
                flash(message, "success")
        except sqlite3.Error:
            database.rollback()
            application.logger.exception("Erreur lors du départ rapide")
            flash(
                "Le départ n'a pas pu être enregistré. Merci de réessayer.",
                "error",
            )
        return redirect(url_for("index"))

    @application.post("/visiteurs")
    def add_visitor():
        database = get_database()
        try:
            database.execute(
                "INSERT INTO visitors (created_at) VALUES (?)", (utc_now_iso(),)
            )
            database.commit()
            send_discord_notification(database, "visitor")
            flash(
                f"Bienvenue à {load_structure_settings(database)['name']} ! Votre visite a été comptabilisée.",
                "success",
            )
        except sqlite3.Error:
            database.rollback()
            application.logger.exception("Erreur lors de l'enregistrement d'un visiteur")
            flash(
                "Votre visite n'a pas pu être comptabilisée. Merci de réessayer.",
                "error",
            )
        return redirect(url_for("index"))

    def pin_csrf_token():
        if "pin_csrf" not in session:
            session["pin_csrf"] = secrets.token_urlsafe(24)
        return session["pin_csrf"]

    def pin_csrf_valid():
        return hmac.compare_digest(
            request.form.get("csrf_token", ""), session.get("pin_csrf", "")
        ) and bool(session.get("pin_csrf"))

    from private_backup import register as register_private_backup
    register_private_backup(application, globals(), pin_csrf_valid)

    @application.route("/admin/initialisation", methods=["GET", "POST"])
    def admin_pin_setup():
        if has_pin(application.config["DATABASE"], "admin"):
            return redirect(url_for("admin_login"))
        if request.remote_addr not in {"127.0.0.1", "::1"}:
            abort(403)
        if request.method == "POST":
            new_pin = request.form.get("new_pin", "")
            if not pin_csrf_valid():
                abort(400)
            if not valid_pin(new_pin) or new_pin != request.form.get("confirm_pin"):
                flash("Saisissez et confirmez un PIN de quatre chiffres.", "error")
            else:
                set_pin(application.config["DATABASE"], "admin", new_pin)
                session.pop("pin_csrf", None)
                flash("PIN administrateur initialisé. Vous pouvez vous connecter.", "success")
                return redirect(url_for("admin_login"))
        return render_template("admin_pin_setup.html", csrf_token=pin_csrf_token())

    @application.route("/admin/recuperation", methods=["GET", "POST"])
    def admin_pin_recovery():
        database = get_database()
        token = request.args.get("token", "") if request.method == "GET" else request.form.get("token", "")
        status = token_status(application.config["DATABASE"], token)
        headers = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
        if status != "valid":
            if status == "expired":
                log_security_event(database, "admin_recovery_expired")
                database.commit()
            return render_template("admin_pin_recovery.html", valid=False), 403, headers
        if request.method == "POST":
            if not pin_csrf_valid():
                abort(400)
            attempts = session.get("recovery_attempts", [])
            now = time.time()
            attempts = [stamp for stamp in attempts if now - stamp < 60]
            if len(attempts) >= 5:
                abort(429)
            attempts.append(now)
            session["recovery_attempts"] = attempts
            new_pin = request.form.get("new_pin", "")
            if not valid_pin(new_pin) or new_pin != request.form.get("confirm_pin"):
                flash("Saisissez et confirmez un PIN de quatre chiffres.", "error")
            elif consume_recovery_token(application.config["DATABASE"], token, new_pin) == "valid":
                log_security_event(database, "admin_recovery_success")
                database.commit()
                session.clear()
                flash("PIN administrateur modifié. Connectez-vous avec le nouveau code.", "success")
                return redirect(url_for("admin_login"))
            else:
                return render_template("admin_pin_recovery.html", valid=False), 403, headers
        return render_template("admin_pin_recovery.html", valid=True, token=token,
                               csrf_token=pin_csrf_token()), 200, headers

    @application.route("/admin/connexion", methods=["GET", "POST"])
    def admin_login():
        if not has_pin(application.config["DATABASE"], "admin"):
            return redirect(url_for("admin_pin_setup"))
        if session.get("access_role") or session.get("admin_authenticated"):
            return redirect(url_for("admin"))
        if request.method == "POST":
            if not pin_csrf_valid():
                abort(400)
            submitted_pin = request.form.get("pin", "")
            requested_role = request.form.get("access_role")
            if requested_role not in {"admin", "moderator"}:
                requested_role = "admin"
            database = get_database()
            if check_pin(application.config["DATABASE"], "admin", submitted_pin):
                log_security_event(database, "admin_login_success")
                database.commit()
                session.clear()
                session["admin_authenticated"] = True
                session["access_role"] = "admin"
                return redirect(url_for("admin"))
            if check_pin(application.config["DATABASE"], "moderator", submitted_pin):
                log_security_event(database, "moderator_login_success")
                database.commit()
                session.clear()
                session["admin_authenticated"] = True
                session["access_role"] = "moderator"
                flash("Accès modérateur activé.", "success")
                return redirect(url_for("admin"))
            log_security_event(database, f"{requested_role}_login_failed")
            database.commit()
            return render_template("admin_login.html", csrf_token=pin_csrf_token(), login_error="Le code PIN est incorrect.")
        return render_template("admin_login.html", csrf_token=pin_csrf_token())

    @application.post("/admin/deconnexion")
    def admin_logout():
        session.clear()
        flash("L'administration a été verrouillée.", "success")
        return redirect(url_for("index"))

    @application.get("/admin")
    def admin():
        """Affiche l'aperçu compact de la fréquentation."""
        database = get_database()
        present_count, visitor_count, sessions_today = get_dashboard_counts(database)
        recent_session_rows = database.execute(
            """
            SELECT sessions.check_in, sessions.check_out,
                   sessions.entry_method, sessions.exit_method,
                   COALESCE(users.first_name, 'Ancien') AS first_name,
                   COALESCE(users.last_name, 'usager') AS last_name,
                   sessions.statistical_category AS category
            FROM sessions
            LEFT JOIN users ON users.id = sessions.user_id
            ORDER BY sessions.check_in DESC
            LIMIT 30
            """
        ).fetchall()
        recent_visitor_rows = database.execute(
            "SELECT id, created_at FROM visitors ORDER BY created_at DESC LIMIT 30"
        ).fetchall()
        recent_identifications = [
            {"kind": "session", "at": parse_timestamp(row["check_in"]), "row": row}
            for row in recent_session_rows
        ]
        recent_identifications.extend(
            {
                "kind": "visitor",
                "at": parse_timestamp(row["created_at"]),
                "row": row,
            }
            for row in recent_visitor_rows
        )
        recent_identifications.sort(key=lambda item: item["at"], reverse=True)
        recent_identifications = recent_identifications[:30]
        return render_template(
            "admin.html",
            present_count=present_count,
            visitor_count=visitor_count,
            sessions_today=sessions_today,
            passages_today=sessions_today + visitor_count,
            recent_identifications=recent_identifications,
            today=datetime.now(PARIS_TIMEZONE).strftime("%Y-%m-%d"),
        )

    @application.get("/admin/frequentation/journee")
    def admin_frequency_day():
        """Consulte la fréquentation détaillée d'une date Europe/Paris."""
        database = get_database()
        selected_day = parse_local_day(request.args.get("date"))
        attendance = load_day_attendance(database, selected_day)
        users = database.execute(
            """
            SELECT id, public_id, first_name, last_name, active
            FROM users
            ORDER BY active DESC, last_name COLLATE NOCASE, first_name COLLATE NOCASE
            """
        ).fetchall()
        corrections = []
        if session.get("access_role") == "admin":
            corrections = database.execute(
                """
                SELECT * FROM attendance_corrections
                ORDER BY action_at DESC, id DESC LIMIT 20
                """
            ).fetchall()
        return render_template(
            "frequency_day.html",
            attendance=attendance,
            selected_day=selected_day,
            previous_day=(selected_day - timedelta(days=1)).isoformat(),
            next_day=(selected_day + timedelta(days=1)).isoformat(),
            today=datetime.now(PARIS_TIMEZONE).date().isoformat(),
            users=users,
            corrections=corrections,
        )

    def attendance_day_redirect(value=None):
        selected = parse_local_day(value or request.form.get("date"))
        return redirect(url_for("admin_frequency_day", date=selected.isoformat()))

    @application.post("/admin/frequentation/journee/sessions/ajouter")
    def admin_add_historical_session():
        database = get_database()
        selected_date = request.form.get("date", "")
        try:
            user_id = int(request.form.get("user_id", ""))
        except ValueError:
            user_id = 0
        user = database.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        check_in, check_in_error = parse_admin_local_datetime(
            selected_date, request.form.get("check_in_time"), "L'heure d'arrivée"
        )
        check_out_time = (request.form.get("check_out_time") or "").strip()
        check_out_date = (request.form.get("check_out_date") or selected_date).strip()
        check_out = None
        check_out_error = None
        if check_out_time:
            check_out, check_out_error = parse_admin_local_datetime(
                check_out_date, check_out_time, "L'heure de départ"
            )
        errors = []
        if user is None:
            errors.append("Choisissez un usager valide.")
        if check_in_error:
            errors.append(check_in_error)
        if check_out_error:
            errors.append(check_out_error)
        if check_in and check_out and check_out < check_in:
            errors.append("L'heure de départ ne peut pas précéder l'arrivée.")
        if user and check_in and not errors and session_overlaps(
            database,
            user["id"],
            check_in.isoformat(timespec="seconds"),
            check_out.isoformat(timespec="seconds") if check_out else None,
        ):
            errors.append("Cet usager possède déjà une session sur cette période.")
        if errors:
            for error in errors:
                flash(error, "error")
            return attendance_day_redirect(selected_date)
        try:
            cursor = database.execute(
                """
                INSERT INTO sessions (
                    user_id, check_in, check_out, entry_method, exit_method,
                    statistical_user_key, statistical_category,
                    statistical_birth_year, statistical_gender,
                    statistical_city, statistical_city_normalized,
                    statistical_postal_code, statistical_nationality,
                    statistical_nationality_normalized
                ) VALUES (?, ?, ?, 'admin', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"], check_in.isoformat(timespec="seconds"),
                    check_out.isoformat(timespec="seconds") if check_out else None,
                    "admin" if check_out else None,
                    user["statistics_key"], user["category"], user["birth_year"],
                    user["gender"], user["city"], user["city_normalized"],
                    user["postal_code"], user["nationality"],
                    user["nationality_normalized"],
                ),
            )
            new_row = database.execute(
                "SELECT * FROM sessions WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            record_attendance_correction(
                database, "add", "session", cursor.lastrowid,
                new_values=attendance_record_values(new_row, "session"),
            )
            database.commit()
            flash("La session usager a été ajoutée.", "success")
        except sqlite3.IntegrityError:
            database.rollback()
            flash("Cette session entre en conflit avec une présence ouverte.", "error")
        return attendance_day_redirect(selected_date)

    @application.post("/admin/frequentation/journee/visiteurs/ajouter")
    def admin_add_historical_visitor():
        database = get_database()
        selected_date = request.form.get("date", "")
        created_at, error = parse_admin_local_datetime(
            selected_date, request.form.get("time"), "L'heure du visiteur"
        )
        if error:
            flash(error, "error")
            return attendance_day_redirect(selected_date)
        cursor = database.execute(
            "INSERT INTO visitors (created_at) VALUES (?)",
            (created_at.isoformat(timespec="seconds"),),
        )
        new_row = database.execute(
            "SELECT * FROM visitors WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        record_attendance_correction(
            database, "add", "visitor", cursor.lastrowid,
            new_values=attendance_record_values(new_row, "visitor"),
        )
        database.commit()
        flash("Le visiteur anonyme a été ajouté.", "success")
        return attendance_day_redirect(selected_date)

    @application.post("/admin/frequentation/journee/sessions/<int:session_id>/modifier")
    def admin_edit_historical_session(session_id):
        database = get_database()
        row = database.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            abort(404)
        selected_date = request.form.get("return_date") or request.form.get("date")
        check_in, check_in_error = parse_admin_local_datetime(
            request.form.get("date"), request.form.get("check_in_time"), "L'heure d'arrivée"
        )
        check_out_time = (request.form.get("check_out_time") or "").strip()
        check_out = None
        check_out_error = None
        if check_out_time:
            check_out, check_out_error = parse_admin_local_datetime(
                request.form.get("check_out_date") or request.form.get("date"),
                check_out_time,
                "L'heure de départ",
            )
        errors = [error for error in (check_in_error, check_out_error) if error]
        if check_in and check_out and check_out < check_in:
            errors.append("L'heure de départ ne peut pas précéder l'arrivée.")
        if check_in and not errors and row["user_id"] and session_overlaps(
            database,
            row["user_id"],
            check_in.isoformat(timespec="seconds"),
            check_out.isoformat(timespec="seconds") if check_out else None,
            exclude_id=session_id,
        ):
            errors.append("Cet usager possède déjà une session sur cette période.")
        if errors:
            for error in errors:
                flash(error, "error")
            return attendance_day_redirect(selected_date)
        old_values = attendance_record_values(row, "session")
        database.execute(
            """
            UPDATE sessions
            SET check_in = ?, check_out = ?, exit_method = ?
            WHERE id = ?
            """,
            (
                check_in.isoformat(timespec="seconds"),
                check_out.isoformat(timespec="seconds") if check_out else None,
                (row["exit_method"] or "admin") if check_out else None,
                session_id,
            ),
        )
        new_row = database.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        record_attendance_correction(
            database, "update", "session", session_id, old_values,
            attendance_record_values(new_row, "session"),
        )
        database.commit()
        flash("La session a été corrigée.", "success")
        return attendance_day_redirect(selected_date)

    @application.post("/admin/frequentation/journee/sessions/<int:session_id>/supprimer")
    def admin_delete_historical_session(session_id):
        database = get_database()
        row = database.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            abort(404)
        if request.form.get("confirmation") != "SUPPRIMER":
            flash("La suppression de la session n'a pas été confirmée.", "error")
            return attendance_day_redirect(request.form.get("date"))
        old_values = attendance_record_values(row, "session")
        database.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        record_attendance_correction(
            database, "delete", "session", session_id, old_values=old_values
        )
        database.commit()
        flash("La session a été supprimée.", "success")
        return attendance_day_redirect(request.form.get("date"))

    @application.post("/admin/frequentation/journee/visiteurs/<int:visitor_id>/supprimer")
    def admin_delete_historical_visitor(visitor_id):
        database = get_database()
        row = database.execute("SELECT * FROM visitors WHERE id = ?", (visitor_id,)).fetchone()
        if row is None:
            abort(404)
        if request.form.get("confirmation") != "SUPPRIMER":
            flash("La suppression du visiteur n'a pas été confirmée.", "error")
            return attendance_day_redirect(request.form.get("date"))
        old_values = attendance_record_values(row, "visitor")
        database.execute("DELETE FROM visitors WHERE id = ?", (visitor_id,))
        record_attendance_correction(
            database, "delete", "visitor", visitor_id, old_values=old_values
        )
        database.commit()
        flash("Le visiteur a été supprimé.", "success")
        return attendance_day_redirect(request.form.get("date"))

    @application.get("/admin/usagers")
    def admin_users_directory():
        """Affiche le répertoire consultable et triable des usagers."""
        database = get_database()
        sort_key = request.args.get("tri", "created")
        sort_orders = {
            "created": "users.created_at DESC, users.last_name COLLATE NOCASE",
            "first_name": "users.first_name COLLATE NOCASE, users.last_name COLLATE NOCASE",
            "last_name": "users.last_name COLLATE NOCASE, users.first_name COLLATE NOCASE",
            "public_id": "CAST(users.public_id AS INTEGER), users.last_name COLLATE NOCASE",
            "duration": "total_duration_seconds DESC, users.last_name COLLATE NOCASE",
            "visits": "visit_count DESC, users.last_name COLLATE NOCASE",
        }
        if sort_key not in sort_orders:
            sort_key = "created"
        all_users = database.execute(
            f"""
            SELECT users.id, users.public_id, users.first_name, users.last_name,
                   users.active, users.category, users.created_at, users.created_source, users.created_by_role,
                   COUNT(sessions.id) AS visit_count,
                   COALESCE(SUM(
                       CASE WHEN sessions.check_out IS NOT NULL
                           THEN MAX(0, (JULIANDAY(sessions.check_out) - JULIANDAY(sessions.check_in)) * 86400)
                           ELSE 0 END
                   ), 0) AS total_duration_seconds,
                   MAX(sessions.check_in) AS last_check_in
            FROM users
            LEFT JOIN sessions ON sessions.user_id = users.id
            GROUP BY users.id
            ORDER BY {sort_orders[sort_key]}
            """
        ).fetchall()
        return render_template(
            "admin_users.html", users=all_users, selected_sort=sort_key
        )

    @application.get("/admin/usagers/<int:user_id>/qr.<string:image_format>")
    def admin_user_qr(user_id, image_format):
        """Affiche ou télécharge le QR code d'un usager depuis l'administration."""
        database = get_database()
        user = database.execute(
            "SELECT public_id FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user is None:
            abort(404)
        return qr_code_response(
            user["public_id"],
            image_format.lower(),
            download=request.args.get("telecharger") == "1",
        )

    @application.get("/admin/usagers/<int:user_id>/badge.<string:image_format>")
    def admin_user_badge(user_id, image_format):
        """Télécharge le badge homogène d'un usager en SVG ou PNG."""
        database = get_database()
        user = database.execute(
            """
            SELECT public_id, first_name, last_name, category
            FROM users WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
        if user is None or image_format.lower() not in {"svg", "png"}:
            abort(404)
        image_format = image_format.lower()
        structure = load_structure_settings(database)
        try:
            content = (
                generate_badge_svg(user, structure)
                if image_format == "svg"
                else generate_badge_png(user, structure)
            )
        except (OSError, RuntimeError, ValueError) as error:
            flash('Badge non généré : ' + str(error), 'error')
            return redirect(url_for('admin_users_directory'))
        filename = (
            f"badge-{safe_filename_part(structure['short_name'])}-{user['public_id']}-"
            f"{safe_filename_part(user['first_name'])}.{image_format}"
        )
        return Response(
            content,
            mimetype="image/svg+xml" if image_format == "svg" else "image/png",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.route("/admin/fermeture", methods=["GET", "POST"])
    def admin_closure_settings():
        """Conserve l'ancienne adresse et enregistre le planning dans Options."""
        database = get_database()
        if request.method == "GET":
            return redirect(url_for("admin_settings_kiosk") + "#closure-sessions")
        enabled = request.form.get("enabled") == "1"
        errors = []
        submitted_times = {}
        for weekday, label in WEEKDAYS:
            value = request.form.get(weekday, "").strip()
            if value and not TIME_PATTERN.fullmatch(value):
                errors.append(f"L'heure du {label.lower()} n'est pas valide.")
            submitted_times[weekday] = value
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            write_setting(database, "automatic_closure_enabled", "1" if enabled else "0")
            for weekday, value in submitted_times.items():
                write_setting(database, f"automatic_closure_{weekday}", value)
            database.commit()
            flash("Les horaires de clôture ont été enregistrés.", "success")
        return redirect(url_for("admin_settings_kiosk") + "#closure-sessions")

    @application.post("/admin/fermeture/basculer")
    def admin_toggle_automatic_closure():
        """Met en pause ou réactive la clôture sans perdre les horaires."""
        database = get_database()
        enabled = read_setting(database, "automatic_closure_enabled", "0") != "1"
        write_setting(database, "automatic_closure_enabled", "1" if enabled else "0")
        database.commit()
        flash(
            "La clôture automatique est activée."
            if enabled
            else "La clôture automatique est mise en pause.",
            "success",
        )
        return redirect(url_for("admin_settings_kiosk") + "#closure-sessions")

    @application.post("/admin/fermeture/maintenant")
    def admin_close_all_now():
        """Ferme ponctuellement toutes les sessions ouvertes à l'heure réelle."""
        database = get_database()
        count = close_all_open_sessions(database, "admin")
        flash(
            f"{count} session{'s' if count != 1 else ''} ouverte{'s' if count != 1 else ''} "
            f"{'ont' if count != 1 else 'a'} été clôturée{'s' if count != 1 else ''}."
            if count
            else "Aucune session n'était ouverte.",
            "success",
        )
        return redirect(url_for("admin_settings_kiosk") + "#closure-sessions")

    @application.post("/admin/journee/reinitialiser")
    def admin_reset_today():
        """Efface les essais du jour et retire les présences sans les compter."""
        if request.form.get("confirmation", "").strip() != "EFFACER AUJOURD'HUI":
            flash("Saisissez EFFACER AUJOURD'HUI pour confirmer.", "error")
            return redirect(url_for("admin_settings_kiosk") + "#daily-reset")

        database = get_database()
        day_start, day_end = today_utc_bounds()
        try:
            with DATABASE_MAINTENANCE_LOCK:
                create_database_safety_copy(database, "avant-reset-journee")
                database.execute("BEGIN IMMEDIATE")
                # Les sessions commencées aujourd'hui sont supprimées, même si
                # elles sont encore ouvertes. Une présence plus ancienne est
                # seulement arrêtée à minuit pour préserver les jours antérieurs.
                database.execute(
                    "DELETE FROM sessions WHERE check_in >= ? AND check_in < ?",
                    (day_start, day_end),
                )
                database.execute(
                    """
                    UPDATE sessions
                    SET check_out = ?, exit_method = 'admin'
                    WHERE check_out IS NULL AND check_in < ?
                    """,
                    (day_start, day_start),
                )
                database.execute(
                    "DELETE FROM visitors WHERE created_at >= ? AND created_at < ?",
                    (day_start, day_end),
                )
                database.commit()
            flash(
                "Les présences, visiteurs et statistiques commencés aujourd'hui ont été remis à zéro. "
                "Une copie de sécurité a été conservée sur le NAS.",
                "success",
            )
        except (OSError, ValueError, sqlite3.Error):
            database.rollback()
            application.logger.exception("Échec de la remise à zéro de la journée")
            flash("La journée n'a pas pu être remise à zéro.", "error")
        return redirect(url_for("admin_settings_kiosk") + "#daily-reset")

    @application.route("/admin/themes", methods=["GET", "POST"])
    def admin_moderator_themes():
        """Autorise le modérateur à changer uniquement le thème de la borne."""
        if session.get("access_role") == "admin":
            return redirect(url_for("admin_settings_display"))
        database = get_database()
        if request.method == "POST":
            home_theme = request.form.get("home_theme", "").strip()
            if home_theme not in HOME_THEMES:
                flash("Le thème d’accueil sélectionné n’est pas disponible.", "error")
            else:
                write_setting(database, "home_theme", home_theme)
                database.commit()
                flash("Les options ont été enregistrées.", "success")
            return redirect(url_for("admin_moderator_themes"))
        return render_template(
            "moderator_themes.html",
            home_theme=load_home_theme(database),
            home_themes=HOME_THEMES,
        )

    SETTINGS_ENDPOINTS = {
        "structure": "admin_settings_structure",
        "affichage": "admin_settings_display",
        "borne": "admin_settings_kiosk",
        "tarifs": "admin_settings_tariffs",
        "donnees": "admin_settings_data",
        "reservations": "admin_settings_reservations",
    }

    def render_settings_page(settings_view):
        database = get_database()
        security_events = []
        if settings_view == "borne":
            purge_security_events(database)
            database.commit()
            labels = {
                "invalid_id_alert": "Seuil de tentatives invalides atteint",
                "invalid_id_discord_queued": "Alerte Discord déclenchée",
                "id_lock_started": "Blocage temporaire de la saisie ID activé",
                "admin_login_success": "Connexion Administrateur réussie",
                "moderator_login_success": "Connexion Modérateur réussie",
                "admin_login_failed": "PIN Administrateur incorrect",
                "moderator_login_failed": "PIN Modérateur incorrect",
                "admin_pin_changed": "PIN Administrateur modifié",
                "admin_recovery_requested": "Récupération administrateur demandée",
                "admin_recovery_success": "Récupération administrateur réussie",
                "admin_recovery_expired": "Jeton de récupération expiré",
            }
            rows = database.execute(
                "SELECT event_type, created_at FROM security_events "
                "WHERE event_type != 'invalid_user_id' ORDER BY id DESC LIMIT 10"
            ).fetchall()
            security_events = [{"label": labels.get(row["event_type"], row["event_type"]),
                                "at": parse_timestamp(row["created_at"]).astimezone(PARIS_TIMEZONE)} for row in rows]
        wake_lock = load_wake_lock_settings(database)
        return render_template(
            "database_backup.html",
            settings_view=settings_view,
            keep_screen_awake=wake_lock["enabled"], wake_lock=wake_lock,
            openlab_schedule=load_openlab_schedule(database),
            show_attendance_decimals=(read_setting(database, "openlab_attendance_show_decimals", "0") == "1"),
            calendar_display_start=read_setting(database, 'calendar_display_start', '09:00'),
            calendar_display_end=read_setting(database, 'calendar_display_end', '19:00'),
            smtp=__import__('welcome_mail').load_public_config(current_database_path()),
            home_theme=load_home_theme(database), home_themes=HOME_THEMES,
            lock_home_scroll=home_scroll_lock_enabled(database),
            retention=load_retention_settings(database),
            automatic_backup=load_automatic_backup_settings(database, application),
            closure=load_automatic_closure_settings(database),
            billing_tariffs=load_billing_tariffs(database),
            rental_catalog=load_rental_catalog(database, include_inactive=True),
            custom_tariffs=load_custom_tariffs(database, include_inactive=True),
            moderator_pin_set=has_pin(application.config["DATABASE"], "moderator"),
            pin_csrf_token=pin_csrf_token(),
            structure_settings=load_structure_settings(database),
            profile_preview=(session.get("profile_preview") if
                             session.get("profile_preview", {}).get("expires", 0) > time.time()
                             else None),
            module_settings=load_modules(database),
            module_labels=MODULE_LABELS,
            reservation_settings={
                key: read_setting(database, f"reservation_{key}")
                for key in ("minimum_age", "accompaniment_under_age", "waitlist_enabled",
                            "offer_hours", "last_offer_hours", "close_minutes",
                            "reminder_one_hours", "reminder_two_hours",
                            "sync_interval_minutes", "wordpress_url", "phone_required", "public_url")
            },
            reservation_secret_set=bool(load_sync_secret(application.config["DATABASE"])),
            reservation_sync_states=database.execute(
                "SELECT e.environment, s.last_attempt_at, s.last_success_at, s.last_error_at, s.last_error, "
                "(SELECT COUNT(*) FROM animation_bookings b WHERE b.environment = e.environment) "
                "AS known_bookings, "
                "(SELECT COUNT(*) FROM reservation_outbox o WHERE o.environment = e.environment "
                "AND o.sent_at IS NULL) AS pending_actions "
                ", (SELECT COUNT(*) FROM animation_reservation_config c WHERE c.environment=e.environment) AS known_animations "
                ", (SELECT value FROM app_settings WHERE key='reservation_protocol_' || e.environment) AS protocol "
                ", (SELECT value FROM app_settings WHERE key='reservation_plugin_' || e.environment) AS plugin "
                "FROM (SELECT 'test' AS environment UNION ALL SELECT 'production') e "
                "LEFT JOIN reservation_sync_state s ON s.environment = e.environment "
                "ORDER BY e.environment"
            ).fetchall(),
            id_security=load_id_security_settings(database),
            id_security_status=security_status(database) if settings_view == "borne" else None,
            security_events=security_events,
        )

    def restore_uploaded_database():
        database_path = Path(current_database_path())
        uploaded_file = request.files.get("database_file")
        confirmation = request.form.get("confirmation", "").strip()
        if uploaded_file is None or not uploaded_file.filename:
            flash("Choisissez une sauvegarde SQLite à importer.", "error")
            return redirect(url_for("admin_settings_data"))
        if confirmation != "RESTAURER":
            flash("Saisissez RESTAURER pour confirmer le remplacement.", "error")
            return redirect(url_for("admin_settings_data"))
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temporary:
                uploaded_file.save(temporary)
                temporary_path = Path(temporary.name)
            validate_database_file(temporary_path)
            timestamp = datetime.now(PARIS_TIMEZONE).strftime("%Y%m%d-%H%M%S")
            safety_copy = database_path.with_name(f"openfablab-avant-restauration-{timestamp}.db")
            with DATABASE_MAINTENANCE_LOCK:
                close_database()
                if database_path.exists():
                    shutil.copy2(database_path, safety_copy)
                os.replace(temporary_path, database_path)
                temporary_path = None
                initialize_database()
            flash("La sauvegarde a été restaurée. Une copie de sécurité de l'état précédent a été conservée.", "success")
        except (OSError, ValueError, sqlite3.Error) as error:
            application.logger.warning("Import de base refusé : %s", error)
            flash(str(error), "error")
        finally:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()
        return redirect(url_for("admin_settings_data"))

    @application.route("/admin/reglages", methods=["GET", "POST"])
    def admin_database_backup():
        if request.method == "POST":
            return restore_uploaded_database()
        return redirect(url_for("admin_settings_display"))

    @application.get("/admin/reglages/affichage")
    def admin_settings_display():
        return render_settings_page("affichage")

    @application.route("/admin/reglages/reservations", methods=["GET", "POST"])
    def admin_settings_reservations():
        return redirect(url_for("admin_settings_structure") + "#reservations")

    @application.post("/admin/reglages/structure/reservations")
    def admin_save_reservation_settings():
        if not pin_csrf_valid():
            abort(400)
        database = get_database()
        limits = {
            "minimum_age": (0, 120), "accompaniment_under_age": (0, 120),
            "offer_hours": (1, 168), "last_offer_hours": (1, 168),
            "close_minutes": (0, 1440), "reminder_one_hours": (0, 168),
            "reminder_two_hours": (0, 168),
        }
        values = {}
        errors = []
        interval_text = request.form.get('sync_interval_minutes', '').replace(',', '.')
        try:
            interval = Decimal(interval_text)
            if not interval.is_finite() or not 1 <= interval <= 60 or interval * 2 != (interval * 2).to_integral_value():
                raise ValueError
            values['sync_interval_minutes'] = format(interval.normalize(), 'f')
        except (ValueError, InvalidOperation):
            errors.append('La synchronisation doit être comprise entre 1 et 60 minutes, par pas de 30 secondes.')
        for key, (minimum, maximum) in limits.items():
            try:
                value = int(request.form.get(key, read_setting(database,f'reservation_{key}')))
                if not minimum <= value <= maximum:
                    raise ValueError
                values[key] = value
            except ValueError:
                errors.append(f"La valeur {key} doit être comprise entre {minimum} et {maximum}.")
        url = request.form.get("wordpress_url", "").strip().rstrip("/")
        if url and (not url.startswith("https://") or urllib.parse.urlparse(url).username
                    or not urllib.parse.urlparse(url).hostname):
            errors.append("L'adresse WordPress doit être une URL HTTPS valide.")
        secret = request.form.get("sync_secret", "").strip()
        public_url=request.form.get('public_url',read_setting(database,'reservation_public_url','')).strip().rstrip('/')
        parsed=urllib.parse.urlsplit(public_url)
        if public_url and (parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment):
            errors.append('L’adresse publique OpenFabLab doit être une URL HTTPS valide, sans mot de passe ni paramètres.')
        if secret and (len(secret) < 40 or not re.fullmatch(r"[A-Za-z0-9_-]+", secret)):
            errors.append("Le secret WordPress est invalide.")
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            for key, value in values.items():
                write_setting(database, f"reservation_{key}", value)
            write_setting(database, "reservation_waitlist_enabled",
                          "1" if request.form.get("waitlist_enabled") == "1" else "0")
            write_setting(database, "reservation_wordpress_url", url)
            write_setting(database,'reservation_public_url',public_url)
            write_setting(database,'reservation_phone_required','1' if request.form.get('phone_required')=='1' else '0')
            if secret:
                save_sync_secret(application.config["DATABASE"], secret)
            for row in database.execute(
                "SELECT service_id FROM animation_reservation_config"
            ).fetchall():
                enqueue_animation(database, row["service_id"])
            database.commit()
            flash("Réglages de réservation enregistrés.", "success")
        return redirect(url_for("admin_settings_structure") + "#reservations")

    @application.post("/admin/reglages/structure/synchroniser")
    def admin_sync_reservations_now():
        if not pin_csrf_valid():
            abort(400)
        database = get_database()
        if not load_modules(database)["public_reservations"]:
            flash("Synchronisation impossible : module Réservations publiques désactivé.", "error")
        else:
            site_url = read_setting(database, "reservation_wordpress_url")
            if not site_url or not load_sync_secret(application.config["DATABASE"]):
                flash("Synchronisation impossible : connexion WordPress incomplète.", "error")
            else:
                try:
                    with RESERVATION_SYNC_LOCK:
                        result = run_sync_cycle(database, application.config["DATABASE"], site_url)
                    notify_sync_events(database, result)
                    if result.get("errors"):
                        reasons = "; ".join(("Test" if item["environment"] == "test" else "Normal")
                                            + " : " + item["error"] for item in result["errors"])
                        flash(f"Synchronisation impossible : {reasons}.", "error")
                    else:
                        flash("Synchronisation réussie (Normal et Test).", "success")
                except (OSError, ValueError, sqlite3.Error, urllib.error.URLError) as error:
                    database.rollback()
                    reason = sync_error_label(error)
                    for environment in ("test", "production"):
                        database.execute(
                            "INSERT INTO reservation_sync_state(environment, cursor, last_error_at, last_error) "
                            "VALUES (?, '', ?, ?) ON CONFLICT(environment) DO UPDATE SET "
                            "last_error_at=excluded.last_error_at, last_error=excluded.last_error",
                            (environment, utc_now_iso(), reason),
                        )
                    database.commit()
                    flash(f"Synchronisation impossible : {reason}.", "error")
        return redirect(url_for("admin_settings_structure") + "#reservations")

    @application.post("/admin/reglages/structure/logo-openfablab")
    def admin_reset_structure_wordmark():
        if not pin_csrf_valid():
            abort(400)
        database = get_database()
        write_setting(database, "structure_wordmark_logo", "")
        database.commit()
        flash("Le logo OpenFabLab est de nouveau affiché dans l’en-tête.", "success")
        return redirect(url_for("admin_settings_structure"))

    @application.route("/admin/reglages/structure", methods=["GET", "POST"])
    def admin_settings_structure():
        if request.method == "GET":
            return render_settings_page("structure")
        if not pin_csrf_valid():
            abort(400)
        database = get_database()
        database.execute('BEGIN IMMEDIATE')
        values = {key: request.form.get(key, read_setting(database, 'structure_' + key))
                  for key in STRUCTURE_FIELDS}
        values = {key: value if key == 'dpo' else value.strip() for key, value in values.items()}
        errors = []
        for key, (label, maximum) in STRUCTURE_FIELDS.items():
            if not values[key] and key in {"name", "short_name", "timezone"}:
                errors.append(f"{label} est obligatoire.")
            if len(values[key]) > maximum:
                errors.append(f"{label} est trop long.")
        if values["email"] and not EMAIL_PATTERN.fullmatch(values["email"]):
            errors.append("L'adresse e-mail n'est pas valide.")
        if values['dpo_email'] and not EMAIL_PATTERN.fullmatch(values['dpo_email']):
            errors.append("L'adresse e-mail du DPO n'est pas valide.")
        if values["website"] and not re.fullmatch(r"https?://[^\s/]+[^\s]*", values["website"]):
            errors.append("Le site web doit commencer par http:// ou https://.")
        if values["privacy_policy_url"]:
            parsed = urllib.parse.urlparse(values["privacy_policy_url"])
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                errors.append("La page de gestion des données doit utiliser une URL HTTP(S) valide.")
        if values["color"] and not re.fullmatch(r"#[0-9a-fA-F]{6}", values["color"]):
            errors.append("La couleur doit utiliser le format #RRGGBB.")
        if bool(values["latitude"]) != bool(values["longitude"]):
            errors.append("Renseignez la latitude et la longitude ensemble.")
        for coordinate, minimum, maximum in (("latitude", -90, 90), ("longitude", -180, 180)):
            if values[coordinate]:
                try:
                    number = Decimal(values[coordinate])
                    if not number.is_finite() or not minimum <= number <= maximum:
                        raise ValueError
                except (InvalidOperation, ValueError):
                    errors.append(f"{STRUCTURE_FIELDS[coordinate][0]} invalide.")
        if values["siret"] and not re.fullmatch(r"[0-9]{14}", values["siret"]):
            errors.append("Le SIRET doit contenir 14 chiffres.")
        if values["iban"] and not re.fullmatch(r"[A-Za-z]{2}[0-9A-Za-z ]{13,58}", values["iban"]):
            errors.append("L'IBAN n'est pas valide.")
        if values["bic"] and not re.fullmatch(r"[A-Za-z0-9]{8}([A-Za-z0-9]{3})?", values["bic"]):
            errors.append("Le BIC doit contenir 8 ou 11 caractères.")
        if values["payment_days"] and (not values["payment_days"].isdigit() or
                                       not 1 <= int(values["payment_days"]) <= 365):
            errors.append("Le délai de règlement doit être compris entre 1 et 365 jours.")
        try:
            ZoneInfo(values["timezone"])
        except (KeyError, ValueError):
            errors.append("Le fuseau horaire n'est pas reconnu.")
        privacy_only = request.form.get('privacy_only') == '1'
        selected = load_modules(database) if privacy_only else {
            key: request.form.get(f"module_{key}") == "1" for key in MODULE_LABELS}
        if not selected['authorizations']:
            dependent = database.execute('SELECT name FROM resources WHERE active=1 AND required_authorization IS NOT NULL').fetchall()
            if dependent:
                errors.append('Impossible de désactiver Formations et habilitations : ressources actives dépendantes : '
                              + ', '.join(row['name'] for row in dependent) + '. Retirez explicitement leurs exigences ou désactivez ces ressources.')
        if selected["public_reservations"] and not selected["activities"]:
            errors.append("Les réservations publiques nécessitent le module Activités.")
        if (selected["booking_slots"] or selected["rentals"]) and not selected["billing"]:
            errors.append("Les créneaux réservables et locations nécessitent le module Facturation.")
        logo_files = {}
        for kind in LOGO_KINDS:
            uploaded = request.files.get(f"logo_{kind}")
            if uploaded and uploaded.filename:
                raw = uploaded.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    errors.append("Chaque logo doit faire moins de 2 Mo.")
                    continue
                try:
                    with Image.open(io.BytesIO(raw)) as logo:
                        if logo.width * logo.height > 20_000_000 or logo.format not in {"PNG", "JPEG", "WEBP"}:
                            raise ValueError
                        logo.load()
                except (UnidentifiedImageError, OSError, ValueError):
                    errors.append("Logo invalide : utilisez une image PNG, JPEG ou WebP.")
                    continue
                logo_files[kind] = raw
        badge_raw = None
        uploaded = request.files.get('badge_template')
        if uploaded and uploaded.filename:
            badge_raw = uploaded.read(2 * 1024 * 1024 + 1)
            try:
                validate_badge_template(badge_raw)
            except ValueError as error:
                errors.append(str(error))
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            privacy_url_changed = values["privacy_policy_url"] != read_setting(
                database, "structure_privacy_policy_url", ""
            )
            if logo_files:
                branding_dir = Path(application.config["DATABASE"]).parent / "branding"
                branding_dir.mkdir(parents=True, exist_ok=True)
                for kind, raw in logo_files.items():
                    temporary_logo = branding_dir / f".{kind}-{secrets.token_hex(5)}.tmp"
                    try:
                        with Image.open(io.BytesIO(raw)) as logo:
                            logo.convert("RGBA" if "A" in logo.getbands() else "RGB").save(temporary_logo, "PNG")
                        os.replace(temporary_logo, branding_dir / f"{kind}.png")
                    finally:
                        temporary_logo.unlink(missing_ok=True)
                    write_setting(database, f"structure_{kind}_logo" if kind != "signature" else "structure_signature", f"{kind}.png")
                    os.chmod(branding_dir / f'{kind}.png', 0o600)
            if badge_raw is not None:
                branding_dir = Path(application.config['DATABASE']).parent / 'branding'
                branding_dir.mkdir(parents=True, exist_ok=True)
                temporary = branding_dir / ('.badge-' + secrets.token_hex(5) + '.tmp')
                try:
                    temporary.write_bytes(badge_raw)
                    os.chmod(temporary, 0o600)
                    os.replace(temporary, branding_dir / BADGE_FILENAME)
                finally:
                    temporary.unlink(missing_ok=True)
                write_setting(database, 'structure_badge_template', BADGE_FILENAME)
            if request.form.get('branding_visibility_form') == '1':
                for key in VISIBILITY_KEYS:
                    write_setting(database, 'structure_' + key, '1' if request.form.get(key) == '1' else '0')
            if request.form.get('branding_resources_form') == '1':
                for key in RESOURCE_USAGE_KEYS:
                    write_setting(database, 'structure_' + key, '1' if request.form.get(key) == '1' else '0')
            for key, value in values.items():
                write_setting(database, f"structure_{key}", value)
            for key, enabled in selected.items():
                write_setting(database, f"module_{key}", "1" if enabled else "0")
            if privacy_url_changed and selected["public_reservations"]:
                for row in database.execute(
                    "SELECT service_id FROM animation_reservation_config"
                ).fetchall():
                    enqueue_animation(database, row["service_id"])
            database.commit()
            flash("Structure et modules enregistrés sans supprimer de données.", "success")
        return redirect(url_for("admin_settings_data" if privacy_only else "admin_settings_structure"))

    @application.post('/admin/reglages/structure/supprimer/<kind>')
    def admin_remove_branding(kind):
        if not pin_csrf_valid() or request.form.get('confirmation') != 'SUPPRIMER':
            abort(400)
        if kind not in LOGO_KINDS and kind != 'badge':
            abort(404)
        database = get_database()
        filename = BADGE_FILENAME if kind == 'badge' else kind + '.png'
        key = ('structure_badge_template' if kind == 'badge' else
               'structure_signature' if kind == 'signature' else 'structure_' + kind + '_logo')
        # Preserve the removed file for recovery; only deactivate the setting.
        # Re-upload explicitly replaces the same dedicated persistent filename.
        write_setting(database, key, '')
        database.commit()
        flash('Ressource personnalisée retirée. Les autres usages restent inchangés.', 'success')
        return redirect(url_for('admin_settings_structure'))

    @application.get('/admin/reglages/structure/badge-apercu.png')
    def admin_badge_preview():
        try:
            raw = generate_badge_png({'public_id': '2001', 'first_name': 'Alex', 'category': 'user'},
                                     load_structure_settings(get_database()))
        except (OSError, ValueError, RuntimeError) as error:
            return Response('Badge non généré : ' + str(error), status=422, mimetype='text/plain')
        return Response(raw, mimetype='image/png', headers={'Cache-Control': 'private, no-store'})

    @application.get('/admin/reglages/structure/ressource/<kind>.png')
    def admin_resource_preview(kind):
        """Preview document resources without exposing a signature publicly."""
        if kind not in {'main', 'signature'}:
            abort(404)
        key = 'structure_signature' if kind == 'signature' else 'structure_main_logo'
        filename = read_setting(get_database(), key)
        if filename != kind + '.png':
            abort(404)
        path = Path(application.config['DATABASE']).parent / 'branding' / filename
        if not path.is_file() or path.is_symlink():
            abort(404)
        response = send_file(path, mimetype='image/png', max_age=0)
        response.headers['Cache-Control'] = 'private, no-store'
        return response

    @application.get("/admin/profil/exporter")
    def admin_export_profile():
        """Export only explicitly approved configuration keys and visual resources."""
        database = get_database()
        settings = {row["key"]: row["value"] for row in database.execute(
            "SELECT key, value FROM app_settings"
        ).fetchall()}
        machines = [{key: row[key] for key in (
            "machine_key", "name", "monthly_cents", "deposit_cents",
            "active", "archived", "sort_order")}
            for row in database.execute("SELECT * FROM rental_catalog ORDER BY sort_order, name")]
        tariffs = [{key: row[key] for key in (
            "tariff_key", "name", "unit", "cents", "active", "archived", "sort_order")}
            for row in database.execute("SELECT * FROM billing_tariff_catalog ORDER BY sort_order, name")]
        assets = {}
        branding = Path(application.config["DATABASE"]).parent / "branding"
        for kind in LOGO_KINDS:
            local = branding / f"{kind}.png"
            setting = read_setting(database, f"structure_{kind}_logo" if kind != "signature" else "structure_signature")
            source = local if setting == f"{kind}.png" and local.is_file() else None
            if source and source.is_file():
                with Image.open(source) as picture:
                    if picture.width * picture.height > 20_000_000:
                        raise ValueError("Ressource visuelle trop grande.")
                    output = io.BytesIO()
                    picture.convert("RGBA" if "A" in picture.getbands() else "RGB").save(output, "PNG")
                    assets[f"assets/{kind}.png"] = output.getvalue()
        if settings.get('structure_badge_template'):
            raw = (branding / BADGE_FILENAME).read_bytes()
            validate_badge_template(raw)
            assets['assets/' + BADGE_FILENAME] = raw
        registry = [{k:r[k] for k in ('category_key','name','color','active','sort_order','is_default')} for r in categories(database,True)]
        types = [{k:r[k] for k in ('type_key','name','color','active','sort_order')} for r in database.execute('SELECT * FROM resource_types')]
        profile = build_profile(settings, machines, assets, tariffs, registry, types)
        name = compact_filename_part(read_setting(database, "structure_short_name", "OpenFabLab"), "OpenFabLab")[:60]
        return Response(profile, mimetype="application/zip", headers={
            "Content-Disposition": f'attachment; filename="{name}.openfablab-profile.zip"',
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        })

    @application.post("/admin/profil/importer")
    def admin_import_profile():
        """Two-step same-file confirmation; never import business records or credentials."""
        if not pin_csrf_valid():
            abort(400)
        upload = request.files.get("profile_file")
        if not upload or not upload.filename:
            flash("Choisissez un profil ZIP à importer.", "error")
            return redirect(url_for("admin_settings_structure"))
        raw = upload.read(MAX_ARCHIVE_BYTES + 1)
        try:
            profile = parse_profile(raw)
            for kind, content in profile["assets"].items():
                if kind == 'assets/' + BADGE_FILENAME:
                    validate_badge_template(content)
                    continue
                with Image.open(io.BytesIO(content)) as picture:
                    if (picture.format != "PNG" or picture.width * picture.height > 20_000_000):
                        raise ValueError("Image du profil invalide.")
                    picture.verify()
            if request.form.get("step") == "preview":
                session["profile_preview"] = {
                    "digest": hashlib.sha256(raw).hexdigest(), "expires": time.time() + 900,
                    "name": profile["settings"].get("structure_name", "FabLab"),
                    "settings": len(profile["settings"]),
                    "machines": len(profile["machines"]),
                    "tariffs": len(profile["tariffs"]),
                    "assets": len(profile["assets"]),
                }
                flash("Profil vérifié. Relisez le résumé et confirmez avec le même fichier.", "success")
            elif request.form.get("step") == "apply":
                preview = session.pop("profile_preview", None)
                if (not preview or preview["expires"] <= time.time() or
                        not hmac.compare_digest(preview["digest"], hashlib.sha256(raw).hexdigest()) or
                        request.form.get("confirmation") != "IMPORTER LE PROFIL"):
                    raise ValueError("Confirmation expirée ou fichier différent : prévisualisez à nouveau le profil.")
                database = get_database()
                timestamp = utc_now_iso()
                with database:
                    if profile['categories']:
                        database.execute('UPDATE user_categories SET is_default=0')
                        for entry in profile['categories']:
                            database.execute('INSERT INTO user_categories VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(category_key) DO UPDATE SET name=excluded.name,normalized_name=excluded.normalized_name,color=excluded.color,active=excluded.active,sort_order=excluded.sort_order,is_default=excluded.is_default,updated_at=excluded.updated_at',
                                (entry['category_key'],entry['name'],entry['name'].strip().casefold(),entry['color'],entry['active'],entry['sort_order'],entry['is_default'],timestamp,timestamp))
                    for entry in profile['resource_types']:
                        database.execute('INSERT INTO resource_types VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(type_key) DO UPDATE SET name=excluded.name,normalized_name=excluded.normalized_name,color=excluded.color,active=excluded.active,sort_order=excluded.sort_order,updated_at=excluded.updated_at',
                            (entry['type_key'],entry['name'],entry['name'].strip().casefold(),entry['color'],entry['active'],entry['sort_order'],timestamp,timestamp))
                    # Imported ranks may overlap retained entries: keep a total, gap-free order.
                    from evolution_schema import reorder
                    reorder(database, 'categories')
                    reorder(database, 'resource_types')
                    for key, value in profile["settings"].items():
                        write_setting(database, key, value)
                    if not load_modules(database)['authorizations'] and database.execute(
                            'SELECT 1 FROM resources WHERE active=1 AND required_authorization IS NOT NULL LIMIT 1').fetchone():
                        raise ValueError('Ce profil désactiverait une habilitation requise par une ressource active ; import refusé.')
                    for machine in profile["machines"]:
                        database.execute(
                            "INSERT INTO rental_catalog (machine_key, name, monthly_cents, deposit_cents, active, archived, sort_order, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                            "ON CONFLICT(machine_key) DO UPDATE SET name=excluded.name, monthly_cents=excluded.monthly_cents, "
                            "deposit_cents=excluded.deposit_cents, active=excluded.active, archived=excluded.archived, "
                            "sort_order=excluded.sort_order, updated_at=excluded.updated_at",
                            (machine["machine_key"], machine["name"], machine["monthly_cents"],
                             machine["deposit_cents"], machine["active"], machine["archived"],
                             machine["sort_order"], timestamp, timestamp),
                        )
                    for tariff in profile["tariffs"]:
                        database.execute(
                            "INSERT INTO billing_tariff_catalog (tariff_key, name, unit, cents, active, archived, sort_order, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                            "ON CONFLICT(tariff_key) DO UPDATE SET name=excluded.name, unit=excluded.unit, "
                            "cents=excluded.cents, active=excluded.active, archived=excluded.archived, "
                            "sort_order=excluded.sort_order, updated_at=excluded.updated_at",
                            (tariff["tariff_key"], tariff["name"], tariff["unit"], tariff["cents"],
                             tariff["active"], tariff["archived"], tariff["sort_order"], timestamp, timestamp),
                        )
                    # A transferred profile must never silently reactivate a previous WP endpoint.
                    write_setting(database, "reservation_wordpress_url", "")
                    write_setting(database, "discord_notifications_enabled", "0")
                    branding = Path(application.config["DATABASE"]).parent / "branding"
                    branding.mkdir(parents=True, exist_ok=True)
                    for path, content in profile["assets"].items():
                        kind = Path(path).stem
                        temporary = branding / f".{kind}-{secrets.token_hex(5)}.tmp"
                        try:
                            temporary.write_bytes(content)
                            os.chmod(temporary, 0o600)
                            os.replace(temporary, branding / Path(path).name)
                        finally:
                            temporary.unlink(missing_ok=True)
                        key = ('structure_badge_template' if kind == 'badge-template' else
                               'structure_signature' if kind == 'signature' else f'structure_{kind}_logo')
                        write_setting(database, key, Path(path).name)
                sync_secret_path(application.config["DATABASE"]).unlink(missing_ok=True)
                Path(application.config["DISCORD_WEBHOOK_FILE"]).unlink(missing_ok=True)
                flash("Profil importé. Données métier conservées ; reconfigurez WordPress et Discord.", "success")
            else:
                abort(400)
        except (ValueError, OSError, sqlite3.Error) as error:
            flash(str(error), "error")
        return redirect(url_for("admin_settings_structure"))

    @application.get("/admin/reglages/borne")
    def admin_settings_kiosk():
        return render_settings_page("borne")

    @application.get("/admin/reglages/tarifs")
    def admin_settings_tariffs():
        return render_settings_page("tarifs")

    @application.route("/admin/reglages/donnees", methods=["GET", "POST"])
    def admin_settings_data():
        if request.method == "POST":
            return restore_uploaded_database()
        return render_settings_page("donnees")

    @application.route("/admin/sauvegarde", methods=["GET", "POST"])
    def admin_database_backup_legacy():
        if request.method == "POST":
            return restore_uploaded_database()
        return redirect(url_for("admin_settings_data"))

    @application.post("/admin/options")
    @application.post("/admin/reglages/<string:settings_view>/enregistrer")
    def admin_update_options(settings_view="legacy"):
        """Enregistre uniquement les options ordinaires de la vue concernée."""
        if settings_view not in {*SETTINGS_ENDPOINTS, "legacy"}:
            abort(404)
        database = get_database()
        errors = []
        previous_backup = load_automatic_backup_settings(database, application)
        previous_schedule = {day["key"]: day for day in load_openlab_schedule(database)}

        if settings_view in {"affichage", "legacy"}:
            home_theme = request.form.get("home_theme", load_home_theme(database)).strip()
            if home_theme not in HOME_THEMES:
                errors.append("Le thème d’accueil sélectionné n’est pas disponible.")
            calendar_start = request.form.get('calendar_display_start', read_setting(database, 'calendar_display_start', '09:00'))
            calendar_end = request.form.get('calendar_display_end', read_setting(database, 'calendar_display_end', '19:00'))
            if not TIME_PATTERN.fullmatch(calendar_start) or not TIME_PATTERN.fullmatch(calendar_end) or calendar_end <= calendar_start:
                errors.append('La fin de la plage affichée du calendrier doit suivre son début (HH:MM).')

        if settings_view in {"borne", "legacy"}:
            security_values = {}
            for field, setting_key, default, minimum, maximum, label in (
                ("invalid_id_threshold", "invalid_id_threshold", 5, 2, 50, "Le seuil de sécurité"),
                ("invalid_id_window_minutes", "invalid_id_window_minutes", 5, 1, 60, "La fenêtre de détection"),
                ("invalid_id_lock_minutes", "invalid_id_lock_minutes", 10, 1, 120, "La durée du blocage"),
            ):
                try:
                    value = int(request.form.get(field, read_setting(database, setting_key, str(default))))
                    if not minimum <= value <= maximum:
                        raise ValueError
                    security_values[setting_key] = value
                except (TypeError, ValueError):
                    errors.append(f"{label} doit être compris entre {minimum} et {maximum}.")
            wake_lock_start = request.form.get("wake_lock_start", read_setting(database, "wake_lock_start", "09:00")).strip()
            wake_lock_end = request.form.get("wake_lock_end", read_setting(database, "wake_lock_end", "17:00")).strip()
            if not TIME_PATTERN.fullmatch(wake_lock_start):
                errors.append("L'heure de début de maintien de l'écran est invalide.")
            if not TIME_PATTERN.fullmatch(wake_lock_end):
                errors.append("L'heure de fin de maintien de l'écran est invalide.")
            openlab_schedule_values = {}
            for weekday_key, weekday_label in WEEKDAYS:
                previous_day = previous_schedule[weekday_key]
                start = request.form.get(f"openlab_attendance_{weekday_key}_start", previous_day["start"]).strip()
                end = request.form.get(f"openlab_attendance_{weekday_key}_end", previous_day["end"]).strip()
                openlab_schedule_values[weekday_key] = (start, end)
                if not start and not end:
                    continue
                if not start or not end:
                    errors.append(f"Renseignez les deux heures de l'OpenLab du {weekday_label.lower()}, ou laissez-les toutes les deux vides.")
                    continue
                if not TIME_PATTERN.fullmatch(start) or not TIME_PATTERN.fullmatch(end):
                    errors.append(f"Les horaires de l'OpenLab du {weekday_label.lower()} sont invalides.")
                    continue
                start_hour, start_minute = map(int, start.split(":"))
                end_hour, end_minute = map(int, end.split(":"))
                if start_minute % 15 or end_minute % 15:
                    errors.append(f"Les horaires de l'OpenLab du {weekday_label.lower()} doivent utiliser des quarts d'heure complets.")
                if end_hour * 60 + end_minute <= start_hour * 60 + start_minute:
                    errors.append(f"L'heure de fin de l'OpenLab du {weekday_label.lower()} doit suivre l'heure de début.")

        if settings_view in {"donnees", "legacy"}:
            retention_values = {}
            current_retention = load_retention_settings(database)
            for field, label in (("contact_years", "coordonnées sensibles"), ("deactivation_years", "désactivation du compte"), ("deletion_years", "suppression du compte")):
                fallback = current_retention.get(field, "")
                raw_value = str(
                    request.form.get(field, fallback if fallback is not None else "")
                ).strip()
                try:
                    value = int(raw_value)
                    if value < 0 or value > 50:
                        raise ValueError
                    retention_values[field] = value
                except ValueError:
                    errors.append(f"La durée de {label} doit être comprise entre 0 et 50 ans.")
            ordered_values = [value for value in retention_values.values() if value > 0]
            if ordered_values != sorted(ordered_values):
                errors.append("Les durées actives doivent suivre l'ordre : coordonnées, désactivation, suppression.")
            try:
                backup_interval_days = int(request.form.get("automatic_backup_interval_days", str(previous_backup["interval_days"])).strip())
                if backup_interval_days < 1 or backup_interval_days > 365:
                    raise ValueError
            except ValueError:
                backup_interval_days = 1
                errors.append("La fréquence de sauvegarde doit être comprise entre 1 et 365 jours.")
            try:
                backup_subdirectory = normalize_backup_subdirectory(request.form.get("automatic_backup_subdirectory", previous_backup["subdirectory"]))
            except ValueError as error:
                backup_subdirectory = previous_backup["subdirectory"]
                errors.append(str(error))

        target_view = "affichage" if settings_view == "legacy" else settings_view
        target_url = url_for(SETTINGS_ENDPOINTS[target_view])
        if errors:
            for error in errors:
                flash(error, "error")
            return redirect(target_url)

        if settings_view in {"affichage", "legacy"}:
            write_setting(database, "home_theme", home_theme)
            write_setting(database, 'calendar_display_start', calendar_start)
            write_setting(database, 'calendar_display_end', calendar_end)
            write_setting(database, "openlab_attendance_show_decimals", "1" if request.form.get("openlab_attendance_show_decimals") == "1" else "0")
        if settings_view in {"borne", "legacy"}:
            for setting_key, value in security_values.items():
                write_setting(database, setting_key, value)
            write_setting(database, "invalid_id_lock_enabled", "1" if request.form.get("invalid_id_lock_enabled") == "1" else "0")
            write_setting(database, "keep_screen_awake", "1" if request.form.get("keep_screen_awake") == "1" else "0")
            write_setting(database, "lock_home_scroll", "1" if request.form.get("lock_home_scroll") == "1" else "0")
            write_setting(database, "wake_lock_start", wake_lock_start)
            write_setting(database, "wake_lock_end", wake_lock_end)
            for weekday_key, (start, end) in openlab_schedule_values.items():
                write_setting(database, f"openlab_attendance_{weekday_key}_start", start)
                write_setting(database, f"openlab_attendance_{weekday_key}_end", end)
        if settings_view in {"donnees", "legacy"}:
            write_setting(database, "retention_contact_years", retention_values["contact_years"])
            write_setting(database, "retention_deactivation_years", retention_values["deactivation_years"])
            write_setting(database, "retention_deletion_years", retention_values["deletion_years"])
            backup_enabled = request.form.get("automatic_backup_enabled") == "1"
            write_setting(database, "automatic_backup_enabled", "1" if backup_enabled else "0")
            write_setting(database, "automatic_backup_interval_days", backup_interval_days)
            write_setting(database, "automatic_backup_subdirectory", backup_subdirectory)
        database.commit()
        if settings_view in {"donnees", "legacy"}:
            run_data_retention(database, force=True)
            if backup_enabled and (not previous_backup["enabled"] or previous_backup["subdirectory"] != backup_subdirectory):
                try:
                    run_automatic_backup(database, application, force=True)
                except (OSError, sqlite3.Error, ValueError):
                    application.logger.exception("Première sauvegarde automatique impossible")
                    flash("Les options sont enregistrées, mais la première sauvegarde automatique a échoué. Vérifiez le dossier configuré.", "error")
        flash("Les options ont été enregistrées.", "success")
        return redirect(target_url)

    @application.post("/admin/options/tarifs")
    def admin_update_billing_tariffs():
        """Met à jour les tarifs utilisés uniquement par les prochains devis."""
        database = get_database()
        fields = (
            ("normal_hourly", "billing_rate_normal_hourly_cents", "Tarif normal horaire"),
            ("normal_half_day", "billing_rate_normal_half_day_cents", "Tarif normal demi-journée"),
            ("reduced_hourly", "billing_rate_reduced_hourly_cents", "Tarif réduit horaire"),
            ("reduced_half_day", "billing_rate_reduced_half_day_cents", "Tarif réduit demi-journée"),
            ("travel", "billing_travel_unit_cents", "Heure de déplacement"),
            ("consumable", "billing_consumable_unit_cents", "Forfait consommables"),
            ("rental_contract", "billing_rental_contract_fee_cents", "Frais fixes de location"),
            ("rental_delivery", "billing_rental_delivery_fee_cents", "Livraison et installation"),
        )
        parsed = {}
        errors = []
        for form_name, setting_key, label in fields:
            cents, error = parse_money_cents(request.form.get(form_name), label)
            if error:
                errors.append(error)
            parsed[setting_key] = cents
        if errors:
            for error in errors:
                flash(error, "error")
            return redirect(url_for("admin_settings_tariffs") + "#tarifs-facturation")
        for key, value in parsed.items():
            write_setting(database, key, value)
        database.commit()
        flash("Les tarifs des prochains devis ont été enregistrés.", "success")
        return redirect(url_for("admin_settings_tariffs") + "#tarifs-facturation")

    @application.post("/admin/options/catalogue-location")
    def admin_update_rental_catalog():
        """Modifie les machines actives et peut ajouter une nouvelle ligne."""
        database = get_database()
        rows = load_rental_catalog(database, include_inactive=True)
        errors = []
        timestamp = utc_now_iso()
        for key, machine in rows.items():
            name = request.form.get(f"machine_name_{key}", "").strip()
            monthly, monthly_error = parse_money_cents(
                request.form.get(f"machine_monthly_{key}"), f"Tarif de {machine['name']}"
            )
            deposit, deposit_error = parse_money_cents(
                request.form.get(f"machine_deposit_{key}"), f"Caution de {machine['name']}"
            )
            if not name or len(name) > 180:
                errors.append("Chaque machine doit avoir un nom de 180 caractères maximum.")
            for error in (monthly_error, deposit_error):
                if error:
                    errors.append(error)
            if not errors:
                database.execute(
                    """
                    UPDATE rental_catalog SET name = ?, monthly_cents = ?,
                        deposit_cents = ?, active = ?, archived = ?, updated_at = ?
                    WHERE machine_key = ?
                    """,
                    (
                        name, monthly, deposit,
                        1 if request.form.get(f"machine_active_{key}") == "1" and
                             request.form.get(f"machine_archived_{key}") != "1" else 0,
                        1 if request.form.get(f"machine_archived_{key}") == "1" else 0,
                        timestamp, key,
                    ),
                )

        new_name = request.form.get("new_machine_name", "").strip()
        if new_name:
            monthly, monthly_error = parse_money_cents(
                request.form.get("new_machine_monthly"), "Tarif de la nouvelle machine"
            )
            deposit, deposit_error = parse_money_cents(
                request.form.get("new_machine_deposit"), "Caution de la nouvelle machine"
            )
            for error in (monthly_error, deposit_error):
                if error:
                    errors.append(error)
            if len(new_name) > 180:
                errors.append("Le nom de la nouvelle machine est trop long.")
            if not errors:
                base_key = normalize_text_key(new_name).replace(" ", "_")[:50] or "machine"
                machine_key = base_key
                suffix = 2
                while database.execute(
                    "SELECT 1 FROM rental_catalog WHERE machine_key = ?", (machine_key,)
                ).fetchone():
                    machine_key = f"{base_key}_{suffix}"
                    suffix += 1
                next_order = database.execute(
                    "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM rental_catalog"
                ).fetchone()[0]
                database.execute(
                    """
                    INSERT INTO rental_catalog (
                        machine_key, name, monthly_cents, deposit_cents,
                        active, sort_order, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                    """,
                    (machine_key, new_name, monthly, deposit, next_order, timestamp, timestamp),
                )
        if errors:
            database.rollback()
            for error in dict.fromkeys(errors):
                flash(error, "error")
        else:
            database.commit()
            flash("Le catalogue de location a été enregistré.", "success")
        return redirect(url_for("admin_settings_tariffs") + "#catalogue-location")

    @application.post("/admin/options/catalogue-location/<machine_key>/supprimer")
    def admin_delete_rental_machine(machine_key):
        if not pin_csrf_valid():
            abort(400)
        database = get_database()
        machine = database.execute("SELECT 1 FROM rental_catalog WHERE machine_key = ?", (machine_key,)).fetchone()
        if not machine:
            abort(404)
        referenced = database.execute(
            "SELECT 1 FROM billing_records WHERE rental_machine_key = ? LIMIT 1", (machine_key,)
        ).fetchone()
        if referenced:
            flash("Machine déjà utilisée dans un dossier : désactivez-la ou archivez-la pour préserver l'historique.", "error")
        else:
            database.execute("DELETE FROM rental_catalog WHERE machine_key = ?", (machine_key,))
            database.commit()
            flash("Machine sans historique supprimée du catalogue.", "success")
        return redirect(url_for("admin_settings_tariffs") + "#catalogue-location")

    @application.post("/admin/options/tarifs-personnalises")
    def admin_update_custom_tariffs():
        if not pin_csrf_valid():
            abort(400)
        database = get_database()
        rows = load_custom_tariffs(database, include_inactive=True)
        parsed = []
        errors = []
        for key, previous in rows.items():
            name = request.form.get(f"tariff_name_{key}", "").strip()
            unit = request.form.get(f"tariff_unit_{key}", "")
            cents, error = parse_money_cents(request.form.get(f"tariff_amount_{key}"), f"Tarif {previous['name']}")
            if not 1 <= len(name) <= 180 or unit not in {"hourly", "half_day"}:
                errors.append("Nom ou unité de tarif invalide.")
            if error:
                errors.append(error)
            archived = int(request.form.get(f"tariff_archived_{key}") == "1")
            parsed.append((name, unit, cents,
                           int(request.form.get(f"tariff_active_{key}") == "1" and not archived),
                           archived, key))
        new_name = request.form.get("new_tariff_name", "").strip()
        new_unit = request.form.get("new_tariff_unit", "hourly")
        new_cents = 0
        if new_name:
            new_cents, error = parse_money_cents(request.form.get("new_tariff_amount"), "Nouveau tarif")
            if not 1 <= len(new_name) <= 180 or new_unit not in {"hourly", "half_day"}:
                errors.append("Nom ou unité du nouveau tarif invalide.")
            if error:
                errors.append(error)
        if errors:
            for error in dict.fromkeys(errors):
                flash(error, "error")
            return redirect(url_for("admin_settings_tariffs") + "#tarifs-personnalises")
        now = utc_now_iso()
        with database:
            for name, unit, cents, active, archived, key in parsed:
                database.execute(
                    "UPDATE billing_tariff_catalog SET name=?, unit=?, cents=?, active=?, archived=?, updated_at=? WHERE tariff_key=?",
                    (name, unit, cents, active, archived, now, key),
                )
            if new_name:
                base_key = normalize_text_key(new_name).replace(" ", "_")[:50] or "tarif"
                key = base_key
                suffix = 2
                while database.execute("SELECT 1 FROM billing_tariff_catalog WHERE tariff_key=?", (key,)).fetchone():
                    key = f"{base_key}_{suffix}"
                    suffix += 1
                order = database.execute("SELECT COALESCE(MAX(sort_order),0)+1 FROM billing_tariff_catalog").fetchone()[0]
                database.execute(
                    "INSERT INTO billing_tariff_catalog (tariff_key,name,unit,cents,active,archived,sort_order,created_at,updated_at) "
                    "VALUES (?,?,?,?,1,0,?,?,?)",
                    (key, new_name, new_unit, new_cents, order, now, now),
                )
        flash("Tarifs personnalisés enregistrés pour les prochains devis.", "success")
        return redirect(url_for("admin_settings_tariffs") + "#tarifs-personnalises")

    @application.post("/admin/options/tarifs-personnalises/<tariff_key>/supprimer")
    def admin_delete_custom_tariff(tariff_key):
        if not pin_csrf_valid():
            abort(400)
        database = get_database()
        if not database.execute("SELECT 1 FROM billing_tariff_catalog WHERE tariff_key=?", (tariff_key,)).fetchone():
            abort(404)
        if database.execute("SELECT 1 FROM billing_records WHERE custom_tariff_key=? LIMIT 1", (tariff_key,)).fetchone():
            flash("Tarif utilisé dans un devis : désactivez-le ou archivez-le pour préserver l'historique.", "error")
        else:
            database.execute("DELETE FROM billing_tariff_catalog WHERE tariff_key=?", (tariff_key,))
            database.commit()
            flash("Tarif sans historique supprimé.", "success")
        return redirect(url_for("admin_settings_tariffs") + "#tarifs-personnalises")

    @application.post("/admin/options/moderateur")
    def admin_update_moderator_pin():
        database = get_database()
        moderator_pin = request.form.get("moderator_pin", "").strip()
        if not pin_csrf_valid():
            abort(400)
        if not valid_pin(moderator_pin):
            flash("Le code modérateur doit contenir exactement 4 chiffres.", "error")
        elif check_pin(application.config["DATABASE"], "admin", moderator_pin):
            flash("Le code modérateur doit être différent du code administrateur.", "error")
        else:
            set_pin(application.config["DATABASE"], "moderator", moderator_pin)
            flash("Le code modérateur a été modifié.", "success")
        return redirect(url_for("admin_settings_kiosk") + "#acces-moderateur")

    @application.post("/admin/options/pin-administrateur")
    def admin_change_admin_pin():
        if not pin_csrf_valid():
            abort(400)
        path = application.config["DATABASE"]
        current_pin = request.form.get("current_pin", "")
        new_pin = request.form.get("new_pin", "")
        if not check_pin(path, "admin", current_pin):
            flash("Le PIN actuel est incorrect.", "error")
        elif not valid_pin(new_pin) or new_pin != request.form.get("confirm_pin"):
            flash("Le nouveau PIN doit contenir quatre chiffres identiques dans les deux champs.", "error")
        else:
            set_pin(path, "admin", new_pin)
            database = get_database()
            log_security_event(database, "admin_pin_changed")
            database.commit()
            flash("Le PIN administrateur a été modifié.", "success")
        return redirect(url_for("admin_settings_kiosk") + "#acces-administrateur")

    @application.get("/admin/sauvegarde/exporter")
    def admin_export_database():
        """Crée un instantané SQLite cohérent, y compris pendant l'activité."""
        with DATABASE_MAINTENANCE_LOCK:
            source = get_database()
            temporary = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
            temporary.close()
            temporary_path = Path(temporary.name)
            try:
                destination = sqlite3.connect(temporary_path)
                source.backup(destination)
                destination.close()
                validate_database_file(temporary_path)
            except Exception:
                temporary_path.unlink(missing_ok=True)
                raise
        # Une base de ce compteur reste petite. La charger avant la réponse permet
        # de supprimer immédiatement le fichier de travail sans gêner Gunicorn.
        database_bytes = temporary_path.read_bytes()
        temporary_path.unlink(missing_ok=True)
        timestamp = datetime.now(PARIS_TIMEZONE).strftime("%Y-%m-%d_%H-%M")
        return Response(
            database_bytes,
            mimetype="application/vnd.sqlite3",
            headers={
                "Content-Disposition": (
                    "attachment; filename="
                    f"openfablab-sauvegarde-{timestamp}.db"
                ),
                "Cache-Control": "private, no-store",
            },
        )

    @application.post("/admin/sauvegarde/reinitialiser")
    def admin_reset_database():
        """Vide toutes les données métier après une confirmation explicite."""
        if request.form.get("confirmation", "").strip() != "TOUT SUPPRIMER":
            flash("Saisissez TOUT SUPPRIMER pour confirmer la remise à zéro.", "error")
            return redirect(url_for("admin_settings_data"))

        database = get_database()
        try:
            with DATABASE_MAINTENANCE_LOCK:
                create_database_safety_copy(database, "avant-remise-a-zero")
                database.execute("BEGIN IMMEDIATE")
                database.execute("DELETE FROM attendance_corrections")
                database.execute("DELETE FROM weather_snapshots")
                database.execute("DELETE FROM sessions")
                database.execute("DELETE FROM visitors")
                database.execute("DELETE FROM billing_records")
                database.execute("DELETE FROM billing_clients")
                database.execute("DELETE FROM fablab_services")
                database.execute("DELETE FROM annual_activity_reports")
                database.execute("DELETE FROM rental_catalog")
                database.execute("DELETE FROM retention_warnings")
                database.execute("DELETE FROM users")
                database.execute("DELETE FROM app_settings")
                database.executemany(
                    "INSERT INTO app_settings (key, value) VALUES (?, ?)",
                    default_application_settings()
                    + [(INITIAL_DEMO_SETTING, "1")],
                )
                database.execute(
                    "DELETE FROM sqlite_sequence WHERE name IN ('users', 'sessions', 'visitors', 'weather_snapshots', 'billing_records', 'fablab_services')"
                )
                database.commit()
            flash(
                "La base a été remise à zéro. Aucun usager, visiteur ou historique ne subsiste dans la base active. "
                "Une copie de sécurité a été conservée sur le NAS.",
                "success",
            )
        except (OSError, ValueError, sqlite3.Error):
            database.rollback()
            application.logger.exception("Échec de la remise à zéro complète")
            flash("La base n'a pas pu être remise à zéro.", "error")
        return redirect(url_for("admin_settings_data"))

    @application.get("/admin/activites")
    def admin_services_legacy():
        return redirect(url_for("admin_services", **request.args))

    @application.get("/admin/animations")
    def admin_services():
        """Liste les animations, réservations et locations enregistrées."""
        database = get_database()
        search = request.args.get("q", "").strip()
        selected_type = request.args.get("type", "").strip()
        selected_year = request.args.get("year", "").strip()
        conditions = []
        parameters = []
        if search:
            conditions.append(
                "(fablab_services.title LIKE ? OR fablab_services.client_name LIKE ? "
                "OR fablab_services.invoice_reference LIKE ?)"
            )
            pattern = f"%{search}%"
            parameters.extend([pattern, pattern, pattern])
        if selected_type in {"animation", "reservation", "rental"}:
            conditions.append("fablab_services.service_type = ?")
            parameters.append(selected_type)
        if re.fullmatch(r"\d{4}", selected_year):
            conditions.append("substr(fablab_services.service_date, 1, 4) = ?")
            parameters.append(selected_year)
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        services = database.execute(
            "SELECT fablab_services.*, billing_records.id AS billing_record_id, "
            "COALESCE(c.booking_mode,'whole') AS booking_mode, "
            "(SELECT COUNT(*) FROM animation_slots sl WHERE sl.service_id=fablab_services.id AND sl.active=1) AS slot_count, "
            "(SELECT COUNT(*) FROM animation_bookings b WHERE b.service_id=fablab_services.id "
            "AND b.status IN ('confirmed','offer_pending','present','absent')) AS registered_count, "
            "(SELECT COUNT(*) FROM animation_bookings b WHERE b.service_id=fablab_services.id AND b.status='waitlisted') AS waiting_count "
            "FROM fablab_services "
            "LEFT JOIN billing_records ON billing_records.service_id = fablab_services.id "
            "LEFT JOIN animation_reservation_config c ON c.service_id=fablab_services.id"
            + where_clause
            + " ORDER BY fablab_services.service_date DESC, fablab_services.id DESC",
            parameters,
        ).fetchall()
        years = [
            row[0]
            for row in database.execute(
                "SELECT DISTINCT substr(service_date, 1, 4) FROM fablab_services ORDER BY 1 DESC"
            ).fetchall()
        ]
        return render_template(
            "services.html", services=services, years=years, search=search,
            selected_type=selected_type, selected_year=selected_year,
        )

    @application.get("/admin/activites/nouveau")
    def admin_service_form_legacy_new():
        return redirect(url_for("admin_service_form"))

    @application.get("/admin/activites/<int:service_id>/modifier")
    def admin_service_form_legacy_edit(service_id):
        return redirect(url_for("admin_service_form", service_id=service_id))

    @application.route("/admin/animations/nouveau", methods=["GET", "POST"])
    @application.route("/admin/animations/<int:service_id>/modifier", methods=["GET", "POST"])
    def admin_service_form(service_id=None):
        """Crée ou modifie uniquement une animation locale."""
        database = get_database()
        service = None
        previous_config = None
        if service_id is not None:
            service = database.execute(
                "SELECT * FROM fablab_services WHERE id = ?", (service_id,)
            ).fetchone()
            if service is None:
                abort(404)
            if service["service_type"] != "animation":
                linked_billing = database.execute(
                    "SELECT id FROM billing_records WHERE service_id = ?",
                    (service_id,),
                ).fetchone()
                flash(
                    "Les créneaux réservables et locations se modifient depuis Facturation.",
                    "error",
                )
                if linked_billing:
                    return redirect(
                        url_for("admin_billing_detail", record_id=linked_billing["id"])
                    )
                return redirect(url_for("admin_services"))
            previous_config = database.execute(
                "SELECT * FROM animation_reservation_config WHERE service_id = ?",
                (service_id,),
            ).fetchone()
        online_defaults = {
            "enabled": 0, "environment": "production", "audience": "all",
            "capacity": None, "signup_open_at": "",
            "close_minutes": int(read_setting(database, "reservation_close_minutes", "60")),
            "accompaniment_under_age": int(read_setting(database, "reservation_accompaniment_under_age", "15")),
            "waitlist_enabled": int(read_setting(database, "reservation_waitlist_enabled", "1")),
            "reminder_one_hours": int(read_setting(database, "reservation_reminder_one_hours", "24")),
            "reminder_two_hours": int(read_setting(database, "reservation_reminder_two_hours", "0")),
            "walkin_count": 0,
            "booking_mode": "whole", "slot_duration_minutes": 20,
            "slot_gap_minutes": 0, "slot_capacity": 1,
        }
        online_config = dict(previous_config) if previous_config else online_defaults
        if request.method == "GET":
            values = dict(service) if service else {
                "service_type": "animation",
                "service_date": datetime.now(PARIS_TIMEZONE).strftime("%Y-%m-%d"),
            }
            if service and service["amount_cents"] is not None:
                values["amount"] = f"{service['amount_cents'] / 100:.2f}"
            if previous_config and previous_config["enabled"]:
                values["actual_participants"] = previous_config["walkin_count"]
            return render_template("service_form.html", values=values, service=service,
                                   online_config=online_config)

        submitted_values = request.form.to_dict(flat=True)
        requested_type = submitted_values.get("service_type", "animation")
        if requested_type not in {"", "animation"}:
            flash(
                "Les créneaux réservables et locations se créent depuis Facturation.",
                "error",
            )
            submitted_values["service_type"] = "animation"
            return render_template(
                "service_form.html", values=submitted_values, service=service
            ), 400
        submitted_values["service_type"] = "animation"
        values, errors = parse_service_form(submitted_values)
        online_enabled = (load_modules(database)["public_reservations"]
                          and request.form.get("online_enabled") == "1")
        database.execute("BEGIN IMMEDIATE")
        if service_id:
            previous_config = database.execute("SELECT * FROM animation_reservation_config WHERE service_id=?", (service_id,)).fetchone()
            service = database.execute("SELECT * FROM fablab_services WHERE id=?", (service_id,)).fetchone()
        if load_modules(database)["public_reservations"]:
            online_config = {
                "enabled": int(online_enabled),
                "environment": request.form.get("online_environment", previous_config["environment"]
                                                if previous_config else "production"),
                "audience": request.form.get("online_audience", "all"),
                "signup_open_at": request.form.get("signup_open_at", "").strip(),
                "waitlist_enabled": int(request.form.get("waitlist_enabled") == "1"),
                "booking_mode": request.form.get("booking_mode", previous_config["booking_mode"] if previous_config else "whole"),
            }
            for key, minimum, maximum in (
                ("capacity", 0, 100000), ("close_minutes", 0, 1440),
                ("accompaniment_under_age", 0, 120),
                ("reminder_one_hours", 0, 168), ("reminder_two_hours", 0, 168),
                ("slot_duration_minutes", 1, 480), ("slot_gap_minutes", 0, 480),
                ("slot_capacity", 1, 100000),
            ):
                try:
                    candidate = request.form.get(key)
                    if candidate is None or candidate == "":
                        candidate = (values.get("expected_participants") or 0) if key == "capacity" else online_defaults.get(key, 0)
                    online_config[key] = int(candidate)
                    if not minimum <= online_config[key] <= maximum:
                        raise ValueError
                except (TypeError, ValueError):
                    errors.append(f"Le paramètre de réservation {key} est invalide.")
            if online_config["environment"] not in {"test", "production"}:
                errors.append("Choisissez un environnement de réservation valide.")
            if online_config["audience"] not in {"all", "registered"}:
                errors.append("Choisissez le public admis pour la réservation.")
            if online_config["booking_mode"] not in {"whole", "slots"}:
                errors.append("Choisissez un mode de réservation valide.")
            elif online_config["booking_mode"] == "slots" and not errors:
                try:
                    generated = generate_slots(values, online_config, read_setting(database, "structure_timezone", "Europe/Paris"), service_id or 0)
                    online_config["capacity"] = len(generated) * online_config["slot_capacity"]
                    values["expected_participants"] = online_config["capacity"]
                except ValueError as error:
                    errors.append(str(error))
            has_bookings = service_id and database.execute(
                "SELECT 1 FROM animation_bookings WHERE service_id=? LIMIT 1", (service_id,)).fetchone()
            if has_bookings and previous_config:
                changed = any(values.get(key) != service[key] for key in ("service_date", "start_time", "end_time"))
                changed = changed or any(online_config.get(key) != previous_config[key] for key in ("environment", "booking_mode"))
                if previous_config["booking_mode"] == "slots":
                    changed = changed or any(online_config.get(key) != previous_config[key] for key in ("slot_duration_minutes", "slot_gap_minutes"))
                    changed = changed or online_config.get("slot_capacity", 0) < previous_config["slot_capacity"]
                    if not errors and online_config["booking_mode"] == "slots":
                        before = [(r["slot_uuid"], r["starts_at"], r["ends_at"]) for r in database.execute(
                            "SELECT * FROM animation_slots WHERE service_id=? AND active=1 ORDER BY starts_at", (service_id,))]
                        after = [(r["slot_uuid"], r["starts_at"], r["ends_at"]) for r in generated]
                        changed = changed or before != after
                else:
                    changed = changed or online_config.get("capacity", 0) < previous_config["capacity"]
                if changed:
                    errors.append("Des inscriptions existent : changer le mode, l’environnement, les horaires ou réduire la capacité est refusé. Aucune inscription n’a été déplacée.")
            if online_enabled and online_config.get("capacity", 0) < 1:
                errors.append("Une animation publiée doit disposer d'au moins une place.")
            if online_config.get("capacity", 0) > 100000:
                errors.append("La capacité théorique totale ne doit pas dépasser 100 000 places.")
            if online_config["signup_open_at"]:
                try:
                    opening = datetime.fromisoformat(online_config["signup_open_at"])
                    if opening.tzinfo is None:
                        opening = opening.replace(tzinfo=PARIS_TIMEZONE)
                    online_config["signup_open_at"] = opening.astimezone(timezone.utc).isoformat(timespec="seconds")
                except ValueError:
                    errors.append("La date d'ouverture des inscriptions est invalide.")
            online_config["walkin_count"] = values.get("actual_participants") or 0
            if previous_config and previous_config["enabled"] and not online_enabled:
                # The manual count remains the explicit form value after disabling.
                pass
            elif online_enabled and service_id:
                present_count = database.execute(
                    "SELECT COUNT(*) FROM animation_bookings WHERE service_id = ? "
                    "AND status IN ('confirmed', 'present') AND is_present = 1", (service_id,)
                ).fetchone()[0]
                values["actual_participants"] = online_config["walkin_count"] + present_count
        if service_id and not load_modules(database)["public_reservations"] and database.execute(
            "SELECT 1 FROM animation_bookings WHERE service_id=? LIMIT 1", (service_id,)).fetchone():
            if any(values.get(key) != service[key] for key in ("service_date", "start_time", "end_time")):
                errors.append("Des inscriptions existent : les horaires sont protégés même lorsque le module est désactivé.")
        if errors:
            database.rollback()
            for error in errors:
                flash(error, "error")
            display_values = dict(submitted_values)
            return render_template(
                "service_form.html", values=display_values, service=service,
                online_config=online_config
            ), 400

        timestamp = utc_now_iso()
        if service is None:
            cursor = database.execute(
                """
                INSERT INTO fablab_services (
                    service_type, title, service_date, start_time, end_time,
                    duration_minutes, minimum_age, description, expected_participants,
                    actual_participants, participants, invoice_reference,
                    client_name, amount_cents, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*values.values(), timestamp, timestamp),
            )
            service_id = cursor.lastrowid
            message = "L'enregistrement a été ajouté."
        else:
            database.execute(
                """
                UPDATE fablab_services SET
                    service_type = ?, title = ?, service_date = ?,
                    start_time = ?, end_time = ?, duration_minutes = ?,
                    minimum_age = ?, description = ?, expected_participants = ?, actual_participants = ?,
                    participants = ?, invoice_reference = ?, client_name = ?,
                    amount_cents = ?, updated_at = ?
                WHERE id = ?
                """,
                (*values.values(), timestamp, service_id),
            )
            message = "L'enregistrement a été mis à jour."
        if load_modules(database)["public_reservations"]:
            if previous_config and previous_config["environment"] != online_config["environment"]:
                enqueue_animation(database, service_id, command="delete")
            database.execute(
                "INSERT INTO animation_reservation_config (service_id, enabled, environment, "
                "audience, capacity, signup_open_at, close_minutes, accompaniment_under_age, "
                "waitlist_enabled, reminder_one_hours, reminder_two_hours, walkin_count, updated_at, "
                "booking_mode, slot_duration_minutes, slot_gap_minutes, slot_capacity) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(service_id) DO UPDATE SET enabled=excluded.enabled, "
                "environment=excluded.environment, audience=excluded.audience, "
                "capacity=excluded.capacity, signup_open_at=excluded.signup_open_at, "
                "close_minutes=excluded.close_minutes, accompaniment_under_age=excluded.accompaniment_under_age, "
                "waitlist_enabled=excluded.waitlist_enabled, reminder_one_hours=excluded.reminder_one_hours, "
                "reminder_two_hours=excluded.reminder_two_hours, walkin_count=excluded.walkin_count, "
                "booking_mode=excluded.booking_mode, slot_duration_minutes=excluded.slot_duration_minutes, "
                "slot_gap_minutes=excluded.slot_gap_minutes, slot_capacity=excluded.slot_capacity, "
                "updated_at=excluded.updated_at",
                (service_id, online_config["enabled"], online_config["environment"],
                 online_config["audience"], online_config["capacity"],
                 online_config["signup_open_at"] or None, online_config["close_minutes"],
                 online_config["accompaniment_under_age"], online_config["waitlist_enabled"],
                 online_config["reminder_one_hours"] or None,
                 online_config["reminder_two_hours"] or None,
                 online_config["walkin_count"], timestamp, online_config["booking_mode"],
                 online_config["slot_duration_minutes"], online_config["slot_gap_minutes"], online_config["slot_capacity"]),
            )
            saved_service = database.execute("SELECT * FROM fablab_services WHERE id=?", (service_id,)).fetchone()
            save_slots(database, saved_service, online_config, read_setting(database, "structure_timezone", "Europe/Paris"))
            enqueue_animation(database, service_id)
        database.commit()
        flash(message, "success")
        return redirect(url_for("admin_services"))

    @application.post("/admin/activites/<int:service_id>/supprimer")
    @application.post("/admin/animations/<int:service_id>/supprimer")
    def admin_delete_service(service_id):
        """Supprime une ligne après confirmation textuelle explicite."""
        if request.form.get("confirmation", "").strip() != "SUPPRIMER":
            flash("Saisissez SUPPRIMER pour confirmer.", "error")
            return redirect(url_for("admin_services"))
        database = get_database()
        service = database.execute(
            "SELECT service_type FROM fablab_services WHERE id = ?", (service_id,)
        ).fetchone()
        if service is None:
            abort(404)
        linked_billing = database.execute(
            "SELECT id FROM billing_records WHERE service_id = ?", (service_id,)
        ).fetchone()
        if service["service_type"] != "animation":
            flash(
                "Les créneaux réservables et locations sont gérés depuis Facturation.",
                "error",
            )
            if linked_billing:
                return redirect(
                    url_for("admin_billing_detail", record_id=linked_billing["id"])
                )
            return redirect(url_for("admin_services"))
        if linked_billing:
            flash(
                "Cette réservation est pilotée par son dossier de facturation et ne peut pas être supprimée ici.",
                "error",
            )
            return redirect(
                url_for("admin_billing_detail", record_id=linked_billing["id"])
            )
        enqueue_animation(database, service_id, command="delete")
        cursor = database.execute(
            "DELETE FROM fablab_services WHERE id = ?", (service_id,)
        )
        database.commit()
        if cursor.rowcount == 0:
            abort(404)
        flash("L'enregistrement a été supprimé.", "success")
        return redirect(url_for("admin_services"))

    def booking_service(database, service_id):
        service = database.execute(
            "SELECT * FROM fablab_services WHERE id = ? AND service_type = 'animation'",
            (service_id,),
        ).fetchone()
        if service is None:
            abort(404)
        config = database.execute(
            "SELECT * FROM animation_reservation_config WHERE service_id = ?", (service_id,)
        ).fetchone()
        return service, config

    def update_booking_presence_total(database, service_id):
        database.execute(
            "UPDATE fablab_services SET actual_participants = "
            "COALESCE((SELECT walkin_count FROM animation_reservation_config WHERE service_id = ?), 0) + "
            "(SELECT COUNT(*) FROM animation_bookings WHERE service_id = ? "
            "AND status IN ('confirmed', 'present') AND is_present = 1) WHERE id = ?",
            (service_id, service_id, service_id),
        )

    @application.get("/admin/animations/<int:service_id>/inscriptions")
    def admin_animation_bookings(service_id):
        database = get_database()
        from family_waitlist import process_due, contact
        process_due(database)
        service, config = booking_service(database, service_id)
        bookings = database.execute(
            "SELECT b.*, u.category, sl.starts_at, sl.ends_at, "
            "EXISTS(SELECT 1 FROM sessions s WHERE s.user_id = b.user_id "
            "AND s.check_out IS NULL) AS on_site "
            "FROM animation_bookings b LEFT JOIN users u ON u.id = b.user_id "
            "LEFT JOIN animation_slots sl ON sl.slot_uuid=b.slot_uuid "
            "WHERE b.service_id = ? ORDER BY COALESCE(sl.starts_at,''), CASE b.status "
            "WHEN 'confirmed' THEN 0 WHEN 'present' THEN 1 WHEN 'offer_pending' THEN 2 "
            "WHEN 'waitlisted' THEN 3 ELSE 4 END, b.created_at, b.external_uuid",
            (service_id,),
        ).fetchall()
        counts = booking_counts(bookings)
        zone = read_setting(database, "structure_timezone", "Europe/Paris")
        bookings = [dict(row, slot_label=slot_label(row, zone)) for row in bookings]
        active = booking_capacity_used(database, service_id)
        pending = pending_confirmation_ids(database, service_id)
        groups = {}
        for booking in bookings:
            if booking["group_uuid"]:
                groups.setdefault(booking["group_uuid"], []).append(booking)
        from family_model import responsibles, age
        for booking in bookings:
            booking['family_new']=booking['source'].startswith('family_')
            person=database.execute('SELECT * FROM users WHERE id=?',(booking['user_id'],)).fetchone() if booking['user_id'] else None
            booking['exact_age']=age(person,datetime.fromisoformat(service['service_date']).date()) if person else None
            booking['responsibles']=responsibles(database,booking['user_id']) if person else []
            booking['group_count']=sum(b['status'] not in ('cancelled','expired','declined') for b in groups.get(booking['group_uuid'],[booking]))
            booking['owner']=database.execute('SELECT u.id,u.first_name,u.last_name FROM family_booking_requests r LEFT JOIN users u ON u.id=r.owner_id WHERE r.group_uuid=?',(booking['group_uuid'],)).fetchone()
            booking['family_contact']=contact(database,booking['user_id']) if person and booking['family_new'] else None
            meta=database.execute('SELECT contact_email,contact_phone,offer_expires_at FROM family_booking_groups WHERE group_uuid=?',(booking['group_uuid'],)).fetchone()
            booking['offer_expires_at']=meta['offer_expires_at'] if meta and booking['status']=='offer_pending' else None
            if booking['family_new']:
                booking['email']=meta['contact_email'] if meta else (person['email'] if person else None)
                booking['phone']=meta['contact_phone'] if meta else (person['phone'] if person else None)
                booking['history']=database.execute('SELECT status,created_at FROM family_booking_history WHERE group_uuid=? ORDER BY id',(booking['group_uuid'],)).fetchall()
        confirmable = {booking["external_uuid"] for booking in bookings if config is not None
                       and all(member["status"] in {"waitlisted", "offer_pending"}
                               and member["external_uuid"] not in pending
                               for member in groups.get(booking["group_uuid"], [booking]))}
        users = sorted(database.execute(
            "SELECT id, public_id, first_name, last_name FROM users WHERE active = 1 "
        ).fetchall(), key=lambda user: (normalize_text_key(user["first_name"]) or "",
                                       normalize_text_key(user["last_name"]) or "", user["public_id"]))
        confirmation_errors = {}
        for row in database.execute(
            "SELECT o.entity_key, o.payload_json, o.last_error FROM reservation_outbox o "
            "JOIN animation_bookings b ON b.external_uuid = o.entity_key "
            "WHERE b.service_id = ? AND o.command_type = 'booking' ORDER BY o.id", (service_id,)
        ):
            payload = json.loads(row["payload_json"])
            if payload.get("action") == "confirm":
                for booking_id in payload.get("members") or [row["entity_key"]]:
                    confirmation_errors[booking_id] = row["last_error"]
        return render_template(
            "animation_bookings.html", service=service, config=config,
            tablet_requests=__import__('tablet_reservations').requests_for(database,service_id),
            bookings=bookings, counts=counts, users=users,
            remaining=max(0, (config["capacity"] if config else 0) - active),
            current_year=int(service["service_date"][:4]),
            booking_reservation_status=booking_reservation_status,
            booking_presence=booking_presence,
            pending_confirmations=pending, confirmable_ids=confirmable,
            confirmation_errors=confirmation_errors,
            csrf_token=pin_csrf_token(),
            slots=slots_summary(database, service_id, zone),
        )

    @application.get("/admin/animations/<int:service_id>/inscriptions.csv")
    def admin_animation_bookings_csv(service_id):
        database = get_database()
        service, _config = booking_service(database, service_id)
        stream = io.StringIO()
        writer = csv.writer(stream, delimiter=";")
        writer.writerow(["Animation", "Date", "Statut", "Prénom", "Nom", "Année de naissance",
                         "Âge dans l'année", "Type", "Catégorie", "Rattachement", "Présence", "E-mail", "Téléphone"]
                        + (["Créneau"] if _config and _config["booking_mode"] == "slots" else []))
        rows = database.execute(
            "SELECT b.*, u.category, sl.starts_at, sl.ends_at FROM animation_bookings b LEFT JOIN users u ON u.id = b.user_id "
            "LEFT JOIN animation_slots sl ON sl.slot_uuid=b.slot_uuid WHERE b.service_id = ? ORDER BY COALESCE(sl.starts_at,''), b.created_at", (service_id,)
        )
        for row in rows:
            from family_waitlist import export_contact
            row=export_contact(database,row)
            presence = booking_presence(row)
            writer.writerow([service["title"], service["service_date"], booking_reservation_status(row),
                             row["first_name"], row["last_name"], row["birth_year"] or "",
                             int(service["service_date"][:4]) - row["birth_year"] if row["birth_year"] else "",
                             "Usager" if row["user_id"] else "Visiteur",
                             dynamic_category_label(database,row['category']) if row['category'] else '',
                             row["link_status"], "Oui" if presence is True else "Non" if presence is False else "Non renseignée",
                             row["email"], row["phone"]]
                            + ([slot_label(row, read_setting(database, "structure_timezone", "Europe/Paris"))] if _config and _config["booking_mode"] == "slots" else []))
        filename = f"openfablab-inscriptions-{service_id}.csv"
        return Response("\ufeff" + stream.getvalue(), mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"',
                                 "Cache-Control": "private, no-store"})

    @application.get("/admin/animations/<int:service_id>/inscriptions.pdf")
    def admin_animation_bookings_pdf(service_id):
        database = get_database()
        service, config = booking_service(database, service_id)
        bookings = database.execute(
            "SELECT b.*, u.category, sl.starts_at, sl.ends_at FROM animation_bookings b LEFT JOIN users u ON u.id = b.user_id "
            "LEFT JOIN animation_slots sl ON sl.slot_uuid=b.slot_uuid WHERE b.service_id = ? ORDER BY COALESCE(sl.starts_at,''), b.created_at, b.external_uuid", (service_id,)
        ).fetchall()
        from family_waitlist import export_contact
        bookings = [dict(export_contact(database,row), slot_label=slot_label(row, read_setting(database, "structure_timezone", "Europe/Paris"))) for row in bookings]
        structure, institution, main, _signature = document_brand_assets(database)
        content = generate_animation_bookings_pdf(service, config, bookings, structure,
                                                  {r['category_key']:r['name'] for r in categories(database,True)}, main, institution)
        filename = f"{service['service_date'].replace('-', '')}_Inscriptions_{safe_filename_part(service['title'])}.pdf"
        return Response(content, mimetype="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        })

    @application.get("/admin/animations/<int:service_id>/inscriptions/usager/<public_id>")
    def admin_animation_booking_user(service_id, public_id):
        """Préremplit un seul participant côté Admin, sans modifier sa fiche maître."""
        if session.get("access_role") != "admin":
            abort(403)
        database = get_database()
        booking_service(database, service_id)
        user = database.execute(
            "SELECT first_name, last_name, birth_year, email, phone FROM users "
            "WHERE public_id = ? AND active = 1", (public_id,),
        ).fetchone()
        if user is None:
            abort(404)
        response = jsonify({key: user[key] or "" for key in
                            ("first_name", "last_name", "birth_year", "email", "phone")})
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @application.post("/admin/animations/<int:service_id>/inscriptions/<booking_uuid>/action")
    def admin_animation_booking_action(service_id, booking_uuid):
        if not pin_csrf_valid():
            abort(400)
        database = get_database()
        current=database.execute('SELECT source FROM animation_bookings WHERE service_id=? AND external_uuid=?',(service_id,booking_uuid)).fetchone()
        if current and current['source'].startswith('family_'):
            from family_reservations import team_action
            try:
                team_action(database,service_id,booking_uuid,request.form.get('action',''),session.get('access_role','admin'),request.form.get('person_id'))
                flash('Réservation mise à jour.','success')
            except ValueError as error:
                flash(str(error),'error')
            return redirect(url_for('admin_animation_bookings',service_id=service_id))
        _service, config = booking_service(database, service_id)
        database.execute("BEGIN IMMEDIATE")
        booking = database.execute(
            "SELECT * FROM animation_bookings WHERE service_id = ? AND external_uuid = ?",
            (service_id, booking_uuid),
        ).fetchone()
        if booking is None:
            abort(404)
        action = request.form.get("action", "")
        allowed = {"present", "absent", "cancel", "confirm", "verify", "link", "unlink"}
        if action not in allowed:
            abort(400)
        if booking_reservation_status(booking) != "confirmed" and action in {"present", "absent"}:
            database.rollback()
            flash("Confirmez d’abord l’inscription avant de renseigner sa présence.", "error")
            return redirect(url_for("admin_animation_bookings", service_id=service_id))
        now = utc_now_iso()
        role = session.get("access_role", "admin")
        details = {}
        if action == "confirm":
            members = database.execute(
                "SELECT * FROM animation_bookings WHERE service_id = ? AND group_uuid = ?",
                (service_id, booking["group_uuid"]),
            ).fetchall() if booking["group_uuid"] else [booking]
            pending = pending_confirmation_ids(database, service_id)
            if (config is None or booking["status"] not in {"waitlisted", "offer_pending"}
                    or any(member["status"] not in {"waitlisted", "offer_pending"} for member in members)
                    or any(member["external_uuid"] in pending for member in members)):
                database.rollback()
                flash("Cette inscription ne peut pas être confirmée dans son état actuel.", "error")
                return redirect(url_for("admin_animation_bookings", service_id=service_id))
            override = role == "admin" and request.form.get("capacity_override") == "1"
            additional = sum(member["status"] == "waitlisted" for member in members)
            slot = database.execute("SELECT * FROM animation_slots WHERE slot_uuid=? AND service_id=? AND active=1",
                                    (booking["slot_uuid"], service_id)).fetchone() if config["booking_mode"] == "slots" else None
            if config["booking_mode"] == "slots" and (not slot or any(member["slot_uuid"] != slot["slot_uuid"] for member in members)):
                database.rollback()
                abort(400)
            limit = slot["capacity"] if slot else config["capacity"]
            if booking_capacity_used(database, service_id, slot["slot_uuid"] if slot else None) + additional > limit and not override:
                database.rollback()
                flash("La capacité est atteinte. Seul l’administrateur peut confirmer un dépassement explicite.", "error")
                return redirect(url_for("admin_animation_bookings", service_id=service_id))
            details = {"capacity_override": override, "members": [member["external_uuid"] for member in members]}
            remote = (read_setting(database, "reservation_wordpress_url")
                      and load_sync_secret(application.config["DATABASE"]))
            if not remote:
                for member in members:
                    database.execute("UPDATE animation_bookings SET status = 'confirmed', updated_at = ? "
                                     "WHERE external_uuid = ?", (now, member["external_uuid"]))
        elif action in {"present", "absent"}:
            database.execute(
                "UPDATE animation_bookings SET status = 'confirmed', is_present = ?, updated_at = ? "
                "WHERE external_uuid = ?", (int(action == "present"), now, booking_uuid)
            )
        elif action == "cancel":
            database.execute(
                "UPDATE animation_bookings SET status = 'cancelled', is_present = 0, updated_at = ? "
                "WHERE service_id = ? AND (external_uuid = ? OR (group_uuid IS NOT NULL AND group_uuid = ?)) "
                "AND status NOT IN ('cancelled', 'expired')",
                (now, service_id, booking_uuid, booking["group_uuid"])
            )
        elif action == "verify":
            database.execute(
                "UPDATE animation_bookings SET link_status = 'manual', verified_at = ?, "
                "verified_by_role = ?, updated_at = ? WHERE external_uuid = ?",
                (now, role, now, booking_uuid),
            )
        elif action == "link":
            public_id = request.form.get("public_id", "").strip()
            user = database.execute(
                "SELECT id FROM users WHERE public_id = ? AND active = 1", (public_id,)
            ).fetchone()
            if user is None:
                flash("Choisissez un usager actif.", "error")
                return redirect(url_for("admin_animation_bookings", service_id=service_id))
            database.execute(
                "UPDATE animation_bookings SET user_id = ?, public_id = ?, link_status = 'manual', "
                "verified_at = ?, verified_by_role = ?, updated_at = ? WHERE external_uuid = ?",
                (user["id"], public_id, now, role, now, booking_uuid),
            )
            details["public_id"] = public_id
        else:
            database.execute(
                "UPDATE animation_bookings SET user_id = NULL, public_id = NULL, "
                "link_status = 'visitor', updated_at = ? WHERE external_uuid = ?",
                (now, booking_uuid),
            )
        enqueue_booking_command(database, booking["environment"], booking_uuid, action, **details)
        database.execute(
            "INSERT INTO reservation_actions (booking_uuid, action, actor_role, created_at) VALUES (?, ?, ?, ?)",
            (booking_uuid, action, role, now),
        )
        update_booking_presence_total(database, service_id)
        database.commit()
        flash("Confirmation en attente de synchronisation ; les places nécessaires sont réservées localement."
              if action == "confirm" and remote else
              "Inscription mise à jour ; la transmission vers WordPress est en attente.", "success")
        return redirect(url_for("admin_animation_bookings", service_id=service_id))

    @application.post("/admin/animations/<int:service_id>/inscriptions/sur-place")
    def admin_animation_booking_walkin(service_id):
        if not pin_csrf_valid():
            abort(400)
        database=get_database()
        from family_reservations import reserve
        selected=request.form.getlist('person_ids')
        if not selected and request.form.get('public_id'):
            found=database.execute('SELECT id FROM users WHERE public_id=? AND active=1',(request.form['public_id'],)).fetchone()
            selected=[found['id']] if found else []
        try:
            if not selected:
                raise ValueError('Sélectionnez les comptes usagers des participants. Chaque personne doit avoir sa propre fiche.')
            config=database.execute('SELECT environment FROM animation_reservation_config WHERE service_id=?',(service_id,)).fetchone()
            value=reserve(database,int(selected[0]),selected,service_id,request.form.get('slot_uuid') or None,
                          secrets.token_urlsafe(32),config['environment'] if config else 'production','administration',True)
            flash('Groupe confirmé.' if value['status']=='confirmed' else 'Tout le groupe est en liste d’attente.','success')
        except ValueError as error:
            database.rollback();flash(str(error),'error')
        return redirect(url_for('admin_animation_bookings',service_id=service_id))

    @application.get("/admin/activites/<int:service_id>/calendrier.ics")
    def admin_service_calendar_legacy(service_id):
        return redirect(url_for("admin_service_calendar", service_id=service_id))

    @application.get("/admin/animations/<int:service_id>/calendrier.ics")
    def admin_service_calendar(service_id):
        """Exporte un événement iCalendar pour Apple Calendar et Outlook."""
        database = get_database()
        row = database.execute(
            """
            SELECT fablab_services.*, billing_records.id AS billing_record_id,
                   billing_records.rental_end_date AS end_date,
                   billing_records.client_contact,
                   billing_records.email AS client_email,
                   billing_records.phone AS client_phone
            FROM fablab_services
            LEFT JOIN billing_records
                ON billing_records.service_id = fablab_services.id
            WHERE fablab_services.id = ?
            """,
            (service_id,),
        ).fetchone()
        if row is None:
            abort(404)
        service = dict(row)
        detail_url = (
            url_for("admin_billing_detail", record_id=service["billing_record_id"], _external=True)
            if service.get("billing_record_id") else
            url_for("admin_service_form", service_id=service_id, _external=True)
        )
        filename = f"{safe_filename_part(service['title'])}-{service['service_date']}.ics"
        return Response(
            build_ics_event(service, base_url=detail_url,
                            structure=load_structure_settings(database)),
            mimetype="text/calendar; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "private, no-store",
            },
        )

    @application.get("/admin/facturation/<int:record_id>/calendrier.ics")
    def admin_billing_calendar(record_id):
        """Exporte un devis en calendrier, avant ou après création de la facture."""
        record = load_billing_record(get_database(), record_id)
        event = {
            "id": f"facturation-{record['id']}",
            "service_type": (
                "rental" if record["billing_type"] == "rental" else "reservation"
            ),
            "title": record["title"],
            "service_date": record["activity_date"],
            "start_time": record.get("activity_start_time"),
            "end_time": record.get("activity_end_time"),
            "end_date": record.get("rental_end_date"),
            "description": record.get("description"),
            "participants": record.get("participants"),
            "client_name": record.get("client_structure"),
            "client_contact": record.get("client_contact"),
            "client_email": record.get("email"),
            "client_phone": record.get("phone"),
            "invoice_reference": (
                record.get("invoice_number") or record.get("quote_number")
            ),
        }
        detail_url = url_for(
            "admin_billing_detail", record_id=record_id, _external=True
        )
        filename = (
            f"{safe_filename_part(record['title'])}-{record['activity_date']}.ics"
        )
        return Response(
            build_ics_event(event, base_url=detail_url,
                            structure=load_structure_settings(get_database())),
            mimetype="text/calendar; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "private, no-store",
            },
        )

    @application.get("/admin/facturation")
    def admin_billing():
        """Liste les dossiers de facturation et leur état d'avancement."""
        database = get_database()
        search = request.args.get("q", "").strip()
        selected_status = request.args.get("status", "").strip()
        selected_year = request.args.get("year", "").strip()
        conditions = []
        parameters = []
        if search:
            pattern = f"%{search}%"
            conditions.append(
                "(quote_number LIKE ? OR invoice_number LIKE ? OR "
                "client_structure LIKE ? OR client_contact LIKE ? OR title LIKE ?)"
            )
            parameters.extend([pattern] * 5)
        if re.fullmatch(r"\d{4}", selected_year):
            conditions.append("substr(quote_date, 1, 4) = ?")
            parameters.append(selected_year)
        status_conditions = {
            "quote": "quote_cancelled_at IS NULL AND quote_signed_at IS NULL",
            "signed": (
                "quote_cancelled_at IS NULL AND quote_signed_at IS NOT NULL "
                "AND invoice_number IS NULL"
            ),
            "cancelled": "quote_cancelled_at IS NOT NULL",
            "ready": "invoice_number IS NOT NULL AND invoice_sent_at IS NULL",
            "sent": "invoice_sent_at IS NOT NULL AND paid_at IS NULL",
            "paid": "paid_at IS NOT NULL",
        }
        if selected_status in status_conditions:
            conditions.append(status_conditions[selected_status])
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        rows = database.execute(
            "SELECT * FROM billing_records" + where_clause
            + " ORDER BY quote_date DESC, id DESC",
            parameters,
        ).fetchall()
        records = [billing_record_dict(row) for row in rows]
        years = [
            row[0]
            for row in database.execute(
                "SELECT DISTINCT substr(quote_date, 1, 4) AS year "
                "FROM billing_records ORDER BY year DESC"
            ).fetchall()
            if row[0]
        ]
        report_years = {
            datetime.now(PARIS_TIMEZONE).year,
            *[int(year) for year in years if str(year).isdigit()],
        }
        report_years.update(
            int(row[0]) for row in database.execute(
                "SELECT DISTINCT substr(service_date, 1, 4) FROM fablab_services "
                "WHERE service_date IS NOT NULL"
            ).fetchall() if row[0] and str(row[0]).isdigit()
        )
        report_years.update(
            int(row[0]) for row in database.execute(
                "SELECT DISTINCT substr(check_in, 1, 4) FROM sessions WHERE check_in IS NOT NULL"
            ).fetchall() if row[0] and str(row[0]).isdigit()
        )
        saved_report_years = {
            row[0] for row in database.execute(
                "SELECT year FROM annual_activity_reports"
            ).fetchall()
        }
        all_records = [
            billing_record_dict(row)
            for row in database.execute("SELECT * FROM billing_records").fetchall()
        ]
        totals = {
            "quotes": sum(
                1 for record in all_records
                if not record["quote_signed_at"] and not record["quote_cancelled_at"]
            ),
            "signed": sum(
                1 for record in all_records
                if record["quote_signed_at"] and not record["invoice_number"]
                and not record["quote_cancelled_at"]
            ),
            "pending": sum(
                record["amount_cents"] for record in all_records
                if record["invoice_sent_at"] and not record["paid_at"]
            ),
            "paid": sum(
                record["amount_cents"] for record in all_records if record["paid_at"]
            ),
        }
        clients = [
            dict(row)
            for row in database.execute(
                """
                SELECT billing_clients.*,
                       COUNT(billing_records.id) AS record_count
                FROM billing_clients
                LEFT JOIN billing_records
                    ON billing_records.client_id = billing_clients.id
                GROUP BY billing_clients.id
                ORDER BY contact_name COLLATE NOCASE, structure_name COLLATE NOCASE
                """
            ).fetchall()
        ]
        return render_template(
            "billing_list.html",
            records=records,
            years=years,
            search=search,
            selected_status=selected_status,
            selected_year=selected_year,
            totals=totals,
            clients=clients,
            report_years=sorted(report_years, reverse=True),
            saved_report_years=saved_report_years,
        )

    @application.route("/admin/facturation/nouveau", methods=["GET", "POST"])
    @application.route(
        "/admin/facturation/<int:record_id>/modifier", methods=["GET", "POST"]
    )
    def admin_billing_form(record_id=None):
        """Crée ou modifie le devis source d'un dossier de facturation."""
        database = get_database()
        record = load_billing_record(database, record_id) if record_id else None
        modules = load_modules(database)
        resource_key = request.values.get('resource_booking','') if not record else ''
        resource_context = None
        if resource_key:
            from evolution_routes import require_csrf
            resource_context = database.execute('SELECT b.*,r.name,u.first_name,u.last_name,u.email,u.phone FROM resource_bookings b JOIN resources r USING(resource_uuid) LEFT JOIN users u ON u.id=b.user_id WHERE booking_uuid=?',(resource_key,)).fetchone()
            if not resource_context:
                abort(404)
            if resource_context['billing_record_id']:
                if request.method=='POST':abort(409,'Cette réservation possède déjà un dossier.')
                return redirect(url_for('admin_billing_detail',record_id=resource_context['billing_record_id']))
            if resource_context['status'] in {'refused','cancelled'}:
                abort(409,'Réservation refusée ou annulée : aucun nouveau devis.')
            if request.method=='POST':require_csrf()
        if not record:
            requested_type = (request.args.get("type") if request.method == "GET"
                              else request.form.get("billing_type")) or "reservation"
            if requested_type not in {"reservation", "rental"}:
                abort(404)
            if requested_type == "reservation" and not modules["booking_slots"] and not resource_context:
                abort(404)
            if requested_type == "rental" and not modules["rentals"]:
                abort(404)
        if request.method == "GET":
            values = dict(record) if record else {
                "billing_type": (
                    "rental" if request.args.get("type") == "rental" else "reservation"
                ),
                "quote_date": datetime.now(PARIS_TIMEZONE).strftime("%Y-%m-%d"),
                "activity_date": datetime.now(PARIS_TIMEZONE).strftime("%Y-%m-%d"),
                "participants": 1,
                "rate_category": "normal",
                "rate_unit": "hourly",
                "rate_quantity": 1,
                "travel_quantity": 0,
                "consumable_mode": "included",
                "consumable_quantity": 0,
                "rental_months": 1,
            }
            values["notes"] = values.get("notes") or ""
            if resource_context:
                begin=parse_timestamp(resource_context['starts_at']).astimezone(PARIS_TIMEZONE)
                end=parse_timestamp(resource_context['ends_at']).astimezone(PARIS_TIMEZONE)
                values.update(resource_booking=resource_key,title=resource_context['name'],activity_date=begin.date().isoformat(),
                              activity_start_time=begin.strftime('%H:%M'),activity_end_time=end.strftime('%H:%M'),
                              client_contact=' '.join(filter(None,(resource_context['first_name'],resource_context['last_name']))),
                              email=resource_context['email'] or '',phone=resource_context['phone'] or '',
                              description='Réservation de ressource · tarif convenu : '+format(resource_context['amount_cents']/100,'.2f')+' €')
            values["quote_signed_date"] = (
                timestamp_to_local_date(record.get("quote_signed_at"))
                if record else ""
            )
            for field_name, timestamp_field in (
                ("invoice_sent_date", "invoice_sent_at"),
                ("paid_date", "paid_at"),
                ("reminder_one_date", "reminder_one_at"),
                ("reminder_two_date", "reminder_two_at"),
            ):
                values[field_name] = (
                    timestamp_to_local_date(record.get(timestamp_field))
                    if record else ""
                )
            return render_template(
                "billing_form.html", values=values, record=record,
                rental_catalog=available_rental_catalog(database, record),
                billing_tariffs=load_billing_tariffs(database),
                custom_tariffs=load_custom_tariffs(database, include_inactive=bool(record)),
            )

        values, errors = parse_billing_form(
            request.form, database, existing_record=record
        )
        if resource_context:
            # Reuse the existing dossier and client registry; snapshot price is
            # not recomputed from an unrelated generic booking tariff.
            values.update(amount_cents=resource_context['amount_cents'],rate_unit_cents=resource_context['amount_cents'],
                          rate_quantity=1,travel_quantity=0,consumable_quantity=0)
        quote_date, quote_date_error = parse_iso_date(
            request.form.get("quote_date"), "La date du devis"
        )
        if quote_date_error:
            errors.append(quote_date_error)
        quote_signed_at = record.get("quote_signed_at") if record else None
        invoice_date = record.get("invoice_date") if record else None
        quote_number = record.get("quote_number") if record else None
        invoice_number = record.get("invoice_number") if record else None
        invoice_sent_at = record.get("invoice_sent_at") if record else None
        paid_at = record.get("paid_at") if record else None
        reminder_one_at = record.get("reminder_one_at") if record else None
        reminder_two_at = record.get("reminder_two_at") if record else None
        if record:
            quote_number, reference_error = validate_billing_reference(
                request.form.get("quote_number", record["quote_number"]),
                "Le nom du devis",
            )
            if reference_error:
                errors.append(reference_error)
            quote_signed_at, signed_error = parse_optional_tracking_date(
                request.form,
                "quote_signed_date",
                "La date de signature du devis",
                record.get("quote_signed_at"),
            )
            if signed_error:
                errors.append(signed_error)
            if record.get("invoice_number"):
                invoice_number, reference_error = validate_billing_reference(
                    request.form.get("invoice_number", record["invoice_number"]),
                    "Le nom de la facture",
                )
                if reference_error:
                    errors.append(reference_error)
                invoice_date, invoice_date_error = parse_iso_date(
                    request.form.get("invoice_date", record.get("invoice_date")),
                    "La date de la facture",
                )
                if invoice_date_error:
                    errors.append(invoice_date_error)
                for form_field, label, existing_field in (
                    ("invoice_sent_date", "La date d’envoi de la facture", "invoice_sent_at"),
                    ("paid_date", "La date de règlement", "paid_at"),
                    ("reminder_one_date", "La date de la relance 1", "reminder_one_at"),
                    ("reminder_two_date", "La date de la relance 2", "reminder_two_at"),
                ):
                    parsed_value, tracking_error = parse_optional_tracking_date(
                        request.form, form_field, label, record.get(existing_field)
                    )
                    if tracking_error:
                        errors.append(tracking_error)
                    if existing_field == "invoice_sent_at":
                        invoice_sent_at = parsed_value
                    elif existing_field == "paid_at":
                        paid_at = parsed_value
                    elif existing_field == "reminder_one_at":
                        reminder_one_at = parsed_value
                    else:
                        reminder_two_at = parsed_value
                if paid_at and not invoice_sent_at:
                    errors.append("Une facture réglée doit avoir une date d’envoi.")
                if (reminder_one_at or reminder_two_at) and not invoice_sent_at:
                    errors.append("Une relance nécessite une date d’envoi de la facture.")
        if errors:
            for error in errors:
                flash(error, "error")
            display_values = dict(request.form)
            display_values["amount_cents"] = values["amount_cents"]
            return render_template(
                "billing_form.html", values=display_values, record=record,
                rental_catalog=available_rental_catalog(database, record),
                billing_tariffs=load_billing_tariffs(database),
                custom_tariffs=load_custom_tariffs(database, include_inactive=bool(record)),
            ), 400

        timestamp = utc_now_iso()
        try:
            if resource_context:
                database.execute('BEGIN IMMEDIATE')
            client_id = upsert_billing_client(
                database,
                values,
                existing_client_id=record.get("client_id") if record else None,
                timestamp=timestamp,
            )
            if record is None:
                quote_number = next_billing_number(
                    database, "quote_number", int(quote_date[:4]),
                    rental=values["billing_type"] == "rental",
                )
                cursor = database.execute(
                    """
                    INSERT INTO billing_records (
                        billing_type, quote_number, quote_date,
                        client_id,
                        client_contact, client_structure, address_line,
                        postal_code, city, phone, email, title, description,
                        activity_date, activity_time_details, participants,
                        rate_category, rate_is_agglo, rate_unit, rate_quantity, travel_quantity,
                        consumable_mode, consumable_quantity, amount_cents, notes,
                        rental_machine_key, rental_machine_name, rental_months,
                        rental_monthly_cents, rental_deposit_cents, rental_delivery,
                        rental_deposit_exempt, rental_end_date,
                        created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        values["billing_type"], quote_number,
                        quote_date,
                        client_id,
                        values["client_contact"], values["client_structure"],
                        values["address_line"], values["postal_code"], values["city"],
                        values["phone"] or None, values["email"] or None,
                        values["title"], values["description"], values["activity_date"],
                        values["activity_time_details"] or None, values["participants"],
                        values["rate_category"], values["rate_is_agglo"],
                        values["rate_unit"],
                        values["rate_quantity"], values["travel_quantity"],
                        values["consumable_mode"], values["consumable_quantity"],
                        values["amount_cents"], values["notes"] or None,
                        values["rental_machine_key"], values["rental_machine_name"],
                        values["rental_months"], values["rental_monthly_cents"],
                        values["rental_deposit_cents"], values["rental_delivery"],
                        values["rental_deposit_exempt"], values["rental_end_date"],
                        timestamp, timestamp,
                    ),
                )
                record_id = cursor.lastrowid
                database.execute(
                    """
                    UPDATE billing_records SET
                        activity_start_time = ?, activity_end_time = ?,
                        activity_duration_minutes = ?, rate_unit_cents = ?,
                        travel_unit_cents = ?, consumable_unit_cents = ?,
                        rental_contract_fee_cents = ?, rental_delivery_fee_cents = ?,
                        custom_tariff_key = ?, custom_tariff_name = ?
                    WHERE id = ?
                    """,
                    (
                        values["activity_start_time"], values["activity_end_time"],
                        values["activity_duration_minutes"], values["rate_unit_cents"],
                        values["travel_unit_cents"], values["consumable_unit_cents"],
                        values["rental_contract_fee_cents"],
                        values["rental_delivery_fee_cents"],
                        values["custom_tariff_key"], values["custom_tariff_name"], record_id,
                    ),
                )
                message = f"Le devis {quote_number} a été créé."
            else:
                database.execute(
                    """
                    UPDATE billing_records SET quote_number = ?, invoice_number = ?,
                        quote_date = ?, client_id = ?, client_contact = ?,
                        client_structure = ?, address_line = ?, postal_code = ?, city = ?,
                        phone = ?, email = ?, title = ?, description = ?, activity_date = ?,
                        activity_time_details = ?, participants = ?, rate_category = ?,
                        rate_is_agglo = ?, rate_unit = ?, rate_quantity = ?, travel_quantity = ?,
                        consumable_mode = ?, consumable_quantity = ?, amount_cents = ?,
                        notes = ?, rental_machine_key = ?, rental_machine_name = ?,
                        rental_months = ?, rental_monthly_cents = ?,
                        rental_deposit_cents = ?, rental_delivery = ?,
                        rental_deposit_exempt = ?, rental_end_date = ?,
                        quote_signed_at = ?, invoice_date = ?, invoice_sent_at = ?,
                        paid_at = ?, reminder_one_at = ?, reminder_two_at = ?,
                        payment_overdue_notified_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        quote_number, invoice_number,
                        quote_date, client_id,
                        values["client_contact"], values["client_structure"],
                        values["address_line"], values["postal_code"], values["city"],
                        values["phone"] or None, values["email"] or None,
                        values["title"], values["description"], values["activity_date"],
                        values["activity_time_details"] or None, values["participants"],
                        values["rate_category"], values["rate_is_agglo"],
                        values["rate_unit"],
                        values["rate_quantity"], values["travel_quantity"],
                        values["consumable_mode"], values["consumable_quantity"],
                        values["amount_cents"], values["notes"] or None,
                        values["rental_machine_key"], values["rental_machine_name"],
                        values["rental_months"], values["rental_monthly_cents"],
                        values["rental_deposit_cents"], values["rental_delivery"],
                        values["rental_deposit_exempt"], values["rental_end_date"],
                        quote_signed_at, invoice_date, invoice_sent_at,
                        paid_at, reminder_one_at, reminder_two_at,
                        (
                            None
                            if invoice_sent_at != record.get("invoice_sent_at")
                            else record.get("payment_overdue_notified_at")
                        ),
                        timestamp, record_id,
                    ),
                )
                database.execute(
                    """
                    UPDATE billing_records SET
                        activity_start_time = ?, activity_end_time = ?,
                        activity_duration_minutes = ?, rate_unit_cents = ?,
                        travel_unit_cents = ?, consumable_unit_cents = ?,
                        rental_contract_fee_cents = ?, rental_delivery_fee_cents = ?,
                        custom_tariff_key = ?, custom_tariff_name = ?
                    WHERE id = ?
                    """,
                    (
                        values["activity_start_time"], values["activity_end_time"],
                        values["activity_duration_minutes"], values["rate_unit_cents"],
                        values["travel_unit_cents"], values["consumable_unit_cents"],
                        values["rental_contract_fee_cents"],
                        values["rental_delivery_fee_cents"],
                        values["custom_tariff_key"], values["custom_tariff_name"], record_id,
                    ),
                )
                updated_record = load_billing_record(database, record_id)
                if updated_record.get("service_id"):
                    synchronize_billing_service(database, updated_record)
                message = f"Le dossier {quote_number} a été mis à jour."
            if resource_context:
                from resource_booking import link_billing
                link_billing(database,resource_key,record_id,'admin')
            database.commit()
            flash(message, "success")
            return redirect(url_for("admin_billing_detail", record_id=record_id))
        except ValueError:
            database.rollback()
            if resource_context:
                abort(409, 'Cette réservation a changé pendant la création du dossier. Rechargez sa fiche.')
            raise
        except sqlite3.IntegrityError:
            database.rollback()
            application.logger.exception("Numérotation de facturation déjà utilisée")
            flash("Ce nom de devis ou de facture est déjà utilisé.", "error")
            return render_template(
                "billing_form.html", values=dict(request.form), record=record,
                rental_catalog=available_rental_catalog(database, record),
                billing_tariffs=load_billing_tariffs(database),
                custom_tariffs=load_custom_tariffs(database, include_inactive=bool(record)),
            ), 409

    @application.get("/admin/api/clients-facturation")
    def admin_billing_clients_api():
        """Fournit les fiches de l'annuaire pour préremplir un devis."""
        rows = get_database().execute(
            """
            SELECT contact_name, structure_name, address_line, postal_code,
                   city, phone, email
            FROM billing_clients
            ORDER BY contact_name COLLATE NOCASE, structure_name COLLATE NOCASE
            """
        ).fetchall()
        clients = [
            {
                "contact": row["contact_name"],
                "structure": row["structure_name"],
                "address_line": row["address_line"],
                "postal_code": row["postal_code"],
                "city": row["city"],
                "phone": row["phone"] or "",
                "email": row["email"] or "",
            }
            for row in rows
        ]
        response = jsonify({"clients": clients})
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @application.get("/admin/facturation/clients/export.<string:output_format>")
    def admin_billing_clients_export(output_format):
        """Exporte toutes les fiches de l'annuaire clients en PDF ou XLSX."""
        if output_format not in {"pdf", "xlsx"}:
            abort(404)
        rows = get_database().execute(
            """
            SELECT billing_clients.*,
                   COUNT(billing_records.id) AS record_count
            FROM billing_clients
            LEFT JOIN billing_records
                ON billing_records.client_id = billing_clients.id
            GROUP BY billing_clients.id
            ORDER BY contact_name COLLATE NOCASE, structure_name COLLATE NOCASE
            """
        ).fetchall()
        clients = [dict(row) for row in rows]
        linked_records = defaultdict(list)
        for row in get_database().execute(
            """
            SELECT client_id, quote_number, invoice_number, title
            FROM billing_records
            WHERE client_id IS NOT NULL
            ORDER BY quote_date, id
            """
        ).fetchall():
            linked_records[row["client_id"]].append({
                "quote_number": row["quote_number"],
                "invoice_number": row["invoice_number"],
                "title": row["title"],
            })
        for client in clients:
            client["linked_records"] = linked_records.get(client["id"], [])
        structure = load_structure_settings(get_database())
        document_bytes = (
            generate_client_directory_pdf(clients, structure)
            if output_format == "pdf"
            else generate_client_directory_xlsx(clients, structure)
        )
        export_date = datetime.now(PARIS_TIMEZONE).strftime("%Y%m%d")
        short_name = compact_filename_part(structure["short_name"], "OpenFabLab")
        filename = f"{export_date}_AnnuaireClients_{short_name}.{output_format}"
        return Response(
            document_bytes,
            mimetype=(
                "application/pdf" if output_format == "pdf"
                else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.route(
        "/admin/facturation/clients/<int:client_id>/modifier",
        methods=["GET", "POST"],
    )
    def admin_billing_client_form(client_id):
        """Permet de corriger la fiche de référence d'un client."""
        database = get_database()
        row = database.execute(
            "SELECT * FROM billing_clients WHERE id = ?", (client_id,)
        ).fetchone()
        if row is None:
            abort(404)
        client = dict(row)
        if request.method == "GET":
            values = {
                "client_contact": client["contact_name"],
                "client_structure": client["structure_name"],
                "address_line": client["address_line"],
                "postal_code": client["postal_code"],
                "city": client["city"],
                "phone": client["phone"] or "",
                "email": client["email"] or "",
            }
            return render_template(
                "billing_client_form.html", client=client, values=values
            )

        values, errors = parse_billing_client_form(request.form)
        normalized_contact = normalize_text_key(values["client_contact"])
        conflicting_client = database.execute(
            """
            SELECT id FROM billing_clients
            WHERE contact_name_normalized = ? AND id <> ?
            """,
            (normalized_contact, client_id),
        ).fetchone() if normalized_contact else None
        if conflicting_client:
            errors.append(
                "Un autre client utilise déjà ce nom de contact. Modifiez sa fiche existante."
            )
        if errors:
            for error in errors:
                flash(error, "error")
            return render_template(
                "billing_client_form.html", client=client, values=values
            ), 400
        try:
            upsert_billing_client(
                database,
                values,
                existing_client_id=client_id,
            )
            database.commit()
        except sqlite3.IntegrityError:
            database.rollback()
            flash(
                "Un autre client utilise déjà ce nom de contact. Modifiez sa fiche existante.",
                "error",
            )
            return render_template(
                "billing_client_form.html", client=client, values=values
            ), 409
        flash("La fiche client a été mise à jour.", "success")
        return redirect(url_for("admin_billing") + "#annuaire-clients")

    @application.get("/admin/facturation/<int:record_id>")
    def admin_billing_detail(record_id):
        record = load_billing_record(get_database(), record_id)
        module_enabled = load_modules(get_database())[
            "rentals" if record["billing_type"] == "rental" else "booking_slots"
        ]
        return render_template("billing_detail.html", record=record, module_enabled=module_enabled)

    @application.post("/admin/facturation/<int:record_id>/signer")
    def admin_billing_sign(record_id):
        database = get_database()
        record = load_billing_record(database, record_id)
        if record.get("quote_cancelled_at"):
            flash("Réouvrez le devis avant de modifier sa signature.", "error")
            return redirect(url_for("admin_billing_detail", record_id=record_id))
        signed = not record.get("quote_signed_at")
        database.execute(
            "UPDATE billing_records SET quote_signed_at = ?, updated_at = ? WHERE id = ?",
            (utc_now_iso() if signed else None, utc_now_iso(), record_id),
        )
        database.commit()
        flash(
            "Le devis est marqué comme signé."
            if signed else "La validation du devis a été retirée.",
            "success",
        )
        return redirect(url_for("admin_billing_detail", record_id=record_id))

    @application.post("/admin/facturation/<int:record_id>/creer-facture")
    def admin_billing_create_invoice(record_id):
        database = get_database()
        record = load_billing_record(database, record_id)
        if record.get("quote_cancelled_at"):
            flash("Un devis annulé doit être réouvert avant de créer sa facture.", "error")
            return redirect(url_for("admin_billing_detail", record_id=record_id))
        if not record.get("quote_signed_at"):
            flash("Le devis doit être marqué comme signé avant la facture.", "error")
            return redirect(url_for("admin_billing_detail", record_id=record_id))
        if record.get("invoice_number"):
            flash("Une facture existe déjà pour ce devis.", "error")
            return redirect(url_for("admin_billing_detail", record_id=record_id))
        today = datetime.now(PARIS_TIMEZONE).strftime("%Y-%m-%d")
        try:
            invoice_number = next_billing_number(
                database, "invoice_number", int(today[:4]),
                rental=record.get("billing_type") == "rental",
            )
            timestamp = utc_now_iso()
            offered = int(record.get("amount_cents") or 0) == 0
            database.execute(
                """
                UPDATE billing_records
                SET invoice_number = ?, invoice_date = ?, invoice_sent_at = ?,
                    paid_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    invoice_number,
                    today,
                    timestamp if offered else None,
                    timestamp if offered else None,
                    timestamp,
                    record_id,
                ),
            )
            updated_record = load_billing_record(database, record_id)
            synchronize_billing_service(database, updated_record)
            database.commit()
            flash(
                (
                    f"La facture {invoice_number} est enregistrée comme offerte."
                    if offered
                    else f"La facture {invoice_number} est prête."
                ),
                "success",
            )
        except sqlite3.IntegrityError:
            database.rollback()
            flash("Le numéro de facture n'a pas pu être attribué. Réessayez.", "error")
        return redirect(url_for("admin_billing_detail", record_id=record_id))

    @application.post("/admin/facturation/<int:record_id>/annulation")
    def admin_billing_toggle_cancellation(record_id):
        """Annule ou réouvre un devis sans supprimer son historique."""
        database = get_database()
        record = load_billing_record(database, record_id)
        if record.get("invoice_number"):
            flash(
                "Une facture existe déjà : supprimez-la d'abord si le dossier "
                "doit revenir à l'étape du devis.",
                "error",
            )
            return redirect(url_for("admin_billing_detail", record_id=record_id))
        reopening = bool(record.get("quote_cancelled_at"))
        database.execute(
            "UPDATE billing_records SET quote_cancelled_at = ?, updated_at = ? "
            "WHERE id = ?",
            (None if reopening else utc_now_iso(), utc_now_iso(), record_id),
        )
        database.commit()
        flash(
            "Le devis est réouvert dans son état précédent."
            if reopening
            else "Le devis est annulé et retiré des devis en attente.",
            "success",
        )
        return redirect(url_for("admin_billing_detail", record_id=record_id))

    @application.post("/admin/facturation/<int:record_id>/envoyer")
    def admin_billing_mark_sent(record_id):
        database = get_database()
        record = load_billing_record(database, record_id)
        if not record.get("invoice_number"):
            flash("Créez d'abord la facture.", "error")
        else:
            database.execute(
                """
                UPDATE billing_records
                SET invoice_sent_at = ?, payment_overdue_notified_at = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (utc_now_iso(), utc_now_iso(), record_id),
            )
            database.commit()
            flash("La facture est marquée comme envoyée.", "success")
        return redirect(url_for("admin_billing_detail", record_id=record_id))

    @application.post("/admin/facturation/<int:record_id>/payer")
    def admin_billing_mark_paid(record_id):
        database = get_database()
        record = load_billing_record(database, record_id)
        if record.get("paid_at"):
            database.execute(
                "UPDATE billing_records SET paid_at = NULL, updated_at = ? WHERE id = ?",
                (utc_now_iso(), record_id),
            )
            database.commit()
            flash("Le règlement a été retiré ; la facture redevient à encaisser.", "success")
        elif not record.get("invoice_sent_at"):
            flash("La facture doit d'abord être marquée comme envoyée.", "error")
        else:
            database.execute(
                "UPDATE billing_records SET paid_at = ?, updated_at = ? WHERE id = ?",
                (utc_now_iso(), utc_now_iso(), record_id),
            )
            database.commit()
            flash("Le règlement est enregistré.", "success")
        return redirect(url_for("admin_billing_detail", record_id=record_id))

    @application.post("/admin/facturation/<int:record_id>/relance/<int:number>")
    def admin_billing_reminder(record_id, number):
        if number not in {1, 2}:
            abort(404)
        database = get_database()
        record = load_billing_record(database, record_id)
        if not record.get("invoice_sent_at") or record.get("paid_at"):
            flash("Une relance concerne uniquement une facture envoyée non réglée.", "error")
        else:
            field = "reminder_one_at" if number == 1 else "reminder_two_at"
            database.execute(
                f"UPDATE billing_records SET {field} = ?, updated_at = ? WHERE id = ?",
                (utc_now_iso(), utc_now_iso(), record_id),
            )
            database.commit()
            flash(f"La relance n° {number} est enregistrée.", "success")
        return redirect(url_for("admin_billing_detail", record_id=record_id))

    @application.post("/admin/facturation/<int:record_id>/supprimer")
    def admin_billing_delete(record_id):
        database = get_database()
        record = load_billing_record(database, record_id)
        if request.form.get("confirmation", "").strip() != "SUPPRIMER":
            flash("Saisissez SUPPRIMER pour confirmer.", "error")
            return redirect(url_for("admin_billing_detail", record_id=record_id))
        if record.get("invoice_number"):
            flash("Un dossier déjà facturé ne peut pas être supprimé.", "error")
            return redirect(url_for("admin_billing_detail", record_id=record_id))
        database.execute("DELETE FROM billing_records WHERE id = ?", (record_id,))
        database.commit()
        flash("Le devis a été supprimé.", "success")
        return redirect(url_for("admin_billing"))

    @application.post("/admin/facturation/<int:record_id>/supprimer-facture")
    def admin_billing_delete_invoice(record_id):
        """Retire uniquement la facture et la prestation statistique liée."""
        database = get_database()
        record = load_billing_record(database, record_id)
        if request.form.get("confirmation", "").strip() != "SUPPRIMER":
            flash("Saisissez SUPPRIMER pour confirmer.", "error")
            return redirect(url_for("admin_billing_detail", record_id=record_id))
        if not record.get("invoice_number"):
            flash("Ce dossier ne contient aucune facture.", "error")
            return redirect(url_for("admin_billing_detail", record_id=record_id))

        service_id = record.get("service_id")
        database.execute(
            """
            UPDATE billing_records
            SET invoice_number = NULL, invoice_date = NULL,
                invoice_sent_at = NULL, paid_at = NULL,
                reminder_one_at = NULL, reminder_two_at = NULL,
                payment_overdue_notified_at = NULL, service_id = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (utc_now_iso(), record_id),
        )
        if service_id:
            database.execute("DELETE FROM fablab_services WHERE id = ?", (service_id,))
        database.commit()
        flash("La facture a été supprimée ; le devis est conservé.", "success")
        return redirect(url_for("admin_billing_detail", record_id=record_id))

    @application.get(
        "/admin/facturation/<int:record_id>/<string:document_kind>.<string:output_format>"
    )
    def admin_billing_document(record_id, document_kind, output_format):
        if document_kind not in {"devis", "facture"} or output_format not in {"pdf", "docx"}:
            abort(404)
        record = load_billing_record(get_database(), record_id)
        internal_kind = "invoice" if document_kind == "facture" else "quote"
        if internal_kind == "invoice" and not record.get("invoice_number"):
            abort(404)
        structure, logo_path, fablab_logo_path, _signature = document_brand_assets(get_database())
        generator = generate_document_pdf if output_format == "pdf" else generate_document_docx
        document_bytes = generator(
            record, internal_kind, logo_path, fablab_logo_path, structure
        )
        number = record["invoice_number"] if internal_kind == "invoice" else record["quote_number"]
        document_date = record.get("invoice_date") if internal_kind == "invoice" else record.get("quote_date")
        structure = compact_filename_part(
            record.get("client_structure") or record.get("client_contact"), "Client"
        )
        kind_label = "Facture" if internal_kind == "invoice" else "Devis"
        filename = (
            f"{compact_french_date(document_date)}_{kind_label}_{structure}_FABLAB_"
            f"{billing_reference_suffix(number)}.{output_format}"
        )
        return Response(
            document_bytes,
            mimetype=(
                "application/pdf" if output_format == "pdf"
                else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.get("/admin/facturation/facdepot/<int:year>.<string:output_format>")
    def admin_billing_facdepot(year, output_format):
        if year < 2000 or year > 2200 or output_format not in {"pdf", "xlsx"}:
            abort(404)
        rows = get_database().execute(
            """
            SELECT * FROM billing_records
            WHERE invoice_number IS NOT NULL AND substr(invoice_date, 1, 4) = ?
            ORDER BY invoice_date, id
            """,
            (str(year),),
        ).fetchall()
        records = [billing_record_dict(row) for row in rows]
        structure, _institution, _main, signature_path = document_brand_assets(get_database())
        document_bytes = (
            generate_facdepot_pdf(records, year, signature_path, structure)
            if output_format == "pdf"
            else generate_facdepot_xlsx(records, year, signature_path, structure)
        )
        export_date = datetime.now(PARIS_TIMEZONE).strftime("%m%d%Y")
        filename = f"{export_date}_BilanFacturation{year}.{output_format}"
        return Response(
            document_bytes,
            mimetype=(
                "application/pdf" if output_format == "pdf"
                else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.route("/admin/rapport-activite/<int:year>/modifier", methods=["GET", "POST"])
    def admin_activity_report_form(year):
        if year < 2000 or year > 2200:
            abort(404)
        database = get_database()
        existing = database.execute(
            "SELECT * FROM annual_activity_reports WHERE year = ?", (year,)
        ).fetchone()
        report = dict(existing) if existing else {
            "year": year,
            "introduction": "",
            "highlights": "",
            "new_equipment": "",
            "changes": "",
            "partnerships": "",
            "additional_notes": "",
        }
        if request.method == "POST":
            fields = (
                "introduction", "highlights", "new_equipment", "changes",
                "partnerships", "additional_notes",
            )
            values = {field: request.form.get(field, "").strip() for field in fields}
            if any(len(value) > 12000 for value in values.values()):
                flash("Chaque rubrique est limitée à 12 000 caractères.", "error")
                report.update(values)
                return render_template(
                    "annual_report_form.html", report=report,
                    statistics=load_statistics(database, year),
                ), 400
            timestamp = utc_now_iso()
            database.execute(
                """
                INSERT INTO annual_activity_reports (
                    year, introduction, highlights, new_equipment, changes,
                    partnerships, additional_notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(year) DO UPDATE SET
                    introduction = excluded.introduction,
                    highlights = excluded.highlights,
                    new_equipment = excluded.new_equipment,
                    changes = excluded.changes,
                    partnerships = excluded.partnerships,
                    additional_notes = excluded.additional_notes,
                    updated_at = excluded.updated_at
                """,
                (
                    year, values["introduction"], values["highlights"],
                    values["new_equipment"], values["changes"],
                    values["partnerships"], values["additional_notes"],
                    existing["created_at"] if existing else timestamp, timestamp,
                ),
            )
            database.commit()
            flash(f"Le rapport d'activité {year} a été enregistré.", "success")
            return redirect(url_for("admin_activity_report_form", year=year))
        return render_template(
            "annual_report_form.html", report=report,
            statistics=load_statistics(database, year),
        )

    @application.get("/admin/rapport-activite/<int:year>.<string:output_format>")
    def admin_activity_report_document(year, output_format):
        if year < 2000 or year > 2200 or output_format not in {"pdf", "docx"}:
            abort(404)
        database = get_database()
        row = database.execute(
            "SELECT * FROM annual_activity_reports WHERE year = ?", (year,)
        ).fetchone()
        if row is None:
            flash("Enregistrez d'abord le contenu du rapport annuel.", "error")
            return redirect(url_for("admin_activity_report_form", year=year))
        report = dict(row)
        statistics = load_statistics(database, year)
        generator = (
            generate_activity_report_pdf if output_format == "pdf"
            else generate_activity_report_docx
        )
        content = generator(report, statistics, structure=load_structure_settings(database))
        export_date = datetime.now(PARIS_TIMEZONE).strftime("%m%d%Y")
        filename = f"{export_date}_RapportActivite{year}.{output_format}"
        return Response(
            content,
            mimetype=(
                "application/pdf" if output_format == "pdf"
                else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.route("/admin/notifications", methods=["GET", "POST"])
    def admin_notifications_legacy():
        if request.method == "POST":
            return admin_notifications()
        return redirect(url_for("admin_notifications"))

    @application.route("/admin/reglages/notifications", methods=["GET", "POST"])
    def admin_notifications():
        """Configure les notifications Discord sans afficher le secret."""
        database = get_database()
        if request.method == "POST":
            current_settings = load_discord_settings(database)
            webhook_url = request.form.get("webhook_url", "").strip()
            if request.form.get('webhook_only') == '1':
                from evolution_routes import require_csrf
                require_csrf()
                try:
                    if request.form.get('clear_webhook') == '1':
                        clear_discord_webhook()
                    elif webhook_url:
                        write_discord_webhook(webhook_url)
                    flash('Webhook enregistré ; les autres réglages restent inchangés.', 'success')
                except (OSError, ValueError):
                    flash('Webhook refusé. Vérifiez son adresse.', 'error')
                return redirect(url_for('admin_notifications'))
            try:
                bot_name = validate_discord_text(
                    request.form.get("bot_name", current_settings["bot_name"]),
                    "Le nom du bot",
                    80,
                    DISCORD_DEFAULTS["bot_name"],
                )
                message_settings = {
                    "discord_message_arrival": validate_discord_text(
                        request.form.get(
                            "arrival_message", current_settings["arrival_message"]
                        ),
                        "Le message d’arrivée",
                        500,
                        DISCORD_DEFAULTS["arrival_message"],
                    ),
                    "discord_message_departure": validate_discord_text(
                        request.form.get(
                            "departure_message", current_settings["departure_message"]
                        ),
                        "Le message de départ",
                        500,
                        DISCORD_DEFAULTS["departure_message"],
                    ),
                    "discord_message_visitor": validate_discord_text(
                        request.form.get(
                            "visitor_message", current_settings["visitor_message"]
                        ),
                        "Le message visiteur",
                        500,
                        DISCORD_DEFAULTS["visitor_message"],
                    ),
                    "discord_message_retention": validate_discord_text(
                        request.form.get(
                            "retention_message", current_settings["retention_message"]
                        ),
                        "Le message de conservation",
                        500,
                        DISCORD_DEFAULTS["retention_message"],
                    ),
                    "discord_message_invoice_overdue": validate_discord_text(
                        request.form.get(
                            "invoice_overdue_message",
                            current_settings["invoice_overdue_message"],
                        ),
                        "Le rappel de facture impayée",
                        500,
                        DISCORD_DEFAULTS["invoice_overdue_message"],
                    ),
                    "discord_message_monthly_animations": validate_discord_text(
                        request.form.get(
                            "monthly_animations_message",
                            current_settings["monthly_animations_message"],
                        ),
                        "Le rappel mensuel des animations et sauvegarde",
                        500,
                        DISCORD_DEFAULTS["monthly_animations_message"],
                    ),
                }
                if request.form.get("clear_webhook") == "1":
                    clear_discord_webhook()
                elif webhook_url:
                    write_discord_webhook(webhook_url)
            except (OSError, ValueError) as error:
                flash(str(error), "error")
                return redirect(url_for("admin_notifications"))

            configured = bool(read_discord_webhook())
            enabled = request.form.get("enabled") == "1"
            if enabled and not configured:
                flash("Ajoutez d'abord une adresse de webhook Discord valide.", "error")
                enabled = False
            write_setting(database, "discord_notifications_enabled", "1" if enabled else "0")
            write_setting(database, "discord_notify_arrivals", "1" if request.form.get("arrivals") == "1" else "0")
            write_setting(database, "discord_notify_departures", "1" if request.form.get("departures") == "1" else "0")
            write_setting(database, "discord_notify_visitors", "1" if request.form.get("visitors") == "1" else "0")
            write_setting(database, "discord_notify_retention", "1" if request.form.get("retention") == "1" else "0")
            write_setting(
                database,
                "discord_notify_invoice_overdue",
                "1" if request.form.get("invoice_overdue") == "1" else "0",
            )
            write_setting(
                database,
                "discord_notify_monthly_animations",
                "1" if request.form.get("monthly_animations") == "1" else "0",
            )
            write_setting(database, "discord_notify_invalid_ids", "1" if request.form.get("invalid_ids") == "1" else "0")
            for name in RESERVATION_DISCORD_FLAGS:
                write_setting(database, f"discord_reservation_{name}",
                              "1" if request.form.get(f"reservation_{name}") == "1" else "0")
            write_setting(database, "discord_bot_name", bot_name)
            for setting_key, setting_value in message_settings.items():
                write_setting(database, setting_key, setting_value)
            database.commit()
            flash("Les notifications ont été configurées.", "success")
            return redirect(url_for("admin_notifications"))
        return render_template(
            "notifications.html", discord=load_discord_settings(database),
            creation_discord={key:read_setting(database,'discord_new_user_'+key,'0')=='1'
                             for key in ('enabled','first_name','last_name','last_initial','age','category','source','time')}
        )

    @application.post("/admin/notifications/test")
    def admin_test_notification():
        database = get_database()
        webhook_url = read_discord_webhook()
        if not webhook_url:
            flash("Aucun webhook Discord n'est configuré.", "error")
            return redirect(url_for("admin_notifications"))
        try:
            post_discord_message(
                webhook_url,
                "✅ Test réussi : OpenFabLab peut envoyer ses notifications.",
                load_discord_settings(database)["bot_name"],
            )
            flash("La notification de test a été envoyée.", "success")
        except (OSError, urllib.error.URLError, ValueError):
            application.logger.warning("Test Discord impossible")
            flash("Discord n'a pas pu être joint. Vérifiez le webhook et la connexion du NAS.", "error")
        return redirect(url_for("admin_notifications"))

    @application.get("/admin/statistiques")
    def admin_statistics_legacy():
        return redirect(url_for("admin_statistics", **request.args))

    @application.get("/admin/frequentation/statistiques")
    def admin_statistics():
        database = get_database()
        selected_year = parse_requested_year(
            request.args.get("year"), allow_total=True
        )
        statistics = load_statistics(database, selected_year)
        show_inactive = request.args.get('show_inactive') == '1'
        active_keys = {r['category_key'] for r in categories(database)}
        hidden_rows = [r for r in statistics['category_rows'] if r['key'] not in active_keys]
        statistics['hidden_category_people'] = sum(r['count'] for r in hidden_rows)
        statistics['show_inactive_categories'] = show_inactive
        if not show_inactive:
            statistics['category_rows'] = [r for r in statistics['category_rows'] if r['key'] in active_keys]
        return render_template("statistics.html", **statistics)
        

    @application.get("/admin/frequentation/exports")
    def admin_frequency_exports():
        """Regroupe les exports de fréquentation sans les exposer au modérateur."""
        database = get_database()
        selected_year = parse_requested_year(
            request.args.get("year"), allow_total=True
        )
        statistics = load_statistics(database, selected_year)
        return render_template(
            "frequency_exports.html",
            selected_year=selected_year,
            selected_period_label=statistics["selected_period_label"],
            available_years=statistics["available_years"],
            is_total_period=statistics["is_total_period"],
        )

    def export_users(category=None):
        """Exporte tout le répertoire ou une catégorie particulière."""
        database = get_database()
        parameters = []
        category_clause = ""
        if category:
            category_clause = "WHERE users.category = ?"
            parameters.append(category)
        users_to_export = database.execute(
            f"""
            SELECT users.public_id, users.first_name, users.last_name,
                   users.category, users.active, users.birth_year, users.gender,
                   users.city, users.postal_code, users.nationality,
                   users.email, users.phone_country_code, users.phone,
                   users.created_at,
                   COUNT(sessions.id) AS visit_count
            FROM users
            LEFT JOIN sessions ON sessions.user_id = users.id
            {category_clause}
            GROUP BY users.id
            ORDER BY users.last_name COLLATE NOCASE,
                     users.first_name COLLATE NOCASE
            """,
            parameters,
        ).fetchall()
        rows = [
            (
                user["public_id"],
                user["last_name"],
                user["first_name"],
                dynamic_category_label(get_database(),user['category']),
                "Actif" if user["active"] else "Inactif",
                user["birth_year"] or "",
                GENDER_LABELS.get(user["gender"], "Inconnu"),
                user["city"] or "",
                user["postal_code"] or "",
                user["nationality"] or "",
                user["email"] or "",
                (
                    f"{user['phone_country_code'] or '+33'} {user['phone']}"
                    if user["phone"] else ""
                ),
                user["visit_count"],
                parse_timestamp(user["created_at"])
                .astimezone(PARIS_TIMEZONE)
                .strftime("%d/%m/%Y"),
            )
            for user in users_to_export
        ]
        filename = "benevoles.csv" if category == "volunteer" else "usagers.csv"
        return csv_download(
            filename,
            (
                "Identifiant",
                "Nom",
                "Prénom",
                "Catégorie",
                "Statut",
                "Année de naissance",
                "Genre renseigné",
                "Commune",
                "Code postal",
                "Nationalité",
                "E-mail",
                "Téléphone",
                "Nombre de visites",
                "Date d'inscription",
            ),
            rows,
        )

    @application.get("/admin/exports/usagers.csv")
    def admin_export_users():
        return export_users()

    @application.get("/admin/exports/benevoles.csv")
    def admin_export_volunteers():
        return export_users("volunteer")

    @application.get("/admin/exports/presences.csv")
    def admin_export_sessions():
        database = get_database()
        selected_year = parse_requested_year(
            request.args.get("year"), allow_total=True
        )
        statistics = load_statistics(database, selected_year)
        rows = []
        for item in statistics["selected_sessions"]:
            presence = item["row"]
            arrival = item["check_in"].astimezone(PARIS_TIMEZONE)
            departure = (
                parse_timestamp(presence["check_out"]).astimezone(PARIS_TIMEZONE)
                if presence["check_out"]
                else None
            )
            rows.append(
                (
                    presence["public_id"],
                    presence["last_name"],
                    presence["first_name"],
                    dynamic_category_label(get_database(),presence['category']),
                    arrival.strftime("%d/%m/%Y %H:%M"),
                    departure.strftime("%d/%m/%Y %H:%M")
                    if departure
                    else "Présent",
                    round(item["duration_seconds"] / 60)
                    if item["duration_seconds"] is not None
                    else "",
                    presence_method_label(presence["entry_method"]),
                    presence_method_label(presence["exit_method"]),
                )
            )
        return csv_download(
            f"presences-{selected_year}.csv",
            (
                "Identifiant",
                "Nom",
                "Prénom",
                "Catégorie",
                "Arrivée",
                "Départ",
                "Durée (minutes)",
                "Méthode d'entrée",
                "Méthode de sortie",
            ),
            rows,
        )

    @application.get("/admin/exports/statistiques.csv")
    def admin_export_statistics():
        database = get_database()
        selected_year = parse_requested_year(
            request.args.get("year"), allow_total=True
        )
        statistics = load_statistics(database, selected_year)
        summary = statistics["selected_summary"]
        period_section = (
            "Total" if statistics["is_total_period"] else f"Année {selected_year}"
        )
        rows = [
            (period_section, "Passages totaux", summary["total"]),
            (period_section, "Sessions d'usagers", summary["sessions"]),
            (period_section, "Visiteurs anonymes", summary["visitors"]),
            (period_section, "Usagers uniques", summary["unique_users"]),
            (period_section, "OpenLabs effectués", summary["open_lab_days"]),
            (period_section, "Heures de présence", summary["hours"]),
            (
                period_section,
                "Durée moyenne d'une visite terminée (minutes)",
                summary["average_minutes"],
            ),
            (
                period_section,
                "Âge moyen approximatif",
                statistics["mean_age"] if statistics["mean_age"] is not None else "",
            ),
            (period_section, "Animations", statistics["service_statistics"]["animations"]),
            (period_section, "Participants aux animations", statistics["service_statistics"]["animation_participants"]),
            (period_section, "Créneaux réservables", statistics["service_statistics"]["reservations"]),
            (period_section, "Participants aux réservations", statistics["service_statistics"]["reservation_participants"]),
            (period_section, "Locations de machines", statistics["service_statistics"]["rentals"]),
            (period_section, "Recettes des réservations et locations (€)", statistics["service_statistics"]["revenue"]),
        ]
        for section, distribution in (
            ("Genre", statistics["gender_rows"]),
            ("Tranche d'âge", statistics["age_rows"]),
            ("Commune", statistics["city_export_rows"]),
            ("Nationalité", statistics["nationality_export_rows"]),
            ("Catégorie", statistics["category_rows"]),
        ):
            for row in distribution:
                rows.append(
                    (
                        section,
                        row["label"],
                        f"{row['count']} ({str(row['percentage']).replace('.', ',')} %)"
                    )
                )
        for row in statistics["category_rows"]:
            rows.append(
                (
                    "Temps moyen par catégorie",
                    row["label"],
                    f"{row['average_minutes']} min"
                    if row["average_minutes"] is not None
                    else "",
                )
            )
        for rank, weekday in enumerate(statistics["busiest_weekdays"], start=1):
            rows.append(
                (
                    "Jours d'OpenLab les plus fréquentés",
                    f"{rank}. {weekday['label']}",
                    (
                        f"{weekday['open_labs']} OpenLabs ; "
                        f"{str(weekday['average_users']).replace('.', ',')} usagers en moyenne ; "
                        f"{str(weekday['average_visitors']).replace('.', ',')} visiteurs en moyenne"
                    ),
                )
            )
        for day in statistics["openlab_attendance"]["days"]:
            for bar in day["bars"]:
                rows.append(
                    (
                        f"Affluence par quart d'heure · {day['label']}",
                        f"{bar['start']}–{bar['end']}",
                        (
                            f"{str(bar['average_users']).replace('.', ',')} usager(s) en moyenne ; "
                            f"{str(bar['average_visitors']).replace('.', ',')} arrivée(s) "
                            "de visiteurs en moyenne"
                        ),
                    )
                )
        for year in statistics["history"]:
            rows.extend(
                [
                    (f"Historique {year['year']}", "Passages totaux", year["total"]),
                    (f"Historique {year['year']}", "Sessions d'usagers", year["sessions"]),
                    (f"Historique {year['year']}", "Visiteurs anonymes", year["visitors"]),
                    (f"Historique {year['year']}", "Usagers uniques", year["unique_users"]),
                    (f"Historique {year['year']}", "OpenLabs effectués", year["open_lab_days"]),
                    (f"Historique {year['year']}", "Heures de présence", year["hours"]),
                ]
            )
        return csv_download(
            f"statistiques-{selected_year}.csv",
            ("Section", "Indicateur", "Valeur"),
            rows,
        )

    @application.get("/admin/exports/animations.csv")
    def admin_export_animations():
        selected_year = parse_requested_year(
            request.args.get("year"), allow_total=True
        )
        year_clause = (
            "" if selected_year == "total" else "AND substr(service_date, 1, 4) = ?"
        )
        parameters = () if selected_year == "total" else (str(selected_year),)
        rows = get_database().execute(
            f"""
            SELECT title, service_date, start_time, end_time, duration_minutes,
                   minimum_age, description, expected_participants, actual_participants
            FROM fablab_services
            WHERE service_type = 'animation' {year_clause}
            ORDER BY service_date, id
            """,
            parameters,
        ).fetchall()
        return csv_download(
            f"animations-{selected_year}.csv",
            ("Titre", "Date", "Début", "Fin", "Durée (minutes)", "Âge minimum", "Description", "Places maximum", "Usagers présents"),
            [
                (
                    row["title"],
                    datetime.strptime(row["service_date"], "%Y-%m-%d").strftime("%d/%m/%Y"),
                    row["start_time"] or "", row["end_time"] or "",
                    row["duration_minutes"] or "", row["minimum_age"],
                    row["description"] or "",
                    row["expected_participants"],
                    row["actual_participants"],
                )
                for row in rows
            ],
        )

    @application.get("/admin/exports/reservations-locations.csv")
    def admin_export_paid_services():
        selected_year = parse_requested_year(
            request.args.get("year"), allow_total=True
        )
        year_clause = (
            "" if selected_year == "total" else "AND substr(service_date, 1, 4) = ?"
        )
        parameters = () if selected_year == "total" else (str(selected_year),)
        rows = get_database().execute(
            f"""
            SELECT service_type, invoice_reference, client_name, title,
                   service_date, start_time, end_time, duration_minutes,
                   participants, amount_cents
            FROM fablab_services
            WHERE service_type IN ('reservation', 'rental')
              {year_clause}
            ORDER BY service_date, id
            """,
            parameters,
        ).fetchall()
        return csv_download(
            f"reservations-locations-{selected_year}.csv",
            ("Type", "Facture", "Structure ou personne", "Créneau ou machine", "Date", "Début", "Fin", "Durée (minutes)", "Participants", "Tarif facturé (€)"),
            [
                (
                    "Créneau réservable" if row["service_type"] == "reservation" else "Location de machine",
                    row["invoice_reference"], row["client_name"], row["title"],
                    datetime.strptime(row["service_date"], "%Y-%m-%d").strftime("%d/%m/%Y"),
                    row["start_time"] or "", row["end_time"] or "",
                    row["duration_minutes"] or "",
                    row["participants"] if row["service_type"] == "reservation" else "",
                    f"{(row['amount_cents'] or 0) / 100:.2f}".replace(".", ","),
                )
                for row in rows
            ],
        )

    @application.get("/admin/api/communes")
    def admin_communes_api():
        """Suggère les communes officielles correspondant à un code postal."""
        postal_code = request.args.get("code_postal", "").strip()
        if not re.fullmatch(r"\d{5}", postal_code):
            return jsonify({"communes": [], "available": True})
        communes, available = load_communes_by_postal_code(postal_code)
        response = jsonify({"communes": communes, "available": available})
        response.headers["Cache-Control"] = "private, max-age=86400"
        return response

    @application.route("/admin/usagers/nouveau", methods=["GET", "POST"])
    def admin_add_user():
        database = get_database()
        if request.method == "GET":
            empty_user = {
                "public_id": next_available_public_id(database),
                "first_name": "",
                "last_name": "",
                "birth_year": None,
                "gender": None,
                "city": "",
                "postal_code": "",
                "nationality": "",
                "email": "",
                "phone_country_code": "+33",
                "phone": "",
                "category": default_category(database),
                "active": 1,
            }
            return render_template(
                "user_form.html",
                user=empty_user,
                form_mode="create",
                errors=[],
                duplicate_users=[],
                country_names=COUNTRY_NAMES,
            )

        user_data, errors = validate_user_form(request.form, database)
        if errors:
            return render_template(
                "user_form.html",
                user=user_data,
                form_mode="create",
                errors=errors,
                duplicate_users=[],
                country_names=COUNTRY_NAMES,
            ), 400

        duplicate_users = find_possible_user_duplicates(database, user_data)
        if duplicate_users and request.form.get("confirm_duplicates") != "1":
            return render_template(
                "user_form.html", user=user_data, form_mode="create",
                errors=[], duplicate_users=duplicate_users, country_names=COUNTRY_NAMES,
            )

        try:
            cursor = database.execute(
                """
                INSERT INTO users (
                    public_id, first_name, last_name, active, category,
                    birth_year, gender, city, city_normalized, postal_code,
                    nationality, nationality_normalized, email,
                    phone_country_code, phone,
                    statistics_key, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_data["public_id"],
                    user_data["first_name"],
                    user_data["last_name"],
                    user_data["active"],
                    user_data["category"],
                    user_data["birth_year"],
                    user_data["gender"],
                    user_data["city"],
                    user_data["city_normalized"],
                    user_data["postal_code"],
                    user_data["nationality"],
                    user_data["nationality_normalized"],
                    user_data["email"],
                    user_data["phone_country_code"],
                    user_data["phone"],
                    secrets.token_hex(16),
                    utc_now_iso(),
                    utc_now_iso(),
                ),
            )
            source = session.get('access_role') or 'admin'
            database.execute('UPDATE users SET created_source=?,created_by_role=? WHERE id=?', (source,source,cursor.lastrowid))
            from family_model import apply_details
            apply_details(database,cursor.lastrowid,user_data)
            database.commit()
            from evolution_routes import after_creation
            after_creation(__import__('types').SimpleNamespace(**globals()),database,cursor.lastrowid,request.form.get('send_welcome')=='1')
            flash(
                f"L'usager {user_data['first_name']} {user_data['last_name']} a été créé avec l'identifiant {user_data['public_id']}.",
                "success",
            )
        except (sqlite3.Error, ValueError):
            database.rollback()
            application.logger.exception("Erreur lors de la création d'un usager")
            flash("L'usager n'a pas pu être créé. Merci de réessayer.", "error")
            return redirect(url_for("admin_add_user"))

        return redirect(url_for("admin_users_directory"))

    @application.route(
        "/admin/usagers/<int:user_id>/modifier", methods=["GET", "POST"]
    )
    def admin_edit_user(user_id):
        database = get_database()
        user = database.execute(
            """
            SELECT *
            FROM users WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
        if user is None:
            abort(404)

        if request.method == "GET":
            age_year = datetime.now(PARIS_TIMEZONE).year if session.get("access_role") == "admin" else None
            return render_template(
                "user_form.html",
                user=user,
                form_mode="edit",
                errors=[],
                age_year=age_year,
                age_in_year=(age_year - user["birth_year"]) if age_year and user["birth_year"] else None,
                country_names=COUNTRY_NAMES,
            )

        user_data, errors = validate_user_form(request.form, database, user_id)
        if errors:
            user_data["id"] = user_id
            age_year = datetime.now(PARIS_TIMEZONE).year if session.get("access_role") == "admin" else None
            return render_template(
                "user_form.html",
                user=user_data,
                form_mode="edit",
                errors=errors,
                age_year=age_year,
                age_in_year=(age_year - user_data["birth_year"]) if age_year and isinstance(user_data["birth_year"], int) else None,
                country_names=COUNTRY_NAMES,
            ), 400

        try:
            database.execute(
                """
                UPDATE users
                SET public_id = ?, first_name = ?, last_name = ?, active = ?,
                    category = ?, birth_year = ?, gender = ?, city = ?,
                    city_normalized = ?, postal_code = ?, nationality = ?,
                    nationality_normalized = ?, email = ?,
                    phone_country_code = ?, phone = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    user_data["public_id"],
                    user_data["first_name"],
                    user_data["last_name"],
                    user_data["active"],
                    user_data["category"],
                    user_data["birth_year"],
                    user_data["gender"],
                    user_data["city"],
                    user_data["city_normalized"],
                    user_data["postal_code"],
                    user_data["nationality"],
                    user_data["nationality_normalized"],
                    user_data["email"],
                    user_data["phone_country_code"],
                    user_data["phone"],
                    utc_now_iso(),
                    user_id,
                ),
            )
            from family_model import apply_details
            apply_details(database,user_id,user_data)
            database.commit()
            flash(
                f"La fiche de {user_data['first_name']} {user_data['last_name']} a été mise à jour.",
                "success",
            )
        except (sqlite3.Error, ValueError):
            database.rollback()
            application.logger.exception("Erreur lors de la modification d'un usager")
            flash("La fiche n'a pas pu être modifiée. Merci de réessayer.", "error")
            return redirect(url_for("admin_edit_user", user_id=user_id))

        return redirect(url_for("admin_users_directory"))

    @application.post("/admin/usagers/<int:user_id>/supprimer")
    def admin_delete_user(user_id):
        database = get_database()
        user = database.execute(
            "SELECT id, first_name, last_name FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if user is None:
            abort(404)

        session_count = database.execute(
            "SELECT COUNT(*) FROM sessions WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        if session_count:
            flash(
                "Cet usager possède un historique et ne peut pas être supprimé. Rendez-le inactif pour conserver les statistiques.",
                "error",
            )
            return redirect(url_for("admin_edit_user", user_id=user_id))

        try:
            database.execute("DELETE FROM users WHERE id = ?", (user_id,))
            database.commit()
            flash(
                f"L'usager {user['first_name']} {user['last_name']} a été supprimé.",
                "success",
            )
        except sqlite3.Error:
            database.rollback()
            application.logger.exception("Erreur lors de la suppression d'un usager")
            flash("L'usager n'a pas pu être supprimé.", "error")

        return redirect(url_for("admin_users_directory"))


def register_error_handlers(application):
    """Affiche des pages simples sans exposer de détails techniques."""

    @application.errorhandler(404)
    def page_not_found(_error):
        return render_template(
            "error.html",
            title="Page introuvable",
            message="La page demandée n'existe pas ou n'est plus disponible.",
        ), 404

    @application.errorhandler(500)
    def internal_error(_error):
        return render_template(
            "error.html",
            title="Un problème est survenu",
            message="L'application a rencontré une erreur. Merci de réessayer.",
        ), 500


flask_app = create_app()
app = create_deployment_application(flask_app)


def run_local_server(application, port):
    """La commande python app.py active la synchronisation Test en local."""
    # Le planificateur complet, s'il est activé, assure déjà cette synchronisation.
    if not application.config["AUTO_CLOSURE_WORKER"]:
        start_local_reservation_sync_worker(application)
    application.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    # Le port 5000 est souvent réservé par AirPlay sur macOS.
    port = int(os.environ.get("OPENFABLAB_PORT", os.environ.get("COMPTEUR_PORT", "5001")))
    run_local_server(flask_app, port)
