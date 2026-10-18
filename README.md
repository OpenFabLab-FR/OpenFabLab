<p align="center"><img src="static/brand/OpenFabLab-logo-horizontal.svg" width="420" alt="OpenFabLab"></p>

# OpenFabLab 2.10.1

**Version stable · Application et plugin facultatif Reservations 2.10.1 · SQLite 21 · Licence MIT**

Cette version améliore la stable 2.10.0 : créneaux WordPress explicites,
notifications Discord par créneau, sons Summer/Steampunk et compte à rebours,
actions du calendrier plus compactes. [Guide et compatibilité](docs/corrections-2.10.1.md).
Protocole 4/révision 3 inchangé ; pas de migration depuis 2.10.0.
OpenFabLab reste gratuit, libre, modulaire et utilisable sans WordPress.

[Release et empreintes SHA-256](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.10.1) ·
[Application 2.10.1](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.10.1/OpenFabLab-2.10.1.zip) ·
[Plugin WordPress 2.10.1 facultatif](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.10.1/openfablab-reservations-2.10.1.zip)

[Installation](docs/installation.md) · [Mise à jour](docs/upgrade.md) ·
[Linux](docs/installation-linux.md) · [Raspberry Pi](docs/installation-raspberry-pi.md) ·
[Windows](docs/installation-windows.md) · [Synology](docs/installation-synology.md)

Depuis 2.10.0 : schéma 21 conservé, préférences et données conservées, aucune
migration supplémentaire. Mettre à jour l’application avant le plugin, sans
désinstaller l’extension ni changer les secrets. Le protocole reste 4/révision 3,
indépendamment des numéros publics ; OpenFabLab reste seul moteur de réservation.
Les abonnements et crédits restent facultatifs et désactivés par défaut.

Les ZIP approuvés sont distribués sans reconstruction. Leurs guides figés peuvent
conserver des mentions de préparation : la documentation de ce tag est la référence
stable à jour. Aucun paquet de déploiement privé n’est distribué publiquement.

## Référence historique : OpenFabLab 2.10.0

**Version stable · SQLite schéma 21 · OpenFabLab Reservations 2.9.0 facultatif · Licence MIT**

OpenFabLab aide les FabLabs à gérer l’accueil, les usagers, les activités,
les réservations et la facturation. Cette version ajoute quatre outils :

- **Abonnements et crédits**, module facultatif et désactivé par défaut :
  cotisations individuelles ou familiales, pass, crédits de passages, heures
  et demi-journées, recharges et historique des mouvements.
- **Alertes Discord de synchronisation temporisées** : dix minutes par défaut
  pour éviter les notifications de microcoupure, rétablissement facultatif.
- **Notes internes du calendrier**, par occurrence, gérées par les administrateurs
  et modérateurs autorisés, sans publication ni action métier automatique.
- **Retour sonore de la borne** : classique, Halloween, Noël ou thème automatique ;
  activé à 50 % pour les préférences absentes, désactivable à tout moment.

Le module Abonnements n’impose aucun paiement ni abonnement pour utiliser le
logiciel. Aucun paiement bancaire en ligne, prélèvement ou renouvellement payant
automatique ; aucune intégration Stripe ou PayPal. Les choix déjà enregistrés
restent conservés, y compris les sons désactivés et les volumes personnalisés.

### Télécharger et installer

[Release et empreintes SHA-256](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.10.0) ·
[Application 2.10.0](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.10.0/OpenFabLab-2.10.0.zip) ·
[Plugin WordPress 2.9.0 facultatif](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.10.0/openfablab-reservations-2.9.0.zip)

[Installation](docs/installation.md) · [Mise à jour depuis 2.9.0](docs/upgrade.md) ·
[Guide des nouveautés et exemples](docs/evolution-2.10.0.md) ·
[Configuration](docs/configuration.md) · [WordPress](docs/wordpress.md)

Depuis 2.9.0 : migration additive SQLite **20 → 21**, avec sauvegarde complète
et conservation des données/réglages. Ne jamais ouvrir une base 21 avec 2.9.0.
Le plugin **OpenFabLab Reservations 2.9.0** est inchangé : aucune mise à jour
nécessaire s’il est déjà installé. OpenFabLab fonctionne sans WordPress ; lorsqu’il
est utilisé, le relais reste HTTPS exclusivement sortant, protocole 4/révision 3.
OpenFabLab reste seul responsable des places et des listes d’attente.

