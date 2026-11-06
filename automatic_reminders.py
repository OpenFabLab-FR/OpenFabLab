"""At-most-once claims; never replay an uncertain external delivery."""
import json
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from zoneinfo import ZoneInfo
from family_model import setting

def maintenance_due_label(db,value):
    """A due_on is a local civil date, not a UTC midnight to shift again.

    Use the installation's configured primary language, never a visitor/session
    language. Scheduling continues to use the structure timezone in process().
    """
    from localized_formats import day
    return day(value,setting(db,'kiosk_language','fr'))

def claim(db,key,kind,now):
    db.commit();db.execute('BEGIN IMMEDIATE')
    result=db.execute("INSERT OR IGNORE INTO automatic_deliveries(delivery_key,kind,state,claimed_at) VALUES(?,?,'claimed',?)",(key,kind,now.isoformat()))
    db.commit();return result.rowcount==1

def finish(db,key,state,now,error=None):
    with db:db.execute('UPDATE automatic_deliveries SET state=?,finished_at=?,error_code=? WHERE delivery_key=?',(state,now.isoformat(),error,key))

def process(db,database_path,now=None,mail_sender=None,discord_sender=None):
    from runtime_policy import external_allowed
    if mail_sender is None and discord_sender is None and not external_allowed(database_path):return dict(isolated=True,sent=0)
    now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc);zone=ZoneInfo(setting(db,'structure_timezone','Europe/Paris'));local=now.astimezone(zone)
    sent=0
    with db:
        db.execute("UPDATE automatic_deliveries SET state='uncertain',error_code='InterruptedDelivery' WHERE state='claimed' AND claimed_at<?",((now-timedelta(minutes=10)).isoformat(),))
    if setting(db,'module_maintenance','0')=='1' and setting(db,'module_discord','1')=='1' and setting(db,'maintenance_discord_enabled','0')=='1' and local.hour>=int(setting(db,'maintenance_reminder_hour','9')):
        from app import read_discord_webhook,send_discord_plain,load_discord_settings
        config=load_discord_settings(db);webhook=read_discord_webhook() if discord_sender is None else 'simulated'
        if webhook and (config['enabled'] or discord_sender is not None):
            from machine_maintenance import reminder_state
            rows=db.execute("SELECT m.*,r.name FROM machine_reminders m JOIN resources r USING(resource_uuid) WHERE state='pending' AND due_on=? AND r.archived_at IS NULL",(local.date().isoformat(),)).fetchall()
            for row in rows:
                if reminder_state(row,local.date())!='today':continue
                key='maintenance/'+row['reminder_uuid']
                if not claim(db,key,'maintenance',now):continue
                # Only the explicitly public-safe reminder subject, never the
                # intervention description, actor, contact or internal history.
                text='🔧 '+row['name']+' · '+row['subject']+' · '+maintenance_due_label(db,row['due_on'])
                try:
                    accepted=(discord_sender or (lambda text:send_discord_plain(webhook,text,config['bot_name'])))(text)
                    if accepted is False:raise RuntimeError('DiscordDeliveryNotConfirmed')
                except Exception as error:finish(db,key,'uncertain',now,type(error).__name__)
                else:finish(db,key,'sent',now);sent+=1
    if setting(db,'module_activities','1')!='1' or setting(db,'module_public_reservations','1')!='1':return dict(sent=sent)
    if setting(db,'reservation_reminder_enabled','auto')=='0':return dict(sent=sent)
    from welcome_mail import load_config,send
    config=load_config(database_path)
    if mail_sender is None and not config.get('host'):return dict(sent=sent)
    from reservation_calendar import event
    from outbound_actions import email_link
    from reservation_email_templates import build_message
    hours=int(setting(db,'reservation_reminder_hours','48'))
    cutoff=datetime.fromisoformat(setting(db,'v214_reminders_available_since',now.isoformat()))
    rows=db.execute("SELECT g.* FROM family_booking_groups g JOIN animation_reservation_config c ON c.service_id=g.service_id WHERE g.status='confirmed' AND g.environment='production' AND c.enabled=1 AND c.environment=g.environment").fetchall()
    for group in rows:
        value=event(db,group);begin=datetime.fromisoformat(value['start']).astimezone(timezone.utc)
        due=begin-timedelta(hours=hours)
        # No backfill for a reminder window already open at upgrade/activation.
        if not cutoff<=due<=now<begin:continue
        if group['slot_uuid'] and not db.execute('SELECT 1 FROM animation_slots WHERE slot_uuid=? AND active=1',(group['slot_uuid'],)).fetchone():continue
        key='animation-reminder/'+group['group_uuid']+'/'+str(group['slot_uuid'] or 'whole')
        # Current confirmed participants only; never waitlist or cancelled people.
        people=db.execute("SELECT first_name,last_name FROM animation_bookings WHERE group_uuid=? AND status IN('confirmed','present','absent')",(group['group_uuid'],)).fetchall()
        if not people:continue
        local_start=datetime.fromisoformat(value['start']);local_end=datetime.fromisoformat(value['end'])
        payload=dict(event='reminder',title=value['title'],date=local_start.date().isoformat(),hours=local_start.strftime('%H:%M')+'–'+local_end.strftime('%H:%M'),
            participants=[p['first_name']+' '+p['last_name'] for p in people],count=len(people),token=group['manage_token'],
            information_url=value['url'],structure=setting(db,'structure_name','Mon FabLab'),timezone=str(zone))
        row=dict(group_uuid=group['group_uuid'],message_uuid=uuid4().hex,recipient=group['contact_email'],kind='reminder',payload_json=json.dumps(payload))
        try:
            link=email_link(db,database_path,payload,'reminder',group['environment'])
            message=build_message(config,row,setting(db,'reservation_public_url') or setting(db,'reservation_wordpress_url'),link,db)
        except (OSError,ValueError):continue # Not ready: no claim and no secret in log.
        if not claim(db,key,'animation_reminder',now):continue
        # Cancellation immediately before the claim prevents delivery.
        if db.execute('SELECT status FROM family_booking_groups WHERE group_uuid=?',(group['group_uuid'],)).fetchone()[0]!='confirmed':
            finish(db,key,'skipped',now);continue
        try:(mail_sender or (lambda message:send(config,message)))(message)
        except Exception as error:finish(db,key,'uncertain',now,type(error).__name__)
        else:finish(db,key,'sent',now);sent+=1
    return dict(sent=sent)
