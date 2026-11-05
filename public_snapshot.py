"""Explicit publication projection, never an internal calendar serialization."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from family_model import setting
from machine_maintenance import public_machines

def build(db,environment,calendar=False,machines=False,now=None,details=False,display_options=False,history=False,availability=False):
    if environment not in ('production','test'):raise ValueError('Environnement invalide.')
    zone=ZoneInfo(setting(db,'structure_timezone','Europe/Paris'));now=now or datetime.now(zone)
    if now.tzinfo is None:raise ValueError('Date explicite requise.')
    today=now.astimezone(zone).date();start=today-timedelta(days=today.weekday()+7);end=start+timedelta(days=98)
    from public_calendar_history import month_before,hidden,past_animations
    first=month_before(today)
    if history:start=first-timedelta(days=first.weekday())
    result=dict(version=1,timezone=str(zone),coverage_start=start.isoformat(),coverage_end=end.isoformat())
    if history:result['history_start']=first.isoformat()
    if calendar:
        from app import load_openlab_schedule,load_modules
        from openlab_openings import public_openings
        schedule=load_openlab_schedule(db);events=public_openings(db,schedule,start,end)
        if details and display_options:
            from openlab_openings import attendance_average
            averages={}
            for event in events:
                begin=datetime.fromisoformat(event['start']);finish=datetime.fromisoformat(event['end'])
                key=(begin.weekday(),begin.strftime('%H:%M'),finish.strftime('%H:%M'))
                if key not in averages:averages[key]=attendance_average(db,schedule,*key,now)
                if averages[key]:event['attendance_average']=averages[key]
        if load_modules(db)['activities'] and load_modules(db)['public_reservations']:
            from outbound_actions import public_catalogue
            for item in public_catalogue(db,environment,True,True,True,current=now):
                info=item.get('publication',{})
                if not info or not start<=datetime.fromisoformat(info['starts_at'].replace('Z','+00:00')).astimezone(zone).date()<end:continue
                event=dict(id='animation-'+str(item['service_id']),kind='animation',title=item['title'],
                    start=info['starts_at'],end=info['ends_at'],service_id=item['service_id'],
                    information_url=item.get('information_url',''),availability_state=item['availability_state'],
                    signup_open_at=info['signup_open_at'],hide_before_opening=info['hide_before_opening'],public_until=info['public_until'],
                    close_at=(datetime.fromisoformat(info['starts_at'].replace('Z','+00:00'))-timedelta(minutes=info['close_minutes'])).isoformat())
                if details:
                    event['description']=item['description']
                    service=db.execute('SELECT capacity FROM animation_reservation_config WHERE service_id=?',(item['service_id'],)).fetchone()
                    if item['booking_mode']=='slots':
                        capacities={r['slot_uuid']:r['capacity'] for r in db.execute('SELECT slot_uuid,capacity FROM animation_slots WHERE service_id=? AND active=1',(item['service_id'],))}
                        event['slots']=[dict(start=s['starts_at'],end=s['ends_at'],capacity=capacities[s['slot_uuid']],availability_state=s['availability_state'],
                            close_at=(datetime.fromisoformat(s['starts_at'].replace('Z','+00:00'))-timedelta(minutes=info['close_minutes'])).isoformat()) for s in item['slots'] if s['slot_uuid'] in capacities]
                    elif service and service[0] is not None:event['capacity']=service[0]
                events.append(event)
        if history and load_modules(db)['activities'] and load_modules(db)['public_reservations']:
            events.extend(past_animations(db,environment,first,now,zone,details))
        events=[e for e in events if (not history or datetime.fromisoformat(e['start'].replace('Z','+00:00')).astimezone(zone).date()>=first) and not hidden(db,e['kind'],e.get('service_id',datetime.fromisoformat(e['start']).astimezone(zone).date().isoformat()),datetime.fromisoformat(e['start']).astimezone(zone).date().isoformat())]
        if history:
            for event in events:event.setdefault('history_eligible',False)
        result['calendar']=events
    if machines:
        result['machines']=public_machines(db,details=details,effective=availability)
        if display_options:
            from public_resource_labels import choice
            result['resource_label']=choice(db)
    return result
