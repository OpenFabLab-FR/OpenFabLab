"""Local calendar projection, no cloud/library, no business writes."""
from i18n import native as __ui_native__
from i18n import t as __ui_text__
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from flask import abort, url_for, session
import re

COLORS = {'openlab':'#447e68','animation':'#16849c','reservation':'#94703a','rental':'#7657a5','training':'#a65378','maintenance':'#8b6540','billing':'#576993'}

def show_maintenance(args):
    values=args.getlist('maintenance') if hasattr(args,'getlist') else [args.get('maintenance','1')]
    return (values[-1] if values else '1')!='0'


def set_visibility(db,kind,key,day,hidden):
    if kind not in COLORS or not isinstance(key,str) or len(key)>120:
        raise ValueError(__ui_text__('Événement inconnu.'))
    date.fromisoformat(day)
    exists=(kind=='openlab' and key==day) or (kind in ('animation','rental','reservation') and db.execute('SELECT 1 FROM fablab_services WHERE id=? AND service_type=?',(key,kind)).fetchone()) or (kind=='reservation' and db.execute('SELECT 1 FROM resource_bookings WHERE booking_uuid=?',(key,)).fetchone()) or (kind=='training' and db.execute('SELECT 1 FROM user_authorizations WHERE grant_uuid=?',(key,)).fetchone())
    if not exists:
        raise ValueError(__ui_text__('Événement inconnu.'))
    db.execute('INSERT INTO calendar_visibility VALUES(?,?,?,?,?) ON CONFLICT(event_kind,event_key,occurrence_date) DO UPDATE SET hidden=excluded.hidden,updated_at=excluded.updated_at',
               (kind,key,day,int(hidden),datetime.now(timezone.utc).isoformat()))


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

def week_bands(days,flag):
    """One bar per contiguous visible run; retain day-specific notes/visibility."""
    by_booking=defaultdict(list)
    for index,day in enumerate(days):
        for event in day['all_day']:
            if event.get(flag):
                by_booking[event['kind'],event['key']].append((index,event))
    runs=[]
    for occurrences in by_booking.values():
        run=None
        for index,event in occurrences:
            if (run and run['end']==index and run['event']['hidden']==event['hidden']
                and not run['event']['internal_note'] and not event['internal_note']):
                run['end']=index+1
            else:
                run=dict(start=index,end=index+1,event=event)
                runs.append(run)
    lanes=[]
    for run in sorted(runs,key=lambda run:(run['start'],-run['end'],run['event']['key'])):
        lane=next((i for i,end in enumerate(lanes) if end<=run['start']),len(lanes))
        if lane==len(lanes):lanes.append(run['end'])
        else:lanes[lane]=run['end']
        run['lane']=lane
    return runs


def week_rentals(days):
    return week_bands(days,'rental_span')


def enrich_billing_event(db, event, modules, a):
    """Billing details are administrator-only, matching the dossier routes.

    Never serialize restricted content and then hide it in the browser.
    """
    role = session.get('access_role') or ('admin' if session.get('admin_authenticated') else None)
    if event['kind'] != 'reservation' or role != 'admin' or not modules['billing']:
        return []
    if event['key'].isdigit():
        row = db.execute('SELECT * FROM billing_records WHERE service_id=? ORDER BY id DESC LIMIT 1', (event['key'],)).fetchone()
    else:
        row = db.execute('SELECT r.* FROM resource_bookings b JOIN billing_records r ON r.id=b.billing_record_id WHERE b.booking_uuid=?', (event['key'],)).fetchone()
    if not row:
        return []
    event['url'] = url_for('admin_billing_detail', record_id=row['id'])
    event['action_label'] = __ui_text__('Ouvrir le dossier')
    event['detail_title'] = row['title'] or event['title']
    event['description'] = row['description'] or ''
    return [__ui_text__('Client : ') + (row['client_structure'] or row['client_contact']),
            __ui_text__('Dossier : ') + row['quote_number'], __ui_text__('Statut : ') + a.billing_status_label(dict(row))]


