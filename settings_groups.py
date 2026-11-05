"""Presentation registry; existing settings endpoints and preferences remain."""
from flask import url_for
GROUPS=[
 ('structure','Structure et identité','admin_settings_structure',{'admin_settings_structure'}),
 ('kiosk','Accueil et borne','admin_settings_kiosk',{'admin_settings_kiosk','admin_settings_display'}),
 ('activities','Calendrier et activités','v215.calendar_settings',{'v215.calendar_settings','admin_settings_tariffs'}),
 ('resources','Ressources et maintenance','resource_portal.settings',{'resource_portal.settings'}),
 ('communication','Communication','admin_notifications',{'admin_notifications','reservation_emails.settings'}),
 ('wordpress','WordPress','v215.wordpress_settings',{'v215.wordpress_settings','admin_settings_reservations','evolution.integrations'}),
 ('users','Usagers et permissions','evolution.users_settings',{'evolution.users_settings'}),
 ('system','Système et sauvegardes','v215.updates',{'v215.updates','admin_settings_data'}),
]

def navigation(endpoint):
    return [dict(key=key,label=label,url=url_for(target),active=endpoint in endpoints) for key,label,target,endpoints in GROUPS]

def secondary(endpoint):
    for key,_,_,endpoints in GROUPS:
        if endpoint not in endpoints:continue
        choices={
          'kiosk':[('admin_settings_kiosk','Borne et sécurité'),('admin_settings_display','Apparence et affichage')],
          'activities':[('v215.calendar_settings','Calendrier et inscriptions'),('admin_settings_tariffs','Tarifs de facturation')],
          'users':[('evolution.users_settings','Comptes et catégories'),('admin_settings_kiosk','Codes d’accès à l’administration')],
          'system':[('v215.updates','Mises à jour'),('admin_settings_data','Santé, sauvegardes et données')],
        }.get(key,[])
        return [dict(label=label,url=url_for(target)+('#sensitive-access' if key=='users' and target=='admin_settings_kiosk' else ''),active=endpoint==target) for target,label in choices]
    return []
