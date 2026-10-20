# OpenFabLab — Roadmap et conception

## Disponible en 2.11.0 stable

Présences automatiques des seuls inscrits confirmés, comptages anonymes distincts,
capacité unifiée, borne tactile et sons saisonniers complémentaires.
[Périmètre et limites](docs/evolution-2.11.0.md). Les projets historiques ci-dessous
restent conservés ; aucun paiement bancaire ni autre module nouveau n’est annoncé.

## Disponible en 2.10.1 stable

Correction des présentations par créneau, enrichissement sonore et compacité du
calendrier, sans refonte des moteurs. À partir de cette version, application et
plugin portent un numéro public commun. La compatibilité reste négociée par le
protocole et les capacités, indépendamment de l’égalité des numéros publics.
Voir [le guide 2.10.1](docs/corrections-2.10.1.md).

## Disponible en 2.10.0 stable

Le module facultatif Abonnements et crédits est livré et désactivé par défaut :
cotisations individuelles/familiales, droits de période, pass et crédits de
fréquentation, recharges, régularisations et historique. Notes privées du
calendrier, temporisation Discord et sons de borne configurables sont disponibles.
SQLite 21, plugin facultatif 2.9.0 inchangé. [Périmètre et règles](docs/evolution-2.10.0.md).
Il ne s’agit pas d’une plateforme de paiement ni d’un développement spécialisé
pour le coworking. Aucune intégration bancaire n’est annoncée.

## Disponible en 2.9.0 stable

Plafonds de liste d’attente configurables, affichages WordPress négociés par
`waitlist_limits_v1`, notification Discord de saturation, analyses privées de
fréquentation, catégories de clients et préavis facultatif avant effacement des
coordonnées. La stable inclut les cinq finitions ergonomiques et de persistance.
SQLite 20, plugin facultatif 2.9.0, protocole 4 / révision 3 ; les données et
réglages existants sont conservés. Voir [le guide 2.9.0](docs/evolution-2.9.0.md).
Le module Abonnements et crédits, absent de la 2.9.0, est disponible depuis la 2.10.0.

## Disponible en 2.8.6 stable — consolidation depuis 2.8.4

Cette version historique réunit les apports développés en 2.8.5 et les
corrections de 2.8.6 : gestion personnelle des réservations, modèles d'e-mails,
rattachement explicite aux comptes, recherche des communes/participants, exports
et guides multiplateformes ; recherches initialement vides et notifications
Discord enrichies sur choix explicite. SQLite 19, plugin facultatif 2.8.5,
protocole 4 / révision 3. Le moteur reste unique et le relais exclusivement
sortant. Voir [apports 2.8.5](docs/corrections-2.8.5.md), [corrections 2.8.6](docs/corrections-2.8.6.md)
et [mise à jour](docs/upgrade.md). Les évolutions futures ne sont pas incluses.

## Disponible en 2.8.4 stable — corrections et ergonomie

Formulaires simplifiés, autorisation temporaire du responsable familial révoquée après abandon d'une inscription, rattachement informatif mieux placé, réservations locales plus lisibles, réglages compacts, calendrier et répertoire des usagers ajustés. SQLite 18, badges pastel, plugin 2.8.2 et moteur de réservation conservés. Voir le [guide historique 2.8.4](docs/corrections-2.8.4.md). Ces corrections sont conservées dans la stable actuelle.

## Disponible en 2.8.3 stable — personnalisation et lisibilité

Badges pastel insécables et libellés longs accessibles, tableaux adaptés aux petits écrans, trois modes d'identifiant public, rattachement informatif à une structure, seuil de fréquentation configurable, dates Discord dans le fuseau local et détails de dossier autorisés dans le calendrier. Migration additive SQLite 17 → 18 ; plugin 2.8.2 et moteur de réservation inchangés. Voir le [guide 2.8.3](docs/usability-2.8.3.md).

## Disponible en 2.8.2 stable — compte facultatif, QR et badges pastel

