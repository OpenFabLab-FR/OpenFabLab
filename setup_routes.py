"""Optional setup for new installations, using existing authentication/settings."""
import json
from flask import abort,redirect,render_template,request,session,url_for
from evolution_routes import require_team,require_csrf,csrf_token
from family_model import setting
from i18n import LANGUAGES,flash
from memberships import atomic
import configuration_flow as flow

def register(application,a,bp):
    @application.before_request
    def first_install():
        if request.endpoint=='admin' and session.get('access_role')=='admin' and setting(a.get_database(),'setup_completed','1')=='0':
            return redirect(url_for('v215.setup'))

    @bp.route('/admin/reglages/assistant',methods=['GET','POST'])
    def setup():
        require_team(admin=True);db=a.get_database()
        state=flow.progress(setting(db,'setup_progress','{}'))
        step=request.values.get('step',state['step'])
        if step not in flow.STEPS:abort(400)
        error=None
        if request.method=='POST':
            require_csrf()
            try:
                with atomic(db):
                    # Refresh under the write lock, including first-resource creation.
                    state=flow.progress(setting(db,'setup_progress','{}'))
                    if request.form.get('revision')!=str(state['revision']):
                        raise ValueError('Cette étape a déjà été enregistrée. Rechargez la page pour continuer.')
                    values={};action=request.form.get('action','save')
                    if action not in ('save','finish','later'):abort(400)
                    if step!='summary' or action=='finish':
                        if step=='identity':values=flow.identity(request.form)
                        elif step=='kiosk':
                            primary=request.form.get('language','fr')
                            if primary not in LANGUAGES:raise ValueError('Choisissez une langue disponible.')
                            allowed=[code for code in LANGUAGES if code==primary or request.form.get('allow_'+code)=='1']
                            title=request.form.get('home_title','').strip()
                            if not title or len(title)>40:raise ValueError('Le titre d’accueil doit contenir entre 1 et 40 caractères.')
                            values=dict(kiosk_language=primary,kiosk_languages=','.join(allowed),home_title=title,
                                kiosk_language_switch_enabled=str(int(request.form.get('language_switch')=='1')))
                        elif step=='hours':values=flow.hours(a.load_openlab_schedule(db),request.form)
                        elif step=='modules':
                            if request.form.get('preset')=='counter':
                                selected={key:key in ('users','frequency') for key in a.MODULE_LABELS}
                                values['module_maintenance']='0'
                            else:selected={key:request.form.get('module_'+key)=='1' for key in a.MODULE_LABELS}
                            errors=flow.module_errors(db,selected)
                            if errors:raise ValueError(errors[0])
                            values.update({'module_'+key:str(int(value)) for key,value in selected.items()})
                        elif step=='resources' and request.form.get('name','').strip():
                            if not a.load_modules(db)['resources'] and setting(db,'module_maintenance','0')!='1':
                                raise ValueError('Activez les ressources ou leur suivi avant de créer une fiche.')
                            __import__('resource_booking').save_resource(db,dict(name=request.form['name'],type_key=request.form.get('type_key'),active='1'),'admin')
                        elif step=='summary':
                            if action!='finish':abort(400)
                            values['setup_completed']='1'
                        # Communication credentials remain exclusively in their
                        # existing forms, never in the progress record.
                        for key,value in values.items():a.write_setting(db,key,value)
                        state['done']=list(dict.fromkeys(state['done']+[step]))
                        state['step']=flow.STEPS[min(flow.STEPS.index(step)+1,len(flow.STEPS)-1)]
                    state['revision']+=1
                    a.write_setting(db,'setup_progress',json.dumps(state,separators=(',',':')))
                if action=='later':return redirect(url_for('v215.settings_home'))
                flash('Configuration enregistrée.','success')
                return redirect(url_for('admin') if step=='summary' else url_for('v215.setup',step=state['step']))
            except ValueError as exc:error=str(exc)
        # Deliberate allowlist: do not even pass SMTP/WordPress/PIN secrets to the
        # template context, including on an existing installation.
        keys=['structure_'+k for k in ('name','short_name','city','country','timezone')]+['home_title','kiosk_language','kiosk_languages','kiosk_language_switch_enabled','module_maintenance']
        settings={key:setting(db,key,'Europe/Paris' if key=='structure_timezone' else '') for key in keys}
        return render_template('setup.html',steps=flow.STEPS,step=step,progress=state,error=error,
            setup_settings=settings,setup_modules=a.load_modules(db),module_labels=a.MODULE_LABELS,
            openlab_schedule=a.load_openlab_schedule(db),setup_languages=LANGUAGES,
            resource_types=db.execute('SELECT type_key,name FROM resource_types WHERE active=1 ORDER BY name').fetchall(),
            evolution_csrf=csrf_token(),form=request.form if request.method=='POST' else None)
