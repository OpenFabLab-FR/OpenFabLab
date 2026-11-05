"""V2.15 extensions; explicit team/admin permissions plus existing CSRF gate."""
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from evolution_routes import require_team, require_csrf, csrf_token
from i18n import flash
import resource_loans as loans
import user_participation as participation


def register(application, namespace):
    from types import SimpleNamespace
    a = SimpleNamespace(**namespace)
    bp = Blueprint('v215', __name__)
    __import__('setup_routes').register(application,a,bp)

    def module(key):
        db = a.get_database()
        if not a.load_modules(db).get(key):
            abort(404)
        return db

    def followup(user_id):
        role = require_team()
        db = module('users')
        modules = a.load_modules(db)
        restriction = participation.active_restriction(db,user_id)
        operations=loans.user_history(db,user_id,role) if modules['resources'] or (modules['billing'] and role=='admin') else []
        operations=[row|{'url':request.script_root+row['url']} for row in operations
                    if (row['kind']=='booking' and modules['resources']) or
                       (row['kind']=='contract' and modules['billing'] and modules['rentals'] and role=='admin')]
        return dict(loans=operations,
                    participation=participation.history(db,user_id) if modules['activities'] else None,
                    restriction=dict(restriction) if restriction and role=='admin' else
                    ({'starts_on':restriction['starts_on'],'ends_on':restriction['ends_on']} if restriction else None),
                    restrictions=[dict(r) for r in db.execute('SELECT * FROM user_booking_restrictions WHERE user_id=? ORDER BY created_at DESC',(user_id,))] if role=='admin' else [])

    @application.context_processor
    def extensions():
        def rental(record):
            if record.get('billing_type') != 'rental':
                return None
            role=require_team(admin=True)
            db=module('billing')
            operation=next((r for r in loans.operations(db) if r['kind']=='contract' and r['key']==str(record['id'])),None)
            if operation:
                operation['late']=loans.overdue(db,operation)
                operation['people']=db.execute('SELECT id,first_name,last_name FROM users WHERE active=1 ORDER BY first_name,last_name LIMIT 2000').fetchall()
            return operation
        return {'user_followup':followup, 'rental_followup':rental,
                'resource_availability':lambda key: loans.availability(a.get_database(),key),
                'settings_navigation':__import__('settings_groups').navigation(request.endpoint),
                'settings_secondary':__import__('settings_groups').secondary(request.endpoint)}

    @bp.get('/admin/reglages/accueil')
    def settings_home():
        require_team(admin=True)
        return render_template('settings_home.html')

    @bp.get('/admin/reglages/wordpress')
    def wordpress_settings():
        require_team(admin=True)
        return application.extensions['render_settings_page']('wordpress')

    @bp.route('/admin/reglages/activites',methods=['GET','POST'])
    def calendar_settings():
        require_team(admin=True);db=a.get_database()
        schedule=a.load_openlab_schedule(db)
        if request.method=='POST':
            require_csrf()
            try:
                values={}
                if request.form.get('group')=='hours':
                    values=__import__('configuration_flow').hours(schedule,request.form)
                elif request.form.get('group')=='display':
                    start=request.form.get('start','');end=request.form.get('end','')
                    if not a.TIME_PATTERN.fullmatch(start) or not a.TIME_PATTERN.fullmatch(end) or end<=start:raise ValueError('La fin doit suivre le début de la plage affichée.')
                    values=dict(calendar_display_start=start,calendar_display_end=end)
                else:abort(400)
                for key,value in values.items():a.write_setting(db,key,value)
                db.commit();flash('Réglages du calendrier enregistrés.','success')
            except ValueError as error:flash(str(error),'error')
            return redirect(url_for('v215.calendar_settings'))
        return render_template('calendar_settings.html',openlab_schedule=schedule,module_settings=a.load_modules(db),
            calendar_start=participation.setting(db,'calendar_display_start','09:00'),
            calendar_end=participation.setting(db,'calendar_display_end','19:00'),evolution_csrf=csrf_token())

    @bp.route('/admin/usagers/<int:user_id>/suivi')
    def user_history(user_id):
        require_team()
        db=module('users')
        user=db.execute('SELECT id,first_name,last_name FROM users WHERE id=?',(user_id,)).fetchone()
        if not user:
            abort(404)
        return render_template('user_followup.html',user=user,followup=followup(user_id),evolution_csrf=csrf_token())

    @bp.post('/admin/recherche')
    def search():
        role=require_team()
        require_csrf()
        db=a.get_database()
        from admin_search import search as local_search
        modules=a.load_modules(db)|{'maintenance':__import__('machine_maintenance').enabled(db)}
        groups=local_search(db,request.form.get('q'),role,modules)
        for group in groups:
            for item in group['items']:
                item['url']=request.script_root+item['url']
        response=jsonify(groups=groups)
        response.headers['Cache-Control']='private, no-store'
        return response

    @bp.post('/admin/usagers/<int:user_id>/restrictions')
    def user_restriction(user_id):
        role=require_team(admin=True)
        require_csrf()
        db=module('users')
        if not a.load_modules(db)['activities']:
            abort(404)
        try:
            if request.form.get('action')=='lift':
                key=request.form.get('key')
                if not db.execute('SELECT 1 FROM user_booking_restrictions WHERE restriction_uuid=? AND user_id=?',(key,user_id)).fetchone():
                    abort(404)
                participation.lift(db,key,role)
            elif request.form.get('action')=='restrict':
                participation.restrict(db,user_id,request.form,role)
            else:
                abort(400)
            flash('Décision enregistrée. Le pointage au FabLab reste possible.','success')
        except ValueError as error:
            flash(str(error),'error')
        return redirect(url_for('v215.user_history',user_id=user_id))

    @bp.post('/admin/locations/<kind>/<key>/materiel')
    def loan_action(kind,key):
        role=require_team(admin=kind=='contract')
        require_csrf()
        if kind not in ('booking','contract'):
            abort(404)
        db=module('resources' if kind=='booking' else 'billing')
        if kind=='contract' and not a.load_modules(db)['rentals']:
            abort(404)
        try:
            loans.transition(db,kind,key,request.form.get('action'),role,
                             request.form.get('user_id') or None)
            flash('Remise ou retour du matériel enregistré.','success')
        except (ValueError,PermissionError) as error:
            flash(str(error),'error')
        target=url_for('evolution.resource_bookings')+'#reservation-'+key if kind=='booking' else url_for('admin_billing_detail',record_id=key)
        return redirect(target)

    @bp.route('/admin/reglages/systeme/mises-a-jour',methods=['GET','POST'])
    def updates():
        require_team(admin=True)
        import os
        from updater_client import request as agent_request, upload
        from update_wire import Refused, MAX_LOCAL_ZIP
        configured=bool(os.environ.get('OPENFABLAB_UPDATE_SOCKET') and os.environ.get('OPENFABLAB_UPDATE_TOKEN_FILE'))
        if request.method=='POST':
            request.max_content_length=MAX_LOCAL_ZIP+1024*1024
            require_csrf()
            operation=request.form.get('operation')
            if operation not in ('discover','prepare','status','install','cancel','prepare_zip'):
                abort(400)
            arguments={}
            if operation in ('install','cancel'):
                arguments['id']=request.form.get('id','')
            if operation=='install':
                if request.form.get('consent')!='INSTALLER':
                    return jsonify(ok=False,message='Confirmez explicitement l’installation préparée.'),400
                arguments['confirmation']=request.form.get('confirmation','')
            try:
                if operation=='prepare_zip':
                    files=request.files.getlist('candidate')
                    if len(files)!=1:
                        raise Refused('LOCAL_ZIP_REQUIRED')
                    return jsonify(ok=True,value=upload(files[0].stream))
                return jsonify(ok=True,value=agent_request(operation,arguments))
            except Refused as error:
                messages={
                    'AGENT_ZIP_UPGRADE_REQUIRED':'Une transition initiale de l’agent est nécessaire pour importer un ZIP.',
                    'LOCAL_ZIP_SIZE_REFUSED':'Choisissez un ZIP de 64 Mio maximum.',
                    'LOCAL_ZIP_REQUIRED':'Sélectionnez un paquet ZIP OpenFabLab.',
                    'NO_NEWER_OFFICIAL_STABLE':'Cette installation dispose déjà d’une version au moins aussi récente que la dernière stable.',
                    'AGENT_DISABLED':'Les mises à jour intégrées sont désactivées.',
                    'AGENT_NOT_CONFIGURED_MANUAL_UPDATE_AVAILABLE':'L’agent local n’est pas configuré. La mise à jour manuelle reste disponible.',
                    'AGENT_UNAVAILABLE_MANUAL_UPDATE_AVAILABLE':'L’agent local ne répond pas. Aucune installation n’a été lancée depuis cette demande.',
                    'UNFINISHED_JOB_REQUIRES_HUMAN_DECISION':'Une opération précédente doit être examinée avant de poursuivre.',
                    'PRESERVED_STATE_REQUIRES_RECOVERY':'Un état a été préservé après échec. Utilisez le diagnostic de récupération indépendant.',
                    'UPDATE_MANIFEST_UNAVAILABLE_USE_MANUAL':'Cette version ne dispose pas des métadonnées requises pour une installation intégrée. Utilisez son guide de mise à jour manuelle.',
                    'UPDATE_CONFIRMATION_REFUSED':'Cette confirmation est incorrecte ou a expiré. Préparez de nouveau la mise à jour.',
                }
                return jsonify(ok=False,message=messages.get(error.code,'L’agent a refusé cette opération. Consultez le code de contrôle avant de réessayer.'),code=error.code),409
        return render_template('updates.html',configured=configured,evolution_csrf=csrf_token())

    @application.before_request
    def preserve_handed_over_contracts():
        if request.method!='POST' or not request.view_args or not request.view_args.get('record_id'):
            return None
        protected={'admin_billing_delete','admin_billing_delete_invoice','admin_billing_sign',
                   'admin_billing_toggle_cancellation','admin_billing_form'}
        if request.endpoint not in protected:
            return None
        # General role protection runs before this hook; never broadens access.
        if require_team(admin=True) != 'admin':
            abort(403)
        record=a.get_database().execute('SELECT * FROM billing_records WHERE id=?',(request.view_args['record_id'],)).fetchone()
        if not record or not record['handed_over_at']:
            return None
        if request.endpoint=='admin_billing_form':
            if request.form.get('rental_machine_key')==record['rental_machine_key'] and request.form.get('billing_type')=='rental':
                return None
        elif request.endpoint=='admin_billing_toggle_cancellation' and record['returned_at']:
            return None
        abort(409,'Ce dossier possède une remise de matériel. Conservez son historique ; enregistrez le retour avant toute annulation.')

    application.register_blueprint(bp)
