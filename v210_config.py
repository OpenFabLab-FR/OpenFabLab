"""Public structure preferences; never credentials or account data."""
import json
from v210_schema import DEFAULTS

TEMPLATE_SUBJECT='{structure_name} : information sur votre formule'
TEMPLATE_BODY='Bonjour,\n\n{evenement}\nFormule : {nom_formule}\nÉchéance : {date_expiration}\nSolde : {credits_restants}\n\nPour toute question, contactez notre équipe.'
DEFAULTS=dict(DEFAULTS,membership_mail_subject=TEMPLATE_SUBJECT,membership_mail_body=TEMPLATE_BODY,
              membership_confirmation_enabled='0')
BOOLS={key for key,value in DEFAULTS.items() if value in ('0','1')}
RANGES={'membership_notice_days':(1,365),'membership_low_threshold':(0,100000),
        'kiosk_sound_volume':(0,100),'discord_sync_delay_minutes':(0,1440)}
CHOICES={'membership_control':{'informative','warning','strict'},
         'membership_hourly_shortfall':{'available','manual'},
         'kiosk_sound_ambience':{'auto','classic','halloween','christmas','summer','steampunk','easter','valentine'}}

def validate(key,value):
    if key not in DEFAULTS:raise ValueError('Réglage inconnu.')
    value=str(value)
    if key in BOOLS and value not in ('0','1'):raise ValueError('Option invalide.')
    if key in RANGES and (not value.isdecimal() or not RANGES[key][0]<=int(value)<=RANGES[key][1]):raise ValueError('Valeur hors limites : '+key)
    if key in CHOICES and value not in CHOICES[key]:raise ValueError('Choix invalide.')
    if key=='membership_exempt_categories':
        entries=json.loads(value)
        if not isinstance(entries,list) or len(entries)>500 or any(not isinstance(v,str) or len(v)>80 for v in entries):raise ValueError('Catégories invalides.')
    if key.startswith('membership_mail_'):
        import string
        if len(value)> (160 if key.endswith('subject') else 5000) or not value.strip():raise ValueError('Modèle vide ou trop long.')
        if key.endswith('subject') and any(ord(c)<32 for c in value):raise ValueError('Objet invalide.')
        for _,field,spec,conversion in string.Formatter().parse(value):
            if field is not None and (field not in {'structure_name','evenement','nom_formule','date_expiration','credits_restants'} or spec or conversion):raise ValueError('Variable de modèle inconnue.')
    return value

def preferences(db):
    stored=dict(db.execute('SELECT key,value FROM app_settings WHERE key IN('+','.join('?' for _ in DEFAULTS)+')',tuple(DEFAULTS)))
    return dict(DEFAULTS,**stored)
