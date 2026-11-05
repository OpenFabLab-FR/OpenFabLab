"""Explicit limited team operations, independent maintenance and kiosk settings."""
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4
from flask import Blueprint,abort,flash,redirect,render_template,request,session,url_for
from i18n import flash
from evolution_routes import require_team,require_csrf,actor
from family_model import setting
import machine_maintenance as machines
import openlab_openings

def register(application,api):
    a=SimpleNamespace(**api);bp=Blueprint('v214',__name__)
    @application.template_filter('machine_datetime')
    def machine_datetime(value):
        from zoneinfo import ZoneInfo
        from i18n import language
        stamp=datetime.fromisoformat(value).astimezone(ZoneInfo(setting(a.get_database(),'structure_timezone','Europe/Paris')))
        if language() in ('de','es','fi'):
            from localized_formats import day
            return day(stamp.date(),language())+f' {stamp:%H:%M}'
        months=('January February March April May June July August September October November December'.split() if language()=='en' else
                'janvier février mars avril mai juin juillet août septembre octobre novembre décembre'.split())
        return (f'{stamp.day} {months[stamp.month-1]} {stamp.year} at {stamp:%H:%M}' if language()=='en' else
                f'{stamp.day} {months[stamp.month-1]} {stamp.year} à {stamp:%H} h {stamp:%M}')
    def database(maintenance=False):
        require_team();db=a.get_database()
        if maintenance and not machines.enabled(db):abort(404)
        return db
    def author():return actor() or 'unknown'

    @bp.route('/admin/maintenance',methods=['GET','POST'])
    @bp.route('/admin/ressources/maintenance',methods=['GET'])
    def directory():
        db=database(True)
        if request.path.endswith('/admin/maintenance'):
            if request.method=='POST':require_csrf();abort(405)
            return redirect(url_for('v214.directory'),code=308)
        return redirect(url_for('evolution.resource_directory'),code=308)

    @bp.route('/admin/maintenance/<key>',methods=['GET','POST'])
    @bp.route('/admin/ressources/<key>/maintenance',methods=['GET','POST'])
    def machine(key):
        db=database(True)
        if request.method=='POST':require_csrf()
        try:machines.machine(db,key)
        except ValueError:abort(404)
        # Old forms use exactly the same controller without a second POST or
        # a cached method-preserving redirect. Successful writes go canonical.
        if request.method=='POST':return application.view_functions['resource_portal.page'](key)
        return redirect(url_for('resource_portal.page',key=key),code=308)

    @bp.route('/admin/calendrier/ouvertures',methods=['GET','POST'])
    def openings():
        db=database()
        if not a.load_modules(db)['activities'] and not machines.enabled(db):abort(404)
        if request.method=='POST':
            require_csrf()
            try:
                if request.form.get('action')=='remove':openlab_openings.remove_exception(db,request.form.get('day',''),author())
                else:openlab_openings.save_exception(db,request.form,author())
                db.commit();flash('Ouverture enregistrée.','success')
            except ValueError as error:db.rollback();flash(str(error),'error')
            return redirect(url_for('v214.openings'))
        return render_template('openlab_exceptions.html',exceptions=db.execute('SELECT * FROM openlab_exceptions ORDER BY day DESC').fetchall())

    @bp.post('/admin/reglages/2-14')
    def settings():
        require_team(admin=True);require_csrf();db=a.get_database();group=request.form.get('group')
        if group=='maintenance':
            values={'module_maintenance':str(int(request.form.get('enabled')=='1'))}
            target='resource_portal.settings'
        elif group=='resources':
            from public_resource_labels import CHOICES
            name=request.form.get('resource_public_name','resources')
            if name not in CHOICES:abort(400)
            values=dict(module_maintenance=str(int(request.form.get('enabled')=='1')),resource_public_name=name)
            target='resource_portal.settings'
        elif group=='kiosk-display':
            mode=request.form.get('machine_information')
            if mode not in ('both','home','identification','none'):abort(400)
            values=dict(kiosk_machine_information=mode);target='admin_settings_kiosk'
        elif group=='kiosk':
            mode=request.form.get('machine_information',setting(db,'kiosk_machine_information','both'));language=request.form.get('language','fr')
            from i18n import LANGUAGES
            if mode not in ('both','home','identification','none') or language not in LANGUAGES:abort(400)
            try:idle=int(request.form.get('idle','10'))
            except ValueError:abort(400)
            if not 1<=idle<=120:abort(400)
            additional=[lang for lang in LANGUAGES if request.form.get('allow_'+lang)=='1' or lang==language]
            values=dict(kiosk_machine_information=mode,kiosk_language=language,kiosk_languages=','.join(additional),kiosk_language_idle_minutes=str(idle),
                        kiosk_language_switch_enabled=str(int(request.form.get('language_switch')=='1')))
            target='admin_settings_kiosk'
        elif group=='notifications':
            try:hours=int(request.form.get('hours','48'));hour=int(request.form.get('hour','9'))
            except ValueError:abort(400)
            if not 1<=hours<=720 or not 0<=hour<=23:abort(400)
            values=dict(maintenance_discord_enabled=str(int(request.form.get('maintenance_discord')=='1')),
                maintenance_reminder_hour=str(hour),reservation_reminder_enabled=str(int(request.form.get('reminders')=='1')),
                reservation_reminder_hours=str(hours),reservation_calendar_enabled=str(int(request.form.get('calendar')=='1')))
            target='admin_notifications'
            if values['reservation_reminder_enabled']=='1' and setting(db,'reservation_reminder_enabled','auto')=='0':
                values['v214_reminders_available_since']=datetime.now().astimezone().isoformat(timespec='seconds')
        elif group=='openlab':
            values=dict(openlab_public_enabled=str(int(request.form.get('public')=='1')),
                        openlab_public_average_enabled=str(int(request.form.get('public_average')=='1')));target='v215.wordpress_settings'
        else:abort(400)
        for key,value in values.items():a.write_setting(db,key,value)
        db.commit();flash('Réglages enregistrés.','success')
        anchor={'resources':'resources-options','maintenance':'resources-options','openlab':'wordpress-settings','kiosk-display':'kiosk-display','kiosk':'options214'}.get(group,'options214')
        return redirect(url_for(target)+'#'+anchor)

    @bp.get('/animations/demande/<token>/calendrier.ics')
    def personal_calendar(token):
        import family_waitlist
        from flask import Response
        from reservation_calendar import event,ics
        db=a.get_database()
        if setting(db,'reservation_calendar_enabled','1')!='1':abort(404)
        try:group=family_waitlist.lookup(db,token)
        except ValueError:abort(404)
        if group['status']!='confirmed':abort(404)
        response=Response(ics(event(db,group)),mimetype='text/calendar')
        response.headers.update({'Content-Disposition':'attachment; filename="animation.ics"',
            'Cache-Control':'private, no-store','Referrer-Policy':'no-referrer','X-Robots-Tag':'noindex, nofollow'})
        return response

    @application.context_processor
    def context():
        db=a.get_database();settings=dict(db.execute('SELECT key,value FROM app_settings'))
        path=request.endpoint or '';location='home' if path=='index' else 'identification' if path=='identification' else None
        show=location and settings.get('kiosk_machine_information','both') in ('both',location)
        from family_model import local_day
        reminders_active=settings.get('reservation_reminder_enabled','auto')=='1'
        if settings.get('reservation_reminder_enabled','auto')=='auto' and path=='admin_notifications':
            from welcome_mail import load_config,validate_config
            try:validate_config(load_config(application.config['DATABASE']));reminders_active=True
            except ValueError:pass
        from fablab_calendar import show_maintenance
        unavailable=machines.public_machines(db,True) if show else []
        from public_resource_labels import labels,CHOICES
        return dict(**labels(db,len(unavailable)),resource_public_choices=CHOICES,settings214=settings,maintenance_enabled=machines.enabled(db),maintenance_visible=show_maintenance(request.args),today214=local_day(db).isoformat(),reservation_reminders_active=reminders_active,
            settings_section=('notifications' if path=='admin_notifications' else 'kiosk' if path=='admin_settings_kiosk' else 'structure' if path=='admin_settings_structure' else ''),
            unavailable_machines=unavailable)

    application.register_blueprint(bp)
