"""Machine state is independent of booking occupancy and authorizations."""
from i18n import native as __ui_native__
import json
from datetime import date,datetime,timezone
from uuid import uuid4
from family_model import setting
from evolution_schema import sync_legacy_machines
from resource_sort import ordered

STATES={'operational':__ui_native__('Disponible'),'maintenance':__ui_native__('En maintenance'),'out_of_service':__ui_native__('Hors service')}
KINDS={'care':__ui_native__('Entretien / prévention'),'preventive':__ui_native__('Maintenance préventive (historique)'),'repair':__ui_native__('Réparation'),'inspection':__ui_native__('Vérification'),'other':__ui_native__('Autre')}
FORM_KINDS={k:v for k,v in KINDS.items() if k!='preventive'}

def stamp():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def require(role):
    if role not in ('admin','moderator'):raise PermissionError('Action réservée à l’équipe.')
def enabled(db):return setting(db,'module_maintenance','0')=='1'
def calendar_date(value):
    try:return date.fromisoformat(str(value))
    except (ValueError,TypeError):raise ValueError('Choisissez une date valide.') from None
def public_visible(row):
    # The single checkbox is unchecked for legacy asymmetric permissions. Never
    # expose those rows through another public channel simply because of state.
    return row['announce'] in (True,1,'1') and row['public_listed'] in (True,1,'1')
def machine(db,key):
    row=db.execute('SELECT r.*,c.status,c.status_since,c.announce,c.public_listed,c.public_reason,c.return_estimate,c.publish_return FROM resources r LEFT JOIN machine_condition c USING(resource_uuid) WHERE r.resource_uuid=?',(key,)).fetchone()
    if not row:raise ValueError('Ressource inconnue.')
    from resource_loans import availability
    return dict(row)|{'status':row['status'] or 'operational','public_visible':public_visible(row),'availability':availability(db,key)}
def directory(db,include_archived=False):
    # Existing rentals already have a unique resources.legacy_machine_key. This
    # import reuses that bridge rather than creating a second machine directory.
    sync_legacy_machines(db)
    return ordered([machine(db,r[0]) for r in db.execute('SELECT resource_uuid FROM resources WHERE (?=1 OR archived_at IS NULL)',(int(include_archived),))])
def history(db,key,entity,action,actor,before,after):
    db.execute('INSERT INTO machine_history(resource_uuid,entity_uuid,action,actor,before_json,after_json,created_at) VALUES(?,?,?,?,?,?,?)',
        (key,entity,action,actor,json.dumps(before or {},ensure_ascii=False),json.dumps(after or {},ensure_ascii=False),stamp()))
def set_condition(db,key,values,role,actor):
    require(role);before=machine(db,key)
    if before['archived_at']:raise ValueError('Restaurez cette ressource avant de modifier son état.')
    state=values.get('status','operational');reason=str(values.get('public_reason','')).strip()
    if state not in STATES or len(reason)>500:raise ValueError('État ou motif public invalide.')
    estimate=str(values.get('return_estimate') or '').strip() or None
    if estimate:calendar_date(estimate)
    public=lambda key:int(values.get(key) in (True,1,'1'))
    announce,listed,publish_return=(before.get(k) or 0 for k in ('announce','public_listed','publish_return'))
    if values.get('visibility_controls')=='1':
        announce=listed=public('public_visible')
        publish_return=1
    elif any(k in values for k in ('announce','public_listed','publish_return')):
        announce,listed,publish_return=public('announce'),public('public_listed'),public('publish_return')
    mode=values.get('availability_mode',before['availability_mode'])
    if mode not in ('on_site','rental'):raise ValueError('Choisissez une disponibilité habituelle valide.')
    # Ended incidents remain in history, never in a future public incident.
    if state=='operational':reason='';estimate=None
    since=before.get('status_since') if before['status']==state and before.get('status_since') else stamp()
    db.execute('''INSERT INTO machine_condition VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(resource_uuid) DO UPDATE SET
        status=excluded.status,status_since=excluded.status_since,announce=excluded.announce,
        public_listed=excluded.public_listed,public_reason=excluded.public_reason,
        return_estimate=excluded.return_estimate,publish_return=excluded.publish_return,updated_at=excluded.updated_at''',
        (key,state,since,announce,listed,reason,estimate,publish_return,stamp()))
    db.execute('UPDATE resources SET availability_mode=? WHERE resource_uuid=?',(mode,key))
    history(db,key,key,'condition',actor,before,machine(db,key))
