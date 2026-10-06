"""Authenticated outbound-only relay. Idle polls never rebuild the catalogue."""
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import sqlite3
import time
import urllib.error
import urllib.request
import family_model as family
import outbound_actions as actions
from reservations_sync import WordPressClient, PRIVATE_API, signed_headers, load_sync_secret


class OutboundClient(WordPressClient):
    def __init__(self,site_url,secret,transport=None):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs): return None
        super().__init__(site_url,secret,transport or urllib.request.build_opener(NoRedirect()).open)

    def post(self, route, payload):
        rest_route='/openfablab/v1'+route
        body=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
        headers=signed_headers(self.secret,'POST',rest_route,body)
        request=urllib.request.Request(self.site_url+PRIVATE_API+route,data=body,headers=headers,method='POST')
        try:
            response=self.transport(request,timeout=10)
        except urllib.error.HTTPError as error:
            response=error
        with response:
            raw=response.read(1_000_001)
            status=response.status
            stamp=response.headers.get('X-OpenFabLab-Response-Timestamp','')
            nonce=response.headers.get('X-OpenFabLab-Response-Nonce','')
            signature=response.headers.get('X-OpenFabLab-Response-Signature','')
        if len(raw)>1_000_000 or not stamp.isdigit() or abs(time.time()-int(stamp))>300 or nonce!=headers['X-OpenFabLab-Nonce']:
            raise ValueError('Réponse WordPress non authentifiée. Vérifiez les versions et la connexion.')
        canonical=f'response/v1\n{stamp}\n{nonce}\n{rest_route}\n{status}\n{hashlib.sha256(raw).hexdigest()}'
        expected=hmac.new(self.secret,canonical.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,signature):
            raise ValueError('Réponse WordPress non authentifiée. Vérifiez les versions et la connexion.')
        result=json.loads(raw)
        if not isinstance(result,dict) or not 200<=status<300:
            raise ValueError('Échange WordPress refusé. Vérifiez la connexion dans les réglages.')
        return result


def negotiate(client, environment):
    value=client.post('/sync/capabilities',{'environment':environment})
    if value.get('protocol_version')!=4 or value.get('outbound_actions_v1') is not True:
        raise ValueError('OpenFabLab et son plugin doivent utiliser la version 2.8.1 ou compatible. Aucune demande n’a été confirmée.')


