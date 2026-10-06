# Configuration de la structure

## Réservations publiques — candidate 2.8.1

Dans Structure, conserver l’URL HTTPS du **site WordPress** et le secret déjà partagé ; aucune URL publique du NAS n’est nécessaire. Le catalogue est publié toutes les 1,5 minute par défaut. Les nouvelles demandes sont relevées séparément toutes les 15 secondes, réglables de 10 à 60 secondes entières. Le bouton de vérification force une publication du catalogue et une relève, sans créer de réservation fictive.

Le choix « Liens personnels dans les e-mails » permet de revenir vers WordPress (automatique si configuré), ou de conserver des liens OpenFabLab lorsque cette adresse est réellement accessible aux participants. Les anciennes URL restent enregistrées. Les diagnostics distinguent Normal et Test, le catalogue, la relève, les retours et les demandes en cours ; un contact signé seul ne prouve jamais qu’une réservation a réussi. Voir [le guide sortant 2.8.1](outbound-2.8.1.md).

Après initialisation Admin, ouvrir **Réglages → Structure et modules**. Compléter nom/nom court, description, coordonnées publiques, fuseau horaire, lieu et couleur. Les valeurs initiales sont « Mon FabLab » et une description générique ; les coordonnées, paramètres bancaires et localisation sont vides. Aucun catalogue ou tarif n'est imposé.

Importer uniquement des logos et une signature que votre structure est autorisée à utiliser. Les fichiers sont persistants dans `data/branding/`, pas dans les assets publics du logiciel. Le pied de page utilise le nom et la description configurés. Les documents utilisent l'identité enregistrée, pas celle d'une installation de référence.

Configurer séparément les horaires et bornes, PIN Admin/Modérateur, tarifs, machines, facturation, conservation des données et sauvegardes. Vérifier les mentions légales et contacts de protection des données propres à votre structure ; les textes génériques ne remplacent pas ces informations.

Les modules peuvent être désactivés sans convertir les données historiques. Réservations publiques est désactivé par défaut. Discord et la météo sont facultatifs ; ne fournir de webhook que dans le réglage privé prévu. La météo utilise la localisation configurée.

Les valeurs déjà enregistrées en base sont conservées lors d'une mise à jour ; les valeurs neutres ne remplacent que les clés absentes. Une remise à zéro volontaire revient aux valeurs génériques et ne restaure pas les anciennes constantes d'une structure.

Variables d'installation utiles : `OPENFABLAB_DATABASE`, `OPENFABLAB_SECRET_KEY_FILE`, `OPENFABLAB_URL_PREFIX`, `OPENFABLAB_ENABLE_SCHEDULER`, `OPENFABLAB_BACKUP_ROOT`, `OPENFABLAB_BACKUP_HOST_ROOT` (Compose). Préférer les fichiers privés et l'interface pour les secrets/PIN ; les anciens alias `COMPTEUR_*` sont conservés uniquement pour compatibilité. Ne les utiliser ni dans un exemple neuf ni dans un rapport public.
# Identité et ressources privées

Les logos de structure, d’en-tête institutionnel, de réseau et des documents sont indépendants. Les champs du responsable du traitement distinguent personne morale et représentant. Le badge générique peut être remplacé par un gabarit privé persistant. Voir [Branding](branding.md) pour les emplacements, les contrôles de sécurité, le profil privé et la conservation lors des mises à jour.

## Protection des données personnelles (2.6.3)

Renseigner la personne morale responsable du traitement, son adresse, le **Représentant** et sa fonction. Renseigner séparément **DPO / délégué à la protection des données**, **E-mail du DPO** et, facultativement, **Téléphone du DPO**. Le premier champ est libre : un service, un organisme, une personne ou toute formulation souhaitée, conservée sans découpage ni reformulation et échappée à l’affichage. L’e-mail général ne sert jamais de repli. Si ces trois champs sont vides, la carte DPO est masquée. Ces renseignements sont publics une fois configurés ; ne pas y saisir de secret.

La page Gestion des données distingue le responsable du traitement et le DPO. Elle précise qu’aucune télémétrie n’est transmise automatiquement à `https://openfablab.fr`. Les échanges facultatifs météo/Discord/WordPress restent ceux configurés pour le fonctionnement de l’installation.

## OpenFabLab 2.7.0 : usagers, intégrations et ressources

**Réglages → Usagers** regroupe les catégories (clés stables, couleur compacte, ordre, activation et catégorie par défaut), l’auto-inscription sur borne et le sujet/message de bienvenue. Installation neuve : Usager, Bénévole, Manager. Migration : toutes les catégories historiques restent conservées, y compris celles sans fiche actuelle. La borne et les notifications de création sont désactivées initialement ; les catégories ne confèrent jamais un droit d’administration.

**Réglages → Structure → SMTP natif** contient SMTP TLS/STARTTLS et son test fictif ; **Notifications** contient la sélection explicite des renseignements de création autorisés à partir vers Discord. Les coordonnées publiques de la structure peuvent être reprises dans le message de bienvenue ; le texte personnalisable permet aussi d’y préciser un lien et des informations pratiques. Les credentials SMTP ne font pas partie du profil de structure.

**Activités → Aperçu / Ressources / Réservations de ressources / Formations et habilitations** permet de choisir les catégories de ressources, forfaits, validations et autorisations nécessaires. Les deux nouveaux modules sont activés initialement ; leur désactivation masque sans supprimer. Une habilitation exigée par une ressource active interdit de masquer silencieusement le module habilitations.

Réglages : **Affichage, Usagers, Borne, Notifications, Tarifs, Données, Structure**. Protection des données/DPO dans Données ; SMTP et WordPress dans Structure ; tous les événements Discord dans Notifications. Le **Calendrier** affiche 09:00–19:00 par défaut (réglable dans Affichage), s’étend aux événements exceptionnels hors plage, et réutilise les compteurs de fréquentation pour les OpenLab passés/en cours. Consulter [le guide 2.7](evolution-2.7.md) pour les limites, la migration et un essai isolé avant toute utilisation réelle.
