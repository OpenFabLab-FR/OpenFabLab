# OpenFabLab 2.8.4 — version stable

Cette livraison repose exclusivement sur la stable 2.8.3. Elle ne modifie ni le moteur transactionnel des places, ni le relais sortant, ni les badges pastel.

## Formulaires et réservations locales

- Création publique plus courte, identifiant proposé sur sa propre ligne dans les modes visible et personnalisable, nom puis prénom ; les trois modes et les zéros initiaux restent conservés.
- Rattachement à une structure placé après les informations familiales dans les formulaires de l'équipe. Il reste facultatif et informatif. Aucun répertoire de clients n'est exposé dans le formulaire public.
- Catalogue local, identification et récapitulatif moins bavards, descriptions compactes, nombre de places au singulier ou au pluriel. « Recommencer » repart réellement de l'identification ; créer un compte n'est proposé que si l'inscription publique est autorisée.
- Réglage de fréquentation compact et dates de la vue hebdomadaire légèrement réduites. Vue mensuelle, couleurs et capacités inchangées.
- Répertoire et fiche usager : libellé « Auto-inscription », plus adapté aux différents appareils, et espacement entre la date et l'origine. Les valeurs techniques de provenance, dates, historiques et exports ne changent pas.

## Confidentialité sur un appareil partagé

L'autorisation temporaire du responsable est liée au formulaire actif, pas à une session générale réutilisable. Une nouvelle inscription, une sortie vers une autre page, une annulation explicite, l'expiration (quinze minutes) ou la création du compte la révoquent côté serveur. Un ancien cookie signé ne permet pas de reprendre une autorisation révoquée.

Le navigateur nettoie les champs en quittant le formulaire et vérifie l'état de son document lors d'un retour depuis son cache. Recharger repart d'un formulaire neuf. Une correction ou une vérification du responsable dans le même formulaire conserve les données nécessaires ; une fois le compte créé, ses liens permanents ne sont pas supprimés.

Le nettoyage différé des champs restaurés par le navigateur respecte les nouvelles saisies de l'utilisateur. Il ne vide pas une inscription en cours simplement parce que l'affichage d'une image est retardé.

Le registre existant `family_api_nonces` reçoit uniquement des empreintes temporaires préfixées `enrollment:` et une expiration : ni nom, ni coordonnée, ni jeton brut. La consommation de l'autorisation est dans la transaction de création du compte. Aucun stockage personnel dans `localStorage` ou `sessionStorage`.

Il faut fermer le formulaire ou revenir à l'accueil après usage ; aucun logiciel ne peut rendre invisible un écran personnel laissé ouvert devant quelqu'un. Si JavaScript est désactivé, la révocation serveur reste appliquée à la navigation et aux nouvelles inscriptions, mais l'effacement instantané d'un ancien écran dans le cache du navigateur n'est pas garanti.

Si la fermeture intervient sans connexion, l'avis d'abandon peut ne pas atteindre le serveur immédiatement. Une nouvelle ouverture du formulaire révoque l'ancienne autorisation ; sinon, sa durée maximale reste de quinze minutes. La fermeture du navigateur ne peut pas être détectée instantanément côté serveur sans cet échange.

## Compatibilité et mise à jour

Application **2.8.4**, SQLite **18**, plugin WordPress **2.8.2 inchangé**, protocole **4 / révision 3**. Aucun changement de schéma, aucune migration 17 → 18 pour une source déjà en 2.8.3 / schéma 18. Aucun secret réel n'est modifié. Les données et paramètres existants sont conservés.

Sauvegarder une PRE18 complète et conserver le runtime 2.8.3. Construire et vérifier 2.8.4 avant arrêt, puis arrêter proprement et compléter par une sauvegarde froide. Remplacer seulement le runtime ; vérifier SQLite, volumes, configuration, santé et relais avant la sauvegarde POST18. Aucun retour automatique destructif dès la première tentative de démarrage public : conserver l'état et décider humainement. Voir [upgrade.md](upgrade.md).

Les essais navigateur ne remplacent pas une vérification sur tablette ou iPhone physique. Le plugin et la caméra WordPress ne sont pas modifiés par cette version.

L'archive approuvée est distribuée sans reconstruction pour conserver son empreinte. Ses documents embarqués peuvent encore mentionner la candidate ; les documents du tag `v2.8.4` sont la référence stable à jour. Les scripts et configurations propres à une installation ne sont pas publiés.
