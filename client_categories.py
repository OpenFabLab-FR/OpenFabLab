"""Optional informative classification of the existing billing directory."""
import re
import sqlite3
from uuid import uuid4
from family_model import timestamp
from participant_search import normalized


def registry(db):
    return [dict(row) for row in db.execute('SELECT * FROM client_categories ORDER BY sort_order,name')]


def validate_entry(entry):
    if not isinstance(entry,dict) or set(entry)!={'category_key','name','active','sort_order'}:
        raise ValueError('Catégorie de client invalide.')
    if not isinstance(entry['category_key'],str) or not re.fullmatch('[a-z0-9_]{1,40}',entry['category_key']):
        raise ValueError('Identifiant de catégorie de client invalide.')
    name=entry['name']
    if not isinstance(name,str) or not 1<=len(name.strip())<=80 or any(ord(c)<32 for c in name):
        raise ValueError('Libellé de catégorie limité à 80 caractères.')
    if type(entry['active']) is not int or entry['active'] not in (0,1) or type(entry['sort_order']) is not int or not 0<=entry['sort_order']<=100000:
        raise ValueError('État ou ordre de catégorie de client invalide.')


def import_registry(db, entries):
    # Update known keys, keep absent/used entries and never remove a client FK.
    for entry in entries:
        validate_entry(entry)
        now=timestamp()
        db.execute('''INSERT INTO client_categories VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(category_key) DO UPDATE SET name=excluded.name,
            normalized_name=excluded.normalized_name,active=excluded.active,
            sort_order=excluded.sort_order,updated_at=excluded.updated_at''',
            (entry['category_key'],entry['name'].strip(),normalized(entry['name'].strip()),entry['active'],entry['sort_order'],now,now))


def selected(db, value, current=None):
    value=str(value or '').strip()
    if not value:
        return None
    row=db.execute('SELECT active FROM client_categories WHERE category_key=?',(value,)).fetchone()
    if not row or not row[0] and value!=current:
        raise ValueError('Choisissez une catégorie de client active, ou conservez sa catégorie archivée.')
    return value


def register(application,a):
    from flask import Blueprint,abort,flash,redirect,render_template,request,url_for
    from evolution_routes import require_csrf,require_team
    bp=Blueprint('client_categories',__name__)
    def guard():
        require_team(True)
        db=a.get_database()
        if not a.load_modules(db)['billing']:
            abort(404)
        return db
    @application.context_processor
    def client_context():
        # No client registry is included in a public or moderator form.
        if request.endpoint not in ('admin_billing','admin_billing_client_form','client_categories.new'):
            return {}
        from evolution_routes import actor
        db=a.get_database()
        if actor()!='admin' or not a.load_modules(db)['billing']:
            return {}
        entries=registry(db)
        return dict(client_categories=entries,client_category_labels={row['category_key']:row['name'] for row in entries},
            client_category_filter=request.args.get('client_category',''),client_search=request.args.get('client_q',''))
    @bp.post('/admin/facturation/categories')
    def save():
        db=guard();require_csrf()
        key=request.form.get('category_key') or 'client_'+uuid4().hex[:20]
        existing=db.execute('SELECT * FROM client_categories WHERE category_key=?',(key,)).fetchone()
        entry=dict(category_key=key,name=request.form.get('name','').strip(),active=int(request.form.get('active')=='1'),
            sort_order=existing['sort_order'] if existing else db.execute('SELECT COUNT(*) FROM client_categories').fetchone()[0])
        try:
            with db:
                import_registry(db,[entry])
                from evolution_schema import audit
                audit(db,'client_category',key,'saved','admin')
            flash('Catégorie de client enregistrée. Aucun droit ni document modifié.','success')
        except (ValueError,sqlite3.IntegrityError) as error:
            db.rollback();flash(str(error) if isinstance(error,ValueError) else 'Ce libellé est déjà utilisé.','error')
        return redirect(url_for('admin_billing',_anchor='annuaire-clients'))
    @bp.route('/admin/facturation/clients/nouveau',methods=['GET','POST'])
    def new():
        db=guard();values={}
        if request.method=='POST':
            require_csrf();values,errors=a.parse_billing_client_form(request.form)
            try:
                values['client_category']=selected(db,request.form.get('client_category'))
            except ValueError as error:
                errors.append(str(error))
            # An existing contact is never overwritten by the standalone create.
            if db.execute('SELECT 1 FROM billing_clients WHERE contact_name_normalized=?',(a.normalize_text_key(values.get('client_contact')),)).fetchone():
                errors.append('Ce client existe déjà : modifiez sa fiche dans l’annuaire.')
            if not errors:
                try:
                    db.execute('BEGIN IMMEDIATE')
                    if db.execute('SELECT 1 FROM billing_clients WHERE contact_name_normalized=?',(a.normalize_text_key(values.get('client_contact')),)).fetchone():
                        raise ValueError('Ce client vient d’être créé : utilisez sa fiche existante.')
                    a.upsert_billing_client(db,values)
                    db.commit()
                    flash('Fiche client créée, sans contrat ni droit automatique.','success')
                    return redirect(url_for('admin_billing',_anchor='annuaire-clients'))
                except (sqlite3.IntegrityError,ValueError):
                    db.rollback();errors.append('Ce client vient d’être créé : utilisez sa fiche existante.')
            for error in errors:flash(error,'error')
            return render_template('billing_client_form.html',client=None,values=values),400
        return render_template('billing_client_form.html',client=None,values=values)
    application.register_blueprint(bp)
