"""Private account service. Inputs arrive via the authenticated outgoing relay.

Transactions belong to the caller; no email/network side effect takes place in
an enrollment transaction. An ID, a name or a family contact is not a login.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from contextvars import ContextVar
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from uuid import uuid4
import family_model as family
import family_reservations as bookings

PUBLIC_REPLY = {'message':'Si votre demande est recevable, vous recevrez un e-mail. Sinon, contactez l’équipe.'}
SESSION_ERROR = 'Session expirée ou indisponible. Identifiez-vous à nouveau.'
EXPIRED = 'Ce lien n’est plus utilisable. Ouvrez-le dans le navigateur de la demande ou demandez un nouveau lien.'
PROFILE_FIELDS = ('first_name','last_name','birth_year','birth_date','gender','nationality','postal_code','city','email','phone','phone_country_code')
LANG=ContextVar('portal_language',default='fr')
def locale(value):return value if isinstance(value,str) and value in ('fr','en','de','es','fi') else 'fr'

def address(value):
    if not isinstance(value,str):
        raise ValueError('Adresse e-mail invalide.')
    value=value.strip().lower()
    if not value.isascii() or len(value)>254 or not re.fullmatch(r'[^@\s\x00-\x1f\x7f]+@[^@\s\x00-\x1f\x7f]+\.[^@\s\x00-\x1f\x7f]+',value):
        raise ValueError('Adresse e-mail invalide.')
    return value

def ttl(db,key,default,low,high):
    return 60*min(high,max(low,int(family.setting(db,'online_'+key+'_minutes',str(default)))))

def protect(db,env):
    if (env not in ('production','test') or family.setting(db,'online_accounts_enabled')!='1' or family.setting(db,'module_users','1')!='1'
            or family.setting(db,'online_relay_environment','production')!=env
            or env!=os.environ.get('OPENFABLAB_ONLINE_ENVIRONMENT','production')):
        raise ValueError('L’espace usager n’est pas disponible.')

def rate(db,secret,kind,value,limit,now):
    key=hmac.new(secret,('limit/online/'+kind+'/'+value).encode(),hashlib.sha256).hexdigest()
    count=db.execute('''INSERT INTO online_limits VALUES(?,?,1) ON CONFLICT(bucket,window)
        DO UPDATE SET hits=MIN(hits+1,1000) RETURNING hits''',(key,now//900)).fetchone()[0]
    return count<=limit

def mail(db,kind,email,now,browser='',req=None,owner=None,language=None):
    db.execute('INSERT INTO online_mail(kind,address,request_id,owner,browser,created,locale) VALUES(?,?,?,?,?,?,?)',
               (kind,email,req,owner,browser,now,locale(language or LANG.get())))

def event(db,kind,req,actor,now):
    db.execute('INSERT INTO online_events(kind,request_id,actor,created) VALUES(?,?,?,?)',(kind,req,actor,now))
    from reservation_notifications import queue, ONLINE_DISCORD_DEFAULTS
    if kind in ONLINE_DISCORD_DEFAULTS and family.setting(db,'online_discord_'+kind,ONLINE_DISCORD_DEFAULTS[kind])=='1':
        env=family.setting(db,'online_relay_environment','production') if actor not in ('admin','moderator') else 'production'
        # An online approval may be carried out by an administrator in a test
        # instance. No online events may leave that instance.
        if family.setting(db,'online_relay_environment','production')=='test':env='test'
        queue(db,'online/'+req+'/'+kind,'online_'+kind,environment=env)

def record_creation(db,kind,actor,now):
    event(db,kind,uuid4().hex,actor,now)
    if kind not in ('created','child_created'):return
    window=now//900
    volume=db.execute("SELECT count(*) FROM online_events WHERE created>=? AND kind IN ('created','child_created')",(window*900,)).fetchone()[0]
    ref='window-'+str(window)
    if volume>=12 and not db.execute("SELECT 1 FROM online_events WHERE kind='creation_volume' AND request_id=?",(ref,)).fetchone():
        event(db,'creation_volume',ref,'system',now)

def request_row(db,kind,values,email,browser,now,owner=None,verified=False):
    rid=uuid4().hex
    values=dict(values,_lang=LANG.get())
    db.execute('INSERT INTO online_requests VALUES(?,?,?,?,?,?,?,?)',
        (rid,kind,json.dumps(values,ensure_ascii=False),email,owner,'review' if verified else 'verify',
         now,now+(30*86400 if verified else 86400)))
    if not verified:
        mail(db,'verify',email,now,browser,rid)
    return rid

def person_values(db,fields,owner=None):
    from app import validate_user_form,next_available_public_id
    from evolution_schema import default_category
    values={k:fields.get(k,'') for k in PROFILE_FIELDS}
    if any(not isinstance(v,str) or len(v)>254 for v in values.values()):
        raise ValueError('Champs invalides.')
    if not values['birth_date'] and not values['birth_year']:
        raise ValueError('Indiquez votre année ou votre date de naissance.')
    if not values['birth_date'] and values['birth_year'].isascii() and values['birth_year'].isdigit():
        years=family.local_day(db).year-int(values['birth_year'])
        threshold=max(18,int(family.setting(db,'family_responsible_age','18')))
        if owner is not None or years<=threshold:
            raise ValueError('Indiquez la date de naissance complète pour vérifier les règles d’âge du FabLab.')
    values.update(public_id=next_available_public_id(db),active='1',category=default_category(db))
    values['phone_country_code']=values['phone_country_code'] or '+33'
    # Only the authenticated owner is supplied for a child's link. Do not use
    # the kiosk guardian session, and never accept arbitrary responsible IDs.
    if owner is not None:
        values['responsible_ids']=[str(owner)]
    return validate_user_form(values,db,public_enrollment=True,online_guardian=owner)

def new_user(db,data):
    from evolution_users import create_user
    return create_user(db,data,'online',notify_links=False)

def account(db,owner):
    return db.execute('''SELECT u.* FROM users u JOIN online_identities i ON i.user_id=u.id
        WHERE u.id=? AND u.active=1 AND lower(trim(u.email))=i.email''',(owner,)).fetchone()

def viewer(db,browser,now,fresh=False):
    s=db.execute('SELECT * FROM online_sessions WHERE browser=? AND expires>?',(browser,now)).fetchone()
    if not s or (fresh and s['issued']+600<=now) or not (u:=account(db,s['owner'])):
        raise ValueError(SESSION_ERROR)
    return u

def identifier_target(db,email):
    """One active adult; only their own verified family links may explain shared contacts."""
    rows=db.execute('SELECT * FROM users WHERE active=1 AND lower(trim(email))=?',(email,)).fetchall()
    today=family.local_day(db)
    adults=[row for row in rows if (family.age(row,today) or 0)>=18]
    if len(adults)!=1:return None
    target=adults[0]
    if len(rows)==1:return target
    if not family.eligible(db,target,today):return None
    children={p['id'] for p in family.members(db,target['id']) if (years:=family.age(p,today)) is not None and 0<=years<18}
    if all(row['id']==target['id'] or row['id'] in children for row in rows):return target
    return None

def claim_error(db,user,email):
    if not user or not user['active']:
        return 'Sélectionnez une fiche usager active.'
    if (user['email'] or '').strip().lower()!=email:
        return 'Sélectionnez une fiche portant l’adresse e-mail vérifiée dans la demande.'
    if (family.age(user,family.local_day(db)) or 0)<18 or family.state(db,user)!='responsible':
        return 'Vérifiez l’âge sur la fiche : l’accès individuel est réservé aux adultes qui atteignent aussi l’âge de responsabilité du FabLab.'
    if db.execute('SELECT 1 FROM online_identities WHERE email=? OR user_id=?',(email,user['id'])).fetchone():
        return 'Un accès existe déjà. Orientez l’usager vers la connexion ou la récupération d’identifiant.'
    return None

def child_duplicates(db,values,guardian):
    from app import find_possible_user_duplicates, normalize_text_key
    # Sharing contact with one’s own household is expected; do not suppress
    # a matching child name or a contact conflict outside that household.
    household={guardian['public_id'],*(p['public_id'] for p in family.members(db,guardian['id']))}
    name=tuple(normalize_text_key(values[k]) for k in ('first_name','last_name'))
    return [p for p in find_possible_user_duplicates(db,values) if p['public_id'] not in household
            or tuple(normalize_text_key(p[k]) for k in ('first_name','last_name'))==name]

def review_candidates(db,req,query=''):
    from app import find_possible_user_duplicates
    from admin_search import folded
    data=json.loads(req['data'])
    if req['kind']=='child':
        candidate_ids={p['public_id'] for p in find_possible_user_duplicates(db,dict(
            first_name=data.get('first_name',''),last_name=data.get('last_name',''),
            email='',phone=''))}
        rows=db.execute('SELECT * FROM users WHERE active=1 ORDER BY last_name,first_name')
    else:
        candidate_ids=None
        rows=db.execute('SELECT * FROM users WHERE active=1 AND lower(trim(email))=? ORDER BY last_name,first_name',(req['email'],))
    candidates=[]
    for row in rows:
        if req['kind']=='child':
            years=family.age(row,family.local_day(db))
            if years is None or not 0<=years<18:continue
            if not query and row['public_id'] not in candidate_ids:continue
        elif claim_error(db,row,req['email']):
            continue
        if query and not (query==row['public_id'] or any(folded(query) in folded(s) for s in
                (row['first_name']+' '+row['last_name'],row['last_name']+' '+row['first_name']))):
            continue
        candidates.append({k:row[k] for k in ('id','first_name','last_name','public_id')})
        if len(candidates)>=20:break
    return candidates

def begin(db,data,browser,secret,now):
    action=data['op']
    email=address(data.get('email'))
    if not rate(db,secret,'contact',email,4,now):
        return PUBLIC_REPLY
    if action=='signup':
        if family.setting(db,'online_signup_enabled')!='1':
            raise ValueError('La création de comptes en ligne est désactivée.')
        if data.get('consent') is not True:raise ValueError('Acceptez les informations de confidentialité.')
        fields={k:data.get(k,'') for k in PROFILE_FIELDS}
        fields['email']=email
        record,errors=person_values(db,fields)
        if errors:raise ValueError(' '.join(errors))
        if db.execute("SELECT 1 FROM online_requests WHERE email=? AND kind='signup' AND state='review' AND expires>?",(email,now)).fetchone():
            return PUBLIC_REPLY
        # Separate pending attempts: an unverified earlier submitter must
        # never inherit the identity or session of a later verified request.
        request_row(db,'signup',fields,email,browser,now)
    elif action=='recover':
        target=identifier_target(db,email)
        if target:
            mail(db,'recover',email,now,browser,owner=target['id'])
        elif db.execute('SELECT 1 FROM users WHERE active=1 AND lower(trim(email))=?',(email,)).fetchone():
            mail(db,'assistance',email,now)
    else:
        bound=db.execute('SELECT user_id FROM online_identities WHERE email=?',(email,)).fetchone()
        if bound and account(db,bound[0]):
            mail(db,action,email,now,browser,owner=bound[0])
        elif db.execute('SELECT 1 FROM users WHERE active=1 AND lower(trim(email))=?',(email,)).fetchone():
            request_row(db,'claim',{},email,browser,now)
    return PUBLIC_REPLY

def issue_ticket(db,row,now):
    token=secrets.token_urlsafe(32)
    db.execute('INSERT INTO online_tickets VALUES(?,?,?,?,?,?,?)',
               (hashlib.sha256(token.encode()).hexdigest(),row['kind'],row['address'],row['request_id'],
                row['owner'],row['browser'],now+ttl(db,'ticket',15,5,30)))
    return token

def activate(db,req,owner,now,actor):
    email=req['email']
    user=db.execute('SELECT * FROM users WHERE id=? AND active=1',(owner,)).fetchone()
    if error:=claim_error(db,user,email):
        raise ValueError(error)
    db.execute('INSERT INTO online_identities VALUES(?,?,?)',(owner,email,now))
    mail(db,'activated',email,now,owner=owner,language=json.loads(req['data']).get('_lang'))
    event(db,'activated',req['id'],actor,now)
    db.execute('DELETE FROM online_requests WHERE id=?',(req['id'],))

def confirm(db,token,browser,now):
    if not isinstance(token,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{43}',token):
        raise ValueError(EXPIRED)
    ticket=db.execute('DELETE FROM online_tickets WHERE digest=? AND expires>? AND browser=? RETURNING *',
        (hashlib.sha256(token.encode()).hexdigest(),now,browser)).fetchone()
    if not ticket:raise ValueError(EXPIRED)
    email=ticket['address']
    if ticket['purpose']=='verify':
        req=db.execute("SELECT * FROM online_requests WHERE id=? AND state='verify' AND expires>?",(ticket['request_id'],now)).fetchone()
        if not req:raise ValueError(EXPIRED)
        if req['kind']=='signup' and family.setting(db,'online_signup_enabled')!='1':raise ValueError(EXPIRED)
        if db.execute("SELECT 1 FROM online_requests WHERE email=? AND kind=? AND state='review' AND expires>?",(email,req['kind'],now)).fetchone():
            db.execute('DELETE FROM online_requests WHERE id=?',(req['id'],))
            return PUBLIC_REPLY
        if req['kind']=='signup' and family.setting(db,'online_approval','manual') in ('automatic','conditional'):
            from app import find_possible_user_duplicates
            value,errors=person_values(db,json.loads(req['data']))
            if not errors and (family.age(value,family.local_day(db)) or 0)>=18 and family.state(db,value)=='responsible' and not find_possible_user_duplicates(db,value):
                activate(db,req,new_user(db,value),now,'automatic')
                record_creation(db,'created','automatic',now)
                return {'message':'Votre adresse e-mail a été confirmée. Votre compte est prêt à être utilisé.'}
            if family.setting(db,'online_approval')=='automatic':
                mail(db,'assistance',email,now)
                db.execute('DELETE FROM online_requests WHERE id=?',(req['id'],))
                return PUBLIC_REPLY
        db.execute("UPDATE online_requests SET state='review',expires=? WHERE id=?",(now+30*86400,req['id']))
        mail(db,'review',email,now)
        event(db,'signup_review',req['id'],'email',now)
        return {'message':('Votre adresse e-mail a été confirmée. L’équipe va examiner votre demande d’accès.'
                           if req['kind']=='claim' else 'Votre adresse e-mail a été confirmée. Votre demande de compte est en attente de validation par le FabLab.')}
    else:
        owner=ticket['owner']
        if ticket['purpose']=='recover':
            target=identifier_target(db,email)
            if target and target['id']==owner:
                mail(db,'identifier',email,now,owner=owner)
            return PUBLIC_REPLY
        user=account(db,owner)
        if not user:raise ValueError(EXPIRED)
        if ticket['purpose']=='email':
            session_user=viewer(db,browser,now,True)
            if session_user['id']!=owner:raise ValueError(EXPIRED)
            if db.execute('SELECT 1 FROM users WHERE id<>? AND lower(trim(email))=?',(owner,email)).fetchone():
                raise ValueError('Adresse à vérifier avec votre équipe.')
            db.execute('UPDATE online_identities SET email=? WHERE user_id=?',(email,owner))
            db.execute('UPDATE users SET email=? WHERE id=?',(email,owner))
            db.execute('DELETE FROM online_sessions WHERE owner=?',(owner,))
            db.execute('DELETE FROM online_tickets WHERE owner=?',(owner,))
            db.execute('DELETE FROM online_mail WHERE owner=?',(owner,))
            event(db,'email_changed',uuid4().hex,'owner',now)
            return {'message':'Votre nouvelle adresse e-mail a été confirmée. Reconnectez-vous avec cette adresse.'}
        elif user['email'].strip().lower()!=email:
            raise ValueError(EXPIRED)
        elif ticket['purpose']=='login':
            db.execute('INSERT OR REPLACE INTO online_sessions VALUES(?,?,?,?)',
                (browser,owner,now+ttl(db,'session',20,5,60),now))
            return {'message':'Vous êtes maintenant connecté.','signed_in':True}
        else:raise ValueError(EXPIRED)

def review(db,rid,decision,existing=None,checked=False,now=None):
    """Only the authenticated admin route may call this inside a write transaction."""
    now=int(time.time()) if now is None else now
    req=db.execute("SELECT * FROM online_requests WHERE id=? AND state='review' AND expires>?",(rid,now)).fetchone()
    if not req:raise ValueError('Demande déjà traitée ou expirée.')
    if decision=='refuse':
        mail(db,'denied',req['email'],now,language=json.loads(req['data']).get('_lang'))
        event(db,'denied',rid,'admin',now)
    elif decision=='accept':
        if not checked:raise ValueError('Vérifiez l’identité et les autorisations avant de confirmer.')
        child=req['kind']=='child'
        created=not existing
        if not existing:
            if req['kind']=='claim':raise ValueError('Sélectionnez la fiche existante après avoir vérifié son identité.')
            value,errors=person_values(db,json.loads(req['data']),req['owner'] if child else None)
            if errors:raise ValueError(' '.join(errors))
            from app import find_possible_user_duplicates
            guardian=account(db,req['owner']) if child else None
            if (child_duplicates(db,value,guardian) if guardian else find_possible_user_duplicates(db,value)):
                raise ValueError('Doublon possible : sélectionnez la fiche correspondante si vous avez vérifié son identité.')
            existing=new_user(db,value)
        if not child:
            activate(db,req,existing,now,'admin')
            if created:record_creation(db,'created','admin',now)
            return
        guardian=account(db,req['owner'])
        if not guardian or not family.eligible(db,guardian) or guardian['email'].strip().lower()!=req['email'].strip().lower():
            raise ValueError('Le rattachement nécessite une nouvelle demande du responsable.')
        linked=db.execute('SELECT * FROM users WHERE id=? AND active=1',(existing,)).fetchone()
        if not linked or family.age(linked,family.local_day(db)) is None or family.age(linked,family.local_day(db))>=18:
            raise ValueError('Fiche enfant requise.')
        prior=any(p['id']==req['owner'] for p in family.responsibles(db,existing))
        family.link(db,existing,req['owner'],notify=not created)
        language=json.loads(req['data']).get('_lang')
        if created:
            mail(db,'child_welcome',req['email'],now,'guardian:'+str(req['owner']),owner=existing,language=language)
            record_creation(db,'child_created','admin',now)
        elif not prior:
            mail(db,'family_done',req['email'],now,language=language)
    else:raise ValueError('Décision inconnue.')
    db.execute('DELETE FROM online_requests WHERE id=?',(rid,))

def dispatch(db,data,env,secret,request_key,now=None):
    selected=LANG.set(locale(data.get('lang')))
    try:return _dispatch(db,data,env,secret,request_key,now)
    finally:LANG.reset(selected)

def _dispatch(db,data,env,secret,request_key,now):
    protect(db,env)
    now=int(time.time()) if now is None else now
    browser=data.get('browser')
    if not isinstance(browser,str) or not re.fullmatch('[a-f0-9]{64}',browser):raise ValueError(SESSION_ERROR)
    op=data.get('op')
    if op in ('options','bootstrap'):
        try:
            viewer(db,browser,now)
            logged_in=True
        except ValueError:logged_in=False
        result={'signup':family.setting(db,'online_signup_enabled')=='1','signed_in':logged_in}
        if logged_in and op=='bootstrap':
            result['profile']=_dispatch(db,dict(data,op='overview'),env,secret,request_key,now)
        return result
    if op in ('signup','login','recover'):
        return begin(db,data,browser,secret,now)
    if op=='confirm':
        result=confirm(db,data.get('ticket'),browser,now)
        if result.get('signed_in') and data.get('include_profile') is True:
            result['profile']=_dispatch(db,dict(data,op='overview'),env,secret,request_key,now)
        return result
    if op=='logout':
        db.execute('DELETE FROM online_sessions WHERE browser=?',(browser,))
        db.execute('DELETE FROM online_tickets WHERE browser=?',(browser,))
        db.execute('DELETE FROM online_mail WHERE browser=?',(browser,))
        return {'signed_out':True}
    u=viewer(db,browser,now,op in ('child','email','phone'))
    owner=u['id']
    people=[u]
    if family.eligible(db,u):
        people.extend(p for p in family.members(db,owner) if p['active']
                      and family.age(p,family.local_day(db)) is not None and family.age(p,family.local_day(db))<18)
    if op=='overview':
        ids=[p['id'] for p in people]
        rows=db.execute('''SELECT b.user_id,b.first_name,b.last_name,b.status,b.group_uuid,s.title,s.service_date,
            s.start_time,s.end_time,g.owner_id,sl.starts_at,sl.ends_at
            FROM animation_bookings b JOIN fablab_services s ON s.id=b.service_id
            LEFT JOIN family_booking_groups g ON g.group_uuid=b.group_uuid
            LEFT JOIN animation_slots sl ON sl.slot_uuid=b.slot_uuid AND sl.service_id=s.id
            WHERE b.environment=? AND b.user_id IN ('''+','.join('?' for _ in ids)+''')
            ORDER BY s.service_date DESC,b.created_at DESC LIMIT 100''',(env,*ids)).fetchall()
        local_date=family.local_day(db).isoformat()
        expires=db.execute('SELECT expires FROM online_sessions WHERE browser=?',(browser,)).fetchone()[0]
        zone=ZoneInfo(family.setting(db,'structure_timezone','Europe/Paris'))
        def summarize(row):
            day=row['service_date']
            hours='–'.join(filter(None,(row['start_time'],row['end_time'])))
            if row['starts_at'] and row['ends_at']:
                start,end=(datetime.fromisoformat(row[key]).astimezone(zone) for key in ('starts_at','ends_at'))
                day=start.date().isoformat()
                hours=f'{start:%H:%M}–{end:%H:%M}'
            return dict(title=row['title'],date=day,person=' '.join((row['first_name'],row['last_name'])).strip(),
                        status=row['status'],hours=hours,
                        cancel=row['group_uuid'] if row['owner_id']==owner and day>=local_date and
                        row['status'] in ('confirmed','waitlisted','offer_pending') else None)
        return {'session_seconds':max(0,expires-now),'today':local_date,'autonomy':int(family.setting(db,'family_autonomy_age','15')),
            'can_manage_family':family.eligible(db,u),'me':{k:u[k] for k in ('first_name','last_name','email','phone','phone_country_code','postal_code','city','public_id')},
            'people':[{k:p[k] for k in ('id','first_name','last_name','public_id')} for p in people],
            'reservations':[summarize(r) for r in rows]}
    if op=='qr':
        from base64 import b64encode
        from welcome_mail import qr_png
        member=data.get('person')
        if type(member) is not int or not (target:=next((p for p in people if p['id']==member),None)):
            raise ValueError('Ce QR Code n’est pas disponible depuis votre espace.')
        return {'png':b64encode(qr_png(target['public_id'])).decode('ascii')}
    if op=='child':
        if not family.eligible(db,u) or data.get('consent') is not True:raise ValueError('Responsable autorisé requis.')
        if not rate(db,secret,'family-create',str(owner),6,now):
            raise ValueError('Plusieurs demandes ont été faites récemment. Réessayez dans quelques minutes.')
        fields={k:data.get(k,'') for k in PROFILE_FIELDS}
        if data.get('same_address') is True:
            fields.update({k:u[k] or '' for k in ('postal_code','city')})
        if data.get('same_contact') is True:
            fields.update({k:u[k] or '' for k in ('email','phone','phone_country_code')})
        v,errors=person_values(db,fields,owner)
        if errors:raise ValueError(' '.join(errors))
        years=family.age(v,family.local_day(db))
        if years is None or not 0<=years<18:raise ValueError('Indiquez la date de naissance de l’enfant.')
        if child_duplicates(db,v,u):
            if not db.execute("SELECT 1 FROM online_requests WHERE kind='child' AND owner=? AND json_extract(data,'$.first_name')=? AND json_extract(data,'$.last_name')=? AND json_extract(data,'$.birth_date')=? AND expires>?",(owner,fields['first_name'],fields['last_name'],fields['birth_date'],now)).fetchone():
                rid=request_row(db,'child',fields,u['email'],browser,now,owner,True)
                event(db,'family_review',rid,'owner',now)
            return {'message':'La demande de rattachement est en attente de validation par le FabLab.'}
        else:
            child_id=new_user(db,v)
            record_creation(db,'child_created','owner',now)
            mail(db,'child_welcome',u['email'],now,'guardian:'+str(owner),owner=child_id)
        return {'message':'Votre enfant a bien été ajouté à votre famille.'}
    if op=='email':
        value=address(data.get('email'))
        if rate(db,secret,'email-change',str(owner),3,now):mail(db,'email',value,now,browser,owner=owner)
        return PUBLIC_REPLY
    if op=='phone':
        from app import PHONE_PATTERN,PHONE_COUNTRY_CODE_PATTERN,normalize_user_phone
        value=data.get('phone','')
        code=data.get('phone_country_code',u['phone_country_code'] or '+33')
        if not isinstance(code,str) or len(code)>7 or not PHONE_COUNTRY_CODE_PATTERN.fullmatch(code):
            raise ValueError('Indiquez un indicatif international, par exemple +33.')
        if not isinstance(value,str) or len(value)>30 or (value and (not PHONE_PATTERN.fullmatch(value) or len(re.sub(r'\D','',value))>15)):
            raise ValueError('Numéro de téléphone invalide.')
        code,phone=normalize_user_phone(code,value)
        if family.missing_contacts(family.contact_policy(db,u),dict(u,phone=phone)):raise ValueError('Numéro de téléphone requis.')
        db.execute('UPDATE users SET phone_country_code=?,phone=? WHERE id=?',(code,phone,owner))
        return {'message':'Téléphone enregistré.'}
    if op=='reserve':
        ids=data.get('participants')
        if (data.get('consent') is not True or not isinstance(ids,list) or not 1<=len(ids)<=20
                or any(type(i) is not int or i not in {p['id'] for p in people} for i in ids)):
            raise ValueError('Sélectionnez les participants et confirmez le nombre de places.')
        sid,slot=data.get('service_id'),data.get('slot_uuid')
        if type(sid) is not int or not 0<sid<2**63 or (slot is not None and (not isinstance(slot,str) or len(slot)>64)):
            raise ValueError('Animation ou créneau indisponible.')
        from outbound_actions import public_catalogue
        if not any(a['service_id']==sid for a in public_catalogue(db,env,include_limits=True)):
            raise ValueError('Animation indisponible.')
        result=bookings.reserve(db,owner,ids,sid,slot or None,request_key,env,'wordpress')
        return {k:result[k] for k in ('count','status')}
    if op in ('cancel','accept_offer','decline_offer'):
        if data.get('consent') is not True or not isinstance(data.get('group'),str) or len(data['group'])>64:
            raise ValueError('Confirmez votre choix pour ce groupe.')
        g=db.execute('SELECT * FROM family_booking_groups WHERE group_uuid=? AND owner_id=? AND environment=?',
                     (data.get('group'),owner,env)).fetchone()
        if not g:raise ValueError('Réservation indisponible.')
        from family_waitlist import respond_as_owner
        return {'status':respond_as_owner(db,g['group_uuid'],owner,env,{'cancel':'cancel','accept_offer':'accept','decline_offer':'decline'}[op])['status']}
    raise ValueError('Action indisponible.')

def prune(db,now):
    for table in ('online_requests','online_tickets','online_sessions'):
        db.execute('DELETE FROM '+table+' WHERE expires<=?',(now,))
    db.execute('DELETE FROM online_limits WHERE window<?',(now//900-1,))
    db.execute('DELETE FROM online_mail WHERE created<?',(now-86400,))
    db.execute('DELETE FROM online_events WHERE created<?',(now-90*86400,))
