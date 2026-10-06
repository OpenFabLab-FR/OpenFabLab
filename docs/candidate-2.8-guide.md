# Vérifier OpenFabLab 2.8.1 dans une installation isolée

OpenFabLab 2.8.1 est la version stable actuelle. Ce guide garde son chemin historique pour les liens existants et décrit les essais **avant** une mise à jour, sans toucher à la production ni aux sauvegardes originales. Voir [installation](installation.md), [mise à jour](upgrade.md) et [relais sortant](outbound-2.8.1.md).

## Installation d'essai

Extraire l'archive dans un dossier neuf. Employer un environnement Python et un persistant **distincts** de la production. Définir `OPENFABLAB_DATABASE` vers la base d'essai, `OPENFABLAB_SECRET_KEY_FILE` vers sa clé privée, **`OPENFABLAB_EXTERNAL_ACTIONS=0`**, `OPENFABLAB_ENABLE_SCHEDULER=0` et `OPENFABLAB_ENABLE_WEATHER=0`. Le premier paramètre de protection interdit les connexions externes, y compris SMTP/Discord/WordPress ; désactiver seulement le planificateur ne suffit pas. Utiliser une copie privée pour test neutralisée, jamais la sauvegarde originale. Lancer avec l'interpréteur de l'environnement : `python app.py`. Pour un essai limité à cet ordinateur, préférer un lanceur liant le serveur à `127.0.0.1` ; le lanceur historique de développement écoute aussi le réseau local.

Depuis une copie 2.8.0, le premier démarrage migre SQLite 15 → 16 de façon additive. La copie automatique dans `migration-backups` ne remplace pas une sauvegarde complète privée PRE 15. Ne démarrer aucun ancien runtime sur la base 16. Un retour vers 2.8.0 exige la PRE 15 et ses fichiers privés, installation arrêtée ; après de nouvelles écritures, sauvegarder l'état courant et demander une décision humaine.

## Parcours à vérifier

1. **Réglages → Usagers** : seuils initiaux 15/18, cinq choix de coordonnées, catégories compactes, couleurs et ordre.
2. Créer un responsable avec les coordonnées exigées, puis deux vrais comptes mineurs avec dates complètes et rattachements. Recherche ciblée du responsable, liens réciproques ; terminer un lien ne supprime ni compte ni historique.
3. Activer la borne, créer une animation fictive, identifier le responsable par ID/contact connu et sélectionner adulte + deux enfants : **trois places**. Avec deux places libres, attendre tout le groupe. Sans responsable lié, refuser.
4. Tester adolescent autonome seul, seuils personnalisés, plusieurs responsables, doublons et créneaux. Âge à la date de l'animation : date précise si connue, méthode historique par année sinon.
5. Administration/Modération : participants distincts, demande commune, ajout/retrait contrôlé, propositions temporaires distinctes des confirmations, présence individuelle. Anciennes inscriptions avec accompagnateur toujours lisibles.
6. **Borne** : titre limité à 40 caractères ; lien « Gestion » vers la page intermédiaire avec accès publics sans PIN. Le footer de l'accueil masque uniquement « Gestion des données » ; les autres pages conservent ce lien et l'espace protégé reste nommé « Administration ».
7. Calendrier : semaine/mois, titres longs, détails, couleurs dans Affichage, masquage d'une occurrence et Afficher les masqués. OpenLab passé terminé sans présence masqué ; une présence historique le fait réapparaître, sauf masquage manuel.
8. Journée : noms longs et correction des sessions. Bienvenue : une seule pièce jointe `OpenFabLab-QR.png`. Aucun envoi réel pendant les tests automatisés.
9. Sauvegarde complète et restauration dans un second dossier : schéma 16, intégrité/FK, comptes, liens, branding, PIN et réglages. Tester aussi le retour contrôlé au runtime 2.8.0 avec la PRE 15 correspondante.
10. Dans la copie fictive, annuler toutes les inscriptions d'une animation, vérifier zéro place active puis confirmer sa suppression avec SUPPRIMER. Contrôler la disparition de ses seules dépendances et la conservation des autres dossiers. Une animation jamais inscrite est également supprimable ; une inscription active, une attente, une proposition ou une facturation liée doit produire un refus explicite.

## Plugin WordPress : essai séparé seulement

