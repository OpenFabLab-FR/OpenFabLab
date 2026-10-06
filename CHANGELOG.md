# Historique public

## 2.8.1 — version stable — 6 octobre 2026

- Réservations WordPress par échanges HTTPS initiés uniquement par OpenFabLab : correction du parcours public qui exigeait une adresse entrante vers le NAS en 2.8.0.
- Protocole 4 et capacité `outbound_actions_v1`, requêtes et réponses authentifiées. Les anciennes versions ne confirment pas de nouvelles demandes par un moteur de secours.
- Catalogue public séparé de la relève légère des actions : 90 secondes et 15 secondes par défaut, relève configurable de 10 à 60 secondes.
- File WordPress InnoDB chiffrée, reprise par bail, résultat durable ; effet métier et reçu d'idempotence dans la même transaction SQLite. WordPress ne décide jamais des places.
- Suppression réelle des classes et routes de l'ancien moteur WordPress, de ses cron métier, e-mails, annuaire et interfaces. Le relais ne gère que catalogue, actions et nonces. Retrait verrouillé des anciennes tables uniquement si elles sont toutes vides ; les données non vides et l'historique OpenFabLab restent préservés.
- Administration WordPress allégée : Normal prioritaire, badges et compteurs compacts, Test/diagnostic repliables, secret jamais affiché. Régénération secondaire confirmée et bloquée pendant une demande/résultat utilisable ; aucune adresse du NAS requise.
- Liens personnels d'e-mail via une page WordPress dédiée, jeton dans le fragment, lecture sans mutation et actions explicites protégées. Les anciens liens OpenFabLab restent lisibles.
- Schéma SQLite 15 → 16 additif : deux tables techniques et réglages, sans purge ni réinterprétation de l'historique. Familles, capacité, groupes indivisibles, FIFO, SMTP et réservations locales restent gérés par le moteur existant.
- Suppression administrative d'une animation terminée sécurisée : retrait transactionnel des dépendances de ses inscriptions familiales annulées, expirées ou refusées ; les autres animations, comptes, passages et facturations restent intacts. Refus explicite en présence d'inscriptions actives, attente, places proposées, dossier incohérent ou facturation liée. Reçus anti-rejeu conservés.

- Confidentialité et packaging renforcés : liste explicite de fichiers publics, exclusion des fichiers privés et rejet des métadonnées macOS parasites dans les sources et archives.

Version corrective et d'architecture de la 2.8.0, déployée et vérifiée en conditions réelles au FougèresLab ; le dernier correctif de suppression a également été confirmé par l'exploitant. Dernière validation locale : **505 tests Python (dont 13 de suppression), 770 contrôles PHP, 622 JavaScript et 108 contrôles de suppression Chromium/WebKit**, sur neuf largeurs de 320 à 1920 px, sans erreur JavaScript ni débordement. Intégrité SQLite, clés étrangères et migration/restauration vers le schéma 16 vérifiées. Les validations antérieures WordPress/MariaDB isolé et du relais ne sont pas présentées comme de nouveaux passages du correctif. Aucun accès entrant, reverse proxy ni port public OpenFabLab n'est nécessaire pour le plugin. JavaScript est requis pour son interface publique ; utiliser **l'application et le plugin 2.8.1 ensemble**, protocole **4 / révision 2**, et lire les [instructions de mise à jour](docs/upgrade.md) avant installation. Les [résultats techniques détaillés](docs/development.md) précisent la couverture et ses limites ; cette publication ne modifie aucun service de production.

## 2.8.0 — version stable — 5 octobre 2026

Version validée localement, migrée depuis la 2.7.1 puis déployée et vérifiée au FougèresLab, avec le plugin WordPress 2.8.0 relié et testé en conditions réelles.

