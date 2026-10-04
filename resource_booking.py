"""FabLab resources, booking states and training/authorization history."""
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from uuid import uuid4
from evolution_schema import audit, now, reorder, ordered_keys

STATUS_LABELS = {'requested':'En attente de validation', 'confirmed':'Confirmée',
                 'performed':'Effectuée', 'refused':'Refusée', 'cancelled':'Annulée'}
TRANSITIONS = {'requested':{'confirmed','refused','cancelled'}, 'confirmed':{'performed','cancelled'},
               'performed':set(), 'refused':set(), 'cancelled':set()}


def save_type(database, name, color, active=True, key=None, order=None):
    name = str(name).strip()
    if not name or len(name)>80 or not re.fullmatch(r'#[a-fA-F0-9]{6}', color):
        raise ValueError('Nom et couleur de catégorie requis.')
    if order is not None and (not isinstance(order,int) or not 0<=order<=100000):
        raise ValueError('Ordre de catégorie invalide.')
    if order is None:
        old = database.execute('SELECT sort_order FROM resource_types WHERE type_key=?', (key,)).fetchone()
        order = old[0] if old else database.execute('SELECT COALESCE(MAX(sort_order),-1)+1 FROM resource_types').fetchone()[0]
    key = key or 'type_' + uuid4().hex
    database.execute('INSERT INTO resource_types VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(type_key) DO UPDATE SET name=excluded.name,normalized_name=excluded.normalized_name,color=excluded.color,active=excluded.active,sort_order=excluded.sort_order,updated_at=excluded.updated_at',
                     (key,name,name.casefold(),color,int(active),order,now(),now()))
    reorder(database, 'resource_types')
    return key


def euros_to_cents(value):
    text = str(value).strip().replace(',', '.')
    if not re.fullmatch(r'\d+(?:\.\d{1,2})?', text):
        raise ValueError('Tarif en euros invalide (deux décimales maximum).')
    try:
        amount = Decimal(text) * 100
        if amount > 100000000:
            raise ValueError('Tarif trop élevé.')
        return int(amount)
    except InvalidOperation:
        raise ValueError('Tarif en euros invalide.') from None


def definitions(database, include_hidden=False):
    rows = {r['authorization_uuid']: dict(r) for r in database.execute('SELECT * FROM authorizations')}
    return [rows[k] for k in ordered_keys(database, 'authorizations') if include_hidden or rows[k]['active']]


def save_definition(database, name, description, role, key=None):
    if role != 'admin':
        raise ValueError('Gestion des habilitations réservée à l’Administrateur.')
    name = str(name).strip()
    if not name or len(name) > 180 or len(description) > 2000:
        raise ValueError('Nom requis (180 caractères maximum) et description limitée à 2000 caractères.')
    if key and not database.execute('SELECT 1 FROM authorizations WHERE authorization_uuid=?', (key,)).fetchone():
        raise ValueError('Habilitation inconnue.')
    if key:
        database.execute('UPDATE authorizations SET name=?,description=? WHERE authorization_uuid=?', (name, description, key))
    else:
        key = str(uuid4())
        database.execute('INSERT INTO authorizations VALUES(?,?,?,?,?)', (key, name, description, 1, now()))
    reorder(database, 'authorizations')
    audit(database, 'authorization_definition', key, 'saved', role)
    return key


def definition_usage(database, key):
    history = database.execute('SELECT COUNT(*) FROM user_authorizations WHERE authorization_uuid=?', (key,)).fetchone()[0]
    resources = database.execute('SELECT COUNT(*),COALESCE(SUM(active),0) FROM resources WHERE required_authorization=?', (key,)).fetchone()
    return history, resources[0], resources[1]


def change_definition(database, key, action, role):
    if role != 'admin' or action not in {'archive', 'reactivate', 'delete'}:
        raise ValueError('Action Administrateur requise.')
    if not database.execute('SELECT 1 FROM authorizations WHERE authorization_uuid=?', (key,)).fetchone():
        raise ValueError('Habilitation inconnue.')
    history, dependencies, active_resources = definition_usage(database, key)
    if action == 'delete' and (history or dependencies):
        raise ValueError('Suppression impossible : formations ou ressources associées. Conservez l’historique en archivant.')
    if action == 'archive' and active_resources:
        raise ValueError('Une ressource active exige cette habilitation. Modifiez sa configuration avant archivage.')
    if action == 'delete':
        database.execute('DELETE FROM authorizations WHERE authorization_uuid=?', (key,))
    else:
        database.execute('UPDATE authorizations SET active=? WHERE authorization_uuid=?', (int(action == 'reactivate'), key))
    reorder(database, 'authorizations')
    audit(database, 'authorization_definition', key, action, role)


