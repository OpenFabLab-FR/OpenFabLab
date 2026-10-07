"""Protocol 4: WordPress transports actions, this process alone decides seats.

No inbound address. A durable receipt and its business effect share one SQLite
transaction. A lost HTTP response can only replay that receipt, not the action.
"""
import base64
import binascii
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
import time
from urllib.parse import urlsplit

ENVIRONMENTS = ('production', 'test')
ACTION_TYPES = ('identify', 'contact', 'reserve', 'guest', 'view', 'cancel', 'accept', 'decline')
IDENTITY_TTL = 1200


@contextmanager
def transaction(db):
    """Preserve an existing business/receipt transaction instead of committing it."""
    own = not db.in_transaction
    if own: db.execute('BEGIN IMMEDIATE')
    try:
        yield
        if own: db.commit()
    except BaseException:
        if own: db.rollback()
        raise


def ensure_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS wordpress_action_receipts (
        environment TEXT NOT NULL CHECK(environment IN ('production','test')),
        action_id TEXT NOT NULL, payload_hash TEXT NOT NULL, action_type TEXT NOT NULL,
        result_json TEXT NOT NULL, created_at INTEGER NOT NULL,
        private_until INTEGER NOT NULL, acknowledged_at INTEGER,
        PRIMARY KEY(environment, action_id))''')
    db.execute('''CREATE TABLE IF NOT EXISTS wordpress_relay_state (
        environment TEXT PRIMARY KEY CHECK(environment IN ('production','test')),
        catalogue_at TEXT, catalogue_count INTEGER NOT NULL DEFAULT 0,
        polled_at TEXT, results_at TEXT, last_error TEXT,
        pending INTEGER NOT NULL DEFAULT 0, processing INTEGER NOT NULL DEFAULT 0,
        failed INTEGER NOT NULL DEFAULT 0, retrying INTEGER NOT NULL DEFAULT 0)''')
    columns={row[1] for row in db.execute('PRAGMA table_info(wordpress_relay_state)')}
    for name in ('pending','processing','failed','retrying'):
        if name not in columns:db.execute('ALTER TABLE wordpress_relay_state ADD COLUMN '+name+' INTEGER NOT NULL DEFAULT 0')
    for key, value in {'reservation_action_interval_seconds':'15',
                       'reservation_link_mode':'auto'}.items():
        db.execute('INSERT OR IGNORE INTO app_settings(key,value) VALUES(?,?)',(key,value))


def action_interval(value):
    try:
        if str(int(value)) != str(value).strip() or not 10 <= int(value) <= 60:
            raise ValueError
        return int(value)
    except (TypeError, ValueError):
        return 15


def public_catalogue(db, environment):
    import family_model as family
    from tablet_reservations import local_catalogue
    if environment not in ENVIRONMENTS: raise ValueError('Environnement invalide.')
    keys = ('service_id','title','description','date','hours','minimum_age',
            'booking_mode','slots','available','waitlist_enabled')
    result=[]
    for item in local_catalogue(db, lambda _db,k,default='':family.setting(_db,k,default), environment=environment):
        public={k:item[k] for k in keys}
        public['waitlist_enabled']=bool(public['waitlist_enabled'])
        public['account_required']=family.setting(db,'reservation_account_required','0')=='1'
        public['phone_required']=family.setting(db,'reservation_phone_required','0')=='1'
        public['autonomy_age']=int(family.setting(db,'family_autonomy_age','15'))
        public['slots']=[{k:s[k] for k in ('slot_uuid','label','available')} for s in item['slots']]
        result.append(public)
    return result


def _b64(data):
    return base64.urlsafe_b64encode(data).decode().rstrip('=')


def issue_link(secret, token, environment, kind='manage', expires=0):
    if not secret or environment not in ENVIRONMENTS or kind not in ('manage','offer'):
        raise ValueError('Liaison de réservation indisponible.')
    payload = _b64(json.dumps({'v':1,'t':token,'e':environment,'k':kind,'x':int(expires)},
                             separators=(',',':')).encode())
    signature = hmac.new(secret, ('link/v1\n'+payload).encode(), hashlib.sha256).hexdigest()
    return payload+'.'+signature


def verify_link(secret, value, environment, action=None, now=None):
    if not isinstance(value,str) or len(value)>600 or not secret:
        raise ValueError('Ce lien est invalide ou indisponible.')
    try:
        payload, signature = value.split('.')
        if not re.fullmatch(r'[A-Za-z0-9_-]+',payload) or not re.fullmatch(r'[a-f0-9]{64}',signature): raise ValueError
        expected=hmac.new(secret,('link/v1\n'+payload).encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,signature): raise ValueError
        data=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
        if set(data) != {'v','t','e','k','x'} or data['v']!=1 or data['e']!=environment or data['k'] not in ('manage','offer'): raise ValueError
        if not re.fullmatch(r'[A-Za-z0-9_-]{40,80}',data['t']) or type(data['x']) is not int: raise ValueError
        if data['x'] and data['x'] <= (time.time() if now is None else now):
            raise ValueError('Cette proposition a expiré. Aucune place n’a été confirmée.')
        if action in ('accept','decline') and data['k']!='offer': raise ValueError
        return data
    except (KeyError,TypeError,json.JSONDecodeError,ValueError,binascii.Error) as error:
        if str(error).startswith('Cette proposition'): raise
        raise ValueError('Ce lien est invalide ou indisponible.') from None


def email_link(db, database_path, payload, kind, environment):
    import family_model as family
    from reservations_sync import load_sync_secret
    site=family.setting(db,'reservation_wordpress_url','').rstrip('/')
    mode=family.setting(db,'reservation_link_mode','auto')
    use_wordpress = mode=='wordpress' or (mode=='auto' and bool(site))
    if use_wordpress:
        secret=load_sync_secret(database_path)
        parsed=urlsplit(site)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Adresse WordPress HTTPS requise pour les liens.')
        if family.setting(db,'reservation_outbound_ready_'+environment,'')!='1':
            raise ValueError('La connexion WordPress doit être vérifiée avant l’envoi.')
        expiry=int(datetime.fromisoformat(payload['expires']).timestamp()) if kind=='offer_pending' else 0
        signed=issue_link(secret,payload['token'],environment,'offer' if kind=='offer_pending' else 'manage',expiry)
        # Fragment never reaches HTTP access logs or the Referer header.
        return site+'/?openfablab_action=1#ofl='+signed
    base=family.setting(db,'reservation_public_url','').rstrip('/')
    parsed=urlsplit(base)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Adresse locale de réservation invalide.')
    return base+'/animations/demande/'+payload['token']


def dispatch(db, data, action, environment, secret, request_key):
    import family_reservations as engine
    import family_waitlist as waiting
    from family_reservation_routes import identity
    if data.get('environment')!=environment: raise ValueError('Environnement invalide.')
    if action in ('view','cancel','accept','decline'):
        link=verify_link(secret,data.get('link'),environment,None if action=='view' else action)
        group=waiting.lookup(db,link['t'])
        if group['environment']!=environment: raise ValueError('Ce lien est invalide ou indisponible.')
        if action=='view':
            return {'status':group['status'],'label':waiting.LABELS.get(group['status'],'Indisponible'),
                    'can_answer':group['status']=='offer_pending' and link['k']=='offer'}
        if data.get('consent') is not True: raise ValueError('Confirmez votre choix.')
        return waiting.respond(db,link['t'],action)
    if type(data.get('service_id')) is not int or data['service_id']<=0: raise ValueError('Animation invalide.')
    service_id=data['service_id']
    if action=='guest':
        if data.get('consent') is not True: raise ValueError('Consentement requis.')
        if set(data)-{'environment','service_id','slot_uuid','first_name','last_name','birth_date','email','phone','consent'}:
            raise ValueError('Une réservation sans compte concerne une seule personne.')
        details={k:data.get(k,'') for k in ('first_name','last_name','birth_date','email','phone')}
        return engine.reserve_guest(db,details,service_id,data.get('slot_uuid'),request_key,environment)
    if action=='identify':
        token,owner=engine.identify(db,service_id,data.get('public_id'),data.get('contact',''),
                                    data.get('client_bucket',''),environment,rate_checked=True)
        return identity(db,token,owner)
    token=data.get('token','')
    owner=engine.grant(db,token,service_id,environment)
    if action=='contact':
        waiting.complete_contact(db,owner,str(data.get('email','')).strip(),data.get('phone'))
        return identity(db,token,owner)
    if action!='reserve': raise ValueError('Action indisponible.')
    keys={hmac.new(token.encode(),str(u['id']).encode(),hashlib.sha256).hexdigest():u['id'] for u in engine.choices(db,owner)}
    selected=data.get('participants')
    if not isinstance(selected,list) or not 1<=len(selected)<=20 or any(not isinstance(k,str) or k not in keys for k in selected):
        raise ValueError('Sélection de participants invalide.')
    if data.get('consent') is not True: raise ValueError('Consentement requis.')
    return engine.reserve(db,owner,[keys[k] for k in selected],service_id,data.get('slot_uuid'),request_key,environment,'wordpress')


def process_action(db, envelope, environment, secret, fail_after=None):
    """Every accepted envelope has a durable, atomic success/error receipt."""
    if environment not in ENVIRONMENTS or not isinstance(envelope,dict): raise ValueError('Action invalide.')
    action_id=envelope.get('id','');raw=envelope.get('payload_json','');kind=envelope.get('type')
    if (not isinstance(raw,str) or len(raw.encode())>16384 or kind not in ACTION_TYPES
        or not re.fullmatch(r'[a-f0-9]{48}',str(action_id))): raise ValueError('Action invalide.')
    digest=hashlib.sha256(raw.encode()).hexdigest()
    if not hmac.compare_digest(digest,str(envelope.get('hash',''))): raise ValueError('Action altérée.')
    data=json.loads(raw)
    if not isinstance(data,dict) or data.get('environment')!=environment: raise ValueError('Environnement invalide.')
    now=int(time.time())
    request_key=hmac.new(secret,('action/v1|'+environment+'|'+action_id).encode(),hashlib.sha256).hexdigest()
    with transaction(db):
        prior=db.execute('SELECT * FROM wordpress_action_receipts WHERE environment=? AND action_id=?',(environment,action_id)).fetchone()
        if prior:
            if prior['payload_hash']!=digest or prior['action_type']!=kind: raise ValueError('Action déjà utilisée pour un autre choix.')
            if kind in ('identify','contact') and prior['private_until']<=now:
                return {'ok':False,'message':'Cette vérification a expiré. Identifiez-vous à nouveau.'}
            return json.loads(prior['result_json'])
        # Business mutations may internally need a transaction, but never
        # commit the outer effect+receipt transaction. Savepoint also discards
        # all partial changes on a validation refusal.
        rate_error=None
        if kind=='identify':
            import family_reservations as engine
            try: engine.limit_identification(db,data.get('client_bucket',''))
            except ValueError as error: rate_error=error
        db.execute('SAVEPOINT outbound_business')
        try:
            if rate_error: raise rate_error
            value=dispatch(db,data,kind,environment,secret,request_key)
            result={'ok':True,'value':value}
            db.execute('RELEASE outbound_business')
        except (ValueError,TypeError) as error:
            db.execute('ROLLBACK TO outbound_business');db.execute('RELEASE outbound_business')
            result={'ok':False,'message':str(error)}
        if fail_after: fail_after(db)
        db.execute('INSERT INTO wordpress_action_receipts VALUES(?,?,?,?,?,?,?,NULL)',
                   (environment,action_id,digest,kind,json.dumps(result,ensure_ascii=False,separators=(',',':')),now,now+IDENTITY_TTL))
    return result


def prune_private_receipts(db):
    with transaction(db):
        db.execute("UPDATE wordpress_action_receipts SET result_json=? WHERE (action_type IN('identify','contact') OR json_extract(result_json,'$.ok')=0) AND private_until<=? AND result_json!=?",
                   ('{"ok":false,"message":"Cette vérification a expiré. Identifiez-vous à nouveau."}',int(time.time()),
                    '{"ok":false,"message":"Cette vérification a expiré. Identifiez-vous à nouveau."}'))
