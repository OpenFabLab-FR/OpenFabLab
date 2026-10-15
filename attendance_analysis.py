"""Read-only, bounded attendance analysis; no new personal history or export.

Visits count recorded arrivals in the selected interval. Durations are clipped
to that interval and use closed sessions only. Categories are session snapshots.
"""
import base64
import calendar
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from participant_search import normalized
from family_model import setting

UTC = timezone.utc
WEEKDAYS = ('Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche')
STATUS = {'confirmed':'Confirmée', 'waitlisted':'Liste d’attente', 'offer_pending':'Place proposée',
          'cancelled':'Annulée', 'declined':'Refusée', 'expired':'Proposition expirée',
          'present':'Présence renseignée', 'absent':'Absence renseignée', 'review':'À vérifier'}


def instant(value):
    result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return (result if result.tzinfo else result.replace(tzinfo=UTC)).astimezone(UTC)


def zone(db):
    return ZoneInfo(setting(db, 'structure_timezone', 'Europe/Paris'))


def scope(db, values):
    mode = values.get('mode', 'user')
    if mode == 'user':
        try:
            user = int(values.get('user_id', '0'))
        except (ValueError, TypeError):
            raise ValueError('Sélectionnez un usager.') from None
        row = db.execute('SELECT id,first_name,last_name,public_id FROM users WHERE id=?', (user,)).fetchone()
        if not row:
            raise ValueError('Sélectionnez un compte encore présent dans le répertoire.')
        return 'user_id=?', [user], dict(mode=mode, user_id=user, label=row['first_name']+' '+row['last_name'])
    if mode == 'category':
        key = values.get('category', '')
        row = db.execute('SELECT name FROM user_categories WHERE category_key=?', (key,)).fetchone()
        if not row:
            raise ValueError('Sélectionnez une catégorie existante.')
        return 'statistical_category=?', [key], dict(mode=mode, category=key, label=row['name'])
    if mode == 'all':
        return '1=1', [], dict(mode=mode, label='Ensemble des usagers')
    raise ValueError('Mode d’analyse invalide.')


def period(db, values, clause, parameters, now):
    local = now.astimezone(zone(db))
    today = local.date()
    choice = values.get('period', '30d')
    end = now
    if choice == '30d':
        start_day = today-timedelta(days=29)
    elif choice in ('3m', '12m'):
        months = 3 if choice == '3m' else 12
        number = today.year*12+today.month-1-months
        year, month = divmod(number, 12)
        start_day = date(year, month+1, min(today.day, calendar.monthrange(year, month+1)[1]))
    elif choice == 'all':
        row = db.execute('SELECT check_in FROM sessions WHERE '+clause+' ORDER BY julianday(check_in) LIMIT 1', parameters).fetchone()
        start_day = instant(row[0]).astimezone(zone(db)).date() if row else today
    elif choice == 'custom':
        try:
            start_day = date.fromisoformat(values.get('start', ''))
            last_day = date.fromisoformat(values.get('end', ''))
            if not date(1900, 1, 1) <= start_day <= last_day <= today:
                raise ValueError
            end = min(now, datetime.combine(last_day+timedelta(days=1), datetime.min.time(), zone(db)).astimezone(UTC))
        except (ValueError, TypeError):
            raise ValueError('Choisissez une période passée ou en cours, avec un début antérieur à la fin.') from None
    else:
        raise ValueError('Période invalide.')
    start = datetime.combine(start_day, datetime.min.time(), zone(db)).astimezone(UTC)
    return start, end


def identity(row):
    # A missing historical key is not a new invented anonymous identity.
    return row['statistical_user_key'] or ('user:'+str(row['user_id']) if row['user_id'] is not None else None)


def sessions(db, clause, parameters, start, end):
    return db.execute('''SELECT id,user_id,check_in,check_out,entry_method,exit_method,
        statistical_user_key,statistical_category FROM sessions WHERE '''+clause+'''
        AND julianday(check_in)<julianday(?)
        AND (julianday(check_in)>=julianday(?) OR julianday(check_out)>julianday(?))
        ORDER BY julianday(check_in),id''', [*parameters, end.isoformat(), start.isoformat(), start.isoformat()])