L’archive validée est conservée sans reconstruction : certaines mentions de
préparation restent dans ses guides figés. La documentation de ce tag fait référence.

## Référence historique : 2.9.0

**Version stable · SQLite schéma 20 · OpenFabLab Reservations 2.9.0 facultatif · Protocole 4, révision 3**

Plafond des listes d’attente, cartes WordPress mieux organisées, analyses privées
de fréquentation, catégories facultatives de clients et préavis SMTP facultatif
avant effacement des coordonnées. Voir le [guide 2.9.0](docs/evolution-2.9.0.md).
La migration additive 19 → 20 conserve les données et réglages existants.
Le plugin 2.8.5 reste compatible avec ses anciens affichages ; 2.9.0 annonce
explicitement les nouveaux états. OpenFabLab reste seul moteur et fonctionne
sans WordPress. Aucune ouverture entrante vers le NAS n’est nécessaire.

Cette version intègre toutes les évolutions 2.9.0 et les cinq finitions validées :
persistance de l’option Discord « Liste d’attente complète », présentation de
Fréquentation → Usagers, formulaire du préavis sous Conservation automatique,
filtres de l’annuaire des clients et affichage conditionnel du plafond personnalisé.
Les analyses restent en lecture seule, sans modifier les calculs ni déduire une
présence d’une réservation. Le module facultatif « Abonnements et crédits »,
absent de cette version 2.9.0, est disponible depuis la 2.10.0.

Télécharger l’[application OpenFabLab 2.9.0](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.9.0/OpenFabLab-2.9.0.zip),
le [plugin facultatif Reservations 2.9.0](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.9.0/openfablab-reservations-2.9.0.zip)
et les [empreintes SHA-256](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.9.0/SHA256SUMS)
depuis la [release stable 2.9.0](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.9.0).
Le plugin 2.9.0 est nécessaire aux nouveaux compteurs et états de liste d’attente,
négociés par `waitlist_limits_v1`. JavaScript est nécessaire au parcours public
WordPress et HTTPS au scanner caméra. Aucun port entrant vers OpenFabLab n’est requis.
Lire [l’installation](docs/installation.md) et [la mise à jour](docs/upgrade.md).

Les ZIP approuvés sont publiés sans reconstruction : leurs guides embarqués peuvent
conserver des mentions de préparation. **La documentation du tag `v2.9.0` est la
référence stable à jour.** Les anciennes releases et leurs archives sont conservées.

### Fonctions historiques conservées

OpenFabLab **2.8.6** consolide les améliorations développées depuis la dernière version publique 2.8.4. Elle réunit [les apports de la 2.8.5](docs/corrections-2.8.5.md), utilisée localement mais non publiée séparément, et [les corrections propres à la 2.8.6](docs/corrections-2.8.6.md) : recherches de participants initialement vides, sélections conservées et notifications Discord enrichies avec champs choisis explicitement. Les renseignements nominatifs sont désactivés par défaut ; aucun contact ni lien personnel n'est envoyé. Il s'agit d'une distribution complète, pas d'un correctif à appliquer sur la 2.8.4.

Toutes les fonctions de la 2.8.5 sont conservées : réservations transactionnelles, familles, QR, comptes facultatifs, liste d’attente, reprise et relais exclusivement sortant. Les installations existantes conservent leurs cadences, configurations et préférences. La 2.8.6 conservait le schéma 19 ; la 2.9.0 passe au schéma 20.

Le plugin **2.8.5**, distribué avec la release 2.8.6, a amélioré la page personnelle et le lien d'information après négociation de capacité. Ces fonctions sont conservées en 2.9.0. Pour l'installation : [Linux](docs/installation-linux.md), [Raspberry Pi](docs/installation-raspberry-pi.md), [Windows](docs/installation-windows.md), [Synology générique](docs/installation-synology.md), [opérations communes](docs/installation-common.md) et [compatibilité et limites](docs/platform-compatibility.md).

Les corrections de la **2.8.4** restent conservées : formulaires simplifiés, confidentialité du responsable familial après abandon d'une inscription, réservations locales plus lisibles et ajustements du calendrier, des réglages et du répertoire des usagers. Voir le [guide historique](docs/corrections-2.8.4.md).

