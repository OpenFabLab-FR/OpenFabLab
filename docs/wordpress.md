# OpenFabLab Reservations 2.7.0

**Plugin WordPress Reservations : version 2.7.0 inchangée, compatible avec OpenFabLab 2.7.1.** Un plugin 2.7.0 déjà en place n’a pas à être réinstallé pour mettre à jour l’application. WordPress reste facultatif pour l’ensemble du logiciel ; la fonction de demandes d’animations depuis la borne de la 2.7.1 nécessite cependant ce moteur configuré pour confirmer les inscriptions. Le dépôt local hors Internet conserve une demande en attente, jamais une place garantie. [Fonctionnement de la borne](corrections-2.7.1.md).

Installer le ZIP autonome `openfablab-reservations-2.7.0.zip` dans **Extensions → Ajouter → Téléverser**, puis activer, après un essai sur un **WordPress séparé**. La source est dans `wordpress/openfablab-reservations/`. Le plugin conserve réservations, créneaux, e-mails et maintenance Test, sans migration supplémentaire de schéma depuis le plugin 2.6.1. Il ajoute réconciliation, diagnostics et actualisation au prochain passage sortant du serveur. La purge confirmée porte uniquement sur la configuration reconstruisible, jamais les transactions. Voir [le protocole et ses limites](evolution-2.7.md).

## Connexion

Dans WordPress **Réglages → OpenFabLab Reservations**, configurer les options du plugin et conserver le secret dans son stockage privé. Dans OpenFabLab **Réglages → Structure et modules → Réservations publiques**, renseigner **la racine HTTPS du site**, par exemple `https://example.invalid` (exemple non fonctionnel), et exactement le même secret. OpenFabLab ajoute les routes REST `/wp-json/openfablab/v1/...` : ne pas saisir cette route comme URL racine.

Enregistrer URL/secret avant d'activer le module. Ne jamais afficher le secret dans des logs ou captures. Une seule instance OpenFabLab synchronise ce site ; conserver le module désactivé dans les autres installations locales. Intervalle initial : **1,5 minute (90 secondes)**. La première initialisation 2.7.1 remplace l’ancienne cadence de deux minutes ; les autres valeurs personnalisées restent inchangées. Demi-minutes acceptées entre 1 et 60 minutes. Les réveils du worker, le transport et le traitement s’ajoutent : aucun délai maximal garanti. Tester la connexion puis « Synchroniser maintenant » lorsque la configuration est cohérente. Voir les [demandes de la borne et leurs limites](corrections-2.7.1.md).

Le sens réseau est **OpenFabLab → HTTPS signé HMAC → WordPress** : aucun port entrant dédié ni ouverture Internet vers le serveur OpenFabLab n’est requis. WordPress ne se connecte pas au serveur pour déclencher une synchronisation.

## Protocole 2, réconciliation et diagnostics

Le plugin annonce `protocol_version: 2`, `animation_slots_v1`, `catalog_snapshot_v1` et `custom_categories_v1`. Les capabilities sont négociées ; un ancien plugin conserve le parcours incrémental compatible, sans bénéficier des nouvelles fonctions de catalogue/catégories.

Avec `catalog_snapshot_v1`, OpenFabLab transmet l’état actuel du catalogue de l’environnement. WordPress applique une réconciliation transactionnelle, masque les animations absentes et conserve les réservations, événements et tokens. Une modification incompatible avec un créneau réservé est refusée, jamais appliquée silencieusement. La capacité continue à compter les réservations WordPress récentes.

Les commandes de catalogue sont recalculées depuis l’état courant et les suppressions nécessaires traitées en priorité. Les actions de réservation gardent leur ordre. Seul un accusé positif valide une commande ; après une erreur, elle reste rejouable. La pagination et le curseur sont contrôlés, avec un état indépendant pour Test et Normal.

OpenFabLab distingue **dernière tentative**, **dernière réussite**, erreur, commandes en attente et version du protocole/plugin. WordPress distingue le dernier contact signé de la réussite de son cycle : celle-ci ne prouve pas à elle seule l’import SQLite. « Actualiser » côté WordPress est traité au prochain passage sortant du serveur ; « Synchroniser maintenant » côté OpenFabLab lance ce passage.

La **purge/resynchronisation du catalogue** exige Administrateur WordPress, POST, nonce, réconciliation 2.7 préalable et confirmation `RESYNCHRONISER TEST` ou `RESYNCHRONISER PRODUCTION`. Elle masque uniquement le catalogue et vide son annuaire reconstruisible dans l’environnement choisi. Réservations, événements et tokens sont préservés ; le prochain passage reconstruit la configuration. Ce mécanisme est distinct de la maintenance d’inscriptions Test décrite plus bas.

Les tests automatiques couvrent ces parcours avec des données fictives. Ils ne prouvent pas le fonctionnement de toutes les combinaisons WordPress, hébergement, cache ou moteur SQL : vérifier votre propre installation et la concurrence InnoDB avant une bascule.

## Pages et environnements

Placer un shortcode dans une page choisie par votre structure :

```text
[openfablab_reservations environment="test"]
[openfablab_reservations environment="production"]
```

Test et Normal sont isolés, y compris animations, réservations et capacités. La valeur technique de Normal reste `production`. Chaque animation publique indique son environnement ; aucune activation globale supplémentaire du mode Normal n'est nécessaire. Une bascule depuis un autre outil nécessite de préparer les animations publiées dans le bon environnement et de décider explicitement du remplacement de l'ancien outil/page. Ne pas créer deux parcours concurrents involontaires.

## Identification et données

La vérification demande identifiant usager actif et au moins un contact concordant. Avant concordance : aucune identité nominative ; après : identité masquée puis préremplissage modifiable. La réservation finale exige prénom, nom, année, e-mail **et** téléphone. Modifier la réservation ne modifie pas la fiche maître.

L'annuaire privé WordPress contient les données nécessaires des usagers actifs, avec empreintes HMAC des contacts. Aucun listing public ni donnée nominative injectée dans le HTML initial. Les contrôles et limitations de fréquence ne constituent pas une vérification par code e-mail/SMS ; informer les usagers de ce compromis et protéger le stockage.

## Créneaux et e-mails

Les créneaux nécessitent OpenFabLab 2.6.x et la capability `animation_slots_v1`. Avec OpenFabLab 2.5.0, le fonctionnement classique reste compatible. Voir [créneaux](animation-slots.md) et [modèles d'e-mails](email-templates.md).

## Maintenance Test

**Outils de données Test** exige administrateur WordPress, nonce, POST et environnement `test` vérifié côté serveur. Diagnostic, sélection individuelle non précochée, prévisualisation et confirmation textuelle `PURGER TEST <service_id>` précèdent l'annulation locale des réservations explicitement déclarées orphelines. Historique et animation sont conservés ; pas d'e-mail, événement NAS parasite ou promotion de file. Production est refusé. Ne pas rejouer une ancienne maintenance déjà effectuée.

Cette fonction n'est pas une purge générale ni une manière d'annuler une vraie réservation connue du serveur. Vérifier IDs, dates et provenance avant toute opération.
