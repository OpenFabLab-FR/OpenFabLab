"""Shared validation; progress uses app_settings, never a shadow configuration."""
import json
import re
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
STEPS=('identity','kiosk','hours','modules','resources','communications','summary')

def hours(schedule,form):
    result={}
    for day in schedule:
        start=form.get(day['key']+'_start','').strip();end=form.get(day['key']+'_end','').strip()
        if start or end:
            if not all(re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',v) for v in (start,end)) or end<=start:
                raise ValueError('Renseignez une plage horaire valide, ou laissez les deux champs vides.')
            if any(int(v[-2:])%15 for v in (start,end)):raise ValueError('Utilisez des quarts d’heure complets.')
        result['openlab_attendance_'+day['key']+'_start']=start
        result['openlab_attendance_'+day['key']+'_end']=end
    return result

def module_errors(db,selected):
    errors=[]
    if not selected['authorizations']:
        dependent=db.execute('SELECT name FROM resources WHERE active=1 AND required_authorization IS NOT NULL').fetchall()
        if dependent:
            errors.append('Impossible de désactiver Formations et habilitations : ressources actives dépendantes : '
                          +', '.join(row['name'] for row in dependent)+'. Retirez explicitement leurs exigences ou désactivez ces ressources.')
    if selected['public_reservations'] and not selected['activities']:
        errors.append('Les réservations publiques nécessitent le module Activités.')
    if (selected['booking_slots'] or selected['rentals']) and not selected['billing']:
        errors.append('Les créneaux réservables et locations nécessitent le module Facturation.')
    return errors

def progress(raw):
    try:value=json.loads(raw)
    except (ValueError,TypeError):value={}
    if not isinstance(value,dict):value={}
    return dict(step=value.get('step') if value.get('step') in STEPS else 'identity',
                done=[s for s in value.get('done',[]) if s in STEPS] if isinstance(value.get('done',[]),list) else [],
                revision=value.get('revision') if type(value.get('revision')) is int and value['revision']>=0 else 0)

def identity(form):
    result={}
    for key,limit in (('name',120),('short_name',60),('city',120),('country',80),('timezone',80)):
        value=form.get(key,'').strip()
        if len(value)>limit or key in ('name','timezone') and not value:
            raise ValueError('Renseignez le nom de la structure et un fuseau horaire valide.')
        result['structure_'+key]=value
    try:ZoneInfo(result['structure_timezone'])
    except (ZoneInfoNotFoundError,ValueError):raise ValueError('Le fuseau horaire n’est pas reconnu.') from None
    return result
