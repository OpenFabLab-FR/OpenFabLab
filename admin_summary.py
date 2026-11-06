"""Read-only daily summary; group actions without changing their counts."""
from collections import defaultdict
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from flask import request,url_for
from family_model import setting
from i18n import native,t
from localized_formats import calendar_moment,event_display,timestamp
import machine_maintenance as machines
import resource_loans as loans
from admin_activity import journal
from admin_planning import billing_confirmed,billing_events,booking_time


def build(db,modules,role,current=None,schedule=None):
    current=(current or datetime.now(timezone.utc)).astimezone(timezone.utc)
    zone=ZoneInfo(setting(db,'structure_timezone','Europe/Paris'));today=current.astimezone(zone).date()
    horizon=today+timedelta(days=14)
    actions=[];upcoming=[];cards=[];grouped=defaultdict(list)
    def action(title,count,url,detail='',kind='tasks',resource=None,late=False,hint=''):
        if count:
            item=dict(title=title,count=count,url=url,detail=native(detail),kind=kind,late=late,hint=hint)
            (grouped[resource] if resource else actions).append(item)
    def schedule_item(title,when,detail,url,kind='calendar',tentative=False,translate_detail=True):
        begins=moment(when)
        if begins and today<=begins.date()<=horizon and (len(when)==10 or begins.astimezone(timezone.utc)>=current.astimezone(timezone.utc)):
            upcoming.append(dict(title=title,date=when,display=event_display(when,zone),
                                 detail=native(detail) if translate_detail else detail,url=url,kind=kind,tentative=tentative))
    def operation_url(row):
        return request.script_root+row['url']+('#reservation-'+row['key'] if row['kind']=='booking' else '')
    def moment(value,end=False):
        if not value:return None
        stamp=calendar_moment(value,zone)
        return stamp+timedelta(days=1) if stamp and len(value)==10 and end else stamp
    if modules['resources']:
        for row in db.execute("""SELECT b.booking_uuid,b.starts_at,r.resource_uuid,r.name FROM resource_bookings b JOIN resources r USING(resource_uuid)
            WHERE b.status='requested' ORDER BY b.starts_at,b.booking_uuid"""):
            begins=moment(row['starts_at'])
            action(row['name'],1,url_for('evolution.resource_bookings')+'#reservation-'+row['booking_uuid'],
                   'Réservation à confirmer','loan',row['resource_uuid'],bool(begins and begins<current))
    operations=[]
    if modules['resources'] or role=='admin' and modules['billing'] and modules['rentals']:
        operations=[r for r in loans.operations(db) if (r['kind']=='booking' and modules['resources']) or
            (r['kind']=='contract' and role=='admin' and modules['billing'] and modules['rentals'])]
        active=[r for r in operations if r['handed_over_at'] and not r['returned_at']]
        late=[r for r in active if loans.overdue(db,r,current)]
        booked=[r for r in operations if r['status']=='confirmed' and not r['handed_over_at'] and not r['returned_at']
                and (start:=moment(r['begin'])) and (end:=moment(r['due'],True)) and start<=current<end]
        cards.append(dict(title='Locations et réservations en cours',icon='↔',count=len(active)+len(booked),
            detail=t('{0} avec remise · {1} sur créneau confirmé',len(active),len(booked)),
            url=url_for('evolution.resource_bookings') if modules['resources'] else url_for('admin_billing')))
        for row in sorted(active,key=lambda r:r['due'] or ''):
            if row in late or (deadline:=moment(row['due'])) and deadline.astimezone(zone).date()<=today:
                action(row['name'],1,operation_url(row),'Retour en retard' if row in late else 'Retour attendu aujourd’hui',
                       'loan',row['resource_uuid'],row in late)
        for row in booked:
            action(row['name'],1,operation_url(row),'Créneau en cours · remise non enregistrée','loan',row['resource_uuid'])
        for row in sorted(operations,key=lambda r:r['begin'] or ''):
            if row['returned_at'] or row['status'] not in ('confirmed','requested'):continue
            tentative=row['status']=='requested'
            if not row['handed_over_at']:
                begin=booking_time(row['begin'],row['activity_start_time'],zone) if row['kind']=='contract' else None
                schedule_item(row['name'],begin.isoformat() if begin else row['begin'],'Début de location' if row['kind']=='contract' else 'Créneau de réservation',
                              operation_url(row),'loan',tentative)
            if row['handed_over_at'] or row['due']!=row['begin'] and (row['kind']=='contract' or row['availability_mode']=='rental'):
                finish=booking_time(row['due'],row['activity_end_time'],zone) if row['kind']=='contract' else None
                schedule_item(row['name'],finish.isoformat() if finish else row['due'],'Retour prévu',operation_url(row),'loan',tentative)
    if modules['resources'] or machines.enabled(db):
        resources=db.execute('SELECT resource_uuid,name FROM resources WHERE archived_at IS NULL ORDER BY name').fetchall()
        unavailable=[r for r in resources if not loans.availability(db,r['resource_uuid'],current)['available']]
        cards.append(dict(title='Ressources indisponibles',icon='◇',count=len(unavailable),url=url_for('evolution.resource_directory')))
    if machines.enabled(db):
        reminders=db.execute("SELECT m.*,r.name FROM machine_reminders m JOIN resources r USING(resource_uuid) WHERE m.state='pending' AND r.archived_at IS NULL AND m.due_on<=? ORDER BY m.due_on",(str(today+timedelta(days=14)),)).fetchall()
        due=[r for r in reminders if r['due_on']<=str(today)]
        for row in due:
            state=machines.reminder_state(row,today)
            action(row['name'],1,url_for('resource_portal.page',key=row['resource_uuid'],_anchor='reminder-'+row['reminder_uuid']),
                   'Rappel', 'resource',row['resource_uuid'],state=='overdue',
                   hint=row['subject']+(' · '+t(machines.REMINDER_LABELS[state]) if state=='today' else ''))
        for row in db.execute("""SELECT c.resource_uuid,r.name FROM machine_condition c JOIN resources r USING(resource_uuid)
            WHERE r.archived_at IS NULL AND c.status IN ('maintenance','unavailable','out_of_service') ORDER BY r.name"""):
            action(row['name'],1,url_for('resource_portal.page',key=row['resource_uuid'],_anchor='availability'),
                   'État de la ressource à suivre','resource',row['resource_uuid'])
        for row in reminders:
            if str(today)<row['due_on']<=str(today+timedelta(days=14)):
                schedule_item(row['name'],row['due_on'],row['subject'],
                              url_for('resource_portal.page',key=row['resource_uuid'],_anchor='reminder-'+row['reminder_uuid']),'resource',translate_detail=False)
        from maintenance_planning import visible
        for row in visible(db,today,horizon+timedelta(days=1)):
            when=row['starts_on']+('T'+row['starts_time'] if row['starts_time'] else '')
            schedule_item(row['name'],when,row['title'],
                          url_for('resource_portal.page',key=row['resource_uuid'],_anchor='maintenance-'+row['slot_uuid']),
                          'resource',bool(row['tentative']),translate_detail=False)
    if modules['resources'] or machines.enabled(db):
        for row in db.execute("""SELECT s.report_id,s.resource_uuid,s.state,s.received_at,r.name FROM resource_problem_reports s
            JOIN resources r USING(resource_uuid) WHERE s.state IN('new','assigned') ORDER BY s.received_at,s.report_id"""):
            received=moment(row['received_at'])
            action(row['name'],1,url_for('resource_portal.page',key=row['resource_uuid'],report=row['report_id'],
                   _anchor='signalement-'+row['report_id']),'Signalement à inspecter' if row['state']=='new' else 'Signalement pris en charge',
                   'report',row['resource_uuid'],hint=timestamp(received.astimezone(zone)) if received else '')
    if modules['activities']:
        from animation_attendance import interval
        pending={}
        for row in db.execute('''SELECT b.service_id,b.slot_uuid,s.title,s.service_date,s.start_time,s.end_time,
            sl.starts_at AS slot_start,sl.ends_at AS slot_end FROM animation_bookings b
            JOIN fablab_services s ON s.id=b.service_id LEFT JOIN animation_slots sl ON sl.slot_uuid=b.slot_uuid
            WHERE b.status='confirmed' AND b.is_present IS NULL AND s.service_date<=?''',(str(today),)):
            try:span=interval(row,zone)
            except (ValueError,TypeError):span=None
            if span and span[1]<=current:
                title,count=pending.get(row['service_id'],(row['title'],0))
                pending[row['service_id']]=title,count+1
        for key,(title,count) in pending.items():
            if modules['public_reservations']:
                action(title,count,url_for('admin_animation_bookings',service_id=key),'Présences à renseigner','calendar')
        candidates=db.execute("""SELECT id,title,service_date,start_time FROM fablab_services
            WHERE service_type='animation' AND service_date BETWEEN ? AND ? ORDER BY service_date,start_time""",
            (str(today),str(horizon))).fetchall()
        animation_count=0
        for row in candidates:
            before=len(upcoming)
            link=url_for('admin_animation_bookings',service_id=row['id']) if modules['public_reservations'] else url_for('admin_services')
            slots=db.execute('SELECT starts_at FROM animation_slots WHERE service_id=? AND active=1 ORDER BY starts_at LIMIT 30',
                             (row['id'],)).fetchall() if modules['public_reservations'] else []
            if slots:
                for slot in slots:schedule_item(row['title'],slot['starts_at'],'Créneau d’animation',link)
            else:
                schedule_item(row['title'],row['service_date']+('T'+row['start_time'] if row['start_time'] else ''),'Animation',link)
            animation_count+=int(len(upcoming)>before)
        cards.append(dict(title='Animations à venir · 14 jours',icon='▤',count=animation_count,url=url_for('admin_services')))
    if modules['frequency'] and schedule:
        from openlab_openings import day_schedule
        week={i:row for i,row in enumerate(schedule)}
        for offset in range(15):
            day=today+timedelta(days=offset)
            row=day_schedule(db,day,week)
            if row['active'] and row['start'] and row['end']:
                schedule_item(row['title'],str(day)+'T'+row['start'],'OpenLab',url_for('admin_frequency_day',date=str(day)))
    if role=='admin' and modules['billing']:
        rows=db.execute('''SELECT id,title,quote_number,quote_signed_at,quote_cancelled_at,invoice_number,invoice_sent_at,paid_at
            FROM billing_records WHERE quote_cancelled_at IS NULL AND (invoice_number IS NULL OR paid_at IS NULL)
            ORDER BY quote_date DESC,id DESC''').fetchall()
        unsigned=[r for r in rows if not r['invoice_number'] and not r['quote_signed_at'] and not r['quote_cancelled_at']]
        unpaid=[r for r in rows if r['invoice_number'] and not r['paid_at'] and not r['quote_cancelled_at']]
        signed=[r for r in rows if not r['invoice_number'] and r['quote_signed_at'] and not r['quote_cancelled_at']]
        for row in unsigned+signed+unpaid:
            sent=moment(row['invoice_sent_at'])
            if row['invoice_number']:
                detail=('Relance : facture envoyée depuis au moins 30 jours' if sent and sent<=current-timedelta(days=30)
                    else 'Facture à encaisser' if sent else 'Facture à envoyer')
            else:detail='Devis signé · facture à établir' if row['quote_signed_at'] else 'Devis en attente de signature'
            action(row['title'],1,url_for('admin_billing_detail',record_id=row['id']),detail,
                   'invoice' if row['invoice_number'] else 'quote',late=bool(row['invoice_number'] and sent and sent<=current-timedelta(days=30)))
        for row in billing_events(db,today,horizon+timedelta(days=1),include_linked=True):
            begin=booking_time(row['activity_date'],row['activity_start_time'],zone)
            rental=row['billing_type']=='rental'
            if rental and (not modules['rentals'] or any(r['kind']=='contract' and r['key']==str(row['id']) for r in operations)):continue
            link=url_for('admin_billing_detail',record_id=row['id'])
            schedule_item(row['title'],begin.isoformat() if begin else row['activity_date'],
                          'Début de location' if rental else 'Prestation client',link,'loan' if rental else 'quote',not billing_confirmed(row))
            if rental and row['rental_end_date'] and not row['returned_at']:
                schedule_item(row['title'],row['rental_end_date'],'Retour prévu',link,'loan',not billing_confirmed(row))
    groups=[dict(title=items[0]['title'],count=sum(i['count'] for i in items),kind='resource',
                 url=url_for('resource_portal.page',key=key),tasks=sorted(items,key=lambda i:not i['late']),
                 late=any(i['late'] for i in items)) for key,items in grouped.items()]
    actions=sorted(groups+actions,key=lambda item:(not item['late'],item['title'].casefold()))
    recent=journal(db,modules,role)
    # Render a bounded pool. The dashboard starts at six and reveals only
    # the rows that fit beside the measured task and activity stack.
    return dict(cards=cards,actions=actions,action_count=sum(item['count'] for item in actions),
                upcoming=sorted(upcoming,key=lambda r:moment(r['date']).astimezone(timezone.utc))[:15],
                recent=sorted(recent,key=lambda r:moment(r['date']) or datetime.min.replace(tzinfo=timezone.utc),reverse=True)[:15])
