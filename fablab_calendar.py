"""Local calendar projection, no cloud/library, no business writes."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from flask import abort, url_for, session
import re

COLORS = {'openlab':'#447e68','animation':'#16849c','reservation':'#94703a','rental':'#7657a5','training':'#a65378'}


def display_window(db, a):
    values = [a.read_setting(db, 'calendar_display_'+key, default)
              for key, default in [('start','09:00'),('end','19:00')]]
    if not all(re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', v) for v in values) or values[1] <= values[0]:
        values = ['09:00','19:00']
    return [int(v[:2])*60+int(v[3:]) for v in values]


def position_overlaps(events):
    """Greedy interval coloring with group widths; touching events separate."""
    ordered=sorted(events,key=lambda e:(e['start_minute'],e['end_minute']))
    group=[];end=-1
    def assign(items):
        lanes=[]
        for item in items:
            lane=next((i for i,t in enumerate(lanes) if t<=item['start_minute']),len(lanes))
            if lane==len(lanes):lanes.append(item['end_minute'])
            else:lanes[lane]=item['end_minute']
            item['lane']=lane
        for item in items:
            item['width']=round(100/len(lanes),4)
            item['left']=round(100*item['lane']/len(lanes),4)
    for item in ordered:
        if group and item['start_minute']>=end:
            assign(group);group=[];end=-1
        group.append(item);end=max(end,item['end_minute'])
    if group:assign(group)
    return ordered


def calendar_view(db,args,a):
    view=args.get('view','week')
    if view not in {'week','month'}:abort(400)
    zone=ZoneInfo(a.read_setting(db,'structure_timezone','Europe/Paris'))
    today=datetime.now(zone).date()
    modules = a.load_modules(db)
    current = datetime.now(zone)
    try:chosen=date.fromisoformat(args.get('date') or today.isoformat())
    except ValueError:abort(400)
    if view=='week':
        start=chosen-timedelta(days=chosen.weekday());end=start+timedelta(days=7)
        previous=start-timedelta(days=7);following=end
    else:
        month=chosen.replace(day=1)
        next_month=(month+timedelta(days=32)).replace(day=1)
        start=month-timedelta(days=month.weekday())
        end=next_month+timedelta(days=(7-next_month.weekday())%7)
        previous=month-timedelta(days=1);following=next_month
    daily=defaultdict(list)
    def add(title,kind,key,day,begin=None,finish=None,link=None,color=None):
        if not start<=day<end:return
        item={'title':title,'kind':kind,'key':str(key),'day':day,'url':link or '#',
              'color':color or COLORS[kind], 'all_day':not begin,'time':''}
        if begin:
            item.update(start_minute=begin.hour*60+begin.minute,end_minute=finish.hour*60+finish.minute)
            if item['end_minute']<=item['start_minute']:item['end_minute']=1440
            item.update(top=round(item['start_minute']/1440*100,4),height=round(max(20,item['end_minute']-item['start_minute'])/1440*100,4),
                        time=begin.strftime('%H:%M')+'–'+finish.strftime('%H:%M'))
        daily[day].append(item)
    def add_span(title,kind,key,begin,finish,link,color=None):
        begin,finish=begin.astimezone(zone),finish.astimezone(zone)
        day=max(start,begin.date())
        while day<end and day<=finish.date():
            lo=max(begin,datetime.combine(day,datetime.min.time(),zone))
            hi=min(finish,datetime.combine(day+timedelta(days=1),datetime.min.time(),zone))
            if hi>lo:add(title,kind,key,day,lo,hi,link,color)
            day+=timedelta(days=1)
    if a.load_modules(db)['frequency']:
        schedule={i:row for i,row in enumerate(a.load_openlab_schedule(db))}
        day=start
        while day<end:
            row=schedule[day.weekday()]
            if row['active'] and row['start'] and row['end']:
                add('OpenLab','openlab',day,day,datetime.fromisoformat(str(day)+'T'+row['start']),
                    datetime.fromisoformat(str(day)+'T'+row['end']),url_for('admin_frequency_day',date=day.isoformat()))
                if datetime.fromisoformat(str(day)+'T'+row['start']).replace(tzinfo=zone) <= current:
                    # Same counters and statistical identities as the existing
                    # attendance page, scoped to the OpenLab interval.
                    attendance = a.load_day_attendance(db, day, row['start'], row['end'])
                    summary = attendance['summary']
                    daily[day][-1]['attendance'] = str(summary['unique_users'])+' usager'+('s' if summary['unique_users']!=1 else '')+' · '+str(summary['visitors'])+' visiteur'+('s' if summary['visitors']!=1 else '')
                    event = daily[day][-1]
                    event['action_label'] = 'Ouvrir la journée'
                    event['extra_details'] = []
                    if summary['peak_users']:
                        event['extra_details'].append('Pic simultané : '+str(summary['peak_users'])+' usager(s) à '+summary['peak_at'])
                    weather = summary['peak_weather']
                    if weather:
                        event['extra_details'].append('Météo enregistrée au pic : '+weather['description']+' · '+str(round(weather['temperature_c']))+' °C')
                    event['people'] = [{'name':item['identity'], 'category':item['row']['statistical_category'],
                        'state':str(item['duration_seconds']//60)+' min' if item['duration_seconds'] is not None else ''}
                        for item in attendance['sessions']]
            day+=timedelta(days=1)
    for service in db.execute('''SELECT s.*,b.rental_end_date FROM fablab_services s
        LEFT JOIN billing_records b ON b.service_id=s.id
        WHERE s.service_date<? AND COALESCE(NULLIF(b.rental_end_date,''),s.service_date)>=?
        AND NOT EXISTS(SELECT 1 FROM resource_bookings r WHERE r.service_id=s.id)''',(str(end),str(start))):
        kind=service['service_type']
        if kind!='animation' and not modules['billing']:continue
        link=url_for('admin_service_form',service_id=service['id'])
        if kind=='animation':
            link=url_for('admin_animation_bookings',service_id=service['id']) if a.load_modules(db)['public_reservations'] else url_for('admin_services')
        elif session.get('access_role')=='moderator':link=url_for('admin_services')
        if kind=='rental' and service['rental_end_date']:
            # A rental remains one business object; display its occupied days
            # even when its starting day is outside the visible period.
            day=max(start,date.fromisoformat(service['service_date']))
            last=date.fromisoformat(service['rental_end_date'])
            while day<end and day<=last:
                add(service['title'],kind,service['id'],day,link=link)
                day+=timedelta(days=1)
            continue
        if service['start_time'] and service['end_time']:
            begin=datetime.fromisoformat(service['service_date']+'T'+service['start_time'])
            finish=datetime.fromisoformat(service['service_date']+'T'+service['end_time'])
        else:begin=finish=None
        add(service['title'],kind,service['id'],date.fromisoformat(service['service_date']),begin,finish,link)
    lower=datetime.combine(start,datetime.min.time(),zone).astimezone(timezone.utc).isoformat()
    upper=datetime.combine(end,datetime.min.time(),zone).astimezone(timezone.utc).isoformat()
    for row in (db.execute("SELECT b.*,r.name,COALESCE(r.color,t.color) AS display_color FROM resource_bookings b JOIN resources r USING(resource_uuid) JOIN resource_types t USING(type_key) WHERE status IN('requested','confirmed','performed') AND b.starts_at<? AND b.ends_at>?",(upper,lower)) if modules['resources'] else []):
        add_span(row['name']+' · '+{'requested':'demande','confirmed':'confirmée','performed':'effectuée'}[row['status']],
                 'reservation',row['booking_uuid'],datetime.fromisoformat(row['starts_at']),datetime.fromisoformat(row['ends_at']),
                 url_for('evolution.resource_bookings')+'#reservation-'+row['booking_uuid'],row['display_color'])
    for row in (db.execute('SELECT g.*,a.name FROM user_authorizations g JOIN authorizations a USING(authorization_uuid) WHERE performed_on>=? AND performed_on<?',(str(start),str(end))) if modules['authorizations'] else []):
        add('Formation · '+row['name'],'training',row['grant_uuid'],date.fromisoformat(row['performed_on']),link=url_for('evolution.authorizations')+'#formation-'+row['grant_uuid'])
    configured_start, configured_end = display_window(db, a)
    timed = [event for events in daily.values() for event in events if not event['all_day']]
    # Extend this period only; never hide an exceptional early/late event or
    # change the configured window or any booking constraints.
    window_start = min([configured_start]+[e['start_minute']//60*60 for e in timed])
    window_end = max([configured_end]+[min(1440, (e['end_minute']+59)//60*60) for e in timed])
    window_duration = window_end-window_start
    for event in timed:
        event.update(top=round((event['start_minute']-window_start)/window_duration*100,4),
                     height=round((event['end_minute']-event['start_minute'])/window_duration*100,4))
    hours=[{'label':f'{minute//60:02d}:{minute%60:02d}', 'top':(minute-window_start)/window_duration*100}
           for minute in [window_start]+list(range((window_start//60+1)*60,window_end,60))]
    days=[];day=start
    while day<end:
        events=daily[day]
        # Presentation metadata only; interval calculation and counters above
        # remain unchanged. This route is restricted to the existing team roles.
        for event in events:
            detail = [event['day'].strftime('%d/%m/%Y'), event['time'] or 'Journée entière']
            event.setdefault('people', [])
            if event.get('attendance'):
                detail.append(event['attendance'])
            detail.extend(event.get('extra_details', []))
            if event['kind'] == 'reservation':
                row = db.execute('SELECT b.status,u.first_name,u.last_name FROM resource_bookings b LEFT JOIN users u ON u.id=b.user_id WHERE booking_uuid=?',(event['key'],)).fetchone()
                if row:
                    from resource_booking import STATUS_LABELS
                    detail.extend([((row['first_name'] or 'Usager supprimé') + ' ' + (row['last_name'] or '')).strip(), STATUS_LABELS[row['status']]])
            elif event['kind'] == 'training':
                row = db.execute('SELECT u.first_name,u.last_name FROM user_authorizations g LEFT JOIN users u ON u.id=g.user_id WHERE grant_uuid=?',(event['key'],)).fetchone()
                if row:
                    detail.append(((row['first_name'] or 'Usager supprimé') + ' ' + (row['last_name'] or '')).strip())
            elif event['kind'] == 'animation':
                config = db.execute('SELECT * FROM animation_reservation_config WHERE service_id=?',(event['key'],)).fetchone()
                if config and modules['public_reservations']:
                    from reservations_sync import booking_counts, booking_reservation_status
                    bookings = db.execute('SELECT b.*,u.category FROM animation_bookings b LEFT JOIN users u ON u.id=b.user_id WHERE service_id=? AND environment=? ORDER BY CASE b.status WHEN \'waitlisted\' THEN 1 ELSE 0 END,b.created_at',(event['key'],config['environment'])).fetchall()
                    counts = booking_counts(bookings)
                    detail.append(str(sum(counts[s] for s in ('confirmed','offer_pending')))+' inscrit(s) / '+str(config['capacity'])+' places')
                    if counts['waitlisted']:
                        detail.append(str(counts['waitlisted'])+' en liste d’attente')
                    labels = {'confirmed':'Confirmée','waitlisted':'Liste d’attente','offer_pending':'Place proposée','cancelled':'Annulée','expired':'Expirée'}
                    event['people'] = [{'name':(b['first_name']+' '+b['last_name']).strip(), 'category':b['category'] or '',
                        'state':labels.get(booking_reservation_status(b),'En cours')}
                        for b in bookings if b['status'] not in ('cancelled','expired')]
                row = db.execute('SELECT actual_participants,expected_participants FROM fablab_services WHERE id=?',(event['key'],)).fetchone()
                if row:
                    if row['actual_participants'] is not None:
                        detail.append(str(row['actual_participants']) + ' participant(s) présent(s)')
                    if row['expected_participants'] is not None:
                        detail.append('Capacité : ' + str(row['expected_participants']) + ' place(s)')
            event['details'] = '\n'.join(detail)
            for person in event['people']:
                row = db.execute('SELECT name FROM user_categories WHERE category_key=?',(person['category'],)).fetchone()
                person['category_label'] = row['name'] if row else person['category']
        days.append({'date':day,'today':day==today,'timed':position_overlaps([e for e in events if not e['all_day']]),'all_day':[e for e in events if e['all_day']],'events':events})
        day+=timedelta(days=1)
    return {'view':view,'chosen':chosen,'days':days,'previous':previous,'following':following,'today':today,'hours':hours,
            'has_all_day':any(day['all_day'] for day in days),
            'timeline_height':max(180, window_duration), 'window_extended':(window_start,window_end)!=(configured_start,configured_end),
            'visible_start':f'{window_start//60:02d}:{window_start%60:02d}', 'visible_end':f'{window_end//60:02d}:{window_end%60:02d}',
            'heading':('Semaine du '+start.strftime('%d/%m/%Y')) if view=='week' else chosen.strftime('%m/%Y')}