def grants_for_user(database, user_id=None):
    from datetime import date
    query = '''SELECT g.*,a.name,u.first_name,u.last_name,
        (SELECT actor_role FROM evolution_audit e WHERE e.entity_type='authorization'
         AND e.entity_key=g.grant_uuid AND e.action='revoked' ORDER BY e.id DESC LIMIT 1) AS revoked_by
        FROM user_authorizations g JOIN authorizations a USING(authorization_uuid)
        LEFT JOIN users u ON u.id=g.user_id'''
    rows = database.execute(query + (' WHERE g.user_id=?' if user_id is not None else '') + ' ORDER BY g.performed_on DESC,g.created_at DESC', (user_id,) if user_id is not None else ()).fetchall()
    today = date.today().isoformat()
    result = []
    for row in rows:
        value = dict(row)
        value['state'] = ('Révoquée' if row['revoked_at'] else 'Expirée' if row['expires_on'] and row['expires_on'] < today else 'À venir' if row['performed_on'] > today else 'Permanente' if not row['expires_on'] else 'Valide')
        result.append(value)
    return result


def save_resource(database, values, role, key=None):
    if role!='admin':
        raise ValueError('Gestion des ressources réservée à l’Administrateur.')
    name = str(values.get('name') or '').strip()
    type_key = values.get('type_key')
    existing = database.execute('SELECT type_key,required_authorization FROM resources WHERE resource_uuid=?', (key,)).fetchone() if key else None
    type_row = database.execute('SELECT active FROM resource_types WHERE type_key=?', (type_key,)).fetchone()
    if not name or len(name)>180 or not type_row or (not type_row['active'] and (not existing or existing['type_key']!=type_key)):
        raise ValueError('Nom et catégorie active de ressource requis.')
    color = str(values.get('color') or '').strip() or None
    if color and not re.fullmatch(r'#[a-fA-F0-9]{6}', color):
        raise ValueError('Couleur de ressource invalide.')
    amount = int(values.get('price_cents') or 0)
    if not 0<=amount<=100000000:
        raise ValueError('Tarif de réservation invalide.')
    requirement = values.get('required_authorization') or None
    if requirement:
        authorization = database.execute('SELECT active FROM authorizations WHERE authorization_uuid=?', (requirement,)).fetchone()
        retaining_archived = (existing and existing['required_authorization'] == requirement
                              and values.get('active') not in (True, 1, '1'))
        if not authorization or (not authorization['active'] and not retaining_archived):
            raise ValueError('Habilitation active requise pour une ressource disponible.')
    key = key or str(uuid4())
    database.execute('INSERT INTO resources(resource_uuid,type_key,name,description,active,color,approval_required,price_cents,required_authorization,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(resource_uuid) DO UPDATE SET type_key=excluded.type_key,name=excluded.name,description=excluded.description,active=excluded.active,color=excluded.color,approval_required=excluded.approval_required,price_cents=excluded.price_cents,required_authorization=excluded.required_authorization,updated_at=excluded.updated_at',
                     (key,type_key,name,str(values.get('description') or '')[:2000],int(values.get('active') in (True,1,'1')),color,
                      int(values.get('approval_required') in (True,1,'1')),amount,requirement,now(),now()))
    audit(database,'resource',key,'saved',role)
    return key


def grant(database, user_id, authorization, performed_on, validated_by, role, expires_on=None):
    if role not in {'admin','moderator'}:
        raise ValueError('Validation réservée à l’équipe.')
    performed = datetime.strptime(performed_on,'%Y-%m-%d').date()
    if expires_on and datetime.strptime(expires_on,'%Y-%m-%d').date()<performed:
        raise ValueError('L’expiration ne peut précéder la formation.')
    if not str(validated_by).strip() or len(validated_by)>160:
        raise ValueError('Renseignez qui a validé la formation.')
    if not database.execute('SELECT 1 FROM users WHERE id=? AND active=1', (user_id,)).fetchone():
        raise ValueError('Usager actif requis.')
    if not database.execute('SELECT 1 FROM authorizations WHERE authorization_uuid=? AND active=1', (authorization,)).fetchone():
        raise ValueError('Habilitation active requise.')
    key = str(uuid4())
    database.execute('INSERT INTO user_authorizations VALUES(?,?,?,?,?,?,?,?,?,?)',
                     (key,user_id,authorization,performed_on,validated_by.strip(),role,expires_on or None,None,None,now()))
    audit(database,'authorization',key,'validated',role)
    return key


def revoke(database, grant_uuid, role, reason):
    if role not in {'admin','moderator'}:
        raise ValueError('Révocation réservée à l’équipe.')
    if not str(reason).strip():
        raise ValueError('Un motif de révocation est nécessaire.')
    row = database.execute('SELECT * FROM user_authorizations WHERE grant_uuid=?', (grant_uuid,)).fetchone()
    if not row or row['revoked_at']:
        raise ValueError('Habilitation inconnue ou déjà révoquée.')
    database.execute('UPDATE user_authorizations SET revoked_at=?,revoked_reason=? WHERE grant_uuid=?', (now(),str(reason)[:500],grant_uuid))
    audit(database,'authorization',grant_uuid,'revoked',role)


