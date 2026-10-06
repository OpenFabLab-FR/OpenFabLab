"""Outbound-only WordPress reservation synchronization for OpenFabLab."""

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse


ENVIRONMENTS = ("test", "production")
RESERVED_STATUSES = ("confirmed", "offer_pending", "present", "absent")


def sync_interval_seconds(value):
    """Keep the historical profile key in minutes; support half minutes exactly."""
    try:
        minutes = Decimal(str(value))
        if not minutes.is_finite() or not 1 <= minutes <= 60 or minutes * 2 != (minutes * 2).to_integral_value():
            raise ValueError
        return int(minutes * 60)
    except (InvalidOperation, ValueError):
        return 90


def booking_reservation_status(booking):
    """Read historical presence statuses without rewriting their history."""
    return "confirmed" if booking["status"] in {"present", "absent"} else booking["status"]


def booking_presence(booking):
    if booking_reservation_status(booking) != "confirmed":
        return None
    value = booking["is_present"]
    if value is not None:
        return int(value) == 1
    if booking["status"] in {"present", "absent"}:
        return booking["status"] == "present"
    return None


def booking_counts(bookings):
    from collections import Counter
    counts = Counter(booking_reservation_status(booking) for booking in bookings)
    counts["present"] = sum(booking_presence(booking) is True for booking in bookings)
    counts["absent"] = sum(booking_presence(booking) is False
                           and booking_reservation_status(booking) == "confirmed" for booking in bookings)
    return counts


def pending_confirmation_ids(database, service_id):
    pending = set()
    for row in database.execute(
        "SELECT o.payload_json FROM reservation_outbox o JOIN animation_bookings b "
        "ON b.external_uuid = o.entity_key WHERE b.service_id = ? "
        "AND o.command_type = 'booking' AND o.sent_at IS NULL", (service_id,)
    ):
        payload = json.loads(row["payload_json"])
        if payload.get("action") == "confirm":
            pending.update(payload.get("members") or [payload["uuid"]])
    return pending


def booking_capacity_used(database, service_id, slot_uuid=None):
    rows = database.execute("SELECT * FROM animation_bookings WHERE service_id = ?"
                            + (" AND slot_uuid = ?" if slot_uuid else ""),
                            (service_id, slot_uuid) if slot_uuid else (service_id,)).fetchall()
    pending = pending_confirmation_ids(database, service_id)
    return sum(row["status"] in RESERVED_STATUSES
               or (row["status"] == "waitlisted" and row["external_uuid"] in pending) for row in rows)
PRIVATE_API = "/wp-json/openfablab/v1"


def normalize_email(value):
    return str(value or "").strip().casefold()


def normalize_phone(country_code, number):
    code = re.sub(r"\D", "", str(country_code or "+33"))
    digits = re.sub(r"\D", "", str(number or ""))
    if code.startswith("00"):
        code = code[2:]
    if digits.startswith("00"):
        return "+" + digits[2:]
    if digits.startswith(code) and len(digits) > 10:
        return "+" + digits
    return "+" + code + digits.lstrip("0") if digits else ""


def contact_fingerprint(secret, kind, value):
    if kind not in {"email", "phone"}:
        raise ValueError("Type de contact inconnu")
    normalized = normalize_email(value) if kind == "email" else str(value or "")
    if not normalized:
        return ""
    return hmac.new(secret, f"contact/v1|{kind}|{normalized}".encode("utf-8"),
                    hashlib.sha256).hexdigest()


def build_directory(database, secret):
    rows = database.execute(
        "SELECT public_id, first_name, last_name, birth_year, category, email, phone_country_code, phone, "
        "COALESCE(updated_at, created_at) AS updated_at FROM users WHERE active = 1"
    ).fetchall()
    return [{"public_id": row["public_id"], "active": True,
             "first_name": row["first_name"], "last_name": row["last_name"],
             "email": normalize_email(row["email"]),
             "phone": normalize_phone(row["phone_country_code"], row["phone"]),
             "birth_year": row["birth_year"], "category": row["category"],
             "email_hmac": contact_fingerprint(secret, "email", row["email"]),
             "phone_hmac": contact_fingerprint(
                 secret, "phone", normalize_phone(row["phone_country_code"], row["phone"])
             ), "updated_at": row["updated_at"]} for row in rows]


