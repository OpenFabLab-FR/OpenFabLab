# OpenFabLab — Roadmap et conception

## Familles, mineurs et comptes rattachés

Modèle disponible dans **OpenFabLab 2.8.0 stable**, validé le 5 octobre 2026. Il remplace la proposition initiale de profils enfants légers et d'accompagnateurs spécifiques. Les anciennes données restent lisibles ; les archives 2.7.1 ne changent pas.

### Fonctionnement livré en 2.8.0

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
2. Vérifier les contraintes HTTPS/hébergement/cache de chaque WordPress. Le protocole 2.8 et sa liaison au NAS ont été validés en conditions réelles au FougèresLab ; cela ne couvre pas tous les hébergements.
3. Préciser les durées de conservation et procédures d'export/effacement des liens, dates et historiques privés. Terminer un lien n'efface pas les données métier.
4. Évaluer un moyen d'identification renforcée (code à usage unique, QR privé, etc.) : la concordance ID/contact ne prouve pas une autorité parentale. Aucune gestion publique arbitraire des rattachements.
5. Décider plus tard d'une extension aux autres personnes liées, sans fusionner leurs comptes.

### Évolutions ultérieures, non disponibles en 2.8.0

Réutiliser les seuils/responsabilités pour les machines et autres ressources, avec habilitations et contraintes propres à chaque ressource. Ne pas déduire une autorisation machine du seul lien familial. Une notion générale de compte Famille reste éventuelle, jamais une fusion d'historiques.

### Critères d'acceptation

Tester adulte seul, adulte/enfant, plusieurs enfants/responsables, autonomie à date précise ou année historique, seuils personnalisés, responsable manquant/non lié/inactif, capacités/attente indivisibles, concurrence, doublons et reprise après réponse perdue. Tester borne sans WordPress, relais WordPress, administration/modération, anciens accompagnateurs, migration et restauration de copie privée, clavier/tactile et petits écrans Chromium/WebKit. Aucun envoi ni donnée fictive en production.
