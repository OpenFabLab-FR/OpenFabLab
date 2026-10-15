# Installer OpenFabLab sur un Synology compatible

Guide public générique, **pas** une procédure privée d’une installation existante. Vérifier sur la documentation du modèle que DSM et Container Manager/Docker sont disponibles et que l’architecture est 64 bits. Tous les NAS Synology ne sont pas équivalents. Voir [compatibilité](platform-compatibility.md).

Dans le Centre de paquets, installer Container Manager si le modèle le propose. Créer un dossier de projet neuf, y extraire l’archive vérifiée puis ouvrir Projet → Créer et utiliser le `compose.yaml` fourni. Examiner le port 5080 et les montages relatifs `data` et `backups` ; choisir des dossiers persistants et les autorisations nécessaires au processus, sans permissions universelles.

Ne pas remplacer les volumes d’une installation existante par ceux de cet exemple. Ne pas transmettre de secret au gestionnaire de projet public. Un `.env` propre au serveur reste privé. Éviter les conteneurs concurrents sur la même SQLite. Construire l’image selon les fonctions disponibles de Container Manager ou depuis un terminal administrateur du serveur avec les commandes Compose du [guide commun](installation-common.md).

Après démarrage, contrôler la santé et ouvrir `/stat/` depuis le réseau local autorisé. Configurer PIN, identité, protection des données et intégrations. `restart: unless-stopped` est conservé ; vérifier le redémarrage de Container Manager/du projet après un reboot DSM. Une URL publique du NAS n’est pas nécessaire pour les réservations WordPress : OpenFabLab initie HTTPS vers WordPress.

Conserver base, fichiers privés, branding, PIN, secrets et configurations dans les emplacements persistants choisis. Faire une sauvegarde complète cohérente en fonctionnement ou arrêter proprement pour une copie froide complète ; ne pas copier seulement une SQLite ouverte. Tester une restauration sur un projet isolé sans communications externes.

Pour mettre à jour : relever version et schéma, sauvegarder PRE complète avec l’image précédente, préparer le build avant interruption, arrêter proprement, sauvegarder à froid les dernières écritures, installer seulement le runtime, migrer puis contrôler santé, données, intégrité/FK et réglages. Sauvegarder POST après reprise. Dès une tentative publique, aucune ancienne base ne doit être restaurée automatiquement.

Les chemins, scripts et paquets privés d'un exploitant restent hors de cette documentation et des releases publiques. Les détails pratiques communs figurent dans [exploitation](installation-common.md), [mise à jour](upgrade.md) et [sauvegarde/restauration](backup-restore.md). Les tests Mac ne constituent pas une construction ou un démarrage sur un nouveau Synology ; chaque installation cible doit être validée par son administrateur. La validation terrain d'une installation 2.9.0 ne certifie pas tous les modèles.