def sync_secret_path(database_path):
    return Path(database_path).with_name(".openfablab_sync_secret")


def save_sync_secret(database_path, value):
    secret = str(value or "").strip()
    if len(secret) < 40 or not re.fullmatch(r"[A-Za-z0-9_\-]+", secret):
        raise ValueError("Le secret doit être la valeur longue générée par WordPress.")
    path = sync_secret_path(database_path)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(secret + "\n")
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def load_sync_secret(database_path):
    try:
        return sync_secret_path(database_path).read_text(encoding="utf-8").strip().encode("utf-8")
    except OSError:
        return b""


def signed_headers(secret, method, path, body, timestamp=None, nonce=None):
    timestamp = int(time.time()) if timestamp is None else int(timestamp)
    nonce = nonce or secrets.token_urlsafe(18)
    digest = hashlib.sha256(body).hexdigest()
    canonical = f"{timestamp}\n{nonce}\n{method.upper()}\n{path}\n{digest}"
    signature = hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"X-OpenFabLab-Timestamp": str(timestamp),
            "X-OpenFabLab-Nonce": nonce,
            "X-OpenFabLab-Signature": signature,
            "Content-Type": "application/json; charset=utf-8"}


class WordPressClient:
    def __init__(self, site_url, secret, transport=None):
        parsed = urlparse(str(site_url or "").rstrip("/"))
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment
                or any(part in {".", ".."} for part in parsed.path.split("/"))):
            raise ValueError("Le site WordPress doit utiliser une URL HTTPS valide.")
        if not secret:
            raise ValueError("Le secret de synchronisation manque.")
        self.site_url = str(site_url).rstrip("/")
        self.secret = secret
        self.transport = transport or urllib.request.urlopen

    def post(self, route, payload):
        path = PRIVATE_API + route
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = signed_headers(self.secret, "POST", "/openfablab/v1" + route, body)
        request = urllib.request.Request(self.site_url + path, data=body,
                                         headers=headers, method="POST")
        with self.transport(request, timeout=10) as response:
            result = json.loads(response.read(2_000_000))
        if not isinstance(result, dict):
            raise ValueError("Réponse WordPress invalide")
        return result


def animation_payload(database, service_id, command="upsert", environment=None):
    service = database.execute(
        "SELECT * FROM fablab_services WHERE id = ? AND service_type = 'animation'",
        (service_id,),
    ).fetchone()
    config = database.execute(
        "SELECT * FROM animation_reservation_config WHERE service_id = ?", (service_id,)
    ).fetchone()
    if command == "upsert" and (service is None or config is None):
        return
    environment = environment or (config["environment"] if config else "test")
    payload = {"command": command, "service_id": service_id,
               "environment": environment}
    if service is not None and config is not None:
        def setting(key, default):
            row = database.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default
        payload["animation"] = {
            "service_id": service_id, "environment": environment,
            "published": bool(config["enabled"]), "title": service["title"],
            "description": service["description"] or "",
            "service_date": service["service_date"],
            "start_time": service["start_time"], "end_time": service["end_time"],
            "capacity": config["capacity"], "minimum_age": service["minimum_age"],
            "audience": config["audience"],
            "signup_open_at": config["signup_open_at"],
            "close_minutes": config["close_minutes"],
            "accompaniment_under_age": config["accompaniment_under_age"],
            "waitlist_enabled": bool(config["waitlist_enabled"]),
            "reminder_one_hours": config["reminder_one_hours"],
            "reminder_two_hours": config["reminder_two_hours"],
            "updated_at": config["updated_at"],
            "timezone": setting("structure_timezone", "Europe/Paris"),
            "privacy_policy_url": setting("structure_privacy_policy_url", ""),
            "offer_hours": int(setting("reservation_offer_hours", "12")),
            "last_offer_hours": int(setting("reservation_last_offer_hours", "24")),
        }
        payload["animation"].update({key: config[key] for key in
            ("booking_mode", "slot_duration_minutes", "slot_gap_minutes", "slot_capacity")})
        payload["animation"]["slots"] = [dict(row) for row in database.execute(
            "SELECT slot_uuid, starts_at, ends_at, capacity FROM animation_slots "
            "WHERE service_id=? AND active=1 ORDER BY starts_at", (service_id,))]
    return payload


