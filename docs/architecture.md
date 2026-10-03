# Architecture

- `app.py` : application Flask, routes, droits, réglages et initialisation/migrations SQLite.
- `animation_slots.py` : génération de créneaux, identifiants stables, validations et synthèses.
- `reservations_sync.py` : échanges HTTPS signés et file d'actions ; aucun serveur entrant dédié au NAS.
- `pin_security.py` : dérivations des PIN et récupération privée à usage unique. Aucun PIN par défaut.
- `billing.py`, `annual_report.py`, `animation_report.py`, `calendar_export.py` : documents, bilans et exports.
- `profile_archive.py` : profil privé de structure, distinct des données métier et des secrets.
- `private_backup.py` : archive du persistant, manifeste, vérification, restauration complète et copie de test neutralisée.
- `runtime_policy.py` : verrou coopératif des requêtes/travailleurs et blocage réseau persistant des instances de test.
- `evolution_schema.py`, `evolution_users.py`, `evolution_routes.py` : registres, migration 14, provenance, inscription et interfaces additionnelles.
- `welcome_mail.py` : SMTP natif optionnel ; credentials séparés de SQLite.
- `resource_booking.py`, `fablab_calendar.py` : ressources, habilitations, transitions et projection du calendrier local.
- `templates/`, `static/`, `badge_templates/` : interface, ressources redistribuables et badge neutre.
- `wordpress/openfablab-reservations/` : plugin indépendant, stockage WordPress, réservation, liste d'attente, e-mails et maintenance Test administrateur.

SQLite stocke les données métier et les réglages non secrets. Clé Flask, dérivations PIN, secret HMAC, webhook et images privées restent dans le dossier persistant de l'installation. Le plugin possède son propre stockage privé WordPress et les options d'e-mails propres au site. Les exports SQLite ne sont donc pas des sauvegardes complètes des credentials.

La synchronisation est initiée par OpenFabLab, pour les deux environnements séparés `test` et `production` (libellé Normal). Les événements et actions sont rejouables selon le protocole existant. Une seule instance serveur doit piloter le même site WordPress. Ne pas donner les mêmes credentials de synchronisation à des instances concurrentes.

OpenFabLab 2.7.0 négocie le protocole 2 et les capabilities `catalog_snapshot_v1` et `custom_categories_v1` : catalogue autoritaire, jamais les réservations WordPress. Les snapshots sont transactionnels et les absents sont masqués sans effacement de l’historique. SQLite utilise le schéma 14, avec migration additive depuis le schéma 13. Voir [les nouveautés 2.7](evolution-2.7.md).

Une animation classique réserve toute sa plage. Une animation en mode créneaux conserve sa fiche globale ; ses créneaux sont des objets internes avec une capacité et une file d'attente indépendantes. Présence, réservation et rattachement à une fiche usager restent trois dimensions distinctes.
