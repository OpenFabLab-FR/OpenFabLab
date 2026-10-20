"""Explicit team-only controls; attendance is not a reservation operation."""
from flask import Blueprint, abort, flash, redirect, request, session, url_for
from evolution_routes import require_team, require_csrf
from types import SimpleNamespace
import animation_attendance as attendance


def register(application,a):
    a=SimpleNamespace(**a)
    bp=Blueprint('v211',__name__)

    @bp.post('/admin/reglages/presences-animations')
    def settings():
        require_team(admin=True);require_csrf()
        attendance.configure(a.get_database(),request.form.get('enabled')=='1')
        flash('Validation des présences configurée.','success')
        return redirect(url_for('admin_settings_structure')+'#presences-animations')

    @bp.post('/admin/animations/<int:service_id>/non-inscrits')
    def walkins(service_id):
        require_team();require_csrf()
        try:
            attendance.set_walkins(a.get_database(),service_id,request.form.get('quantity',''),session.get('access_role'))
            flash('Participants non inscrits enregistrés.','success')
        except ValueError as error:flash(str(error),'error')
        return redirect(url_for('admin_animation_bookings',service_id=service_id))

    application.register_blueprint(bp)
