# Architecture

- `app.py` : application Flask, routes, droits, réglages et initialisation/migrations SQLite.
- `animation_slots.py` : génération de créneaux, identifiants stables, validations et synthèses.
- `reservations_sync.py` : échanges HTTPS signés et file d'actions ; aucun serveur entrant dédié au NAS.
- `pin_security.py` : dérivations des PIN et récupération privée à usage unique. Aucun PIN par défaut.
- `billing.py`, `annual_report.py`, `animation_report.py`, `calendar_export.py` : documents, bilans et exports.
- `profile_archive.py` : profil privé de structure, distinct des données métier et des secrets.
- `templates/`, `static/`, `badge_templates/` : interface, ressources redistribuables et badge neutre.
- `wordpress/openfablab-reservations/` : plugin indépendant, stockage WordPress, réservation, liste d'attente, e-mails et maintenance Test administrateur.

SQLite stocke les données métier et les réglages non secrets. Clé Flask, dérivations PIN, secret HMAC, webhook et images privées restent dans le dossier persistant de l'installation. Le plugin possède son propre stockage privé WordPress et les options d'e-mails propres au site. Les exports SQLite ne sont donc pas des sauvegardes complètes des credentials.

La synchronisation est initiée par OpenFabLab, pour les deux environnements séparés `test` et `production` (libellé Normal). Les événements et actions sont rejouables selon le protocole existant. Une seule instance serveur doit piloter le même site WordPress. Ne pas donner les mêmes credentials de synchronisation à des instances concurrentes.

Une animation classique réserve toute sa plage. Une animation en mode créneaux conserve sa fiche globale ; ses créneaux sont des objets internes avec une capacité et une file d'attente indépendantes. Présence, réservation et rattachement à une fiche usager restent trois dimensions distinctes.
