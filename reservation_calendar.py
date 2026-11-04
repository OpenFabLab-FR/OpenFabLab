"""Participant calendar: explicit public allowlist, no internal calendar export."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from html import escape
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
from calendar_export import _escape,_fold
from family_model import setting

def event(db,group):
    service=db.execute('SELECT id,title,description,service_date,start_time,end_time,information_url,updated_at FROM fablab_services WHERE id=?',(group['service_id'],)).fetchone()
    if not service:raise ValueError('Animation indisponible.')
    zone=ZoneInfo(setting(db,'structure_timezone','Europe/Paris'))
    slot=db.execute('SELECT starts_at,ends_at FROM animation_slots WHERE slot_uuid=? AND service_id=?',(group['slot_uuid'],group['service_id'])).fetchone() if group['slot_uuid'] else None
    if group['slot_uuid'] and not slot:raise ValueError('Créneau indisponible.')
    if slot:begin,finish=[datetime.fromisoformat(slot[k]).astimezone(zone) for k in ('starts_at','ends_at')]
    else:
        begin=datetime.fromisoformat(service['service_date']+'T'+(service['start_time'] or '00:00')).replace(tzinfo=zone)
        finish=datetime.fromisoformat(service['service_date']+'T'+(service['end_time'] or '23:59')).replace(tzinfo=zone)
        if finish<=begin:finish+=timedelta(days=1)
    uid=sha256((setting(db,'calendar_instance_uuid')+'|'+str(service['id'])+'|'+str(group['slot_uuid'] or '')).encode()).hexdigest()+'@openfablab.local'
    location=', '.join(filter(None,[setting(db,'structure_name'),setting(db,'structure_address'),setting(db,'structure_postal_code'),setting(db,'structure_city')]))
    from animation_information import optional_url
    stamps=[]
    for raw in (service['updated_at'],dict(group).get('updated_at')):
        try:stamps.append(datetime.fromisoformat(raw).astimezone(timezone.utc))
        except (ValueError,TypeError):pass
    updated=max(stamps).isoformat() if stamps else datetime.now(timezone.utc).isoformat()
    return dict(uid=uid,title=service['title'],description=service['description'] or '',start=begin.isoformat(),end=finish.isoformat(),
                timezone=str(zone),location=location,url=optional_url(service['information_url']),updated=updated,
                cancelled=group['status']=='cancelled')

def ics(value):
    start=datetime.fromisoformat(value['start']).astimezone(timezone.utc)
    end=datetime.fromisoformat(value['end']).astimezone(timezone.utc)
    try:updated=datetime.fromisoformat(value['updated']).astimezone(timezone.utc)
    except (ValueError,TypeError):updated=datetime.now(timezone.utc)
    # UTC timestamps are interoperable, including both DST folds. The original
    # timezone remains available as informational metadata, never as a second clock.
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//OpenFabLab//Participant Calendar//EN',
           'CALSCALE:GREGORIAN','METHOD:'+('CANCEL' if value['cancelled'] else 'PUBLISH'),'BEGIN:VEVENT',
           'UID:'+value['uid'],'DTSTAMP:'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
           'LAST-MODIFIED:'+updated.strftime('%Y%m%dT%H%M%SZ'),'SEQUENCE:'+str(int(updated.timestamp())),
           'DTSTART:'+start.strftime('%Y%m%dT%H%M%SZ'),'DTEND:'+end.strftime('%Y%m%dT%H%M%SZ'),
           'SUMMARY:'+_escape(value['title']),'DESCRIPTION:'+_escape(value['description']),
           'LOCATION:'+_escape(value['location']),'X-WR-TIMEZONE:'+_escape(value['timezone']),
           'STATUS:'+('CANCELLED' if value['cancelled'] else 'CONFIRMED')]
    if value['url']:lines.append('URL:'+value['url'])
    lines+=['END:VEVENT','END:VCALENDAR']
    return ('\r\n'.join(part for line in lines for part in _fold(line))+'\r\n').encode('utf-8')

def google(value):
    dates='/'.join(datetime.fromisoformat(value[k]).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ') for k in ('start','end'))
    return 'https://calendar.google.com/calendar/render?'+urlencode(dict(action='TEMPLATE',text=value['title'],dates=dates,
        details=value['description'],location=value['location'],ctz=value['timezone']))

def attach(db,message,row,kind):
    if setting(db,'reservation_calendar_enabled','1')!='1' or kind not in ('confirmed','accepted','modified','cancelled'):return
    group=db.execute('SELECT * FROM family_booking_groups WHERE group_uuid=?',(row['group_uuid'],)).fetchone()
    if not group or group['status'] not in ('confirmed','cancelled') or (group['status']=='cancelled' and kind!='cancelled'):return
    value=event(db,group)
    notice='Après modification ou annulation, importez le nouveau fichier ; la synchronisation automatique n’est pas garantie.'
    if value['cancelled']:
        section='\n\nCalendrier : cette réservation est annulée. Le fichier animation.ics joint porte cette annulation.\n'+notice+'\n'
        block='<hr><p>Calendrier : cette réservation est annulée. Le fichier animation.ics joint porte cette annulation.</p><p>'+notice+'</p>'
    else:
        section='\n\nAjouter à mon calendrier :\nApple, Outlook et autres calendriers : fichier animation.ics joint.\nGoogle Agenda : '+google(value)+'\n'+notice+'\n'
        block='<hr><p>Ajouter à mon calendrier : fichier animation.ics joint (Apple, Outlook et autres calendriers), ou <a href="'+escape(google(value),quote=True)+'">Google Agenda</a>.</p><p>'+notice+'</p>'
    for part in list(message.walk()):
        if part.get_content_type()=='text/plain':part.set_content(part.get_content()+section)
        elif part.get_content_type()=='text/html':
            content=part.get_content()
            # Customized models may be fragments, not complete HTML documents.
            import re
            content,count=re.subn(r'</body\s*>',lambda match:block+match[0],content,count=1,flags=re.I)
            part.set_content(content if count else content+block,subtype='html')
    message.add_attachment(ics(value),maintype='text',subtype='calendar',filename='animation.ics')
