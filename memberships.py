"""Optional entitlements. Integer balances, immutable terms and audited movements.

All mutating functions join the caller transaction or acquire BEGIN IMMEDIATE.
No transport, user creation, payment or reservation logic belongs here.
"""
import calendar
import hashlib
import json
import re
from contextlib import contextmanager
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal,InvalidOperation
from uuid import uuid4
from zoneinfo import ZoneInfo

KINDS={'period','credits'};UNITS={'none','passage','session','hour','halfday'}
MAX_BALANCE=1_000_000_000_000

class EntryDenied(ValueError):pass

def setting(db,key,default=''):
    row=db.execute('SELECT value FROM app_settings WHERE key=?',(key,)).fetchone()
    return row[0] if row else default

def enabled(db):return setting(db,'module_memberships','0')=='1'
def stamp():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def zone(db):return ZoneInfo(setting(db,'structure_timezone','Europe/Paris'))
def today(db):return datetime.now(zone(db)).date()
def pack(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def hashed(value):return hashlib.sha256(str(value).encode()).hexdigest()

@contextmanager
def atomic(db):
    nested=db.in_transaction
    marker='membership_'+uuid4().hex
    db.execute('SAVEPOINT '+marker if nested else 'BEGIN IMMEDIATE')
    try:
        yield
        db.execute('RELEASE '+marker) if nested else db.commit()
    except Exception:
        if nested:
            db.execute('ROLLBACK TO '+marker);db.execute('RELEASE '+marker)
        else:db.rollback()
        raise

def text(value,label,maximum=160,required=False):
    value=str(value or '').strip()
    if len(value)>maximum or any(ord(c)<32 and c not in '\n\t' for c in value) or (required and not value):
        raise ValueError(label+' : texte lisible requis, '+str(maximum)+' caractères maximum.')
    return value

def integer(value,label,minimum=0,maximum=100000):
    if isinstance(value,bool) or not re.fullmatch(r'-?\d+',str(value or '0')):raise ValueError(label+' invalide.')
    result=int(value or 0)
    if not minimum<=result<=maximum:raise ValueError(label+' hors limites.')
    return result

def units(value,terms):
    try:
        amount=Decimal(str(value).replace(',','.'))
        result=amount*(int(terms.get('unit_minutes',60))*60 if terms['unit']=='hour' else 1)
        if not result.is_finite() or result!=result.to_integral_value() or not 0<=result<=MAX_BALANCE:raise ValueError()
        return int(result)
    except (ValueError,InvalidOperation):raise ValueError('Quantité positive et précise requise (secondes entières pour les heures).') from None

def amount_label(value,terms):
    if terms['unit']=='hour':
        number=Decimal(value)/Decimal(int(terms.get('unit_minutes',60))*60)
        return format(number.quantize(Decimal('.001')),'f').rstrip('0').rstrip('.').replace('.',',')+' crédit(s) horaire(s)'
    return str(value)+' '+{'passage':'passage(s)','session':'séance(s)','halfday':'demi-journée(s)','none':'droit(s)'}[terms['unit']]

def validate_plan(values):
    name=text(values.get('name'),'Nom',120,True);description=text(values.get('description'),'Description',2000)
    kind=values.get('kind');scope=values.get('scope');unit=values.get('unit')
    if kind not in KINDS or scope not in {'individual','family'} or unit not in UNITS:raise ValueError('Type, bénéficiaires ou unité invalides.')
    if (kind=='period')!=(unit=='none'):raise ValueError('Un droit de période ne consomme pas de crédits.')
    validity=values.get('validity_unit','years')
    if validity not in {'days','weeks','months','years','fixed'}:raise ValueError('Durée de validité invalide.')
    quantity=integer(values.get('validity_value',1),'Durée',1,1000)
    fixed=str(values.get('fixed_end') or '')
    if validity=='fixed':date.fromisoformat(fixed)
    terms=dict(kind=kind,scope=scope,unit=unit,validity_unit=validity,validity_value=quantity,fixed_end=fixed,
               unit_minutes=integer(values.get('unit_minutes',60),'Durée d’un crédit',1,1440),
               grace_minutes=integer(values.get('grace_minutes',15),'Délai de retour',0,240))
    terms['quantity']=units(values.get('quantity',0),terms) if kind=='credits' else 0
    windows=values.get('halfday_windows',[['08:00','13:00'],['13:00','20:00']])
    if isinstance(windows,str):
        try:windows=json.loads(windows)
        except ValueError:raise ValueError('Plages de demi-journée invalides.') from None
    if not isinstance(windows,list) or not 1<=len(windows)<=8:raise ValueError('Définir une à huit plages de demi-journée.')
    normalized=[]
    for item in windows:
        if not isinstance(item,list) or len(item)!=2 or not all(isinstance(v,str) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',v) for v in item) or item[0]>=item[1]:
            raise ValueError('Chaque plage doit avoir un début et une fin le même jour.')
        normalized.append(item)
    normalized.sort()
    if any(a[1]>b[0] for a,b in zip(normalized,normalized[1:])):raise ValueError('Les plages ne doivent pas se chevaucher.')
    terms['halfday_windows']=normalized
    price=integer(values.get('price_cents',0),'Prix en centimes',0,100000000)
    return dict(name=name,description=description,kind=kind,scope=scope,unit=unit,price_cents=price,terms=terms)

def save_plan(db,values,plan_id=None,creation_key=None):
    value=validate_plan(values);now=stamp()
    with atomic(db):
        if plan_id:
            if not db.execute('SELECT 1 FROM membership_plans WHERE plan_id=?',(plan_id,)).fetchone():raise ValueError('Formule inconnue.')
            db.execute('UPDATE membership_plans SET name=?,description=?,kind=?,scope=?,unit=?,price_cents=?,terms_json=?,updated_at=? WHERE plan_id=?',
                (value['name'],value['description'],value['kind'],value['scope'],value['unit'],value['price_cents'],pack(value['terms']),now,plan_id))
        else:
            plan_id=hashed('plan/'+creation_key)[:32] if creation_key else uuid4().hex
            old=db.execute('SELECT * FROM membership_plans WHERE plan_id=?',(plan_id,)).fetchone()
            if old:
                if any(old[key]!=value[key] for key in ('name','description','kind','scope','unit','price_cents')) or old['terms_json']!=pack(value['terms']):raise ValueError('Cette création de formule a déjà été utilisée avec un autre contenu.')
                return plan_id
            db.execute('INSERT INTO membership_plans VALUES(?,?,?,?,?,?,?,?,1,?,?)',
                (plan_id,value['name'],value['description'],value['kind'],value['scope'],value['unit'],value['price_cents'],pack(value['terms']),now,now))
    return plan_id

def end_date(start,terms):
    start=date.fromisoformat(str(start));count=terms['validity_value'];unit=terms['validity_unit']
    if unit=='fixed':end=date.fromisoformat(terms['fixed_end'])
    elif unit in {'days','weeks'}:end=start+timedelta(days=count*(7 if unit=='weeks' else 1)-1)
    else:
        months=count*(12 if unit=='years' else 1);index=start.year*12+start.month-1+months
        year,month=divmod(index,12);month+=1
        last=calendar.monthrange(year,month)[1]
        target=date(year,month,min(start.day,last))
        end=target if start.day>last else target-timedelta(days=1)
    if end<start:raise ValueError('La fin de validité précède le début.')
    return end

def related(db,owner,member):
    if owner==member:return True
    links=db.execute('SELECT member_id,responsible_id FROM user_family_links WHERE ended_at IS NULL').fetchall()
    graph={}
    for a,b in links:graph.setdefault(a,set()).add(b);graph.setdefault(b,set()).add(a)
    reach={owner}
    for _ in range(2):reach|={p for a in tuple(reach) for p in graph.get(a,set())}
    return member in reach

def validate_beneficiaries(db,owner,people,scope):
    owner=int(owner);people=sorted(set(int(i) for i in people))
    if not people or len(people)>100 or (scope=='individual' and people!=[owner]):raise ValueError('Sélectionnez explicitement les bénéficiaires autorisés.')
    for person in set(people)|{owner}:
        if not db.execute('SELECT 1 FROM users WHERE id=? AND active=1',(person,)).fetchone():raise ValueError('Compte bénéficiaire inactif ou inconnu.')
        if scope=='family' and not related(db,owner,person):raise ValueError('Ce bénéficiaire ne possède pas de lien familial enregistré avec le titulaire.')
    return people

def prior(db,key,payload):
    key=hashed(key);digest=hashed(pack(payload))
    row=db.execute('SELECT * FROM membership_ledger WHERE operation_key=?',(key,)).fetchone()
    if row and row['request_hash']!=digest:raise ValueError('Cette opération a déjà été utilisée avec un autre contenu.')
    return key,digest,row

def movement(db,grant_id,quantity,kind,key,payload,actor='system',reason='',user_id=None,session_id=None,reversal_of=None,charge_key=None):
    key,digest,old=prior(db,key,payload)
    if old:return dict(old)
    grant=db.execute('SELECT * FROM membership_grants WHERE grant_id=?',(grant_id,)).fetchone()
    if not grant:raise ValueError('Attribution inconnue.')
    balance=grant['balance']+quantity
    if not 0<=balance<=MAX_BALANCE:raise ValueError('L’opération dépasserait le solde autorisé.')
    if actor not in {'system','admin'}:raise ValueError('Auteur non autorisé.')
    db.execute('UPDATE membership_grants SET balance=?,revision=revision+1 WHERE grant_id=?',(balance,grant_id))
    db.execute('INSERT INTO membership_ledger VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (key,digest,grant_id,user_id,session_id,kind,quantity,balance,actor,text(reason,'Motif',300),stamp(),reversal_of,charge_key))
    return dict(db.execute('SELECT * FROM membership_ledger WHERE operation_key=?',(key,)).fetchone())

def assign(db,plan_id,owner,people,starts_on,key,renew_from=None):
    payload=dict(plan=plan_id,owner=int(owner),people=sorted(set(int(p) for p in people)),start=str(starts_on),renew=renew_from)
    with atomic(db):
        op,digest,old=prior(db,key,payload)
        if old:return old['grant_id']
        plan=db.execute('SELECT * FROM membership_plans WHERE plan_id=? AND active=1',(plan_id,)).fetchone()
        if not plan:raise ValueError('Formule inactive ou inconnue.')
        terms=json.loads(plan['terms_json']);people=validate_beneficiaries(db,owner,people,plan['scope'])
        start=date.fromisoformat(str(starts_on))
        if renew_from:
            previous=db.execute('SELECT * FROM membership_grants WHERE grant_id=?',(renew_from,)).fetchone()
            if not previous or previous['owner_id']!=int(owner):raise ValueError('Attribution précédente incompatible.')
            latest=db.execute('SELECT MAX(ends_on) FROM membership_grants WHERE owner_id=? AND plan_id=?',(int(owner),plan_id)).fetchone()[0]
            start=max(start,date.fromisoformat(previous['ends_on'])+timedelta(days=1),date.fromisoformat(latest or previous['ends_on'])+timedelta(days=1))
        end=end_date(start,terms);grant=uuid4().hex;now=stamp()
        snapshot=dict(terms,name=plan['name'],description=plan['description'],price_cents=plan['price_cents'])
        db.execute('INSERT INTO membership_grants(grant_id,plan_id,owner_id,terms_json,starts_on,ends_on,created_at) VALUES(?,?,?,?,?,?,?)',
            (grant,plan_id,int(owner),pack(snapshot),start.isoformat(),end.isoformat(),now))
        db.executemany('INSERT INTO membership_beneficiaries VALUES(?,?,?,NULL)',[(grant,p,now) for p in people])
        movement(db,grant,terms['quantity'],'initial',key,payload,'admin','Attribution',int(owner))
        if terms['kind']=='credits':
            for person in people:
                db.execute('INSERT INTO membership_preferences(user_id,primary_plan_id) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET primary_plan_id=COALESCE(membership_preferences.primary_plan_id,excluded.primary_plan_id)',(person,plan_id))
        if renew_from and setting(db,'membership_confirmation_enabled','0')=='1':
            from membership_notices import queue
            queue(db,grant,'renewal','renewal/'+op)
        return grant

def adjust(db,grant_id,value,kind,key,reason):
    if kind not in {'recharge','correction'}:raise ValueError('Mouvement invalide.')
    reason=text(reason,'Motif',300,True)
    with atomic(db):
        row=db.execute('SELECT * FROM membership_grants WHERE grant_id=?',(grant_id,)).fetchone()
        if not row:raise ValueError('Attribution inconnue.')
        terms=json.loads(row['terms_json'])
        if terms['kind']!='credits':raise ValueError('Ce droit ne possède pas de crédits consommables.')
        raw=str(value).strip();negative=raw.startswith('-')
        quantity=units(raw[1:] if negative else raw,terms)*(-1 if negative else 1)
        if kind=='recharge' and quantity<=0:raise ValueError('Recharge strictement positive requise.')
        result=movement(db,grant_id,quantity,kind,key,dict(grant=grant_id,quantity=quantity,kind=kind,reason=reason),'admin',reason,row['owner_id'])
        if kind=='recharge' and setting(db,'membership_confirmation_enabled','0')=='1':
            from membership_notices import queue
            queue(db,grant_id,'recharge','recharge/'+result['operation_key'])
        return result

def reverse(db,operation_key,key,reason):
    with atomic(db):
        payload=dict(reverse=operation_key,reason=text(reason,'Motif',300,True))
        _,_,old=prior(db,key,payload)
        if old:return dict(old)
        row=db.execute('SELECT * FROM membership_ledger WHERE operation_key=?',(operation_key,)).fetchone()
        if not row or row['kind'] not in {'consumption','reconciliation','recharge','correction'}:raise ValueError('Mouvement non annulable.')
        existing=db.execute('SELECT * FROM membership_ledger WHERE reversal_of=?',(operation_key,)).fetchone()
        if existing:raise ValueError('Ce mouvement possède déjà une écriture compensatoire.')
        if row['charge_key'] and row['quantity']>0:raise ValueError('Cette régularisation a déjà ajusté la durée. Utilisez une correction administrative motivée.')
        if row['charge_key'] and row['quantity']<0:
            charge_row=db.execute('SELECT * FROM membership_consumptions WHERE charge_key=?',(row['charge_key'],)).fetchone()
            if not charge_row or charge_row['settled']<-row['quantity']:raise ValueError('Cette consommation a déjà été régularisée ; utilisez une correction motivée.')
            db.execute('UPDATE membership_consumptions SET settled=settled+?,waived=waived-?,updated_at=? WHERE charge_key=?',(row['quantity'],row['quantity'],stamp(),row['charge_key']))
        return movement(db,row['grant_id'],-row['quantity'],'reversal',key,payload,'admin',payload['reason'],row['user_id'],row['session_id'],operation_key)

def state_change(db,grant_id,status,key,reason):
    if status not in {'active','suspended'}:raise ValueError('État invalide.')
    with atomic(db):
        payload=dict(grant=grant_id,status=status,reason=reason);_,_,old=prior(db,key,payload)
        if old:return
        movement(db,grant_id,0,'status',key,payload,'admin',text(reason,'Motif',300,True))
        db.execute('UPDATE membership_grants SET status=? WHERE grant_id=?',(status,grant_id))

def grants_for(db,user_id):
    result=[]
    for row in db.execute('SELECT g.*,b.ended_at FROM membership_grants g JOIN membership_beneficiaries b USING(grant_id) WHERE b.user_id=? ORDER BY g.ends_on,g.created_at',(user_id,)):
        value=dict(row);value['terms']=json.loads(row['terms_json']);value['balance_label']=amount_label(row['balance'],value['terms'])
        value['beneficiaries']=db.execute('SELECT u.id,u.first_name,u.last_name,b.ended_at FROM membership_beneficiaries b JOIN users u ON u.id=b.user_id WHERE b.grant_id=?',(row['grant_id'],)).fetchall()
        result.append(value)
    return result

def access(db,user_id,at=None):
    if not enabled(db):return dict(enabled=False,allowed=True,warning=False,message='',credit=None)
    day=(at or datetime.now(timezone.utc)).astimezone(zone(db)).date()
    user=db.execute('SELECT active,category FROM users WHERE id=?',(user_id,)).fetchone()
    if not user or not user['active']:return dict(enabled=True,allowed=False,warning=True,message='Compte inactif.',credit=None)
    pref=db.execute('SELECT * FROM membership_preferences WHERE user_id=?',(user_id,)).fetchone()
    exempt=bool(pref and pref['exempt']) or user['category'] in json.loads(setting(db,'membership_exempt_categories','[]'))
    valid=[]
    for row in grants_for(db,user_id):
        if row['ended_at'] or row['status']!='active' or not row['starts_on']<=day.isoformat()<=row['ends_on']:continue
        if row['terms']['scope']=='family' and (row['owner_id'] is None or not related(db,row['owner_id'],user_id)):continue
        valid.append(row)
    periods=[g for g in valid if g['terms']['kind']=='period']
    credits=[g for g in valid if g['terms']['kind']=='credits']
    if pref and pref['primary_plan_id']:credits=[g for g in credits if g['plan_id']==pref['primary_plan_id']]
    elif len({g['plan_id'] for g in credits})>1:credits=[]
    credit=next((g for g in credits if g['balance']>0 or entry_covered(db,g,user_id,at)),None)
    reasons=[]
    if not exempt:
        if setting(db,'membership_require_period','0')=='1' and not periods:reasons.append('Aucun abonnement de période valide.')
        if setting(db,'membership_require_credit','0')=='1' and not credit:reasons.append('Forfait absent, expiré ou à régulariser auprès de l’accueil.')
    mode=setting(db,'membership_control','informative');denied=bool(reasons and mode=='strict')
    message=('Votre accès nécessite une régularisation. Merci de contacter l’accueil.' if denied else
             'Entrée autorisée. '+ ' '.join(reasons) if reasons else
             'Accès exempté par la structure.' if exempt else
             (credit['terms']['name']+' · '+credit['balance_label']) if credit else
             (periods[0]['terms']['name']+' · valide jusqu’au '+date.fromisoformat(periods[0]['ends_on']).strftime('%d/%m/%Y')) if periods else
             'Aucun forfait de fréquentation sélectionné.')
    return dict(enabled=True,allowed=not denied,warning=bool(reasons and mode!='informative'),message=message,credit=None if exempt else credit,exempt=exempt)


def entry_covered(db,grant,user_id,at=None):
    terms=grant['terms'];moment=at or datetime.now(timezone.utc)
    if terms['unit']=='passage' and terms['grace_minutes']:
        return bool(db.execute('''SELECT 1 FROM membership_consumptions c JOIN sessions s ON s.id=c.session_id
            WHERE c.grant_id=? AND c.user_id=? AND c.settled>0 AND s.check_out IS NOT NULL
            AND julianday(s.check_out) BETWEEN julianday(?) AND julianday(?) LIMIT 1''',
            (grant['grant_id'],user_id,(moment-timedelta(minutes=terms['grace_minutes'])).isoformat(),moment.isoformat())).fetchone())
    if terms['unit']=='halfday':
        local=moment.astimezone(zone(db))
        for begin,finish in terms['halfday_windows']:
            if begin<=local.strftime('%H:%M')<finish:
                key=hashed('/'.join([grant['grant_id'],str(user_id),str(local.date()),begin,finish]))
                if db.execute('SELECT 1 FROM membership_consumptions WHERE charge_key=? AND settled=1',(key,)).fetchone():return True
    return False

def charge(db,grant_id,user_id,session_id,key,requested,reconcile=False):
    """Post only the difference; shortage stays explicit, never a negative balance."""
    old=db.execute('SELECT * FROM membership_consumptions WHERE charge_key=?',(key,)).fetchone()
    if old and old['requested']==requested and (not reconcile or not old['remaining']):return dict(old)
    grant=db.execute('SELECT * FROM membership_grants WHERE grant_id=?',(grant_id,)).fetchone()
    prior_settled=old['settled'] if old else 0;revision=(old['revision']+1) if old else 1
    waived=min(requested,old['waived'] if old else 0)
    delta=requested-waived-prior_settled
    available=grant['balance']
    if delta>available and setting(db,'membership_hourly_shortfall','available')=='manual':settled=prior_settled
    else:settled=prior_settled+min(delta,available) if delta>0 else requested-waived
    remaining=max(0,requested-settled-waived)
    if settled!=prior_settled:
        movement(db,grant_id,-(settled-prior_settled),'consumption' if not old else 'reconciliation',
            'charge/'+key+'/'+str(revision),dict(charge=key,requested=requested,revision=revision),reason='Présence constatée',user_id=user_id,session_id=session_id,charge_key=key)
    db.execute('''INSERT INTO membership_consumptions VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(charge_key) DO UPDATE SET requested=excluded.requested,settled=excluded.settled,
        remaining=excluded.remaining,revision=excluded.revision,updated_at=excluded.updated_at,waived=excluded.waived''',
        (key,grant_id,user_id,session_id,requested,settled,remaining,revision,stamp(),waived))
    return dict(db.execute('SELECT * FROM membership_consumptions WHERE charge_key=?',(key,)).fetchone())

def on_entry(db,user_id,session_id,at=None,decision=None):
    decision=decision or access(db,user_id,at)
    if not decision['enabled']:return
    if not decision['allowed']:raise EntryDenied(decision['message'])
    grant=decision.get('credit')
    db.execute('INSERT OR IGNORE INTO membership_session_links(session_id,grant_id,user_id,created_at) VALUES(?,?,?,?)',
        (session_id,grant['grant_id'] if grant else None,user_id,stamp()))
    if not grant:return
    terms=grant['terms']
    if terms['unit'] in {'passage','session'}:
        recent=None
        if terms['unit']=='passage' and terms['grace_minutes']:
            moment=at or datetime.now(timezone.utc)
            recent=db.execute('''SELECT 1 FROM membership_consumptions c JOIN sessions s ON s.id=c.session_id
               WHERE c.grant_id=? AND c.user_id=? AND c.settled>0 AND s.check_out IS NOT NULL
               AND julianday(s.check_out)>=julianday(?) AND julianday(s.check_out)<=julianday(?) LIMIT 1''',
               (grant['grant_id'],user_id,(moment-timedelta(minutes=terms['grace_minutes'])).isoformat(),moment.isoformat())).fetchone()
        if not recent:charge(db,grant['grant_id'],user_id,session_id,hashed('session/'+str(session_id)),1)

def on_exit(db,session_id,review=False):
    if not enabled(db):return
    link=db.execute('SELECT * FROM membership_session_links WHERE session_id=?',(session_id,)).fetchone()
    if not link or not link['grant_id']:return
    row=db.execute('SELECT * FROM sessions WHERE id=?',(session_id,)).fetchone()
    if not row or not row['check_out']:return
    if row['exit_method']=='automatic' and not review:
        db.execute('UPDATE membership_session_links SET review_required=1 WHERE session_id=?',(session_id,));return
    start=datetime.fromisoformat(row['check_in']);end=datetime.fromisoformat(row['check_out'])
    if start.tzinfo is None or end.tzinfo is None or end<start:raise ValueError('Durée de présence incohérente.')
    grant=db.execute('SELECT * FROM membership_grants WHERE grant_id=?',(link['grant_id'],)).fetchone()
    if not grant:return
    terms=json.loads(grant['terms_json'])
    if terms['unit']=='hour':charge(db,grant['grant_id'],link['user_id'],session_id,hashed('session/'+str(session_id)),int((end-start).total_seconds()),reconcile=review)
    elif terms['unit']=='halfday':
        local=zone(db);day=start.astimezone(local).date();last=end.astimezone(local).date()
        if (last-day).days>366:
            db.execute('UPDATE membership_session_links SET review_required=1 WHERE session_id=?',(session_id,));return
        while day<=last:
            for begin,finish in terms['halfday_windows']:
                lo=datetime.combine(day,time.fromisoformat(begin),local).astimezone(timezone.utc)
                hi=datetime.combine(day,time.fromisoformat(finish),local).astimezone(timezone.utc)
                if max(start,lo)<min(end,hi):
                    key=hashed('/'.join([grant['grant_id'],str(link['user_id']),str(day),begin,finish]))
                    # A second session in the same half-day never consumes again.
                    if not db.execute('SELECT 1 FROM membership_consumptions WHERE charge_key=?',(key,)).fetchone():charge(db,grant['grant_id'],link['user_id'],session_id,key,1)
            day+=timedelta(days=1)
    if review:db.execute('UPDATE membership_session_links SET review_required=0 WHERE session_id=?',(session_id,))


def safe_exit(db,session_id):
    """Malformed legacy timing must not trap a recognized user in the kiosk."""
    try:
        with atomic(db):on_exit(db,session_id)
    except ValueError:
        db.execute('UPDATE membership_session_links SET review_required=1 WHERE session_id=?',(session_id,))


def beneficiaries(db,grant_id,people,key,reason):
    with atomic(db):
        grant=db.execute('SELECT * FROM membership_grants WHERE grant_id=?',(grant_id,)).fetchone()
        if not grant:raise ValueError('Attribution inconnue.')
        people=validate_beneficiaries(db,grant['owner_id'],people,json.loads(grant['terms_json'])['scope'])
        payload=dict(grant=grant_id,people=people,reason=text(reason,'Motif',300,True))
        _,_,old=prior(db,key,payload)
        if old:return
        movement(db,grant_id,0,'beneficiaries',key,payload,'admin',payload['reason'])
        db.execute('UPDATE membership_beneficiaries SET ended_at=? WHERE grant_id=? AND ended_at IS NULL',(stamp(),grant_id))
        for person in people:
            db.execute('INSERT INTO membership_beneficiaries VALUES(?,?,?,NULL) ON CONFLICT(grant_id,user_id) DO UPDATE SET ended_at=NULL',(grant_id,person,stamp()))


def select_credit(db,user_id,plan_id,exempt,reason):
    """No public selection; the team explicitly chooses heterogeneous credits."""
    reason=text(reason,'Motif',300,True)
    if plan_id and not db.execute('''SELECT 1 FROM membership_grants g JOIN membership_beneficiaries b USING(grant_id)
        WHERE b.user_id=? AND b.ended_at IS NULL AND g.plan_id=?''',(user_id,plan_id)).fetchone():
        raise ValueError('Ce compte ne bénéficie pas de ce carnet.')
    with atomic(db):
        db.execute('INSERT INTO membership_preferences VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET primary_plan_id=excluded.primary_plan_id,exempt=excluded.exempt,reason=excluded.reason',
            (user_id,plan_id or None,int(exempt),reason))
        from evolution_schema import audit
        audit(db,'membership_preferences',user_id,'update','admin',dict(reason=reason))


def reconcile(db,session_id,key,reason):
    """Explicit review of real departure only; never invent a closing time."""
    with atomic(db):
        link=db.execute('SELECT * FROM membership_session_links WHERE session_id=?',(session_id,)).fetchone()
        if not link or not link['grant_id']:raise ValueError('Aucun carnet lié à cette session.')
        if not db.execute('SELECT 1 FROM sessions WHERE id=? AND check_out IS NOT NULL',(session_id,)).fetchone():raise ValueError('Renseignez d’abord le départ réellement constaté dans Fréquentation.')
        payload=dict(session=session_id,reason=text(reason,'Motif',300,True))
        _,_,old=prior(db,key,payload)
        if old:return
        movement(db,link['grant_id'],0,'reconciliation',key,payload,'admin',payload['reason'],link['user_id'],session_id)
        on_exit(db,session_id,review=True)
