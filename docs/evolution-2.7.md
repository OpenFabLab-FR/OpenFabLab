# OpenFabLab 2.7.0 — nouveautés et fonctionnement

Version stable validée localement puis sur une installation réelle de FabLab, avec migration SQLite **13 → 14** et SMTP réel fonctionnel. Le plugin associé est Reservations **2.7.0** ; son schéma reste **2.6.0**. Aucun secret ne change automatiquement. Chaque structure doit vérifier ses intégrations et son hébergement ; la validation d’une installation ne couvre pas toutes les configurations possibles.

## Synchronisation : cause reproduite et limites du diagnostic

Dans le code 2.6.3, suppression d’animation et outbox partagent déjà une transaction SQLite : ce point était correct. En revanche, un ancien `upsert` refusé interrompait la file avant une suppression ultérieure ; une commande perdue n’était jamais reconstruite. Le plugin pouvait acquitter une suppression malgré un échec d’écriture. Sa « dernière synchronisation » était actualisée dès la vérification HMAC, avant le traitement : elle ne prouvait pas une réussite. Ces mécanismes ont été reproduits localement. Sans les traces de l’installation concernée, ils ne prouvent pas la cause précise de son incident réel.

Le serveur initie toujours les échanges **HTTPS sortants signés HMAC** : aucun port entrant requis. Test et Normal ont catalogue, curseur, file et diagnostic séparés. Les commandes de catalogue sont recalculées depuis l’état actuel, les suppressions nécessaires prioritaires ; les actions de réservation gardent leur ordre.

Après négociation `catalog_snapshot_v1`, chaque passage transmet le catalogue complet de l’environnement. WordPress verrouille les lignes, applique les configurations compatibles et masque les animations absentes. Cette transaction ne supprime **jamais** réservations, événements ou tokens et n’impose pas les comptes du serveur : les réservations WordPress fraîches restent comptées. Une modification incompatible avec un créneau réservé est refusée, jamais déplacée silencieusement ; le diagnostic demande correction explicite.

Réponse positive requise avant acquittement de l’outbox ; en cas de coupure, la commande reste rejouable. Actions de réservation existantes idempotentes, pagination `has_more` et refus du curseur immobile. Une erreur Test n’empêche pas Normal et inversement. Les routes publiques conservent leurs en-têtes anti-cache.

OpenFabLab affiche tentative, réussite, erreur, animations, inscriptions, commandes en attente, protocole/plugin et **Synchroniser maintenant**. WordPress distingue contact signé et réussite du cycle (catalogue/flux servis, pas confirmation de leur import SQLite). L’actualisation sera traitée au prochain passage du serveur : WordPress ne réveille pas le NAS. Les actions NAS en attente se consultent dans OpenFabLab, sans copier sa file privée sur WordPress.

Purge administrative : Administrateur WordPress, POST, nonce et confirmation `RESYNCHRONISER TEST` ou `RESYNCHRONISER PRODUCTION`. Elle exige une réconciliation 2.7 préalable, masque le catalogue et vide uniquement l’annuaire de cet environnement. Toutes les transactions sont conservées ; date/utilisateur/environnement/action sont journalisés sans secret. Le prochain passage reconstruit la configuration. Ce n’est pas une purge d’inscriptions et la maintenance Test précédente reste intacte.

Un ancien plugin conserve le protocole incrémental classique ; les fonctions nouvelles nécessitent leurs capabilities. Catégories personnalisées et réconciliation demandent Reservations 2.7.0. Installer d’abord ce plugin sur un WordPress d’essai. Ne jamais donner le secret de production à une instance de développement.

## Catégories et usagers

Réglages → **Usagers**, titre **Usagers et catégories** : nom, couleur compacte, ordre, activation et unique catégorie active par défaut. Les actions sont compactes ; suppression/réaffectation reste dans un panneau dangereux replié. Clés historiques stables : un renommage ne change ni fiches ni droits. Supprimer une catégorie utilisée exige une réaffectation active ; sa clé est archivée pour les statistiques historiques. Une catégorie inutilisée peut être supprimée. La sélection est contrôlée, avec création par l’Administrateur dans les réglages.

Installation neuve : **Usager, Bénévole, Manager** seulement, Usager par défaut. Migration depuis un schéma historique, même sans usager : **Usager, Bénévole, Volontaire, Fabmanager, Stagiaire, Personnel**, clés et affectations inchangées. Une installation déjà équipée du registre garde sa configuration et sa catégorie par défaut ; aucune catégorie n’est supprimée à la réinitialisation.

