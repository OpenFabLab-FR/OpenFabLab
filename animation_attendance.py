"""Internal attendance only: never reserve, promote a waitlist or send a message."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from memberships import atomic
from family_model import setting
from reservations_sync import booking_counts


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def ensure(db):
    """Schema 22, inside the additive migration transaction. No historical replay."""
    db.execute('''CREATE TABLE IF NOT EXISTS animation_attendance_origin(
        booking_uuid TEXT PRIMARY KEY REFERENCES animation_bookings(external_uuid) ON DELETE CASCADE,
        origin TEXT NOT NULL CHECK(origin IN('manual','kiosk')),recorded_at TEXT NOT NULL,
        session_id INTEGER REFERENCES sessions(id) ON DELETE SET NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS animation_walkins(
        service_id INTEGER PRIMARY KEY REFERENCES fablab_services(id) ON DELETE CASCADE,
        quantity INTEGER NOT NULL CHECK(quantity BETWEEN 0 AND 100000),updated_at TEXT NOT NULL)''')
    # Preserve previous stored totals verbatim. Only seed their anonymous component;
    # an explicit subsequent presence change recomputes the total from its sources.
    db.execute('''INSERT OR IGNORE INTO animation_walkins
        SELECT s.id,MAX(0,CASE WHEN c.enabled=1 THEN c.walkin_count ELSE
          COALESCE(s.actual_participants,0)-(SELECT COUNT(*) FROM animation_bookings b
          WHERE b.service_id=s.id AND b.status IN('confirmed','present','absent')
          AND COALESCE(b.is_present,b.status='present')=1) END),?
        FROM fablab_services s LEFT JOIN animation_reservation_config c ON c.service_id=s.id
        WHERE s.service_type='animation' ''', (stamp(),))
    db.execute("INSERT OR IGNORE INTO app_settings VALUES('animation_auto_presence_enabled','1')")
    db.execute("INSERT OR IGNORE INTO app_settings VALUES('animation_auto_presence_since',?)", (stamp(),))
    db.execute('CREATE INDEX IF NOT EXISTS animation_attendance_users ON animation_bookings(user_id,status,service_id)')
    # All entry points (including cancellations from the WordPress engine) keep
    # aggregates consistent. These triggers do not change booking or seat counts.
    for operation, ref in (('INSERT','NEW'),('UPDATE OF is_present,status,service_id','NEW'),('DELETE','OLD')):
        name={'INSERT':'insert','DELETE':'delete'}.get(operation,'update')
        db.execute(f'''CREATE TRIGGER IF NOT EXISTS attendance_total_{name} AFTER {operation} ON animation_bookings
            BEGIN UPDATE fablab_services SET actual_participants=
              COALESCE((SELECT quantity FROM animation_walkins WHERE service_id={ref}.service_id),
                       (SELECT walkin_count FROM animation_reservation_config WHERE service_id={ref}.service_id),0)
              +(SELECT COUNT(*) FROM animation_bookings b WHERE b.service_id={ref}.service_id
                AND b.status IN('confirmed','present','absent') AND COALESCE(b.is_present,b.status='present')=1)
              WHERE id={ref}.service_id; END''')


def total(db, service_id):
    db.execute('''UPDATE fablab_services SET actual_participants=
        COALESCE((SELECT quantity FROM animation_walkins WHERE service_id=?),0)+
        (SELECT COUNT(*) FROM animation_bookings WHERE service_id=? AND status IN('confirmed','present','absent')
         AND COALESCE(is_present,status='present')=1) WHERE id=?''',(service_id,service_id,service_id))


def summary(db, service_id, bookings):
    counts=booking_counts(bookings)
    row=db.execute('SELECT quantity FROM animation_walkins WHERE service_id=?',(service_id,)).fetchone()
    anonymous=row[0] if row else 0
    return dict(expected=counts['confirmed']-counts['present']-counts['absent'],
                anonymous=anonymous,actual=counts['present']+anonymous)


def manual(db, service_id, booking_uuid, action, role):
    if role not in ('admin','moderator') or action not in ('present','absent','unknown'):
        raise ValueError('Action non autorisée.')
    with atomic(db):
        booking=db.execute('SELECT * FROM animation_bookings WHERE external_uuid=? AND service_id=?',
                           (booking_uuid,service_id)).fetchone()
        if not booking or booking['status'] not in ('confirmed','present','absent'):
            raise ValueError('Confirmez d’abord l’inscription avant de renseigner sa présence.')
        value={'present':1,'absent':0,'unknown':None}[action];now=stamp()
        db.execute("UPDATE animation_bookings SET status='confirmed',is_present=?,updated_at=? WHERE external_uuid=?",
                   (value,now,booking_uuid))
        db.execute("INSERT INTO animation_attendance_origin VALUES(?,'manual',?,NULL) ON CONFLICT(booking_uuid) DO UPDATE SET origin='manual',recorded_at=excluded.recorded_at,session_id=NULL",(booking_uuid,now))
        db.execute('INSERT INTO reservation_actions(booking_uuid,action,actor_role,created_at) VALUES(?,?,?,?)',
                   (booking_uuid,action,role,now))
        total(db,service_id)


def set_walkins(db, service_id, value, role):
    if role not in ('admin','moderator') or not str(value).isdecimal() or not 0<=int(value)<=100000:
        raise ValueError('Indiquez un nombre de participants entre 0 et 100 000.')
    with atomic(db):
        if not db.execute("SELECT 1 FROM fablab_services WHERE id=? AND service_type='animation'",(service_id,)).fetchone():
            raise ValueError('Animation inconnue.')
        db.execute('INSERT INTO animation_walkins VALUES(?,?,?) ON CONFLICT(service_id) DO UPDATE SET quantity=excluded.quantity,updated_at=excluded.updated_at',
                   (service_id,int(value),stamp()))
        db.execute('UPDATE animation_reservation_config SET walkin_count=? WHERE service_id=?',(int(value),service_id))
        total(db,service_id)


def configure(db, enabled):
    with atomic(db):
        previous=setting(db,'animation_auto_presence_enabled','1')
        db.execute("INSERT INTO app_settings VALUES('animation_auto_presence_enabled',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",('1' if enabled else '0',))
        if enabled and previous!='1':
            # Re-enabling is prospective, not a replay of the disabled period.
            db.execute("UPDATE app_settings SET value=? WHERE key='animation_auto_presence_since'",(stamp(),))


def interval(row, zone):
    if row['slot_uuid']:
        if not row['slot_start'] or not row['slot_end']:return None
        start,end=(datetime.fromisoformat(row[k]) for k in ('slot_start','slot_end'))
        if start.tzinfo is None or end.tzinfo is None:return None
    else:
        values=[]
        for key in ('start_time','end_time'):
            wall=datetime.fromisoformat(row['service_date']+'T'+row[key])
            start=wall.replace(tzinfo=zone)
            # Refuse ambiguous/nonexistent local times, as the slot engine does.
            if (start.utcoffset()!=wall.replace(tzinfo=zone,fold=1).utcoffset() or
                    start.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)!=wall):return None
            values.append(start)
        start,end=values
    start,end=start.astimezone(timezone.utc),end.astimezone(timezone.utc)
    return (start,end) if end>start else None


def process(db, now=None, user_id=None):
    """Bounded current-day scan, also called by the native 30s worker.

    Half-open event intervals; an open arrival at exactly the start is evidence.
    Any competing overlapping confirmed registration prevents automation, even
    when one of its statuses was set manually. No PII is copied into the origin.
    """
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None:raise ValueError('Une date avec fuseau est nécessaire.')
    now=now.astimezone(timezone.utc)
    changed=0
    with atomic(db):
        # Preference and horizon are read under the same writer lock as the
        # validation: a concurrent disable/manual decision cannot be bypassed.
        if setting(db,'animation_auto_presence_enabled','1')!='1':return 0
        if any(setting(db,'module_'+key,'1')!='1' for key in ('activities','frequency','users')):return 0
        since=datetime.fromisoformat(setting(db,'animation_auto_presence_since',now.isoformat()))
        zone=ZoneInfo(setting(db,'structure_timezone','Europe/Paris'))
        day=now.astimezone(zone).date().isoformat()
        rows=db.execute('''SELECT b.*,s.service_date,s.start_time,s.end_time,
            sl.starts_at AS slot_start,sl.ends_at AS slot_end,o.origin
            FROM fablab_services s JOIN animation_bookings b ON b.service_id=s.id
            LEFT JOIN animation_slots sl ON sl.slot_uuid=b.slot_uuid AND sl.service_id=s.id
            LEFT JOIN animation_attendance_origin o ON o.booking_uuid=b.external_uuid
            WHERE s.service_type='animation' AND s.service_date=? AND b.environment='production'
              AND b.status IN('confirmed','present','absent') AND b.user_id IS NOT NULL
              AND b.link_status IN('registered','matched','manual')'''+
            (' AND b.user_id=?' if user_id is not None else ''),(day,user_id) if user_id is not None else (day,)).fetchall()
        ranges={}
        for row in rows:
            try:ranges[row['external_uuid']]=interval(row,zone)
            except (ValueError,TypeError):ranges[row['external_uuid']]=None
        by_user={};ambiguous=set()
        for row in rows:
            if ranges[row['external_uuid']]:by_user.setdefault(row['user_id'],[]).append(row)
        for bookings in by_user.values():
            leader=None;limit=None
            for booking in sorted(bookings,key=lambda b:ranges[b['external_uuid']][0]):
                begin,finish=ranges[booking['external_uuid']]
                if limit is not None and begin<limit:
                    ambiguous.update((leader,booking['external_uuid']))
                if limit is None or begin>=limit or finish>limit:
                    leader=booking['external_uuid'];limit=finish
        for row in rows:
            current=ranges[row['external_uuid']]
            if not current or row['status']!='confirmed' or row['is_present'] is not None or row['origin']:
                continue
            start,end=current
            if start>now or end<=since:continue
            if row['external_uuid'] in ambiguous:continue
            evidence=db.execute('''SELECT id,check_in,check_out FROM sessions WHERE user_id=?
                AND entry_method IN('id','qr','manual','list') AND julianday(check_in)<julianday(?)
                AND (check_out IS NULL OR julianday(check_out)>julianday(?)) ORDER BY check_in DESC''',
                (row['user_id'],end.isoformat(),max(start,since).isoformat())).fetchall()
            for passage in evidence:
                try:
                    arrival=datetime.fromisoformat(passage['check_in'])
                    departure=datetime.fromisoformat(passage['check_out']) if passage['check_out'] else now
                    if arrival.tzinfo is None or departure.tzinfo is None:continue
                    begin=max(start,since,arrival);finish=min(end,now,departure)
                    if not (begin<finish or (passage['check_out'] is None and begin==finish==arrival and start<=arrival<end)):continue
                except (ValueError,TypeError):continue
                db.execute('UPDATE animation_bookings SET is_present=1,updated_at=? WHERE external_uuid=? AND is_present IS NULL',
                           (now.isoformat(timespec='seconds'),row['external_uuid']))
                db.execute("INSERT INTO animation_attendance_origin VALUES(?,'kiosk',?,?)",
                           (row['external_uuid'],now.isoformat(timespec='seconds'),passage['id']))
                changed+=1
                break
    return changed