def totals(db, clause, parameters, start, end, tz, charts=True, observed_at=None):
    people = Counter()
    weekdays = [0]*7
    hourly = [0.0]*24
    heat = [[0.0]*24 for _ in range(7)]
    evolution = defaultdict(lambda: dict(visits=0, seconds=0.0, people=set()))
    visits = completed = opened = invalid = 0
    seconds = 0.0
    last = None
    bucket_kind = 'day' if (end-start).days <= 90 else 'month'
    def bucket(value):
        return value.astimezone(tz).strftime('%Y-%m-%d' if bucket_kind == 'day' else '%Y-%m')
    for row in sessions(db, clause, parameters, start, end):
        try:
            arrival = instant(row['check_in'])
            departure = instant(row['check_out']) if row['check_out'] else None
        except (ValueError, TypeError):
            invalid += 1
            continue
        key = identity(row)
        if start <= arrival < end:
            visits += 1
            last = max(last or arrival, arrival)
            if key:
                people[key] += 1
            weekdays[arrival.astimezone(tz).weekday()] += 1
            entry = evolution[bucket(arrival)]
            entry['visits'] += 1
            if key:
                entry['people'].add(key)
            if not departure:
                opened += 1
            elif departure >= arrival:
                completed += 1
        if not departure:
            continue
        if departure < arrival or departure > (observed_at or end):
            invalid += 1
            continue
        cursor, finish = max(arrival, start), min(departure, end)
        seconds += max(0, (finish-cursor).total_seconds())
        if not charts:
            continue
        # UTC quarter boundaries handle modern IANA half/quarter-hour offsets
        # and both occurrences of a repeated local hour at winter DST.
        while cursor < finish:
            boundary = datetime.fromtimestamp((int(cursor.timestamp())//900+1)*900, UTC)
            stop = min(finish, boundary)
            duration = (stop-cursor).total_seconds()
            local = cursor.astimezone(tz)
            hourly[local.hour] += duration
            heat[local.weekday()][local.hour] += duration
            evolution[bucket(cursor)]['seconds'] += duration
            cursor = stop
    regular = sum(count >= 2 for count in people.values())
    # Mean uses visits with a recorded departure; boundary-overlapping sessions
    # contribute to time but not the visit denominator or visit mean.
    mean_seconds = db.execute('''SELECT AVG(MAX(0,(MIN(julianday(check_out),julianday(?))-
        MAX(julianday(check_in),julianday(?)))*86400)) FROM sessions WHERE '''+clause+'''
        AND julianday(check_in)>=julianday(?) AND julianday(check_in)<julianday(?)
        AND check_out IS NOT NULL AND julianday(check_out)>=julianday(check_in)
        AND julianday(check_out)<=julianday(?)''',
        [end.isoformat(), start.isoformat(), *parameters, start.isoformat(), end.isoformat(),(observed_at or end).isoformat()]).fetchone()[0]
    return dict(visits=visits, seconds=round(seconds), mean_seconds=round(mean_seconds or 0),
        distinct=len(people), regular=regular, regular_percent=round(100*regular/len(people), 1) if people else None,
        completed=completed, open=opened, invalid=invalid, last=last.astimezone(tz).isoformat() if last else None,
        weekdays=weekdays, hourly=[round(v) for v in hourly], heat=[[round(v) for v in day] for day in heat],
        evolution=[dict(period=key,visits=entry['visits'],seconds=round(entry['seconds']),distinct=len(entry['people']))
                   for key,entry in sorted(evolution.items())], bucket=bucket_kind)


def cohorts(db, start, end, now, category=None):
    # Determine first RECORDED visit globally, not first in the filter and not
    # account creation. No name/contact lookup or reconstructed deleted account.
    key_sql="COALESCE(NULLIF(statistical_user_key,''),CASE WHEN user_id IS NOT NULL THEN 'user:'||user_id END)"
    # SQL groups the retained history; only cohort aggregates reach Python.
    # The earliest row supplies its own historical category, even after change.
    query = '''WITH visits AS (SELECT '''+key_sql+''' AS person,julianday(check_in) AS t,
        statistical_category AS category,ROW_NUMBER() OVER(PARTITION BY '''+key_sql+'''
        ORDER BY julianday(check_in),id) AS position FROM sessions
        WHERE julianday(check_in)<julianday(?) AND '''+key_sql+''' IS NOT NULL),
        firsts AS (SELECT person,t FROM visits WHERE position=1
        AND t>=julianday(?) AND t<julianday(?) '''+('AND category=?' if category else '')+'''),
        counts AS (SELECT f.person,f.t,COUNT(v.person) AS returns FROM firsts f
        LEFT JOIN visits v ON v.person=f.person AND v.t>f.t AND v.t<=f.t+?
        GROUP BY f.person,f.t)
        SELECT SUM(t+?<=julianday(?)),SUM(t+?>julianday(?)),
        SUM(t+?<=julianday(?) AND returns>=1),SUM(t+?<=julianday(?) AND returns>=3) FROM counts'''
    results=[]
    for horizon in (30,90):
        params=[now.isoformat(),start.isoformat(),end.isoformat(),*([category] if category else []),horizon]
        params.extend([horizon,now.isoformat()]*4)
        eligible,immature,returned,repeated=[value or 0 for value in db.execute(query,params).fetchone()]
        results.append(dict(days=horizon, eligible=eligible, immature=immature,
            returned=returned if eligible >= 3 else None, repeated=repeated if eligible >= 3 else None))
    return results


def history(db, clause, parameters, start, end, tz, cursor=None):
    args = [*parameters, start.isoformat(), end.isoformat()]
    extra = ''
    if cursor:
        try:
            value = json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
            if set(value) != {'t','id'} or type(value['id']) is not int or value['id'] < 1:
                raise ValueError
            instant(value['t'])
        except Exception:
            raise ValueError('Pagination invalide.') from None
        extra = ' AND (julianday(check_in)<julianday(?) OR (julianday(check_in)=julianday(?) AND id<?))'
        args.extend([value['t'],value['t'],value['id']])
    rows = db.execute('''SELECT id,check_in,check_out,entry_method FROM sessions WHERE '''+clause+'''
        AND julianday(check_in)>=julianday(?) AND julianday(check_in)<julianday(?)'''+extra+'''
        ORDER BY julianday(check_in) DESC,id DESC LIMIT 11''', args).fetchall()
    data = []
    for row in rows[:10]:
        arrival = instant(row['check_in'])
        departure = instant(row['check_out']) if row['check_out'] else None
        data.append(dict(arrival=arrival.astimezone(tz).isoformat(),departure=departure.astimezone(tz).isoformat() if departure else None,
            seconds=max(0,round((departure-arrival).total_seconds())) if departure else None,
            context=row['entry_method']))
    next_cursor = None
    if len(rows)>10:
        last = rows[9]
        next_cursor = base64.urlsafe_b64encode(json.dumps(dict(t=last['check_in'],id=last['id']),separators=(',',':')).encode()).decode().rstrip('=')
    return dict(passages=data,cursor=next_cursor)


def animations(db, info, start, end, now, tz):
    # Only stored reservation presence, never joined to attendance times.
    if info['mode'] == 'user':
        clause, params = 'b.user_id=?', [info['user_id']]
    elif info['mode'] == 'category':
        clause, params = 'u.category=?', [info['category']]
    else:
        clause, params = '1=1', []
    rows = db.execute('''SELECT b.service_id,b.status,b.is_present,s.title,s.service_date,
        s.start_time,s.end_time,sl.starts_at,sl.ends_at FROM animation_bookings b
        JOIN fablab_services s ON s.id=b.service_id LEFT JOIN users u ON u.id=b.user_id
        LEFT JOIN animation_slots sl ON sl.slot_uuid=b.slot_uuid
        WHERE b.environment='production' AND '''+clause+'''
        AND s.service_date>=? AND s.service_date<=? ORDER BY s.service_date,s.start_time''',
        [*params,start.astimezone(tz).date().isoformat(),
         max(end,now+timedelta(days=366)).astimezone(tz).date().isoformat()])
    past, future, collective = [], [], Counter()
    present = 0
    for row in rows:
        begin = instant(row['starts_at']) if row['starts_at'] else datetime.fromisoformat(row['service_date']+'T'+(row['start_time'] or '00:00')).replace(tzinfo=tz).astimezone(UTC)
        if start <= begin < end and row['is_present'] == 1:
            present += 1
            collective[(row['service_id'],row['title'])] += 1
        if info['mode'] != 'user':
            continue
        entry = dict(title=row['title'],date=begin.astimezone(tz).date().isoformat(),
            hours=(row['start_time'] or '')+'–'+(row['end_time'] or ''),
            status=STATUS.get(row['status'],'Autre état enregistré'),presence='Présence renseignée' if row['is_present']==1
            else ('Absence renseignée' if row['status']=='absent' else 'Présence non renseignée'),places=1)
        if begin >= now and row['status'] in ('confirmed','waitlisted','offer_pending'):
            future.append(entry)
        elif start <= begin < end and begin < now:
            past.append(entry)
    return dict(present=present,upcoming=future[:50],past=past[-50:][::-1],
        aggregate=[dict(title=title,count=count) for (_,title),count in collective.most_common(10)],
        category_basis='Catégorie actuelle des comptes pour les animations (pas d’instantané de catégorie dans les réservations).')


def analyse(db, values, now=None):
    now = now or datetime.now(UTC)
    clause, parameters, info = scope(db, values)
    start, end = period(db, values, clause, parameters, now)
    tz = zone(db)
    current = totals(db, clause, parameters, start, end, tz,observed_at=now)
    previous_start = start-(end-start)
    previous = totals(db, clause, parameters, previous_start, start, tz, charts=False,observed_at=now)
    comparison = {}
    for field in ('visits','seconds','distinct'):
        before, after = previous[field], current[field]
        comparison[field] = dict(previous=before,current=after,delta=after-before,
            percent=round(100*(after-before)/before,1) if before else None)
    small = info['mode']!='user' and current['distinct']<3
    if info['mode']!='user':
        current['last']=None  # No individual timing in a collective response.
    if small:
        current.update(weekdays=[],hourly=[],heat=[],evolution=[])
    booking = animations(db, info, start, end, now, tz)
    if small:
        booking['aggregate'] = []
    return dict(scope=info,timezone=tz.key,start=start.astimezone(tz).isoformat(),end=end.astimezone(tz).isoformat(),
        previous_start=previous_start.astimezone(tz).isoformat(),metrics=current,comparison=comparison,
        cohorts=cohorts(db,start,end,now,info.get('category')) if info['mode']!='user' else [],
        small_collective=small,animations=booking,
        history=history(db,clause,parameters,start,end,tz) if info['mode']=='user' else None)


def register(application, a):
    from flask import Blueprint, abort, jsonify, render_template, request
    from evolution_routes import require_team
    from evolution_schema import categories
    bp = Blueprint('attendance_analysis', __name__)
    def guard():
        require_team()
        db = a.get_database()
        if not a.load_modules(db)['frequency']:
            abort(404)
        return db
    @bp.after_request
    def private(response):
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return response
    @bp.get('/admin/frequentation/usagers')
    def page():
        return render_template('attendance_analysis.html',analysis_categories=categories(guard(),True))
    @bp.get('/admin/frequentation/usagers/recherche')
    def search():
        db = guard()
        query = request.args.get('q','').strip()[:80]
        if not query:
            return jsonify(users=[],more=False)
        db.create_function('analysis_key',1,normalized,deterministic=True)
        pattern = '%'+normalized(query).replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
        rows = db.execute("""SELECT id,first_name,last_name,public_id FROM users WHERE
            analysis_key(first_name || ' ' || last_name) LIKE ? ESCAPE '\\' OR public_id LIKE ? ESCAPE '\\'
            ORDER BY analysis_key(first_name),id LIMIT 26""", (pattern,pattern)).fetchall()
        return jsonify(users=[dict(row) for row in rows[:25]],more=len(rows)>25)
    @bp.get('/admin/frequentation/usagers/donnees')
    def data():
        db = guard()
        try:
            if request.args.get('cursor'):
                clause, params, info = scope(db,request.args)
                if info['mode']!='user':
                    raise ValueError('Les passages détaillés sont réservés à la vue individuelle.')
                start, end = period(db,request.args,clause,params,datetime.now(UTC))
                return jsonify(history(db,clause,params,start,end,zone(db),request.args['cursor']))
            return jsonify(analyse(db,request.args))
        except ValueError as error:
            return jsonify(message=str(error)),400
    application.register_blueprint(bp)