Les nouvelles fiches portent date/origine (Administrateur, Modérateur, borne) et rôle créateur connu. Une ancienne fiche reste « Historique / inconnue » ; aucune personne créatrice n’est inventée. La catégorie et la provenance n’accordent aucun privilège.

Auto-inscription désactivée par défaut. **Créer un compte**, lien discret dans le pied de la borne après Administration, réutilise le formulaire, verrouille la session privilégiée, impose la catégorie par défaut et attribue l’ID sous verrou SQLite. Les champs d’ID/catégorie/activation envoyés manuellement sont ignorés. Prénom/nom requis ; autres coordonnées facultatives sur borne. CSRF, formulaire expirant, cinq tentatives par dix minutes (empreinte IP privée) et reçu de deux minutes. QR réservé à cette session, sans cache ; retour automatique à l’accueil après une minute. La borne doit rester sur un réseau maîtrisé : ce n’est pas un portail Internet ouvert.

## SMTP natif et Discord

Réglages → **Structure → SMTP natif** : TLS/STARTTLS uniquement, certificat vérifié, expéditeur/Répondre à et test fictif. Credentials dans `.openfablab_smtp.json`, permissions 600, à côté de la base ; jamais SQLite, profil ou ZIP public. Mot de passe vide = conserver. SMTP indépendant de WordPress et facultatif. L’ancienne route Intégrations redirige vers Structure ; les POST conservés sont protégés.

Sujet/corps texte personnalisables : `{{structure_name}}`, `{{first_name}}`, `{{last_name}}`, `{{public_id}}`, `{{contact}}`, `{{website}}`. QR intégré et PNG joint, issus du même ID. Envoi facultatif, case disponible avec adresse valide ; présélection configurable. Un échec SMTP ne supprime pas le compte. État et dernier succès dans la fiche ; renvoi confirmé. La délivrabilité réelle reste à tester avec son fournisseur.

Réglages → **Notifications → Notifications à la création d’usager**, événement désactivé par défaut. Seuls les champs cochés partent : prénom, nom ou initiale, âge, catégorie, origine, date. E-mail, téléphone, adresse, ID et QR ne sont jamais admissibles. Informer les personnes et définir les destinataires avant activation ; ces renseignements choisis quittent l’installation vers Discord.

## Ressources, réservations et habilitations

Activités → **Aperçu | Réserver une ressource | Gestion des ressources | Formations et habilitations**. Aperçu conserve la page et la route historiques.

Ressources : catégorie, couleur héritée ou propre, activation, prix forfaitaire et confirmation automatique ou validation de l’équipe. Seul « Machine » est initial ; Salle/Bureau apparaissent uniquement sur création explicite. Catégories contrôlées et masquables, formulaires compacts et identifiants internes `type_key` conservés. Les machines de locations sont reprises par clé stable, sans remplacement de leurs tarifs ou anciens dossiers. Le catalogue de locations et les nouveaux forfaits de réservation restent distincts.

Modules **Ressources** et **Formations et habilitations**, activés initialement pour les nouvelles installations et pour les migrations sans réglage antérieur. Désactiver masque navigation, routes d’écriture et événements correspondants du calendrier, sans aucune suppression. Désactivation des habilitations refusée si une ressource active en dépend, même si Ressources est masqué : retirer explicitement son exigence ou désactiver cette ressource. L’import de profil respecte ce garde-fou.

UUID de réservation stable, plage explicite et contrôle transactionnel des chevauchements par ressource ; ressources indépendantes. États : **En attente de validation**, **Confirmée**, **Effectuée**, **Refusée**, **Annulée**, avec audit. Les états terminaux ne se rouvrent pas implicitement. Une réservation tarifée crée ou rattache **un seul dossier** dans Facturation, avec son annuaire client et le prix convenu. Aucune deuxième comptabilité. Vérifier/compléter les coordonnées avant émission des documents.

Formations/habilitations : définition, usager, date effectuée, validateur libre explicite, expiration facultative (permanente sinon), révocation motivée avec historique. Une ressource peut exiger cette habilitation sur toute la plage, dans le fuseau de la structure. Manquante/expirée/révoquée : refus sauf **dérogation Administrateur motivée et auditée**. Le Modérateur ne peut contourner ce contrôle. Pas de certification OpenBadge externe.

## Calendrier

