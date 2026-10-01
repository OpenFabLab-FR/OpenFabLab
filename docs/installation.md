# Installer une nouvelle instance

Application 2.6.2, schéma SQLite 13. Prérequis : Python 3.10+ (3.12 dans Docker), navigateur moderne, disque persistant. Le plugin optionnel demande WordPress avec PHP 8.1+ et HTTPS. Les tests n'installent pas WordPress ni MySQL.

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

La préparation publique a été contrôlée statiquement pour Docker. Un build d'image réel doit être validé sur une machine Docker isolée ; les tests Python locaux ne le remplacent pas.
