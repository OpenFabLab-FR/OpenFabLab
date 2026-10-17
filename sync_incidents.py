"""Durable, per-environment incident; notification delay never delays polling."""
import hashlib
import json
from datetime import datetime, timezone, timedelta


def observe(db, environment, channel, failed, now=None, critical=False):
    from reservation_notifications import queue, setting
    if environment not in ('production','test') or channel not in ('poll','catalogue'):
        raise ValueError('Canal de synchronisation inconnu.')
    now=now or datetime.now(timezone.utc)
    existing=db.execute('SELECT 1 FROM wordpress_sync_incidents WHERE environment=?',(environment,)).fetchone()
    if not existing:
        # Carry an already alerted 2.9 episode forward, without another alert.
        active={};sequence=0;alert=None;legacy_candidates=[]
        for previous_channel in ('poll','catalogue'):
            old_key='reservation_discord_sync_'+environment+'_'+previous_channel
            old=json.loads(setting(db,old_key,'{}'))
            if old.get('active'):
                active[previous_channel]=True;sequence=max(sequence,int(old.get('sequence',0)))
                candidate=old_key+'/'+str(old.get('sequence',0))
                legacy_candidates.append(candidate)
                event=db.execute('SELECT state FROM reservation_discord_events WHERE event_key=?',(hashlib.sha256(candidate.encode()).hexdigest(),)).fetchone()
                if event:
                    if alert is None or event['state']=='sent':alert=candidate
                    elif event['state']=='pending':db.execute("UPDATE reservation_discord_events SET state='skipped' WHERE event_key=?",(hashlib.sha256(candidate.encode()).hexdigest(),))
        for candidate in legacy_candidates:
            if candidate!=alert:db.execute("UPDATE reservation_discord_events SET state='skipped' WHERE event_key=? AND state='pending'",(hashlib.sha256(candidate.encode()).hexdigest(),))
        db.execute('INSERT INTO wordpress_sync_incidents VALUES(?,?,?,?,?,?)',(environment,sequence,now.isoformat() if active else None,json.dumps(active),alert,int(bool(active))))
    row=db.execute('SELECT * FROM wordpress_sync_incidents WHERE environment=?',(environment,)).fetchone()
    channels=json.loads(row['channels_json']); sequence=row['sequence']; started=row['started_at']; alert=row['alert_key']
    if failed:
        if not row['active']:
            sequence+=1;started=now.isoformat();alert=None
        channels[channel]=True
        delay=int(setting(db,'discord_sync_delay_minutes','10'))
        if not alert and (critical or now-datetime.fromisoformat(started)>=timedelta(minutes=delay)):
            alert='sync-incident/'+environment+'/'+str(sequence)
            queue(db,alert,'sync_error',environment=environment,now=now)
    else:
        channels.pop(channel,None)
        if not channels:
            if alert:
                key=hashlib.sha256(alert.encode()).hexdigest()
                previous=db.execute('SELECT state FROM reservation_discord_events WHERE event_key=?',(key,)).fetchone()
                if previous and previous['state']=='sent' and setting(db,'discord_sync_recovery_enabled','0')=='1':
                    queue(db,alert+'/recovered','sync_recovered',environment=environment,now=now)
                db.execute("UPDATE reservation_discord_events SET state='skipped' WHERE event_key=? AND state='pending'",(key,))
            started=None;alert=None
    db.execute('UPDATE wordpress_sync_incidents SET sequence=?,started_at=?,channels_json=?,alert_key=?,active=? WHERE environment=?',
        (sequence,started,json.dumps(channels,sort_keys=True),alert,int(bool(channels)),environment))
