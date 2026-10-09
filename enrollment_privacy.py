"""Revocable, form-scoped public enrollment; no permanent identity change.

Only scoped hashes and expirations use the existing temporary nonce registry.
No contact, raw token or new schema is stored. Cookie replay cannot revive a
revoked form. A new form always revokes the previous form on the shared device.
"""
import hashlib
import hmac
import secrets
import time
from flask import abort, current_app, redirect, request, session, url_for

TTL = 900
KEYS = ('enrollment_started', 'enrollment_proposal', 'enrollment_mode',
        'family_enrollment_guardian', '_enrollment_flow', '_enrollment_previous_document')


def _prefix():
    device = session.get('_enrollment_device', '')
    if not device:
        return None
    digest = hmac.new(str(current_app.secret_key).encode(), device.encode(), hashlib.sha256).hexdigest()
    return 'enrollment:' + digest + ':'


def _key():
    prefix, flow = _prefix(), session.get('_enrollment_flow', '')
    return prefix + hashlib.sha256(flow.encode()).hexdigest() if prefix and flow else None


def forget():
    for key in KEYS:
        session.pop(key, None)


def abandon(db):
    prefix = _prefix()
    if prefix:
        with db:
            db.execute('DELETE FROM family_api_nonces WHERE nonce_hash LIKE ?', (prefix + '%',))
    forget()


def begin(db):
    abandon(db)
    session.pop('enrollment_receipt', None)
    session.setdefault('_enrollment_device', secrets.token_urlsafe(32))
    session['_enrollment_flow'] = secrets.token_urlsafe(32)
    session['enrollment_started'] = time.time()
    # Existing hidden CSRF also binds cached forms to this particular enrollment.
    session['evolution_csrf'] = secrets.token_urlsafe(32)
    with db:
        db.execute("DELETE FROM family_api_nonces WHERE nonce_hash LIKE 'enrollment:%' AND expires_at<=?", (int(time.time()),))
        db.execute('INSERT INTO family_api_nonces(nonce_hash,expires_at) VALUES(?,?)', (_key(), int(time.time()) + TTL))


def active(db):
    key = _key()
    if not key or not session.get('enrollment_started') or time.time() - session['enrollment_started'] >= TTL:
        return False
    row = db.execute('SELECT expires_at FROM family_api_nonces WHERE nonce_hash=?', (key,)).fetchone()
    return bool(row and row[0] > time.time())


def require_active(db):
    if not active(db):
        abandon(db)
        abort(400, 'Cette inscription a expiré ou a été quittée. Ouvrez un nouveau formulaire depuis l’accueil.')


def remember_guardian(db, user_id):
    require_active(db)
    session['family_enrollment_guardian'] = {
        'id': user_id, 'until': session['enrollment_started'] + TTL,
        'flow': session['_enrollment_flow']}


def guardian_id(db):
    grant = session.get('family_enrollment_guardian', {})
    if (not active(db) or grant.get('flow') != session.get('_enrollment_flow') or
            grant.get('until', 0) <= time.time()):
        return None
    return grant.get('id')


def consume(db):
    """Called inside account creation's BEGIN IMMEDIATE; rollback restores it."""
    if not active(db):
        raise ValueError('Cette inscription a déjà été validée ou quittée. Revenez à l’accueil.')
    result = db.execute('DELETE FROM family_api_nonces WHERE nonce_hash=? AND expires_at>?', (_key(), int(time.time())))
    if result.rowcount != 1:
        raise ValueError('Cette inscription n’est plus disponible. Revenez à l’accueil.')


def register(application, api):
    @application.before_request
    def public_post_scope():
        if request.endpoint == 'evolution.enroll' and request.method == 'POST':
            db = api.get_database()
            if not api.load_modules(db)['users'] or api.read_setting(db, 'self_enrollment_enabled', '0') != '1':
                abort(404)
            require_active(db)
            # WebKit may reload a POST as a fresh navigation. A previously
            # rendered submission cannot redisplay personal data on refresh.
            received=request.form.get('evolution_csrf','')
            if not received or not hmac.compare_digest(received,session.get('evolution_csrf','')):
                if received and hmac.compare_digest(hashlib.sha256(received.encode()).hexdigest(),session.get('_enrollment_previous_document','')):
                    return redirect(url_for('evolution.enroll'),code=303)
                abort(400)

    @application.after_request
    def leaving_public_enrollment(response):
        allowed = {'evolution.enroll', 'evolution.enrollment_done', 'evolution.enrollment_qr'}
        if (session.get('_enrollment_flow') and request.endpoint not in allowed and
                response.mimetype == 'text/html' and response.status_code < 400):
            abandon(api.get_database())
        return response
