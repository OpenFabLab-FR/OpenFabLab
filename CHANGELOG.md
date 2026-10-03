# Historique public

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
