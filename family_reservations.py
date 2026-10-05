"""Single transactional booking engine for kiosk, team and optional WP gateway.

Every booking row represents one real user and consumes one seat. No companion
row or split submission is generated. Historical rows retain their old data.
"""
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo
import family_model as family


def effective_service(db, service_id, slot_uuid=None, environment='production', check_open=True):
    row=db.execute("SELECT s.*,c.* FROM fablab_services s JOIN animation_reservation_config c ON c.service_id=s.id WHERE s.id=? AND s.service_type='animation'",(service_id,)).fetchone()
    if not row or not row['enabled'] or row['environment']!=environment:
        raise ValueError('Animation indisponible.')
    service=dict(row)
    zone=ZoneInfo(family.setting(db,'structure_timezone','Europe/Paris'))
    start=datetime.fromisoformat(service['service_date']+'T'+(service['start_time'] or '00:00')).replace(tzinfo=zone)
    if service['booking_mode']=='slots':
        slot=db.execute('SELECT * FROM animation_slots WHERE service_id=? AND slot_uuid=? AND active=1',(service_id,slot_uuid)).fetchone()
        if not slot:
            raise ValueError('Choisissez un créneau ouvert.')
        start=datetime.fromisoformat(slot['starts_at']).astimezone(zone)
        service.update(capacity=slot['capacity'],service_date=start.date().isoformat())
    elif slot_uuid:
        raise ValueError('Cette animation ne comporte pas de créneau individuel.')
    if check_open:
        now=datetime.now(timezone.utc)
        opening=datetime.fromisoformat(service['signup_open_at'].replace('Z','+00:00')) if service['signup_open_at'] else None
        if opening and not opening.tzinfo:
            opening=opening.replace(tzinfo=zone)
        if (opening and now<opening) or now>=start-timedelta(minutes=service['close_minutes']):
            raise ValueError('Les inscriptions à cette animation sont closes.')
    return service


def choices(db, owner_id, today=None):
    owner=db.execute('SELECT * FROM users WHERE id=? AND active=1',(owner_id,)).fetchone()
    if not owner:
        raise ValueError('Compte inactif ou inconnu.')
    linked=family.members(db,owner_id) if family.eligible(db,owner,today) else []
    result={owner_id:dict(owner,label='Moi-même')}
    result.update({u['id']:dict(u,label='Membre rattaché') for u in linked if u['active']})
    for member in [owner,*linked]:
        for responsible in family.responsibles(db,member['id']):
            if family.eligible(db,responsible,today):
                result.setdefault(responsible['id'],dict(responsible,label='Responsable'))
    return list(result.values())


def participants(db, owner_id, ids, service, staff=False):
    try:
        selected=list(dict.fromkeys(int(i) for i in ids))
    except (TypeError,ValueError):
        raise ValueError('Sélection de participants invalide.')
    if not selected or len(selected)>20:
        raise ValueError('Sélectionnez de 1 à 20 participants.')
    today=date.fromisoformat(service['service_date'])
    allowed={u['id']:u for u in choices(db,owner_id,today)} if not staff else {
        u['id']:dict(u) for u in db.execute('SELECT * FROM users WHERE active=1')}
    if not set(selected)<=set(allowed):
        raise ValueError('Choisissez uniquement des comptes actifs autorisés.')
    people=[allowed[i] for i in selected]
    for user in people:
        age=family.age(user,today)
        if age is None or age<int(service['minimum_age']):
            raise ValueError('L’âge minimum de cette animation doit être respecté par chaque participant.')
        if family.state(db,user,today)=='dependent':
            guardians={r['id'] for r in family.responsibles(db,user['id']) if family.eligible(db,r,today)}
            if not guardians & set(selected):
                raise ValueError(user['first_name']+' doit participer avec un responsable. Sélectionnez également un responsable rattaché à son compte.')
    if len(people)>int(service['capacity']):
        raise ValueError('Le groupe dépasse la capacité totale de cette animation ou de ce créneau.')
    return people


