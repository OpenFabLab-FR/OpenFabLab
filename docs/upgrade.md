# Mettre à jour OpenFabLab

## 2.6.2 → 2.6.3

SQLite reste au **schéma 13**. Seuls six réglages manquants sont ajoutés : DPO libre, e-mail/téléphone DPO, utilisation du logo complémentaire, de la signature et du badge privé. Les trois cases sont activées par défaut pour conserver l’apparence actuelle. Les réglages existants, même vides ou désactivés, restent prioritaires ; aucun fichier privé n’est effacé. Des anciennes clés DPO explicites peuvent être reprises, jamais l’e-mail général ni des valeurs institutionnelles prédéfinies.

Sauvegarder à froid le dossier de données complet et la configuration, tester l’initialisation normale sur une copie isolée puis préserver ce même `data` pour la nouvelle image. Vérifier santé, SQLite, contenu métier, ressources, réglages DPO et profil privé avant remise en service. Ne rejouer aucune migration historique ou migration PIN. Le plugin Reservations reste 2.6.1.

Lorsqu’un paquet de mise à jour automatisé est préparé pour l’installation, privilégier une seule commande avec contrôles préalables, sauvegarde, essai isolé, bascule, vérifications et rollback prudent. Une migration plus complexe peut nécessiter des étapes supplémentaires. Ne jamais restaurer automatiquement une sauvegarde si cela risque de perdre de nouvelles écritures métier.

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
# Mise à jour 2.6.1 → 2.6.2

Le schéma reste 13. Ne rejouer aucune migration historique ni migration PIN. Sauvegarder la base à froid, tout `data`, `.env`, compose et l’image précédente ; préparer l’image avant interruption. Les nouvelles clés de logos/RGPD sont ajoutées sans écraser les réglages existants. Les ressources privées ne sont pas incluses dans le ZIP public et doivent rester persistantes. Après mise à jour, comparer les données métier, vérifier santé, identité, badges et documents. Ne revenir à l’ancienne sauvegarde qu’avant de nouvelles écritures métier ; sinon conserver l’état et décider explicitement. Voir [Branding](branding.md).
