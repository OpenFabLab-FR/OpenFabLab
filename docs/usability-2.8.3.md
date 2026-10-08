# OpenFabLab 2.8.3 : personnalisation et lisibilité

La version stable 2.8.3 succède à la 2.8.2 ; le plugin WordPress 2.8.2 reste compatible, inchangé, au protocole 4 / révision 3. OpenFabLab reste l'unique moteur des réservations, familles, capacités et listes d'attente. Aucun accès entrant au serveur n'est nécessaire.

## Identifiants

Réglages → Usagers → Inscription et bienvenue propose trois modes pour l'accès public :

- Automatique discret : fonctionnement des installations existantes.
- Automatique visible : proposition non modifiable avant validation, recommandé et choisi pour une installation neuve.
- Personnalisable : saisie de quatre chiffres, zéros initiaux conservés.

Une proposition ne réserve pas le numéro. L'attribution définitive est transactionnelle ; si un autre compte l'a obtenu entre-temps, une nouvelle proposition est affichée et doit être validée. Il n'existe pas de recherche publique des comptes par disponibilité. La protection CSRF, la durée limitée du formulaire et la limitation des tentatives sont conservées.

Administrateurs et modérateurs peuvent choisir un numéro à la création, quel que soit ce mode. La modification d'une fiche reste réservée à l'administrateur selon les droits existants. L'identifiant technique permanent ne change pas : familles, historique et réservations restent reliés au même compte. Après changement du code public, rééditer le badge et le QR Code ; l'ancien QR à quatre chiffres ne doit plus être utilisé. Le code public n'est pas un secret d'authentification ; le parcours WordPress continue à vérifier une coordonnée après saisie ou scan.

## Structure de rattachement

Dans une fiche usager, l'équipe peut choisir une structure parmi les clients ayant un nom de structure, ou saisir un nom libre. Aucun client n'est créé automatiquement. Le nom est conservé si la fiche client est ensuite supprimée ; le lien devient vide. Effacer le choix et le nom retire le rattachement. Cette information n'accorde ni abonnement, ni accès, ni facturation automatique. Elle n'est pas publiée dans l'annuaire public ou les réservations WordPress.

## Fréquentation, couleurs et calendrier

Réglages → Affichage permet de choisir un seuil de référence de 1 à 10 000 personnes, dix par défaut. La jauge s'adapte sans bloquer une arrivée. Les couleurs de catégories et du visiteur anonyme restent pastel, calculées depuis leur couleur configurée. Les badges ne coupent plus les mots ; un intitulé tronqué s'ouvre au toucher ou au clavier dans une petite fenêtre.

La fenêtre d'un créneau réservable présente client, référence, statut et description du dossier lorsqu'il existe et que l'administrateur est autorisé à le consulter. Ces données ne sont pas envoyées au navigateur d'un modérateur ni d'un visiteur. Une description longue se développe explicitement.

## Notifications

Le fuseau explicite existant de Réglages → Structure (identifiant IANA, par exemple Europe/Paris) est réutilisé. Les dates internes restent UTC ; la date de création Discord est présentée en français, heure locale, sans secondes. Les coordonnées géographiques ne sont pas utilisées pour deviner un fuseau. Les choix de confidentialité sont inchangés.

## Migration et restauration

Schéma SQLite 18 : ajout nullable de `users.affiliation_client_id`, référence à `billing_clients.id` avec `ON DELETE SET NULL`, et ajout de `users.affiliation_name` (texte vide par défaut). Les réglages `public_id_assignment_mode` et `attendance_reference` sont ajoutés sans écraser les valeurs existantes et inclus dans le profil de configuration. Aucune table métier n'est supprimée. La migration est transactionnelle, répétable, avec contrôle d'intégrité et de clés étrangères et sauvegarde PRE17.

Avant mise à jour, sauvegarder complètement les données persistantes, fichiers privés, configuration, authentification et runtime. Ne jamais démarrer 2.8.2 sur une base passée au schéma 18. Avant toute remise en service publique, une restauration contrôlée de la PRE17 avec le runtime 2.8.2 est possible. Après remise en service ou écriture potentielle, arrêter, sauvegarder l'état et attendre une décision humaine : aucun retour automatique vers une ancienne base.

Voir les [instructions générales de mise à jour](upgrade.md). Le scanner avec caméra physique reste à vérifier sur le matériel réel ; cette version ne change pas son code.