def calendar_view(db,args,a,current=None):
    view=args.get('view','week')
    if view not in {'week','month'}:abort(400)
    zone=ZoneInfo(a.read_setting(db,'structure_timezone',__ui_text__('Europe/Paris')))
    current=(current or datetime.now(zone)).astimezone(zone)
    today=current.date()
    modules = a.load_modules(db)
    role=session.get('access_role') or ('admin' if session.get('admin_authenticated') else None)
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
    show_hidden=args.get('hidden')=='1'
    def add(title,kind,key,day,begin=None,finish=None,link=None,color=None):
        if not start<=day<end:return
        item={'title':title,'kind':kind,'key':str(key),'day':day,'url':link or '#',
              'color':color or a.read_setting(db,'calendar_color_'+kind,COLORS[kind]), 'all_day':not begin,'time':'',
              'hidden':False,'automatic_hidden':False}
        override=db.execute('SELECT hidden FROM calendar_visibility WHERE event_kind=? AND event_key=? AND occurrence_date=?',(kind,str(key),day.isoformat())).fetchone()
        item['hidden']=bool(override and override['hidden'])
        if begin:
            item.update(start_minute=begin.hour*60+begin.minute,end_minute=finish.hour*60+finish.minute)
            clock='%H:%M'
            if finish.date()>begin.date():
                item['end_minute']=1440
            elif begin.utcoffset()!=finish.utcoffset() and item['end_minute']<=item['start_minute']:
                # A slot can finish at an earlier wall time in the repeated
                # autumn hour. Keep its real elapsed length and show both offsets.
                minutes=(finish.astimezone(timezone.utc)-begin.astimezone(timezone.utc)).total_seconds()/60
                item['end_minute']=min(1440,item['start_minute']+max(1,int(minutes)))
                clock='%H:%M %Z'
            elif item['end_minute']<=item['start_minute']:
                item['end_minute']=min(1440,item['start_minute']+1)
            item.update(top=round(item['start_minute']/1440*100,4),height=round(max(20,item['end_minute']-item['start_minute'])/1440*100,4),
                        time=begin.strftime(clock)+'–'+finish.strftime(clock))
        daily[day].append(item)
    def add_span(title,kind,key,begin,finish,link,color=None,*,flag='rental_span',all_day=False,meta=None):
        begin,finish=begin.astimezone(zone),finish.astimezone(zone)
        def instant(value):return value.astimezone(timezone.utc)
        multi_day = begin.date() != (finish-timedelta(microseconds=1)).date()
        day=max(start,begin.date())
        while day<end and day<=finish.date():
            lo=max(begin,datetime.combine(day,datetime.min.time(),zone),key=instant)
            hi=min(finish,datetime.combine(day+timedelta(days=1),datetime.min.time(),zone),key=instant)
            if instant(hi)>instant(lo):
                # Render references to the same booking in the upper band;
                # midnight crossings must not expand the hourly grid to 24h.
                add(title,kind,key,day,None if multi_day or all_day else lo,None if multi_day or all_day else hi,link,color)
                daily[day][-1].update(span_start=begin.isoformat(),span_end=finish.isoformat(),**{flag:multi_day})
                if multi_day:
                    daily[day][-1]['time']=(begin.strftime('%d/%m')+' – '+(finish-timedelta(days=1)).strftime('%d/%m')
                        if all_day else begin.strftime('%d/%m %H:%M')+' – '+finish.strftime('%d/%m %H:%M'))
                if meta:daily[day][-1].update(meta)
            day+=timedelta(days=1)
    def add_timed(title,kind,key,day,begin,finish,link):
        if begin and finish and finish<begin:
            # A real overnight event has one piece on each civil day.
            midnight=datetime.combine(day+timedelta(days=1),datetime.min.time(),zone)
            if start<=day<end:add(title,kind,key,day,begin,midnight,link)
            if start<=midnight.date()<end and finish.time()!=datetime.min.time():
                add(title,kind,key,midnight.date(),midnight,finish+timedelta(days=1),link)
            return
        add(title,kind,key,day,begin if begin and finish and finish>begin else None,
            finish if begin and finish and finish>begin else None,link)
    from admin_planning import billing_events,billing_confirmed,booking_time
    if modules['frequency']:
        schedule={i:row for i,row in enumerate(a.load_openlab_schedule(db))}
        day=start
        while day<end:
            from openlab_openings import day_schedule
            row=day_schedule(db,day,schedule)
            if row['exception'] and not row['active']:
                add(row['title'] if row['title']!=__ui_text__('OpenLab') else __ui_text__('Fermeture exceptionnelle OpenLab'),'openlab',day,day,link=url_for('v214.openings'),color='#777f86')
            if row['active'] and row['start'] and row['end']:
                begin=booking_time(str(day),row['start'],zone)
                finish=booking_time(str(day),row['end'],zone)
                add(row['title'],'openlab',day,day,begin if finish else None,finish,url_for('admin_frequency_day',date=day.isoformat()))
                if begin and finish and begin.astimezone(timezone.utc)<=current.astimezone(timezone.utc):
                    # Same counters and statistical identities as the existing
                    # attendance page, scoped to the OpenLab interval.
                    attendance = a.load_day_attendance(db, day, row['start'], row['end'])
                    summary = attendance['summary']
                    daily[day][-1]['attendance'] = str(summary['unique_users'])+__ui_text__(' usager')+('s' if summary['unique_users']!=1 else '')+' · '+str(summary['visitors'])+__ui_text__(' visiteur')+('s' if summary['visitors']!=1 else '')
                    event = daily[day][-1]
                    ended=finish.astimezone(timezone.utc)<current.astimezone(timezone.utc)
                    event['automatic_hidden']=bool(ended and summary['unique_users']==0 and summary['visitors']==0)
                    event['action_label'] = __ui_text__('Ouvrir la journée')
                    event['extra_details'] = []
                    if summary['peak_users']:
                        event['extra_details'].append(__ui_text__('Pic simultané : ')+str(summary['peak_users'])+__ui_text__(' usager(s) à ')+summary['peak_at'])
                    weather = summary['peak_weather']
                    if weather:
                        event['extra_details'].append(__ui_text__('Météo enregistrée au pic : ')+weather['description']+' · '+str(round(weather['temperature_c']))+__ui_text__(' °C'))
                    event['people'] = [{'name':item['identity'], 'category':item['row']['statistical_category'],
                        'state':str(item['duration_seconds']//60)+__ui_text__(' min') if item['duration_seconds'] is not None else ''}
                        for item in attendance['sessions']]
            day+=timedelta(days=1)
    for service in db.execute('''SELECT s.*,b.id AS billing_id,b.rental_end_date,r.name AS rental_name,b.handed_over_at,b.returned_at,
        b.quote_signed_at,b.quote_cancelled_at,b.invoice_number,b.activity_start_time,b.activity_end_time FROM fablab_services s
        LEFT JOIN billing_records b ON b.id=(SELECT MIN(f.id) FROM billing_records f WHERE f.service_id=s.id)
        LEFT JOIN resources r ON r.legacy_machine_key=b.rental_machine_key
        WHERE s.service_date<? AND COALESCE(NULLIF(b.rental_end_date,''),s.service_date)>=?
        AND NOT EXISTS(SELECT 1 FROM resource_bookings r WHERE r.service_id=s.id)''',(str(end),str(start-timedelta(days=1)))):
        kind=service['service_type']
        if kind=='animation' and not modules['activities']:continue
        if kind!='animation' and (not modules['billing'] or kind=='rental' and not modules['rentals']):continue
        link=url_for('admin_service_form',service_id=service['id'])
        if kind=='animation':
            link=url_for('admin_animation_bookings',service_id=service['id']) if a.load_modules(db)['public_reservations'] else url_for('admin_services')
        elif role!='admin':link=url_for('admin_services')
        elif service['billing_id']:link=url_for('admin_billing_detail',record_id=service['billing_id'])
        if kind=='rental' and service['rental_end_date']:
            # A rental remains one business object; display its occupied days
            # even when its starting day is outside the visible period.
            first=date.fromisoformat(service['service_date'])
            day=max(start,first)
            last=date.fromisoformat(service['rental_end_date'])
            title=__ui_text__('Location · {0}',service['rental_name'] or service['title'])
            begin=booking_time(str(first),service['start_time'] or service['activity_start_time'],zone)
            finish=booking_time(str(last),service['end_time'] or service['activity_end_time'],zone)
            if first==last and begin and finish and finish>begin:
                add_span(title,kind,service['id'],begin,finish,link)
                if first in daily and daily[first] and daily[first][-1]['key']==str(service['id']):
                    daily[first][-1].update(rental_meta=dict(service),tentative=not billing_confirmed(service))
                continue
            while day<end and day<=last:
                add(title,kind,service['id'],day,link=link)
                daily[day][-1].update(rental_span=last>first,rental_meta=dict(service),
                    tentative=not billing_confirmed(service) and not service['quote_cancelled_at'],
                    time=first.strftime('%d/%m/%Y')+' – '+last.strftime('%d/%m/%Y'))
                day+=timedelta(days=1)
            continue
        begin=booking_time(service['service_date'],service['start_time'] or service['activity_start_time'],zone)
        finish=booking_time(service['service_date'],service['end_time'] or service['activity_end_time'],zone)
        day=date.fromisoformat(service['service_date'])
        if not start<=day<end and not (begin and finish and finish<begin and day+timedelta(days=1)==start):continue
        add_timed(service['title'],kind,service['id'],day,begin,finish,link)
        event_days=[visible for visible in (day,day+timedelta(days=1)) if daily.get(visible) and daily[visible][-1]['key']==str(service['id']) and daily[visible][-1]['kind']==kind]
        if kind=='animation' and modules['public_reservations']:
            scheduled=db.execute('SELECT COUNT(*) FROM animation_slots WHERE service_id=? AND active=1',(service['id'],)).fetchone()[0]
            if scheduled:
                for visible in event_days:daily[visible][-1]['schedule_count']=scheduled
        if role=='admin' and kind!='animation' and service['billing_id'] and not service['quote_cancelled_at']:
            for visible in event_days:daily[visible][-1]['tentative']=not billing_confirmed(service)
    # Unsigned quotes have no service yet. They are visible only to users who
    # can open the dossier, and never enter the outbound/public projection.
    if role=='admin' and modules['billing']:
        for row in billing_events(db,start-timedelta(days=1),end):
            rental=row['billing_type']=='rental'
            if rental and not modules['rentals']:continue
            try:
                first=date.fromisoformat(row['activity_date'])
                last=date.fromisoformat(row['rental_end_date']) if rental and row['rental_end_date'] else first
            except (TypeError,ValueError):continue
            link=url_for('admin_billing_detail',record_id=row['id'])
            title=__ui_text__('Location · {0}',row['title']) if rental else row['title']
            begin=booking_time(str(first),row['activity_start_time'],zone)
            finish=booking_time(str(last),row['activity_end_time'],zone)
            if not rental and begin and finish and finish<begin:
                key='billing-'+str(row['id'])
                add_timed(title,'billing',key,first,begin,finish,link)
                for visible in (first,first+timedelta(days=1)):
                    if daily.get(visible) and daily[visible][-1]['key']==key:
                        daily[visible][-1]['tentative']=not billing_confirmed(row)
                continue
            for offset in range(max(0,(start-first).days), max(0,min((last-first).days+1,(end-first).days))):
                day=first+timedelta(days=offset)
                timed=first==last and begin and finish and begin<finish
                add(title,'billing','billing-'+str(row['id']),day,begin if timed else None,finish if timed else None,link)
                daily[day][-1].update(tentative=not billing_confirmed(row),rental_span=rental and last>first,
                    span_start=begin.isoformat() if begin else str(first),span_end=finish.isoformat() if finish else str(last),
                    time=(begin.strftime('%H:%M')+'–'+finish.strftime('%H:%M')) if timed else
                         (first.strftime('%d/%m')+' – '+last.strftime('%d/%m')) if rental and last>first else '')
    lower=datetime.combine(start,datetime.min.time(),zone).astimezone(timezone.utc).isoformat()
    upper=datetime.combine(end,datetime.min.time(),zone).astimezone(timezone.utc).isoformat()
    for row in (db.execute("SELECT b.*,r.name,COALESCE(r.color,t.color) AS display_color FROM resource_bookings b JOIN resources r USING(resource_uuid) JOIN resource_types t USING(type_key) WHERE status IN('requested','confirmed','performed') AND b.starts_at<? AND b.ends_at>?",(upper,lower)) if modules['resources'] else []):
        add_span(__ui_text__('Location · {0}',row['name']),
                 'reservation',row['booking_uuid'],datetime.fromisoformat(row['starts_at']),datetime.fromisoformat(row['ends_at']),
                 url_for('evolution.resource_bookings')+'#reservation-'+row['booking_uuid'],row['display_color'])
        for day in daily.values():
            if day and day[-1]['key']==row['booking_uuid']:day[-1]['tentative']=row['status']=='requested'
    for row in (db.execute('SELECT g.*,a.name FROM user_authorizations g JOIN authorizations a USING(authorization_uuid) WHERE performed_on>=? AND performed_on<?',(str(start),str(end))) if modules['authorizations'] else []):
        add(__ui_text__('Formation · ')+row['name'],'training',row['grant_uuid'],date.fromisoformat(row['performed_on']),link=url_for('evolution.authorizations')+'#formation-'+row['grant_uuid'])
    from machine_maintenance import enabled as maintenance_enabled, reminder_state, REMINDER_LABELS
    if maintenance_enabled(db) and show_maintenance(args):
        for row in db.execute('SELECT i.*,r.name FROM machine_interventions i JOIN resources r USING(resource_uuid) WHERE performed_on>=? AND performed_on<?',(str(start),str(end))):
            add(__ui_text__('Intervention effectuée · ')+row['name'],'maintenance',row['intervention_uuid'],date.fromisoformat(row['performed_on']),link=url_for('resource_portal.page',key=row['resource_uuid'])+'#intervention-'+row['intervention_uuid'],color='#3b8a68')
            daily[date.fromisoformat(row['performed_on'])][-1]['extra_details']=[row['description']]
        for row in db.execute("SELECT m.*,r.name FROM machine_reminders m JOIN resources r USING(resource_uuid) WHERE state IN('pending','done') AND due_on>=? AND due_on<?",(str(start),str(end))):
            day=date.fromisoformat(row['due_on']);state=reminder_state(row,today)
            add(__ui_text__('Rappel · ')+row['name'],'maintenance',row['reminder_uuid'],day,link=url_for('resource_portal.page',key=row['resource_uuid'])+'#reminder-'+row['reminder_uuid'],
                color={'overdue':'#a85247','today':'#916916','done':'#3b8a68'}.get(state,'#4478aa'))
            daily[day][-1].update(reminder_state=state,reminder_label=REMINDER_LABELS[state],extra_details=[row['subject']])
        from maintenance_planning import interval, visible
        for row in visible(db,start,end):
            begin,finish=interval(row,zone)
            add_span(row['title']+' · '+row['name'],'maintenance','planned-'+row['slot_uuid'],begin,finish,
                url_for('resource_portal.page',key=row['resource_uuid'],_anchor='maintenance-'+row['slot_uuid']),
                '#9a7719',flag='maintenance_span',all_day=not row['starts_time'],
                meta=dict(tentative=bool(row['tentative']),planning_confirmed=not row['tentative']))
        for row in db.execute("SELECT c.*,r.name,r.archived_at FROM machine_condition c JOIN resources r USING(resource_uuid) WHERE c.status!='operational'"):
            since=datetime.fromisoformat(row['status_since']).astimezone(zone).date()
            observed=min(today,datetime.fromisoformat(row['archived_at']).astimezone(zone).date()) if row['archived_at'] else today
            if since>observed:continue
            estimate=date.fromisoformat(row['return_estimate']) if row['return_estimate'] else None
            label,color={'maintenance':('En maintenance','#9a7719'),'unavailable':('Indisponible','#bb612c'),
                         'out_of_service':('Hors service','#b44d58')}.get(row['status'],('Indisponible','#bb612c'))
            link=url_for('resource_portal.page',key=row['resource_uuid'],_anchor='availability')
            title=__ui_text__(label)+' · '+row['name']
            # A condition is one interval. An estimate describes the day of
            # return, not another full day out of service. If that day has
            # arrived and the machine is still down, keep the observed state.
            finish_day=observed+timedelta(days=1)
            if estimate and not row['archived_at']:
                finish_day=max(finish_day,estimate)
            add_span(title,'maintenance',row['resource_uuid'],datetime.combine(since,datetime.min.time(),zone),
                datetime.combine(finish_day,datetime.min.time(),zone),link,color,
                flag='maintenance_span',all_day=True,
                meta=dict(time='',condition_ongoing=not row['archived_at'],estimated_return=estimate))
    configured_start, configured_end = display_window(db, a)
    timed = [event for events in daily.values() for event in events if not event['all_day'] and (show_hidden or not (event['hidden'] or event['automatic_hidden']))]
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
            detail = [event['day'].strftime('%d/%m/%Y'), event['time'] or __ui_text__('Journée entière')]
            if event.get('tentative'):detail.append(__ui_text__('Prévisionnel'))
            event.setdefault('people', [])
            if event.get('attendance'):
                detail.append(event['attendance'])
            if event['hidden']:
                detail.append(__ui_text__('Masqué manuellement — données conservées'))
            elif event['automatic_hidden']:
                detail.append(__ui_text__('Non tenu automatiquement — aucune présence enregistrée'))
            detail.extend(event.get('extra_details', []))
            detail.extend(enrich_billing_event(db, event, modules, a))
            def rental_details(row,begin=None,finish=None):
                def format_stamp(value):
                    return datetime.fromisoformat(value).astimezone(zone).strftime('%d/%m/%Y %H:%M')
                if begin and finish:
                    detail.append(__ui_text__('Créneau : {0} – {1}',format_stamp(begin),format_stamp(finish)))
                detail.append(__ui_text__('Remise : {0}',format_stamp(row['handed_over_at'])) if row['handed_over_at'] else __ui_text__('Remise non enregistrée'))
                detail.append(__ui_text__('Retour : {0}',format_stamp(row['returned_at'])) if row['returned_at'] else __ui_text__('Retour non enregistré'))
            if event.get('rental_meta'):
                rental=event['rental_meta']
                detail.append(__ui_text__('Annulée') if rental['quote_cancelled_at'] else __ui_text__('Confirmée') if rental['quote_signed_at'] else __ui_text__('En attente'))
                rental_details(rental,event.get('span_start'),event.get('span_end'))
            if event['kind']=='reservation' and not event.get('description') and (session.get('access_role') or ('admin' if session.get('admin_authenticated') else None))=='admin':
                row=db.execute("SELECT description FROM fablab_services WHERE id=? AND service_type='reservation'",(event['key'],)).fetchone()
                if row and row['description']:
                    event['description']=row['description']
            if event['kind'] == 'reservation':
                row = db.execute('SELECT b.*,u.first_name,u.last_name,r.required_authorization,a.name AS authorization_name FROM resource_bookings b LEFT JOIN users u ON u.id=b.user_id JOIN resources r USING(resource_uuid) LEFT JOIN authorizations a ON a.authorization_uuid=r.required_authorization WHERE booking_uuid=?',(event['key'],)).fetchone()
                if row:
                    from resource_booking import STATUS_LABELS
                    detail.extend([((row['first_name'] or __ui_text__('Usager supprimé')) + ' ' + (row['last_name'] or '')).strip(), STATUS_LABELS[row['status']]])
                    rental_details(row,row['starts_at'],row['ends_at'])
                    detail.append(__ui_text__('Tarif : ')+format(row['amount_cents']/100,'.2f').replace('.',',')+' €')
                    if row['required_authorization']:
                        detail.append(__ui_text__('Habilitation requise : ')+(row['authorization_name'] or __ui_text__('Habilitation historique')))
                        from resource_booking import authorization_valid
                        detail.append(__ui_text__('Habilitation valable au créneau') if row['user_id'] and authorization_valid(db,row['user_id'],row['required_authorization'],datetime.fromisoformat(row['starts_at']).astimezone(zone).isoformat(),datetime.fromisoformat(row['ends_at']).astimezone(zone).isoformat()) else __ui_text__('Habilitation à vérifier'))
            elif event['kind'] == 'training':
                row = db.execute('SELECT u.first_name,u.last_name FROM user_authorizations g LEFT JOIN users u ON u.id=g.user_id WHERE grant_uuid=?',(event['key'],)).fetchone()
                if row:
                    detail.append(((row['first_name'] or __ui_text__('Usager supprimé')) + ' ' + (row['last_name'] or '')).strip())
            elif event['kind'] == 'animation':
                description=db.execute('SELECT description FROM fablab_services WHERE id=?',(event['key'],)).fetchone()
                if description and description[0]:
                    detail.append(description[0])
                config = db.execute('SELECT * FROM animation_reservation_config WHERE service_id=?',(event['key'],)).fetchone()
                if config and modules['public_reservations']:
                    from reservations_sync import booking_counts, booking_reservation_status
                    bookings = db.execute('SELECT b.*,u.category FROM animation_bookings b LEFT JOIN users u ON u.id=b.user_id WHERE service_id=? AND environment=? ORDER BY CASE b.status WHEN \'waitlisted\' THEN 1 ELSE 0 END,b.created_at',(event['key'],config['environment'])).fetchall()
                    counts = booking_counts(bookings)
                    detail.append(str(counts['confirmed'])+__ui_text__(' confirmé(s) / ')+str(config['capacity'])+__ui_text__(' places'))
                    if counts['offer_pending']:
                        detail.append(str(counts['offer_pending'])+__ui_text__(' place(s) temporairement proposée(s)'))
                    detail.append(str(max(0,config['capacity']-counts['confirmed']-counts['offer_pending']))+__ui_text__(' place(s) libre(s)'))
                    if counts['waitlisted']:
                        detail.append(str(counts['waitlisted'])+__ui_text__(' en liste d’attente'))
                    labels = {'confirmed':__ui_native__('Confirmée'),'waitlisted':__ui_native__('Liste d’attente'),'offer_pending':__ui_native__('Place proposée'),'cancelled':__ui_native__('Annulée'),'expired':__ui_native__('Expirée')}
                    event['people'] = [{'name':(b['first_name']+' '+b['last_name']).strip(), 'category':b['category'] or '',
                        'state':labels.get(booking_reservation_status(b),__ui_text__('En cours'))}
                        for b in bookings if b['status'] not in ('cancelled','expired','declined')]
                    slots=db.execute('SELECT * FROM animation_slots WHERE service_id=? AND active=1 ORDER BY starts_at',(event['key'],)).fetchall()
                    if slots:
                        from reservations_sync import booking_capacity_used
                        for slot in slots:
                            count=booking_capacity_used(db,int(event['key']),slot['slot_uuid'])
                            detail.append(datetime.fromisoformat(slot['starts_at']).astimezone(zone).strftime('%H:%M')+'–'+datetime.fromisoformat(slot['ends_at']).astimezone(zone).strftime('%H:%M')+' : '+str(count)+' / '+str(slot['capacity'])+__ui_text__(' place(s)'))
                row = db.execute('SELECT actual_participants,expected_participants FROM fablab_services WHERE id=?',(event['key'],)).fetchone()
                if row:
                    if row['actual_participants'] is not None:
                        detail.append(str(row['actual_participants']) + __ui_text__(' participant(s) présent(s)'))
                    if row['expected_participants'] is not None:
                        detail.append(__ui_text__('Capacité : ') + str(row['expected_participants']) + __ui_text__(' place(s)'))
            from i18n import NativeText
            event['details'] = '\n'.join(__ui_text__(str(part)) if isinstance(part,NativeText) else part for part in detail)
            note=db.execute('SELECT note FROM calendar_notes WHERE event_kind=? AND event_key=? AND occurrence_date=?',
                (event['kind'],event['key'],event['day'].isoformat())).fetchone()
            event['internal_note']=note['note'] if note else ''
            for person in event['people']:
                row = db.execute('SELECT name FROM user_categories WHERE category_key=?',(person['category'],)).fetchone()
                person['category_label'] = row['name'] if row else person['category']
        events=[e for e in events if show_hidden or not(e['hidden'] or e['automatic_hidden'])]
        days.append({'date':day,'today':day==today,'timed':position_overlaps([e for e in events if not e['all_day']]),'all_day':[e for e in events if e['all_day']],'events':events})
        day+=timedelta(days=1)
    return {'view':view,'chosen':chosen,'days':days,'previous':previous,'following':following,'today':today,'hours':hours,'show_hidden':show_hidden,
            'week_rentals':week_rentals(days) if view=='week' else [],
            'week_maintenance':week_bands(days,'maintenance_span') if view=='week' else [],
            'month_weeks':[dict(days=days[i:i+7],maintenance=week_bands(days[i:i+7],'maintenance_span'))
                           for i in range(0,len(days),7)] if view=='month' else [],
            'has_all_day':any(not (event.get('rental_span') or event.get('maintenance_span')) for day in days for event in day['all_day']),
            'timeline_height':max(180, window_duration), 'window_extended':(window_start,window_end)!=(configured_start,configured_end),
            'visible_start':f'{window_start//60:02d}:{window_start%60:02d}', 'visible_end':f'{window_end//60:02d}:{window_end%60:02d}',
            'heading':(__ui_text__('Semaine du ')+start.strftime('%d/%m/%Y')) if view=='week' else chosen.strftime('%m/%Y')}