def authorization_valid(database, user_id, requirement, starts_at, ends_at=None):
    if not requirement:
        return True
    day = str(starts_at)[:10]
    end_day = str(ends_at or starts_at)[:10]
    return bool(database.execute('SELECT 1 FROM user_authorizations WHERE user_id=? AND authorization_uuid=? AND revoked_at IS NULL AND performed_on<=? AND (expires_on IS NULL OR expires_on>=?) LIMIT 1', (user_id,requirement,day,end_day)).fetchone())


def validate_booking(database, resource, user_id, start, end, role, override='', exclude=None):
    if role not in {'admin','moderator'}:
        raise ValueError('Réservation réservée à l’équipe.')
    if not resource or not resource['active']:
        raise ValueError('Ressource indisponible.')
    if not database.execute('SELECT 1 FROM users WHERE id=? AND active=1', (user_id,)).fetchone():
        raise ValueError('Usager actif requis.')
    a, b = datetime.fromisoformat(start), datetime.fromisoformat(end)
    if a.tzinfo is None or b.tzinfo is None or b<=a or b-a>__import__('datetime').timedelta(days=366):
        raise ValueError('Plage horaire invalide ; début et fin explicites requis.')
    start, end = a.astimezone(timezone.utc).isoformat(), b.astimezone(timezone.utc).isoformat()
    # ISO datetimes are normalized UTC before comparisons, no offset-string races.
    overlap = database.execute("SELECT 1 FROM resource_bookings WHERE resource_uuid=? AND status IN('requested','confirmed') AND starts_at<? AND ends_at>? AND (? IS NULL OR booking_uuid!=?) LIMIT 1", (resource['resource_uuid'],end,start,exclude,exclude)).fetchone()
    if overlap:
        raise ValueError('Cette ressource est déjà demandée ou réservée sur cette plage.')
    from zoneinfo import ZoneInfo
    setting=database.execute("SELECT value FROM app_settings WHERE key='structure_timezone'").fetchone()
    zone=ZoneInfo(setting[0] if setting else 'Europe/Paris')
    if not authorization_valid(database,user_id,resource['required_authorization'],a.astimezone(zone).isoformat(),b.astimezone(zone).isoformat()):
        if role!='admin' or not str(override).strip():
            raise ValueError('Habilitation manquante, expirée ou révoquée. Une dérogation Administrateur motivée est nécessaire.')
    return start, end


def book(database, resource_uuid, user_id, start, end, role, override=''):
    resource = database.execute('SELECT * FROM resources WHERE resource_uuid=?', (resource_uuid,)).fetchone()
    start, end = validate_booking(database,resource,user_id,start,end,role,override)
    key = str(uuid4())
    state = 'requested' if resource['approval_required'] else 'confirmed'
    database.execute('INSERT INTO resource_bookings(booking_uuid,resource_uuid,user_id,starts_at,ends_at,status,amount_cents,override_reason,created_by_role,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                     (key,resource_uuid,user_id,start,end,state,resource['price_cents'],str(override).strip() or None,role,now(),now()))
    audit(database,'resource_booking',key,state,role,{'override':bool(str(override).strip())})
    return key


def transition(database, key, state, role):
    if role not in {'admin','moderator'}:
        raise ValueError('Modification réservée à l’équipe.')
    row = database.execute('SELECT * FROM resource_bookings WHERE booking_uuid=?', (key,)).fetchone()
    if not row or state not in TRANSITIONS[row['status']]:
        raise ValueError('Transition de réservation refusée.')
    if state=='confirmed':
        resource = database.execute('SELECT * FROM resources WHERE resource_uuid=?', (row['resource_uuid'],)).fetchone()
        validate_booking(database,resource,row['user_id'],row['starts_at'],row['ends_at'],role,row['override_reason'] if role=='admin' else '',key)
    database.execute('UPDATE resource_bookings SET status=?,updated_at=? WHERE booking_uuid=?', (state,now(),key))
    audit(database,'resource_booking',key,state,role)


def link_billing(database, key, record_id, role):
    if role!='admin':
        raise ValueError('Lien de facturation réservé à l’Administrateur.')
    booking = database.execute('SELECT * FROM resource_bookings WHERE booking_uuid=?', (key,)).fetchone()
    record = database.execute('SELECT * FROM billing_records WHERE id=?', (record_id,)).fetchone()
    if not booking or not record or booking['billing_record_id']:
        raise ValueError('Dossier inconnu ou réservation déjà facturée.')
    database.execute('UPDATE resource_bookings SET billing_record_id=?,service_id=?,updated_at=? WHERE booking_uuid=?', (record_id,record['service_id'],now(),key))
    audit(database,'resource_booking',key,'billing_linked',role,{'record_id':record_id})
