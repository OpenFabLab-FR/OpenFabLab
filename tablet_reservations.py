"""Private durable kiosk requests; WordPress remains the only booking authority.

The kiosk never performs a network action or promises a place. Requests live in
the existing SQLite outbox. The existing synchronizer submits them to the same
public WordPress booking service and imports its canonical reservation events.
"""
import hashlib
import hmac
import json
import re
import secrets
import time
import urllib.error
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for
from evolution_routes import require_csrf, require_team
from reservations_sync import booking_capacity_used, load_sync_secret, normalize_email, normalize_phone

STATES = {'pending':'En attente de confirmation', 'sending':'En attente de confirmation',
          'uncertain':'À vérifier par l’équipe', 'confirmed':'Confirmée',
          'waitlisted':'Liste d’attente', 'rejected':'Demande refusée', 'cancelled':'Demande annulée'}
ACTIVE = {'pending', 'sending', 'uncertain', 'confirmed', 'waitlisted'}


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def local_catalogue(database, settings, current=None):
    """Read-only local projection; availability is indicative, never a promise."""
    current = current or datetime.now(timezone.utc)
    zone = ZoneInfo(settings(database, 'structure_timezone', 'Europe/Paris'))
    result = []
    for row in database.execute('SELECT s.*,c.* FROM fablab_services s JOIN animation_reservation_config c ON c.service_id=s.id WHERE s.service_type=\'animation\' AND c.enabled=1 AND c.environment=\'production\' AND s.service_date>=? ORDER BY s.service_date,s.start_time LIMIT 100', (current.astimezone(zone).date().isoformat(),)):
        item = dict(row)
        if not row['start_time'] or not row['end_time']:
            continue
        begin = datetime.fromisoformat(row['service_date']+'T'+row['start_time']).replace(tzinfo=zone)
        finish = datetime.fromisoformat(row['service_date']+'T'+row['end_time']).replace(tzinfo=zone)
        opening = datetime.fromisoformat(row['signup_open_at'].replace('Z','+00:00')) if row['signup_open_at'] else None
        if opening and not opening.tzinfo:
            opening = opening.replace(tzinfo=zone)
        if opening and opening > current:
            continue
        item['slots'] = []
        if row['booking_mode'] == 'slots':
            for slot in database.execute('SELECT * FROM animation_slots WHERE service_id=? AND active=1 ORDER BY starts_at', (row['service_id'],)):
                start = datetime.fromisoformat(slot['starts_at']).astimezone(zone)
                if current >= start - timedelta(minutes=row['close_minutes']):
                    continue
                entry = dict(slot, label=start.strftime('%d/%m/%Y · %H:%M')+'–'+datetime.fromisoformat(slot['ends_at']).astimezone(zone).strftime('%H:%M'))
                entry['available'] = max(0,slot['capacity']-booking_capacity_used(database,row['service_id'],slot['slot_uuid']))
                item['slots'].append(entry)
            if not item['slots']:
                continue
            item['available'] = sum(s['available'] for s in item['slots'])
        else:
            if current >= begin - timedelta(minutes=row['close_minutes']):
                continue
            item['available'] = max(0,row['capacity']-booking_capacity_used(database,row['service_id']))
        item.update(date=begin.strftime('%d/%m/%Y'), hours=begin.strftime('%H:%M')+'–'+finish.strftime('%H:%M'))
        result.append(item)
    return result


def person(values, prefix=''):
    """Transport/field checks only; authoritative age/capacity rules stay in WP."""
    data = {key:str(values.get(prefix+key,'')).strip() for key in ('first_name','last_name','birth_year','email','phone','public_id')}
    for key in ('first_name','last_name'):
        if not data[key] or len(data[key].encode('utf-8')) > 80 or any(ord(c)<32 for c in data[key]):
            raise ValueError('Complétez le prénom et le nom (80 caractères maximum).')
    if not data['birth_year'].isdigit() or not 1900 <= int(data['birth_year']) <= datetime.now().year:
        raise ValueError('Renseignez une année de naissance valide.')
    data['birth_year'] = int(data['birth_year'])
    if len(data['email']) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', data['email']):
        raise ValueError('Renseignez une adresse e-mail valide.')
    if len(data['phone']) > 40 or len(re.sub(r'\D','',data['phone'])) < 8:
        raise ValueError('Renseignez un numéro de téléphone valide.')
    if data['public_id'] and not re.fullmatch(r'[0-9]{4}',data['public_id']):
        raise ValueError('L’identifiant OpenFabLab comporte quatre chiffres.')
    return data


