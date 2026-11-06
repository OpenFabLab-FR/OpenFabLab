"""Private maintenance slots; independent of actual machine state and reminders."""
from datetime import date, datetime, time, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo
from family_model import setting, timestamp

TABLES = ('machine_maintenance_slots',)
FIELDS = ('slot_uuid','resource_uuid','starts_on','ends_on','starts_time','ends_time',
          'title','tentative','created_at','updated_at','cancelled_at','revision')


def validate(db):
    from v2153_schema import validate as previous
    previous(db)
    if tuple(r[1] for r in db.execute('PRAGMA table_info(machine_maintenance_slots)')) != FIELDS:
        raise RuntimeError('Schéma 28 incomplet.')


def ensure(db):
    from v2153_schema import validate as previous
    previous(db)
    db.execute("""CREATE TABLE machine_maintenance_slots (
        slot_uuid TEXT PRIMARY KEY,
        resource_uuid TEXT NOT NULL REFERENCES resources(resource_uuid) ON DELETE RESTRICT,
        starts_on TEXT NOT NULL, ends_on TEXT NOT NULL CHECK(ends_on>=starts_on),
        starts_time TEXT, ends_time TEXT,
        title TEXT NOT NULL CHECK(length(title) BETWEEN 1 AND 200),
        tentative INTEGER NOT NULL CHECK(tentative IN(0,1)),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, cancelled_at TEXT,
        revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1),
        CHECK((starts_time IS NULL)=(ends_time IS NULL)))""")
    db.execute('CREATE INDEX maintenance_slot_dates ON machine_maintenance_slots(starts_on,ends_on) WHERE cancelled_at IS NULL')
    db.execute('CREATE INDEX maintenance_slot_resource ON machine_maintenance_slots(resource_uuid,starts_on DESC)')
    validate(db)


def interval(row, zone, strict=False):
    first,last=(date.fromisoformat(row[name]) for name in ('starts_on','ends_on'))
    timed=bool(row['starts_time'])
    if not timed:
        return datetime.combine(first,time.min,zone),datetime.combine(last+timedelta(days=1),time.min,zone)
    a,b=(datetime.combine(day,time.fromisoformat(row[name]),zone)
         for day,name in ((first,'starts_time'),(last,'ends_time')))
    if strict:
        for stamp in (a,b):
            if (stamp.fold or stamp.utcoffset()!=stamp.replace(fold=1).utcoffset()
                    or stamp.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)!=stamp.replace(tzinfo=None)):
                raise ValueError('Choisissez un horaire non ambigu lors du changement d’heure.')
    return a,b


def save(db, key, form, role, cancel=False):
    from machine_maintenance import require
    require(role)
    if not db.in_transaction:raise RuntimeError('Transaction requise.')
    resource=db.execute('SELECT archived_at FROM resources WHERE resource_uuid=?',(key,)).fetchone()
    if resource is None or resource[0]:raise ValueError('Ressource archivée ou inconnue.')
    identifier=form.get('identifier')
    prior=db.execute('SELECT * FROM machine_maintenance_slots WHERE resource_uuid=? AND slot_uuid=?',(key,identifier)).fetchone() if identifier else None
    if (identifier or cancel) and (not prior or prior['cancelled_at'] or str(prior['revision'])!=form.get('revision')):
        raise ValueError('Ce créneau a changé. Rechargez la page.')
    now=timestamp()
    if cancel:
        db.execute('UPDATE machine_maintenance_slots SET cancelled_at=?,updated_at=?,revision=revision+1 WHERE slot_uuid=?',(now,now,identifier))
        return identifier
    title=(form.get('title') or '').strip()
    if not 1<=len(title)<=200:raise ValueError('Indiquez le titre de la maintenance (200 caractères maximum).')
    try:
        first,last=(date.fromisoformat(form.get(name,'')) for name in ('starts_on','ends_on'))
        start,end=(form.get(name) or None for name in ('starts_time','ends_time'))
        if bool(start)!=bool(end):raise ValueError
        if start:
            if any(len(value)!=5 or value[2]!=':' for value in (start,end)):raise ValueError
            start,end=(time.fromisoformat(value).isoformat(timespec='minutes') for value in (start,end))
        if first>last or (last-first).days>366 or last==date.max:raise ValueError
    except (ValueError,TypeError):
        raise ValueError('Indiquez deux dates dans l’ordre (366 jours maximum) et, si nécessaire, les deux heures.') from None
    value=dict(starts_on=str(first),ends_on=str(last),starts_time=start,ends_time=end)
    a,b=interval(value,ZoneInfo(setting(db,'structure_timezone','Europe/Paris')),strict=True)
    if a.astimezone(timezone.utc)>=b.astimezone(timezone.utc):raise ValueError('La fin doit être postérieure au début.')
    identifier=identifier or str(uuid4())
    db.execute("""INSERT INTO machine_maintenance_slots VALUES(?,?,?,?,?,?,?,?,?,?,NULL,1)
        ON CONFLICT(slot_uuid) DO UPDATE SET starts_on=excluded.starts_on,ends_on=excluded.ends_on,
        starts_time=excluded.starts_time,ends_time=excluded.ends_time,title=excluded.title,tentative=excluded.tentative,
        updated_at=excluded.updated_at,revision=machine_maintenance_slots.revision+1""",
        (identifier,key,str(first),str(last),start,end,title,int(form.get('tentative')=='1'),now,now))
    return identifier


def visible(db,start,end):
    return db.execute("""SELECT s.*,r.name FROM machine_maintenance_slots s JOIN resources r USING(resource_uuid)
        WHERE s.cancelled_at IS NULL AND s.starts_on<? AND s.ends_on>=?
        ORDER BY s.starts_on,s.starts_time,s.slot_uuid""",(str(end),str(start))).fetchall()
