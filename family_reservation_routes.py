"""Progressive, non-JavaScript kiosk flow and signed optional WordPress gateway."""
import hashlib
import hmac
import json
import re
import secrets
import time
from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for
from evolution_routes import require_csrf
import family_reservations as engine
import family_model as family
import family_waitlist as waiting


def identity(db, token, owner):
    """Returned only after verification; no contacts or identifiers in choices."""
    return {'token':token, 'contact_required':waiting.contact(db,owner) is None,
            'phone_required':family.setting(db,'reservation_phone_required','0')=='1',
            'participants':[{'key':hmac.new(token.encode(),str(u['id']).encode(),hashlib.sha256).hexdigest(),
                'name':u['first_name']+' '+u['last_name'],'label':u['label']} for u in engine.choices(db,owner)]}


def kiosk(application,a,service_id):
    from tablet_reservations import local_catalogue
    db=a.get_database()
    if a.read_setting(db,'tablet_reservations_enabled','0')!='1' or not a.load_modules(db)['public_reservations']:
        abort(404)
    for key in ('access_role','admin_authenticated','pin_csrf_token'):
        session.pop(key,None)
    item=next((i for i in local_catalogue(db,a.read_setting) if i['service_id']==service_id),None)
    if not item:
        abort(404)
    errors=[];stage='identify';people=[];selected=[]
    grant=session.get('family_booking',{})
    if request.method=='GET':
        grant={};session.pop('family_booking',None)
    else:
        require_csrf()
        try:
            action=request.form.get('step')
            if action=='identify':
                token,owner=engine.identify(db,service_id,request.form.get('public_id'),request.form.get('contact',''),
                    hmac.new(str(application.secret_key).encode(),(request.remote_addr or '').encode(),hashlib.sha256).hexdigest())
                grant={'token':token,'id':owner,'service_id':service_id,'until':time.time()+900,'nonce':secrets.token_urlsafe(32)}
                session['family_booking']=grant
                stage='contact' if waiting.contact(db,owner) is None else 'select'
            else:
                owner=engine.grant(db,grant.get('token',''),service_id,'production')
                stage='select'
                if action=='contact':
                    stage='contact'
                    waiting.complete_contact(db,owner,request.form.get('email','').strip(),request.form.get('phone'))
                    stage='select'
                elif waiting.contact(db,owner) is None:
                    stage='contact'
                    raise ValueError('Complétez les coordonnées nécessaires avant de choisir les participants.')
                if action=='contact':
                    action='contact_completed'
                slot=request.form.get('slot_uuid') if action=='select' else grant.get('slot_uuid')
                selected=request.form.getlist('person_ids') if action=='select' else grant.get('person_ids',[])
                if action!='contact_completed':
                    effective=engine.effective_service(db,service_id,slot)
                    people=engine.participants(db,owner,selected,effective)
                if action=='select':
                    grant.update(person_ids=[u['id'] for u in people],slot_uuid=slot)
                    session['family_booking']=grant;stage='confirm'
                elif action=='confirm':
                    if not hmac.compare_digest(request.form.get('nonce',''),grant['nonce']) or request.form.get('consent')!='1':
                        raise ValueError('Confirmez le récapitulatif et le consentement.')
                    receipt=engine.reserve(db,owner,selected,service_id,slot,grant['nonce'])
                    session['family_receipt']=dict(receipt,until=time.time()+900,title=item['title'])
                    session.pop('family_booking',None)
                    return redirect(url_for('family_gateway.receipt'))
                elif action!='contact_completed':
                    raise ValueError('Étape inconnue.')
        except ValueError as error:
            db.rollback();errors.append(str(error))
    choices=engine.choices(db,grant['id']) if grant.get('until',0)>time.time() else []
    response=application.make_response(render_template('family_booking.html',animation=item,stage=stage,errors=errors,
        choices=choices,people=people,selected=selected,grant=grant,
        phone_required=family.setting(db,'reservation_phone_required','0')=='1'))
    response.headers['Cache-Control']='private, no-store';response.headers['Referrer-Policy']='no-referrer'
    return response