def enqueue_animation(database, service_id, command="upsert"):
    payload = animation_payload(database, service_id, command)
    if payload is None:
        return
    database.execute(
        "INSERT INTO reservation_outbox (environment, command_type, entity_key, "
        "payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (payload['environment'], command, str(service_id), json.dumps(payload, ensure_ascii=False),
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )


def enqueue_booking_command(database, environment, booking_uuid, action, **details):
    if environment not in ENVIRONMENTS or action not in {
        "present", "absent", "cancel", "confirm", "verify", "link", "unlink", "walkin"
    }:
        raise ValueError("Commande de réservation invalide")
    payload = {"environment": environment, "uuid": booking_uuid, "action": action,
               **details}
    database.execute(
        "INSERT INTO reservation_outbox (environment, command_type, entity_key, payload_json, created_at) "
        "VALUES (?, 'booking', ?, ?, ?)",
        (environment, booking_uuid, json.dumps(payload, ensure_ascii=False),
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )


def import_events(database, environment, events, notifications=None):
    """Apply each external event once; replay cannot duplicate a booking."""
    count = 0
    touched_services = set()
    for event in events:
        event_id = str(event.get("id", ""))
        booking = event.get("booking")
        if not event_id.isdigit() or not isinstance(booking, dict):
            continue
        if database.execute("SELECT 1 FROM reservation_sync_events WHERE external_event_id = ?",
                            (f"{environment}:{event_id}",)).fetchone():
            continue
        service = database.execute("SELECT id FROM fablab_services WHERE id = ?",
                                   (booking.get("service_id"),)).fetchone()
        if service is None or booking.get("environment") != environment:
            continue
        public_id = booking.get("public_id")
        user = None
        if public_id and booking.get("link_status") in {"matched", "manual"}:
            user = database.execute("SELECT id FROM users WHERE public_id = ? AND active = 1",
                                    (public_id,)).fetchone()
        status = str(booking.get("status", ""))[:30]
        presence = booking.get("is_present")
        if status in {"present", "absent"}:
            presence = int(status == "present") if presence is None else int(presence)
            status = "confirmed"
        values = (str(booking.get("uuid", "")), service["id"], environment,
                  str(booking.get("first_name", ""))[:80],
                  str(booking.get("last_name", ""))[:80], booking.get("birth_year"),
                  str(booking.get("email", ""))[:254], str(booking.get("phone", ""))[:40],
                  status,
                  str(booking.get("link_status", ""))[:30], public_id,
                  user["id"] if user else None, booking.get("group_uuid"),
                  str(booking.get("source", "online"))[:30], presence,
                  booking.get("created_at"), booking.get("updated_at"), booking.get("slot_uuid") or None)
        slot = values[-1]
        config = database.execute("SELECT booking_mode, environment FROM animation_reservation_config WHERE service_id=?", (service["id"],)).fetchone()
        if config and (config["environment"] != environment or (config["booking_mode"] == "slots") != bool(slot)):
            raise ValueError("Environnement ou créneau de réservation incompatible.")
        existing = database.execute("SELECT service_id, environment, slot_uuid FROM animation_bookings WHERE external_uuid=?", (values[0],)).fetchone()
        if existing and (existing["service_id"] != service["id"] or existing["environment"] != environment or existing["slot_uuid"] != slot):
            raise ValueError("Une inscription ne peut pas changer d’animation ou de créneau.")
        if slot and not database.execute("SELECT 1 FROM animation_slots WHERE slot_uuid=? AND service_id=?",
                                         (slot, service["id"])).fetchone():
            raise ValueError("Créneau WordPress inconnu : synchroniser le catalogue avant les inscriptions.")
        if not values[0] or not values[3] or not values[4] or not values[-2]:
            continue
        database.execute(
            "INSERT INTO animation_bookings (external_uuid, service_id, environment, "
            "first_name, last_name, birth_year, email, phone, status, link_status, "
            "public_id, user_id, group_uuid, source, is_present, created_at, updated_at, slot_uuid) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(external_uuid) DO UPDATE SET "
            "status=excluded.status, link_status=excluded.link_status, "
            "public_id=excluded.public_id, user_id=excluded.user_id, "
            "is_present=excluded.is_present, updated_at=excluded.updated_at, "
            "email=excluded.email, phone=excluded.phone",
            values,
        )
        database.execute(
            "INSERT INTO reservation_sync_events (external_event_id, environment, received_at) "
            "VALUES (?, ?, ?)",
            (f"{environment}:{event_id}", environment,
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        touched_services.add(service["id"])
        if notifications is not None:
            notifications.append({"type": str(event.get("type", "")),
                                  "service_id": service["id"], "environment": environment,
                                  "link_status": values[9]})
        count += 1
    for service_id in touched_services:
        database.execute(
            "UPDATE fablab_services SET actual_participants = "
            "COALESCE((SELECT walkin_count FROM animation_reservation_config WHERE service_id = ?), 0) "
            "+ (SELECT COUNT(*) FROM animation_bookings WHERE service_id = ? "
            "AND status IN ('confirmed', 'present') AND is_present = 1) WHERE id = ?",
            (service_id, service_id, service_id),
        )
    return count


def sync_error_label(error):
    """Diagnostic bref, sans URL, contenu de réponse ni donnée personnelle."""
    if isinstance(error, urllib.error.HTTPError):
        return f"HTTP {error.code}"
    if isinstance(error, urllib.error.URLError):
        return "Connexion HTTPS indisponible"
    if isinstance(error, ValueError):
        return "Réponse ou configuration invalide"
    return type(error).__name__


def run_sync_cycle(database, database_path, site_url, now=None, client=None,
                   environments=ENVIRONMENTS):
    """Même chemin signé pour Normal et Test, sans activation supplémentaire."""
    from runtime_policy import external_allowed
    if not external_allowed(database_path):
        return {"configured": False, "imported": 0, "isolated": True}
    if not environments or any(environment not in ENVIRONMENTS for environment in environments):
        raise ValueError("Environnement de synchronisation invalide")
    secret = load_sync_secret(database_path)
    if not site_url or not secret:
        return {"configured": False, "imported": 0}
    if database.execute('PRAGMA user_version').fetchone()[0]>=16:
        from outbound_sync import catalogue
        return catalogue(database,database_path,site_url,client,environments,force=False)
    # Valider HTTPS avant de préparer l'annuaire, même avec un client de test.
    validated_client = WordPressClient(site_url, secret)
    client = client or validated_client
    now = now or datetime.now(timezone.utc)
    directory = build_directory(database, secret)
    imported = 0
    notifications = []
    rejected = []
    errors = []
    for environment in environments:
        database.execute(
            "INSERT INTO reservation_sync_state(environment, cursor, last_attempt_at) "
            "VALUES (?, '', ?) ON CONFLICT(environment) DO UPDATE SET last_attempt_at=excluded.last_attempt_at",
            (environment, now.isoformat(timespec="seconds")),
        )
        database.commit()
        try:
            imported += _sync_environment(database, client, environment, directory, now,
                                           notifications, rejected)
        except (OSError, ValueError, sqlite3.Error) as error:
            database.rollback()
            database.execute(
                "UPDATE reservation_sync_state SET last_error_at = ?, last_error = ? "
                "WHERE environment = ?", (now.isoformat(timespec="seconds"),
                                           sync_error_label(error), environment),
            )
            database.commit()
            errors.append({"environment": environment, "error": sync_error_label(error)})
    return {"configured": True, "imported": imported, "notifications": notifications,
            "rejected": rejected, "errors": errors}


def _sync_environment(database, client, environment, directory, now, notifications, rejected):
    """Une erreur d'un environnement ne bloque pas l'autre ni son diagnostic."""
    imported = 0
    try:
        capabilities = client.post('/sync/capabilities', {'environment': environment})
    except urllib.error.HTTPError as error:
        if error.code!=404:
            raise
        capabilities = {}  # Original pre-capability plugin: incremental only.
    if not isinstance(capabilities,dict):
        raise ValueError('Capabilities WordPress invalides')
    if capabilities.get('family_gateway_v1') is True:
        # Protocol 3 reads the live catalogue and books on OpenFabLab. No
        # directory, companion request, mirror upsert or booking replay is sent.
        database.execute('INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)',
                         ('reservation_protocol_'+environment,'3'))
        database.execute('INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)',
                         ('reservation_plugin_'+environment,str(capabilities.get('plugin_version','2.8.0'))))
        database.execute('UPDATE reservation_sync_state SET last_success_at=?,last_error=NULL,last_error_at=NULL WHERE environment=?',
                         ((now or datetime.now(timezone.utc)).isoformat(timespec='seconds'),environment))
        database.commit()
        return 0
    if database.execute('PRAGMA user_version').fetchone()[0] >= 15:
        # Never import/reconfirm seats from a separate legacy capacity engine.
        # Historical records remain untouched, without replay.
        raise ValueError('La candidate 2.8 nécessite le plugin WordPress 2.8 pour cette intégration.')
    # Historical protocol helpers remain available for offline recovery tests.
    slots_supported = capabilities.get('animation_slots_v1') is True
    snapshot_supported = capabilities.get('catalog_snapshot_v1') is True
    if capabilities.get('custom_categories_v1') is not True and any(
            user.get('category') not in {'user','volunteer','voluntary','fabmanager','intern','staff'} for user in directory):
        raise ValueError('Mettez à jour le plugin WordPress pour les catégories personnalisées')
    if not client.post("/sync/directory", {"environment": environment, "users": directory}).get('ok'):
        raise ValueError('Annuaire refusé')
    # Prioritize pending catalogue tombstones independently of a different
    # incompatible upsert. Never reorder reservation commands among themselves.
    tombstones = database.execute("SELECT id,payload_json FROM reservation_outbox WHERE environment=? AND sent_at IS NULL AND command_type NOT IN ('booking','public_request') ORDER BY id", (environment,)).fetchall()
    for row in tombstones:
        old=json.loads(row['payload_json']); current=animation_payload(database,int(old['service_id']))
        if current is not None and current['environment']==environment:
            continue
        try:
            result=client.post('/sync/animations',dict(command='delete',service_id=int(old['service_id']),environment=environment))
            if not result.get('ok'):raise ValueError('Suppression WordPress refusée')
        except (OSError,ValueError) as error:
            database.execute('UPDATE reservation_outbox SET attempts=attempts+1,last_error=? WHERE id=?',(sync_error_label(error),row['id']))
            database.commit();raise
        database.execute('UPDATE reservation_outbox SET sent_at=?,attempts=attempts+1,last_error=NULL WHERE id=?',(now.isoformat(timespec='seconds'),row['id']))
        database.commit()
    if snapshot_supported:
        catalogue = [animation_payload(database, row[0])['animation'] for row in database.execute(
            'SELECT service_id FROM animation_reservation_config WHERE environment=? ORDER BY service_id',
            (environment,)).fetchall()]
        result = client.post('/sync/snapshot', {'environment': environment, 'animations': catalogue})
        if not result.get('ok'):
            raise ValueError('Réconciliation refusée')
    database.execute('INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)',
                     ('reservation_protocol_' + environment, str(capabilities.get('protocol_version', 1))))
    database.execute('INSERT OR REPLACE INTO app_settings(key,value) VALUES(?,?)',
                     ('reservation_plugin_' + environment, str(capabilities.get('plugin_version', 'ancien/inconnu'))))
    database.commit()
    rows = database.execute(
        "SELECT id, command_type, payload_json FROM reservation_outbox "
        "WHERE environment = ? AND sent_at IS NULL AND command_type!='public_request' ORDER BY id LIMIT 100", (environment,)
    ).fetchall()
    for row in rows:
        route = "/sync/commands" if row["command_type"] == "booking" else "/sync/animations"
        payload = json.loads(row["payload_json"])
        if row['command_type'] != 'booking':
            service_id = int(payload['service_id'])
            current = animation_payload(database, service_id)
            # Send current truth, never obsolete intermediate configuration. A
            # refused old update must not prevent the later deletion reaching WP.
            if current is None or current['environment'] != environment:
                payload = {'command': 'delete', 'service_id': service_id, 'environment': environment}
            elif payload['command'] == 'upsert':
                payload = current
            elif snapshot_supported:
                # A historical delete followed by recreate has been reconciled.
                payload = current
        if payload.get("animation", {}).get("booking_mode") == "slots" or payload.get("slot_uuid"):
            if not slots_supported:
                raise ValueError("Le plugin WordPress doit être mis à jour pour les créneaux")
        try:
            result = client.post(route, payload)
            if not result.get('ok'):
                raise ValueError('Publication WordPress refusée')
        except (OSError, ValueError) as error:
            database.execute('UPDATE reservation_outbox SET attempts=attempts+1,last_error=? WHERE id=?',
                             (sync_error_label(error), row['id']))
            database.commit()
            raise
        rejection = None
        if result.get("confirmation") == "refused":
            rejection = ("Confirmation refusée : capacité atteinte." if result.get("reason") == "capacity"
                         else "Confirmation refusée : inscription incompatible.")
            rejected.append(rejection)
        database.execute("UPDATE reservation_outbox SET sent_at = ?, attempts = attempts + 1 "
                         ", last_error = ? WHERE id = ?",
                         (now.isoformat(timespec="seconds"), rejection, row["id"]))
        database.commit()
    if not client.post("/heartbeat", {"environment": environment}).get('ok'):
        raise ValueError('Traitement WordPress refusé')
    imported += receive_events(database, client, environment, now, notifications)
    if database.execute("SELECT 1 FROM reservation_outbox WHERE environment=? AND command_type='public_request' AND sent_at IS NULL LIMIT 1",(environment,)).fetchone():
        from tests.historical_tablet_reservations import process_requests
        process_requests(database,client,environment)
        imported += receive_events(database,client,environment,now,notifications)
    from tablet_reservations import reconcile_requests
    reconcile_requests(database,environment)
    return imported


def receive_events(database, client, environment, now, notifications):
    imported = 0
    state = database.execute(
        "SELECT cursor FROM reservation_sync_state WHERE environment = ?", (environment,)
    ).fetchone()
    cursor = state["cursor"] if state else ""
    while True:
        result = client.post("/sync/events", {"environment": environment,
                                               "cursor": cursor, "limit": 100})
        if not result.get('ok',True):
            raise ValueError('Flux WordPress refusé')
        events = result.get("events", [])
        if not isinstance(events, list):
            raise ValueError("Flux d'événements WordPress invalide")
        imported += import_events(database, environment, events, notifications)
        next_cursor = str(result.get("cursor", cursor))
        has_more = result.get('has_more', len(events)>=100)
        if has_more and next_cursor==cursor:
            raise ValueError('Le curseur WordPress ne progresse pas')
        cursor = next_cursor
        database.execute(
            "INSERT INTO reservation_sync_state (environment, cursor, last_success_at, last_error_at, last_error) "
            "VALUES (?, ?, ?, NULL, NULL) ON CONFLICT(environment) DO UPDATE SET "
            "cursor=excluded.cursor, last_success_at=excluded.last_success_at, "
            "last_error_at=NULL, last_error=NULL",
            (environment, cursor, now.isoformat(timespec="seconds")),
        )
        database.commit()
        if not has_more:
            break
    return imported