- Chaque participant conserve un vrai compte : une personne sélectionnée = une place. Responsables et membres rattachés, plusieurs responsables possibles, liens privés réciproques et fin manuelle conservant l'historique.
- Seuils d'autonomie/responsabilité et cinq politiques de coordonnées configurables ; naissance précise pour les nouveaux mineurs, année historique préservée.
- Moteur transactionnel commun borne/administration/plugin WordPress 2.8 : groupes indivisibles, capacité par créneau, doublons, autorisations temporaires et répétition sans double inscription.
- Le mécanisme spécifique d'accompagnateur reste uniquement lisible dans les anciennes réservations ; aucune conversion ou purge OpenFabLab.
- Plugin optionnel refondu en relais HTTPS ; nettoyage des six tables historiques du plugin seulement, manuel, protégé, avec sauvegarde préalable. Les options et secrets sont conservés. Aucun nettoyage à l'installation.
- Titre de borne configurable, accès publics depuis la page intermédiaire, catégories compactes et chronologie sans débordement de noms.
- Accueil tablette minimaliste : lien « Gestion » vers la page intermédiaire ; « Gestion des données » masqué uniquement dans son footer. Les pages internes et l'espace protégé conservent leurs libellés et leurs liens.
- Calendrier : couleurs par type, masquage par occurrence sans supprimer de données, OpenLab terminé sans présence masqué automatiquement, détails et titres améliorés.
- Une seule pièce jointe QR PNG dans le message de bienvenue ; suivi quotidien idempotent du passage au seuil de responsabilité lorsque des coordonnées manquent.
- Migration additive SQLite 14 → 15 avec sauvegarde PRE cohérente. Sauvegardes complètes/restauration adaptées au nouveau schéma.

- Liste d’attente automatique : FIFO compatible avec la capacité, propositions temporaires pour le groupe entier, acceptation/refus et expiration atomiques ; une place bloquée ne peut pas être vendue une seconde fois.
- E-mail valide obligatoire, téléphone obligatoire optionnel, complément de coordonnées après identification ; contact d’un responsable utilisable sans duplication sur le compte enfant.
- SMTP natif et journal durable des confirmations, attentes, propositions, modifications et annulations ; traitement indépendant de WordPress, reprises bornées, historique et échéances dans l’administration.
- Derniers ajustements : login sans aide PIN redondante, accès rapide sur une ligne, thème avant couleurs compactes puis horaires, formulaire animation simplifié et colonne Identifiant non coupée.
- Le menu de tri du répertoire reste contenu à 320 px ; les exports privés d’inscriptions utilisent le contact de la demande sans le recopier dans le compte enfant.

- Harmonisation finale des titres internes et champs numériques : âges, durées, montants en euros, conservation et sauvegardes ; lien direct vers les règles d'autonomie, corrections de tableaux et petits écrans WebKit.

Validation automatisée finale : **451 tests Python, 724 contrôles PHP et 622 contrôles JavaScript** ; contrôles responsive et parcours Chromium/WebKit de 320 à 1440 px, migration/restauration d'une copie privée et archives publiques vérifiées. WordPress nécessite JavaScript et un accès HTTPS vers OpenFabLab. PHP/SQL et SMTP sont simulés dans les suites locales ; pas de nouveau build Docker ni de WordPress/MySQL réel réalisé par ces suites. La validation NAS/WordPress réelle a été confirmée par l'exploitant. Voir [le guide de vérification](docs/candidate-2.8-guide.md).

## 2.7.1 — version stable

Version corrective et d’amélioration de la 2.7.0, testée localement puis déployée en conditions réelles au FougèresLab.

### Corrections

- Couleur du registre dynamique appliquée à tous les badges de catégorie, sans anciennes couleurs prioritaires.
- Catégories masquées cachées par défaut dans les statistiques, option explicite pour leur historique ; totaux historiques inchangés.
- Correction d’une session dans une ligne pleine largeur avec focus et fermeture clavier, sans déformer le tableau.
- Suppression de la provenance « Historique / inconnue » dans le répertoire ; formulation neutre dans la fiche.
- Badges symétriques à pastille pleine ; labels de correction Journée au-dessus des champs ; historique annuel et ombre des sous-onglets ajustés.