def same_person(left, right):
    contact_matches = (normalize_email(left.get('email')) == normalize_email(right.get('email'))
                       and bool(left.get('email'))) or (bool(left.get('phone')) and
                       re.sub(r'\D','',left['phone']) == re.sub(r'\D','',right.get('phone') or ''))
    if left.get('public_id') and left.get('public_id') == right.get('public_id') and contact_matches:
        return True
    return (all(str(left.get(k,'')).strip().casefold()==str(right.get(k,'')).strip().casefold()
                for k in ('first_name','last_name','birth_year','email'))
            and re.sub(r'\D','',left.get('phone') or '') == re.sub(r'\D','',right.get('phone') or ''))


def requests_for(database, service_id=None):
    result = []
    for row in database.execute("SELECT * FROM reservation_outbox WHERE command_type='public_request' ORDER BY id"):
        payload = json.loads(row['payload_json'])
        if service_id is None or payload['request']['service_id'] == service_id:
            result.append(dict(row, payload=payload, state_label=STATES[payload['state']]))
    return result


def save_state(database, row, payload, state, diagnostic=None, done=False):
    payload['state'] = state
    encoded=json.dumps(payload,ensure_ascii=False)
    changed=database.execute('UPDATE reservation_outbox SET payload_json=?,last_error=?,sent_at=? WHERE id=? AND payload_json=?',
                     (encoded,diagnostic,timestamp() if done else None,row['id'],row['payload_json']))
    database.commit()
    if changed.rowcount != 1:
        return False
    row['payload_json']=encoded
    return True


def matching_bookings(database, data):
    rows = [dict(row) for row in database.execute("SELECT * FROM animation_bookings WHERE environment=? AND service_id=? AND COALESCE(slot_uuid,'')=? AND status IN ('confirmed','waitlisted','offer_pending','present','absent')",
            (data['environment'],data['service_id'],data.get('slot_uuid') or ''))]
    main = [b for b in rows if same_person(data,b)]
    companion = data.get('companion')
    if companion:
        main = [b for b in main if b['group_uuid'] and any(other['group_uuid']==b['group_uuid'] and other['external_uuid']!=b['external_uuid'] and same_person(companion,other) for other in rows)]
    return main


def reconcile_requests(database, environment):
    """Link receipts to canonical events, including later cancellation/expiry.

    An acknowledged POST has no UUID in protocol 2. Only events created after
    this request can link it to an inactive booking; older cancelled attempts
    must never turn a new pending request into a false confirmation.
    """
    for row in requests_for(database):
        payload = row['payload']; data = payload['request']
        if row['environment'] != environment or payload['state'] not in ACTIVE:
            continue
        if payload.get('booking_uuid'):
            booking = database.execute('SELECT * FROM animation_bookings WHERE environment=? AND external_uuid=?',
                                       (environment,payload['booking_uuid'])).fetchone()
        else:
            candidates = matching_bookings(database,data)
            booking = candidates[0] if candidates else None
            if booking is None and payload['state'] in ('sending','uncertain','confirmed','waitlisted'):
                # Canonical terminal events may already have arrived before ACK.
                for candidate in database.execute("SELECT * FROM animation_bookings WHERE environment=? AND service_id=? AND COALESCE(slot_uuid,'')=? AND status IN ('cancelled','expired') ORDER BY updated_at DESC",
                        (environment,data['service_id'],data.get('slot_uuid') or '')):
                    if candidate['created_at'] >= row['created_at'] and same_person(data,dict(candidate)) and not data.get('companion'):
                        booking=candidate;break
        if booking:
            old_uuid=payload.get('booking_uuid')
            payload['booking_uuid']=booking['external_uuid']
            state = ('cancelled' if booking['status'] in ('cancelled','expired') else
                     'waitlisted' if booking['status']=='waitlisted' else 'confirmed')
            if state != payload['state'] or old_uuid != payload['booking_uuid']:
                save_state(database,row,payload,state,done=True)


