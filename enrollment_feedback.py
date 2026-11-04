"""Feedback for an already-authorized enrollment POST, not an ID lookup API."""
import hashlib,secrets,time
from flask import jsonify,request,session
from i18n import t

USED_ID='Cet identifiant est déjà utilisé. Choisissez-en un autre.'
OLD_USED_ID='Cet identifiant est déjà utilisé par un autre usager.'
TEMPORARY='L’inscription ne peut pas être enregistrée pour le moment. Vos informations sont conservées. Réessayez dans un instant.'

def rotate_document():
    session['_enrollment_previous_document']=hashlib.sha256(session.get('evolution_csrf','').encode()).hexdigest()
    session['evolution_csrf']=secrets.token_urlsafe(32)
    return session['evolution_csrf']

def enhanced():
    return request.method=='POST' and request.headers.get('X-OpenFabLab-Enrollment-Form')=='1' and request.accept_mimetypes.best=='application/json'

def field_errors(errors):
    # Only native validation messages. Never interpolate another account's data
    # or expose the text of a database/server exception.
    fields={}
    for message in errors:
        if message.startswith('Coordonnées obligatoires : '):
            missing=message.removeprefix('Coordonnées obligatoires : ').rstrip('.')
            for label,key in (('e-mail','email'),('téléphone','phone')):
                if label in missing:fields.setdefault(key,message)
            continue
        if message==USED_ID or message.startswith("L'identifiant doit"):key='public_id'
        elif message=='Le prénom est obligatoire.':key='first_name'
        elif message=='Le nom est obligatoire.':key='last_name'
        elif message.startswith("L'adresse e-mail"):key='email'
        elif message.startswith("L'année de naissance"):key='birth_year'
        elif message.startswith(('Date de naissance','La date de naissance')):key='birth_date'
        elif message.startswith('Le numéro de téléphone'):key='phone'
        elif message.startswith("L'indicatif téléphonique"):key='phone_country_code'
        else:continue
        fields.setdefault(key,message)
    return fields

def response(user,errors,status,render,proposal=False):
    fields=field_errors(errors)
    if enhanced():
        value=dict(enrollment=True,ok=False,errors=[t(e) for e in errors],
                   field_errors={key:t(value) for key,value in fields.items()},csrf_token=rotate_document())
        if proposal:value['proposed_id']=user['public_id']
        return jsonify(value),status
    return render('user_form.html',user=user,form_mode='create',kiosk=True,errors=errors,
                  enrollment_field_errors=fields,duplicate_users=[]),status

def remaining_seconds():
    from enrollment_privacy import TTL
    return max(0,int(TTL-(time.time()-session.get('enrollment_started',0))))
