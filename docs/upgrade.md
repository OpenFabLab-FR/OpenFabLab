# Mettre à jour OpenFabLab

## 2.6.0 → première édition publique 2.6.1

SQLite reste au **schéma 13**. Les changements sont la préparation Open Source : valeurs initiales neutres, Libre Franklin, ressources génériques, documentation et tests. Pas de changement fonctionnel métier intentionnel. Les réglages déjà enregistrés, les usagers, dossiers, inscriptions et fichiers persistants doivent être conservés.

Avant de quitter une ancienne distribution, vérifier que vos logos/signature sont dans le stockage privé `data/branding/` et référencés par les réglages. Les logos institutionnels et signatures qui provenaient de fichiers embarqués historiques ne sont pas redistribués. Sauvegarder ces fichiers dans votre espace privé et les importer via l'interface de structure si nécessaire ; le logiciel ne reconstitue pas les images ou coordonnées supprimées de ses constantes publiques. Il ne remplace pas vos valeurs enregistrées par des valeurs neutres.

## 2.5.x (schéma 12) → 2.6.x (schéma 13)

La migration normale est additive : paramètres de mode de réservation, table de créneaux et rattachement optionnel des inscriptions. Les animations existantes deviennent `whole`, sans créneau requis, et les inscriptions classiques ne sont pas déplacées.

1. Vérifier santé, version, espace et image/code de rollback ; construire la nouvelle image avant interruption si possible, sans monter les données actives dans un conteneur d'essai.
2. Vérifier la base en lecture seule, arrêter proprement, sauvegarder à froid l'ensemble des données et fichiers privés dans un dossier distinct.
3. Tester la migration sur une copie ; vérifier schéma, integrity, FK et conservation des données. Aucun essai sur l'unique copie réelle.
4. Installer le nouveau code en préservant `data/` et configuration privée. L'initialisation normale applique les migrations. Désactiver réseau/scheduler pour un contrôle avant exposition si votre orchestration le permet.
5. Vérifier santé, versions, rôles, dossiers/documents, réservations classiques, créneaux Test, synchronisation, puis redémarrage et sauvegarde post-mise à jour.

Installer d'abord le plugin Reservations 2.6.1 : il conserve le parcours classique avec un serveur 2.5.0, puis fournit `animation_slots_v1` au serveur 2.6.x. Ne pas changer les secrets pour une simple mise à jour.

## Retour arrière

Conserver l'état problématique pour analyse. Si des écritures métier ont eu lieu depuis la bascule, arrêter et définir une reprise explicite pour ne pas les perdre. Une ancienne version ne doit **jamais** recevoir une base de schéma plus récent. Restaurer uniquement sa sauvegarde froide cohérente et ses fichiers privés ; conserver les anciennes images/dossiers jusqu'à validation durable. Aucun nettoyage automatique n'est prévu.
