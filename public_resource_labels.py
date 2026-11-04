"""Presentation vocabulary only; never rename resources or change publication."""
from family_model import setting
CHOICES={'resources':('Ressources','ressource','ressources'),
         'machines':('Machines','machine','machines'),
         'equipment':('Équipements','équipement','équipements'),
         'rooms':('Salles','salle','salles')}

def choice(db):
    value=setting(db,'resource_public_name','resources')
    return value if value in CHOICES else 'resources'

def labels(db,count):
    from i18n import t
    title,singular,plural=CHOICES[choice(db)]
    return dict(resource_public_title=t(title),
                resource_unavailable_title=t(title+' indisponibles'),
                resource_unavailable_count=t('{0} '+(singular+' indisponible' if count==1 else plural+' indisponibles'),count))
