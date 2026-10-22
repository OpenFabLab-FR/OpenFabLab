"""Read-only publication clock shared by kiosk and negotiated WP projection.

Only the per-animation hide-before-opening preference is persistent, in the
existing settings store. No booking, occurrence or historical row is changed.
All comparisons/durations use UTC (24 elapsed hours, including DST changes).
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import family_model as family


def visibility_key(service_id):
    return 'animation_hide_before_opening_' + str(int(service_id))


def opening_value(raw, zone_name, previous=None):
    """Keep an unchanged stored instant (including the repeated autumn hour).

    New naive inputs follow the first occurrence of an ambiguous local hour.
    A local hour skipped in spring is invalid, not silently shifted.
    """
    zone=ZoneInfo(zone_name)
    parsed=datetime.fromisoformat(raw.replace('Z','+00:00'))
    if previous and parsed.tzinfo is None:
        old=datetime.fromisoformat(previous.replace('Z','+00:00'))
        old=old if old.tzinfo else old.replace(tzinfo=zone)
        if old.astimezone(zone).strftime('%Y-%m-%dT%H:%M')==parsed.strftime('%Y-%m-%dT%H:%M'):
            return old.astimezone(timezone.utc).isoformat(timespec='seconds')
    if parsed.tzinfo is None:
        local=parsed.replace(tzinfo=zone)
        if local.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)!=parsed:
            raise ValueError('Cette heure locale n’existe pas lors du changement d’heure.')
        parsed=local
    return parsed.astimezone(timezone.utc).isoformat(timespec='seconds')


def clock(db, service, current=None):
    service = dict(service)
    zone = ZoneInfo(family.setting(db, 'structure_timezone', 'Europe/Paris'))
    def utc(value):
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=zone)).astimezone(timezone.utc)
    start = utc(service['service_date'] + 'T' + service['start_time'])
    end = utc(service['service_date'] + 'T' + service['end_time'])
    if service.get('booking_mode') == 'slots':
        ends = [utc(row[0]) for row in db.execute(
            'SELECT ends_at FROM animation_slots WHERE service_id=? AND active=1', (service['service_id'],))]
        if ends:
            end = max(ends)
    opening = utc(service['signup_open_at']) if service.get('signup_open_at') else None
    now = (current or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ended = now >= end
    hidden = family.setting(db, visibility_key(service['service_id']), '0') == '1'
    return dict(ends_at=end.isoformat(), starts_at=start.isoformat(),
                signup_open_at=opening.isoformat() if opening else '',
                signup_open_label=opening.astimezone(zone).strftime('%d/%m/%Y à %H:%M') if opening else '',
                public_until=(end + timedelta(hours=24)).isoformat(),
                hide_before_opening=hidden, ended=ended,
                visible=bool(service.get('enabled')) and now < end + timedelta(hours=24)
                    and not (hidden and opening and now < opening),
                not_open=bool(opening and now < opening))