Le parcours public sans compte devient une option de structure,
autorisée par défaut, sans création de fiche usager. Le parcours familial avec
compte reste inchangé et propose QR et saisie avec vérification de coordonnée.
Protocole 4/révision 3, SQLite 17, badges pastel calculés à partir des couleurs
configurées, couleur indépendante des visiteurs anonymes et catalogue public
harmonisé. Voir le [guide 2.8.2](docs/reservations-2.8.2.md).

## Disponible en 2.8.1 stable — intégration WordPress sortante

La version stable 2.8.1 remplace les appels WordPress → OpenFabLab du protocole 3 par un relais sortant protocole 4 : catalogue public reçu toutes les 90 secondes par défaut, demandes et résultats relevés toutes les 15 secondes (10 à 60 configurables). WordPress ne décide jamais des places. Les liens d’e-mail peuvent revenir vers une page WordPress protégée ; aucun accès entrant au NAS n’est nécessaire. Voir [le fonctionnement et les limites](docs/outbound-2.8.1.md).

Le modèle familial, les groupes indivisibles et la liste d’attente de 2.8.0 restent inchangés. Deux tables techniques sont ajoutées au schéma 16, sans conversion ni suppression de l’historique OpenFabLab. Le moteur historique WordPress et ses outils sont retirés ; ses cinq tables métier sont supprimées sous verrou uniquement si toutes sont vides, sinon elles restent intactes et inutilisées. L’application et le plugin 2.8.1 doivent être installés ensemble après sauvegarde et vérification de chaque installation ; un composant 2.8.0 ne négocie pas ce relais.

## Abonnements et crédits — périmètre livré depuis 2.10.0

La proposition initiale est désormais implémentée pour un usage FabLab générique.
Elle ne constitue plus un module entièrement à développer. Les retours des
structures pourront préciser de futures améliorations, sans engagement spécifique
envers un espace de coworking ni projet de paiement bancaire décidé.

- Cotisations annuelles individuelles ou familiales, abonnements individuels
  ou familiaux à durée limitée, renouvellements administratifs.
- Carnets de crédits (par exemple des demi-journées), rechargements et
  corrections auditables ; distinguer adhésion associative et consommation.
- Adhésion familiale commune sans fusionner les comptes individuels.
- Contrôle facultatif de validité/solde à l’identification : désactivé,
  avertissement ou refus de la **validation d’entrée**, jamais de l’identification
  elle-même. Les installations n’utilisant pas ce module restent inchangées.
- Réutilisation des usagers, familles, rattachements documentaires de facturation, fréquentation et
  permissions ; débits/remboursements transactionnels, audit et anti-double compte.

Pour mémoire, la 2.9.0 ne créait aucune table, interface, abonnement ni contrôle anticipé.
Ses catégories de clients sont informatives, ses identifiants techniques et
relations existantes sont conservés, et l’analyse de fréquentation reste en
lecture seule : aucun droit ni crédit n’est déduit implicitement de ces données.

## Familles, mineurs et comptes rattachés

Modèle disponible dans **OpenFabLab 2.8.0 stable**, validé le 5 octobre 2026. Il remplace la proposition initiale de profils enfants légers et d'accompagnateurs spécifiques. Les anciennes données restent lisibles ; les archives 2.7.1 ne changent pas.

### Référence historique : fonctionnement livré en 2.8.0

Cette section décrit la version précédente. Pour le plugin actuel, le relais sortant et le retrait de l'ancien moteur sont décrits ci-dessus : aucune liaison WordPress → NAS ni outil de nettoyage manuel historique n'est livré en 2.8.1.

