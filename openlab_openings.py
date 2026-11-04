"""Announced openings, never a replacement for measured attendance statistics."""
from datetime import date,datetime,time,timedelta
from zoneinfo import ZoneInfo
from family_model import setting
from evolution_schema import audit

def save_exception(db,values,role):
    if role not in ('admin','moderator'):raise PermissionError('Action réservée à l’équipe.')
    day=date.fromisoformat(str(values.get('day',''))).isoformat()
    kind=values.get('kind');title=str(values.get('public_title','')).strip()
    if kind not in ('closed','extra','hours') or len(title)>180:raise ValueError('Exception d’ouverture invalide.')
    start=end=None
    if kind!='closed':
        start=time.fromisoformat(str(values.get('starts_at',''))).strftime('%H:%M')
        end=time.fromisoformat(str(values.get('ends_at',''))).strftime('%H:%M')
        if end<=start:raise ValueError('La fin doit être après le début de l’ouverture.')
        # Reject nonexistent wall times at the daylight-saving spring transition.
        zone=ZoneInfo(setting(db,'structure_timezone','Europe/Paris'))
        from datetime import timezone
        for clock in (start,end):
            wall=datetime.fromisoformat(day+'T'+clock)
            if wall.replace(tzinfo=zone).astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)!=wall:
                raise ValueError('Cette heure n’existe pas dans le fuseau horaire de la structure.')
    db.execute('''INSERT INTO openlab_exceptions VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(day) DO UPDATE SET
        kind=excluded.kind,starts_at=excluded.starts_at,ends_at=excluded.ends_at,public_title=excluded.public_title,
        publish=excluded.publish,actor=excluded.actor,updated_at=excluded.updated_at''',
        (day,kind,start,end,title,int(values.get('publish') in (True,1,'1')),role,datetime.now().astimezone().isoformat()))
    audit(db,'openlab_exception',day,'saved',role,{'kind':kind})

def remove_exception(db,day,role):
    if role not in ('admin','moderator'):raise PermissionError('Action réservée à l’équipe.')
    day=date.fromisoformat(day).isoformat()
    db.execute('DELETE FROM openlab_exceptions WHERE day=?',(day,))
    audit(db,'openlab_exception',day,'removed',role)

def day_schedule(db,day,schedule):
    row=dict(schedule[day.weekday()]);exception=db.execute('SELECT * FROM openlab_exceptions WHERE day=?',(day.isoformat(),)).fetchone()
    row.update(title='OpenLab',exception=False,public=setting(db,'openlab_public_enabled','0')=='1')
    if exception:
        row.update(active=exception['kind']!='closed',start=exception['starts_at'],end=exception['ends_at'],
            title=exception['public_title'] or 'OpenLab',exception=True,public=bool(exception['publish']) and row['public'])
    return row

def public_openings(db,schedule,start,end):
    result=[];zone=ZoneInfo(setting(db,'structure_timezone','Europe/Paris'));day=start
    while day<end:
        row=day_schedule(db,day,schedule)
        if row['public'] and row['active'] and row['start'] and row['end']:
            begin=datetime.fromisoformat(day.isoformat()+'T'+row['start']).replace(tzinfo=zone)
            finish=datetime.fromisoformat(day.isoformat()+'T'+row['end']).replace(tzinfo=zone)
            result.append(dict(id='openlab-'+day.isoformat(),kind='openlab',title=row['title'],start=begin.isoformat(),end=finish.isoformat()))
        day+=timedelta(days=1)
    return result


def attendance_average(db,schedule,weekday,starts,ends,now):
    """Opt-in aggregate of *observed* comparable sessions, never presumed openings.

    Last 12 calendar months, excluding today; same weekday/current hours; closed/changed exceptional
    hours excluded. Only completed identified arrivals within that time window,
    deduplicated per day, and anonymous arrivals. Days without measured activity
    are unknown, not zero. No row-level data or sample sizes leave this function.
    """
    if setting(db,'openlab_public_average_enabled','0')!='1':return None
    from collections import defaultdict
    zone=ZoneInfo(setting(db,'structure_timezone','Europe/Paris'));today=now.astimezone(zone).date()
    # Calendar anniversary, including leap-year boundaries (not 52 weeks).
    try:first=today.replace(year=today.year-1)
    except ValueError:first=today.replace(year=today.year-1,day=28)
    observed=defaultdict(lambda:dict(users=set(),visitors=0))
    def moment(value):
        try:
            result=datetime.fromisoformat(value.replace('Z','+00:00'))
            return result.astimezone(zone) if result.tzinfo else None
        except (ValueError,TypeError):return None
    def comparable(instant):
        if not instant or not first<=instant.date()<today or instant.weekday()!=weekday:return False
        row=day_schedule(db,instant.date(),schedule)
        return row['active'] and row['start']==starts and row['end']==ends and starts<=instant.strftime('%H:%M')<ends
    cutoff=datetime.combine(first,time.min,zone).isoformat()
    for row in db.execute('SELECT user_id,statistical_user_key,check_in,check_out FROM sessions WHERE julianday(check_in)>=julianday(?) AND check_out IS NOT NULL',(cutoff,)):
        arrival=moment(row['check_in']);departure=moment(row['check_out'])
        identity=row['statistical_user_key'] or (str(row['user_id']) if row['user_id'] is not None else None)
        if comparable(arrival) and departure and departure<=now and departure>=arrival and identity:
            observed[arrival.date()]['users'].add(identity)
    for row in db.execute('SELECT created_at FROM visitors WHERE julianday(created_at)>=julianday(?)',(cutoff,)):
        arrival=moment(row['created_at'])
        if comparable(arrival):observed[arrival.date()]['visitors']+=1
    days=list(observed.values())
    if len(days)<6:return None
    identities=set().union(*(d['users'] for d in days))
    total=sum(len(d['users']) for d in days);visitors=sum(d['visitors'] for d in days)
    if len(identities)<5 or total<5*len(days) or 0<visitors<5:return None
    return dict(users=round(total/len(days)),visitors=round(visitors/len(days)),
                since=first.isoformat(),until=(today-timedelta(days=1)).isoformat(),method='observed_same_weekday_hours_12m_v1')