def intervention(db,key,values,role,actor,identifier=None):
    require(role);machine(db,key)
    if not identifier and machine(db,key)['archived_at']:raise ValueError('Restaurez cette ressource avant d’ajouter une intervention.')
    before=dict(db.execute('SELECT * FROM machine_interventions WHERE intervention_uuid=? AND resource_uuid=?',(identifier,key)).fetchone() or {})
    if identifier and not before:raise ValueError('Intervention inconnue.')
    if before and str(values.get('revision'))!=str(before['revision']):raise ValueError('Cette intervention a changé. Rechargez la page.')
    associated=None
    if values.get('reminder_id'):
        if before:raise ValueError('Associez le rappel lors de l’enregistrement de la nouvelle intervention.')
        associated=db.execute('SELECT * FROM machine_reminders WHERE reminder_uuid=? AND resource_uuid=?',
                              (values['reminder_id'],key)).fetchone()
        if not associated or associated['state']!='pending' or str(values.get('reminder_revision'))!=str(associated['revision']):
            raise ValueError('Ce rappel a changé ou a déjà été traité. Rechargez la page.')
    performed=str(values.get('performed_on',''));performed_date=calendar_date(performed)
    from zoneinfo import ZoneInfo
    if performed_date>datetime.now(ZoneInfo(setting(db,'structure_timezone','Europe/Paris'))).date():
        raise ValueError('Une intervention effectuée ne peut pas avoir une date future. Créez plutôt un rappel.')
    kind=values.get('kind','care');description=str(values.get('description','')).strip()
    if kind not in KINDS or not description or len(description)>8000:raise ValueError('Description et type d’intervention requis.')
    identifier=identifier or str(uuid4());now=stamp()
    db.execute('''INSERT INTO machine_interventions VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(intervention_uuid) DO UPDATE SET
        performed_on=excluded.performed_on,kind=excluded.kind,description=excluded.description,
        actor=excluded.actor,updated_at=excluded.updated_at,revision=machine_interventions.revision+1''',
        (identifier,key,performed,kind,description,actor,now,now,1))
    after=dict(db.execute('SELECT * FROM machine_interventions WHERE intervention_uuid=?',(identifier,)).fetchone())
    history(db,key,identifier,'intervention',actor,before,after)
    if associated:
        db.execute("UPDATE machine_reminders SET state='done',intervention_uuid=?,revision=revision+1,actor=?,updated_at=? WHERE reminder_uuid=?",
                   (identifier,actor,now,associated['reminder_uuid']))
        linked=dict(db.execute('SELECT * FROM machine_reminders WHERE reminder_uuid=?',(associated['reminder_uuid'],)).fetchone())
        history(db,key,associated['reminder_uuid'],'reminder',actor,dict(associated),linked)
    if values.get('remind_on'):
        reminder(db,key,dict(due_on=values['remind_on'],subject=values.get('reminder_subject') or KINDS[kind]),role,actor,intervention_id=identifier)
    return identifier
def reminder(db,key,values,role,actor,identifier=None,intervention_id=None):
    require(role);machine(db,key)
    if not identifier and machine(db,key)['archived_at']:raise ValueError('Restaurez cette ressource avant d’ajouter un rappel.')
    before=dict(db.execute('SELECT * FROM machine_reminders WHERE reminder_uuid=? AND resource_uuid=?',(identifier,key)).fetchone() or {})
    if identifier and not before:raise ValueError('Rappel inconnu.')
    if before and str(values.get('revision'))!=str(before['revision']):raise ValueError('Ce rappel a changé. Rechargez la page.')
    due=str(values.get('due_on',''));calendar_date(due)
    subject=str(values.get('subject','')).strip();state=values.get('state',before.get('state','pending')) if before else 'pending'
    if state=='pending' and machine(db,key)['archived_at']:raise ValueError('Restaurez cette ressource avant d’ajouter un rappel.')
    if not subject or len(subject)>200 or state not in ('pending','done','cancelled'):raise ValueError('Objet ou état du rappel invalide.')
    identifier=identifier or str(uuid4());now=stamp()
    db.execute('''INSERT INTO machine_reminders VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(reminder_uuid) DO UPDATE SET
        due_on=excluded.due_on,subject=excluded.subject,state=excluded.state,revision=machine_reminders.revision+1,
        actor=excluded.actor,updated_at=excluded.updated_at''',
        (identifier,key,intervention_id,due,subject,state,1,actor,now,now))
    after=dict(db.execute('SELECT * FROM machine_reminders WHERE reminder_uuid=?',(identifier,)).fetchone())
    history(db,key,identifier,'reminder',actor,before,after)
    return identifier

def reminder_action(db,key,values,role,actor):
    require(role);machine(db,key)
    prior=db.execute('SELECT * FROM machine_reminders WHERE reminder_uuid=? AND resource_uuid=?',(values.get('identifier'),key)).fetchone()
    if not prior or prior['state']!='pending' or str(prior['revision'])!=str(values.get('revision')):
        raise ValueError('Ce rappel a changé ou a déjà été traité. Rechargez la page.')
    updated=dict(prior)
    action=values.get('action')
    if action=='reminder_reschedule':updated['due_on']=values.get('due_on','')
    elif action=='reminder_cancel':updated['state']='cancelled'
    elif action=='reminder_close':updated['state']='done'
    else:raise ValueError('Action sur le rappel invalide.')
    return reminder(db,key,updated,role,actor,prior['reminder_uuid'])

