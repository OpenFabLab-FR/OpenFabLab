"""Public calendar history, separate from booking visibility. Read only."""
import calendar
from datetime import date,datetime,timedelta,timezone
from animation_publication import clock
from animation_information import optional_url

def month_before(day):
    year,month=(day.year,day.month-1) if day.month>1 else (day.year-1,12)
    return date(year,month,min(day.day,calendar.monthrange(year,month)[1]))

def hidden(db,kind,key,day):
    row=db.execute('SELECT hidden FROM calendar_visibility WHERE event_kind=? AND event_key=? AND occurrence_date=?',(kind,str(key),str(day))).fetchone()
    return bool(row and row[0])

def past_animations(db,environment,first,now,zone,details=False):
    events=[]
    for row in db.execute("SELECT s.*,c.* FROM fablab_services s JOIN animation_reservation_config c ON c.service_id=s.id WHERE s.service_type='animation' AND c.enabled=1 AND c.environment=? AND s.service_date>=? AND s.service_date<=? ORDER BY s.service_date,s.id",(environment,first.isoformat(),now.astimezone(zone).date().isoformat())):
        item=dict(row)
        if not item['start_time'] or not item['end_time'] or hidden(db,'animation',item['service_id'],item['service_date']):continue
        try:info=clock(db,item,now);end=datetime.fromisoformat(info['ends_at'])
        except (ValueError,TypeError):continue
        if end<=datetime.fromisoformat(info['starts_at']):continue
        if end>now or now<end+timedelta(hours=24):continue
        # No realization/cancellation flag exists. Positive observed attendance
        # is conservative evidence; an old blank/zero is not invented as held.
        observed=(item['actual_participants'] or 0)>0 or db.execute("SELECT 1 FROM animation_bookings WHERE service_id=? AND environment=? AND status IN('confirmed','present','absent') AND COALESCE(is_present,status='present')=1 LIMIT 1",(item['service_id'],environment)).fetchone()
        if not observed or info['hide_before_opening'] and info['signup_open_at'] and now<datetime.fromisoformat(info['signup_open_at']):continue
        event=dict(id='animation-'+str(item['service_id']),kind='animation',title=item['title'],start=info['starts_at'],end=info['ends_at'],service_id=item['service_id'],information_url=optional_url(item.get('information_url','')),availability_state='ended',signup_open_at=info['signup_open_at'],hide_before_opening=info['hide_before_opening'],public_until=info['public_until'],close_at=info['starts_at'])
        event['history_eligible']=True
        if details:
            event['description']=item.get('description') or ''
            if item['booking_mode']=='slots':
                event['slots']=[dict(start=s['starts_at'],end=s['ends_at'],capacity=s['capacity'],availability_state='ended',close_at=s['starts_at']) for s in db.execute('SELECT * FROM animation_slots WHERE service_id=? AND active=1 ORDER BY starts_at',(item['service_id'],))]
            elif item['capacity'] is not None:event['capacity']=item['capacity']
        events.append(event)
    return events