### Animations depuis la borne

- Option désactivée par défaut et lien de footer ; catalogue public sans participants ni coordonnées.
- Demande locale durable sans connexion Internet, explicitement en attente, puis traitement par le moteur WordPress existant (capacités, groupes, doublons, listes d’attente).
- Réconciliation des réponses perdues sans renvoi aveugle ; contrôle par l’équipe si le résultat reste incertain.
- Synchronisation à 90 secondes par défaut, demi-minutes administrables ; délai réel dépendant du réseau et du traitement.
- Modérateur : participants, ajout sur place et suivi des demandes autorisés ; réglages sensibles toujours protégés.

### Interface

- Connexion Administrateur/Modérateur par choix segmenté accessible ; PIN toujours masqué à quatre chiffres.
- Micro-interactions communes discrètes, focus visible et respect du mouvement réduit.
- Sept sous-onglets Réglages en deux rangées sur téléphone.
- Ombre équilibrée et statique sur le seul logo OpenFabLab d’en-tête ; logos personnalisés et partenaires inchangés.

### Ressources

- Sous-navigation clarifiée ; résumé compact des ressources et même formulaire pour ajout/modification.
- Tarifs saisis en euros, calcul décimal exact et stockage inchangé en centimes.
- Catégories et définitions réordonnables par poignées souris/tactiles ou flèches clavier, sauvegarde automatique et positions normalisées.

### Formations et habilitations

- Liste des habilitations, modification, ordre, archivage et réactivation ; cartes compactes avec commandes alignées.
- Suppression seulement sans historique ni dépendance ; ressource active associée protégée.
- Historique des formations et révocations motivées visible dans la fiche usager ; aucune suppression de validation.

### Calendrier

- Présentation plus lisible, jours nommés, aujourd’hui et week-ends discrets, détails accessibles au clic/clavier.
- Calculs horaires, fréquentation et règles métier conservés.
- Détail OpenLab enrichi avec pic et usagers, météo déjà enregistrée seulement ; participants des animations pour l’équipe ; rangée de journée entière masquée lorsqu’elle est vide.

### Notifications

- Webhook, nouvel usager puis événements ; cases homogènes et information explicite sur les données personnelles.
- Présentation mobile et enregistrement indépendant du webhook.

### E-mail

- Test SMTP simple distinct de l’exemple de bienvenue fictif avec QR.
- Les essais restent interdits dans une copie privée de test neutralisée.

### Compatibilité

- Schéma SQLite **14 inchangé**. Normalisation idempotente des seuls ordres de configuration ; classement des habilitations dans les paramètres existants.
- Sauvegardes privées compatibles avec les correctives 2.7.x ; fichiers persistants et PIN dérivés conservés.
- Plugin OpenFabLab Reservations **2.7.0 inchangé**.

### Distribution et validation

- Le Dockerfile copie maintenant le module de réservation depuis la borne, déjà présent dans les sources validées. Aucun changement métier associé.
- 396 tests Python, 461 contrôles PHP et 622 contrôles JavaScript réussis ; contrôles responsive Chromium/WebKit de 320 à 1440 px.
- Deux tests de packaging ajoutés : démarrage depuis les seuls fichiers copiés dans l’image et détection du module manquant.
- ZIP applicatif approuvé et plugin inchangé, empreintes SHA-256, contenu public, licences et reproductibilité vérifiés. Docker indisponible localement : contrôle réel du jeu de fichiers et de l’entrée WSGI, pas de build d’image local revendiqué.
- Familles, profils enfants et réservation pour un enfant restent en roadmap, non implémentés dans cette version.

## 2.7.0 — version stable

### Calendrier

