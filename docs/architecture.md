# Architecture

## Moteur commun 2.8.0

`family_model.py` : naissance, seuils, rattachements privés et migration 15. `family_reservations.py` : moteur unique transactionnel, une personne réelle par ligne/place, demande idempotente et groupe entier confirmé/attente. `family_routes.py` et `family_reservation_routes.py` : interface progressive et API privée signée. WordPress 2.8 est un relais HTTPS vers cette API, sans copie d'annuaire ni seconde autorité de capacité. Le protocole 2 historique est refusé avant export/rejeu sur le schéma 15. Les anciennes données restent lisibles.

`calendar_visibility` ne touche pas aux données métier. Les backups privés incluent relations/naissance, hors profils publics. Voir [conception 2.8](families-2.8.md). La description du protocole sortant ci-dessous est historique.

`family_waitlist.py` ajoute au même moteur la sélection FIFO compatible, les
propositions temporaires, leur historique, les liens opaques de réponse et le
journal SMTP durable. Les états et occupations changent sous `BEGIN IMMEDIATE` ;
les envois réseau se font après commit et sous claim exclusif. Les propositions
consomment des places au même titre que les confirmations. Un traitement local
indépendant de WordPress expire les offres et reprend les e-mails ; les instances
privées et les environnements Test bloquent les envois réels.

- `app.py` : application Flask, routes, droits, réglages et initialisation/migrations SQLite.
- `animation_slots.py` : génération de créneaux, identifiants stables, validations et synthèses.
- `reservations_sync.py` : contrôles de liaison/capabilities et compatibilité historique. Les nouvelles réservations 2.8 viennent par l'API HTTPS familiale, pas par l'import d'une seconde autorité de capacité.
- `pin_security.py` : dérivations des PIN et récupération privée à usage unique. Aucun PIN par défaut.
- `billing.py`, `annual_report.py`, `animation_report.py`, `calendar_export.py` : documents, bilans et exports.
- `profile_archive.py` : profil privé de structure, distinct des données métier et des secrets.
- `private_backup.py` : archive du persistant, manifeste, vérification, restauration complète et copie de test neutralisée.
- `runtime_policy.py` : verrou coopératif des requêtes/travailleurs et blocage réseau persistant des instances de test.
- `evolution_schema.py`, `evolution_users.py`, `evolution_routes.py` : registres, migration 14, provenance, inscription et interfaces additionnelles.
- `welcome_mail.py` : SMTP natif optionnel ; credentials séparés de SQLite.
- `resource_booking.py`, `fablab_calendar.py` : ressources, habilitations, transitions et projection du calendrier local.
- `templates/`, `static/`, `badge_templates/` : interface, ressources redistribuables et badge neutre.
- `wordpress/openfablab-reservations/` : relais public facultatif vers OpenFabLab ; ancien stockage, e-mails et maintenance conservés pour l'historique et le nettoyage protégé.

SQLite stocke les données métier et les réglages non secrets. Clé Flask, dérivations PIN, secret HMAC, webhook et images privées restent dans le dossier persistant de l'installation. Le plugin possède son propre stockage privé WordPress et les options d'e-mails propres au site. Les exports SQLite ne sont donc pas des sauvegardes complètes des credentials.

### Référence historique 2.7 et versions précédentes

Les paragraphes suivants décrivent le protocole sortant antérieur, pas l'autorité des nouvelles réservations 2.8. La synchronisation était initiée par OpenFabLab, pour les environnements séparés `test` et `production` (Normal). Les événements/actions étaient rejouables selon ce protocole. Ne pas donner les mêmes credentials à des instances concurrentes.

OpenFabLab 2.7.0 négocie le protocole 2 et les capabilities `catalog_snapshot_v1` et `custom_categories_v1` : catalogue autoritaire, jamais les réservations WordPress. Les snapshots sont transactionnels et les absents sont masqués sans effacement de l’historique. SQLite utilise le schéma 14, avec migration additive depuis le schéma 13. Voir [les nouveautés 2.7](evolution-2.7.md).

Une animation classique réserve toute sa plage. Une animation en mode créneaux conserve sa fiche globale ; ses créneaux sont des objets internes avec une capacité et une file d'attente indépendantes. Présence, réservation et rattachement à une fiche usager restent trois dimensions distinctes.
