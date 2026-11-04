"""Administrator-only, read-only observations. No integrity scan, replay or secrets."""
import json
from datetime import datetime,timezone,timedelta
from openfablab import __version__
from i18n import native

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
        catalogue_at=known_timestamp(row['catalogue_at']) if row else None,
        pending=row['pending']+row['processing'] if row and stamp else None,
        retrying=row['retrying'] if row and stamp else None,
        failed=row['failed'] if row and stamp else None,
        error_known=bool(row and row['last_error']),**counters)

def diagnostic(db,now=None,database_path=None):
    now=now or datetime.now(timezone.utc)
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
    if database_path is None:
        from flask import current_app,has_app_context
        database_path=current_app.config['DATABASE'] if has_app_context() else None
    panels=[]
    def add(key,title,state,evidence,hint,last=None):
        panels.append(dict(key=key,title=native(title),state=state,evidence=native(evidence),hint=native(hint),last=last))
    add('database','Application et base','unknown',
        'Version '+result['version']+' · SQLite '+str(result['schema'])+'. '+result['integrity'],
        'Un contrôle d’intégrité explicite et une restauration isolée complètent ces observations.')
    add('backups','Sauvegardes','error' if result['backup_error'] else 'observed' if result['backup_success'] else 'unknown',
        'Le dernier essai a signalé une erreur.' if result['backup_error'] else 'Dernière sauvegarde réussie enregistrée.' if result['backup_success'] else 'Aucune réussite connue.',
        'Un fichier présent ne prouve pas sa restauration. Vérifiez une copie dans un environnement isolé.',result['backup_success'])
    if result['wordpress']:
        for row in result['wordpress']['states']:
            stamp=row['catalogue_at'];fresh=False
            if stamp:
                age=(now-datetime.fromisoformat(stamp)).total_seconds()
                from reservations_sync import sync_interval_seconds
                fresh=0<=age<=max(240,2*sync_interval_seconds(settings.get('reservation_sync_interval_minutes','1'))+120)
            state='error' if row['error_known'] else 'observed' if fresh and row['freshness']=='recent' and row['retry_ack']==0 else 'attention'
            add('wordpress-'+row['environment'],'WordPress '+('Normal' if row['environment']=='production' else 'Test'),state,
                'Catalogue et relève récents observés.' if state=='observed' else 'Échanges récents incomplets ou erreur connue.',
                'Vérifiez Normal et Test, HTTPS, l’heure du serveur et la liaison dans Structure. Les refus métier ne prouvent pas une panne.',row['observed_at'])
    smtp_configured=False
    if database_path:
        from welcome_mail import load_config,validate_config
        try:validate_config(load_config(database_path));smtp_configured=True
        except ValueError:pass
    sent=known_timestamp(db.execute("SELECT MAX(at) FROM (SELECT sent_at AS at FROM family_booking_emails WHERE state='sent' UNION ALL SELECT welcome_sent_at FROM users WHERE welcome_status='sent' UNION ALL SELECT finished_at FROM automatic_deliveries WHERE state='sent' AND kind='animation_reminder')").fetchone()[0])
    add('smtp','E-mails SMTP','observed' if smtp_configured and sent else 'unknown',
        'Dernier envoi accepté par SMTP enregistré ; livraison au destinataire non attestée.' if smtp_configured and sent else 'SMTP configuré, aucun envoi accepté connu.' if smtp_configured else 'SMTP non configuré ou configuration à vérifier.',
        'Un serveur configuré ne prouve pas la livraison. Vérifiez le dernier envoi et les règles du fournisseur.',known_timestamp(sent))
    uncertain=db.execute("SELECT COUNT(*) FROM automatic_deliveries WHERE state='uncertain' OR (state='claimed' AND (julianday(claimed_at) IS NULL OR julianday(claimed_at)<julianday(?)))",((now-timedelta(minutes=10)).isoformat(),)).fetchone()[0]
    active=db.execute("SELECT COUNT(*) FROM automatic_deliveries WHERE state='claimed' AND julianday(claimed_at)>=julianday(?)",((now-timedelta(minutes=10)).isoformat(),)).fetchone()[0]
    last_job=known_timestamp(db.execute('SELECT MAX(claimed_at) FROM automatic_deliveries').fetchone()[0])
    add('jobs','Travaux automatiques et rappels','attention' if uncertain else 'unknown',
        str(uncertain)+' envoi(s) incertain(s), sans renvoi automatique.' if uncertain else str(active)+' envoi(s) en cours.' if active else 'Aucun envoi incertain connu ; exécution future non certifiée.',
        'Consultez les rappels à venir. Un rappel ne devient jamais une intervention réalisée.',last_job)
    if database_path:
        from pathlib import Path
        import shutil
        try:
            usage=shutil.disk_usage(Path(database_path).parent)
            add('storage','Stockage','attention' if usage.free<100*1024*1024 else 'observed',str(round(usage.free/1024**3,2))+' Gio libres observés.',
                'Cette mesure concerne le stockage de la base, pas nécessairement le volume des sauvegardes.')
        except OSError:
            add('storage','Stockage','unknown','Mesure indisponible.','Vérifiez le stockage sur le serveur.')
    result['panels']=panels
    return result
