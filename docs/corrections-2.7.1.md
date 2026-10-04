# OpenFabLab 2.7.1 — version stable corrective

Cette version corrige l’ergonomie de la 2.7.0 sans nouvelle migration de données métier. SQLite reste au schéma 14 ; le plugin Reservations reste en 2.7.0. Elle a été testée puis déployée en conditions réelles au FougèresLab.

## Demandes d’animations depuis la borne

Option facultative « Autoriser la réservation d’animations depuis la borne », désactivée par défaut, près de l’inscription autonome. Le footer de l’accueil affiche « Réserver une animation » uniquement si cette option et le module Réservations publiques sont actifs. Aucun parcours public de réservation de ressource n’est ouvert.

Le catalogue local ne montre que les animations publiées en mode Normal, futures et ouvertes aux inscriptions. Les places affichées sont **indicatives**, issues de la dernière synchronisation. Un usager saisit son identifiant à quatre chiffres et ses coordonnées concordantes ; un visiteur remplit les mêmes informations que sur WordPress. Aucun répertoire ni participant n’est exposé. Le QR n’est pas utilisé dans ce nouveau formulaire.

Le dépôt fonctionne sans connexion Internet : la demande est enregistrée durablement dans l’outbox SQLite existante, **en attente de confirmation**. Il ne crée pas une place confirmée ni une présence et ne réserve pas la dernière place. Le moteur transactionnel WordPress reste l’autorité commune : âge, accompagnateur, capacités, créneaux, doublons, liste d’attente et e-mails suivent son parcours public existant. Le synchroniseur transmet ensuite la demande et importe les inscriptions canoniques. Aucun SMTP local n’est obligatoire. URL et secret de synchronisation doivent déjà être configurés.

La cadence initiale devient **1,5 minute (90 secondes)**. À la première initialisation, l’ancienne valeur de deux minutes est remplacée par 1,5 ; les autres valeurs personnalisées sont conservées. Les réglages et le profil acceptent les demi-minutes de 1 à 60 minutes. Les réveils du worker restent espacés de 30 secondes : délai indicatif jusqu’à environ 90–120 secondes, **plus** transport et traitement, sans garantie de moins de deux minutes. Une panne réseau peut prolonger l’attente indéfiniment. Le réseau local entre tablette et serveur reste nécessaire.

Le protocole actuel ne renvoie pas d’identifiant d’idempotence pour un dépôt public. Après une réponse réseau perdue ou un arrêt pendant l’envoi, **aucun renvoi aveugle** : rapprochement avec les événements WordPress ; à défaut, état « À vérifier par l’équipe ». L’équipe contrôle alors les inscriptions avant toute nouvelle demande. Un refus métier est distinct d’une panne. Les demandes en attente peuvent être annulées par l’équipe ; une demande incertaine n’est pas supprimée arbitrairement. Les confirmations et annulations ultérieures suivent les événements du moteur commun.

Le parcours public verrouille une session Administrateur/Modérateur préexistante, contrôle le CSRF, les formulaires expirés, les tentatives répétées et les doublons locaux. Le reçu temporaire ne contient pas de coordonnées. Une copie privée pour test reste incapable de transmettre ces demandes aux services réels.

## Catégories

Nom, couleur et activation proviennent du registre de la structure. La couleur ne dépend plus d’une classe historique. Les catégories inactives restent consultables en activant « Afficher les catégories inactives » dans les statistiques ; les totaux et pourcentages conservent toute la période, avec une indication des personnes masquées.

Réordonner avec ↑/↓ (clavier/tactile) ou la poignée (souris/tactile). L’ordre est sauvegardé sans bouton et normalisé sans trou ni doublon. Les nouveaux éléments vont à la fin. Les noms/couleurs/activations des catégories existantes sont également sauvegardés à la modification ; le bouton Enregistrer fonctionne aussi sans JavaScript. Un échec est annoncé, jamais présenté comme une réussite.

Les ordres des catégories sont dans leurs tables existantes et leur profil de structure ; les habilitations et leur ordre restent dans SQLite et les sauvegardes complètes, pas dans un profil de branding. Leur ordre est enregistré dans le paramètre interne `authorization_order`, sans ajouter de colonne au schéma.

## Journée, connexion et réglages

Modifier une session ouvre une ligne sous celle-ci. Le formulaire se répartit sur toute la largeur et s’empile sur téléphone. Fermer ou Échap ramène le focus au bouton Modifier. La suppression reste distincte et confirmée.

La connexion conserve le système de PIN dérivé et les deux rôles. Aucun PIN n’est prérempli ou exporté en clair. Les sous-onglets Réglages occupent au maximum deux rangées sur téléphone. Les effets visuels n’animent pas la mise en page et respectent `prefers-reduced-motion`.

