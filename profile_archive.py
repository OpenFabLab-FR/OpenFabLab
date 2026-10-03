"""Private, versioned OpenFabLab configuration profile (no business data or secrets)."""

import hashlib
import io
import json
import re
import zipfile
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


FORMAT = "openfablab-profile"
VERSION = 1
MAX_ARCHIVE_BYTES = 6 * 1024 * 1024
MAX_ASSET_BYTES = 2 * 1024 * 1024
ASSET_NAMES = {"assets/main.png", "assets/institution.png", "assets/signature.png", "assets/wordmark.png",
               "assets/header_institution.png", "assets/network.png", "assets/badge-template.svg"}
STRUCTURE_KEYS = {
    "name", "short_name", "description", "address", "city", "postal_code",
    "email", "phone", "website", "country", "timezone", "latitude", "longitude", "color", "privacy_policy_url",
    "legal_entity", "billing_address", "siret", "vat_number", "vat_note",
    "iban", "bic", "account_holder", "payment_terms", "payment_days",
    "regie_contact", "signer_name", "rental_terms",
    "main_logo", "institution_logo", "signature", "wordmark_logo", "header_institution_logo", "network_logo",
    "show_wordmark_logo", "show_header_institution_logo", "show_network_logo", "badge_template",
    "use_main_logo", "use_signature", "use_badge_template", "dpo", "dpo_email", "dpo_phone",
    "data_controller", "data_controller_address", "data_controller_representative", "data_controller_representative_role",
}
MODULE_KEYS = {
    "frequency", "users", "activities", "public_reservations", "booking_slots",
    "rentals", "billing", "weather", "discord",
    'resources', 'authorizations',
}
BILLING_KEYS = {
    "billing_rate_normal_hourly_cents", "billing_rate_normal_half_day_cents",
    "billing_rate_reduced_hourly_cents", "billing_rate_reduced_half_day_cents",
    "billing_travel_unit_cents", "billing_consumable_unit_cents",
    "billing_rental_contract_fee_cents", "billing_rental_delivery_fee_cents",
}
EXACT_KEYS = {
    "home_theme", "keep_screen_awake", "lock_home_scroll", "wake_lock_start",
    "wake_lock_end", "openlab_attendance_show_decimals",
    'calendar_display_start', 'calendar_display_end',
    "retention_contact_years", "retention_deactivation_years", "retention_deletion_years",
    "automatic_closure_enabled", "invalid_id_threshold", "invalid_id_window_minutes",
    "invalid_id_lock_enabled", "invalid_id_lock_minutes",
    "discord_notifications_enabled", "discord_bot_name",
    'self_enrollment_enabled', 'welcome_default', 'welcome_subject', 'welcome_body',
    'discord_new_user_enabled', 'discord_new_user_first_name', 'discord_new_user_last_name',
    'discord_new_user_last_initial', 'discord_new_user_age', 'discord_new_user_category',
    'discord_new_user_source', 'discord_new_user_time',
}
DISCORD_MESSAGE_KEYS = {
    "discord_message_arrival", "discord_message_departure", "discord_message_visitor",
    "discord_message_retention", "discord_message_invoice_overdue",
    "discord_message_monthly_animations",
}
DISCORD_NOTIFY_KEYS = {
    "discord_notify_arrivals", "discord_notify_departures", "discord_notify_visitors",
    "discord_notify_retention", "discord_notify_invoice_overdue",
    "discord_notify_monthly_animations", "discord_notify_invalid_ids",
}
DISCORD_RESERVATION_KEYS = {
    "discord_reservation_new_booking", "discord_reservation_waitlist_entry",
    "discord_reservation_cancellation", "discord_reservation_offer_proposed",
    "discord_reservation_offer_accepted", "discord_reservation_link_review",
    "discord_reservation_animation_full", "discord_reservation_email_error",
    "discord_reservation_sync_error",
}
RESERVATION_RANGES = {
    "reservation_minimum_age": (0, 120),
    "reservation_accompaniment_under_age": (0, 120),
    "reservation_offer_hours": (1, 168),
    "reservation_last_offer_hours": (1, 168),
    "reservation_close_minutes": (0, 1440),
    "reservation_reminder_one_hours": (0, 168),
    "reservation_reminder_two_hours": (0, 168),
    "reservation_sync_interval_minutes": (1, 60),
}


