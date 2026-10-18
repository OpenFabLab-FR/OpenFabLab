"""Admission bound only. Never prune existing bookings, FIFO or pending offers."""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import family_model as family

GENERAL_MODES={'automatic':'Automatique — 100 % de la capacité','custom':'Personnalisé','unlimited':'Sans limite'}
SERVICE_MODES={'general':'Utiliser le réglage général','custom':'Limite personnalisée','unlimited':'Sans limite'}

def integer(value):
    if isinstance(value,bool):raise ValueError('Limite entière de 0 à 100 000 personnes requise.')
    try:
        text=str(value).strip();number=int(text)
        if not text.isdigit() or not 0<=number<=100000:raise ValueError
        return number
    except (ValueError,TypeError):raise ValueError('Limite entière de 0 à 100 000 personnes requise.') from None

def settings(db):
    mode=family.setting(db,'reservation_waitlist_limit_mode','automatic')
    if mode not in GENERAL_MODES:mode='automatic'
    try:value=integer(family.setting(db,'reservation_waitlist_limit_value','0'))
    except ValueError:value=0
    return dict(mode=mode,value=value)

def limit(db,service):
    service=dict(service);mode=service.get('waitlist_limit_mode','general')
    if mode=='general':
        general=settings(db);mode=general['mode'];value=general['value']
    else:value=service.get('waitlist_limit_value',0)
    if mode=='unlimited':return None
    if mode=='automatic':return int(service['capacity'])
    return integer(value if value is not None else 0)

def waiting(db,service_id,slot=None,environment='production'):
    return db.execute("SELECT COUNT(*) FROM animation_bookings WHERE service_id=? AND environment=? AND COALESCE(slot_uuid,'')=? AND status='waitlisted'",(service_id,environment,slot or '')).fetchone()[0]

def require_room(db,service,people,slot=None,environment='production'):
    maximum=limit(db,service)
    count=waiting(db,service['service_id'],slot,environment)
    if maximum is not None and count+people>maximum:
        raise ValueError('La liste d’attente ne peut plus accueillir tout le groupe. Aucune inscription n’a été créée ; réessayez si des places se libèrent.')

def observe(db,service,slot=None,environment='production',notify=True):
    """Called only inside business/configuration transactions, never from sync."""
    from reservations_sync import booking_capacity_used
    service=dict(service);maximum=limit(db,service);count=waiting(db,service['service_id'],slot,environment)
    full=bool(service['enabled'] and service['waitlist_enabled'] and maximum is not None and maximum>0 and count>=maximum)
    previous=db.execute('SELECT is_full,sequence FROM waitlist_full_state WHERE service_id=? AND environment=? AND slot_key=?',(service['service_id'],environment,slot or '')).fetchone()
    sequence=previous['sequence'] if previous else 0
    crossing=full and not (previous and previous['is_full'])
    if crossing:sequence+=1
    db.execute('''INSERT INTO waitlist_full_state VALUES(?,?,?,?,?)
        ON CONFLICT(service_id,environment,slot_key) DO UPDATE SET is_full=excluded.is_full,sequence=excluded.sequence''',
        (service['service_id'],environment,slot or '',int(full),sequence))
    if crossing and notify:
        from reservation_notifications import queue
        confirmed=db.execute("SELECT COUNT(*) FROM animation_bookings WHERE service_id=? AND environment=? AND COALESCE(slot_uuid,'')=? AND status IN('confirmed','present','absent')",(service['service_id'],environment,slot or '')).fetchone()[0]
        snapshot={'capacity':service['capacity'],'occupied':booking_capacity_used(db,service['service_id'],slot),'confirmed':confirmed,'waiting':count,'waiting_limit':maximum}
        from reservation_notifications import slot_snapshot
        snapshot.update(slot_snapshot(db,slot))
        queue(db,'waitlist-full/'+str(service['service_id'])+'/'+environment+'/'+(slot or '')+'/'+str(sequence),
            'waitlist_full',service['service_id'],environment,presentation=snapshot)

def observe_service(db,service_id,notify=True,only_missing=False):
    from family_reservations import effective_service
    row=db.execute('SELECT * FROM animation_reservation_config WHERE service_id=?',(service_id,)).fetchone()
    if not row:return
    slots=[r[0] for r in db.execute('SELECT slot_uuid FROM animation_slots WHERE service_id=? AND active=1',(service_id,))] if row['booking_mode']=='slots' else [None]
    for slot in slots:
        if only_missing and db.execute('SELECT 1 FROM waitlist_full_state WHERE service_id=? AND environment=? AND slot_key=?',(service_id,row['environment'],slot or '')).fetchone():continue
        if not row['enabled']:
            db.execute('UPDATE waitlist_full_state SET is_full=0 WHERE service_id=? AND environment=? AND slot_key=?',(service_id,row['environment'],slot or ''));continue
        observe(db,effective_service(db,service_id,slot,row['environment'],False),slot,row['environment'],notify)

def seed_states(db):
    for row in db.execute('SELECT service_id FROM animation_reservation_config').fetchall():observe_service(db,row[0],False,True)

def availability(db,service,slot=None,environment='production',now=None):
    """Read-only snapshot for UI; the locked engine revalidates at submission."""
    from reservations_sync import booking_capacity_used
    service=dict(service);zone=ZoneInfo(family.setting(db,'structure_timezone','Europe/Paris'))
    current=now or datetime.now(timezone.utc)
    start=datetime.fromisoformat(service['service_date']+'T'+(service['start_time'] or '00:00')).replace(tzinfo=zone)
    if slot:
        row=db.execute('SELECT starts_at FROM animation_slots WHERE slot_uuid=?',(slot,)).fetchone()
        if row:start=datetime.fromisoformat(row[0]).astimezone(zone)
    opened=datetime.fromisoformat(service['signup_open_at'].replace('Z','+00:00')) if service.get('signup_open_at') else None
    if opened and not opened.tzinfo:opened=opened.replace(tzinfo=zone)
    capacity=int(service['capacity']);occupied=booking_capacity_used(db,service['service_id'],slot)
    count=waiting(db,service['service_id'],slot,environment);maximum=limit(db,service)
    available=max(0,capacity-occupied)
    if not service['enabled']:state='unpublished'
    elif opened and current<opened:state='not_open'
    elif current>=start-timedelta(minutes=service['close_minutes']):state='closed'
    elif available:state='available'
    elif not service['waitlist_enabled']:state='full'
    elif maximum is not None and count>=maximum:state='waiting_full'
    else:state='waiting'
    return dict(state=state,available=available,confirmed=occupied,capacity=capacity,
        waiting=count,waiting_limit=maximum,waiting_enabled=bool(service['waitlist_enabled']))