Le logo OpenFabLab par défaut conserve son SVG, sa taille et son placement, avec une ombre équilibrée permanente. La classe `brand-wordmark--openfablab` n’est ajoutée qu’à ce logo : les logos personnalisés, institutionnels, de réseau et autres images restent inchangés. Cet effet statique n’a ni variante au survol ni animation.

Notifications : webhook, événement nouvel usager, autres événements puis messages. Enregistrer le webhook ne modifie pas les autres options. Les données personnelles transmises à Discord restent celles choisies explicitement.

Le webhook reste hors SQLite et n'est pas affiché. Il est cependant inclus dans la sauvegarde complète privée, comme les autres secrets persistants ; cette archive doit être conservée en lieu sûr et ne jamais être publiée.

Structure → SMTP : « Tester la configuration SMTP » envoie un message simple, sans usager/QR/pièce jointe ; « Envoyer un exemple d’e-mail de bienvenue » utilise le modèle configuré avec une identité et un QR fictifs. Aucun envoi ne fonctionne dans une copie de test dont les actions externes sont neutralisées.

## Ressources et habilitations

Activités : Aperçu → Réserver une ressource → Gestion des ressources → Formations et habilitations.

Les tarifs acceptent une virgule ou un point et au maximum deux décimales. Ils restent des centimes entiers en base. Disponibilité, validation manuelle, conflits, expiration, dérogation Administrateur auditée et facturation conservent leurs contrôles.

Les habilitations peuvent être modifiées/réordonnées/archivées/réactivées. Une ressource active exigeant une habilitation bloque son archivage. Une suppression exige une confirmation et l’absence de formations ou ressources associées. Les validations historiques et les révocations motivées restent conservées. Le journal identifie le rôle ayant révoqué ; il n’invente pas une personne derrière un PIN partagé.

La fiche usager distingue permanente, valide, à venir, expirée ou révoquée et montre les dates, le validateur et, pour l’équipe autorisée, le motif de révocation.

## Calendrier

Jours/horaires plus lisibles, couleurs légères, week-ends et aujourd’hui différenciés. Les événements ouvrent un résumé accessible et un lien vers la page source ; sans JavaScript le lien direct fonctionne. Semaine/Mois, plage visible et calculs de fréquentation sont conservés.

Le détail OpenLab montre les horaires, compteurs, pic et son heure, ainsi que les usagers et catégories, sans identité pour les visiteurs anonymes. La météo n’apparaît que si elle est déjà enregistrée au pic ; aucun appel historique externe. Les détails d’animation réservés à l’équipe montrent inscriptions, catégories et liste d’attente. La rangée « Journée entière » n’apparaît que si elle contient un événement.

Les badges utilisent un fond pâle et un disque entier dans la couleur configurée. Le formulaire de correction Journée a les labels au-dessus des champs (quatre, deux puis une colonne selon la largeur). Historique annuel tient sur MacBook, les sous-onglets ont une marge pour leur ombre, et les cartes d’habilitations rapprochent titre et commandes. Le bandeau visuel de copie de test est retiré, pas ses protections.

## Roadmap — réservation publique des ressources (non implémentée)

Évolution future : depuis la borne et éventuellement WordPress, choisir une machine, salle, bureau ou autre ressource puis un créneau disponible ; vérifier les habilitations et soumettre une demande. Sans « Confirmation obligatoire », confirmer si toutes les règles sont satisfaites ; sinon rester en attente de confirmation par l’Administrateur/Modérateur autorisé, avec acceptation ou refus et notification selon les intégrations disponibles. Réutiliser le service métier partagé, sans dupliquer capacités et règles.

## Essai et mise à jour

Avant mise à jour, conserver une sauvegarde complète privée et le runtime précédent. La 2.7.1 ne réécrit pas les données métier, les historiques, le branding, les secrets ou les PIN. Elle normalise seulement les ordres de listes à l’initialisation.

Pour les essais, restaurer une **copie privée pour test** dans un dossier isolé : ses services externes restent désactivés, y compris après une mise à jour. Ne publier aucune ressource ou capture privée. Toujours contrôler l’installation cible avant remise en service ; voir [la procédure de mise à jour](upgrade.md).

Le ZIP stable inclut uniquement la correction de packaging Docker approuvée : copie de `tablet_reservations.py` dans l’image, sans modification du module lui-même. Son empreinte figure dans `SHA256SUMS`. La documentation du dépôt est présentée au statut stable séparément, sans reconstruire ce ZIP approuvé.
