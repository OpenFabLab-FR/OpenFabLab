"""Explicit staff linking: one existing participant, no new booking or account."""
import sqlite3
import family_model as family
import family_reservations as engine


def attach(db,service_id,booking_uuid,user_id,role,consent=False):
    from outbound_actions import transaction
    if role not in ('admin','moderator') or consent is not True:
        raise ValueError('Confirmez explicitement le rattachement au compte choisi.')
    with transaction(db):
        booking=db.execute('SELECT * FROM animation_bookings WHERE external_uuid=? AND service_id=?',(booking_uuid,service_id)).fetchone()
        person=db.execute('SELECT * FROM users WHERE id=? AND active=1',(user_id,)).fetchone()
        if not booking or not person:raise ValueError('Participant ou compte indisponible.')
        if booking['user_id'] is not None:
            if booking['user_id']==person['id']:return False
            raise ValueError('Cette personne est déjà rattachée à un compte. Rien n’a été fusionné.')
        # Linking is administrative identity metadata, not a new enrollment:
        # an unpublished/closed animation must remain linkable.
        service_row=db.execute("SELECT s.*,c.capacity AS booking_capacity FROM fablab_services s LEFT JOIN animation_reservation_config c ON c.service_id=s.id WHERE s.id=? AND s.service_type='animation'",(service_id,)).fetchone()
        if not service_row:raise ValueError('Animation indisponible.')
        service=dict(service_row,capacity=service_row['booking_capacity'] or service_row['expected_participants'] or 1)
        if booking['slot_uuid']:
            slot=db.execute('SELECT starts_at,capacity FROM animation_slots WHERE service_id=? AND slot_uuid=?',(service_id,booking['slot_uuid'])).fetchone()
            if not slot:raise ValueError('Créneau introuvable ; le rattachement a été interrompu.')
            from datetime import datetime
            from zoneinfo import ZoneInfo
            service.update(capacity=slot['capacity'],service_date=datetime.fromisoformat(slot['starts_at']).astimezone(ZoneInfo(family.setting(db,'structure_timezone','Europe/Paris'))).date().isoformat())
        others=db.execute("SELECT * FROM animation_bookings WHERE group_uuid=? AND external_uuid<>? AND status NOT IN('cancelled','expired','declined')",(booking['group_uuid'],booking_uuid)).fetchall() if booking['group_uuid'] else []
        if any(row['user_id'] is None for row in others):raise ValueError('Vérifiez d’abord les autres participants sans compte avec l’équipe.')
        engine.participants(db,person['id'],[person['id']]+[row['user_id'] for row in others],service,True)
        duplicate=db.execute("SELECT 1 FROM animation_bookings WHERE external_uuid<>? AND service_id=? AND environment=? AND COALESCE(slot_uuid,'')=? AND (user_id=? OR public_id=?) AND status NOT IN('cancelled','expired','declined')",(booking_uuid,service_id,booking['environment'],booking['slot_uuid'] or '',person['id'],person['public_id'])).fetchone()
        if duplicate and booking['status'] not in ('cancelled','expired','declined'):
            raise ValueError('Ce compte possède déjà une inscription active pour cette animation. Rien n’a été fusionné.')
        stamp=family.timestamp()
        db.execute("UPDATE animation_bookings SET user_id=?,public_id=?,link_status='manual',verified_at=?,verified_by_role=? WHERE external_uuid=?",(person['id'],person['public_id'],stamp,role,booking_uuid))
        db.execute('INSERT INTO reservation_actions(booking_uuid,action,actor_role,created_at) VALUES(?,?,?,?)',(booking_uuid,'link_account:'+str(person['id']),role,stamp))
        if booking['group_uuid'] and db.execute('SELECT 1 FROM family_booking_groups WHERE group_uuid=?',(booking['group_uuid'],)).fetchone():
            db.execute('INSERT INTO family_booking_history(group_uuid,status,actor,created_at) VALUES(?,?,?,?)',(booking['group_uuid'],'linked',role,stamp))
        return True


def register(application,a):
    from flask import Blueprint,abort,flash,redirect,render_template,request,url_for
    from evolution_routes import require_team,require_csrf
    from participant_search import search_users
    bp=Blueprint('booking_account_links',__name__)
    @bp.route('/admin/animations/<int:service_id>/inscriptions/<booking_uuid>/compte',methods=['GET','POST'])
    def link(service_id,booking_uuid):
        role=require_team();db=a.get_database()
        booking=db.execute('SELECT * FROM animation_bookings WHERE service_id=? AND external_uuid=?',(service_id,booking_uuid)).fetchone()
        if not booking:abort(404)
        selected=None;errors=[]
        if request.method=='POST':
            require_csrf()
            try:
                selected=db.execute('SELECT id,public_id,first_name,last_name FROM users WHERE id=? AND active=1',(int(request.form.get('person_id','')),)).fetchone()
                if not selected:raise ValueError('Choisissez un compte actif.')
                if request.form.get('action')=='attach':
                    attach(db,service_id,booking_uuid,selected['id'],role,request.form.get('consent')=='1')
                    flash('La réservation est rattachée au compte choisi. Les places et l’historique sont conservés.','success')
                    return redirect(url_for('admin_animation_bookings',service_id=service_id))
            except (ValueError,sqlite3.IntegrityError) as error:errors.append(str(error))
        return render_template('booking_account_link.html',booking=booking,selected=selected,
            users=search_users(db,request.args.get('usager',''))['users'],errors=errors)
    application.register_blueprint(bp)
