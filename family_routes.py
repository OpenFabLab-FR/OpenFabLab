"""Additive 2.8 UI hooks, protected relationships and settings; no public directory."""
import re
import hashlib
import hmac
import json
import secrets
import time
from types import SimpleNamespace
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from evolution_routes import actor, require_csrf, require_team
import family_model as families


def register(application, api):
    a = SimpleNamespace(**api)
    bp = Blueprint('family',__name__)

    @application.template_filter('family_state')
    def family_state(user):
        return families.LABELS[families.state(a.get_database(),user)]

    @application.template_filter('family_age')
    def family_age(user):
        try:
            return families.age(user,families.local_day(a.get_database()))
        except (TypeError,ValueError):
            return None

    @application.context_processor
    def context():
        db = a.get_database()
        config = {k:families.setting(db,k,v) for k,v in families.DEFAULTS.items()}
        from fablab_calendar import COLORS
        colors = {k:families.setting(db,'calendar_color_'+k,v) for k,v in COLORS.items()}
        result = {'family_settings':config,'contact_policies':families.POLICIES,
                  'home_title':config['home_title'], 'calendar_colors':colors,
                  'calendar_color_defaults':COLORS}
        if request.endpoint in ('admin_edit_user','admin_add_user','evolution.enroll'):
            current = (request.view_args or {}).get('user_id')
            person = db.execute('SELECT * FROM users WHERE id=?',(current,)).fetchone() if current else None
            result['family_responsibles'] = families.responsibles(db,current) if current else []
            result['family_members'] = families.members(db,current) if current else []
            result['family_status'] = families.LABELS[families.state(db,person)] if person else ''
            from family_waitlist import contact
            details=contact(db,current) if person and person['active'] else None
            result['family_managed_contact']=details if details and details['user_id']!=current else None
            result['family_warnings'] = []
            if person:
                if families.state(db,person)=='dependent' and not result['family_responsibles']:
                    result['family_warnings'].append('Responsable à renseigner')
                if families.missing_contacts(families.contact_policy(db,person),person):
                    result['family_warnings'].append('Coordonnées à compléter')
            selected = request.form.getlist('responsible_ids')
            if request.endpoint=='evolution.enroll':
                grant = session.get('family_enrollment_guardian',{})
                selected = [str(grant['id'])] if grant.get('until',0)>time.time() else []
            result['selected_responsibles'] = [dict(u) for u in db.execute('SELECT * FROM users WHERE id IN ('+(','.join('?' for _ in selected) or 'NULL')+')',selected)]
        return result

    @application.before_request
    def family_form_steps():
        if request.endpoint not in ('admin_add_user','admin_edit_user','evolution.enroll') or request.method!='POST':
            return
        action = request.form.get('family_step')
        if action not in ('search','verify'):
            return
        require_csrf()
        db = a.get_database()
        public = request.endpoint=='evolution.enroll'
        results=[]; errors=[]
        if public:
            if action!='verify':
                abort(403)
            # No name search at all on the kiosk; bounded ID/contact challenge.
            if time.time()-session.get('enrollment_started',0)>900:
                abort(400)
            from family_reservations import limit_identification, matching_account
            try:
                bucket=hmac.new(str(application.secret_key).encode(),(request.remote_addr or '').encode(),hashlib.sha256).hexdigest()
                limit_identification(db,'enrollment:'+bucket)
            except ValueError:
                abort(429)
            identifier=request.form.get('guardian_public_id','')
            contact=request.form.get('guardian_contact','').strip()
            user=matching_account(db,identifier,contact)
            if not user or not families.eligible(db,user):
                errors.append('Identifiant ou coordonnée non concordants, ou responsable non éligible. Adressez-vous à l’équipe.')
            else:
                session['family_enrollment_guardian']={'id':user['id'],'until':time.time()+900}
        else:
            require_team()
            term=request.form.get('responsible_search','').strip()
            if len(term)<2 or len(term)>80:
                errors.append('Saisissez au moins deux caractères du nom, prénom ou identifiant.')
            else:
                query='%'+term.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
                results=[dict(u) for u in db.execute("SELECT * FROM users WHERE active=1 AND (first_name LIKE ? ESCAPE '\\' OR last_name LIKE ? ESCAPE '\\' OR public_id LIKE ? ESCAPE '\\') ORDER BY last_name,first_name LIMIT 30",(query,query,query)) if families.eligible(db,u)]
        values=request.form.to_dict()
        values['birth_year']=values.get('birth_year') or None
        values['active']=int(values.get('active','1'))
        if public:
            values.update(public_id=a.next_available_public_id(db),category=a.default_category(db))
        current=(request.view_args or {}).get('user_id')
        if current:
            values['id']=current
        return render_template('user_form.html',user=values,form_mode='edit' if current else 'create',
                               kiosk=public,errors=errors,duplicate_users=[],country_names=a.COUNTRY_NAMES,
                               responsible_search_results=results)

    @application.before_request
    def birthdays():
        if actor() not in ('admin','moderator') or request.method!='GET':
            return
        db = a.get_database()
        from runtime_policy import external_allowed
        notify=None
        if external_allowed(application.config['DATABASE']) and a.load_modules(db)['discord']:
            config=a.load_discord_settings(db)
            webhook=a.read_discord_webhook()
            if config['enabled'] and webhook:
                notify=lambda message:a.send_discord_plain(webhook,message,config['bot_name'])
        families.observe_ages(db,notify=notify)

    @bp.route('/animations/<int:service_id>/famille',methods=['GET','POST'])
    def booking(service_id):
        from family_reservation_routes import kiosk
        return kiosk(application,a,service_id)

    @bp.post('/admin/usagers/<int:user_id>/famille/<key>/terminer')
    def unlink(user_id,key):
        require_team(True);require_csrf();db=a.get_database()
        with db:
            try:
                families.end_link(db,key,user_id)
            except ValueError as error:
                abort(409,str(error))
        flash('Rattachement terminé. Les comptes et leur historique sont conservés.','success')
        return redirect(url_for('admin_edit_user',user_id=user_id))

    @bp.post('/admin/calendrier/visibilite')
    def visibility():
        require_team(True);require_csrf();db=a.get_database()
        from fablab_calendar import set_visibility
        try:
            with db:
                set_visibility(db,request.form.get('kind'),request.form.get('key'),request.form.get('day'),request.form.get('hidden')=='1')
        except ValueError as error:
            abort(400,str(error))
        return redirect(url_for('evolution.calendar',view=request.form.get('view','week'),date=request.form.get('date'),hidden='1' if request.form.get('show_hidden')=='1' else None))

    @bp.post('/admin/reglages/affichage/couleurs')
    def colors():
        require_team(True);require_csrf();db=a.get_database()
        from fablab_calendar import COLORS
        values={k:request.form.get(k,v) for k,v in COLORS.items()}
        if request.form.get('reset')=='1':
            values=COLORS.copy()
        if not all(re.fullmatch(r'#[0-9a-fA-F]{6}',v) for v in values.values()):
            abort(400,'Couleur invalide.')
        with db:
            for key,value in values.items():
                a.write_setting(db,'calendar_color_'+key,value)
        return redirect(url_for('admin_settings_display')+'#calendar-colors')

    @bp.post('/admin/reglages/borne/titre')
    def title():
        require_team(True);require_csrf();db=a.get_database()
        title=request.form.get('home_title','').strip()
        if not title or len(title)>40 or any(ord(c)<32 for c in title):
            abort(400,'Titre requis, 40 caractères maximum.')
        with db:
            a.write_setting(db,'home_title',title)
        return redirect(url_for('admin_settings_kiosk')+'#home-title')

    application.register_blueprint(bp)
    from family_reservation_routes import register as register_gateway
    register_gateway(application,a)
