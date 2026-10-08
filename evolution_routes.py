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
from evolution_schema import categories, default_category, save_category, remove_category, sync_legacy_machines, audit, now, reorder
from evolution_users import create_user, creation_message, SOURCES
import resource_booking as resources
import welcome_mail
from badge_palette import DEFAULT_REFERENCE, normalize_color, pastel_palette, validate_color
from usability import ID_MODES, enrollment_mode, attendance_reference, validate_reference, affiliation_choices


def category_palette(color):
    """Pastel background and related, accessible dark foreground."""
    palette = pastel_palette(color)
    return palette['background'], palette['ink']


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

    @application.template_filter('money')
    def money(value):
        cents = int(value)
        return str(cents // 100) + ',' + str(cents % 100).zfill(2)

    @application.before_request
    def protect_user_forms():
        if request.method=='POST' and request.endpoint in {'admin_add_user','admin_edit_user'}:
            require_csrf()

    @application.context_processor
    def evolution_context():
        db = a.get_database()
        colors = {row['category_key']:row['color'] for row in categories(db,True)}
        visitor_color = normalize_color(a.read_setting(db, 'anonymous_visitor_color', DEFAULT_REFERENCE))
        # Keys/colors are validated registry values, never CSS supplied by a user.
        styles = []
        import re
        selectors = []
        for key, color in colors.items():
            if re.fullmatch(r'[a-zA-Z0-9_-]+', key):
                selectors.append(('.category-badge.category-' + key, color))
        # A custom account category named "visitor" must remain independent.
        selectors.append(('.category-badge.anonymous-visitor-badge', visitor_color))
        for selector, color in selectors:
            palette = pastel_palette(color)
            styles.append(selector + '{--category-color:' + palette['reference'] +
                ';--category-background:' + palette['background'] + ';--category-ink:' + palette['ink'] +
                ';--category-border:' + palette['border'] + ';}')
        return {'evolution_csrf':csrf_token(), 'category_colors':colors, 'category_styles': ''.join(styles),
                'enrollment_mode':enrollment_mode(db), 'public_id_modes':ID_MODES,
                'attendance_reference':attendance_reference(db),
                'affiliation_choices':affiliation_choices(db) if request.endpoint in ('admin_edit_user','admin_add_user') else [],
                'anonymous_visitor_color': visitor_color,
                'user_grants': resources.grants_for_user(db, request.view_args['user_id']) if request.endpoint == 'admin_edit_user' else [],
                'creation_sources':SOURCES, 'self_enrollment_enabled':a.read_setting(db,'self_enrollment_enabled','0')=='1',
                'tablet_reservations_enabled':a.read_setting(db,'tablet_reservations_enabled','0')=='1',
                'welcome_default':a.read_setting(db,'welcome_default','0')=='1',
                'smtp_ready':bool(welcome_mail.load_config(application.config['DATABASE']))}

    @bp.post('/admin/reglages/affichage/visiteurs')
    def visitor_color_settings():
        require_team(True)
        require_csrf()
        try:
            color = validate_color(request.form.get('anonymous_visitor_color'))
        except ValueError as error:
            abort(400, str(error))
        db = a.get_database()
        with db:
            a.write_setting(db, 'anonymous_visitor_color', color)
        flash('Couleur des visiteurs enregistrée.', 'success')
        return redirect(url_for('admin_settings_display', _anchor='anonymous-visitor-color'))

    @bp.post('/admin/reglages/affichage/frequentation')
    def attendance_settings():
        require_team(True)
        require_csrf()
        try:
            value = validate_reference(request.form.get('attendance_reference'))
        except ValueError as error:
            abort(400, str(error))
        db = a.get_database()
        with db:
            a.write_setting(db, 'attendance_reference', value)
        flash('Seuil de fréquentation enregistré.', 'success')
        return redirect(url_for('admin_settings_display', _anchor='attendance-reference'))

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
                                          request.form.get('key') or None)
                        audit(db,'category',key,'saved',role)
                    elif request.form.get('action')=='remove_category':
                        if request.form.get('confirmation')!='SUPPRIMER':
                            raise ValueError('Saisissez SUPPRIMER pour confirmer.')
                        key=request.form.get('key')
                        action=remove_category(db,key,request.form.get('replacement') or None)
                        audit(db,'category',key,action,role)
                    elif request.form.get('action')=='preferences':
                        mode=request.form.get('public_id_assignment_mode',enrollment_mode(db))
                        if mode not in ID_MODES:
                            raise ValueError('Mode d’attribution de l’identifiant invalide.')
                        a.write_setting(db,'public_id_assignment_mode',mode)
                        for key in ('self_enrollment_enabled','tablet_reservations_enabled','welcome_default'):
                            a.write_setting(db,key,'1' if request.form.get(key)=='1' else '0')
                        subject,body=request.form.get('welcome_subject',''),request.form.get('welcome_body','')
                        welcome_mail.validate_template(subject,body)
                        a.write_setting(db,'welcome_subject',subject);a.write_setting(db,'welcome_body',body)
                    elif request.form.get('action')=='family':
                        from family_model import validate_settings
                        for key,value in validate_settings(request.form).items():
                            a.write_setting(db,key,value)
                        db.execute("DELETE FROM app_settings WHERE key='family_age_checked_on'")
                    else:
                        raise ValueError('Action inconnue.')
                if request.headers.get('X-OpenFabLab-Autosave') == '1':
                    return {'ok': True}
                flash('Réglages enregistrés.', 'success')
            except (ValueError,sqlite3.IntegrityError) as error:
                if request.headers.get('X-OpenFabLab-Autosave') == '1':
                    db.rollback()
                    return {'ok':False, 'message':str(error) if isinstance(error,ValueError) else 'Nom déjà utilisé.'},400
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
                    message=welcome_mail.build_smtp_test(config,request.form.get('recipient'),
                        a.read_setting(db,'structure_name','Mon FabLab'),a.read_setting(db,'structure_website',''))
                    welcome_mail.send(config,message)
                elif action=='welcome_test':
                    values={'structure_name':a.read_setting(db,'structure_name','Mon FabLab'),'first_name':'Camille','last_name':'Exemple',
                            'public_id':'9876','contact':a.read_setting(db,'structure_email',''),'website':a.read_setting(db,'structure_website','')}
                    message=welcome_mail.build_message(config,request.form.get('recipient'),values,
                        '[EXEMPLE FICTIF] ' + a.read_setting(db,'welcome_subject',welcome_mail.SUBJECT),
                        a.read_setting(db,'welcome_body',welcome_mail.BODY))
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

    @bp.post('/admin/reglages/ordre/<kind>')
    def save_order(kind):
        role = require_team(True); require_csrf()
        db = a.get_database()
        try:
            import json
            keys = json.loads(request.form.get('keys', 'null'))
            db.execute('BEGIN IMMEDIATE')
            keys = reorder(db, kind, keys)
            audit(db, 'ordering', kind, 'reordered', role)
            db.commit()
        except (ValueError, sqlite3.Error):
            db.rollback()
            return {'ok': False, 'message': 'Ordre non enregistré. Rechargez la liste et réessayez.'}, 400
        return {'ok': True, 'keys': keys}

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
        mode=enrollment_mode(db)
        def proposal(user, errors, status=400):
            user['public_id']=a.next_available_public_id(db)
            session['enrollment_proposal']=user['public_id']
            session['enrollment_mode']=mode
            return render_template('user_form.html',user=user,form_mode='create',kiosk=True,errors=errors,
                duplicate_users=[],country_names=a.COUNTRY_NAMES),status
        if request.method=='GET':
            session['enrollment_started']=time.time()
            return proposal(blank, [], 200)
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
        values=request.form.copy()
        # MultiDict.update appends values; get() could otherwise retain a forged
        # category or inactive flag. Assignment replaces all submitted values.
        if session.get('enrollment_mode')!=mode:
            return proposal(blank, ['Le mode d’inscription a changé. Vérifiez la nouvelle proposition.'], 409)
        code=(request.form.get('public_id','') if mode=='customizable' else
              session.get('enrollment_proposal','') if mode=='automatic_visible' else a.next_available_public_id(db))
        for key,value in {'public_id':code,'category':default_category(db),'active':'1'}.items():
            values[key]=value
        user,errors=a.validate_user_form(values,db,public_enrollment=True)
        if errors:
            # A proposed ID is not a reservation and reveals no other person's
            # identity/contact. No anonymous availability/directory endpoint.
            if any('identifiant' in error.lower() and 'utilisé' in error for error in errors):
                return proposal(user, errors + ['Un autre identifiant vous est proposé. Vérifiez-le avant de valider.'], 409)
            return render_template('user_form.html',user=user,form_mode='create',kiosk=True,errors=errors,duplicate_users=[],country_names=a.COUNTRY_NAMES),400
        try:
            db.execute('BEGIN IMMEDIATE')
            if mode=='automatic_discreet':
                user['public_id']=a.next_available_public_id(db)
            elif db.execute('SELECT 1 FROM users WHERE public_id=?',(user['public_id'],)).fetchone():
                db.rollback()
                return proposal(user, ['Cet identifiant vient d’être attribué. Vérifiez la nouvelle proposition avant de valider.'], 409)
            user_id=create_user(db,user,'kiosk')
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            return proposal(user, ['L’identifiant vient d’être attribué. Vérifiez la nouvelle proposition.'], 409)
        after_creation(a,db,user_id,request.form.get('send_welcome')=='1')
        session['enrollment_receipt']={'id':user_id,'until':time.time()+120}
        session.pop('enrollment_started',None)
        return redirect(url_for('evolution.enrollment_done'))

    @application.after_request
    def protect_enrollment_response(response):
        if request.path.startswith('/inscription'):
            response.headers['Cache-Control']='private, no-store'
            response.headers['Referrer-Policy']='no-referrer'
        return response

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
                                            request.form.get('active')=='1',request.form.get('key') or None)
                    elif action=='resource':
                        require_team(True)
                        if request.form.get('required_authorization') and not a.load_modules(db)['authorizations']:
                            raise ValueError('Activez Formations et habilitations avant d’exiger une habilitation.')
                        values = {k:request.form.get(k) for k in ('name','description','type_key','color','active','approval_required','price_cents','required_authorization')}
                        if 'price_euros' in request.form:
                            values['price_cents'] = resources.euros_to_cents(request.form['price_euros'])
                        resources.save_resource(db,values,role,request.form.get('key') or None)
                    else:
                        raise ValueError('Action inconnue.')
                if request.headers.get('X-OpenFabLab-Autosave') == '1':
                    return {'ok': True}
                flash('Ressource enregistrée.', 'success')
            except (ValueError,sqlite3.IntegrityError) as error:
                if request.headers.get('X-OpenFabLab-Autosave') == '1':
                    db.rollback()
                    return {'ok':False, 'message':str(error) if isinstance(error,ValueError) else 'Référence incompatible.'},400
                db.rollback();flash(str(error) if isinstance(error,ValueError) else 'Nom déjà utilisé ou référence invalide.','error')
            return redirect(url_for('evolution.resource_directory'))
        return render_template('resources.html',resource_types=db.execute('SELECT * FROM resource_types ORDER BY sort_order,name').fetchall(),
            resources=db.execute('SELECT r.*, t.name AS type_name,COALESCE(r.color,t.color) AS display_color,a.name AS authorization_name FROM resources r JOIN resource_types t USING(type_key) LEFT JOIN authorizations a ON a.authorization_uuid=r.required_authorization ORDER BY r.name').fetchall(),
            authorizations=resources.definitions(db,True))

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
                        resources.save_definition(db, request.form.get('name',''), request.form.get('description',''),role,request.form.get('key') or None)
                    elif action in {'archive', 'reactivate', 'delete'}:
                        if action == 'delete' and request.form.get('confirmation') != 'SUPPRIMER':
                            raise ValueError('Confirmez la suppression.')
                        resources.change_definition(db, request.form.get('key'), action, role)
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
        definitions = resources.definitions(db, True)
        today = datetime.now().date().isoformat()
        for definition in definitions:
            key = definition['authorization_uuid']
            history, dependencies, active_resources = resources.definition_usage(db, key)
            definition.update(history_count=history, dependencies=dependencies, active_resources=active_resources,
                qualified_count=db.execute('SELECT COUNT(DISTINCT g.user_id) FROM user_authorizations g JOIN users u ON u.id=g.user_id WHERE u.active=1 AND g.authorization_uuid=? AND g.revoked_at IS NULL AND g.performed_on<=? AND (g.expires_on IS NULL OR g.expires_on>=?)',(key,today,today)).fetchone()[0])
        return render_template('authorizations.html',definitions=definitions,
            users=db.execute('SELECT id,first_name,last_name FROM users WHERE active=1 ORDER BY first_name').fetchall(),
            grants=resources.grants_for_user(db))

    @bp.get('/admin/calendrier')
    def calendar():
        require_team()
        from fablab_calendar import calendar_view
        return render_template('calendar.html',**calendar_view(a.get_database(),request.args,a))

    application.register_blueprint(bp)