Le ZIP 2.8.1 final facultatif doit être essayé sur un WordPress **non productif**. Configurer dans OpenFabLab l'adresse HTTPS du site WordPress et le secret privé partagé existant. Aucune URL publique OpenFabLab ni connexion entrante vers le NAS n'est nécessaire. WordPress attend le premier catalogue ; OpenFabLab relève les demandes toutes les 15 secondes par défaut, séparément du catalogue (90 secondes). Aucun annuaire familial public ; après identification, choix temporaires opaques ; validation et places dans OpenFabLab. Sans liaison, aucune confirmation WordPress. Les comptes sans contact connu passent par leur responsable éligible ou l'équipe : le seul ID ne donne pas accès aux familles.

Sauvegarder WordPress avant l'installation. Le moteur historique et son outil de nettoyage manuel ne sont plus livrés. L'installation retire ses cinq tables métier uniquement si elles sont toutes vides, sous verrou ; dès qu'une table contient des données, toutes restent intactes et inutilisées. Le catalogue, la file du relais et les nonces sont conservés. **Ne supprimer aucune animation, réservation passée, statistique ou facture OpenFabLab.** Tester la séparation stricte Normal/Test, les reprises après interruption, les doublons et les liens d'e-mail : un GET ne doit provoquer aucune action métier.

## Essayer la liste d’attente sans envoi réel

Créer uniquement des comptes et animations fictifs dans la copie protégée. Remplir
une animation de quatre places, puis déposer un groupe de trois et un groupe d’une
personne. Libérer deux places : seul le groupe d’une personne reçoit une proposition,
celui de trois garde sa priorité. Vérifier les places proposées dans l’administration.
Les tests automatisés simulent SMTP et suivent le lien personnel, puis acceptent,
refusent ou font expirer la proposition ; ils vérifient aussi la concurrence et les
reprises après erreur. Ne pas retirer les protections d'une copie privée pour
envoyer ces messages : ses coordonnées réelles ne sont pas des destinataires de test.

Dans une installation d’essai entièrement fictive et explicitement autorisée à
communiquer, configurer un SMTP fictif et le relais WordPress HTTPS d'essai, puis laisser le
traitement local automatique fonctionner. Les liens personnels reviennent vers WordPress,
jamais vers le NAS en mode relais. Sans SMTP ni liaison WordPress validée pour l'environnement,
le message reste préparé en attente ; aucune livraison n’est annoncée. Le schéma
conserve les demandes et reprises. Voir [les règles et délais](families-2.8.md).

## Limites de validation externe

- Propositions, réponses, expirations et e-mails natifs sont intégrés et testés avec transports fictifs. La délivrabilité réelle dépend du SMTP et de la page personnelle HTTPS WordPress ; aucun message réel n’est envoyé pendant cette préparation.
- Plugin refondu : JavaScript et WordPress accessible en HTTPS nécessaires ; aucune exposition publique OpenFabLab. La borne reste utilisable sans JavaScript ni WordPress.
- Transitions d'âge : vérification quotidienne à la première activité équipe ; Discord configuré/autorisé requis. Un envoi incertain n'est pas répété automatiquement.
- Les suites PHP publiques simulent WordPress/SQL ; des validations complémentaires antérieures du relais utilisent aussi un vrai WordPress/MariaDB isolé et Chromium/WebKit. Aucun build Docker réel n'est revendiqué sur un poste où Docker est indisponible.
- Le déploiement NAS 2.8.1, son relais et le correctif de suppression ont été validés par l'exploitant du FougèresLab. La publication ne modifie pas cette production : vérifier le service, les volumes et le parcours WordPress sur chaque autre installation cible avant ouverture aux utilisateurs.

Voir [le modèle familial](families-2.8.md) et [les résultats publics](development.md). Les empreintes des archives approuvées figurent dans le `SHA256SUMS` joint à la release. Les copies privées, rapports d'exploitation et captures nominatives ne sont pas distribués.

## Dernière harmonisation visuelle

Titres internes plus légers, champs numériques en taille standard et graisse normale,
unités alignées (euros, âges, durées), tableaux contenus sur tablette et formulaire
de devis corrigé sur mobile WebKit. Les grands titres de page et compteurs d’accueil
gardent leur hiérarchie. « Règles par défaut » donne un accès direct au réglage
« Âges, autonomie et familles ». Aucune règle métier ni permission ne change.
