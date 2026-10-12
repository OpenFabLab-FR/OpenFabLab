# Exploiter OpenFabLab, quelle que soit la plateforme

Une application Python/Flask/SQLite, Gunicorn dans Docker, un stockage persistant local fiable et un seul processus de réservation/synchronisation. WordPress reste facultatif. Ne pas partager la base active entre plusieurs instances ou la placer sur un montage réseau SQLite non validé.

## Premier lancement et réseau

Vérifier l’architecture 64 bits et la [matrice de compatibilité](platform-compatibility.md). Construire l’image localement : aucun registre d’images OpenFabLab officielles n’est annoncé. Dans un dossier neuf, vérifier SHA256SUMS avant extraction. Examiner Compose, ses ports et montages avant démarrage.

Le Compose fourni expose 5080 sur les interfaces du serveur. Pour un essai sur le serveur lui-même, remplacer la ligne de port par `127.0.0.1:5080:8000`. Pour une borne sur le réseau local, choisir volontairement l’interface LAN et restreindre l’accès réseau. Jamais de redirection WAN générale. Un accès distant exige VPN ou accès HTTPS contrôlé ; les PIN seuls ne protègent pas une administration Internet. Le relais WordPress n’exige aucun port entrant.

```sh
docker compose config --quiet
docker compose build application
docker compose up -d application
docker compose ps
docker compose logs --tail=100 application
```

À exécuter dans le dossier choisi, après adaptation, pas dans une production existante. Ouvrir `/stat/` ; santé `/stat/sante`. Configurer le PIN Administrateur depuis l’accès local autorisé, l’identité, le fuseau, les modules et la protection des données. SMTP et Discord sont facultatifs : voir [configuration](configuration.md), [sécurité](../SECURITY.md), [modèles](email-templates.md), [WordPress](wordpress.md).

Les montages `./data:/data` et `./backups:/nas-backups` conservent base, secrets, PIN, branding et sauvegardes. Ne pas retirer ces répertoires lors d’une recréation. Un `.env` privé n’est ni un asset public ni une sauvegarde complète. Vérifier les droits effectifs sans rendre le stockage accessible à tous.

```sh
docker compose stop -t 30 application
docker compose start application
docker compose restart application
```

`restart: unless-stopped` reprend le conteneur au démarrage de Docker ; vérifier aussi le démarrage automatique de Docker sur le système. Un arrêt volontaire n’est pas automatiquement annulé.

## Sauvegarder et restaurer

Utiliser **Réglages → Données → Sauvegarde complète privée** pour une sauvegarde cohérente en fonctionnement : API de sauvegarde SQLite, fichiers persistants, manifeste et empreintes. Ne pas copier seulement une base ouverte en oubliant son WAL. Conserver séparément Compose, `.env`, l’image/runtime et les paramètres du serveur.

Pour une copie froide, arrêter proprement et copier **tout** le persistant, y compris les fichiers cachés, avant de le remplacer. Tester la restauration dans un dossier et des volumes distincts, réseaux externes neutralisés. La sauvegarde contient des données privées et n’est pas chiffrée : stockage protégé, jamais GitHub.

Voir [procédure testable](backup-restore.md) et [format/restauration privés](private-backup.md). Avant mise à jour : PRE complète + runtime exact, construction avant arrêt, copie froide finale, migration, intégrité/FK, santé et paramètres, puis POST. Après une tentative publique, aucune ancienne base ne doit être restaurée automatiquement. [Guide de mise à jour](upgrade.md).

## Diagnostic

Vérifier successivement `docker compose ps`, journaux, permissions et espace disque, URL/préfixe, santé locale. En cas de liaison WordPress, vérifier HTTPS et catalogue/relève Normal/Test sans régénérer de secret au hasard. Ne pas transmettre de logs contenant des liens personnels ou configurations privées. Les réservations restent contrôlées par OpenFabLab, jamais par un calcul WordPress de secours.
