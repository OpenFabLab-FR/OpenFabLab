<p align="center"><img src="static/brand/OpenFabLab-logo-horizontal.svg" width="420" alt="OpenFabLab"></p>

# OpenFabLab 2.7.0

**Version stable · SQLite schéma 14 · OpenFabLab Reservations 2.7.0**

OpenFabLab est un logiciel libre de gestion de FabLab créé par **William Aumand**, distribué sous licence MIT. Il réunit la fréquentation du lieu, les usagers et les activités dans une application web installée sur le serveur de votre structure.

Site du projet : [openfablab.fr](https://openfablab.fr).

OpenFabLab 2.7.0 est une version stable, testée localement puis validée sur une installation réelle de FabLab. Elle enrichit le quotidien du Fabmanager : calendrier centralisé, ressources réservables, formations et habilitations, catégories d’usagers configurables, inscription autonome facultative et sauvegardes privées complètes. Une installation neuve reste générique. Voir [les nouveautés et leur fonctionnement](docs/evolution-2.7.md) et [la personnalisation](docs/branding.md).

La navigation Réglages comporte sept onglets courts et des formulaires compacts. Le calendrier Semaine/Mois propose une plage visible configurable, 09:00–19:00 par défaut, sans double défilement vertical. Les modules Ressources et Formations restent facultatifs. Une installation neuve propose Usager, Bénévole et Manager ; une migration conserve les catégories historiques, y compris celles sans usager actuel. Le lien facultatif **Créer un compte** reste discret dans le pied de la borne.

## Fonctionnalités

- Suivi des arrivées/départs, visiteurs anonymes, usagers, identifiants QR et badges.
- Statistiques de fréquentation et exports, bilans d'activité.
- Animations, inscriptions, présence distincte de la réservation, listes d'attente, CSV et PDF.
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
- Plugin WordPress : réservation publique, Normal/Test séparés, préremplissage contrôlé, six modèles d'e-mails texte, réconciliation du catalogue, reprise des synchronisations manquées et maintenance réservée à l'administration.

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

Ouvrir `http://localhost:5080/stat/` ; santé : `/stat/sante`. Le projet/conteneur s'appelle `openfablab`, l'image `openfablab:v2.7.0`. Données : `./data:/data`, base `/data/openfablab.db`. Sauvegardes : `./backups:/nas-backups`, sous-dossier `OpenFabLab`. `.env.example` documente uniquement la racine de sauvegarde facultative. Protéger l'accès réseau et configurer HTTPS avant toute utilisation réelle ; aucun reverse proxy propre à une structure n'est livré.

## Première initialisation

Une instance neuve n'a **aucun usager, PIN, tarif, machine, compte bancaire, webhook ou secret WordPress prédéfini**. Définir le PIN Administrateur depuis l'accès local autorisé, puis configurer la structure et, si nécessaire, le PIN Modérateur. Dans Docker, un administrateur du serveur peut créer un lien privé à usage unique :

```sh
docker compose exec application python -m openfablab reset-admin-pin --database /data/openfablab.db
```

Ne partager ni enregistrer ce lien dans un document public. Compléter identité, fuseau, horaires, protection des données, tarifs et machines selon votre organisation. Voir [configuration](docs/configuration.md).

## Modules

Fréquentation, usagers, activités, réservations publiques, créneaux réservables, locations, facturation, météo et Discord sont configurables dans **Réglages → Structure et modules**. Désactiver les modules inutiles. Une animation à créneaux internes reste une seule animation ; elle ne devient pas une collection d'activités séparées.

## Réservations WordPress et créneaux

Installer le ZIP autonome Reservations 2.7.0 dans WordPress, après un essai sur une installation séparée, puis configurer l'URL HTTPS racine du site et le même secret privé des deux côtés. N'autoriser qu'une instance OpenFabLab à synchroniser avec ce WordPress.

```text
[openfablab_reservations environment="test"]
[openfablab_reservations environment="production"]
```

Normal correspond à la valeur technique `production`. Test reste entièrement séparé. Les pages sont choisies par chaque structure ; aucun chemin n'est imposé. La cadence initiale est de deux minutes, administrable, avec synchronisation manuelle. Le plugin reste compatible avec le parcours classique OpenFabLab 2.5.0 ; les créneaux nécessitent OpenFabLab 2.6.x et la capability `animation_slots_v1`.

Exemple : **Découverte casque VR**, 10:00–12:00, durée 20 minutes, battement 10 minutes, une place par créneau : **10:00–10:20, 10:30–10:50, 11:00–11:20, 11:30–11:50**. Les créneaux ont des capacités et files d'attente indépendantes. [Guide WordPress](docs/wordpress.md), [créneaux](docs/animation-slots.md), [modèles d'e-mails](docs/email-templates.md).

## Sauvegarde et restauration

Dans **Réglages → Données**, choisir le niveau adapté :

1. **Sauvegarde SQLite** : données métier ; les fichiers privés externes ne sont pas inclus.
2. **Sauvegarde complète privée** : base, dérivations PIN, clé persistante, réglages et ressources de l’installation, avec manifeste et empreintes.
3. **Copie privée pour test/diagnostic** : données et identité conservées, intégrations externes neutralisées et connexions externes bloquées.

Ces fichiers peuvent contenir des données personnelles et des secrets : ils ne sont pas chiffrés et **ne doivent jamais être publiés**. Conserver aussi la configuration de déploiement et tester la restauration sur une instance isolée. Un profil `.openfablab-profile.zip` ne remplace pas une sauvegarde d’installation. [Procédure complète](docs/backup-restore.md), [format privé et restauration](docs/private-backup.md).

## Mise à jour

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

Voir [CONTRIBUTING.md](CONTRIBUTING.md) et [SECURITY.md](SECURITY.md). Utiliser des données fictives, garder les migrations additives et respecter les licences des ressources. Signaler les vulnérabilités par le canal privé du dépôt lorsqu'il est activé, pas dans une issue publique contenant des secrets.

## Licence et remerciements

Code et ressources propres à OpenFabLab : [MIT](LICENSE), Copyright (c) 2026 William Aumand. Les composants tiers conservent leurs propres licences : [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), notamment jsQR (Apache 2.0) et Libre Franklin (SIL OFL 1.1).

Merci à **FougèresLab, FabLab de Fougères Agglomération**, pour la première installation réelle et le terrain de test. OpenFabLab est un projet créé par William Aumand ; cette collaboration ne fait pas de la collectivité le propriétaire ou l'éditeur du logiciel.
