"""Resource lifecycle. Caller holds BEGIN IMMEDIATE until commit; no cascade."""
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from evolution_schema import audit,now
from family_model import setting

def resource(db,key):
    row=db.execute('SELECT * FROM resources WHERE resource_uuid=?',(key,)).fetchone()
    if not row:raise ValueError('Ressource inconnue.')
    return dict(row)

def pending(db,key,current=None):
    item=resource(db,key);current=current or datetime.now(timezone.utc)
    result={}
    from resource_loans import outstanding
    if outstanding(db,key):result['prets_non_restitues']=len(outstanding(db,key))
    count=db.execute("SELECT COUNT(*) FROM resource_bookings WHERE resource_uuid=? AND (status='requested' OR (status='confirmed' AND (julianday(ends_at) IS NULL OR julianday(ends_at)>julianday(?))))",(key,current.isoformat())).fetchone()[0]
    if count:result['reservations']=count
    count=db.execute("SELECT COUNT(*) FROM machine_reminders WHERE resource_uuid=? AND state='pending'",(key,)).fetchone()[0]
    if count:result['rappels']=count
    day=current.astimezone(ZoneInfo(setting(db,'structure_timezone','Europe/Paris'))).date().isoformat()
    count=db.execute('SELECT COUNT(*) FROM machine_maintenance_slots WHERE resource_uuid=? AND cancelled_at IS NULL AND ends_on>=?',(key,day)).fetchone()[0]
    if count:result['maintenances_planifiees']=count
    count=db.execute("SELECT COUNT(*) FROM resource_problem_reports WHERE resource_uuid=? AND state IN('new','assigned')",(key,)).fetchone()[0]
    if count:result['signalements']=count
    if item['legacy_machine_key']:
        count=db.execute("SELECT COUNT(*) FROM billing_records WHERE rental_machine_key=? AND quote_cancelled_at IS NULL AND COALESCE(rental_end_date,activity_date)>=?",(item['legacy_machine_key'],day)).fetchone()[0]
        if count:result['locations']=count
    return result

def dependencies(db,key):
    item=resource(db,key);result={}
    # Discover every FK, including future/unknown referencing tables. Quoted
    # identifiers originate only from SQLite schema metadata, never request data.
    quote=lambda n:'"'+n.replace('"','""')+'"'
    for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall():
        for foreign in db.execute('PRAGMA foreign_key_list('+quote(name)+')').fetchall():
            if foreign[2].casefold()=='resources':
                if foreign[4] and foreign[4].casefold()!='resource_uuid':raise ValueError('Référence inconnue : suppression refusée. Utilisez l’archivage.')
                count=db.execute('SELECT COUNT(*) FROM '+quote(name)+' WHERE '+quote(foreign[3])+'=?',(key,)).fetchone()[0]
                if count:result[name]=count
    if item['legacy_machine_key']:
        for table,column in [('rental_catalog','machine_key'),('billing_records','rental_machine_key')]:
            count=db.execute('SELECT COUNT(*) FROM '+table+' WHERE '+column+'=?',(item['legacy_machine_key'],)).fetchone()[0]
            if count:result[table]=count
    return result

def change(db,key,action,role,confirmation='',current=None):
    if role!='admin':raise PermissionError('Gestion des ressources réservée à l’Administrateur.')
    if not db.in_transaction:raise RuntimeError('Transaction de modification requise.')
    item=resource(db,key)
    if action=='archive':
        if item['archived_at']:raise ValueError('Cette ressource est déjà archivée.')
        remaining=pending(db,key,current)
        if remaining:raise ValueError('Archivage impossible : des opérations ou des signalements restent à traiter.')
        db.execute('UPDATE resources SET archived_at=?,updated_at=? WHERE resource_uuid=?',(now(),now(),key))
    elif action=='restore':
        if not item['archived_at']:raise ValueError('Cette ressource n’est pas archivée.')
        if item['active'] and item['required_authorization'] and not db.execute('SELECT 1 FROM authorizations WHERE authorization_uuid=? AND active=1',(item['required_authorization'],)).fetchone():
            raise ValueError('Réactivez l’habilitation requise avant de restaurer cette ressource.')
        db.execute('UPDATE resources SET archived_at=NULL,updated_at=? WHERE resource_uuid=?',(now(),key))
    elif action=='delete':
        if confirmation!=key:raise ValueError('Confirmez explicitement la suppression définitive.')
        if dependencies(db,key):raise ValueError('Suppression impossible : historique ou données associées. Utilisez l’archivage pour les conserver.')
        db.execute('DELETE FROM resources WHERE resource_uuid=?',(key,))
    else:raise ValueError('Action sur la ressource inconnue.')
    audit(db,'resource',key,action,role)
    if action!='delete':
        from machine_maintenance import history
        history(db,key,key,action,role,item,resource(db,key))