Les fonctions de personnalisation introduites en 2.8.3 sont conservées : badges pastel, modes d'attribution des identifiants, rattachement informatif à une structure, jauge de fréquentation, dates Discord et détails du calendrier. Voir le [guide 2.8.3](docs/usability-2.8.3.md). Le moteur de réservation reste celui de la 2.8.5 ; le plugin WordPress 2.8.5 est inchangé par la 2.8.6.

La [release historique 2.8.6](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.8.6) et ses téléchargements restent accessibles. Pour la version actuelle, utiliser les liens 2.10.1 en tête de ce document. Lire les [règles familiales](docs/families-2.8.md) et les [instructions de mise à jour](docs/upgrade.md) avant de changer une installation existante.

OpenFabLab est un logiciel libre de gestion de FabLab créé par **William Aumand**, distribué sous licence MIT. Il réunit la fréquentation du lieu, les usagers et les activités dans une application web installée sur le serveur de votre structure.

Site du projet : [openfablab.fr](https://openfablab.fr).

Les personnes disposant d'un compte peuvent être rattachées à des responsables. Une personne sélectionnée correspond à une place : la borne, l'administration et WordPress utilisent le même moteur OpenFabLab, avec groupes familiaux indivisibles, liste d'attente et propositions automatiques par e-mail. Une réservation sans compte reste une inscription à une animation, pas un compte permanent. Une installation neuve reste générique ; chaque structure active et configure ses modules. Voir le [changelog](CHANGELOG.md) et la [personnalisation](docs/branding.md).

La navigation Réglages comporte sept onglets courts et des formulaires compacts. Le calendrier Semaine/Mois propose une plage visible configurable, 09:00–19:00 par défaut, sans double défilement vertical. Les modules Ressources et Formations restent facultatifs. Une installation neuve propose Usager, Bénévole et Manager ; une migration conserve les catégories historiques, y compris celles sans usager actuel. Les accès facultatifs **Créer un compte** et **Réserver une animation** figurent sur la page **Gestion**, sans exiger de PIN pour ces parcours publics. L'espace **Administration / Modération** reste protégé.

## Fonctionnalités

- Suivi des arrivées/départs, visiteurs anonymes, usagers, identifiants QR et badges.
- Statistiques de fréquentation et exports, bilans d'activité.
- Animations, inscriptions, présence distincte de la réservation, listes d'attente, CSV et PDF.
- Réservation d'animations depuis la borne, facultative ; comptes liés, responsables et une place par personne, confirmation ou attente pour le groupe entier par le moteur local.
- Seuils d'autonomie et de responsabilité et coordonnées requises configurables ; comptes indépendants et rattachements conservés dans le temps.
- Réservation pour toute une animation ou par créneaux internes, capacité et attente par créneau.
- Locations, catalogue de machines, clients et dossiers de facturation.
- Identité visuelle configurable, modules activables, météo et notifications Discord facultatives.
- Sauvegarde/restauration SQLite, [sauvegarde complète privée et copie de test isolée](docs/private-backup.md), profil privé de configuration.
- Catégories d’usagers configurables : nom, couleur, ordre, active/masquée et catégorie active par défaut ; provenance et historique de création des fiches, indépendants des droits.
- Inscription autonome facultative sur la borne, sans session privilégiée ; e-mail de bienvenue avec identifiant et QR Code via SMTP natif facultatif.
- Notification Discord de création d’usager désactivée par défaut, limitée aux champs choisis.
- Calendrier Semaine/Mois : OpenLab et fréquentation, activités, réservations, locations et formations.
- Machines et autres ressources réservables, catégories de ressources, gratuité ou tarif, confirmation automatique ou validation par l’équipe et lien avec la facturation existante.
- Formations et habilitations permanentes ou expirables, révocation et historique ; une ressource peut exiger une habilitation valide, avec dérogation Administrateur motivée et auditée.
- Plugin WordPress 2.9.0 optionnel : catalogue public, disponibilités négociées, parcours familial et file durable Normal/Test séparés, avec échanges HTTPS initiés uniquement par OpenFabLab ; aucun moteur de réservation ni ancien expéditeur d'e-mails WordPress. L'historique métier reste conservé dans OpenFabLab.

Les captures ne sont pas distribuées : aucun écran comportant des données personnelles n'est nécessaire à l'installation.

## Architecture

Une application **Python/Flask + SQLite** sert l'interface locale. Docker utilise Gunicorn. Le plugin PHP s'installe séparément sur WordPress. **OpenFabLab est l'unique autorité de capacité** : il initie les échanges HTTPS signés vers WordPress. WordPress affiche le catalogue et conserve temporairement des demandes, jamais des places attribuées. Les nouvelles installations proposent 60 secondes pour le catalogue et 10 secondes pour les actions (réglage de 10 à 60 secondes) ; les cadences déjà enregistrées, notamment 90/15 secondes, sont conservées. WordPress n'appelle pas le serveur OpenFabLab. Il reste facultatif pour les réservations locales.

Voir [l'architecture](docs/architecture.md) et les [recommandations de sécurité](SECURITY.md). Les PIN à quatre chiffres ne suffisent pas à protéger une administration exposée sur Internet.

## Installation rapide

Prérequis : Python **3.10 ou ultérieur**, environnement virtuel et accès au navigateur. Python 3.12 est utilisé dans l'image Docker. Depuis la source ou le ZIP applicatif :

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Ouvrir `http://localhost:5001`. Le serveur de développement est réservé aux essais locaux. Sur macOS, `AppStart.command` propose un lanceur équivalent. Le guide [installation](docs/installation.md) décrit les chemins persistants et la première initialisation.

## Installation Docker

Avec Docker Engine et Compose v2 :

```sh
docker compose config --quiet
docker compose build application
docker compose up -d application
```

Ouvrir `http://localhost:5080/stat/` ; santé : `/stat/sante`. Le projet/conteneur s'appelle `openfablab`, l'image générique `openfablab:v2.10.0`. Une installation existante conserve son Compose et peut garder son ancien alias d'image : vérifier la version réelle dans l'interface. Données : `./data:/data`, base `/data/openfablab.db`. Sauvegardes : `./backups:/nas-backups`, sous-dossier `OpenFabLab`. `.env.example` documente uniquement la racine de sauvegarde facultative. Employer des volumes et ports d'essai distincts ; ne pas exécuter ces commandes dans une installation de production. Protéger l'accès réseau ; aucun reverse proxy propre à une structure n'est livré.

## Première initialisation

Une instance neuve n'a **aucun usager, PIN, tarif, machine, compte bancaire, webhook ou secret WordPress prédéfini**. Définir le PIN Administrateur depuis l'accès local autorisé, puis configurer la structure et, si nécessaire, le PIN Modérateur. Dans Docker, un administrateur du serveur peut créer un lien privé à usage unique :

```sh
docker compose exec application python -m openfablab reset-admin-pin --database /data/openfablab.db
```

Ne partager ni enregistrer ce lien dans un document public. Compléter identité, fuseau, horaires, protection des données, tarifs et machines selon votre organisation. Voir [configuration](docs/configuration.md).

## Modules

Fréquentation, usagers, activités, réservations publiques, créneaux réservables, locations, facturation, météo et Discord sont configurables dans **Réglages → Structure et modules**. Désactiver les modules inutiles. Une animation à créneaux internes reste une seule animation ; elle ne devient pas une collection d'activités séparées.

## Réservations depuis la borne, WordPress et créneaux

En **2.9.0**, le moteur commun reste OpenFabLab : une personne sélectionnée = une place, responsables compris s'ils participent. Les groupes sont confirmés ou mis en attente ensemble, sans confirmation partielle. La borne fonctionne sans Internet si le serveur local reste accessible. Activer **Réglages → Usagers → Autoriser la réservation d’animations depuis la borne**. L'accès public figure sur la page Gestion, sans PIN.

WordPress reste **facultatif**. **OpenFabLab Reservations 2.9.0** utilise les mêmes comptes liés et règles, avec compte identifié par ID ou QR/contact connu, ou sans compte pour une personne autonome si la structure l’autorise. Le compte est facultatif par défaut ; la réservation sans compte demande coordonnées et date de naissance et ne crée aucune fiche usager. OpenFabLab relève les demandes par HTTPS sortant vers le site ; aucune URL NAS n'est nécessaire dans le plugin. Le protocole 4 ne se rabat pas sur les moteurs précédents. Le moteur historique WordPress est supprimé. Les anciennes tables métier vides sont retirées sous verrou ; des tables encore remplies restent intactes et inutilisées, sans toucher aux données OpenFabLab. La liste d’attente propose automatiquement les places au plus ancien groupe compatible ; e-mail natif, blocage temporaire, réponse et expiration sont gérés par OpenFabLab. Un e-mail valide est obligatoire ; le téléphone peut être exigé par la structure. Voir [familles et compatibilité](docs/families-2.8.md).

```text
[openfablab_reservations environment="test"]
[openfablab_reservations environment="production"]
```

Normal correspond à la valeur technique `production`. Test reste séparé. Les pages sont choisies par chaque structure ; aucun chemin n'est imposé. Les demandes publiques attendent la relève sortante, puis sont traitées uniquement dans OpenFabLab. Le moteur historique WordPress n'est jamais utilisé pour les nouvelles places. La compatibilité de l'ancien couple application 2.7.1/plugin 2.7.0 reste documentée dans [les corrections 2.7.1](docs/corrections-2.7.1.md).

Exemple : **Découverte casque VR**, 10:00–12:00, durée 20 minutes, battement 10 minutes, une place par créneau : **10:00–10:20, 10:30–10:50, 11:00–11:20, 11:30–11:50**. Les créneaux ont des capacités et files d'attente indépendantes. [Guide WordPress](docs/wordpress.md), [créneaux](docs/animation-slots.md), [modèles d'e-mails](docs/email-templates.md).

## Sauvegarde et restauration

Dans **Réglages → Données**, choisir le niveau adapté :

1. **Sauvegarde SQLite** : données métier ; les fichiers privés externes ne sont pas inclus.
2. **Sauvegarde complète privée** : base, dérivations PIN, clé persistante, réglages et ressources de l’installation, avec manifeste et empreintes.
3. **Copie privée pour test/diagnostic** : données et identité conservées, intégrations externes neutralisées et connexions externes bloquées.

Ces fichiers peuvent contenir des données personnelles et des secrets : ils ne sont pas chiffrés et **ne doivent jamais être publiés**. Conserver aussi la configuration de déploiement et tester la restauration sur une instance isolée. Un profil `.openfablab-profile.zip` ne remplace pas une sauvegarde d’installation. [Procédure complète](docs/backup-restore.md), [format privé et restauration](docs/private-backup.md).

## Mise à jour

**2.8.6 → 2.9.0 : schéma SQLite 19 → 20**, migration additive et transactionnelle.
Préserver les données, réglages, fichiers privés et secrets ; conserver une
sauvegarde complète **PRE19** et le runtime 2.8.6, préparer le nouveau runtime
avant l’arrêt, puis sauvegarder à froid les dernières écritures. Contrôler
version, intégrité SQLite, clés étrangères, volumes et santé ; conserver une POST20.
**Installation déjà en 2.9.0 / schéma 20 : aucune nouvelle migration**, sauvegarde
PRE20 et runtime 2.9.0 correspondant. Après toute tentative de reprise publique,
aucune restauration destructive automatique. Ne jamais ouvrir une base 20 avec
2.8.6. Voir la [procédure détaillée](docs/upgrade.md).

### Référence historique des schémas

**2.8.3 → 2.8.4 : schéma SQLite 18 inchangé**, aucune migration. Conserver une sauvegarde complète **PRE18** et le runtime exact 2.8.3 ; préparer puis remplacer uniquement l'application en préservant données, configuration et secrets. Vérifier intégrité/FK, données, réglages et santé, puis sauvegarder POST18. Le plugin 2.8.2 reste inchangé. Après toute tentative de démarrage public, ne pas restaurer automatiquement une ancienne base : préserver l'état et décider humainement. [Procédure de mise à jour](docs/upgrade.md).

**2.8.2 → 2.8.3 : schéma SQLite 17 → 18**, migration additive et transactionnelle : deux champs de rattachement et deux réglages, sans suppression des données existantes. Conserver une **PRE17 complète** et le runtime exact 2.8.2 ; remplacer uniquement l'application. Le plugin 2.8.2 est inchangé, aucun secret à régénérer. Vérifier intégrité/FK, données et réglages avant réouverture, puis sauvegarder POST18. Ne jamais démarrer 2.8.2 sur une base 18 ; après remise en service, préserver l'état et décider humainement, sans rollback automatique destructif. [Procédure de mise à jour](docs/upgrade.md).

**2.8.1 → 2.8.2 : schéma SQLite 16 → 17**, migration additive et transactionnelle : date de naissance privée de l’inscription sans compte et réglages, sans suppression de l’historique. Sauvegarder à froid tout le persistant **PRE 16** et WordPress, conserver le runtime 2.8.1, puis mettre à jour les deux composants vers 2.8.2. Avant réouverture, un retour exige le runtime 2.8.1 avec sa PRE 16 correspondante ; ne jamais démarrer 2.8.1 sur une base 17. Après de nouvelles écritures, préserver l’état et décider humainement d’une reprise, sans restauration automatique destructrice. [Procédure de mise à jour](docs/upgrade.md).

**2.7.1 → 2.8.0 : schéma SQLite 14 → 15**, migration additive et transactionnelle, sans conversion ni suppression des anciennes réservations. Conserver une sauvegarde complète PRE 14 et le runtime 2.7.1 ; ne jamais démarrer 2.7.1 sur la base 15.

**2.7.0 → 2.7.1 : schéma SQLite 14 inchangé**, aucune migration métier destructive attendue. Sauvegarder tout le persistant et conserver le runtime précédent, puis vérifier santé, intégrité/FK, données et configuration. Ne pas rejouer la migration historique 13 → 14. [Procédure de mise à jour](docs/upgrade.md).

Sauvegarder à froid **tout le persistant** avant tout changement de schéma et conserver l’image/code, Compose et configuration précédents. OpenFabLab 2.7.0 migre de manière additive du **schéma 13 au 14**, en préservant les clés historiques, et crée aussi une sauvegarde SQLite avant initialisation. Vérifier `integrity_check`, `foreign_key_check` et les données avant remise en service. Les anciennes animations restent en mode classique. **Ne jamais démarrer 2.6.x sur une base schéma 14** : un rollback exige la sauvegarde schéma 13 correspondante et la prise en compte des nouvelles écritures éventuelles. Voir [mise à jour](docs/upgrade.md) et [anciennes installations](docs/legacy-migration.md).

## Développement et tests

Les tests utilisent uniquement des données fictives et des bases temporaires. Aucun ZIP historique ou accès à une production n'est nécessaire.
Ces commandes s'exécutent depuis la copie du dépôt source ; le ZIP applicatif contient le runtime et ses guides, pas les suites de développement.

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci
npx playwright install chromium
.venv/bin/python tools/run_checks.py
.venv/bin/python build_openfablab.py
.venv/bin/python build_wordpress_plugin.py
.venv/bin/python tests/check_v26_archives.py
```

PHP 8.1+ est recommandé pour les tests natifs ; une alternative PHP WebAssembly locale est fournie pour les postes sans PHP. Les ZIP et leurs empreintes sont générés dans `dist/`, jamais à partir d'un dossier privé voisin. [Guide développeur](docs/development.md).

## Contribution et sécurité

Les comptes enfants/responsables et réservations familiales sont disponibles en **2.8.0**. Les extensions futures restent distinguées dans la [roadmap](ROADMAP.md).

Voir [CONTRIBUTING.md](CONTRIBUTING.md) et [SECURITY.md](SECURITY.md). Utiliser des données fictives, garder les migrations additives et respecter les licences des ressources. Signaler les vulnérabilités par le canal privé du dépôt lorsqu'il est activé, pas dans une issue publique contenant des secrets.

## Licence et remerciements

Code et ressources propres à OpenFabLab : [MIT](LICENSE), Copyright (c) 2026 William Aumand. Les composants tiers conservent leurs propres licences : [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), notamment jsQR (Apache 2.0) et Libre Franklin (SIL OFL 1.1).

Merci à **FougèresLab, FabLab de Fougères Agglomération**, pour la première installation réelle et le terrain de test. OpenFabLab est un projet créé par William Aumand ; cette collaboration ne fait pas de la collectivité le propriétaire ou l'éditeur du logiciel.
