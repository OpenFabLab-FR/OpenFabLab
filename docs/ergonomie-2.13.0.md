# OpenFabLab 2.13.0 — Activités et Réglages

Cette version stable fait évoluer la 2.12.0, avec une validation en usage réel.
SQLite reste au schéma **22**, sans nouvelle migration. Les données historiques,
les thèmes, les sons et l’accueil de la borne sont conservés.

## Inscriptions

Les participants sont regroupés par statut : confirmés, places proposées,
liste d’attente, puis inscriptions terminées dans un panneau fermé. Les membres
d’une même demande sont associés au sein de chaque groupe. Une personne retirée
d’une demande conserve son propre statut historique ; aucune demande n’est scindée
par le moteur pour cette présentation.

Six indicateurs compacts distinguent capacité, confirmations, places disponibles,
attente, présences et absences. Une réservation confirmée reste verte, même avec
une absence renseignée. La présence conserve son badge séparé et ses commandes
directes. « À confirmer » conserve exactement la valeur de présence inconnue.
La fin d’une animation ne marque jamais automatiquement les inscrits absents.

Les échéances de propositions affichées proviennent des propositions actives,
pas d’un délai codé en dur. Contacts, historique, rattachement, modification des
participants et interventions de l’équipe sont dans **Détails et actions**.
Le parcours normal d’attribution et toutes les vérifications restent identiques.

« Places disponibles » soustrait aussi les places temporairement proposées et
les confirmations dont l'acquittement est encore attendu. Un message contextuel
explique les propositions en cours et leur échéance, sans septième compteur.

## Publication et inscriptions

« Publier cette animation » reste obligatoire pour être visible publiquement.
Deux choix utilisent l’unique ouverture des inscriptions déjà enregistrée :

- Afficher avant l’ouverture (défaut compatible) : « Inscriptions à venir », date,
  heure et commande désactivée ; aucune réservation anticipée n’est acceptée.
- Masquer jusqu’à l’ouverture : invisible avant, visible à partir de cette date.

Après la fin effective, l’animation reste visible **24 heures écoulées**, en gris,
sous les animations à venir, sans réservation. La fin du dernier créneau actif
sert de référence pour une animation à créneaux. Les calculs en UTC préservent
24 heures réelles lors des changements d’heure ; l’affichage utilise le fuseau
de la structure. Après cette limite, l’animation disparaît du catalogue, pas de
l’administration, de l’historique ou des statistiques.

Le canal Normal/Test reste indépendant et accessible aux administrateurs dans
**Options avancées**. La suppression est repliée et conserve confirmation écrite,
CSRF et refus en cas de références ou d’inscriptions actives.

## Réglages

- Affichage : couleur des visiteurs, seuil et décimales réunis avec une sauvegarde
  commune ; couleurs du calendrier indépendantes, plage horaire allégée.
- Données : préavis et suivi conservés, bouton espacé, modèle d’e-mail repliable.
  Les opérations manuelles et les restaurations sont regroupées dans deux panneaux.
- Borne : deux formulaires PIN toujours indépendants dans **Accès sensible** ;
  planning renommé **Clôture automatique des présences** ; remise à zéro repliée.
- Structure : identité, facturation et modules visibles ; WordPress, SMTP et profil
  privé repliables. Une erreur WordPress ouvre son panneau et reste signalée.

Les durées de conservation, destinataires et modèles ne sont pas réinitialisés.
Le journal de préavis ne conserve ni copie de coordonnées ni contenu. Pas de
destinataire familial de secours, pas de renvoi automatique d’un envoi incertain ;
un échec ne bloque pas la purge. Ces règles techniques sont inchangées.

## Machines et anciens dossiers

Une seule case **Active** commande l’offre de nouveaux devis. Décocher conserve
la machine, réactivable. Supprimer retire du catalogue visible ; une machine sans
référence peut être supprimée physiquement, sinon sa référence reste archivée
en interne. Les anciens dossiers gardent leur machine, son nom, son prix et sa
caution. Modifier un dossier avec la même machine réutilise cet instantané.
Choisir expressément une autre machine adopte les tarifs courants de celle-ci.

Sur smartphone, chaque machine présente un résumé repliable : nom, état et
montants. Les champs restent dans un seul formulaire, même repliés, et plusieurs
machines peuvent être modifiées avant la sauvegarde commune. Une saisie invalide
révèle automatiquement sa ligne. Le tableau reste directement éditable sur ordinateur.

## Compatibilité

Le plugin facultatif **Reservations 2.13.0** est réellement modifié pour ces règles
de catalogue. Protocole **4/révision 3** et signatures inchangés ; la capacité
optionnelle `publication_visibility_v1` négocie les nouvelles métadonnées.
WordPress filtre aussi le catalogue côté serveur selon l’heure, y compris un
instantané encore en cache. OpenFabLab revalide chaque demande sous transaction.

Reservations 2.11.0 conserve les échanges existants ; il ne reçoit pas les nouveaux
champs qu’il ne sait pas lire. L’affichage enrichi et le maintien des animations
terminées demandent le nouveau plugin. Mettre à jour sans désinstallation ni
changement de secret. OpenFabLab reste utilisable sans WordPress.

Le seul nouveau choix persistant est une préférence par animation dans
`app_settings` : `animation_hide_before_opening_<id>` (absente = afficher).
Elle est sauvegardée avec SQLite et retirée lors d’une suppression autorisée
de l’animation. Elle ne doit pas être transférée comme profil générique vers les
identifiants d’animations d’une autre installation. Aucune nouvelle table.

Avant mise à jour : sauvegarde complète et contrôle préalable. Les procédures NAS
propres à une structure ne font pas partie de la distribution publique.
