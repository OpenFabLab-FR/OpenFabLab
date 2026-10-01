<p align="center"><img src="static/brand/OpenFabLab-logo-horizontal.svg" width="420" alt="OpenFabLab"></p>

# OpenFabLab

OpenFabLab est un logiciel libre de gestion de FabLab créé par **William Aumand**, distribué sous licence MIT. Il réunit la fréquentation du lieu, les usagers et les activités dans une application web installée sur le serveur de votre structure.

Site du projet : [openfablab.fr](https://openfablab.fr).

Cette édition est **OpenFabLab 2.6.2**, SQLite **schéma 13**, avec le plugin séparé **OpenFabLab Reservations 2.6.1**. Elle sépare les logos d’en-tête et de documents, permet un badge privé persistant et complète l’identité du responsable du traitement. Une installation neuve reste générique. Ce dépôt ne contient ni données d’une structure ni historique privé de déploiement. Voir [Personnalisation et badges](docs/branding.md).

## Fonctionnalités

- Suivi des arrivées/départs, visiteurs anonymes, usagers, identifiants QR et badges.
- Statistiques de fréquentation et exports, bilans d'activité.
- Animations, inscriptions, présence distincte de la réservation, listes d'attente, CSV et PDF.
- Réservation pour toute une animation ou par créneaux internes, capacité et attente par créneau.
- Locations, catalogue de machines, clients et dossiers de facturation.
- Identité visuelle configurable, modules activables, météo et notifications Discord facultatives.
- Sauvegarde/restauration SQLite et profil privé de configuration.
- Plugin WordPress : réservation publique, Normal/Test séparés, préremplissage contrôlé, six modèles d'e-mails texte et maintenance Test réservée à l'administration.

Les captures ne sont pas distribuées : aucun écran comportant des données personnelles n'est nécessaire à l'installation.

## Architecture

Une application **Python/Flask + SQLite** sert l'interface locale. Docker utilise Gunicorn. Le plugin PHP s'installe séparément sur WordPress. Le serveur du FabLab initie les échanges **HTTPS signés HMAC** vers WordPress ; la synchronisation ne nécessite aucun accès entrant vers ce serveur. Elle est facultative et désactivée sur une installation neuve.

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

Ouvrir `http://localhost:5080/stat/` ; santé : `/stat/sante`. Le projet/conteneur s'appelle `openfablab`, l'image `openfablab:v2.6.2`. Données : `./data:/data`, base `/data/openfablab.db`. Sauvegardes : `./backups:/nas-backups`, sous-dossier `OpenFabLab`. `.env.example` documente uniquement la racine de sauvegarde facultative. Protéger l'accès réseau et configurer HTTPS avant toute utilisation réelle ; aucun reverse proxy propre à une structure n'est livré.

## Première initialisation

Une instance neuve n'a **aucun usager, PIN, tarif, machine, compte bancaire, webhook ou secret WordPress prédéfini**. Définir le PIN Administrateur depuis l'accès local autorisé, puis configurer la structure et, si nécessaire, le PIN Modérateur. Dans Docker, un administrateur du serveur peut créer un lien privé à usage unique :

```sh
docker compose exec application python -m openfablab reset-admin-pin --database /data/openfablab.db
```

Ne partager ni enregistrer ce lien dans un document public. Compléter identité, fuseau, horaires, protection des données, tarifs et machines selon votre organisation. Voir [configuration](docs/configuration.md).

## Modules

Fréquentation, usagers, activités, réservations publiques, créneaux réservables, locations, facturation, météo et Discord sont configurables dans **Réglages → Structure et modules**. Désactiver les modules inutiles. Une animation à créneaux internes reste une seule animation ; elle ne devient pas une collection d'activités séparées.

## Réservations WordPress et créneaux

Installer le ZIP autonome Reservations 2.6.1 dans WordPress, puis configurer l'URL HTTPS racine du site et le même secret privé des deux côtés. N'autoriser qu'une instance OpenFabLab à synchroniser avec ce WordPress.

```text
[openfablab_reservations environment="test"]
[openfablab_reservations environment="production"]
```

Normal correspond à la valeur technique `production`. Test reste entièrement séparé. Les pages sont choisies par chaque structure ; aucun chemin n'est imposé. La cadence initiale est de deux minutes, administrable, avec synchronisation manuelle. Le plugin reste compatible avec le parcours classique OpenFabLab 2.5.0 ; les créneaux nécessitent OpenFabLab 2.6.x et la capability `animation_slots_v1`.

Exemple : **Découverte casque VR**, 10:00–12:00, durée 20 minutes, battement 10 minutes, une place par créneau : **10:00–10:20, 10:30–10:50, 11:00–11:20, 11:30–11:50**. Les créneaux ont des capacités et files d'attente indépendantes. [Guide WordPress](docs/wordpress.md), [créneaux](docs/animation-slots.md), [modèles d'e-mails](docs/email-templates.md).

## Sauvegarde et restauration

Sauvegarder la base **et les fichiers privés persistants**. Un export SQLite seul ne contient pas les secrets stockés à côté. Les profils `.openfablab-profile.zip` sont également privés. Conserver des copies protégées et tester leur restauration sur une instance isolée. [Procédure complète](docs/backup-restore.md).

## Mise à jour

Sauvegarder à froid avant tout changement de schéma, conserver l'image/code précédents, vérifier intégrité, clés étrangères et données avant remise en service. La migration 12 → 13 est additive ; les anciennes animations restent en mode classique. Un rollback vers un ancien schéma exige sa sauvegarde cohérente, jamais la base migrée. Voir [mise à jour](docs/upgrade.md) et [anciennes installations](docs/legacy-migration.md).

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

Voir [CONTRIBUTING.md](CONTRIBUTING.md) et [SECURITY.md](SECURITY.md). Utiliser des données fictives, garder les migrations additives et respecter les licences des ressources. Signaler les vulnérabilités par le canal privé du dépôt lorsqu'il est activé, pas dans une issue publique contenant des secrets.

## Licence et remerciements

Code et ressources propres à OpenFabLab : [MIT](LICENSE), Copyright (c) 2026 William Aumand. Les composants tiers conservent leurs propres licences : [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), notamment jsQR (Apache 2.0) et Libre Franklin (SIL OFL 1.1).

Merci à **FougèresLab, FabLab de Fougères Agglomération**, pour la première installation réelle et le terrain de test. OpenFabLab est un projet créé par William Aumand ; cette collaboration ne fait pas de la collectivité le propriétaire ou l'éditeur du logiciel.