- Chaque participant est un véritable compte OpenFabLab : identité, identifiant/QR, historique propre. Aucun compte collectif « famille » et aucune catégorie spéciale.
- Un compte peut être rattaché à plusieurs responsables. Les liens persistent à l'autonomie et au seuil de responsabilité ; leur fin manuelle reste tracée.
- Seuils et coordonnées configurables : initialement non autonome avant 15 ans, autonome dès 15 ans, responsable possible dès 18 ans. Ce sont des seuils métier, jamais une déclaration de majorité juridique.
- Réserver pour soi et/ou des membres rattachés. Un membre non autonome exige un responsable lié, éligible, sélectionné dans le même groupe/créneau.
- Une personne = une place : adulte + deux enfants = trois places. Un responsable non participant ne consomme aucune place, mais ne satisfait pas l'exigence de présence.
- Confirmation ou attente du groupe entier ; capacité, doublons, retrait/ajout contrôlés côté serveur. Présences individuelles.
- Attente automatique FIFO compatible avec la capacité, places temporairement proposées pour le groupe entier, réponse personnelle et expiration. Courriels natifs OpenFabLab, sans validation manuelle normale ni seconde file WordPress.
- E-mail valide obligatoire pour les inscriptions ; téléphone configurable séparément. Contact du responsable lié possible sans copie sur l’enfant.
- OpenFabLab devient l'autorité transactionnelle commune borne/administration/plugin 2.8. WordPress reste facultatif, simple relais HTTPS signé, sans annuaire familial répliqué. Il doit joindre OpenFabLab ; la borne fonctionne sans WordPress.
- Ancien accompagnateur : lecture historique seulement, aucune conversion, suppression ou invention de rattachement.
- Migration additive 14 → 15 avec PRE cohérente, sauvegardes/restauration, données anciennes conservées.
- Le nettoyage manuel concerne **exclusivement les anciennes tables du plugin WordPress**, après sauvegarde/confirmation. Jamais les animations, réservations passées, statistiques ou factures OpenFabLab.

L'interface reste progressive : animation, identification, personnes, créneau, récapitulatif, confirmation/attente. Pas d'annuaire public, pas de date de naissance dans le catalogue ou les choix WordPress, droits serveur et autorisations courtes. L'administration montre les personnes et l'appartenance à une même demande, avec liens vers les responsables selon les droits existants.

Voir [la conception](docs/families-2.8.md) et [le guide d'essai](docs/candidate-2.8-guide.md).

### Points de vigilance et évolutions à étudier

1. Vérifier sur chaque installation la délivrabilité du SMTP natif et les liens HTTPS personnels. Les propositions/réponses/expirations sont livrées ; les tests automatisés simulent les transports. Les anciens rappels d'avant-animation restent historiques, sans relance supplémentaire ajoutée.
2. Vérifier les contraintes HTTPS/hébergement/cache de chaque WordPress. Le contact signé de 2.8.0 ne prouvait pas le fonctionnement du parcours public : celui-ci exigeait une liaison entrante vers OpenFabLab. La 2.8.1 corrige cette dépendance par un relais sortant ; le parcours complet reste à vérifier sur chaque installation cible.
3. Préciser les durées de conservation et procédures d'export/effacement des liens, dates et historiques privés. Terminer un lien n'efface pas les données métier.
4. Évaluer un moyen d'identification renforcée (code à usage unique, QR privé, etc.) : la concordance ID/contact ne prouve pas une autorité parentale. Aucune gestion publique arbitraire des rattachements.
5. Décider plus tard d'une extension aux autres personnes liées, sans fusionner leurs comptes.

### Évolutions ultérieures, non disponibles en 2.8.3

Réutiliser les seuils/responsabilités pour les machines et autres ressources, avec habilitations et contraintes propres à chaque ressource. Ne pas déduire une autorisation machine du seul lien familial. Une notion générale de compte Famille reste éventuelle, jamais une fusion d'historiques.

### Critères d'acceptation

Tester adulte seul, adulte/enfant, plusieurs enfants/responsables, autonomie à date précise ou année historique, seuils personnalisés, responsable manquant/non lié/inactif, capacités/attente indivisibles, concurrence, doublons et reprise après réponse perdue. Tester borne sans WordPress, relais WordPress, administration/modération, anciens accompagnateurs, migration et restauration de copie privée, clavier/tactile et petits écrans Chromium/WebKit. Aucun envoi ni donnée fictive en production.
