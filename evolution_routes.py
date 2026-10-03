"""Local 2.7 UI extensions; two roles, additive routes and explicit CSRF."""
import hmac
import hashlib
import io
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, session, url_for
from evolution_schema import categories, default_category, save_category, remove_category, sync_legacy_machines, audit, now
from evolution_users import create_user, creation_message, SOURCES
import resource_booking as resources
import welcome_mail


def csrf_token():
    session.setdefault('evolution_csrf', secrets.token_urlsafe(32))
    return session['evolution_csrf']


def require_csrf():
    value = request.form.get('evolution_csrf', '')
    if not session.get('evolution_csrf') or not hmac.compare_digest(value, session['evolution_csrf']):
        abort(400, 'Confirmation de formulaire expirée. Rechargez la page.')


def actor():
    return session.get('access_role') or ('admin' if session.get('admin_authenticated') else None)


def require_team(admin=False):
    role = actor()
    if role not in ({'admin'} if admin else {'admin','moderator'}):
        abort(403)
    return role


def after_creation(a, database, user_id, send_email):
    user = database.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    message = creation_message(database,user)
    if message and a.load_modules(database)['discord']:
        settings = a.load_discord_settings(database)
        webhook = a.read_discord_webhook()
        if settings['enabled'] and webhook:
            # Use the existing protected delivery path, with no custom JSON logs.
            try:
                a.send_discord_plain(webhook,message,settings['bot_name'])
            except (OSError,ValueError):
                flash('Compte créé ; notification Discord momentanément indisponible.', 'error')
    if send_email:
        if welcome_mail.send_welcome(database,current_app.config['DATABASE'],user):
            flash('E-mail de bienvenue envoyé.', 'success')
        else:
            flash('Compte conservé ; l’e-mail de bienvenue n’a pas pu être envoyé. Vérifiez SMTP.', 'error')


