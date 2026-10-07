# Architecture

## Version stable 2.8.2

Protocole 4 / révision 3, SQLite 17 : [architecture et migration 2.8.2](reservations-2.8.2.md).
L’action `guest` utilise le même moteur, verrou de capacité, journal de reçus et
liste d’attente que les comptes. Aucun compte synthétique ni moteur WordPress.
La colonne `guest_birth_date` est un instantané d’inscription privé. Le QR
historique quatre chiffres remplace seulement la saisie, pas la vérification.
Le moteur décrit ci-dessous conserve l’architecture sortante introduite en 2.8.1 ; les évolutions de schéma sont distinguées par version.

## Moteur commun 2.8.2

`family_model.py` : naissance, seuils, rattachements privés et migrations additives jusqu’au schéma 17. `family_reservations.py` : moteur unique transactionnel, une personne réelle par ligne/place, demande idempotente et groupe entier confirmé/attente. `family_routes.py` et `family_reservation_routes.py` : interface progressive et routes historiques conservées. `outbound_actions.py` et `outbound_sync.py` : journal atomique et échanges HTTPS initiés seulement par OpenFabLab vers WordPress, protocole 4. Aucun annuaire global ni seconde autorité de capacité ; aucune adresse entrante du NAS requise. Voir [le relais 2.8.1](outbound-2.8.1.md). Les anciennes données restent lisibles.

`calendar_visibility` ne touche pas aux données métier. Les backups privés incluent relations/naissance, hors profils publics. Voir [conception 2.8](families-2.8.md). La section 2.7 ci-dessous est historique ; elle ne décrit pas le relais actuel.

`family_waitlist.py` ajoute au même moteur la sélection FIFO compatible, les
propositions temporaires, leur historique, les liens opaques de réponse et le
journal SMTP durable. Les états et occupations changent sous `BEGIN IMMEDIATE` ;
les envois réseau se font après commit et sous claim exclusif. Les propositions
consomment des places au même titre que les confirmations. Un traitement local
indépendant de WordPress expire les offres et reprend les e-mails ; les instances
privées et les environnements Test bloquent les envois réels.

- `app.py` : application Flask, routes, droits, réglages et initialisation/migrations SQLite.
- `animation_slots.py` : génération de créneaux, identifiants stables, validations et synthèses.
- `reservations_sync.py` : contrôles de liaison/capabilities et déclenchement de la relève sortante sur le schéma 17 ; aucun ancien consommateur d'événements WordPress. Le moteur reçoit des actions, jamais des décisions de capacité WordPress. Les anciennes données OpenFabLab restent lisibles indépendamment de ce transport.
- `pin_security.py` : dérivations des PIN et récupération privée à usage unique. Aucun PIN par défaut.
- `billing.py`, `annual_report.py`, `animation_report.py`, `calendar_export.py` : documents, bilans et exports.
- `profile_archive.py` : profil privé de structure, distinct des données métier et des secrets.
- `private_backup.py` : archive du persistant, manifeste, vérification, restauration complète et copie de test neutralisée.
- `runtime_policy.py` : verrou coopératif des requêtes/travailleurs et blocage réseau persistant des instances de test.
- `evolution_schema.py`, `evolution_users.py`, `evolution_routes.py` : registres, migration 14, provenance, inscription et interfaces additionnelles.
- `welcome_mail.py` : SMTP natif optionnel ; credentials séparés de SQLite.
- `resource_booking.py`, `fablab_calendar.py` : ressources, habilitations, transitions et projection du calendrier local.
- `templates/`, `static/`, `badge_templates/` : interface, ressources redistribuables et badge neutre.
- `wordpress/openfablab-reservations/` : relais public facultatif vers OpenFabLab ; catalogue et file durable uniquement ; aucune classe de capacité, annuaire, e-mail ni tâche de décision WordPress.

SQLite stocke les données métier et les réglages non secrets. Clé Flask, dérivations PIN, secret HMAC, webhook et images privées restent dans le dossier persistant de l'installation. Le plugin possède son stockage de relais et sa configuration de connexion privée dans WordPress ; il n'envoie pas les e-mails métier. Les exports SQLite ne sont donc pas des sauvegardes complètes des credentials.

### Ajouts SQLite du schéma 16

Aucune colonne métier existante n'est supprimée ou réinterprétée. Deux tables sont ajoutées transactionnellement :

- `wordpress_action_receipts` : `environment`, `action_id`, `payload_hash`, `action_type`, `result_json`, `created_at`, `private_until`, `acknowledged_at`. Clé primaire composée de l'environnement et de l'action ; le reçu et l'effet métier partagent le même commit. Les résultats privés ont un délai d'expurgation.
- `wordpress_relay_state` : `environment` (clé), `catalogue_at`, `catalogue_count`, `polled_at`, `results_at`, `last_error`, `pending`, `processing`, `failed`, `retrying`. Un état diagnostic par environnement, jamais une autorité de capacité.

Les réglages manquants `reservation_action_interval_seconds=15` et `reservation_link_mode=auto` sont initialisés sans remplacer les valeurs existantes. Les indicateurs `reservation_outbound_ready_production` et `reservation_outbound_ready_test` attestent séparément la liaison correspondante ; une réussite Test ne valide pas les liens Normal. La version du schéma passe à 16 dans la transaction d'initialisation. Les réglages, tables et fichiers privés antérieurs restent conservés. Une seconde initialisation est idempotente.

WordPress ajoute uniquement `relay_catalogues` (catalogue public et date) et `relay_actions` (dépôt, session opaque, bail, résultat chiffré, acquittement et expiration), dans le préfixe de tables configuré. La table de nonces anti-rejeu est conservée. Les cinq anciennes tables métier vides sont retirées sous verrou ; si une table contient encore des lignes, elles sont toutes conservées mais ne sont jamais lues par le nouveau relais. Les anciennes classes et routes sont supprimées du runtime ; leur couverture reste exercée séparément dans les fixtures de développement, hors ZIP.

### Référence historique 2.7 et versions précédentes

Les paragraphes suivants décrivent le protocole sortant antérieur, pas l'autorité des nouvelles réservations 2.8. La synchronisation était initiée par OpenFabLab, pour les environnements séparés `test` et `production` (Normal). Les événements/actions étaient rejouables selon ce protocole. Ne pas donner les mêmes credentials à des instances concurrentes.

OpenFabLab 2.7.0 négocie le protocole 2 et les capabilities `catalog_snapshot_v1` et `custom_categories_v1` : catalogue autoritaire, jamais les réservations WordPress. Les snapshots sont transactionnels et les absents sont masqués sans effacement de l’historique. SQLite utilise le schéma 14, avec migration additive depuis le schéma 13. Voir [les nouveautés 2.7](evolution-2.7.md).

Une animation classique réserve toute sa plage. Une animation en mode créneaux conserve sa fiche globale ; ses créneaux sont des objets internes avec une capacité et une file d'attente indépendantes. Présence, réservation et rattachement à une fiche usager restent trois dimensions distinctes.
