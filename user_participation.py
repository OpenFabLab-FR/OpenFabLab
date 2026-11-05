"""Observed attendance and voluntary booking restrictions, never automatic sanctions."""
from datetime import date,datetime,timezone
from zoneinfo import ZoneInfo
from uuid import uuid4
from evolution_schema import audit,now
from memberships import atomic
from family_model import setting

def active_restriction(db,user_id,day=None):
    day=day or datetime.now(ZoneInfo(setting(db,'structure_timezone','Europe/Paris'))).date().isoformat()
    return db.execute('''SELECT * FROM user_booking_restrictions WHERE user_id=? AND revoked_at IS NULL
        AND starts_on<=? AND ends_on>=? ORDER BY created_at DESC LIMIT 1''',(user_id,day,day)).fetchone()

def check_new_booking(db,ids):
    if any(active_restriction(db,int(key)) for key in ids):
        raise ValueError('Les nouvelles réservations d’animations sont temporairement suspendues pour un participant. Contactez l’équipe.')

def restrict(db,user_id,values,role):
    if role!='admin':raise PermissionError('Décision réservée à l’Administrateur.')
    from datetime import date
    start,end=(date.fromisoformat(str(values.get(k,''))) for k in ('starts_on','ends_on'))
    reason=str(values.get('reason','')).strip()
    if end<start or not reason or len(reason)>1000:raise ValueError('Dates cohérentes et motif administratif requis.')
    key=str(uuid4())
    with atomic(db):
        if not db.execute('SELECT 1 FROM users WHERE id=?',(user_id,)).fetchone():raise ValueError('Usager inconnu.')
        db.execute('INSERT INTO user_booking_restrictions VALUES(?,?,?,?,?,?,?,NULL)',(key,user_id,start.isoformat(),end.isoformat(),reason,role,now()))
        audit(db,'user_restriction',key,'created',role,{'user_id':user_id})
    return key

def lift(db,key,role):
    if role!='admin':raise PermissionError('Décision réservée à l’Administrateur.')
    with atomic(db):
        row=db.execute('SELECT * FROM user_booking_restrictions WHERE restriction_uuid=?',(key,)).fetchone()
        if not row:raise ValueError('Restriction inconnue.')
        if row['revoked_at']:return False
        db.execute('UPDATE user_booking_restrictions SET revoked_at=? WHERE restriction_uuid=?',(now(),key))
        audit(db,'user_restriction',key,'lifted',role)
    return True

def history(db,user_id,current=None):
    current=current or datetime.now(timezone.utc);zone=ZoneInfo(setting(db,'structure_timezone','Europe/Paris'))
    rows=[];counts={'present':0,'absent':0,'unknown':0,'cancelled':0}
    from animation_attendance import interval
    for row in db.execute('''SELECT b.*,s.title,s.service_date,s.start_time,s.end_time,sl.starts_at AS slot_start,sl.ends_at AS slot_end
        FROM animation_bookings b JOIN fablab_services s ON s.id=b.service_id
        LEFT JOIN animation_slots sl ON sl.slot_uuid=b.slot_uuid WHERE b.user_id=? ORDER BY s.service_date DESC,b.created_at DESC''',(user_id,)):
        r=dict(row)
        try:
            span=interval(r,zone)
            started=bool(span and span[0]<=current);past=bool(span and span[1]<=current)
        except (ValueError,TypeError):started=past=False
        # Older explicit attendance can survive missing historical hours. A
        # future date or an invalid slot never becomes observed attendance.
        if not started and not r['slot_uuid']:
            try:
                if date.fromisoformat(r['service_date'])<current.astimezone(zone).date():started=past=True
            except (ValueError,TypeError):pass
        if r['status'] in ('cancelled','declined','expired','refused'):state='cancelled'
        elif r['status'] in ('confirmed','present','absent') and (r['is_present']==1 or r['status']=='present') and started:state='present'
        elif r['status'] in ('confirmed','present','absent') and (r['is_present']==0 or r['status']=='absent') and past:state='absent'
        else:state='unknown'
        counts[state]+=1;rows.append(r|dict(attendance_state=state,ended=past))
    return dict(rows=rows,counts=counts)