def register(application,a):
    bp=Blueprint('family_gateway',__name__)

    @application.after_request
    def refresh_waitlist_after_team_change(response):
        # Service edits, capacity increases and historical cancellations also
        # release places. Never send network mail inside the HTTP request.
        if (request.method=='POST' and response.status_code<400 and
                request.path.startswith('/admin/') and session.get('access_role') in ('admin','moderator')):
            db=a.get_database()
            if not db.in_transaction:
                try:
                    waiting.process_due(db)
                except Exception as error:
                    # The business change is already committed. A later native
                    # cycle retries maintenance; never report a false rollback.
                    application.logger.warning('Reservation maintenance: %s',type(error).__name__)
        return response

    @bp.route('/animations/demande/<token>',methods=['GET','POST'])
    def response_link(token):
        db=a.get_database()
        waiting.process_due(db)
        errors=[]
        try:
            group=waiting.lookup(db,token)
        except ValueError:
            abort(404)
        if request.method=='POST':
            require_csrf()
            try:
                waiting.respond(db,token,request.form.get('action'))
                return redirect(url_for('family_gateway.response_link',token=token))
            except ValueError as error:
                errors.append(str(error));group=waiting.lookup(db,token)
        group['label']=waiting.LABELS.get(group['status'],'Indisponible')
        service=dict(db.execute('SELECT title,service_date,start_time,end_time FROM fablab_services WHERE id=?',(group['service_id'],)).fetchone())
        if group['slot_uuid']:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            slot=db.execute('SELECT starts_at,ends_at FROM animation_slots WHERE slot_uuid=?',(group['slot_uuid'],)).fetchone()
            if slot:
                zone=ZoneInfo(family.setting(db,'structure_timezone','Europe/Paris'))
                start=datetime.fromisoformat(slot['starts_at']).astimezone(zone)
                end=datetime.fromisoformat(slot['ends_at']).astimezone(zone)
                service.update(service_date=start.date().isoformat(),start_time=start.strftime('%H:%M'),end_time=end.strftime('%H:%M'))
        people=db.execute("SELECT first_name,last_name FROM animation_bookings WHERE group_uuid=? AND (status NOT IN('cancelled','expired','declined') OR status=?) ORDER BY rowid",(group['group_uuid'],group['status'])).fetchall()
        response=application.make_response(render_template('family_response.html',group=group,service=service,
            people=people,errors=errors,can_answer=group['status']=='offer_pending' and group['offer_token_hash']==waiting.digest(token)))
        response.headers['Cache-Control']='private, no-store'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Robots-Tag']='noindex, nofollow, noarchive'
        return response

    @bp.get('/animations/confirmation')
    def receipt():
        value=session.get('family_receipt',{})
        if value.get('until',0)<time.time():
            abort(404)
        response=application.make_response(render_template('family_receipt.html',receipt=value))
        response.headers['Cache-Control']='private, no-store'
        response.headers['Referrer-Policy']='no-referrer'
        return response

    @bp.post('/api/reservations/familles/<action>')
    def gateway(action):
        from reservations_sync import load_sync_secret
        db=a.get_database()
        if not a.load_modules(db)['public_reservations']:
            abort(404)
        secret=load_sync_secret(application.config['DATABASE'])
        stamp=request.headers.get('X-OpenFabLab-Timestamp','')
        nonce=request.headers.get('X-OpenFabLab-Nonce','')
        signature=request.headers.get('X-OpenFabLab-Signature','')
        raw=request.get_data(cache=True)
        if not request.is_secure or not secret or not stamp.isdigit() or abs(time.time()-int(stamp))>300 or not re.fullmatch(r'[A-Za-z0-9_-]{20,80}',nonce) or len(raw)>16384:
            abort(403)
        canonical='\n'.join((stamp,nonce,'POST','/api/reservations/familles/'+action,hashlib.sha256(raw).hexdigest()))
        expected=hmac.new(secret,canonical.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,signature):
            abort(403)
        with db:
            db.execute('DELETE FROM family_api_nonces WHERE expires_at<?',(int(time.time()),))
            claimed=db.execute('INSERT OR IGNORE INTO family_api_nonces VALUES(?,?)',(hashlib.sha256(nonce.encode()).hexdigest(),int(time.time())+600))
        if claimed.rowcount!=1:
            abort(409)
        data=request.get_json(silent=True)
        if not isinstance(data,dict) or data.get('environment') not in ('production','test'):
            abort(400)
        environment=data['environment']
        try:
            if action=='catalogue':
                from tablet_reservations import local_catalogue
                items=local_catalogue(db,a.read_setting,environment=environment)
                value={'animations':[{k:i[k] for k in ('service_id','title','description','date','hours','minimum_age','booking_mode','slots','available','waitlist_enabled')} for i in items]}
            elif action in ('identify','contact','reserve'):
                service_id=int(data.get('service_id',0))
                if action=='identify':
                    token,owner=engine.identify(db,service_id,data.get('public_id'),data.get('contact',''),data.get('client_bucket','wordpress'),environment)
                    value=identity(db,token,owner)
                else:
                    token=data.get('token','')
                    owner=engine.grant(db,token,service_id,environment)
                    if action=='contact':
                        waiting.complete_contact(db,owner,str(data.get('email','')).strip(),data.get('phone'))
                        value=identity(db,token,owner)
                        response=jsonify(value)
                        response.headers['Cache-Control']='private, no-store'
                        response.headers['Referrer-Policy']='no-referrer'
                        return response
                    keys={hmac.new(token.encode(),str(u['id']).encode(),hashlib.sha256).hexdigest():u['id'] for u in engine.choices(db,owner)}
                    selected=data.get('participants',[])
                    if not isinstance(selected,list) or not selected or len(selected)>20 or any(not isinstance(key,str) or key not in keys for key in selected):
                        raise ValueError('Sélection de participants invalide.')
                    if data.get('consent') is not True:
                        raise ValueError('Consentement requis.')
                    value=engine.reserve(db,owner,[keys[key] for key in selected],service_id,data.get('slot_uuid'),data.get('request_key'),environment,'wordpress')
            else:
                abort(404)
        except (ValueError,TypeError) as error:
            db.rollback();return jsonify(message=str(error)),409
        response=jsonify(value)
        response.headers['Cache-Control']='private, no-store';response.headers['Referrer-Policy']='no-referrer'
        return response
    application.register_blueprint(bp)
