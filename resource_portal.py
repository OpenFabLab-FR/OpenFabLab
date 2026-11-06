"""Permanent UUID resource pages, shared PDFs and optional public QR access."""
import io
from ipaddress import ip_address, ip_network
import sqlite3
from pathlib import Path
from urllib.parse import unquote,urlsplit,urlunsplit
from uuid import UUID
from flask import Blueprint,Response,abort,current_app,flash,redirect,render_template,request,send_file,session,url_for
from werkzeug.utils import secure_filename
from evolution_routes import csrf_token,require_csrf,require_team
from family_model import setting
from i18n import t
import machine_maintenance as machines
import resource_documents as documents
import resource_loans as loans
import resource_reports as reports


PRIVATE_NETWORKS=tuple(map(ip_network,('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','fc00::/7')))

def _base(value,local=False):
    value=str(value or '').strip().rstrip('/')
    if not value:return ''
    error='Indiquez une adresse HTTP ou HTTPS utilisant une IP privée du réseau local.' if local else 'Utilisez l’adresse HTTPS complète d’OpenFabLab, sans secret, paramètre ni fragment.'
    try:
        parsed=urlsplit(value)
        port=parsed.port
        if local and not any(ip_address(parsed.hostname or '') in network for network in PRIVATE_NETWORKS):raise ValueError
    except ValueError:raise ValueError(error) from None
    decoded=unquote(parsed.path)
    if (parsed.scheme not in (('http','https') if local else ('https',)) or not parsed.hostname
            or parsed.username is not None or parsed.password is not None or '?' in value or '#' in value
            or any(ord(c)<=32 for c in value+decoded) or '\\' in value+decoded
            or '%' in decoded or any(part in ('.','..') for part in decoded.split('/'))
            or port is not None and not 1<=port<=65535):
        raise ValueError(error)
    return urlunsplit((parsed.scheme,parsed.netloc,parsed.path.rstrip('/'),'',''))

def public_base(value):
    return _base(value)

def local_base(value):
    return _base(value,local=True)

def resource_url(db,key):
    local=setting(db,'resource_qr_access','public')=='local'
    base=local_base(setting(db,'resource_local_base_url')) if local else public_base(setting(db,'resource_public_base_url'))
    if not base:raise ValueError('Configurez l’adresse des fiches QR dans les réglages des ressources.')
    return base+'/r/'+str(UUID(key))


def public_resource(db,key):
    if setting(db,'resource_public_pages_enabled','0')!='1':abort(404)
    item=next((r for r in machines.public_machines(db,details=True) if r['id']==key),None)
    if item is None:abort(404)
    return item


def label_pdf(name,category,url):
    import segno
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A6
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph
    from xml.sax.saxutils import escape
    fonts=Path(__file__).parent/'static/fonts'
    if 'OFLLabel' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('OFLLabel',str(fonts/'LibreFranklin-Regular.ttf')))
        pdfmetrics.registerFont(TTFont('OFLLabelBold',str(fonts/'LibreFranklin-Bold.ttf')))
    from reportlab.pdfgen import canvas
    output=io.BytesIO();pdf=canvas.Canvas(output,pagesize=A6)
    pdf.setTitle('OpenFabLab - '+name);pdf.setAuthor('OpenFabLab')
    width,height=A6;margin=9*mm
    pdf.setFillColor(colors.HexColor('#14778c'));pdf.setFont('OFLLabelBold',9)
    pdf.drawString(margin,height-margin-8,'OpenFabLab')
    title=Paragraph(escape(name),ParagraphStyle('resource',fontName='OFLLabelBold',fontSize=13,leading=16,textColor=colors.HexColor('#17333c')))
    _,title_height=title.wrap(width-2*margin,35*mm)
    title.drawOn(pdf,margin,height-20*mm-title_height)
    helptext=Paragraph(escape(t('Scannez pour consulter l’état et les tutoriels.')),ParagraphStyle('scan',fontName='OFLLabel',fontSize=9,leading=12,alignment=1))
    _,help_height=helptext.wrap(width-2*margin,25*mm)
    qr=segno.make(url,error='m',micro=False)
    matrix=list(qr.matrix);quiet=4
    size=min(69*mm,height-24*mm-title_height-7*mm-help_height-20*mm)
    unit=size/(len(matrix)+quiet*2)
    left=(width-size)/2;bottom=height-24*mm-title_height-size
    pdf.setFillColor(colors.white);pdf.rect(left,bottom,size,size,fill=1,stroke=0)
    pdf.setFillColor(colors.black)
    for y,row in enumerate(matrix):
        for x,value in enumerate(row):
            if value:pdf.rect(left+(x+quiet)*unit,bottom+size-(y+quiet+1)*unit,unit+.01,unit+.01,fill=1,stroke=0)
    helptext.drawOn(pdf,margin,bottom-7*mm-help_height)
    pdf.setFillColor(colors.HexColor('#637279'));pdf.setFont('OFLLabel',7)
    pdf.drawCentredString(width/2,9*mm,urlsplit(url).hostname)
    pdf.showPage();pdf.save();return output.getvalue()


