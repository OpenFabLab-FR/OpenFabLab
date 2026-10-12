"""Optional public web URL. Syntactic validation only: never fetch or resolve."""
import ipaddress
import re
from urllib.parse import urlsplit, parse_qsl


def validate_url(value):
    value=str(value or '').strip()
    if not value:
        return ''
    if len(value)>2048 or any(ord(c)<33 for c in value) or any(c in value for c in '<>"\\'):
        raise ValueError('Renseignez un lien HTTP ou HTTPS valide, sans espace ni identifiant privé.')
    try:
        parts=urlsplit(value)
        host=(parts.hostname or '').rstrip('.').lower().encode('idna').decode()
        port=parts.port
    except (ValueError,UnicodeError):
        raise ValueError('Lien d’information invalide.') from None
    if parts.scheme not in ('http','https') or not host or parts.username or parts.password:
        raise ValueError('Le lien d’information doit utiliser HTTP ou HTTPS, sans identifiant ni mot de passe.')
    if port is not None and not 1<=port<=65535:
        raise ValueError('Port du lien invalide.')
    if host=='localhost' or host.endswith(('.localhost','.local','.lan','.internal')):
        raise ValueError('Un lien public ne peut pas désigner une adresse interne.')
    try:
        address=ipaddress.ip_address(host)
    except ValueError:
        if '.' not in host or not re.fullmatch(r'[a-z0-9.-]+',host) or host.replace('.','').isdigit():
            raise ValueError('Renseignez un nom de domaine public valide.')
    else:
        if not address.is_global:
            raise ValueError('Un lien public ne peut pas désigner une adresse privée.')
    sensitive={'token','secret','password','passwd','api_key','apikey','access_token','pin'}
    if any(key.lower() in sensitive for key,_ in parse_qsl(parts.query)):
        raise ValueError('Le lien d’information ne doit pas contenir de secret ou de jeton personnel.')
    return value


def optional_url(value):
    try:
        return validate_url(value)
    except ValueError:
        return ''


def metrics(db,service_id):
    from reservations_sync import booking_capacity_used
    row=db.execute('SELECT s.expected_participants,c.capacity,c.waitlist_enabled FROM fablab_services s LEFT JOIN animation_reservation_config c ON c.service_id=s.id WHERE s.id=?',(service_id,)).fetchone()
    capacity=row['capacity'] if row['capacity'] is not None else row['expected_participants'] or 0
    states=db.execute("SELECT SUM(status IN('confirmed','present','absent')) AS confirmed,SUM(status='waitlisted') AS waitlisted,SUM(is_present=1 AND status IN('confirmed','present')) AS present FROM animation_bookings WHERE service_id=?",(service_id,)).fetchone()
    return dict(capacity=int(capacity),confirmed_count=states['confirmed'] or 0,
        remaining_count=max(0,int(capacity)-booking_capacity_used(db,service_id)),
        present_count=states['present'] or 0,waitlisted_count=states['waitlisted'] or 0,
        waitlist_enabled=bool(row['waitlist_enabled']))
