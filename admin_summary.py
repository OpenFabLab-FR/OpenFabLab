"""Read-only daily summary projected from existing modules; no new ledger."""
from datetime import datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
from flask import request,url_for
from family_model import setting
from i18n import native,t
import machine_maintenance as machines
import resource_loans as loans


def build(db,modules,role,current=None):
    current=current or datetime.now(timezone.utc)
    zone=ZoneInfo(setting(db,'structure_timezone','Europe/Paris'));today=current.astimezone(zone).date()
    actions=[];upcoming=[];recent=[];cards=[]
    def action(title,count,url,detail=''):
        if count:actions.append(dict(title=title,count=count,url=url,detail=native(detail)))
    def operation_url(row):
        return request.script_root+row['url']+('#reservation-'+row['key'] if row['kind']=='booking' else '')
    def moment(value,end=False):
        if not value:return None
        try:
            if len(value)==10 and end:return datetime.combine(datetime.fromisoformat(value).date()+timedelta(days=1),time.min,zone)
            stamp=datetime.fromisoformat(value)
            return stamp if stamp.tzinfo else stamp.replace(tzinfo=zone)
        except (TypeError,ValueError):return None
    if modules['resources']:
        for row in db.execute("""SELECT b.booking_uuid,r.name FROM resource_bookings b JOIN resources r USING(resource_uuid)
            WHERE b.status='requested' ORDER BY b.starts_at,b.booking_uuid"""):
            action(row['name'],1,url_for('evolution.resource_bookings')+'#reservation-'+row['booking_uuid'],'Réservation à confirmer')
        for row in db.execute("""SELECT b.booking_uuid,r.name,b.created_at FROM resource_bookings b
            JOIN resources r USING(resource_uuid) ORDER BY b.created_at DESC,b.booking_uuid LIMIT 15"""):
            recent.append(dict(title=row['name'],detail=native('Réservation de ressource'),date=row['created_at'],
                url=url_for('evolution.resource_bookings')+'#reservation-'+row['booking_uuid']))
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
                actions.append(dict(title=row['name'],count=None,url=operation_url(row),detail=native('Retour en retard' if row in late else 'Retour attendu aujourd’hui')))
        for row in booked:
            actions.append(dict(title=row['name'],count=None,url=operation_url(row),detail=native('Créneau en cours · remise non enregistrée')))
        for row in sorted(operations,key=lambda r:r['begin'] or ''):
            if row['handed_over_at'] or row['status']!='confirmed':continue
            try:
                start=datetime.fromisoformat(row['begin'])
                if start.tzinfo is None:start=start.replace(tzinfo=zone)
            except (ValueError,TypeError):continue
            if current<=start<=current+timedelta(days=14):
                upcoming.append(dict(title=row['name'],date=row['begin'],detail=native('Remise à venir'),url=operation_url(row)))
    if modules['resources'] or machines.enabled(db):
        resources=db.execute('SELECT resource_uuid,name FROM resources WHERE archived_at IS NULL ORDER BY name').fetchall()
        unavailable=[r for r in resources if not loans.availability(db,r['resource_uuid'],current)['available']]
        cards.append(dict(title='Ressources indisponibles',icon='◇',count=len(unavailable),url=url_for('evolution.resource_directory')))
    if machines.enabled(db):
        reminders=db.execute("SELECT m.*,r.name FROM machine_reminders m JOIN resources r USING(resource_uuid) WHERE m.state='pending' AND r.archived_at IS NULL AND m.due_on<=? ORDER BY m.due_on",(str(today+timedelta(days=14)),)).fetchall()
        due=[r for r in reminders if r['due_on']<=str(today)]
        for row in due:
            actions.append(dict(title=row['name'],count=1,url=url_for('resource_portal.page',key=row['resource_uuid'])+'#reminder-'+row['reminder_uuid'],detail=row['subject']))
        for row in db.execute("""SELECT c.resource_uuid,r.name FROM machine_condition c JOIN resources r USING(resource_uuid)
            WHERE r.archived_at IS NULL AND c.status IN ('maintenance','out_of_service') ORDER BY r.name"""):
            action(row['name'],1,url_for('resource_portal.page',key=row['resource_uuid'])+'#availability','État de la ressource à suivre')
        for row in reminders:
            if str(today)<row['due_on']<=str(today+timedelta(days=14)):
                upcoming.append(dict(title=row['name'],date=row['due_on'],detail=row['subject'],url=url_for('resource_portal.page',key=row['resource_uuid'])+'#reminders'))
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
            action(title,count,url_for('admin_animation_bookings',service_id=key),'Présences à renseigner')
        upcoming_animations=db.execute("""SELECT id,title,service_date,start_time FROM fablab_services
            WHERE service_type='animation' AND (service_date>? OR (service_date=? AND COALESCE(start_time,'00:00')>=?))
            AND service_date<=? ORDER BY service_date,start_time""",
            (str(today),str(today),current.astimezone(zone).strftime('%H:%M'),str(today+timedelta(days=14)))).fetchall()
        cards.append(dict(title='Animations à venir · 14 jours',icon='▤',count=len(upcoming_animations),url=url_for('admin_services')))
        for row in upcoming_animations[:10]:
            upcoming.append(dict(title=row['title'],date=row['service_date']+'T'+(row['start_time'] or '00:00'),detail=native('Animation'),url=url_for('admin_animation_bookings',service_id=row['id'])))
        for row in db.execute('''SELECT s.id,s.title,COUNT(*) AS quantity,MAX(b.created_at) AS created_at,b.status
            FROM animation_bookings b JOIN fablab_services s ON s.id=b.service_id
            GROUP BY COALESCE(b.group_uuid,b.external_uuid) ORDER BY MAX(b.created_at) DESC LIMIT 15'''):
            recent.append(dict(title=row['title'],detail=t('Inscriptions : {0}',row['quantity']),date=row['created_at'],url=url_for('admin_animation_bookings',service_id=row['id'])))
    if modules['users']:
        for row in db.execute('SELECT id,first_name,last_name,created_at FROM users ORDER BY created_at DESC,id DESC LIMIT 15'):
            recent.append(dict(title=row['first_name']+' '+row['last_name'],detail=native('Compte usager créé'),date=row['created_at'],url=url_for('v215.user_history',user_id=row['id'])))
    if role=='admin' and modules['billing']:
        rows=db.execute('SELECT id,title,quote_number,quote_signed_at,quote_cancelled_at,invoice_number,invoice_sent_at,paid_at FROM billing_records ORDER BY quote_date DESC,id DESC').fetchall()
        unsigned=[r for r in rows if not r['invoice_number'] and not r['quote_signed_at'] and not r['quote_cancelled_at']]
        unpaid=[r for r in rows if r['invoice_number'] and not r['paid_at'] and not r['quote_cancelled_at']]
        signed=[r for r in rows if not r['invoice_number'] and r['quote_signed_at'] and not r['quote_cancelled_at']]
        for row in unsigned+signed+unpaid:
            sent=moment(row['invoice_sent_at'])
            if row['invoice_number']:
                detail=('Relance : facture envoyée depuis au moins 30 jours' if sent and sent<=current-timedelta(days=30)
                    else 'Facture à encaisser' if sent else 'Facture à envoyer')
            else:detail='Devis signé · facture à établir' if row['quote_signed_at'] else 'Devis en attente de signature'
            action(row['title'],1,url_for('admin_billing_detail',record_id=row['id']),detail)
    return dict(cards=cards,actions=actions,upcoming=sorted(upcoming,key=lambda r:r['date'])[:8],
                recent=sorted(recent,key=lambda r:moment(r['date']) or datetime.min.replace(tzinfo=timezone.utc),reverse=True)[:15])
