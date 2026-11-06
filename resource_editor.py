"""Unified presentation reuses the resource, maintenance and lifecycle engines."""
from datetime import datetime,timezone
from family_model import local_day
import resource_booking as bookings
import machine_maintenance as machines
import resource_loans as loans
from resource_sort import ordered
from evolution_schema import audit,now

def save_fields(db,key,form,role,section,modules):
    existing=dict(db.execute('SELECT * FROM resources WHERE resource_uuid=?',(key,)).fetchone())
    if existing['archived_at']:raise ValueError('Restaurez cette ressource avant de la modifier.')
    values=dict(existing)
    if section=='general':
        for field in ('name','type_key','description'):values[field]=form.get(field,'')
        values['color']='' if form.get('color_default')=='1' else form.get('color','')
    elif section=='booking_settings':
        values.update(active=form.get('active')=='1',approval_required=form.get('approval_required')=='1',
            price_cents=bookings.euros_to_cents(form.get('price_euros','')),required_authorization=form.get('required_authorization') or None)
        if values['required_authorization'] and not modules['authorizations'] and values['required_authorization']!=existing['required_authorization']:
            raise ValueError('Activez Formations et habilitations avant d’exiger une habilitation.')
    else:raise ValueError('Action inconnue.')
    bookings.save_resource(db,values,role,key)

def save_legacy_prices(db,key,form,role,api):
    if role!='admin':raise PermissionError('Tarifs réservés à l’Administrateur.')
    row=db.execute('SELECT c.* FROM rental_catalog c JOIN resources r ON r.legacy_machine_key=c.machine_key WHERE r.resource_uuid=?',(key,)).fetchone()
    if not row or row['archived']:raise ValueError('Tarif historique non modifiable.')
    monthly,error=api.parse_money_cents(form.get('monthly'),'Tarif mensuel')
    if error:raise ValueError(error)
    deposit,error=api.parse_money_cents(form.get('deposit'),'Caution')
    if error:raise ValueError(error)
    db.execute('UPDATE rental_catalog SET monthly_cents=?,deposit_cents=?,updated_at=? WHERE machine_key=?',(monthly,deposit,now(),row['machine_key']))
    audit(db,'resource',key,'rental_prices_saved',role)

def context(db,key,role,modules,api):
    item=machines.machine(db,key)
    operations=loans.operations(db,key)
    operations=[r|dict(late=loans.overdue(db,r)) for r in operations if
        (r['kind']=='booking' and modules['resources']) or (r['kind']=='contract' and role=='admin' and modules['billing'] and modules['rentals'])]
    for operation in operations:
        if operation['kind']=='contract':operation['people']=db.execute('SELECT id,first_name,last_name FROM users WHERE active=1 ORDER BY first_name,last_name LIMIT 2000').fetchall() if modules['users'] else []
    today=local_day(db)
    reminders=[]
    for row in db.execute('SELECT * FROM machine_reminders WHERE resource_uuid=? ORDER BY due_on,created_at',(key,)):
        state=machines.reminder_state(row,today)
        reminders.append(dict(row)|dict(due_state=state,due_label=machines.REMINDER_LABELS[state]))
    return dict(resource=item,machine=item,states=machines.STATES,kinds=machines.KINDS,form_kinds=machines.FORM_KINDS,
        resource_types=db.execute('SELECT * FROM resource_types ORDER BY sort_order,name').fetchall(),authorizations=bookings.definitions(db,True),
        interventions=db.execute('SELECT * FROM machine_interventions WHERE resource_uuid=? ORDER BY performed_on DESC,created_at DESC',(key,)).fetchall(),
        reminders=reminders,
        maintenance_slots=db.execute('SELECT * FROM machine_maintenance_slots WHERE resource_uuid=? ORDER BY starts_on DESC,starts_time DESC,slot_uuid',(key,)).fetchall() if machines.enabled(db) else [],
        history=machines.history_entries(db,key),operations=sorted(operations,key=lambda r:r['begin'],reverse=True),
        legacy_catalog=db.execute('SELECT c.* FROM rental_catalog c JOIN resources r ON r.legacy_machine_key=c.machine_key WHERE r.resource_uuid=?',(key,)).fetchone()
            if role=='admin' and modules['billing'] and modules['rentals'] else None,
        affected_bookings=db.execute("SELECT starts_at,ends_at FROM resource_bookings WHERE resource_uuid=? AND status IN ('requested','confirmed') AND julianday(ends_at)>julianday(?) ORDER BY starts_at",(key,datetime.now(timezone.utc).isoformat())).fetchall() if not loans.availability(db,key)['available'] else [],
        discord_configured=bool(api.read_discord_webhook()) and modules['discord'] and api.load_discord_settings(db)['enabled'])
