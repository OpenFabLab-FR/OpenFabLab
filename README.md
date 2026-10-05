<p align="center"><img src="static/brand/OpenFabLab-logo-horizontal.svg" width="420" alt="OpenFabLab"></p>

# OpenFabLab 2.8.0

**Version stable · SQLite schéma 15 · plugin optionnel Reservations 2.8.0**

Télécharger l'application, le plugin facultatif et leurs empreintes depuis la [release 2.8.0](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.8.0). Lire les [règles familiales et réservations](docs/families-2.8.md) et la [mise à jour depuis 2.7.1](docs/upgrade.md) avant de changer une installation existante.

OpenFabLab est un logiciel libre de gestion de FabLab créé par **William Aumand**, distribué sous licence MIT. Il réunit la fréquentation du lieu, les usagers et les activités dans une application web installée sur le serveur de votre structure.

Site du projet : [openfablab.fr](https://openfablab.fr).

OpenFabLab 2.8.0 introduit les comptes rattachés à des responsables et les réservations familiales : une personne, un compte, une place. La borne, l'administration et WordPress utilisent désormais le même moteur local, avec groupes indivisibles, liste d'attente et propositions automatiques par e-mail. Le calendrier et l'interface ont aussi été harmonisés. La version a été migrée puis déployée et vérifiée en conditions réelles au FougèresLab. Une installation neuve reste générique ; chaque structure active et configure ses modules. Voir le [changelog](CHANGELOG.md) et la [personnalisation](docs/branding.md).

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
- Plugin WordPress 2.8 optionnel : parcours familial, Normal/Test séparés, relais HTTPS signé vers le même moteur ; anciens e-mails et outils conservés pour l'historique, sans reprise automatique pour les nouvelles demandes.

Les captures ne sont pas distribuées : aucun écran comportant des données personnelles n'est nécessaire à l'installation.

## Architecture

Une application **Python/Flask + SQLite** sert l'interface locale. Docker utilise Gunicorn. Le plugin PHP s'installe séparément sur WordPress. Pour les nouvelles réservations 2.8, **OpenFabLab est l'unique autorité de capacité** : WordPress lui adresse des appels **HTTPS signés HMAC**. Il faut donc que ce serveur soit accessible au site WordPress via un accès HTTPS sécurisé ; cela diffère du protocole sortant 2.7. WordPress n'est pas nécessaire aux réservations locales.

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

Ouvrir `http://localhost:5080/stat/` ; santé : `/stat/sante`. Le projet/conteneur s'appelle `openfablab`, l'image `openfablab:v2.8.0`. Données : `./data:/data`, base `/data/openfablab.db`. Sauvegardes : `./backups:/nas-backups`, sous-dossier `OpenFabLab`. `.env.example` documente uniquement la racine de sauvegarde facultative. Employer des volumes et ports d'essai distincts ; ne pas exécuter ces commandes dans une installation de production. Protéger l'accès réseau et configurer HTTPS avant toute utilisation réelle ; aucun reverse proxy propre à une structure n'est livré.

## Première initialisation

Une instance neuve n'a **aucun usager, PIN, tarif, machine, compte bancaire, webhook ou secret WordPress prédéfini**. Définir le PIN Administrateur depuis l'accès local autorisé, puis configurer la structure et, si nécessaire, le PIN Modérateur. Dans Docker, un administrateur du serveur peut créer un lien privé à usage unique :

```sh
docker compose exec application python -m openfablab reset-admin-pin --database /data/openfablab.db
```

Ne partager ni enregistrer ce lien dans un document public. Compléter identité, fuseau, horaires, protection des données, tarifs et machines selon votre organisation. Voir [configuration](docs/configuration.md).

## Modules

Fréquentation, usagers, activités, réservations publiques, créneaux réservables, locations, facturation, météo et Discord sont configurables dans **Réglages → Structure et modules**. Désactiver les modules inutiles. Une animation à créneaux internes reste une seule animation ; elle ne devient pas une collection d'activités séparées.

## Réservations depuis la borne, WordPress et créneaux

En **2.8.0**, le moteur commun est OpenFabLab : une personne sélectionnée = une place, responsables compris s'ils participent. Les groupes sont confirmés ou mis en attente ensemble, sans confirmation partielle. La borne fonctionne sans Internet si le serveur local reste accessible. Activer **Réglages → Usagers → Autoriser la réservation d’animations depuis la borne**. L'accès public figure sur la page Gestion, sans PIN.

WordPress reste **facultatif**. **OpenFabLab Reservations 2.8.0** utilise les mêmes comptes liés et règles, après identification par ID/contact connu, et exige un accès HTTPS signé au serveur OpenFabLab. Le plugin 2.7 ne peut pas traiter les nouvelles réservations 2.8. Les anciennes références du plugin peuvent être nettoyées manuellement après sauvegarde, sans toucher aux données OpenFabLab. La liste d’attente propose automatiquement les places au plus ancien groupe compatible ; e-mail natif, blocage temporaire, réponse et expiration sont gérés par OpenFabLab. Un e-mail valide est obligatoire ; le téléphone peut être exigé par la structure. Voir [familles et compatibilité](docs/families-2.8.md).

```text
[openfablab_reservations environment="test"]
[openfablab_reservations environment="production"]
```

Normal correspond à la valeur technique `production`. Test reste séparé. Les pages sont choisies par chaque structure ; aucun chemin n'est imposé. Les nouvelles demandes sont traitées directement dans OpenFabLab : elles n'attendent pas une synchronisation du moteur historique WordPress. La compatibilité de l'ancien couple application 2.7.1/plugin 2.7.0 reste documentée dans [les corrections 2.7.1](docs/corrections-2.7.1.md).

Exemple : **Découverte casque VR**, 10:00–12:00, durée 20 minutes, battement 10 minutes, une place par créneau : **10:00–10:20, 10:30–10:50, 11:00–11:20, 11:30–11:50**. Les créneaux ont des capacités et files d'attente indépendantes. [Guide WordPress](docs/wordpress.md), [créneaux](docs/animation-slots.md), [modèles d'e-mails](docs/email-templates.md).

## Sauvegarde et restauration

Dans **Réglages → Données**, choisir le niveau adapté :

1. **Sauvegarde SQLite** : données métier ; les fichiers privés externes ne sont pas inclus.
2. **Sauvegarde complète privée** : base, dérivations PIN, clé persistante, réglages et ressources de l’installation, avec manifeste et empreintes.
3. **Copie privée pour test/diagnostic** : données et identité conservées, intégrations externes neutralisées et connexions externes bloquées.

Ces fichiers peuvent contenir des données personnelles et des secrets : ils ne sont pas chiffrés et **ne doivent jamais être publiés**. Conserver aussi la configuration de déploiement et tester la restauration sur une instance isolée. Un profil `.openfablab-profile.zip` ne remplace pas une sauvegarde d’installation. [Procédure complète](docs/backup-restore.md), [format privé et restauration](docs/private-backup.md).

## Mise à jour

**2.7.1 → 2.8.0 : schéma SQLite 14 → 15**, migration additive et transactionnelle, sans conversion ni suppression des anciennes réservations. Une copie SQLite cohérente 14 précède l'initialisation ; conserver aussi une sauvegarde complète privée et le runtime 2.7.1. Ne jamais démarrer 2.7.1 sur la base 15. Le rollback exige la PRE 14 avec ses fichiers privés, installation arrêtée ; après de nouvelles écritures, aucune restauration automatique. [Procédure de mise à jour](docs/upgrade.md), [guide de vérification isolée](docs/candidate-2.8-guide.md).

### Référence historique des schémas

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