def process_requests(database, client, environment):
    """Called only by the already guarded worker, after fetching WP events.

No blind replay: a sending/uncertain request is reconciled against canonical
events, otherwise left for the team. Transport failure before this step leaves
the durable request pending. WP HTTP 409 is a business refusal, not a retry.
"""
    from runtime_policy import external_allowed
    path=database.execute('PRAGMA database_list').fetchone()[2]
    if not external_allowed(path):
        return
    reconcile_requests(database,environment)
    for row in requests_for(database):
        if row['environment'] != environment or row['sent_at'] is not None:
            continue
        payload = row['payload']; data = payload['request']
        matches = matching_bookings(database,data)
        if matches:
            payload['booking_uuid'] = matches[0]['external_uuid']
            state = 'waitlisted' if matches[0]['status']=='waitlisted' else 'confirmed'
            save_state(database,row,payload,state,done=True)
            continue
        if payload['state'] in ('sending','uncertain'):
            save_state(database,row,payload,'uncertain','Réponse non reçue : vérifier l’inscription avant toute nouvelle demande.')
            continue
        config = database.execute('SELECT enabled,environment FROM animation_reservation_config WHERE service_id=?',(data['service_id'],)).fetchone()
        if not config or not config['enabled'] or config['environment'] != environment:
            save_state(database,row,payload,'rejected','Animation indisponible.',True)
            continue
        # Persist before I/O: a crash cannot cause an automatic double submission.
        if not save_state(database,row,payload,'sending'):
            continue  # Cancelled or claimed concurrently: never submit stale data.
        database.execute('UPDATE reservation_outbox SET attempts=attempts+1 WHERE id=?',(row['id'],));database.commit()
        try:
            result = client.post('/public/reserve',data)
            if not isinstance(result,dict) or result.get('status') not in {'confirmed','waitlisted'} or result.get('count') != (2 if data.get('companion') else 1):
                raise ValueError('Réponse de réservation non vérifiable')
            save_state(database,row,payload,result['status'],done=True)
        except urllib.error.HTTPError as error:
            if error.code == 429:
                save_state(database,row,payload,'pending','Service occupé : nouvel essai au prochain cycle.')
            elif error.code in (400,403,404,409):
                save_state(database,row,payload,'rejected','Demande refusée par le service de réservation. Contactez l’équipe.',True)
            else:
                save_state(database,row,payload,'uncertain','Réponse non reçue : vérification par l’équipe nécessaire.')
        except (OSError, ValueError):
            save_state(database,row,payload,'uncertain','Réponse non reçue : vérification par l’équipe nécessaire.')


