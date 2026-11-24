"""Secondary administration only: role checked on every GET and mutation."""
import json
import time
import os
from collections import Counter
from urllib.parse import urlsplit
from flask import Blueprint,abort,redirect,render_template,request,url_for
from i18n import flash
from evolution_routes import require_csrf,require_team
from family_model import setting
from outbound_actions import transaction
from account_schema import SETTINGS
import online_accounts as service
from admin_search import folded

# These are the fields of the portal form. Other existing preferences keep
# their storage keys, but are owned by Communication and Appearance.
PORTAL_OPTIONS = ('online_accounts_enabled','online_signup_enabled','online_approval',
                  'online_relay_environment','online_session_minutes','online_ticket_minutes',
                  'online_account_url')
PORTAL_SWITCHES = {'online_accounts_enabled','online_signup_enabled'}

def access_matches(db, query):
    if not 2<=len(query)<=80 or any(ord(c)<32 for c in query):
        return []
    escaped='%'+folded(query).replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
    db.create_function('ofl_access_fold',1,folded,deterministic=True)
    try:
        return db.execute("""SELECT u.id,u.first_name,u.last_name,u.public_id
            FROM online_identities i JOIN users u ON u.id=i.user_id
            WHERE ofl_access_fold(u.first_name||' '||u.last_name) LIKE ? ESCAPE '\\'
               OR ofl_access_fold(u.last_name||' '||u.first_name) LIKE ? ESCAPE '\\'
               OR u.public_id=?
            ORDER BY u.last_name,u.first_name,u.public_id LIMIT 20""",(escaped,escaped,query)).fetchall()
    finally:
        db.create_function('ofl_access_fold',1,None)

def valid_option(key,value):
    allowed={'online_approval':('manual','automatic','conditional'),'online_relay_environment':('test','production')}
    if key in allowed:
        if value not in allowed[key]:raise ValueError('Option invalide.')
    elif key in ('online_session_minutes','online_ticket_minutes'):
        if not value.isascii() or not value.isdigit() or not 5<=int(value)<=(60 if key=='online_session_minutes' else 30):
            raise ValueError('Durée invalide.')
    elif key=='online_account_url':
        p=urlsplit(value)
        if value and (len(value)>500 or p.scheme!='https' or not p.hostname or p.username or p.password or p.query or p.fragment or '\\' in value or any(ord(c)<=32 for c in value)):
            raise ValueError('Page de compte HTTPS requise, sans paramètres.')
    elif key not in SETTINGS or value not in ('0','1'):raise ValueError('Option invalide.')

