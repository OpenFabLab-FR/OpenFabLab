# OpenFabLab Reservations 2.6.1

Installer le ZIP autonome `openfablab-reservations-2.6.1.zip` dans **Extensions → Ajouter → Téléverser**, puis activer le plugin. La source est également dans `wordpress/openfablab-reservations/`. Cette distribution publique ajoute la licence MIT complète et les notices ; son runtime reste celui de Reservations 2.6.1.

## Connexion

Dans WordPress **Réglages → OpenFabLab Reservations**, configurer les options du plugin et conserver le secret dans son stockage privé. Dans OpenFabLab **Réglages → Structure et modules → Réservations publiques**, renseigner **la racine HTTPS du site**, par exemple `https://example.invalid` (exemple non fonctionnel), et exactement le même secret. OpenFabLab ajoute les routes REST `/wp-json/openfablab/v1/...` : ne pas saisir cette route comme URL racine.

Enregistrer URL/secret avant d'activer le module. Ne jamais afficher le secret dans des logs ou captures. Une seule instance OpenFabLab synchronise ce site ; conserver le module désactivé dans les autres installations locales. Intervalle initial : **2 minutes**, une valeur personnalisée reste inchangée. Tester la connexion puis « Synchroniser maintenant » lorsque la configuration est cohérente.

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
