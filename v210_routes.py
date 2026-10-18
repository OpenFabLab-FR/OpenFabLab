"""Small, role-checked local extensions; no public membership directory."""
import json
import sqlite3
from decimal import Decimal,InvalidOperation
from datetime import date
from uuid import uuid4
from flask import Blueprint,abort,flash,redirect,render_template,request,url_for
import memberships as m
import v210_config as config


def register(application,a):
    from evolution_routes import require_team,require_csrf,csrf_token
    from kiosk_feedback import register as register_feedback
    register_feedback(application,a)
    bp=Blueprint('v210',__name__)
    application.add_template_filter(json.loads,'from_json')
    application.add_template_filter(lambda value,terms:m.amount_label(value,json.loads(terms)),'member_amount')
    application.add_template_filter(lambda value:dict(initial='Attribution',recharge='Recharge',consumption='Consommation',correction='Correction',reversal='Compensation',renewal='Renouvellement',status='État / document',beneficiaries='Bénéficiaires',selection='Sélection',reconciliation='Régularisation').get(value,value),'member_kind')

    @application.context_processor
    def preferences_context():
        return dict(v210=config.preferences(a.get_database()))

    @bp.post('/admin/reglages/2-10/<section>')
    def settings(section):
        require_team(admin=True);require_csrf();db=a.get_database()
        sets={'sound':({'kiosk_sound_enabled','kiosk_sound_volume','kiosk_sound_ambience','kiosk_sound_countdown'},'admin_settings_kiosk'),
              'sync':({'discord_sync_delay_minutes','discord_sync_recovery_enabled'},'admin_notifications')}
        if section not in sets:abort(404)
        keys,dest=sets[section]
        try:
            values={key:config.validate(key,request.form.get(key,'0' if key in config.BOOLS else config.DEFAULTS[key])) for key in keys}
            with m.atomic(db):
                for key,value in values.items():a.write_setting(db,key,value)
            flash('Préférences enregistrées.','success')
        except ValueError as error:flash(str(error),'error')
        return redirect(url_for(dest))

    @bp.post('/admin/calendrier/note')
    def calendar_note():
        require_team();require_csrf();db=a.get_database()
        try:
            from fablab_calendar import calendar_view
            day=date.fromisoformat(request.form.get('day',''));kind=request.form.get('kind');key=request.form.get('key')
            view=calendar_view(db,dict(view='week',date=day.isoformat(),hidden='1'),a)
            if not any(e['kind']==kind and e['key']==key and e['day']==day for d in view['days'] for e in d['events']):raise ValueError('Occurrence inconnue.')
            note=m.text(request.form.get('note'),'Note',2000)
            with m.atomic(db):
                if note:db.execute('INSERT INTO calendar_notes VALUES(?,?,?,?,?) ON CONFLICT(event_kind,event_key,occurrence_date) DO UPDATE SET note=excluded.note,updated_at=excluded.updated_at',(kind,key,day.isoformat(),note,m.stamp()))
                else:db.execute('DELETE FROM calendar_notes WHERE event_kind=? AND event_key=? AND occurrence_date=?',(kind,key,day.isoformat()))
            flash('Note interne enregistrée.','success')
        except ValueError as error:flash(str(error),'error')
        return redirect(url_for('evolution.calendar',view=request.form.get('view','week'),date=request.form.get('date') or date.today().isoformat()))

    def allowed():
        require_team(admin=True)
        db=a.get_database()
        if not m.enabled(db):abort(404)
        return db

    @bp.get('/admin/abonnements')
    def memberships():
        db=allowed();person=request.args.get('user','');query=request.args.get('q','').strip()[:80]
        if person and not person.isdecimal():abort(400)
        from participant_search import search_users
        users=search_users(db,query)['users'] if query else []
        selected=db.execute('SELECT id,first_name,last_name,public_id FROM users WHERE id=?',(person,)).fetchone() if person else None
        plans=[dict(row,terms=json.loads(row['terms_json'])) for row in db.execute('SELECT * FROM membership_plans ORDER BY active DESC,name')]
        grants=m.grants_for(db,int(person)) if selected else []
        day=m.today(db).isoformat()
        summary=db.execute('''SELECT COUNT(*) AS total,SUM(status='active' AND starts_on<=? AND ends_on>=?) AS active,
            SUM(ends_on<?) AS expired,SUM(status='active' AND ends_on BETWEEN ? AND date(?,?)) AS soon,
            SUM(json_extract(terms_json,'$.kind')='credits' AND balance=0) AS empty
            FROM membership_grants''',(day,day,day,day,day,'+'+m.setting(db,'membership_notice_days','14')+' days')).fetchone()
        page=m.integer(request.args.get('page','0'),'Page',0,100000)
        where=' WHERE EXISTS(SELECT 1 FROM membership_beneficiaries b WHERE b.grant_id=g.grant_id AND b.user_id=?)' if selected else '';params=(selected['id'],) if selected else ()
        history=db.execute('''SELECT l.*,g.terms_json,u.first_name,u.last_name FROM membership_ledger l JOIN membership_grants g USING(grant_id)
            LEFT JOIN users u ON u.id=l.user_id'''+where+' ORDER BY l.created_at DESC,l.rowid DESC LIMIT 51 OFFSET ?',params+(page*50,)).fetchall()
        pending=db.execute('SELECT session_id,remaining FROM membership_consumptions WHERE remaining>0 LIMIT 100').fetchall()
        reviews=db.execute('''SELECT session_id FROM membership_session_links WHERE grant_id IS NOT NULL AND (review_required=1
            OR session_id IN(SELECT id FROM sessions WHERE check_out IS NULL) OR session_id IN(SELECT session_id FROM membership_consumptions WHERE remaining>0)) LIMIT 100''').fetchall()
        recent=db.execute('''SELECT g.*,u.first_name,u.last_name FROM membership_grants g LEFT JOIN users u ON u.id=g.owner_id
            ORDER BY g.ends_on,g.created_at DESC LIMIT 100''').fetchall()
        families=[]
        if selected:
            families=db.execute('SELECT id,first_name,last_name FROM users WHERE active=1 AND id IN(SELECT member_id FROM user_family_links WHERE responsible_id=? AND ended_at IS NULL UNION SELECT responsible_id FROM user_family_links WHERE member_id=? AND ended_at IS NULL UNION SELECT ?)',(person,person,person)).fetchall()
        edit=db.execute('SELECT * FROM membership_plans WHERE plan_id=?',(request.args.get('edit',''),)).fetchone()
        from evolution_schema import categories
        return render_template('memberships.html',plans=plans,grants=grants,selected=selected,results=users,query=query,
            membership_summary=summary,history=history[:50],more_history=len(history)>50,history_page=page,pending=pending,reviews=reviews,
            recent=recent,family_choices=families,editing=dict(edit,terms=json.loads(edit['terms_json'])) if edit else None,
            today=day,operation_key=uuid4().hex,membership_categories=categories(db),member_preferences=db.execute('SELECT * FROM membership_preferences WHERE user_id=?',(person,)).fetchone() if selected else None)

    @bp.post('/admin/abonnements/action')
    def membership_action():
        db=allowed();require_csrf();f=request.form;kind=f.get('action');person=f.get('user','');key=f.get('operation_key','')
        if not key or len(key)>100:abort(400)
        try:
            if kind=='plan':
                values=f.to_dict();price=Decimal(f.get('price','0').replace(',','.'))*100
                if not price.is_finite() or price!=price.to_integral_value():raise ValueError('Prix en euros avec deux décimales maximum.')
                values['price_cents']=str(int(price))
                m.save_plan(db,values,f.get('plan_id') or None,creation_key=key)
            elif kind=='assign':m.assign(db,f['plan_id'],person,f.getlist('beneficiaries'),f['starts_on'],key,f.get('renew_from') or None)
            elif kind in ('recharge','correction'):m.adjust(db,f['grant_id'],f['quantity'],kind,key,f['reason'])
            elif kind=='reverse':m.reverse(db,f['entry_key'],key,f['reason'])
            elif kind=='status':m.state_change(db,f['grant_id'],f['status'],key,f['reason'])
            elif kind=='beneficiaries':m.beneficiaries(db,f['grant_id'],f.getlist('beneficiaries'),key,f['reason'])
            elif kind=='preference':m.select_credit(db,int(person),f.get('plan_id'),f.get('exempt')=='1',f['reason'])
            elif kind=='review':m.reconcile(db,int(f['session_id']),key,f['reason'])
            elif kind=='archive':
                active=m.integer(f.get('active'),'État',0,1)
                with m.atomic(db):db.execute('UPDATE membership_plans SET active=?,updated_at=? WHERE plan_id=?',(active,m.stamp(),f['plan_id']))
            elif kind=='billing':
                if not a.load_modules(db)['billing']:raise ValueError('Le module Facturation est désactivé.')
                with m.atomic(db):
                    record=f.get('billing_record_id','')
                    if record and not db.execute('SELECT 1 FROM billing_records WHERE id=?',(record,)).fetchone():raise ValueError('Dossier inconnu.')
                    m.movement(db,f['grant_id'],0,'status',key,dict(billing=record,grant=f['grant_id']),'admin','Rattachement documentaire uniquement')
                    db.execute('UPDATE membership_grants SET billing_record_id=? WHERE grant_id=?',(record or None,f['grant_id']))
            elif kind=='settings':
                keys={k for k in config.DEFAULTS if k.startswith('membership_')}
                values={k:config.validate(k,json.dumps(f.getlist(k)) if k=='membership_exempt_categories' else f.get(k,'0' if k in config.BOOLS else config.DEFAULTS[k])) for k in keys}
                from evolution_schema import audit
                with m.atomic(db):
                    for k,v in values.items():a.write_setting(db,k,v)
                    audit(db,'memberships','configuration','update','admin')
            else:raise ValueError('Action inconnue.')
            flash('Modification enregistrée. Aucun paiement n’a été créé.','success')
        except (ValueError,InvalidOperation,KeyError,sqlite3.IntegrityError) as error:
            db.rollback();flash(str(error) if not isinstance(error,sqlite3.Error) else 'Opération refusée : contrôle de cohérence.','error')
        return redirect(url_for('v210.memberships',user=person) if person.isdecimal() else url_for('v210.memberships'))
    application.register_blueprint(bp)