def history_entries(db,key):
    labels={'condition':'État de la ressource modifié','intervention':'Intervention enregistrée','reminder':'Rappel modifié','archive':'Ressource archivée','restore':'Ressource restaurée'}
    fields={'name':'Nom','color':'Couleur','type_key':'Catégorie','active':'Réservation activée','status':'État','announce':'Annonce sur la borne','public_listed':'Catalogue WordPress',
            'public_reason':'Motif','return_estimate':'Date de retour estimée','publish_return':'Publication de la date',
            'performed_on':'Date de l’intervention','kind':'Type','description':'Intervention réalisée',
            'due_on':'Date du rappel','subject':'Objet','state':'État du rappel','intervention_uuid':'Intervention associée','availability_mode':'Disponibilité habituelle'}
    result=[]
    for row in db.execute('SELECT * FROM machine_history WHERE resource_uuid=? ORDER BY id DESC',(key,)):
        item=dict(row);before=json.loads(item['before_json']);after=json.loads(item['after_json']);changes=[]
        for field,label in fields.items():
            if field not in after or after.get(field)==before.get(field):continue
            value=after[field]
            if field=='status':value=STATES.get(value,value)
            elif field=='kind':value=KINDS.get(value,value)
            elif field=='state':value=__ui_native__({'pending':'À venir','done':'Traité','cancelled':'Annulé'}.get(value,'Non renseigné'))
            elif field in ('announce','public_listed','publish_return','active'):value=__ui_native__('Oui' if value else 'Non')
            elif field=='type_key':
                category=db.execute('SELECT name FROM resource_types WHERE type_key=?',(value,)).fetchone()
                value=category[0] if category else __ui_native__('Catégorie archivée')
            elif field=='intervention_uuid':value=__ui_native__('Associée' if value else 'Non associée')
            elif field=='availability_mode':value=__ui_native__('Disponible à la location' if value=='rental' else 'Disponible')
            changes.append(dict(label=__ui_native__(label),value=value,date=field in ('performed_on','due_on','return_estimate')))
        label=labels.get(item['action'],'Modification enregistrée')
        if item['action']=='resource':
            label='Description modifiée' if before.get('description')!=after.get('description') else 'Fiche de la ressource modifiée'
            for change in changes:
                if change['label']==__ui_native__('Intervention réalisée'):change['label']=__ui_native__('Description')
        if item['action']=='condition' and before.get('status')==after.get('status'):
            if any(before.get(k)!=after.get(k) for k in ('announce','public_listed')):label='Visibilité publique modifiée'
            else:label='Informations publiques modifiées'
        elif item['action']=='reminder':
            label='Rappel créé' if not before else ('Rappel reporté' if before.get('due_on')!=after.get('due_on') else 'Rappel modifié')
            if before and before.get('state')!=after.get('state'):label='Rappel annulé' if after.get('state')=='cancelled' else 'Rappel traité'
        elif item['action']=='intervention' and not before:label='Intervention ajoutée'
        item.update(label=__ui_native__(label),changes=changes);result.append(item)
    return result
def public_machines(db,unavailable_only=False,details=False,effective=True):
    if not enabled(db):return []
    # One checkbox, one public authorization; old asymmetric rows remain private
    # until the team explicitly confirms the shared publication choice.
    rows=db.execute('''SELECT r.resource_uuid,r.name,r.type_key,t.name AS category,c.status,c.public_reason,c.return_estimate,c.publish_return
        FROM resources r JOIN machine_condition c USING(resource_uuid) JOIN resource_types t USING(type_key)
        WHERE r.archived_at IS NULL AND c.announce=1 AND c.public_listed=1''')
    result=[]
    for r in rows:
        from resource_loans import availability
        state=availability(db,r['resource_uuid'])['status']
        if unavailable_only and state in ('operational','rental_available'):continue
        loan=state in ('loaned','overdue')
        # Older plugins receive their known generic unavailable state, with an
        # honest public reason. New peers negotiate the specific loan statuses.
        public_state=(state if effective else 'operational') if state=='rental_available' else state if effective or not loan else 'out_of_service'
        item=dict(id=r['resource_uuid'],name=r['name'],status=public_state,reason=('En prêt' if state=='loaned' else 'Retour en retard') if loan else r['public_reason'] if r['status']!='operational' else '',
                 return_estimate=r['return_estimate'] if r['publish_return'] and r['status']!='operational' else None)
        if details:item.update(category=r['category'],category_key=r['type_key'])
        result.append(item)
    return ordered(result,identity='id')
def technically_available(db,key):
    if machine(db,key)['archived_at']:return False
    from resource_loans import outstanding
    if outstanding(db,key):return False
    if not enabled(db):return True
    row=db.execute('SELECT status FROM machine_condition WHERE resource_uuid=?',(key,)).fetchone()
    return not row or row[0]=='operational'