def register(application, api):
    a = SimpleNamespace(**api)
    bp = Blueprint('evolution', __name__)

    @application.before_request
    def protect_user_forms():
        if request.method=='POST' and request.endpoint in {'admin_add_user','admin_edit_user'}:
            require_csrf()

    @application.context_processor
    def evolution_context():
        db = a.get_database()
        colors = {row['category_key']:row['color'] for row in categories(db,True)}
        return {'evolution_csrf':csrf_token(), 'category_colors':colors,
                'creation_sources':SOURCES, 'self_enrollment_enabled':a.read_setting(db,'self_enrollment_enabled','0')=='1',
                'welcome_default':a.read_setting(db,'welcome_default','0')=='1',
                'smtp_ready':bool(welcome_mail.load_config(application.config['DATABASE']))}

    @bp.route('/admin/reglages/usagers', methods=['GET','POST'])
    def users_settings():
        role = require_team(True)
        db = a.get_database()
        if request.method=='POST':
            require_csrf()
            try:
                with db:
                    if request.form.get('action')=='category':
                        key=save_category(db,request.form.get('name',''),request.form.get('color','#16849c'),
                                          request.form.get('active')=='1',request.form.get('default')=='1',
                                          request.form.get('key') or None, int(request.form.get('order','0')))
                        audit(db,'category',key,'saved',role)
                    elif request.form.get('action')=='remove_category':
                        if request.form.get('confirmation')!='SUPPRIMER':
                            raise ValueError('Saisissez SUPPRIMER pour confirmer.')
                        key=request.form.get('key')
                        action=remove_category(db,key,request.form.get('replacement') or None)
                        audit(db,'category',key,action,role)
                    elif request.form.get('action')=='preferences':
                        for key in ('self_enrollment_enabled','welcome_default'):
                            a.write_setting(db,key,'1' if request.form.get(key)=='1' else '0')
                        subject,body=request.form.get('welcome_subject',''),request.form.get('welcome_body','')
                        welcome_mail.validate_template(subject,body)
                        a.write_setting(db,'welcome_subject',subject);a.write_setting(db,'welcome_body',body)
                    else:
                        raise ValueError('Action inconnue.')
                flash('Réglages enregistrés.', 'success')
            except (ValueError,sqlite3.IntegrityError) as error:
                db.rollback();flash('Réglages refusés : ' + (str(error) if isinstance(error,ValueError) else 'nom déjà utilisé.'),'error')
            return redirect(url_for('evolution.users_settings'))
        return render_template('evolution_users_settings.html', entries=categories(db,True),
            enrollment=a.read_setting(db,'self_enrollment_enabled','0')=='1',
            welcome_subject=a.read_setting(db,'welcome_subject',welcome_mail.SUBJECT),
            welcome_body=a.read_setting(db,'welcome_body',welcome_mail.BODY))

    @bp.route('/admin/reglages/integrations', methods=['GET','POST'])
    def integrations():
        require_team(True)
        db=a.get_database()
        config=welcome_mail.load_config(application.config['DATABASE'])
        if request.method=='POST':
            require_csrf()
            try:
                action=request.form.get('action')
                if action=='smtp':
                    proposed={k:request.form.get(k,'') for k in ('host','port','security','username','sender_name','sender_email','reply_to')}
                    proposed['password']=request.form.get('password') or config.get('password','')
                    welcome_mail.save_config(application.config['DATABASE'],proposed)
                elif action=='test':
                    values={'structure_name':'Atelier Exemple','first_name':'Camille','last_name':'Exemple',
                            'public_id':'9876','contact':'contact@example.invalid','website':'https://example.invalid'}
                    message=welcome_mail.build_message(config,request.form.get('recipient'),values,'[TEST] ' + welcome_mail.SUBJECT)
                    welcome_mail.send(config,message)
                elif action=='discord':
                    with db:
                        for key in ('enabled','first_name','last_name','last_initial','age','category','source','time'):
                            a.write_setting(db,'discord_new_user_' + key, '1' if request.form.get(key)=='1' else '0')
                else:
                    raise ValueError('Action inconnue.')
                flash('Réglages/envoi validés.', 'success')
            except (OSError,ValueError,welcome_mail.smtplib.SMTPException):
                flash('Échec : vérifiez les paramètres ou la connexion SMTP. Aucun secret affiché.', 'error')
            return redirect(url_for('admin_notifications')+'#new-user-notifications' if action=='discord' else url_for('admin_settings_structure')+'#smtp')
        return redirect(url_for('admin_settings_structure')+'#smtp')

    @bp.post('/admin/usagers/<int:user_id>/bienvenue')
    def resend_welcome(user_id):
        require_team();require_csrf()
        if request.form.get('confirmation')!='ENVOYER':
            abort(400)
        db=a.get_database()
        if not db.execute('SELECT 1 FROM users WHERE id=?', (user_id,)).fetchone():
            abort(404)
        after_creation_email=welcome_mail.send_welcome(db,application.config['DATABASE'],db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone())
        flash('E-mail envoyé.' if after_creation_email else 'E-mail non envoyé ; fiche conservée.', 'success' if after_creation_email else 'error')
        return redirect(url_for('admin_edit_user',user_id=user_id))

    @bp.route('/inscription', methods=['GET','POST'])
    def enroll():
        db=a.get_database()
        if not a.load_modules(db)['users'] or a.read_setting(db,'self_enrollment_enabled','0')!='1':
            abort(404)
        # Entering this path explicitly locks the tablet. No moderator session
        # survives the public enrollment, including a bookmarked admin page.
        session.pop('access_role',None);session.pop('admin_authenticated',None)
        blank={'public_id':a.next_available_public_id(db),'first_name':'','last_name':'','active':1,
               'category':default_category(db),'phone_country_code':'+33'}
        if request.method=='GET':
            session['enrollment_started']=time.time()
            return render_template('user_form.html',user=blank,form_mode='create',kiosk=True,errors=[],duplicate_users=[],country_names=a.COUNTRY_NAMES)
        require_csrf()
        if time.time()-session.get('enrollment_started',0)>900:
            abort(400,'Formulaire expiré. Revenez à l’accueil.')
        ip=request.remote_addr or 'unknown'
        bucket=hmac.new(application.secret_key.encode(),ip.encode(),hashlib.sha256).hexdigest()
        since=(datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat()
        import json
        details=json.dumps({'bucket':bucket})
        count=db.execute("SELECT COUNT(*) FROM security_events WHERE event_type='enrollment_attempt' AND created_at>? AND details_json=?",(since,details)).fetchone()[0]
        if count>=5:
            abort(429,'Trop de tentatives. Réessayez dans quelques minutes.')
        db.execute('INSERT INTO security_events(event_type,created_at,details_json) VALUES(?,?,?)',('enrollment_attempt',now(),details));db.commit()
        values=dict(request.form)
        values.update(public_id=a.next_available_public_id(db),category=default_category(db),active='1')
        user,errors=a.validate_user_form(values,db,public_enrollment=True)
        if errors:
            return render_template('user_form.html',user=user,form_mode='create',kiosk=True,errors=errors,duplicate_users=[],country_names=a.COUNTRY_NAMES),400
        try:
            db.execute('BEGIN IMMEDIATE')
            # Allocate ID again under lock, not from an old tablet form.
            user['public_id']=a.next_available_public_id(db)
            user_id=create_user(db,user,'kiosk')
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback();abort(409,'L’identifiant vient d’être utilisé. Réessayez.')
        after_creation(a,db,user_id,request.form.get('send_welcome')=='1')
        session['enrollment_receipt']={'id':user_id,'until':time.time()+120}
        session.pop('enrollment_started',None)
        return redirect(url_for('evolution.enrollment_done'))

    def receipt_user():
        receipt=session.get('enrollment_receipt',{})
        if receipt.get('until',0)<time.time():
            session.pop('enrollment_receipt',None);abort(404)
        user=a.get_database().execute('SELECT * FROM users WHERE id=?',(receipt['id'],)).fetchone()
        if not user:
            abort(404)
        return user

    @bp.get('/inscription/terminee')
    def enrollment_done():
        response=application.make_response(render_template('enrollment_done.html',user=receipt_user()))
        response.headers['Cache-Control']='private, no-store'
        response.headers['Referrer-Policy']='no-referrer'
        return response

    @bp.get('/inscription/qr.png')
    def enrollment_qr():
        response=send_file(io.BytesIO(welcome_mail.qr_png(receipt_user()['public_id'])),mimetype='image/png')
        response.headers['Cache-Control']='private, no-store'
        return response

    @bp.route('/admin/ressources', methods=['GET','POST'])
    def resource_directory():
        role=require_team();db=a.get_database()
        sync_legacy_machines(db);db.commit()
        if request.method=='POST':
            require_csrf()
            try:
                with db:
                    action=request.form.get('action')
                    if action=='type':
                        require_team(True)
                        resources.save_type(db,request.form.get('name',''),request.form.get('color','#16849c'),
                                            request.form.get('active')=='1',request.form.get('key') or None,int(request.form.get('order','0')))
                    elif action=='resource':
                        require_team(True)
                        if request.form.get('required_authorization') and not a.load_modules(db)['authorizations']:
                            raise ValueError('Activez Formations et habilitations avant d’exiger une habilitation.')
                        resources.save_resource(db,{k:request.form.get(k) for k in ('name','description','type_key','color','active','approval_required','price_cents','required_authorization')},role,request.form.get('key') or None)
                    else:
                        raise ValueError('Action inconnue.')
                flash('Ressource enregistrée.', 'success')
            except (ValueError,sqlite3.IntegrityError) as error:
                db.rollback();flash(str(error) if isinstance(error,ValueError) else 'Nom déjà utilisé ou référence invalide.','error')
            return redirect(url_for('evolution.resource_directory'))
        return render_template('resources.html',resource_types=db.execute('SELECT * FROM resource_types ORDER BY sort_order,name').fetchall(),
            resources=db.execute('SELECT r.*, t.name AS type_name,COALESCE(r.color,t.color) AS display_color FROM resources r JOIN resource_types t USING(type_key) ORDER BY r.name').fetchall(),
            authorizations=db.execute('SELECT * FROM authorizations WHERE active=1 ORDER BY name').fetchall())

    @bp.route('/admin/ressources/reservations', methods=['GET','POST'])
    def resource_bookings():
        role=require_team();db=a.get_database()
        if request.method=='POST':
            require_csrf()
            try:
                db.execute('BEGIN IMMEDIATE')
                action=request.form.get('action')
                if action=='book':
                    zone=ZoneInfo(a.read_setting(db,'structure_timezone','Europe/Paris'))
                    start=datetime.fromisoformat(request.form.get('starts_at','')).replace(tzinfo=zone).isoformat()
                    end=datetime.fromisoformat(request.form.get('ends_at','')).replace(tzinfo=zone).isoformat()
                    for raw in (start,end):
                        local=datetime.fromisoformat(raw)
                        if local.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)!=local.replace(tzinfo=None):
                            raise ValueError('Cet horaire local n’existe pas lors du changement d’heure.')
                        if local.replace(fold=0).utcoffset()!=local.replace(fold=1).utcoffset():
                            raise ValueError('Cet horaire local est ambigu lors du changement d’heure ; choisissez une plage sans ambiguïté.')
                    key=resources.book(db,request.form.get('resource_uuid'),int(request.form.get('user_id','')),start,end,role,request.form.get('override_reason',''))
                elif action=='transition':
                    key=request.form.get('booking_uuid')
                    resources.transition(db,key,request.form.get('status'),role)
                elif action=='billing':
                    key=request.form.get('booking_uuid')
                    resources.link_billing(db,key,int(request.form.get('record_id','')),role)
                else:
                    raise ValueError('Action inconnue.')
                db.commit();flash('Réservation enregistrée.', 'success')
            except (ValueError,sqlite3.IntegrityError) as error:
                db.rollback();flash(str(error) if isinstance(error,ValueError) else 'Référence incompatible ou dossier déjà utilisé.','error')
            return redirect(url_for('evolution.resource_bookings'))
        return render_template('resource_bookings.html',
            resources=db.execute('SELECT * FROM resources WHERE active=1 ORDER BY name').fetchall(),
            users=db.execute('SELECT id,first_name,last_name FROM users WHERE active=1 ORDER BY first_name').fetchall(),
            bookings=db.execute('SELECT b.*,r.name,u.first_name,u.last_name FROM resource_bookings b JOIN resources r USING(resource_uuid) LEFT JOIN users u ON u.id=b.user_id ORDER BY b.starts_at DESC').fetchall(),
            records=db.execute('SELECT id,quote_number,client_contact FROM billing_records WHERE id NOT IN(SELECT billing_record_id FROM resource_bookings WHERE billing_record_id IS NOT NULL) ORDER BY id DESC').fetchall(),
            statuses=resources.STATUS_LABELS,transitions=resources.TRANSITIONS)

    @bp.route('/admin/habilitations', methods=['GET','POST'])
    def authorizations():
        role=require_team();db=a.get_database()
        if request.method=='POST':
            require_csrf()
            try:
                with db:
                    action=request.form.get('action')
                    if action=='definition':
                        require_team(True)
                        name=request.form.get('name','').strip()
                        if not name or len(name)>180:
                            raise ValueError('Nom d’habilitation requis.')
                        db.execute('INSERT INTO authorizations VALUES(?,?,?,?,?)',(str(uuid4()),name,request.form.get('description','')[:2000],1,now()))
                    elif action=='grant':
                        resources.grant(db,int(request.form.get('user_id','')),request.form.get('authorization_uuid'),request.form.get('performed_on'),request.form.get('validated_by',''),role,request.form.get('expires_on') or None)
                    elif action=='revoke':
                        resources.revoke(db,request.form.get('grant_uuid'),role,request.form.get('reason',''))
                    else:
                        raise ValueError('Action inconnue.')
                flash('Historique d’habilitation enregistré.','success')
            except (ValueError,sqlite3.IntegrityError) as error:
                db.rollback();flash(str(error) if isinstance(error,ValueError) else 'Référence incompatible.','error')
            return redirect(url_for('evolution.authorizations'))
        return render_template('authorizations.html',definitions=db.execute('SELECT * FROM authorizations WHERE active=1 ORDER BY name').fetchall(),
            users=db.execute('SELECT id,first_name,last_name FROM users WHERE active=1 ORDER BY first_name').fetchall(),
            grants=db.execute('SELECT g.*,a.name,u.first_name,u.last_name FROM user_authorizations g JOIN authorizations a USING(authorization_uuid) LEFT JOIN users u ON u.id=g.user_id ORDER BY g.performed_on DESC').fetchall())

    @bp.get('/admin/calendrier')
    def calendar():
        require_team()
        from fablab_calendar import calendar_view
        return render_template('calendar.html',**calendar_view(a.get_database(),request.args,a))

    application.register_blueprint(bp)
