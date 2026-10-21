"""Shared, read-only statistical semantics; never infer that an event was held."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

MONTHS=('janvier','février','mars','avril','mai','juin','juillet','août','septembre','octobre','novembre','décembre')

def local_zone(db):
    row=db.execute("SELECT value FROM app_settings WHERE key='structure_timezone'").fetchone()
    return ZoneInfo(row[0] if row else 'Europe/Paris')

def french_date(value):
    day=date.fromisoformat(value) if isinstance(value,str) else value
    return f'{day.day} {MONTHS[day.month-1]} {day.year}'

def _instant(value):
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:raise ValueError('Timestamp must carry its timezone')
    return parsed.astimezone(timezone.utc)

def animation_end(db,row,zone):
    """Latest reserved slot end, otherwise local schedule; no realization flag exists."""
    slots=db.execute('SELECT ends_at FROM animation_slots WHERE service_id=?',(row['id'],)).fetchall()
    try:
        if slots:return max(_instant(slot[0]) for slot in slots)
        day=date.fromisoformat(row['service_date'])
        if row['end_time']:
            naive=datetime.combine(day,time.fromisoformat(row['end_time']))
            # Conservative at DST folds: never count as ended before both interpretations.
            valid=[]
            for fold in (0,1):
                moment=naive.replace(tzinfo=zone,fold=fold).astimezone(timezone.utc)
                if moment.astimezone(zone).replace(tzinfo=None)==naive:valid.append(moment)
            return max(valid) if valid else None
        return datetime.combine(day+timedelta(days=1),time(),zone).astimezone(timezone.utc)
    except (ValueError,TypeError):return None

def service_statistics(db,year,now=None):
    now=now or datetime.now(timezone.utc);zone=local_zone(db)
    rows=db.execute('SELECT * FROM fablab_services ORDER BY service_date').fetchall()
    selected=[r for r in rows if year=='total' or r['service_date'][:4]==str(year)]
    animations=[r for r in selected if r['service_type']=='animation']
    past=[];undated=0
    for row in animations:
        end=animation_end(db,row,zone)
        if end is None:undated+=1
        elif end<=now:past.append(row)
    participants=0;missing=0;unknown_bookings=0;anonymous=0
    for row in past:
        # Stored totals preserve legacy manual participation; never add bookings again.
        participants+=row['actual_participants'] or 0
        walkin=db.execute('SELECT quantity FROM animation_walkins WHERE service_id=?',(row['id'],)).fetchone()
        anonymous+=walkin[0] if walkin else 0
        states=db.execute("SELECT is_present,status FROM animation_bookings WHERE service_id=? AND status IN('confirmed','present','absent')",(row['id'],)).fetchall()
        unknown=sum(r['is_present'] is None and r['status']=='confirmed' for r in states)
        unknown_bookings+=unknown
        # Legacy zero cannot prove that attendance was explicitly recorded.
        if unknown or not states and not row['actual_participants']:missing+=1
    reservations=[r for r in selected if r['service_type']=='reservation']
    rentals=[r for r in selected if r['service_type']=='rental']
    revenue=sum(r['amount_cents'] or 0 for r in reservations+rentals)
    return dict(animations=len(past),animations_scheduled=len(animations),
        animations_upcoming=len(animations)-len(past)-undated,animations_undated=undated,
        animation_participants=participants,animation_anonymous=anonymous,
        animation_presence_incomplete=missing,animation_unknown_bookings=unknown_bookings,
        animation_duration_minutes=sum(r['duration_minutes'] or 0 for r in past),
        reservations=len(reservations),reservation_participants=sum(r['participants'] or 0 for r in reservations),
        reservation_duration_minutes=sum(r['duration_minutes'] or 0 for r in reservations),
        rentals=len(rentals),rental_duration_minutes=sum(r['duration_minutes'] or 0 for r in rentals),
        revenue_cents=revenue,revenue=f'{revenue/100:.2f}'.replace('.',','),
        years=sorted({int(r['service_date'][:4]) for r in rows if r['service_date'][:4].isdigit()},reverse=True))

def coverage(db,year,sessions,visitors,now=None):
    zone=local_zone(db);today=(now or datetime.now(timezone.utc)).astimezone(zone).date()
    session_days=[s['local_date'] for s in sessions if s['local_date']<=today]
    visitor_days=[v['local_date'] for v in visitors if v['local_date']<=today]
    days=session_days+visitor_days
    selected=[d for d in days if year=='total' or d.year==year]
    first=min(days).isoformat() if days else None
    selected_first=min(selected).isoformat() if selected else None
    animation=db.execute("SELECT MIN(service_date) FROM fablab_services WHERE service_type='animation'").fetchone()[0]
    message=f'Fréquentation enregistrée depuis le {french_date(first)}.' if first else 'Aucune donnée de fréquentation enregistrée.'
    last=max(days).isoformat() if days else None
    selected_last=max(selected).isoformat() if selected else None
    partial=bool(selected and year!='total' and (min(days)>date(year,1,1) or max(days)<date(year,12,31)))
    period=(f'Données observées dans la période : du {french_date(selected_first)} au {french_date(selected_last)}.' if selected_first else 'Aucune donnée pour cette période.')
    if partial:period+=' Période partielle ; les journées sans enregistrement ne prouvent pas une fermeture.'
    return dict(first=first,last=last,selected_first=selected_first,selected_last=selected_last,partial=partial,message=message,period=period,
        sessions_first=min(session_days).isoformat() if session_days else None,
        visitors_first=min(visitor_days).isoformat() if visitor_days else None,
        animations_first=animation,timezone=str(zone))