def catalogue(db, database_path, site_url, client=None, environments=actions.ENVIRONMENTS, force=True):
    from runtime_policy import external_allowed
    if not external_allowed(database_path): return {'configured':False,'isolated':True,'imported':0}
    secret=load_sync_secret(database_path)
    if not secret or not site_url: return {'configured':False,'imported':0}
    validated=OutboundClient(site_url,secret)
    client=client or validated
    errors=[]
    for env in environments:
        if env not in actions.ENVIRONMENTS: raise ValueError('Environnement invalide.')
        stamp=datetime.now(timezone.utc).isoformat(timespec='seconds')
        if not force:
            from reservations_sync import sync_interval_seconds
            prior=db.execute('SELECT catalogue_at FROM wordpress_relay_state WHERE environment=?',(env,)).fetchone()
            if prior and prior[0] and (datetime.now(timezone.utc)-datetime.fromisoformat(prior[0])).total_seconds()<sync_interval_seconds(family.setting(db,'reservation_sync_interval_minutes','1.5')):
                continue
        try:
            negotiate(client,env)
            from runtime_policy import storage_guard
            with storage_guard(database_path):
                public=actions.public_catalogue(db,env)
            result=client.post('/outbound/catalogue',{'environment':env,'animations':public,'protocol_version':4})
            if result.get('ok') is not True: raise ValueError('Catalogue refusé.')
            with actions.transaction(db):
                db.execute('INSERT INTO wordpress_relay_state(environment,catalogue_at,catalogue_count,last_error) VALUES(?,?,?,NULL) ON CONFLICT(environment) DO UPDATE SET catalogue_at=excluded.catalogue_at,catalogue_count=excluded.catalogue_count,last_error=NULL',(env,stamp,len(public)))
                for key,value in [('reservation_protocol_'+env,'4'),('reservation_plugin_'+env,result.get('plugin_version','2.8.1')),('reservation_outbound_ready_'+env,'1')]:
                    db.execute('INSERT INTO app_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
                db.execute("INSERT INTO reservation_sync_state(environment,cursor,last_attempt_at,last_success_at,last_error) VALUES(?,'',?,?,NULL) ON CONFLICT(environment) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,last_success_at=excluded.last_success_at,last_error=NULL",(env,stamp,stamp))
        except (OSError,ValueError,sqlite3.Error):
            db.rollback()
            message='Connexion sortante non vérifiée. Vérifiez les versions, HTTPS et le secret partagé.'
            with actions.transaction(db):
                db.execute('INSERT INTO wordpress_relay_state(environment,last_error) VALUES(?,?) ON CONFLICT(environment) DO UPDATE SET last_error=excluded.last_error',(env,message))
                db.execute("INSERT INTO app_settings(key,value) VALUES(?,'0') ON CONFLICT(key) DO UPDATE SET value='0'",('reservation_outbound_ready_'+env,))
                db.execute("INSERT INTO reservation_sync_state(environment,cursor,last_attempt_at,last_error_at,last_error) VALUES(?,'',?,?,?) ON CONFLICT(environment) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,last_error_at=excluded.last_error_at,last_error=excluded.last_error",(env,stamp,stamp,message))
            errors.append({'environment':env,'error':message})
    return {'configured':True,'imported':0,'errors':errors,'notifications':[],'rejected':[]}


def poll(db, database_path, site_url, client=None, environments=actions.ENVIRONMENTS):
    from runtime_policy import external_allowed
    if not external_allowed(database_path): return {'isolated':True,'processed':0}
    secret=load_sync_secret(database_path)
    if not secret or not site_url: return {'configured':False,'processed':0}
    client=client or OutboundClient(site_url,secret)
    processed=0;errors=[]
    for env in environments:
        if env not in actions.ENVIRONMENTS: raise ValueError('Environnement invalide.')
        try:
            processed+=_poll_environment(db,database_path,client,env,secret)
        except (OSError,ValueError,sqlite3.Error):
            db.rollback()
            message='Demandes non relevées ou résultats non acquittés. La connexion sera réessayée, sans nouvelle attribution de places.'
            with actions.transaction(db):
                db.execute('INSERT INTO wordpress_relay_state(environment,last_error) VALUES(?,?) ON CONFLICT(environment) DO UPDATE SET last_error=excluded.last_error',(env,message))
            errors.append({'environment':env,'error':message})
    return {'configured':True,'processed':processed,'errors':errors}


def _poll_environment(db,database_path,client,env,secret):
    # An idle cycle needs only technical state, never accounts or a catalogue.
    value=client.post('/outbound/poll',{'environment':env,'protocol_version':4})
    if value.get('protocol_version')!=4 or value.get('outbound_actions_v1') is not True:
        raise ValueError('Plugin incompatible : aucune action traitée.')
    envelopes=value.get('actions',[])
    if not isinstance(envelopes,list) or len(envelopes)>20: raise ValueError('File WordPress invalide.')
    queue=value.get('queue',{})
    if not isinstance(queue,dict):raise ValueError('État WordPress invalide.')
    counts=[queue.get(key,0) for key in ('pending','processing','failed','retrying')]
    if any(type(count) is not int or not 0<=count<=100000 for count in counts):raise ValueError('État WordPress invalide.')
    with actions.transaction(db):
        db.execute('INSERT INTO wordpress_relay_state(environment,polled_at,pending,processing,failed,retrying,last_error) VALUES(?,?,?,?,?,?,NULL) ON CONFLICT(environment) DO UPDATE SET polled_at=excluded.polled_at,pending=excluded.pending,processing=excluded.processing,failed=excluded.failed,retrying=excluded.retrying,last_error=NULL',(env,datetime.now(timezone.utc).isoformat(),*counts))
    results=[]
    for envelope in envelopes:
        from runtime_policy import storage_guard
        with storage_guard(database_path):
            result=actions.process_action(db,envelope,env,secret)
        results.append({'id':envelope['id'],'hash':envelope['hash'],'lease':envelope.get('lease'),'result':result})
    if results:
        ack=client.post('/outbound/results',{'environment':env,'protocol_version':4,'results':results})
        if ack.get('acknowledged')!=[r['id'] for r in results]:raise ValueError('Résultats non acquittés, ils seront retransmis.')
        with actions.transaction(db):
            for r in results:
                db.execute('UPDATE wordpress_action_receipts SET acknowledged_at=? WHERE environment=? AND action_id=?',(int(time.time()),env,r['id']))
            db.execute('UPDATE wordpress_relay_state SET results_at=?,last_error=NULL WHERE environment=?',(datetime.now(timezone.utc).isoformat(),env))
    return len(results)


def start_worker(application, get_database, load_modules):
    import threading
    from runtime_policy import storage_guard, external_allowed
    def work():
        next_catalogue=0;next_prune=0
        while True:
            interval=15
            try:
                with application.app_context():
                    db=get_database()
                    interval=actions.action_interval(family.setting(db,'reservation_action_interval_seconds','15'))
                    site=family.setting(db,'reservation_wordpress_url','')
                    if external_allowed(application.config['DATABASE']) and load_modules(db)['public_reservations'] and site:
                        if time.monotonic()>=next_catalogue:
                            catalogue(db,application.config['DATABASE'],site,force=False)
                            from reservations_sync import sync_interval_seconds
                            next_catalogue=time.monotonic()+sync_interval_seconds(family.setting(db,'reservation_sync_interval_minutes','1.5'))
                        poll(db,application.config['DATABASE'],site)
                    if time.monotonic()>=next_prune:
                        with storage_guard(application.config['DATABASE']):
                            actions.prune_private_receipts(db)
                        next_prune=time.monotonic()+300
            except Exception as error:
                logging.getLogger(__name__).warning('WordPress relay: %s',type(error).__name__)
            time.sleep(interval)
    threading.Thread(target=work,name='openfablab-outbound-actions',daemon=True).start()
