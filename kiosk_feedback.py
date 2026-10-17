"""Optional progressive audio. A receipt belongs to the attendance transaction."""
import hashlib
import json
import secrets
from datetime import datetime,timedelta,timezone
from flask import abort,g,has_request_context,jsonify,request,session
from itsdangerous import BadSignature,SignatureExpired,URLSafeTimedSerializer


class Feedback(str):
    def __new__(cls,text,event='',replayed=False,warning=False):
        result=super().__new__(cls,text);result.event=event;result.replayed=replayed;result.warning=warning
        if has_request_context():g.kiosk_event='' if replayed else ('warning' if warning else event)
        return result


def nonce():
    return getattr(g,'kiosk_nonce',None) if has_request_context() else None


def replay(db,payload):
    key=nonce()
    if not key:return None
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    row=db.execute('SELECT payload_hash FROM kiosk_action_receipts WHERE request_key=?',(key,)).fetchone()
    if row:
        if row['payload_hash']!=digest:abort(400,'Cette action a déjà été utilisée pour une autre opération.')
        return Feedback('Cette action a déjà été prise en compte.',replayed=True)
    return None


def receipt(db,payload,result):
    key=nonce()
    if key:
        now=datetime.now(timezone.utc)
        db.execute('DELETE FROM kiosk_action_receipts WHERE created_at<?',((now-timedelta(days=1)).isoformat(),))
        db.execute('INSERT INTO kiosk_action_receipts VALUES(?,?,?,?)',(key,
            hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),
            json.dumps(dict(event=result.event,warning=result.warning)),now.isoformat()))
    return result


def register(application,a):
    serializer=URLSafeTimedSerializer(application.secret_key,salt='kiosk-action-v1')
    endpoints={'identification','toggle_presence','quick_departure','add_visitor'}

    @application.before_request
    def before():
        if request.method!='POST' or request.endpoint not in endpoints:return
        token=request.form.get('kiosk_action')
        if not token:return # Existing non-JS clients retain their existing behavior.
        try:
            value=serializer.loads(token,max_age=1200)
            if value['browser']!=session.get('kiosk_browser'):abort(400)
            g.kiosk_nonce=value['nonce']
        except (BadSignature,SignatureExpired,KeyError,TypeError):abort(400)

    @application.context_processor
    def audio_context():
        if request.endpoint not in endpoints|{'index','users','admin_settings_kiosk'}:return {}
        session.setdefault('kiosk_browser',secrets.token_urlsafe(24))
        db=a.get_database();ambience=a.read_setting(db,'kiosk_sound_ambience','auto')
        if ambience=='auto':ambience=a.load_home_theme(db)
        if ambience not in ('halloween','christmas'):ambience='classic'
        return dict(kiosk_audio=dict(enabled=a.read_setting(db,'kiosk_sound_enabled','1')=='1',
            volume=int(a.read_setting(db,'kiosk_sound_volume','50')),ambience=ambience,base=request.script_root),
            kiosk_action=serializer.dumps(dict(browser=session['kiosk_browser'],nonce=secrets.token_urlsafe(24))))

    @application.after_request
    def audio_response(response):
        if request.headers.get('X-OFL-Kiosk')=='1' and request.endpoint in endpoints and request.method=='POST' and response.status_code in (302,303):
            target=response.headers['Location']
            # Narrow response: never a directory, secret, account balance or private URL.
            response=jsonify(location=target,event=getattr(g,'kiosk_event','error'))
            response.headers['Cache-Control']='no-store'
        return response