Onglet principal Administrateur/Modérateur, **Semaine/Mois**, précédent/suivant/Aujourd’hui, fiches cliquables, blocs horaires et chevauchements séparés, événements sans horaire. OpenLab, animation globale (pas chaque créneau interne), prestations, locations y compris celles commencées avant la période affichée, ressources et formations.

Réglages → **Affichage → Plage horaire visible du Calendrier** : **09:00–19:00** par défaut, fin strictement après début. Affichage seulement : ni contrainte de réservation ni changement des OpenLab. Extension de la semaine aux événements hors plage, avec message visible, sans modifier les préférences. Hauteur liée à la durée affichée, aucun défilement vertical imbriqué ; glissement horizontal contenu sur petits écrans. Colonne Heures élargie pour éviter la troncature. Couleurs de catégories/ressources, aucun cloud ni bibliothèque.

Blocs OpenLab passés/en cours : compteur secondaire usagers distincts et visiteurs, calculé par **la même fonction `load_day_attendance` que la page de fréquentation**, bornée au créneau OpenLab (arrivées enregistrées dans cette plage). Même identité statistique et distinction sessions/usagers/visiteurs ; aucune écriture ni méthode parallèle. OpenLab futur : aucun faux compteur à zéro. Les droits et modules limitent les liens accessibles.

## Navigation Réglages

**Affichage | Usagers | Borne | Notifications | Tarifs | Données | Structure**, sur une ligne sur ordinateur/tablette paysage, grille compacte sans scrollbar sur téléphone. Données accueille responsable du traitement, représentant, DPO, conservation et sauvegardes ; Structure conserve identité, branding, modules, WordPress et SMTP. Les préférences calendrier et les deux nouveaux modules sont transportés par le profil privé version 1. Les catégories restent distinctes des rôles Administrateur/Modérateur.

## Migration et sauvegardes

SQLite **13 → 14** depuis 2.6.x. Avant toute écriture d’initialisation, copie SQLite cohérente vérifiée dans `migration-backups/` à côté de la base. La transaction reconstruit seulement la contrainte fixe des catégories sur `users`, copie ses anciennes colonnes sans transformation et conserve clés/indices/triggers/séquence ; provenance, registres et tables sont ajoutés. Les catégories historiques des sessions ne sont pas réécrites. `foreign_key_check` avant validation. Aucun fichier privé déplacé/remplacé ; paramètres/branding/PIN/secrets existants restent prioritaires.

Une sauvegarde SQLite seule n’inclut pas les ressources privées ni SMTP : sauvegarder **tout le dossier de données**, configuration et image/code antérieurs à froid avant la migration. OpenFabLab 2.7.0 propose aussi une [sauvegarde complète privée et une copie pour test](private-backup.md), avec manifeste, empreintes et restauration contrôlée. La copie de test conserve les PIN dérivés et les ressources présentes tout en neutralisant les actions externes. Ne publier aucune de ces archives.

Profil privé version 1 : catégories/types, préférences bienvenue/Discord et ressources autorisées ; pas de comptes métier ni credentials/secrets SMTP. Les anciens profils sans registres restent lisibles. L’import de profil conserve ses protections existantes : WordPress déconnecté et Discord désactivé pour éviter une connexion accidentelle d’une copie.

## Essai recommandé

Extraire dans un dossier séparé. Tester base fictive neuve, puis **copie** de sauvegarde 2.6.x avec workers/WordPress/Discord désactivés. Vérifier schéma 14, intégrité/FK, volumes et réglages privés ; essayer catégories, borne, ressources, habilitations, calendrier et transport SMTP simulé. Pour la chaîne complète, WordPress **de test séparé**, secret indépendant, plugin 2.7.0 : réservation Test neuve, suppression, coupure/reprise, capacité et attente par créneau. Ne connecter jamais deux instances au WordPress de production.

Les tests PHP simulent `wpdb` sur SQLite ; contrôler aussi la concurrence InnoDB sur un WordPress d’essai. Le SMTP réel a été validé sur l’installation de référence, mais la délivrabilité et les politiques d’autres fournisseurs restent à vérifier. Les suites locales simulent les transports SMTP/Discord et ne contactent pas les services de production. Les contrôles Docker locaux sont statiques lorsqu’aucun moteur Docker n’est disponible ; ne pas les confondre avec un build réellement exécuté.

## Roadmap, sans développement partiel

OpenBadges, abonnements et familles restent à concevoir séparément. Aucun formulaire trompeur, facturation automatique ni migration partielle de ces fonctions.
