"""Export iCalendar compatible avec Calendrier Apple et Microsoft Outlook."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


def _escape(value) -> str:
    return (
        str(value or "")
        .replace("\\", "\\\\")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def _fold(line: str) -> list[str]:
    """Plie les lignes à 75 octets sans couper un caractère UTF-8."""
    chunks = []
    current = ""
    for character in line:
        candidate = current + character
        if len(candidate.encode("utf-8")) > 73:
            chunks.append(current)
            current = " " + character
        else:
            current = candidate
    chunks.append(current)
    return chunks


def build_ics_event(service: dict, *, base_url: str = "", structure=None) -> bytes:
    """Produit un événement autonome importable par les deux calendriers."""
    structure = structure or {"name": "Mon FabLab", "address": "", "website": "", "timezone": "Europe/Paris"}
    timezone_name = structure.get("timezone") or "Europe/Paris"
    event_zone = ZoneInfo(timezone_name)
    service_date = datetime.strptime(service["service_date"], "%Y-%m-%d")
    start_time = service.get("start_time")
    end_time = service.get("end_time")
    if start_time and end_time:
        start = f"{service['service_date'].replace('-', '')}T{start_time.replace(':', '')}00"
        end_date = service.get("end_date") or service["service_date"]
        if end_date == service["service_date"] and end_time <= start_time:
            end_date = (service_date + timedelta(days=1)).strftime("%Y-%m-%d")
        end = f"{end_date.replace('-', '')}T{end_time.replace(':', '')}00"
        if timezone_name == "Europe/Paris":
            date_lines = [f"DTSTART;TZID=Europe/Paris:{start}", f"DTEND;TZID=Europe/Paris:{end}"]
        else:
            start_utc = datetime.strptime(start, "%Y%m%dT%H%M%S").replace(tzinfo=event_zone).astimezone(timezone.utc)
            end_utc = datetime.strptime(end, "%Y%m%dT%H%M%S").replace(tzinfo=event_zone).astimezone(timezone.utc)
            date_lines = [f"DTSTART:{start_utc:%Y%m%dT%H%M%SZ}", f"DTEND:{end_utc:%Y%m%dT%H%M%SZ}"]
    else:
        end_date = service.get("end_date")
        if end_date:
            end_day = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        else:
            end_day = service_date + timedelta(days=1)
        date_lines = [
            f"DTSTART;VALUE=DATE:{service_date.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{end_day.strftime('%Y%m%d')}",
        ]

    details = []
    type_labels = {
        "animation": "Animation",
        "reservation": "Créneau réservable",
        "rental": "Location",
    }
    event_type = type_labels.get(service.get("service_type"), "Événement")
    details.append(event_type)
    if service.get("description"):
        details.append(service["description"])
    if service.get("minimum_age") is not None and service.get("service_type") == "animation":
        details.append(f"Âge minimum : {service['minimum_age']} ans")
    if service.get("expected_participants") is not None:
        details.append(f"Places maximum : {service['expected_participants']}")
    if service.get("actual_participants") is not None:
        details.append(f"Usagers présents : {service['actual_participants']}")
    if service.get("participants") is not None and service.get("service_type") == "reservation":
        details.append(f"Participants : {service['participants']}")
    if service.get("client_name"):
        details.append(f"Client : {service['client_name']}")
    if service.get("client_contact"):
        details.append(f"Contact : {service['client_contact']}")
    if service.get("client_email"):
        details.append(f"E-mail : {service['client_email']}")
    if service.get("client_phone"):
        details.append(f"Téléphone : {service['client_phone']}")
    if service.get("invoice_reference"):
        details.append(f"Dossier : {service['invoice_reference']}")
    if base_url:
        details.append(f"Fiche : {base_url}")

    uid_source = f"{service.get('id')}|{service.get('service_date')}|{service.get('title')}"
    uid = sha256(uid_source.encode("utf-8")).hexdigest()[:32]
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary = f"{event_type} : {service.get('title') or ''}"
    domain = urlparse(structure.get("website") or "").hostname
    if not domain:
        domain = "openfablab.local"
    location = ", ".join(part for part in (structure.get("name"), structure.get("address")) if part)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//OpenFabLab//Calendar Export//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VTIMEZONE",
        "TZID:Europe/Paris",
        "X-LIC-LOCATION:Europe/Paris",
        "BEGIN:DAYLIGHT",
        "TZOFFSETFROM:+0100",
        "TZOFFSETTO:+0200",
        "TZNAME:CEST",
        "DTSTART:19700329T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU",
        "END:DAYLIGHT",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:+0200",
        "TZOFFSETTO:+0100",
        "TZNAME:CET",
        "DTSTART:19701025T030000",
        "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU",
        "END:STANDARD",
        "END:VTIMEZONE",
        "BEGIN:VEVENT",
        f"UID:{uid}@{domain}",
        f"DTSTAMP:{now}",
        *date_lines,
        f"SUMMARY:{_escape(summary)}",
        f"LOCATION:{_escape(location)}",
        f"DESCRIPTION:{_escape(chr(10).join(details))}",
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    folded = [chunk for line in lines for chunk in _fold(line)]
    return ("\r\n".join(folded) + "\r\n").encode("utf-8")
