# Installer une nouvelle instance

OpenFabLab **2.8.4** est la dernière version stable, avec SQLite 18 et le plugin facultatif 2.8.2 inchangé. Voir [les corrections](corrections-2.8.4.md). Ne pas remplacer une installation existante sans sa sauvegarde complète et sans lire la procédure de mise à jour.

## OpenFabLab 2.8.4 stable

L'application utilise SQLite **18** et le plugin facultatif **2.8.2 inchangé**, protocole **4 / révision 3**. Les nouvelles installations proposent l'identifiant public visible ; les installations mises à jour conservent le mode discret. Voir [les nouveautés](usability-2.8.3.md). Pour une mise à jour, lire [upgrade.md](upgrade.md) et sauvegarder les données et le runtime avant toute migration.

Télécharger l'application et `SHA256SUMS` depuis la [release 2.8.4](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.8.4), vérifier l'empreinte puis utiliser un dossier neuf. Le [ZIP officiel du plugin 2.8.2](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.8.2/openfablab-reservations-2.8.2.zip) reste compatible : ne pas le réinstaller s'il est déjà à jour. Pour une installation existante, suivre [la procédure de mise à jour](upgrade.md), sans remplacer ses données par une base de test. Le ZIP approuvé conserve ses guides de préparation ; la documentation du tag `v2.8.4` est la référence publiée à jour.

Prérequis : Python 3.10+ (3.12 dans Docker), navigateur moderne, disque persistant. Le plugin demande WordPress avec PHP 8.1+, OpenSSL AES-GCM, InnoDB, JavaScript et HTTPS ; seul OpenFabLab doit pouvoir joindre WordPress en HTTPS sortant. La borne et l'application fonctionnent sans plugin. Voir [le guide WordPress](wordpress.md) et [les vérifications isolées](candidate-2.8-guide.md).

## Python local

Extraire le ZIP applicatif dans un dossier neuf, sans dossier privé voisin nécessaire. Créer `.venv`, installer `requirements.txt`, puis lancer `.venv/bin/python app.py`. L'adresse locale est `http://localhost:5001`. Ce serveur de développement n'est pas destiné à une exposition publique.

Sans configuration explicite, la base canonique est `openfablab.db` dans le projet et les fichiers privés suivent son emplacement. Pour une installation durable, définir `OPENFABLAB_DATABASE` vers un chemin persistant, par exemple un dossier `data/openfablab.db`, et `OPENFABLAB_SECRET_KEY_FILE` dans ce même dossier. Ne jamais pointer une instance de test vers les données d'une installation réelle.

## Docker Compose

```sh
docker compose config --quiet
docker compose build application
docker compose up -d application
```

Le compose fourni publie `5080:8000`, préfixe `/stat`, `restart: unless-stopped` et healthcheck `/stat/sante`. Il monte **`./data:/data`** et **`${OPENFABLAB_BACKUP_HOST_ROOT:-./backups}:/nas-backups`**. Le sous-dossier de sauvegarde initial est `OpenFabLab`, modifiable dans les réglages. Une racine différente peut être définie dans un `.env` privé à partir de `.env.example`, sans y mettre de secret.

Vérifier que l'utilisateur du processus peut créer et conserver les fichiers dans les montages. Ne pas contourner un refus d'accès par des permissions globales ouvertes. Aucun chemin de NAS, nom de domaine ou reverse proxy particulier n'est imposé par cette distribution.

## Initialisation

Ouvrir `/stat/`. L'installation est vide : aucun usager, machine, tarif ou PIN prédéfini. La configuration initiale Admin est réservée à l'accès local autorisé. Pour Docker, depuis un accès administrateur au serveur :

```sh
docker compose exec application python -m openfablab reset-admin-pin --database /data/openfablab.db
```

Ouvrir le chemin privé émis sur **votre** instance dans les dix minutes, définir un nouveau PIN, puis configurer le Modérateur si nécessaire. Ne publier ni ce lien ni les PIN. Compléter [la configuration](configuration.md), les informations aux usagers et la protection réseau avant ouverture.

Le packaging Docker inclut les modules du moteur familial, de liste d'attente et de palette pastel. Les fichiers des instructions de copie et l'entrée WSGI sont contrôlés par démarrage local. Aucun nouveau build Docker réel n'est revendiqué sur le poste de publication. Vérifier l'image et les montages sur chaque installation cible.
