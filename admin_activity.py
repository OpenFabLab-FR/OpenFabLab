"""Bounded administrative journal built from durable events, not page visits."""
from flask import url_for
from i18n import native, t
import machine_maintenance as machines

PROFILE_FIELDS = ('public_id','first_name','last_name','active','category','birth_year','gender','city',
                  'postal_code','nationality','email','phone_country_code','phone','birth_date',
                  'birth_precision','affiliation_client_id','affiliation_name')


def record_user_change(db, before, user_id, timestamp):
    after = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    if any(before[key] != after[key] for key in PROFILE_FIELDS):
        db.execute('INSERT INTO user_profile_activity(user_id,created_at) VALUES(?,?)', (user_id,timestamp))


def journal(db, modules, role):
    if role not in ('admin','moderator'):return []
    rows = []

    def name(row):
        return ' '.join(filter(None,(row['first_name'],row['last_name'])))

    def add(title, label, when, link, kind, person=''):
        if when:
            rows.append(dict(title=title, detail=native(label), date=when, url=link, kind=kind,person=person))

    if modules['users']:
        for row in db.execute('SELECT id,first_name,last_name,created_at FROM users ORDER BY created_at DESC,id DESC LIMIT 15'):
            add(row['first_name']+' '+row['last_name'], 'Compte usager créé', row['created_at'],
                url_for('v215.user_history',user_id=row['id']), 'people')
        for row in db.execute('''SELECT u.id,u.first_name,u.last_name,e.created_at FROM user_profile_activity e
            JOIN users u ON u.id=e.user_id ORDER BY e.created_at DESC,e.id DESC LIMIT 15'''):
            add(row['first_name']+' '+row['last_name'], 'Compte usager modifié', row['created_at'],
                url_for('v215.user_history',user_id=row['id']), 'people')
    if modules['activities'] and modules['public_reservations']:
        for row in db.execute('''SELECT s.id,s.title,b.created_at,b.first_name,b.last_name FROM animation_bookings b JOIN fablab_services s ON s.id=b.service_id
            WHERE b.group_uuid IS NULL OR NOT EXISTS(SELECT 1 FROM animation_bookings newer
                WHERE newer.group_uuid=b.group_uuid AND (newer.created_at,newer.external_uuid)>(b.created_at,b.external_uuid))
            ORDER BY b.created_at DESC,b.external_uuid DESC LIMIT 15'''):
            add(row['title'], 'Inscription à une animation', row['created_at'],
                url_for('admin_animation_bookings',service_id=row['id']), 'calendar',name(row))
    if modules['resources']:
        for row in db.execute('''SELECT b.booking_uuid,r.name,b.created_at,u.first_name,u.last_name FROM resource_bookings b JOIN resources r USING(resource_uuid)
            LEFT JOIN users u ON u.id=b.user_id
            ORDER BY b.created_at DESC,b.booking_uuid DESC LIMIT 15'''):
            add(row['name'], 'Réservation de ressource', row['created_at'],
                url_for('evolution.resource_bookings')+'#reservation-'+row['booking_uuid'], 'loan',name(row) if modules['users'] else '')
        for row in db.execute('''SELECT b.booking_uuid,r.name,e.action,e.created_at,u.first_name,u.last_name FROM evolution_audit e
            JOIN resource_bookings b ON b.booking_uuid=e.entity_key JOIN resources r USING(resource_uuid)
            LEFT JOIN users u ON u.id=b.user_id
            WHERE e.entity_type='resource_booking' AND e.action IN('confirmed','refused','cancelled','performed','billing_linked')
            AND e.id>(SELECT MIN(i.id) FROM evolution_audit i WHERE i.entity_type='resource_booking'
                      AND i.entity_key=e.entity_key)
            ORDER BY e.created_at DESC,e.id DESC LIMIT 15'''):
            add(row['name'], 'Réservation modifiée', row['created_at'],
                url_for('evolution.resource_bookings')+'#reservation-'+row['booking_uuid'], 'loan',name(row) if modules['users'] else '')
    if modules['resources'] or machines.enabled(db):
        for row in db.execute('''SELECT s.report_id,s.resource_uuid,r.name,s.received_at FROM resource_problem_reports s
            JOIN resources r USING(resource_uuid) ORDER BY s.received_at DESC LIMIT 15'''):
            add(row['name'], 'Nouveau signalement', row['received_at'],
                url_for('resource_portal.page',key=row['resource_uuid'],report=row['report_id'],_anchor='signalement-'+row['report_id']), 'report')
    if machines.enabled(db):
        for row in db.execute('''SELECT r.name,h.resource_uuid,h.action,h.entity_uuid,h.created_at,h.actor FROM machine_history h
            JOIN resources r USING(resource_uuid)
            WHERE h.action='intervention' OR (h.action='condition' AND
              CASE WHEN json_valid(h.before_json) AND json_valid(h.after_json) THEN
                json_extract(h.before_json,'$.status') IS NOT json_extract(h.after_json,'$.status') ELSE 0 END)
            ORDER BY h.created_at DESC,h.id DESC LIMIT 15'''):
            section = 'availability' if row['action']=='condition' else 'intervention-'+row['entity_uuid']
            add(row['name'], 'État de la ressource modifié' if row['action']=='condition' else 'Intervention enregistrée',
                row['created_at'],url_for('resource_portal.page',key=row['resource_uuid'],_anchor=section),'resource',
                t({'admin':'Administrateur','moderator':'Modérateur'}.get(row['actor'],'')).strip())
    if role=='admin' and modules['billing']:
        for column,label,where,kind in (
            ('created_at','Devis créé','quote_number IS NOT NULL','quote'),
            ('quote_signed_at','Devis signé','quote_signed_at IS NOT NULL','quote'),
            ('invoice_date','Facture datée','invoice_number IS NOT NULL','invoice'),
            ('paid_at','Facture réglée','paid_at IS NOT NULL','invoice'),
        ):
            for row in db.execute(f'SELECT id,title,client_structure,client_contact,{column} AS stamp FROM billing_records WHERE {where} ORDER BY {column} DESC,id DESC LIMIT 15'):
                add(row['title'],label,row['stamp'],url_for('admin_billing_detail',record_id=row['id']),kind,row['client_structure'] or row['client_contact'])
    # The existing audit has one handover/return event per real action, not
    # per reservation date. Ignore orphaned rows and hide contract data from moderators.
    if modules['resources'] or role=='admin' and modules['billing'] and modules['rentals']:
        for row in db.execute('''SELECT e.action,e.created_at,e.entity_key,b.booking_uuid,c.id AS contract_id,r.name,
            c.client_structure,c.client_contact,u.first_name,u.last_name
            FROM evolution_audit e
            LEFT JOIN resource_bookings b ON b.booking_uuid=CASE WHEN substr(e.entity_key,1,8)='booking:' THEN substr(e.entity_key,9) END
            LEFT JOIN billing_records c ON c.id=CASE WHEN substr(e.entity_key,1,9)='contract:' THEN CAST(substr(e.entity_key,10) AS INTEGER) END
            JOIN resources r ON r.resource_uuid=b.resource_uuid OR r.legacy_machine_key=c.rental_machine_key
            LEFT JOIN users u ON u.id=COALESCE(b.user_id,c.rental_user_id)
            WHERE e.entity_type='resource_loan' AND ((? AND b.booking_uuid IS NOT NULL) OR (? AND c.id IS NOT NULL))
            ORDER BY e.created_at DESC,e.id DESC LIMIT 15''',(int(modules['resources']),int(role=='admin' and modules['billing'] and modules['rentals']))):
            link=(url_for('admin_billing_detail',record_id=row['contract_id']) if row['contract_id'] is not None else
                  url_for('evolution.resource_bookings')+'#reservation-'+row['booking_uuid'])
            person=name(row) if modules['users'] else ''
            if not person and row['contract_id'] is not None:person=row['client_structure'] or row['client_contact']
            add(row['name'],'Matériel remis' if row['action']=='handover' else 'Matériel restitué',row['created_at'],link,'loan',person)
    return rows
