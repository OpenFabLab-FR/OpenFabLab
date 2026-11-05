"""Read-only signed WordPress capability/freshness checks; never polls/replays work."""
import time
from .data_checks import connection
from .security import Refused
from .stage_diagnostics import phase,recording


def check(database,data,started=None,*,client_factory=None,clock=time.time,sleep=time.sleep,report=None):
    with recording(report):
        return checked(database,data,started,client_factory=client_factory,clock=clock,sleep=sleep)

def checked(database,data,started=None,*,client_factory=None,clock=time.time,sleep=time.sleep):
    # /app is the already-verified pinned runtime, not a downloaded candidate.
    # Private controllers use /package:/app; permanent agents /opt/agent:/app.
    with phase('WORDPRESS_IMPORTS'):
        from outbound_sync import OutboundClient,negotiate
        from reservations_sync import load_sync_secret,sync_interval_seconds
    with phase('WORDPRESS_SETTINGS'):
        with connection(database) as db:
            settings=dict(db.execute('SELECT key,value FROM app_settings'))
    if settings.get('module_public_reservations','0')!='1' or settings.get('module_activities','1')!='1':
        return dict(success=True,status='NOT_APPLICABLE_MODULE_DISABLED')
    with phase('WORDPRESS_SECRET'):
        secret=load_sync_secret(database)
        if not secret or not settings.get('reservation_wordpress_url'):
            raise Refused('WORDPRESS_ACTIVE_BUT_UNCONFIGURED')
    with phase('WORDPRESS_CLIENT'):
        client=(client_factory or OutboundClient)(settings['reservation_wordpress_url'],secret)
        timeout=min(1800,max(180,2*sync_interval_seconds(settings.get('reservation_sync_interval_minutes','1'))+120))
    with phase('WORDPRESS_EXCHANGES'):
        return exchanges(database,client,negotiate,timeout,started,clock,sleep)

def exchanges(database,client,negotiate,timeout,started,clock,sleep):
    deadline=clock()+(timeout if started is not None else 0)
    observations={}
    while True:
        with phase('WORDPRESS_LOCAL_STATE'):
            with connection(database) as db:
                local={r[0]:(r[1],r[2]) for r in db.execute('SELECT environment,catalogue_count,last_error FROM wordpress_relay_state')}
        for env in ('production','test'):
            state=None
            try:
                value=negotiate(client,env)
                state=value.get('relay_state')
                if not isinstance(state,dict) or state.get('environment')!=env:
                    raise ValueError('environment')
                now=int(clock());queue=state.get('queue',{})
                recent=all(type(state.get(k)) is int and -300<=now-state[k]<=timeout and
                           (started is None or state[k]>=started) for k in ('catalogue_at','polled_at'))
                acknowledged=env in local and local[env][0]==state.get('animations') and not local[env][1]
                quiet=all(type(queue.get(k)) is int and queue[k]==0 for k in ('pending','processing'))
                observations[env]=dict(verified=recent and acknowledged and quiet,recent=recent,
                    acknowledged=acknowledged,no_inflight_business_action=quiet)
            except (OSError,ValueError):
                observations[env]=dict(verified=False,code='SIGNED_EXCHANGE_UNVERIFIED')
        if all(v['verified'] for v in observations.values()):
            return dict(success=True,protocol=4,revision=3,environments=observations,business_action_sent=False)
        if clock()>=deadline:
            env=next(e for e in ('production','test') if not observations[e]['verified'])
            raise Refused('WORDPRESS_'+('NORMAL' if env=='production' else 'TEST')+'_EXCHANGE_UNVERIFIED')
        sleep(5)