def result(db, group):
    rows=db.execute('SELECT external_uuid,status FROM animation_bookings WHERE group_uuid=? ORDER BY external_uuid',(group,)).fetchall()
    states={r['status'] for r in rows}
    meta=db.execute('SELECT status FROM family_booking_groups WHERE group_uuid=?',(group,)).fetchone()
    return {'group_uuid':group,'status':meta['status'] if meta else next(iter(states)) if len(states)==1 else 'updated',
            'count':len([r for r in rows if r['status'] not in ('cancelled','expired','declined')]),
            'booking_uuids':[r['external_uuid'] for r in rows]}


def reserve(db, owner_id, ids, service_id, slot_uuid, request_key, environment='production', source='kiosk', staff=False):
    if source not in ('kiosk','wordpress','administration') or not re.fullmatch(r'[A-Za-z0-9_-]{24,100}',str(request_key)):
        raise ValueError('Demande invalide.')
    try:
        selected=sorted(set(int(i) for i in ids))
    except (TypeError,ValueError):
        raise ValueError('Sélection invalide.')
    fingerprint=hashlib.sha256(json.dumps([owner_id,selected,service_id,slot_uuid or '',environment],separators=(',',':')).encode()).hexdigest()
    db.execute('BEGIN IMMEDIATE')
    try:
        import family_waitlist as waiting
        waiting.adopt_candidates(db)
        waiting.settle(db)
        prior=db.execute('SELECT * FROM family_booking_requests WHERE request_key=?',(request_key,)).fetchone()
        if prior:
            if not hmac.compare_digest(prior['request_hash'],fingerprint):
                raise ValueError('Cette demande a déjà été utilisée pour un autre choix.')
            value=result(db,prior['group_uuid']);db.commit();return value
        service=effective_service(db,service_id,slot_uuid,environment,check_open=not staff)
        people=participants(db,owner_id,selected,service,staff)
        details=waiting.require_contact(db,owner_id,people)
        for person in people:
            duplicate=db.execute("SELECT 1 FROM animation_bookings WHERE service_id=? AND environment=? AND COALESCE(slot_uuid,'')=? AND (user_id=? OR public_id=?) AND status NOT IN('cancelled','expired','declined')",(service_id,environment,slot_uuid or '',person['id'],person['public_id'])).fetchone()
            if duplicate:
                raise ValueError('Une inscription existe déjà pour un participant sélectionné.')
        from reservations_sync import booking_capacity_used
        available=service['capacity']-booking_capacity_used(db,service_id,slot_uuid)
        state='confirmed' if available>=len(people) else 'waitlisted'
        if state=='waitlisted' and not service['waitlist_enabled']:
            raise ValueError('Il ne reste pas assez de places pour tout le groupe. La liste d’attente est fermée.')
        group=str(uuid4());now=family.timestamp()
        for person in people:
            db.execute('''INSERT INTO animation_bookings(external_uuid,service_id,environment,first_name,last_name,birth_year,email,phone,status,link_status,public_id,user_id,group_uuid,source,is_present,created_at,updated_at,slot_uuid)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (str(uuid4()),service_id,environment,person['first_name'],person['last_name'],person['birth_year'],None,None,state,'registered',person['public_id'],person['id'],group,'family_'+source,None,now,now,slot_uuid or None))
        db.execute('INSERT INTO family_booking_requests VALUES(?,?,?,?,?,?)',(request_key,fingerprint,owner_id,group,source,now))
        waiting.create_group(db,group,owner_id,service_id,slot_uuid,environment,state,details)
        value=result(db,group);db.commit();return value
    except Exception:
        db.rollback();raise


def limit_identification(db, bucket):
    # Server-side rate limit survives new cookies; hashes avoid storing contacts.
    now=int(time.time())
    safe_bucket=hashlib.sha256(str(bucket).encode()).hexdigest()
    db.execute('BEGIN IMMEDIATE')
    try:
        since=(datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat()
        detail=json.dumps({'family_bucket':safe_bucket})
        attempts=db.execute("SELECT COUNT(*) FROM security_events WHERE event_type='family_identify_attempt' AND created_at>? AND details_json=?",(since,detail)).fetchone()[0]
        if attempts>=5:
            raise ValueError('Trop de tentatives. Patientez avant de réessayer.')
        db.execute('INSERT INTO security_events(event_type,created_at,details_json) VALUES(?,?,?)',('family_identify_attempt',family.timestamp(),detail));db.commit()
    except Exception:
        db.rollback();raise
    return now


def matching_account(db, public_id, contact):
    user=db.execute('SELECT * FROM users WHERE public_id=? AND active=1',(str(public_id),)).fetchone()
    from reservations_sync import normalize_phone
    contact=str(contact).strip()
    matched=bool(user and contact and ((user['email'] and hmac.compare_digest(user['email'].casefold().encode(),contact.casefold().encode())) or (user['phone'] and hmac.compare_digest(normalize_phone(user['phone_country_code'],user['phone']),normalize_phone('',contact)))))
    return user if matched else None


def identify(db, service_id, public_id, contact, bucket, environment='production'):
    now=limit_identification(db,bucket)
    config=db.execute('SELECT enabled,environment FROM animation_reservation_config WHERE service_id=?',(service_id,)).fetchone()
    if not config or not config['enabled'] or config['environment']!=environment:
        raise ValueError('Animation indisponible.')
    user=matching_account(db,public_id,contact)
    if not user:
        raise ValueError('Identifiant ou coordonnée non concordants. Adressez-vous à l’équipe.')
    token=secrets.token_urlsafe(32)
    with db:
        db.execute('DELETE FROM family_booking_grants WHERE expires_at<?',(now,))
        db.execute('INSERT INTO family_booking_grants VALUES(?,?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user['id'],service_id,environment,now+900))
    return token,user['id']


def grant(db, token, service_id, environment):
    if not isinstance(token,str) or len(token)>100:
        raise ValueError('Identification requise.')
    row=db.execute('SELECT * FROM family_booking_grants WHERE token_hash=? AND service_id=? AND environment=? AND expires_at>?',(hashlib.sha256(token.encode()).hexdigest(),service_id,environment,int(time.time()))).fetchone()
    if not row:
        raise ValueError('Identification expirée. Identifiez-vous à nouveau.')
    return row['owner_id']


def team_action(db, service_id, booking_uuid, action, role, person_id=None):
    """Team rights are checked by the route; business checks remain here."""
    if role not in ('admin','moderator') or action not in ('confirm','cancel','remove','add','present','absent','verify'):
        raise ValueError('Action non autorisée pour cette réservation.')
    db.execute('BEGIN IMMEDIATE')
    try:
        import family_waitlist as waiting
        waiting.adopt_candidates(db)
        waiting.settle(db)
        booking=db.execute('SELECT * FROM animation_bookings WHERE service_id=? AND external_uuid=?',(service_id,booking_uuid)).fetchone()
        if not booking or not booking['source'].startswith('family_'):
            raise ValueError('Réservation inconnue.')
        group=db.execute("SELECT * FROM animation_bookings WHERE group_uuid=? AND status NOT IN('cancelled','expired','declined')",(booking['group_uuid'],)).fetchall()
        now=family.timestamp()
        if action=='add':
            if not group or len({b['status'] for b in group})!=1 or group[0]['status'] not in ('confirmed','waitlisted'):
                raise ValueError('Ce groupe ne peut pas être complété dans son état actuel.')
            service=effective_service(db,service_id,booking['slot_uuid'],booking['environment'],False)
            selected=[b['user_id'] for b in group]+[person_id]
            people=participants(db,group[0]['user_id'],selected,service,True)
            if len(people)!=len(group)+1:
                raise ValueError('Cette personne fait déjà partie de la demande.')
            person=next(p for p in people if p['id']==int(person_id))
            duplicate=db.execute("SELECT 1 FROM animation_bookings WHERE service_id=? AND environment=? AND COALESCE(slot_uuid,'')=? AND (user_id=? OR public_id=?) AND status NOT IN('cancelled','expired','declined')",(service_id,booking['environment'],booking['slot_uuid'] or '',person['id'],person['public_id'])).fetchone()
            if duplicate:
                raise ValueError('Une inscription existe déjà pour cette personne.')
            from reservations_sync import booking_capacity_used
            if group[0]['status']=='confirmed' and booking_capacity_used(db,service_id,booking['slot_uuid'])>=service['capacity']:
                raise ValueError('Aucune place disponible. Le groupe confirmé reste inchangé.')
            db.execute('''INSERT INTO animation_bookings(external_uuid,service_id,environment,first_name,last_name,birth_year,email,phone,status,link_status,public_id,user_id,group_uuid,source,is_present,created_at,updated_at,slot_uuid)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (str(uuid4()),service_id,booking['environment'],person['first_name'],person['last_name'],person['birth_year'],None,None,group[0]['status'],'registered',person['public_id'],person['id'],booking['group_uuid'],'family_administration',None,now,now,booking['slot_uuid']))
        elif action=='confirm':
            if not group or any(b['status'] not in ('waitlisted','offer_pending') for b in group):
                raise ValueError('Le groupe ne peut pas être confirmé dans son état actuel.')
            service=effective_service(db,service_id,booking['slot_uuid'],booking['environment'],False)
            participants(db,group[0]['user_id'],[b['user_id'] for b in group],service,True)
            from reservations_sync import booking_capacity_used
            if booking_capacity_used(db,service_id,booking['slot_uuid'])+sum(b['status']=='waitlisted' for b in group)>service['capacity']:
                raise ValueError('Il ne reste pas assez de places pour confirmer tout le groupe.')
            db.execute("UPDATE animation_bookings SET status='confirmed',updated_at=? WHERE group_uuid=? AND status IN('waitlisted','offer_pending')",(now,booking['group_uuid']))
            waiting.transition(db,booking['group_uuid'],'confirmed',role)
        elif action=='cancel':
            waiting.transition(db,booking['group_uuid'],'cancelled',role)
            # Local earlier candidates without a valid contact remain readable.
            db.execute("UPDATE animation_bookings SET status='cancelled',is_present=0,updated_at=? WHERE group_uuid=? AND status NOT IN('cancelled','expired','declined')",(now,booking['group_uuid']))
        elif action=='remove':
            remaining=[b['user_id'] for b in group if b['external_uuid']!=booking_uuid]
            if remaining:
                service=effective_service(db,service_id,booking['slot_uuid'],booking['environment'],False)
                participants(db,remaining[0],remaining,service,True)
            db.execute("UPDATE animation_bookings SET status='cancelled',is_present=0,updated_at=? WHERE external_uuid=?",(now,booking_uuid))
        elif action in ('present','absent'):
            if booking['status']!='confirmed':
                raise ValueError('Confirmez d’abord tout le groupe avant de renseigner une présence.')
            db.execute('UPDATE animation_bookings SET is_present=?,updated_at=? WHERE external_uuid=?',(int(action=='present'),now,booking_uuid))
        else:
            db.execute('UPDATE animation_bookings SET verified_at=?,verified_by_role=?,updated_at=? WHERE external_uuid=?',(now,role,now,booking_uuid))
        db.execute('INSERT INTO reservation_actions(booking_uuid,action,actor_role,created_at) VALUES(?,?,?,?)',(booking_uuid,action,role,now))
        if action in ('add','remove'):
            meta=db.execute('SELECT * FROM family_booking_groups WHERE group_uuid=?',(booking['group_uuid'],)).fetchone()
            if meta:
                db.execute('UPDATE family_booking_groups SET revision=revision+1,updated_at=? WHERE group_uuid=?',(now,booking['group_uuid']))
                db.execute('INSERT INTO family_booking_history(group_uuid,status,actor,created_at) VALUES(?,?,?,?)',(booking['group_uuid'],'modified',role,now))
                if waiting._active(db,booking['group_uuid']):
                    waiting._queue(db,booking['group_uuid'],'modified')
                else:
                    waiting.transition(db,booking['group_uuid'],'cancelled',role)
        waiting.settle(db)
        db.execute("UPDATE fablab_services SET actual_participants=COALESCE((SELECT walkin_count FROM animation_reservation_config WHERE service_id=?),0)+(SELECT COUNT(*) FROM animation_bookings WHERE service_id=? AND status IN('confirmed','present') AND is_present=1) WHERE id=?",(service_id,service_id,service_id))
        db.commit()
    except Exception:
        db.rollback();raise