def register(application,namespace):
    from types import SimpleNamespace
    a=SimpleNamespace(**namespace)
    bp=Blueprint('resource_portal',__name__)
    def team_resource(key,write=False):
        role=require_team();db=a.get_database()
        if not a.load_modules(db)['resources'] and not machines.enabled(db):abort(404)
        try:item=documents.require_resource(db,key,role,write)
        except ValueError:abort(404)
        return db,item,role

    @bp.route('/admin/ressources/<key>/fiche',methods=['GET','POST'])
    def page(key):
        db,item,role=team_resource(key)
        modules=a.load_modules(db);error_action=None;retained={}
        if request.method=='POST':
            require_csrf()
            try:
                action=request.form.get('action')
                if action=='import':
                    uploads=[u for u in request.files.getlist('pdf') if u.filename]
                    if not 1<=len(uploads)<=8:raise ValueError('Choisissez de un à huit PDF.')
                    with __import__('memberships').atomic(db):
                        for upload in uploads:
                            values=dict(request.form)
                            if len(uploads)>1 or not values.get('title'):values['title']=Path(upload.filename).stem[:180]
                            documents.import_pdf(db,current_app.config['DATABASE'],key,upload,values,role)
                elif action=='attach':
                    with __import__('memberships').atomic(db):documents.attach(db,key,request.form.get('document'),role)
                elif action in ('update','detach'):
                    documents.modify(db,current_app.config['DATABASE'],key,request.form.get('document'),request.form,role,request.files.get('pdf'))
                elif action in ('general','booking_settings','legacy_prices'):
                    require_team(admin=True)
                    import resource_editor
                    with __import__('memberships').atomic(db):
                        if action=='legacy_prices':
                            if not modules['billing'] or not modules['rentals']:abort(404)
                            resource_editor.save_legacy_prices(db,key,request.form,role,a)
                        else:resource_editor.save_fields(db,key,request.form,role,action,modules)
                elif action=='report':
                    report_id=request.form.get('report_id','')
                    with __import__('memberships').atomic(db):
                        intervention=reports.decide(db,key,report_id,request.form.get('decision'),role,request.form.get('reason'))
                    flash('Décision enregistrée.','success')
                    if request.form.get('decision')=='intervention':
                        return redirect(url_for('resource_portal.page',key=key)+'#intervention-'+intervention)
                    return redirect(url_for('resource_portal.page',key=key,report=report_id)+'#signalement-'+report_id)
                elif action in ('maintenance_slot','maintenance_slot_cancel'):
                    if not machines.enabled(db):abort(404)
                    from maintenance_planning import save
                    with __import__('memberships').atomic(db):
                        slot=save(db,key,request.form,role,cancel=action=='maintenance_slot_cancel')
                    flash('Planning de maintenance enregistré.','success')
                    return redirect(url_for('resource_portal.page',key=key,_anchor='maintenance-'+slot))
                elif action in ('condition','intervention','reminder','reminder_reschedule','reminder_cancel','reminder_close'):
                    if not machines.enabled(db):abort(404)
                    with __import__('memberships').atomic(db):
                        if action=='condition':machines.set_condition(db,key,request.form,role,role)
                        elif action=='intervention':machines.intervention(db,key,request.form,role,role,request.form.get('identifier') or None)
                        elif action=='reminder':machines.reminder(db,key,request.form,role,role,request.form.get('identifier') or None)
                        else:machines.reminder_action(db,key,request.form,role,role)
                elif action in ('handover','return'):
                    kind=request.form.get('loan_kind');operation_key=request.form.get('loan_key')
                    if kind=='contract':
                        require_team(admin=True)
                        if not modules['billing'] or not modules['rentals']:abort(404)
                    elif kind!='booking' or not modules['resources']:abort(404)
                    if not any(r['kind']==kind and r['key']==operation_key for r in loans.operations(db,key)):
                        raise ValueError('Cette opération ne concerne pas cette ressource.')
                    loans.transition(db,kind,operation_key,action,role,request.form.get('user_id') or None)
                elif action in ('archive','restore','delete'):
                    require_team(admin=True)
                    with __import__('memberships').atomic(db):__import__('resource_lifecycle').change(db,key,action,role,request.form.get('confirm_delete',''))
                else:abort(400)
                flash('Fiche de la ressource enregistrée.','success')
                if action=='delete':return redirect(url_for('evolution.resource_directory'))
                section={'general':'general','booking_settings':'bookings','legacy_prices':'bookings','condition':'availability',
                    'intervention':'interventions','reminder':'reminders','reminder_reschedule':'reminders','reminder_cancel':'reminders','reminder_close':'reminders',
                    'archive':'advanced','restore':'advanced','handover':'loans','return':'loans'}.get(action,'documents')
                return redirect(url_for('resource_portal.page',key=key)+'#'+section)
            except (ValueError,sqlite3.IntegrityError) as error:
                db.rollback();flash(str(error) if isinstance(error,ValueError) else 'Référence incompatible. Aucune modification enregistrée.','error')
                error_action=action;retained=dict(request.form)
        def submitted(action,field,default='',target=''):
            selected=retained.get('identifier') or retained.get('reminder_id') or retained.get('document') or retained.get('loan_key') or ''
            return retained.get(field,'') if action==error_action and selected==str(target or '') else default
        def form_failed(action,target=''):
            return bool(error_action==action and submitted(action,'action',None,target)==action)
        url=None
        try:url=resource_url(db,key)
        except ValueError:pass
        category=db.execute('SELECT name FROM resource_types WHERE type_key=?',(item['type_key'],)).fetchone()
        context=__import__('resource_editor').context(db,key,role,modules,a)
        report_rows,report_page,report_more=reports.list_reports(db,key,max(1,min(100000,request.args.get('reports',1,type=int))),
            request.args.get('report') or retained.get('report_id'))
        edit_resource=dict(context['resource'])
        if error_action=='general':edit_resource.update({k:retained.get(k,'') for k in ('name','type_key','description','color')});edit_resource['color']=None if retained.get('color_default')=='1' else retained.get('color')
        return render_template('resource_page.html',**context,edit_resource=edit_resource,error_action=error_action,submitted=submitted,form_failed=form_failed,category=category[0] if category else '',
            availability=loans.availability(db,key),documents=documents.items(db,key),
            library=db.execute('SELECT document_uuid,title,language FROM resource_documents WHERE archived_at IS NULL AND document_uuid NOT IN(SELECT document_uuid FROM resource_document_links WHERE resource_uuid=?) ORDER BY title LIMIT 500',(key,)).fetchall(),
            public_url=url,public_pages_enabled=setting(db,'resource_public_pages_enabled','0')=='1',
            public_visible=context['resource']['public_visible'],evolution_csrf=csrf_token(),
            reports=report_rows,report_page=report_page,report_more=report_more,report_states=reports.STATES,
            report_actions=reports.ACTIONS,report_retained=retained),400 if error_action else 200

    @bp.route('/r/<key>',methods=['GET','POST'])
    def public_page(key):
        db=a.get_database();item=public_resource(db,key)
        report_enabled=reports.enabled(db)
        error='';description='';status=200
        if request.method=='POST':
            if not report_enabled:abort(404)
            request.max_content_length=8192
            require_csrf()
            description=request.form.get('description','')
            try:
                with __import__('memberships').atomic(db):
                    item=public_resource(db,key)
                    if not reports.enabled(db):abort(404)
                    result=None if request.form.get('website') else reports.submit(
                        db,key,description,request.remote_addr,current_app.secret_key)
            except reports.Throttled as problem:
                error=t(str(problem));status=429
            except ValueError as problem:
                error=t(str(problem));status=400
            else:
                if result:
                    try:notify_report(db,key,item['name'],*result)
                    except (OSError,ValueError):pass  # notification cannot undo the report
                flash(t('Merci, votre signalement a été transmis à l’équipe.'),'success')
                return redirect(url_for('resource_portal.public_page',key=key)+'#signalement',code=303)
        response=Response(render_template('resource_public.html',resource=item,documents=documents.items(db,key,True),
            status_label=loans.LABELS.get(item['status'],'Indisponible'),report_enabled=report_enabled,
            report_error=error,report_description=description[:500],evolution_csrf=csrf_token() if report_enabled else None),status=status)
        response.headers['Cache-Control']='private, no-store'
        return response

    def notify_report(db,key,name,report_id,description,received):
        if setting(db,'resource_reports_discord','0')!='1' or not a.load_modules(db)['discord']:
            return
        settings=a.load_discord_settings(db)
        webhook=a.read_discord_webhook()
        if not settings['enabled'] or not webhook:
            return
        from zoneinfo import ZoneInfo
        from localized_formats import day
        import re
        local=received.astimezone(ZoneInfo(setting(db,'structure_timezone','Europe/Paris')))
        base=resource_url(db,key).rsplit('/r/',1)[0]
        path=url_for('resource_portal.page',key=key,report=report_id,_anchor='signalement-'+report_id)
        link=base+path.removeprefix(request.script_root)
        def plain(value):
            return re.sub(r'([\\\x60*_~|<>\[\]])',r'\\\1',value)
        message=t('Nouveau signalement')+' · '+plain(name)+'\n'+day(local.date())+' · '+local.strftime('%H:%M')
        message+='\n'+plain(description)+'\n<'+link+'>'
        # Persisted before this best-effort dispatch. No duplicate on retry.
        a.send_discord_plain(webhook,message,settings['bot_name'])

    @bp.get('/admin/ressources/<key>/documents/<document>.pdf')
    def internal_pdf(key,document):
        db,_,_=team_resource(key)
        return pdf_response(db,key,document,False)

    @bp.get('/r/<key>/documents/<document>.pdf')
    def public_pdf(key,document):
        db=a.get_database();public_resource(db,key)
        return pdf_response(db,key,document,True)

    def pdf_response(db,key,document,public_only):
        row=next((r for r in documents.items(db,key,public_only) if r['document_uuid']==document),None)
        if row is None:abort(404)
        try:path=documents.blob_path(current_app.config['DATABASE'],row)
        except ValueError:abort(404)
        response=send_file(path,mimetype='application/pdf',as_attachment=request.args.get('download')=='1',
            download_name=(secure_filename(row['title']) or document)+'.pdf',conditional=False,max_age=0)
        response.headers.update({'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff',
            'Content-Security-Policy':"sandbox; default-src 'none'; frame-ancestors 'self'",'Referrer-Policy':'no-referrer'})
        return response

    @bp.get('/admin/ressources/<key>/qr.<image_format>')
    def qr(key,image_format):
        db,item,_=team_resource(key)
        if image_format not in ('png','svg','pdf'):abort(404)
        try:url=resource_url(db,key)
        except (ValueError,TypeError):abort(409,'Configurez l’adresse des fiches QR dans les réglages des ressources.')
        import segno
        if image_format=='pdf':
            content=label_pdf(item['name'],'',url);mime='application/pdf'
        else:
            output=io.BytesIO();segno.make(url,error='m',micro=False).save(output,kind=image_format,scale=8,border=4)
            content=output.getvalue();mime='image/png' if image_format=='png' else 'image/svg+xml'
        return Response(content,mimetype=mime,headers={'Content-Disposition':'attachment; filename="ressource-'+key+'.'+image_format+'"',
            'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})

    @bp.route('/admin/reglages/ressources',methods=['GET','POST'])
    def settings():
        require_team(admin=True);db=a.get_database()
        mode=setting(db,'resource_qr_access','public')
        remote=setting(db,'resource_public_base_url')
        local=setting(db,'resource_local_base_url')
        enabled=setting(db,'resource_public_pages_enabled','0')=='1'
        report_enabled=reports.enabled(db)
        report_discord=setting(db,'resource_reports_discord','0')=='1'
        if request.method=='POST':
            require_csrf()
            mode=request.form.get('access','public')
            remote=request.form.get('base_url',remote)
            local=request.form.get('local_url',local)
            enabled=request.form.get('enabled')=='1'
            report_enabled=request.form.get('reports_enabled')=='1'
            report_discord=request.form.get('reports_discord')=='1'
            try:
                if mode not in ('public','local'):raise ValueError('Choisissez un accès local ou public.')
                remote,local=public_base(remote),local_base(local)
                if enabled and not (local if mode=='local' else remote):raise ValueError('Renseignez l’adresse du mode d’accès choisi.')
                a.write_setting(db,'resource_public_base_url',remote)
                a.write_setting(db,'resource_local_base_url',local)
                a.write_setting(db,'resource_qr_access',mode)
                a.write_setting(db,'resource_public_pages_enabled',str(int(enabled)))
                a.write_setting(db,'resource_reports_enabled',str(int(report_enabled)))
                a.write_setting(db,'resource_reports_discord',str(int(report_discord)))
                db.commit();flash('Réglages des fiches ressources enregistrés.','success')
            except ValueError as error:flash(str(error),'error')
            else:return redirect(url_for('resource_portal.settings'))
        return render_template('resource_settings.html',public_base=remote,local_base=local,access=mode,
            pages_enabled=enabled,reports_enabled=report_enabled,reports_discord=report_discord,
            evolution_csrf=csrf_token()),400 if request.method=='POST' else 200

    application.register_blueprint(bp)
