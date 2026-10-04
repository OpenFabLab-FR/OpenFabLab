# Sauvegardes privées complètes et copies de test

Réglages → Données distingue trois exports : SQLite seul (données métier),
sauvegarde complète privée (installation) et copie privée pour test (clone isolé).
Les deux archives privées contiennent des données personnelles et des dérivations
de PIN. Elles ne sont **pas chiffrées** : stockage sécurisé, accès restreint,
jamais GitHub, site public ou capture. Une empreinte détecte une altération mais
n'authentifie pas l'auteur : ne restaurez que des archives de confiance.

## Format v1

ZIP : `backup-manifest.json` et `persistent/…`. Le manifeste contient format,
version du format, type `complete`/`test`, version applicative, schéma SQLite,
date UTC, présence des composants, liaisons des fichiers privés et, pour chaque
fichier, chemin relatif, taille, permissions et SHA-256. Aucune valeur de secret
n'est inscrite dans le manifeste. Les fichiers privés eux-mêmes sont dans le ZIP.

Les anciennes valeurs de PIN en clair encore présentes dans SQLite provoquent un
refus : elles doivent d'abord être dérivées par le mécanisme normal. Les variables
de PIN initial dans un éventuel fichier `.env` persistant sont retirées de la
copie ; les dérivations locales permettent de conserver l'authentification.

Tout le dossier persistant (parent de la base) est inclus par défaut, notamment
base, PIN dérivés, clé Flask, identité, logos, signature, badge privé, profil,
SMTP, synchronisation WordPress et webhook Discord. SQLite est copié par son API
de sauvegarde, avec consolidation du WAL : aucune base active copiée à la volée.
Les requêtes, travailleurs et exports coopèrent via un verrou de stockage.

Exclusions explicites : caches, logs, temporaires, locks, jeton temporaire de
récupération PIN, journaux SQLite déjà consolidés, sauvegardes précédentes et
répertoires de restauration. Liens symboliques et fichiers spéciaux sont refusés
(pas ignorés). Pour une ancienne installation locale où base et sources partagent
un dossier, les sources publiques et dépendances de développement sont exclues.
En production, utilisez toujours un dossier persistant dédié, monté sur `/data`.
Un fichier privé inconnu futur reste inclus : ce n'est pas une liste blanche de
fichiers privés. Les répertoires vides sans fichier ne sont pas transportés.

La configuration de déploiement (image, Compose, variables d'environnement
externes au dossier persistant, reverse proxy) n'est pas une donnée applicative.
Conservez-la séparément. Le paquet de mise à jour NAS sauvegarde aussi ce runtime.
Les chemins de clé Flask et de webhook configurés sont liés au runtime lors de
l'export Web ; une restauration Web vers des clés situées hors du persistant est
refusée pour éviter un remplacement partiel. Utilisez alors la restauration hors
ligne et rétablissez explicitement les chemins de votre runtime.

## Copie pour test

La base est copiée puis neutralisée : réservations publiques, Discord et météo
désactivés, URL WordPress et secrets d'intégration retirés. SMTP désactivé,
identifiants de connexion supprimés. Les fichiers de webhook, secret de
synchronisation et `.env` ne sont pas transportés dans ce clone. Le PIN reste sa
dérivation existante (sel, paramètres et hash), indépendante du système hôte.
La clé Flask est renouvelée : les sessions/cookies de production ne sont pas
réutilisables. Le clone conserve les données, catégories, horaires et branding.

Le marqueur `.openfablab-test-instance.json` bloque les travailleurs et les
connexions externes (DNS, sockets, HTTPS et SMTP), même si un réglage est réactivé
dans l'interface. Le loopback et les sockets locaux restent utilisables. Le
contrôle s'applique aussi avec `OPENFABLAB_EXTERNAL_ACTIONS=0` pour les opérations
hors ligne. Aucun accès réseau externe n'est requis pour créer/restaurer un ZIP.
Le type `test` du manifeste réimpose la neutralisation à la restauration, même si
le fichier marqueur est absent de l'archive. Une restauration complète dans une
instance de test ne réactive pas ses intégrations. Une conversion volontaire en
production demande une intervention explicite hors ligne ; elle n'est pas faite
par l'interface d'administration.

## Restauration contrôlée

Administrateur seulement, POST et nonce de session, confirmation exacte
`RESTAURER INSTALLATION`. Format, compatibilité (2.6.x/2.7.x, schéma 13/14),
liste exacte des fichiers, chemins, tailles, empreintes, SQLite integrity/FK et
format des dérivations PIN sont vérifiés avant remplacement. Les archives
futures, fichiers supplémentaires, doublons et chemins dangereux sont refusés.
Limites : 20 000 fichiers, 2 Gio décompressés, 100 Mio téléversés via l'interface.

Une archive de sécurité `restore-backups/<identifiant>/before-restore.zip` et
l'ancien état sont conservés. Les fichiers sont remplacés, **pas fusionnés**.
Le remplacement est journalisé et protégé par verrou ; chaque renommage est
atomique, mais un ensemble de fichiers ne constitue pas une transaction de
système de fichiers. Une interruption laisse un journal et interdit le démarrage
normal jusqu'à récupération. Une erreur gérée restaure l'ancien état. Ne faites
pas fonctionner deux versions différentes sur le même persistant.

Après restauration : intégrité, FK, schéma, initialisation additive normale et
reconnexion avec le PIN de l'archive. Une base 13 est migrée normalement vers 14
par OpenFabLab 2.7.x ; jamais de rétrogradation 14 → 13.

Hors ligne (service arrêté) :

```sh
python private_backup.py export --database data/openfablab.db --archive /chemin-prive/complet.zip
python private_backup.py export --kind test --database data/openfablab.db --archive /chemin-prive/test.zip
python private_backup.py validate --archive /chemin-prive/test.zip
python private_backup.py restore --database data/openfablab.db --archive /chemin-prive/test.zip
python private_backup.py recover --database data/openfablab.db
```

Le dossier Review est un dossier de développement, **pas** un format de sauvegarde.
Pour un diagnostic privé, transmettez uniquement la copie de test, par un canal
privé adapté, jamais une archive complète de production contenant ses secrets.