- Calendrier centralisé en vues Semaine/Mois, navigation précédent/suivant/Aujourd’hui et liens vers les fiches.
- OpenLab et fréquentation, animations globales, prestations, réservations, locations et formations ; chevauchements séparés et événements sans horaire.
- Plage visible configurable, 09:00–19:00 par défaut, étendue aux événements hors plage sans modifier les préférences ; absence de double défilement vertical.
- Compteurs OpenLab issus du même calcul de fréquentation que les statistiques existantes ; aucun compteur fictif pour les créneaux futurs.

### Usagers

- Catégories configurables : clé stable, nom, couleur, ordre, activation/masquage et catégorie active par défaut.
- Suppression/réaffectation contrôlée, archivage des clés utilisées et conservation des statistiques historiques ; catégories indépendantes des droits.
- Installation neuve : Usager, Bénévole et Manager. Migration : catégories et affectations historiques conservées, même sans fiche actuelle.
- Inscription autonome facultative sur la borne : session privilégiée verrouillée, CSRF, limitation des tentatives, catégorie par défaut imposée et reçu QR temporaire.
- Date, origine et rôle créateur des nouvelles fiches ; provenance historique laissée inconnue lorsqu’elle n’est pas disponible.

### E-mails et notifications

- SMTP natif facultatif avec TLS/STARTTLS et vérification des certificats ; configuration privée hors SQLite et profil de structure.
- E-mail de bienvenue personnalisable avec identifiant, QR intégré et PNG joint ; état de l’envoi et renvoi confirmé. Un échec d’envoi ne supprime pas le compte.
- Notification Discord « nouvel usager » configurable et désactivée par défaut ; seuls les champs d’identité choisis sont envoyés, jamais les coordonnées, l’identifiant ou le QR.

### Ressources et réservations

- Machines et autres ressources, catégories activables, couleurs, ressources gratuites ou tarifées ; catalogue de locations historique préservé.
- Confirmation automatique ou validation par l’équipe, plages explicites et contrôle transactionnel des chevauchements par ressource.
- États En attente de validation, Confirmée, Effectuée, Refusée et Annulée, avec historique ; pas de réouverture implicite d’un état terminal.
- Lien unique vers les clients et dossiers de facturation existants pour une réservation tarifée ; pas de deuxième comptabilité.
- Module Ressources désactivable sans effacer ses données.

### Formations et habilitations

- Validation d’une formation pour un usager, validateur explicite, habilitation permanente ou date d’expiration facultative.
- Révocation motivée et historique ; habilitation valide sur toute la plage requise pour les ressources qui l’exigent.
- Dérogation Administrateur motivée et auditée, inaccessible au Modérateur.
- Module masquable sans suppression ; désactivation refusée lorsqu’une ressource active dépend encore d’une habilitation.

### WordPress

- OpenFabLab Reservations 2.7.0 : protocole 2 et capabilities de catalogue et catégories, sans nouvelle migration de schéma WordPress.
- Réconciliation du catalogue par environnement, absents masqués et configuration reconstruite, sans effacer réservations, événements ou tokens.
- Commandes obsolètes recalculées, suppressions prioritaires, accusés vérifiés, pagination explicite et reprise de la file après erreur.
- Diagnostics distincts : dernière tentative, dernière réussite, erreur et simple contact signé ; actualisation au prochain passage sortant du serveur.
- Purge/resynchronisation administrative confirmée de la seule configuration reconstruisible, Test et Normal séparés ; maintenance Test existante conservée.

### Sauvegardes

- Trois niveaux distincts : SQLite, sauvegarde complète privée et copie privée pour test/diagnostic.
- Sauvegarde du persistant avec manifeste, tailles et SHA-256 ; restauration contrôlée sans fusion, état de sécurité et journal de récupération.
- Copie de test conservant données, branding et dérivations PIN, avec WordPress/Discord/SMTP/météo neutralisés et connexions externes bloquées ; clé de session renouvelée.
- Avertissement de confidentialité explicite : archives privées sensibles et non chiffrées, jamais destinées aux distributions publiques.

