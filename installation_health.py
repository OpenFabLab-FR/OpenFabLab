"""Administrator-only, read-only observations. No integrity scan, replay or secrets."""
import json
from datetime import datetime,timezone
from openfablab import __version__

def known_timestamp(value):
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed.isoformat() if parsed.tzinfo is not None else None
    except (ValueError,TypeError,AttributeError):return None

def queue_state(db,environment,now=None):
    now=now or datetime.now(timezone.utc)
    row=db.execute('SELECT * FROM wordpress_relay_state WHERE environment=?',(environment,)).fetchone()
    counts=db.execute('''SELECT COUNT(CASE WHEN acknowledged_at IS NOT NULL THEN 1 END),
        COUNT(CASE WHEN acknowledged_at IS NULL AND created_at>=? THEN 1 END),
        COUNT(CASE WHEN acknowledged_at IS NULL AND created_at<? THEN 1 END)
        FROM wordpress_action_receipts WHERE environment=?''',(now.timestamp()-120,now.timestamp()-120,environment)).fetchone()
    counters=dict(zip(('acknowledged','awaiting_ack','retry_ack'),counts))
    old=db.execute('''WITH records AS (SELECT sent_at,command_type,
        CASE WHEN json_valid(payload_json) THEN json_extract(payload_json,'$.state') END AS state
        FROM reservation_outbox WHERE environment=?) SELECT COUNT(*),
        COUNT(CASE WHEN sent_at IS NOT NULL OR (command_type='public_request' AND state IN('confirmed','waitlisted','rejected','cancelled')) THEN 1 END),
        COUNT(CASE WHEN sent_at IS NULL AND command_type='public_request' AND COALESCE(state,'') NOT IN('confirmed','waitlisted','rejected','cancelled') THEN 1 END) FROM records''',(environment,)).fetchone()
    counters.update(zip(('legacy','legacy_resolved','legacy_review'),old))
    stamp=known_timestamp(row['polled_at']) if row else None
    try:
        parsed=datetime.fromisoformat(stamp.replace('Z','+00:00'))
        age=(now-parsed).total_seconds()
        freshness='recent' if 0<=age<=120 else 'stale'
    except (ValueError,TypeError,AttributeError):freshness='unknown'
    return dict(environment=environment,observed_at=stamp,freshness=freshness,
        pending=row['pending']+row['processing'] if row and stamp else None,
        retrying=row['retrying'] if row and stamp else None,
        failed=row['failed'] if row and stamp else None,
        error_known=bool(row and row['last_error']),**counters)

def diagnostic(db,now=None):
    settings=dict(db.execute('SELECT key,value FROM app_settings'))
    result=dict(version=__version__,schema=db.execute('PRAGMA user_version').fetchone()[0],
        integrity='Aucun résultat de contrôle d’intégrité mémorisé disponible.',
        backup_success=known_timestamp(settings.get('automatic_backup_last_success')),
        backup_error=bool(settings.get('automatic_backup_last_error')),wordpress=None)
    used=bool(settings.get('reservation_wordpress_url')) or bool(db.execute('SELECT 1 FROM wordpress_relay_state WHERE polled_at IS NOT NULL OR catalogue_at IS NOT NULL LIMIT 1').fetchone())
    if used and settings.get('module_activities','1')=='1' and settings.get('module_public_reservations','1')=='1':
        configured=bool(settings.get('reservation_wordpress_url'))
        result['wordpress']=dict(configured=configured,
            states=[queue_state(db,env,now) for env in ('production','test')] if configured else [])
    return result