def register(app,api):
    bp=Blueprint('online_admin',__name__)
    def db_users():
        require_team(admin=True)
        db=api['get_database']()
        if not api['load_modules'](db)['users']:abort(404)
        return db

    @bp.route('/admin/usagers/demandes',methods=['GET','POST'])
    def queue():
        db=db_users()
        search=request.method=='POST' and request.form.get('decision')=='find_access'
        review_search=request.method=='POST' and request.form.get('decision')=='find_for_review'
        if search or review_search:
            require_csrf()
        elif request.method=='POST':
            require_csrf()
            try:
                with transaction(db):
                    if request.form.get('decision')=='revoke':
                        if request.form.get('checked')!='1':raise ValueError('Confirmation requise.')
                        holder=request.form.get('user_id',type=int)
                        identity=db.execute('SELECT email FROM online_identities WHERE user_id=?',(holder,)).fetchone()
                        if not identity:raise ValueError('Aucun accès en ligne à révoquer pour cette fiche.')
                        db.execute('DELETE FROM online_requests WHERE owner=? OR email=?',(holder,identity[0]))
                        db.execute('DELETE FROM online_sessions WHERE owner=?',(holder,))
                        db.execute('DELETE FROM online_identities WHERE user_id=?',(holder,))
                        db.execute('DELETE FROM online_tickets WHERE owner=?',(holder,))
                        db.execute('DELETE FROM online_mail WHERE owner=?',(holder,))
                        service.event(db,'access_revoked',service.uuid4().hex,'admin',int(time.time()))
                    else:
                        service.review(db,request.form.get('id'),request.form.get('decision'),
                            request.form.get('user_id',type=int),request.form.get('checked')=='1')
            except ValueError as err:flash(str(err),'error')
            else:
                flash({'revoke':'Accès en ligne révoqué. La fiche usager et son historique sont conservés.',
                       'accept':'Demande acceptée.','refuse':'Demande refusée.'}[request.form['decision']],'success')
            return redirect(url_for('.queue'))
        search_term=request.form.get('q','').strip()[:80] if search else ''
        selected_id=request.args.get('revoke',type=int)
        selected=db.execute("""SELECT u.id,u.first_name,u.last_name,u.public_id
            FROM online_identities i JOIN users u ON u.id=i.user_id WHERE u.id=?""",(selected_id,)).fetchone() if selected_id is not None else None
        access_candidates=access_matches(db,search_term) if search else []
        pending=[]
        for r in db.execute("SELECT * FROM online_requests WHERE state='review' AND expires>? ORDER BY created,id LIMIT 100",(int(time.time()),)):
            data=json.loads(r['data'])
            targeted=review_search and request.form.get('id')==r['id']
            lookup=request.form.get('lookup','').strip()[:80] if targeted else ''
            candidates=service.review_candidates(db,r,lookup) if not lookup or len(lookup)>=2 else []
            reason=None
            if r['kind']=='claim' and not candidates and not lookup:
                matching=db.execute('SELECT * FROM users WHERE lower(trim(email))=? LIMIT 2',(r['email'],)).fetchall()
                if len(matching)==1:reason=service.claim_error(db,matching[0],r['email'])
            pending.append(dict(id=r['id'],kind=r['kind'],email=r['email'],first=data.get('first_name',''),
                                last=data.get('last_name',''),birth=data.get('birth_date',''),candidates=candidates,
                                searched=targeted,lookup=lookup,reason=reason))
        failures=db.execute('SELECT count(*) FROM online_mail WHERE attempts>=4').fetchone()[0]
        return render_template('online_requests.html',pending=pending,failures=failures,
            search=search,search_term=search_term,access_candidates=access_candidates,
            selected=selected,selection_missing=selected_id is not None and selected is None),{'Cache-Control':'private, no-store'}

    @bp.route('/admin/reglages/comptes-en-ligne',methods=['GET','POST'])
    def settings():
        db=db_users()
        if request.method=='POST':
            require_csrf()
            try:
                with transaction(db):
                    for k in PORTAL_OPTIONS:
                        value=request.form.get(k,'0' if k in PORTAL_SWITCHES else setting(db,k,SETTINGS[k]))
                        valid_option(k,value)
                        if k=='online_relay_environment' and setting(db,k)!=value and any(db.execute('SELECT 1 FROM '+name+' LIMIT 1').fetchone() for name in ('online_identities','online_requests','online_sessions')):
                            raise ValueError('Utilisez une instance distincte pour changer d’environnement.')
                        db.execute('UPDATE app_settings SET value=? WHERE key=?',(value,k))
                    if setting(db,'online_accounts_enabled')=='1':
                        if setting(db,'online_relay_environment')!=os.environ.get('OPENFABLAB_ONLINE_ENVIRONMENT','production'):
                            raise ValueError('Cet environnement doit correspondre à celui déclaré sur l’hôte de cette instance.')
                        from online_mail import portal_url
                        portal_url(db)
                    else:
                        for name in ('online_sessions','online_tickets','online_mail','online_requests'):
                            db.execute('DELETE FROM '+name)
            except ValueError as err:flash(str(err),'error')
            else:flash('Les réglages des comptes en ligne ont été enregistrés.','success')
            return redirect(url_for('.settings'))
        return render_template('online_settings.html',options={k:setting(db,k,SETTINGS[k]) for k in PORTAL_OPTIONS})

    @bp.get('/admin/elements-a-traiter.json')
    def counts():
        role=require_team()
        db=api['get_database']()
        if setting(db,'online_header_tasks','1')!='1':abort(404)
        from admin_summary import build
        result=build(db,api['load_modules'](db),role,actions_only=True)
        counts=Counter()
        for row in result['actions']:counts[row['kind']]+=row['count']
        entries=[]
        labels={'accounts':'Demandes de comptes','resource':'Ressources','maintenance':'Maintenance',
                'loan':'Locations et réservations','report':'Signalements','activity':'Activités','tasks':'À traiter',
                'invoice':'Factures','quote':'Devis','calendar':'Calendrier'}
        for kind,count in counts.items():
            matches=[i for i in result['actions'] if i['kind']==kind]
            from i18n import t
            entries.append(dict(kind='people' if kind=='accounts' else kind,label=t(labels.get(kind,'À traiter')),count=count,
                url=matches[0]['url'] if len(matches)==1 or kind=='accounts' else url_for('admin',_anchor='summary-tasks')))
        return {'total':result['action_count'],'groups':entries},{'Cache-Control':'private, no-store'}

    app.register_blueprint(bp)
