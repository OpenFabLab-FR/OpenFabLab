"""Actual handovers on existing bookings/contracts; no duplicate loan ledger."""
from datetime import date,datetime,timezone
from zoneinfo import ZoneInfo
from memberships import atomic
from evolution_schema import audit,now
from family_model import setting

LABELS={'operational':'Disponible','rental_available':'Disponible à la location','reserved':'Réservée','loaned':'En prêt',
        'overdue':'Retour en retard','maintenance':'En maintenance','unavailable':'Indisponible','out_of_service':'Hors service','archived':'Archivée'}

def local_day(db,current=None):
    return (current or datetime.now(timezone.utc)).astimezone(ZoneInfo(setting(db,'structure_timezone','Europe/Paris'))).date()

def operations(db,key=None,user_id=None):
    result=[]
    for row in db.execute('''SELECT b.*,r.name,r.archived_at,r.availability_mode FROM resource_bookings b
        JOIN resources r USING(resource_uuid) WHERE (? IS NULL OR b.resource_uuid=?)
        AND (? IS NULL OR b.user_id=?) AND NOT EXISTS(SELECT 1 FROM billing_records c
        WHERE c.id=b.billing_record_id AND c.billing_type='rental')''',(key,key,user_id,user_id)):
        r=dict(row);r.update(kind='booking',key=r['booking_uuid'],begin=r['starts_at'],due=r['ends_at'],
                            url='/admin/ressources/reservations',person=r['user_id'])
        result.append(r)
    for row in db.execute('''SELECT b.*,r.resource_uuid,r.name,r.archived_at FROM billing_records b
        JOIN resources r ON r.legacy_machine_key=b.rental_machine_key WHERE b.billing_type='rental'
        AND (? IS NULL OR r.resource_uuid=?) AND (? IS NULL OR b.rental_user_id=?)''',(key,key,user_id,user_id)):
        r=dict(row);r.update(kind='contract',key=str(r['id']),begin=r['activity_date'],due=r['rental_end_date'] or r['activity_date'],
            url='/admin/facturation/'+str(r['id']),person=r['rental_user_id'],status='cancelled' if r['quote_cancelled_at'] else 'confirmed' if r['quote_signed_at'] else 'requested')
        result.append(r)
    return result

def outstanding(db,key):
    return [r for r in operations(db,key) if r['handed_over_at'] and not r['returned_at']]

def overdue(db,row,current=None):
    if not row['handed_over_at'] or row['returned_at']:return False
    current=current or datetime.now(timezone.utc)
    try:
        if len(row['due'])==10:return date.fromisoformat(row['due'])<local_day(db,current)
        due=datetime.fromisoformat(row['due'].replace('Z','+00:00'))
        return due.tzinfo is not None and due<current
    except (ValueError,TypeError):return False

def availability(db,key,current=None):
    row=db.execute('''SELECT r.archived_at,r.availability_mode,c.status FROM resources r LEFT JOIN machine_condition c USING(resource_uuid)
                      WHERE r.resource_uuid=?''',(key,)).fetchone()
    if not row:raise ValueError('Ressource inconnue.')
    if row['archived_at']:state='archived'
    elif row['status'] in ('maintenance','out_of_service'):state=row['status']
    else:
        active=outstanding(db,key)
        state=('overdue' if any(overdue(db,r,current) for r in active) else 'loaned' if active else
               'unavailable' if row['status']=='unavailable' else 'rental_available' if row['availability_mode']=='rental' else 'operational')
    return dict(status=state,label=LABELS[state],available=state in ('operational','rental_available'))

def transition(db,kind,key,action,role,user_id=None,current=None):
    if role not in ('admin','moderator') or kind not in ('booking','contract') or action not in ('handover','return'):
        raise PermissionError('Action réservée à l’équipe.')
    if kind=='contract' and role!='admin':raise PermissionError('Contrat réservé à l’Administrateur.')
    current=current or datetime.now(timezone.utc)
    if current.tzinfo is None:raise ValueError('Horodatage avec fuseau requis.')
    table,column=('resource_bookings','booking_uuid') if kind=='booking' else ('billing_records','id')
    with atomic(db):
        row=next((r for r in operations(db) if r['kind']==kind and r['key']==str(key)),None)
        if not row:raise ValueError('Location ou réservation inconnue.')
        if action=='handover':
            if row['handed_over_at']:return False
            if row['status']!='confirmed':raise ValueError('Confirmez la réservation ou acceptez le devis avant la remise.')
            if not availability(db,row['resource_uuid'],current)['available']:
                raise ValueError('Cette ressource est indisponible. Aucune remise enregistrée.')
            if kind=='contract' and user_id:
                if not db.execute('SELECT 1 FROM users WHERE id=? AND active=1',(user_id,)).fetchone():raise ValueError('Choisissez un usager actif.')
                db.execute('UPDATE billing_records SET rental_user_id=? WHERE id=?',(user_id,key))
            db.execute('UPDATE '+table+' SET handed_over_at=? WHERE '+column+'=?',(current.isoformat(timespec='seconds'),key))
        else:
            if not row['handed_over_at']:raise ValueError('La remise de ce matériel n’a pas été enregistrée.')
            if row['returned_at']:return False
            if datetime.fromisoformat(row['handed_over_at'])>current:raise ValueError('Le retour précède la remise.')
            db.execute('UPDATE '+table+' SET returned_at=? WHERE '+column+'=?',(current.isoformat(timespec='seconds'),key))
        audit(db,'resource_loan',kind+':'+str(key),action,role,{'resource_uuid':row['resource_uuid']})
    return True

def user_history(db,user_id,role,current=None):
    if role not in ('admin','moderator'):raise PermissionError('Action réservée à l’équipe.')
    current=current or datetime.now(timezone.utc)
    zone=ZoneInfo(setting(db,'structure_timezone','Europe/Paris'))
    def label(row):
        if row['returned_at']:return 'Terminée'
        if overdue(db,row,current):return 'Retour en retard'
        if row['handed_over_at']:return 'En prêt'
        if row['status']=='cancelled':return 'Annulée'
        if row['status']=='refused':return 'Refusée'
        if row['status']=='requested':return 'Demande à confirmer'
        try:
            begin=datetime.fromisoformat(row['begin'])
            if begin.tzinfo is None:begin=begin.replace(tzinfo=zone)
            if begin<=current:return 'Remise non enregistrée'
        except (ValueError,TypeError):return 'Remise non enregistrée'
        return 'À venir'
    rows=operations(db,user_id=user_id)
    return [r|dict(label=label(r))
            for r in sorted(rows,key=lambda r:r['begin'],reverse=True) if role=='admin' or r['kind']=='booking']
