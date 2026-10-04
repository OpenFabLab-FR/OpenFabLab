# Mettre à jour OpenFabLab

## 2.7.0 → 2.7.1

SQLite reste au **schéma 14** et Reservations au **2.7.0**. L’initialisation normalise les ordres des catégories et initialise l’ordre des habilitations dans la configuration existante. Elle ajoute l’option de demandes d’animations depuis la borne, désactivée par défaut, et remplace une fois l’ancienne cadence de deux minutes par 1,5 minute ; les autres intervalles personnalisés sont préservés. Elle ne migre pas les données métier, ne remplace pas les ressources privées et ne modifie pas les PIN ou les secrets. Les nouvelles ressources et catégories restent configurées par la structure, sans valeurs institutionnelles imposées. Les demandes publiques utilisent l’outbox existante, sans nouvelle table.

Conserver une sauvegarde complète privée et le runtime précédent. Tester la nouvelle version avec une copie privée de test isolée, puis contrôler santé, intégrité/FK, données, droits, catégories, ressources et branding. Ne rejouer aucune migration historique. OpenFabLab 2.7.1 est stable et a été déployé en conditions réelles au FougèresLab ; cette validation ne dispense pas des contrôles sur chaque installation. Voir [les corrections](corrections-2.7.1.md).

Les configurations de production, fichiers privés et intégrations doivent être conservés. Ne jamais importer une base de test ou ses protections dans la production. Reservations 2.7.0 reste inchangé : aucun redéploiement WordPress nécessaire pour cette seule mise à jour. Après de nouvelles écritures, ne restaurer aucune sauvegarde PRE automatiquement : conserver l’état courant et décider d’une reprise explicite.

## 2.6.x / schéma 13 → 2.7.0 / schéma 14

Le persistant complet, pas seulement SQLite, doit être sauvegardé avant migration.
Le [format privé complet](private-backup.md) distingue production et copie de test
neutralisée. Les paquets d'exploitation privés peuvent automatiser préflight,
build avant interruption, PRE/POST complets, essai hors réseau, migration,
validation et rollback avant exposition en une seule commande. Après exposition
potentiellement suivie d'écritures, aucune ancienne sauvegarde n'est restaurée
automatiquement. Les chemins et scripts propres à une infrastructure restent
privés ; ils ne font pas partie de la distribution publique.

Le plugin associé est **Reservations 2.7.0**, sans changement de schéma WordPress. Les anciennes clés de catégories et leurs affectations restent conservées. Le mécanisme normal migre transactionnellement et crée aussi une copie SQLite pré-initialisation ; celle-ci ne remplace pas une sauvegarde complète.

1. Relever version, schéma et état du service. Contrôler la base en lecture seule et vérifier l’espace disponible.
2. Conserver l’image/code 2.6.x, Compose, configuration et chemins de montage. Préparer la nouvelle image avant interruption lorsque possible ; la tester avec une base vierge, sans réseau ni workers.
3. Arrêter proprement puis sauvegarder **tout le persistant** : SQLite, PIN dérivés, clé Flask, secrets, branding, profils et autres fichiers privés. Sur 2.6.x, copier le dossier complet à froid puisque son interface ne propose pas encore le nouveau format. Conserver cette sauvegarde schéma 13 sans la modifier.
4. Tester la migration normale sur une copie isolée. Pour une migration hors ligne, désactiver les workers et actions externes et n’exposer aucun port public. Ne pas forcer `user_version` manuellement ni rejouer des migrations historiques/PIN.
5. Vérifier schéma 14, intégrité, clés étrangères, conservation des données et réglages, puis mettre en service avec le même persistant. Contrôler HTTP/HTTPS, droits, modules et ressources privées.
6. Après validation et redémarrage, créer une sauvegarde complète privée schéma 14, distincte de l’état schéma 13.

Contrôles SQLite avant et après :

```sql
PRAGMA user_version;
PRAGMA integrity_check;
PRAGMA foreign_key_check;
```

Attendus : 13 avant, 14 après ; `ok` ; aucune ligne FK. Comparer aussi les données métier : l’intégrité ne prouve pas à elle seule leur conservation.

**Ne jamais démarrer 2.6.x avec une base schéma 14.** Un rollback exige la sauvegarde froide **schéma 13 correspondante**, ses fichiers privés et son runtime. Après exposition ou écritures de workers, ne pas restaurer automatiquement cet état ancien : préserver la base 14 et décider explicitement de la reprise pour éviter une perte de nouvelles données. Voir [nouveautés et contrôles d’essai](evolution-2.7.md).

Pour les déploiements, privilégier lorsque raisonnable un paquet privé préparé, une commande ponctuelle, contrôles automatisés, sauvegarde, rollback prudent et rapport lisible. La distribution publique ne contient pas les scripts ni chemins propres à une infrastructure ; une migration complexe peut nécessiter une procédure distincte.

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
