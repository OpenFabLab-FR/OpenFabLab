"""Internal animation slots, not billable standalone activities. No I/O/network."""
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo


def generate_slots(service, config, zone="Europe/Paris", service_id=0):
    if config.get("booking_mode", "whole") != "slots":
        return []
    try:
        duration = int(config["slot_duration_minutes"])
        gap = int(config["slot_gap_minutes"])
        capacity = int(config["slot_capacity"])
        if not 1 <= duration <= 480 or not 0 <= gap <= 480 or not 1 <= capacity <= 100000:
            raise ValueError
        tz = ZoneInfo(zone)
        start = datetime.fromisoformat(service["service_date"] + "T" + service["start_time"])
        end = datetime.fromisoformat(service["service_date"] + "T" + service["end_time"])
        # Reject nonexistent/ambiguous wall times instead of silently moving a slot.
        for value in (start, end):
            aware = value.replace(tzinfo=tz)
            if (aware.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) != value
                    or aware.utcoffset() != value.replace(tzinfo=tz, fold=1).utcoffset()):
                raise ValueError
        start, end = start.replace(tzinfo=tz).astimezone(timezone.utc), end.replace(tzinfo=tz).astimezone(timezone.utc)
        if end <= start or start + timedelta(minutes=duration) > end:
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise ValueError("Créneaux invalides : durée et capacité positives, battement positif ou nul, horaires valides et au moins un créneau complet sont nécessaires.")
    slots = []
    while start + timedelta(minutes=duration) <= end:
        stop = start + timedelta(minutes=duration)
        a, b = start.isoformat(timespec="seconds"), stop.isoformat(timespec="seconds")
        key = f"openfablab-slot-v1|{config['environment']}|{service_id}|{a}|{b}"
        slots.append({"slot_uuid": str(uuid5(NAMESPACE_URL, key)), "starts_at": a,
                      "ends_at": b, "capacity": capacity,
                      "label": start.astimezone(tz).strftime("%H:%M") + "–" + stop.astimezone(tz).strftime("%H:%M")})
        start += timedelta(minutes=duration + gap)
    return slots


def save_slots(database, service, config, zone):
    slots = generate_slots(dict(service), dict(config), zone, service["id"])
    # Keep removed rows for historical references; never delete a booking or move it.
    database.execute("UPDATE animation_slots SET active = 0 WHERE service_id = ?", (service["id"],))
    for slot in slots:
        database.execute("INSERT INTO animation_slots (slot_uuid, service_id, starts_at, ends_at, capacity, active) "
                         "VALUES (?, ?, ?, ?, ?, 1) ON CONFLICT(slot_uuid) DO UPDATE SET capacity=excluded.capacity, active=1",
                         (slot["slot_uuid"], service["id"], slot["starts_at"], slot["ends_at"], slot["capacity"]))
    return slots


def slots_summary(database, service_id, zone="Europe/Paris"):
    rows = database.execute("SELECT s.*, "
        "(SELECT COUNT(*) FROM animation_bookings b WHERE b.service_id=s.service_id AND b.slot_uuid=s.slot_uuid "
        "AND b.status IN ('confirmed','offer_pending','present','absent')) AS occupied, "
        "(SELECT COUNT(*) FROM animation_bookings b WHERE b.service_id=s.service_id AND b.slot_uuid=s.slot_uuid "
        "AND b.status='waitlisted') AS waiting FROM animation_slots s "
        "WHERE s.service_id=? AND s.active=1 ORDER BY s.starts_at", (service_id,)).fetchall()
    return [dict(row, label=slot_label(row, zone), available=max(0, row["capacity"]-row["occupied"])) for row in rows]


def slot_label(row, zone="Europe/Paris"):
    if not row or not row["starts_at"]:
        return ""
    tz = ZoneInfo(zone)
    return "–".join(datetime.fromisoformat(row[key]).astimezone(tz).strftime("%H:%M") for key in ("starts_at", "ends_at"))