def register(application, api):
    a = SimpleNamespace(**api)
    bp = Blueprint('tablet_reservations',__name__)

    @bp.before_request
    def guard():
        if request.endpoint.endswith('cancel_request'):
            require_team();return
        database = a.get_database()
        if a.read_setting(database,'tablet_reservations_enabled','0') != '1' or not a.load_modules(database)['public_reservations']:
            abort(404)
        # Public paths always lock an existing team session, including POST.
        session.pop('access_role',None);session.pop('admin_authenticated',None)
        session.pop('pin_csrf_token',None)

    @bp.after_request
    def no_cache(response):
        response.headers['Cache-Control']='private, no-store'
        response.headers['Referrer-Policy']='no-referrer'
        return response

    def animations():
        return local_catalogue(a.get_database(),a.read_setting)

    def animation(service_id):
        item = next((item for item in animations() if item['service_id']==service_id),None)
        if item is None:
            abort(404)
        return item

    @bp.get('/animations')
    def catalogue():
        session.pop('tablet_receipt',None)
        return render_template('tablet_animations.html',animations=animations())

    @bp.get('/animations/<int:service_id>')
    def detail(service_id):
        return render_template('tablet_animation.html',animation=animation(service_id))

    @bp.route('/animations/<int:service_id>/reserver',methods=['GET','POST'])
    def reserve(service_id):
        db = a.get_database(); item = animation(service_id)
        errors=[]
        if request.method=='GET':
            session['tablet_form']={'token':secrets.token_urlsafe(32),'started':time.time(),'service_id':service_id}
        else:
            require_csrf()
            form=session.get('tablet_form',{})
            if (form.get('service_id')!=service_id or time.time()-form.get('started',0)>900
                    or not hmac.compare_digest(form.get('token',''),request.form.get('form_token',''))):
                abort(400,'Formulaire expiré. Revenez aux animations.')
            bucket=hmac.new(str(application.secret_key).encode(),(request.remote_addr or '').encode(),hashlib.sha256).hexdigest()
            since=(datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat()
            if db.execute("SELECT COUNT(*) FROM security_events WHERE event_type='tablet_request_attempt' AND created_at>? AND details_json=?",(since,json.dumps({'bucket':bucket}))).fetchone()[0]>=5:
                abort(429)
            db.execute('INSERT INTO security_events(event_type,created_at,details_json) VALUES(?,?,?)',('tablet_request_attempt',timestamp(),json.dumps({'bucket':bucket})));db.commit()
            try:
                if request.form.get('website') or request.form.get('consent')!='1':
                    raise ValueError('Acceptez l’utilisation de ces informations pour gérer votre demande.')
                if not a.read_setting(db,'reservation_wordpress_url','') or not load_sync_secret(application.config['DATABASE']):
                    raise ValueError('Le service de réservation n’est pas configuré. Adressez-vous à l’équipe.')
                data=person(request.form)
                kind=request.form.get('participant_kind')
                if kind not in ('user','visitor') or (kind=='user' and not data['public_id']) or (kind=='visitor' and data['public_id']):
                    raise ValueError('Choisissez Usager ou Visiteur et renseignez votre identifiant si nécessaire.')
                if kind=='user':
                    user=db.execute('SELECT * FROM users WHERE public_id=? AND active=1',(data['public_id'],)).fetchone()
                    if not user or not (normalize_email(user['email'])==normalize_email(data['email']) or (user['phone'] and normalize_phone(user['phone_country_code'],user['phone'])==normalize_phone('',data['phone']))):
                        raise ValueError('Identifiant ou coordonnées non concordants. Adressez-vous à l’équipe.')
                if item['audience']=='registered' and kind!='user':
                    raise ValueError('Cette animation est réservée aux usagers inscrits.')
                data.update(environment=item['environment'],service_id=service_id)
                if item['booking_mode']=='slots':
                    slot=request.form.get('slot_uuid','')
                    if not any(s['slot_uuid']==slot for s in item['slots']):
                        raise ValueError('Choisissez un créneau ouvert.')
                    data['slot_uuid']=slot
                if request.form.get('with_companion')=='1':
                    data['companion']=person(request.form,'companion_')
                db.execute('BEGIN IMMEDIATE')
                if matching_bookings(db,data) or any(row['payload']['state'] in ACTIVE and row['environment']==data['environment'] and (row['payload']['request'].get('slot_uuid') or '')==(data.get('slot_uuid') or '') and same_person(row['payload']['request'],data) for row in requests_for(db,service_id)):
                    raise ValueError('Une inscription ou une demande existe déjà pour cette personne.')
                key=str(uuid4())
                payload={'state':'pending','request':data,'title':item['title'],'date':item['date'],'hours':item['hours']}
                if item['booking_mode']=='slots':
                    payload['hours']=next(s['label'] for s in item['slots'] if s['slot_uuid']==data['slot_uuid'])
                db.execute("INSERT INTO reservation_outbox(environment,command_type,entity_key,payload_json,created_at) VALUES(?,'public_request',?,?,?)",(item['environment'],key,json.dumps(payload,ensure_ascii=False),timestamp()))
                db.commit()
                session.pop('tablet_form',None)
                session['tablet_receipt']={'key':key,'until':time.time()+900}
                return redirect(url_for('tablet_reservations.done'))
            except ValueError as error:
                db.rollback();errors.append(str(error))
        return render_template('tablet_reserve.html',animation=item,errors=errors,form_token=session.get('tablet_form',{}).get('token',''),values=request.form),400 if errors else 200

    @bp.get('/animations/demande')
    def done():
        receipt=session.get('tablet_receipt',{})
        if receipt.get('until',0)<time.time():abort(404)
        row=a.get_database().execute("SELECT payload_json FROM reservation_outbox WHERE command_type='public_request' AND entity_key=?",(receipt.get('key'),)).fetchone()
        if not row:abort(404)
        payload=json.loads(row[0])
        # Explicit allowlist: never pass participant/contact fields to this page.
        return render_template('tablet_done.html',receipt={k:payload[k] for k in ('title','date','hours')},state=payload['state'],state_label=STATES[payload['state']])

    @bp.post('/admin/animations/<int:service_id>/demandes/<key>/annuler')
    def cancel_request(service_id,key):
        require_csrf();db=a.get_database()
        row=next((row for row in requests_for(db,service_id) if row['entity_key']==key),None)
        if not row:abort(404)
        if row['payload']['state']!='pending':abort(409)
        if not save_state(db,row,row['payload'],'cancelled',done=True):
            abort(409)  # The worker may already have claimed it for transmission.
        return redirect(url_for('admin_animation_bookings',service_id=service_id))

    application.register_blueprint(bp)
