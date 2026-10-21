# Maintenance pratique d’OpenFabLab

Ce guide s’applique aux installations Linux, Raspberry Pi 64 bits, Windows via
les environnements documentés et Synology. Les chemins sont ceux de **votre**
installation. Ne copier aucune commande privée d’une autre structure.

## Lire l’état sans modifier les données

Connectez-vous comme administrateur : Réglages → Données → État de l’installation.
Comparez la version et le schéma avec les guides de votre release. Une donnée
indisponible n’est pas un diagnostic de panne. Les observations de WordPress sont
datées ; une configuration enregistrée seule ne prouve pas une synchronisation.
Gardez les rapports techniques privés : ils peuvent contenir des informations sensibles.

## Installer une version et comprendre le contrôle préalable

**Sauvegarde nécessaire avant toute modification.** Lire [mise à jour](upgrade.md),
notes de version et empreintes SHA-256. Un contrôle préalable vérifie la source,
la base, les volumes et les ressources sans déployer. Un refus protège l’installation :
ne pas désactiver le contrôle, comprendre le rapport. Préserver configuration,
volumes, secrets et ancien runtime. 2.11.0 → 2.12.0 conserve SQLite 22 ; aucune
migration 21 → 22 à rejouer. Les scripts privés ne sont jamais exécutés par le logiciel.

## Sauvegarder

Réglages → Données : une sauvegarde SQLite seule contient les données métier,
pas tous les fichiers de configuration. Préférer la **sauvegarde complète privée**
pour un secours intégral ; protéger l’archive et son accès, garder aussi votre
configuration de serveur et le runtime/image exact. Une copie pour test contient
encore des données personnelles : ce n’est pas une anonymisation.

## Vérifier une sauvegarde

Contrôler ses empreintes et son format avec les outils génériques documentés dans
[sauvegarde/restauration](backup-restore.md). Vérifier l’intégrité et les références
SQLite sur une copie. **Un ZIP valide ou un fichier présent ne prouve pas une restauration.**
Faire périodiquement un essai de restauration isolé et constater des données connues,
les réglages, le schéma et la santé HTTP avant de considérer ce secours exploitable.

## Restaurer pour un essai

**Ne remplacez jamais le dossier de production.** Utiliser un nouveau dossier et
un port distincts ; bloquer les communications sortantes **avant le premier import
ou démarrage** : SMTP, Discord et WordPress ne doivent pas joindre de destinataires.
Utiliser les mécanismes de copie pour test existants et les réglages d’isolation
du guide de sauvegarde. Ouvrir avec un runtime compatible avec le schéma restauré,
vérifier les données puis supprimer seulement le dossier d’essai explicitement identifié.

## Si le logiciel ne démarre plus

Ne pas multiplier les migrations ou restaurations. Conserver l’état et les rapports,
vérifier espace disque, droits des volumes, image réellement lancée et erreur de
démarrage. Une étiquette Docker ne prouve pas la version de son contenu. Après un
démarrage public, sauvegarder les nouvelles écritures avant toute décision humaine
de retour arrière. Ne jamais ouvrir une base plus récente avec un ancien runtime.

## Si WordPress ne synchronise plus

Vérifier module actif, date du dernier relevé authentifié Normal/Test, URL HTTPS,
certificats, accès sortant, versions et protocole/capacités. Ne pas ouvrir de port
entrant vers OpenFabLab et ne pas changer les secrets au hasard. Les anciennes
commandes sans date d’envoi ne sont pas toutes bloquées. Ne pas vider la file ni
rejouer les réservations : reçus et acquittements préviennent les doubles effets.
Voir [WordPress](wordpress.md) et [diagnostic des états](consolidation-2.12.0.md).

## Si SMTP ou Discord ne partent plus

Vérifier les options de l’événement, le module et les services activés, les échéances
de temporisation, le réseau sortant et le fournisseur. Ne pas afficher ni copier
les secrets dans les rapports partagés. Un envoi d’essai doit être volontaire,
vers un destinataire autorisé ; les tests automatisés utilisent des transports simulés.
Éviter les relances manuelles répétées lorsque la réception est incertaine.

## Si une sauvegarde automatique échoue

Vérifier le dernier essai et dernier succès connus, espace disponible, montage du
dossier, permissions et quota. Faire une sauvegarde privée manuelle puis vérifier
sa restauration isolée. Ne pas supprimer la dernière bonne sauvegarde pour faire
de la place sans autre copie. La présence d’un fichier ne prouve pas sa cohérence.

## Comprendre les schémas

La version applicative et le schéma sont distincts. 2.10.1 utilise 21 ; 2.11.0 et
2.12.0 utilisent 22. La migration additive 21 → 22 conserve les données historiques.
Une migration interrompue doit être diagnostiquée, pas relancée aveuglément.
La suite `tests/test_migration_restore.py` vérifie installation, conservation,
idempotence, exception transactionnelle, refus d’un schéma futur et restauration
isolée sur données fictives. Elle ne remplace pas la sauvegarde de chaque structure.

## Déplacer l’installation

**Sauvegarde et interruption planifiée nécessaires.** Préparer un serveur compatible,
installer le même runtime et restaurer dans un nouvel emplacement isolé. Reprendre
les volumes, paramètres, fichiers privés, droits et URL selon les guides de plateforme.
Vérifier intégrité, schéma, données, documents et sauvegardes. Un seul serveur maître
doit synchroniser un WordPress donné : ne jamais activer simultanément les sorties
de l’ancienne installation et de la nouvelle. Ne basculer le trafic qu’après validation.

Les restaurations modifient les données ; les diagnostics ci-dessus restent en
lecture seule. Les procédures de secours propres à une structure sont privées.
