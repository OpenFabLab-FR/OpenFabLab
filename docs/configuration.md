# Configuration de la structure

Après initialisation Admin, ouvrir **Réglages → Structure et modules**. Compléter nom/nom court, description, coordonnées publiques, fuseau horaire, lieu et couleur. Les valeurs initiales sont « Mon FabLab » et une description générique ; les coordonnées, paramètres bancaires et localisation sont vides. Aucun catalogue ou tarif n'est imposé.

Importer uniquement des logos et une signature que votre structure est autorisée à utiliser. Les fichiers sont persistants dans `data/branding/`, pas dans les assets publics du logiciel. Le pied de page utilise le nom et la description configurés. Les documents utilisent l'identité enregistrée, pas celle d'une installation de référence.

Configurer séparément les horaires et bornes, PIN Admin/Modérateur, tarifs, machines, facturation, conservation des données et sauvegardes. Vérifier les mentions légales et contacts de protection des données propres à votre structure ; les textes génériques ne remplacent pas ces informations.

Les modules peuvent être désactivés sans convertir les données historiques. Réservations publiques est désactivé par défaut. Discord et la météo sont facultatifs ; ne fournir de webhook que dans le réglage privé prévu. La météo utilise la localisation configurée.

Les valeurs déjà enregistrées en base sont conservées lors d'une mise à jour ; les valeurs neutres ne remplacent que les clés absentes. Une remise à zéro volontaire revient aux valeurs génériques et ne restaure pas les anciennes constantes d'une structure.

Variables d'installation utiles : `OPENFABLAB_DATABASE`, `OPENFABLAB_SECRET_KEY_FILE`, `OPENFABLAB_URL_PREFIX`, `OPENFABLAB_ENABLE_SCHEDULER`, `OPENFABLAB_BACKUP_ROOT`, `OPENFABLAB_BACKUP_HOST_ROOT` (Compose). Préférer les fichiers privés et l'interface pour les secrets/PIN ; les anciens alias `COMPTEUR_*` sont conservés uniquement pour compatibilité. Ne les utiliser ni dans un exemple neuf ni dans un rapport public.
# Identité et ressources privées 2.6.2

Les logos de structure, d’en-tête institutionnel, de réseau et des documents sont indépendants. Les champs du responsable du traitement distinguent personne morale et représentant. Le badge générique peut être remplacé par un gabarit privé persistant. Voir [Branding](branding.md) pour les emplacements, les contrôles de sécurité, le profil privé et la conservation lors des mises à jour.