### Interface

- Réglages regroupés en sept onglets courts, formulaires et contrôles compactés ; onglet Aperçu historique conservé.
- Lien d’inscription autonome discret dans le pied de borne ; modules facultatifs et protections de leurs routes conservés.
- Ajustements responsive et accessibilité, calendrier sans défilement imbriqué et navigation compacte sur téléphone.

### Migration

- SQLite 13 → 14 transactionnel et additif : sauvegarde pré-initialisation, registres et tables supplémentaires, anciennes colonnes et clés de catégories conservées.
- Données historiques, réglages et fichiers privés conservés ; profil version 1 enrichi de champs facultatifs et anciens profils compatibles.
- Une base schéma 14 ne doit jamais être utilisée par 2.6.x ; rollback uniquement avec la sauvegarde cohérente schéma 13 et prise en compte des nouvelles écritures.
- OpenBadges, abonnements et familles restent en roadmap, sans implémentation partielle.

## 2.6.3 — DPO et ressources complémentaires

- DPO libre, e-mail et téléphone facultatif dédiés, indépendants du contact général ; carte publique conditionnelle distincte du responsable du traitement.
- Intitulé « Représentant » simplifié, ponctuation adaptée aux renseignements disponibles.
- Trois cartes directement visibles : logo complémentaire des documents, signature des bilans et badge privé, avec aperçu, état, remplacement et retrait explicite.
- Désactivation/réactivation des trois ressources sans effacer leurs fichiers ; comportement existant conservé après mise à jour.
- Profil privé enrichi, reprise additive des anciennes clés DPO disponibles et schéma SQLite toujours 13.
- Mention explicite de l’absence de télémétrie vers le site du projet ; aucun mécanisme de collecte ajouté.
- Plugin Reservations 2.6.1 inchangé ; aucune modification des données métier, PIN ou secrets.

## 2.6.2 — identité et ressources privées persistantes

- Badge personnalisé SVG persistant, rendu SVG/PNG commun, erreurs explicites si le modèle configuré manque ; badge générique conservé pour les nouvelles installations.
- Quatre usages de logos indépendants, prévisualisations, remplacement, retrait explicite et visibilité des logos d’en-tête.
- Séparation additive du logo institutionnel historique d’en-tête et du logo documentaire.
- Personne morale responsable du traitement, adresse, représentant et fonction configurables ; profil privé enrichi.
- Schéma SQLite inchangé (13) ; aucun changement WordPress, PIN, secret ou donnée métier.

## 2.6.1 — première publication publique

- OpenFabLab est créé par William Aumand, sous licence MIT ; documentation pour les installations tierces.
- Valeurs initiales et ressources neutres : aucune banque, identité de structure, machine, tarif, usager, PIN ou secret préconfiguré. Les réglages enregistrés d'une installation existante restent conservés.
- Libre Franklin Regular/Bold sous SIL OFL 1.1 remplace les fontes propriétaires. Logos et signatures d'installations exclus ; badge générique.
- Tests autonomes, fixture SQLite fictive schéma 12, distributions autorisées/reproductibles et notices tierces.
- SQLite reste au schéma 13 ; aucun changement fonctionnel métier intentionnel par rapport à 2.6.0.
- Plugin inclus séparément : Reservations 2.6.1, runtime inchangé ; licence MIT complète ajoutée au ZIP public.

Fonctionnalités héritées de 2.6.0 : réservations classiques et par créneaux, attente par créneau, inscriptions et présence distinctes, exports CSV/PDF. Le plugin 2.6.1 propose six modèles d'e-mails personnalisables et une maintenance Test administrateur.

FougèresLab, FabLab de Fougères Agglomération, est la première installation réelle et le terrain de test du projet, non son éditeur.