def allowed_setting(key):
    """Use a narrow allowlist; never export a newly added secret by accident."""
    if key in EXACT_KEYS:
        return True
    if key.startswith("structure_"):
        return key.removeprefix("structure_") in STRUCTURE_KEYS
    if key.startswith("module_"):
        return key.removeprefix("module_") in MODULE_KEYS
    if key.startswith("billing_"):
        return key in BILLING_KEYS
    if key.startswith("reservation_"):
        return key in {
            "reservation_minimum_age", "reservation_accompaniment_under_age",
            "reservation_waitlist_enabled", "reservation_offer_hours",
            "reservation_last_offer_hours", "reservation_close_minutes",
            "reservation_reminder_one_hours", "reservation_reminder_two_hours",
            "reservation_sync_interval_minutes",
        }
    if key in DISCORD_MESSAGE_KEYS | DISCORD_NOTIFY_KEYS | DISCORD_RESERVATION_KEYS:
        return True
    if key.startswith("openlab_attendance_"):
        return re.fullmatch(r"openlab_attendance_(monday|tuesday|wednesday|thursday|friday|saturday|sunday)_(start|end)", key) is not None
    if key.startswith("automatic_closure_"):
        return key.removeprefix("automatic_closure_") in {
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
        }
    return False


def build_profile(settings, machines, assets, tariffs=None, categories=None, resource_types=None):
    safe_settings = {key: value for key, value in settings.items() if allowed_setting(key)}
    if not all(isinstance(value, str) for value in safe_settings.values()):
        raise ValueError("Réglage du profil invalide.")
    if not set(assets).issubset(ASSET_NAMES):
        raise ValueError("Ressource du profil non autorisée.")
    manifest = {
        "format": FORMAT, "version": VERSION,
        "settings": safe_settings,
        "machines": machines,
        "tariffs": tariffs or [],
        'categories': categories or [], 'resource_types': resource_types or [],
        "assets": {name: hashlib.sha256(raw).hexdigest() for name, raw in assets.items()},
    }
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("profile.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True))
        for name, raw in assets.items():
            archive.writestr(name, raw)
    if memory.tell() > MAX_ARCHIVE_BYTES:
        raise ValueError("Le profil est trop volumineux.")
    return memory.getvalue()


def parse_profile(raw):
    if len(raw) > MAX_ARCHIVE_BYTES or not raw.startswith(b"PK"):
        raise ValueError("Le fichier n'est pas un profil ZIP OpenFabLab valide.")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            if (len(names) != len(set(names)) or "profile.json" not in names or
                    not set(names).issubset(ASSET_NAMES | {"profile.json"}) or
                    any(member.file_size > MAX_ASSET_BYTES for member in members)):
                raise ValueError("Le profil contient des ressources non autorisées.")
            manifest = json.loads(archive.read("profile.json"))
            if manifest.get("format") != FORMAT or manifest.get("version") != VERSION:
                raise ValueError("Format ou version de profil incompatible.")
            settings = manifest.get("settings")
            machines = manifest.get("machines")
            tariffs = manifest.get("tariffs")
            digests = manifest.get("assets")
            category_registry = manifest.get('categories', [])
            type_registry = manifest.get('resource_types', [])
            for registry, key_field, has_default in ((category_registry,'category_key',True),(type_registry,'type_key',False)):
                if not isinstance(registry,list) or len(registry)>500:
                    raise ValueError('Annuaire de profil invalide.')
                used_keys=set();used_names=set()
                for entry in registry:
                    if not isinstance(entry,dict) or set(entry)!={key_field,'name','color','active','sort_order'} | ({'is_default'} if has_default else set()):
                        raise ValueError('Annuaire de profil invalide.')
                    key=entry[key_field];name=entry['name']
                    if (not isinstance(key,str) or not re.fullmatch('[a-z0-9_]{1,40}',key) or key in used_keys
                        or not isinstance(name,str) or not 1<=len(name)<=80 or name.strip().casefold() in used_names
                        or not isinstance(entry['color'],str) or not re.fullmatch('#[a-fA-F0-9]{6}',entry['color'])):
                        raise ValueError('Nom, identifiant ou couleur d’annuaire invalide.')
                    used_keys.add(key);used_names.add(name.strip().casefold())
                    for field in ('active','is_default') if has_default else ('active',):
                        if type(entry[field]) is not int or entry[field] not in (0,1):
                            raise ValueError('État d’annuaire invalide.')
                    if type(entry['sort_order']) is not int or not 0<=entry['sort_order']<=100000:
                        raise ValueError('Ordre d’annuaire invalide.')
                if has_default and registry and (sum(e['is_default'] for e in registry)!=1 or any(e['is_default'] and not e['active'] for e in registry)):
                    raise ValueError('Une catégorie active par défaut est nécessaire.')
            if (not isinstance(settings, dict) or not isinstance(machines, list) or
                    not isinstance(tariffs, list) or
                    not isinstance(digests, dict) or set(digests) != set(names) - {"profile.json"}):
                raise ValueError("Contenu du profil invalide.")
            for key, value in settings.items():
                if not isinstance(key, str) or not allowed_setting(key) or not isinstance(value, str) or len(value) > 8000:
                    raise ValueError("Le profil contient un réglage non autorisé.")
                if (key.startswith("module_") or key.startswith(('structure_show_', 'structure_use_'))) and value not in {"0", "1"}:
                    raise ValueError("État de module invalide.")
                if key == 'structure_badge_template' and value not in {'', 'badge-template.svg'}:
                    raise ValueError('Nom du modèle de badge invalide.')
                if (key in {'self_enrollment_enabled','welcome_default'} or key.startswith('discord_new_user_')) and value not in {'0','1'}:
                    raise ValueError('État d’inscription ou de notification invalide.')
                if key.endswith('_logo') and key.startswith('structure_') and not key.startswith(('structure_show_', 'structure_use_')):
                    kind = key.removeprefix('structure_').removesuffix('_logo')
                    if value not in {'', kind + '.png'}:
                        raise ValueError('Nom de logo invalide.')
                if key in {'calendar_display_start','calendar_display_end'} and not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value):
                    raise ValueError('Plage affichée du calendrier invalide.')
                if key in RESERVATION_RANGES:
                    minimum, maximum = RESERVATION_RANGES[key]
                    if not value.isdecimal() or not minimum <= int(value) <= maximum:
                        raise ValueError("Paramètre de réservation invalide.")
                if key == "reservation_waitlist_enabled" and value not in {"0", "1"}:
                    raise ValueError("État de liste d’attente invalide.")
                if key == "structure_color" and value and not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
                    raise ValueError("Couleur de structure invalide.")
                if key == 'structure_dpo_email' and value and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
                    raise ValueError('E-mail du DPO invalide.')
                if key in {'structure_dpo', 'structure_dpo_email', 'structure_dpo_phone'} and len(value) > {'structure_dpo':500,'structure_dpo_email':254,'structure_dpo_phone':40}[key]:
                    raise ValueError('Coordonnées du DPO trop longues.')
                if key in {"structure_latitude", "structure_longitude"} and value:
                    try:
                        number = Decimal(value)
                        limit = 90 if key.endswith("latitude") else 180
                        if not number.is_finite() or not -limit <= number <= limit:
                            raise ValueError
                    except (InvalidOperation, ValueError):
                        raise ValueError("Coordonnées de structure invalides.") from None
                if key == "structure_timezone":
                    try:
                        ZoneInfo(value)
                    except (ValueError, ZoneInfoNotFoundError):
                        raise ValueError("Fuseau horaire du profil invalide.") from None
                if key in {"structure_website", "structure_privacy_policy_url"} and value:
                    parsed = urlparse(value)
                    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
                        raise ValueError("URL de structure invalide.")
            if bool(settings.get("structure_latitude")) != bool(settings.get("structure_longitude")):
                raise ValueError("La latitude et la longitude doivent être configurées ensemble.")
            if (settings.get("module_public_reservations") == "1" and
                    settings.get("module_activities") != "1"):
                raise ValueError("Les réservations publiques nécessitent le module Activités.")
            if ((settings.get("module_booking_slots") == "1" or
                    settings.get("module_rentals") == "1") and
                    settings.get("module_billing") != "1"):
                raise ValueError("Les créneaux réservables et locations nécessitent le module Facturation.")
            if settings.get('structure_badge_template') and 'assets/badge-template.svg' not in digests:
                raise ValueError('Le profil configure un modèle de badge absent.')
            keys = set()
            if settings.get('calendar_display_end','19:00') <= settings.get('calendar_display_start','09:00'):
                raise ValueError('La fin de la plage du calendrier doit suivre son début.')
            for machine in machines:
                if not isinstance(machine, dict) or set(machine) != {"machine_key", "name", "monthly_cents", "deposit_cents", "active", "archived", "sort_order"}:
                    raise ValueError("Catalogue de machines invalide.")
                key = machine["machine_key"]
                if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9_]{1,60}", key) or key in keys:
                    raise ValueError("Identifiant de machine invalide.")
                keys.add(key)
                if not isinstance(machine["name"], str) or not 1 <= len(machine["name"]) <= 180:
                    raise ValueError("Nom de machine invalide.")
                for field in ("monthly_cents", "deposit_cents", "sort_order"):
                    if type(machine[field]) is not int or not 0 <= machine[field] <= 100_000_000:
                        raise ValueError("Tarif de machine invalide.")
                for field in ("active", "archived"):
                    if type(machine[field]) is not int or machine[field] not in (0, 1):
                        raise ValueError("État de machine invalide.")
            assets = {}
            tariff_keys = set()
            for tariff in tariffs:
                if (not isinstance(tariff, dict) or set(tariff) !=
                        {"tariff_key", "name", "unit", "cents", "active", "archived", "sort_order"}):
                    raise ValueError("Catalogue de tarifs invalide.")
                key = tariff["tariff_key"]
                if not isinstance(key, str) or not re.fullmatch(r"[a-z0-9_]{1,60}", key) or key in tariff_keys:
                    raise ValueError("Identifiant de tarif invalide.")
                tariff_keys.add(key)
                if (not isinstance(tariff["name"], str) or not 1 <= len(tariff["name"]) <= 180 or
                        tariff["unit"] not in ("hourly", "half_day")):
                    raise ValueError("Désignation de tarif invalide.")
                for field in ("cents", "sort_order"):
                    if type(tariff[field]) is not int or not 0 <= tariff[field] <= 100_000_000:
                        raise ValueError("Montant de tarif invalide.")
                for field in ("active", "archived"):
                    if type(tariff[field]) is not int or tariff[field] not in (0, 1):
                        raise ValueError("État de tarif invalide.")
            for name, digest in digests.items():
                content = archive.read(name)
                if not isinstance(digest, str) or not hashlib.sha256(content).hexdigest() == digest:
                    raise ValueError("Une ressource du profil est corrompue.")
                assets[name] = content
            return {"settings": settings, "machines": machines, "tariffs": tariffs, "assets": assets,
                    'categories':category_registry, 'resource_types':type_registry}
    except (zipfile.BadZipFile, KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Le profil ZIP est invalide ou endommagé.") from error
