# Réservations publiques — OpenFabLab 2.8.2 stable

OpenFabLab et OpenFabLab Reservations **2.8.2** s’utilisent ensemble : protocole
**4, révision 3**, schéma SQLite **17**. Utiliser les deux composants 2.8.2 ensemble.
WordPress reste facultatif et ne décide jamais des places. Les échanges HTTPS
signés sont exclusivement initiés par OpenFabLab ; aucun port entrant ou
reverse proxy vers le NAS n’est nécessaire. Catalogue : 90 secondes par défaut ;
relève légère des demandes : 15 secondes, configurable de 10 à 60 secondes.

## Avec ou sans compte

Dans Réglages → Structure → Confirmation et liste d’attente, « Compte OpenFabLab
obligatoire pour réserver une animation » est désactivé par défaut, y compris
après migration depuis 2.8.1. Activé, il réserve les nouvelles inscriptions
publiques aux comptes identifiés ; il n’annule pas les inscriptions existantes.
Le catalogue transmet cette règle et le réglage indépendant du téléphone.
La carte choisie reste sélectionnée pendant le parcours. Un rappel compact du
titre, de la date et des horaires accompagne chaque formulaire et récapitulatif.
Le catalogue indique « liste d’attente autorisée » lorsque cette règle est active.
OpenFabLab les vérifie de nouveau au traitement : modifier le navigateur ou
utiliser un ancien catalogue ne permet pas de les contourner.

Sans compte : une seule personne autonome, prénom, nom, date de naissance et
e-mail valide. Téléphone facultatif sauf activation du réglage de la structure.
La date exacte remplace l’année du parcours historique : l’âge minimum et
l’autonomie sont vérifiés à la date de l’animation, sans approximation d’année.
Il s’agit d’informations déclarées, pas d’une preuve d’identité ou d’âge.
Une personne non autonome utilise le parcours familial avec comptes et responsable.
Il n’y a ni accompagnateur artificiel, ni création de fiche, identifiant, PIN ou QR.
L’administration et les exports d’inscriptions signalent « Sans compte ».
Les coordonnées restent privées, dans le dossier d’inscription ; jamais dans
le catalogue ni un annuaire public.

Avec compte : le parcours familial 2.8.1 est conservé. Chaque personne a son
compte, une place par personne, responsable éligible et rattaché pour les
non-autonomes, confirmation ou attente pour tout le groupe ensemble.

## QR Code et caméra

Les badges, QR SVG/PNG et e-mails OpenFabLab utilisent le même texte :
l’identifiant public à **quatre chiffres**, zéros initiaux conservés. Ce n’est
pas une signature ni un mot de passe. Le scanner réutilise le décodeur jsQR
1.4.0 déjà livré, sans CDN. Après le scan, l’e-mail ou le téléphone de la fiche
doit toujours correspondre, exactement comme en saisie manuelle.

La caméra s’ouvre uniquement sur demande, frontale préférée, avec changement
de caméra si disponible. Permission refusée, caméra absente/occupée ou navigateur
incompatible : saisie manuelle immédiatement disponible. HTTPS nécessaire pour
la caméra. Décodage sur l’appareil ; aucune image enregistrée ou envoyée.
Reconnaissance, fermeture, saisie manuelle, changement de formulaire, page quittée
ou cachée : flux arrêté. Une permission accordée après fermeture est également
arrêtée. Un QR laissé devant la caméra ne déclenche pas plusieurs demandes.

## Décisions, reprise et liens

Le relais durable WordPress chiffre les demandes temporaires. La nouvelle action
`guest` transporte une demande d’une personne, pas une attribution de place.
Le moteur commun, sous `BEGIN IMMEDIATE`, contrôle fermeture, âge, capacité et
doublons, puis écrit inscription et reçu durable dans la même transaction.
Identifiant technique stable et empreinte de contenu : retry identique retourne
le reçu, retry modifié est refusé. Une coupure avant le reçu annule toute
l’opération ; après le reçu, la retransmission n’inscrit pas une seconde personne.
Le rapprochement nom/prénom/e-mail normalisé empêche une nouvelle demande active
identique sur la même animation/créneau ; aucune recherche ni création de compte.

FIFO compatible avec la capacité, propositions temporaires, acceptation/refus,
expiration et annulation restent dans OpenFabLab. Les liens personnels reviennent
vers WordPress en mode WordPress. Une personne sans compte peut répondre sans
identification. GET n’applique aucune action métier ; POST explicite, jeton signé,
expiration et protections anti-rejeu sont conservés. Normal et Test restent séparés.

## Migration et compatibilité

Migration transactionnelle **16 → 17** : une colonne nullable
`animation_bookings.guest_birth_date TEXT` et le réglage
`reservation_account_required=0`, inséré seulement s’il n’existe pas.
Tables, comptes, familles, contacts historiques, facturations et reçus restent
intacts. La migration est idempotente ; aucune réinterprétation d’ancien visiteur.
Le réglage est inclus dans le profil de configuration exportable/importable.
Secrets WordPress et SMTP restent dans leurs fichiers privés, hors SQLite et ZIP.

La finition des badges ajoute aussi le réglage d’affichage
`anonymous_visitor_color` (gris bleuté `#72828a` par défaut), sans table ni colonne
supplémentaire. Il est initialisé uniquement s’il manque, y compris sur une base
déjà en schéma 17. Les badges de catégories et de visiteurs utilisent une palette
pastel calculée à partir de la couleur configurée. Le moteur de réservation et
les couleurs du calendrier ne sont pas modifiés par cette finition.

La révision 3 est nécessaire pour l’action sans compte et les règles du catalogue.
L’application refuse un plugin révision 2 avant traitement. Le plugin refuse les
catalogues, relèves et résultats sans révision 3. Pas de moteur de secours.

Avant mise à jour : désactiver temporairement la page publique, laisser finir
les demandes en cours, sauvegarder WordPress et l’ensemble des volumes persistants
OpenFabLab à l’arrêt (PRE 16), conserver l’image 2.8.1. Installer le ZIP plugin
2.8.2 via WordPress → Extensions → Ajouter → Téléverser puis remplacer la version
existante, **sans désinstaller**. Mettre à jour l’application et vérifier schéma 17,
SQLite, Normal/Test et premier catalogue avant réouverture de la page.

Avant toute nouvelle écriture utilisateur : restauration contrôlée de l’image
2.8.1 **et de tous les fichiers PRE 16**, et du plugin/sauvegarde WordPress préservés.
Ne jamais démarrer 2.8.1 sur une base 17. Après utilisation : arrêter proprement,
conserver et sauvegarder l’état POST, diagnostiquer ; aucun rollback automatique
ni conversion destructive de 17 vers 16. Lire aussi [mise à jour](upgrade.md).
