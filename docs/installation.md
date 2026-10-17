# Installer une nouvelle instance

## OpenFabLab 2.10.0 stable

Télécharger l’[application et les empreintes](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.10.0),
vérifier le ZIP puis l’extraire dans un dossier neuf. SQLite **21** est créée
à l’initialisation, sans usagers ni abonnements préchargés. Le module Abonnements
et crédits est **désactivé par défaut** ; l’application fonctionne sans ce module
et sans WordPress. Sons activés à **50 %** pour les préférences absentes,
désactivables dans Réglages → Borne. Les confirmations visuelles sont conservées.

Le plugin facultatif **Reservations 2.9.0**, protocole **4/révision 3**, est inchangé.
Il n’a pas à être réinstallé s’il est déjà en 2.9.0. Voir [WordPress](wordpress.md),
[les nouveautés](evolution-2.10.0.md) et [la configuration](configuration.md).
Les prérequis et les méthodes Python/Compose ci-dessous restent applicables.
Guides : [Linux](installation-linux.md), [Raspberry Pi](installation-raspberry-pi.md),
[Windows](installation-windows.md), [Synology](installation-synology.md).
Une installation existante doit suivre [la mise à jour](upgrade.md) avec sauvegarde.
Les ZIP validés sont conservés sans reconstruction ; la documentation de ce tag
est la référence stable si un guide embarqué conserve une mention de préparation.

## Référence historique : installation 2.9.0

## OpenFabLab 2.9.0 stable

L’application utilise **SQLite 20**, avec le plugin facultatif **Reservations
2.9.0 / protocole 4, révision 3**. Elle fonctionne entièrement sans WordPress.
Télécharger l’[application et SHA256SUMS](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.9.0),
vérifier l’empreinte, puis extraire dans un dossier neuf. Le
[ZIP du plugin 2.9.0](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.9.0/openfablab-reservations-2.9.0.zip)
ne s’installe que si cette interface publique est souhaitée. Le plugin 2.8.5
reste compatible avec ses affichages antérieurs ; 2.9.0 apporte les nouveaux
compteurs et états d’attente. Voir [le guide 2.9.0](evolution-2.9.0.md).

Une installation existante doit suivre [la mise à jour](upgrade.md), avec
sauvegarde complète et conservation du runtime avant toute intervention.
Les nouvelles installations proposent l’identifiant public visible ; les
installations mises à jour conservent leur mode et leurs paramètres.

Une seule application : [Linux](installation-linux.md), [Raspberry Pi 64 bits](installation-raspberry-pi.md),
[Windows avec Linux](installation-windows.md), [Synology générique](installation-synology.md).
Lire aussi [les limites réellement vérifiées](platform-compatibility.md) et
[les opérations communes](installation-common.md). Aucun essai matériel non
réalisé n’est présenté comme validé. Les ZIP approuvés restent inchangés ; leurs
guides peuvent conserver des mentions de préparation. La documentation du tag
`v2.9.0` reste la référence pour cette ancienne version ; la stable courante
est 2.10.0, présentée ci-dessus.

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

L'exemple Compose courant nomme l'image `openfablab:v2.10.0`.
L'étiquette nomme l'image construite depuis ce dossier ; elle ne suffit pas à
prouver sa version réelle. Le runtime de l'archive courante est **2.10.0**.
Une installation existante peut conserver un ancien alias : vérifier la version
dans l'interface après construction, sans remplacer son Compose personnalisé.

Vérifier que l'utilisateur du processus peut créer et conserver les fichiers dans les montages. Ne pas contourner un refus d'accès par des permissions globales ouvertes. Aucun chemin de NAS, nom de domaine ou reverse proxy particulier n'est imposé par cette distribution.

## Initialisation

Ouvrir `/stat/`. L'installation est vide : aucun usager, machine, tarif ou PIN prédéfini. La configuration initiale Admin est réservée à l'accès local autorisé. Pour Docker, depuis un accès administrateur au serveur :

```sh
docker compose exec application python -m openfablab reset-admin-pin --database /data/openfablab.db
```

Ouvrir le chemin privé émis sur **votre** instance dans les dix minutes, définir un nouveau PIN, puis configurer le Modérateur si nécessaire. Ne publier ni ce lien ni les PIN. Compléter [la configuration](configuration.md), les informations aux usagers et la protection réseau avant ouverture.

Le packaging Docker inclut les modules du moteur familial, de liste d'attente et de palette pastel. Les fichiers des instructions de copie et l'entrée WSGI sont contrôlés par démarrage local. Aucun nouveau build Docker réel n'est revendiqué sur le poste de publication. Vérifier l'image et les montages sur chaque installation cible.
