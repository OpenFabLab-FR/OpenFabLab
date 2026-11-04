# OpenFabLab 2.14.4 — version stable

## Ressources : archiver plutôt que perdre l’historique

Activités → Gestion des ressources → Autres actions : l’administrateur peut
archiver une ressource. Le filtre « Afficher les ressources archivées » permet
à l’équipe de la retrouver, de consulter ses données et, à l’administrateur,
de la restaurer. Les mêmes droits qu’avant régissent l’édition et le suivi.
Le statut Hors service reste une indisponibilité temporaire, distincte d’une archive.

Une archive disparaît des listes actives, des nouvelles réservations/locations,
du catalogue WordPress et des annonces publiques de la borne. Ses anciens
réglages, interventions, rappels traités, réservations, factures et liens restent
conservés. La restauration retrouve les réglages antérieurs, sans les élargir.
Une habilitation requise devenue inactive doit d’abord être réactivée.

L’archivage refuse les réservations demandées non traitées, les réservations
confirmées non terminées, les locations en cours/futures et les rappels à traiter
(y compris en retard). Il faut les traiter ou annuler volontairement dans leur
espace habituel. Aucun traitement automatique ni suppression d’opération.

La suppression définitive demande une confirmation distincte et n’est accessible
qu’aux administrateurs. Le serveur vérifie toutes les clés étrangères, y compris
une référence inconnue, les interventions/rappels/historiques et les liens au
catalogue de location ou à la facturation. Sinon, il refuse et propose l’archivage.
Les ressources issues du catalogue historique sont liées à ce catalogue : elles
ne sont pas supprimées puis recréées silencieusement par l’import historique.
L’audit de création/suppression reste conservé ; aucune cascade métier.

Le vieux texte sur une visibilité limitée à un écran est retiré de l’état actuel.
La case et les préférences de visibilité restent identiques.

## WordPress et langues

Sans titre automatique, le sélecteur apparaît à droite de la première ligne de
ressource ; catégorie, nom et statut restent groupés à gauche. Avec un titre,
il reste dans la barre de titre. Il n’existe qu’un sélecteur, hébergé par le premier
composant OpenFabLab effectivement visible : calendrier, ressources ou réservations.
Les catalogues vides sans information ne créent pas une fausse barre vide.
Sur petit écran, un retour à la ligne est permis, sans rétrécir les textes.

Second clic, choix d’une langue, clic extérieur et Échap referment le menu.
Les flèches, Début/Fin et Tab sont prises en charge avec un focus visible.
Le menu est fermé à l’ouverture d’une fenêtre bloquante. Le contraste reste
lisible en clair et sombre ; les styles sont limités aux composants OpenFabLab.
La protection des saisies avant changement de langue et les préférences restent actives.

Les événements du calendrier ont un survol discret et un focus clavier, sans
changement de dimensions. Les mouvements réduits sont respectés ; le toucher
ne nécessite aucun survol pour consulter les informations.

## Un mois d’historique public, pas un mois de nouvelles réservations

Le jour de référence est celui du fuseau configuré. Exemple : le 3 novembre,
la borne historique est le 3 octobre inclus ; la semaine qui contient cette date
reste affichable, mais ses jours antérieurs ne publient pas d’événement.
Les fins de mois sont bornées au dernier jour existant (31 mars → 28/29 février).
Le serveur et le navigateur appliquent cette limite ; des paramètres URL ne
permettent pas de la contourner. La semaine actuelle reste l’affichage initial.

Le catalogue de réservation et sa règle des 24 heures ne changent pas.
La projection historique est distincte, en lecture seule, et négociée avec
`public_calendar_history_v1`, sans changement du protocole 4/révision 3.
L’ancien format reste envoyé à un ancien plugin ; le nouveau plugin accepte
les projections 2.14.3, sans prétendre inventer des événements absents.

Au-delà de 24 h, une animation n’est reprise que si sa publication reste activée,
si elle appartient au bon environnement, n’est pas masquée et qu’une participation
positive est constatée dans les données. Un ancien zéro ou une absence de saisie
ne prouve pas qu’elle a eu lieu : elle n’est pas inventée comme réalisée. Le modèle
ne possède pas de drapeau de réalisation/annulation distinct ; désactiver ou masquer
l’animation empêche sa publication. Aucune note interne, personne, présence
individuelle, contact ou jeton n’est transmis. Un ancien instantané périmé reste
signalé comme tel ; un événement initialement futur ne devient pas admissible
à l’historique simplement parce que le temps passe sans resynchronisation.

## Noms des documents

Les téléchargements de devis et factures PDF/DOCX utilisent AAAAMMJJ :
`20261023_Devis_StructureFictive_FABLAB_7.pdf`. C’est la date du document, pas
la date du téléchargement lorsqu’une date valide existe. Les contenus, montants,
références, dates imprimées, e-mails et documents déjà enregistrés sont inchangés.

## Migration et sauvegardes

Le seul ajout de schéma est `resources.archived_at TEXT NULL`, SQLite24→25.
Le champ active contrôle déjà les réservations : le réutiliser aurait confondu
archivage et simple désactivation, ou perdu les préférences à la restauration.
Pas de table parallèle, pas d’archivage automatique de ressource existante.
Les anciennes colonnes et données restent identiques ; une exception annule la
transaction, et une réexécution en schéma25 ne rejoue pas les anciens semis.

Sauvegarder intégralement avant mise à jour. Ne jamais démarrer 2.14.3 ou une
ancienne application sur la base25. Les étapes génériques sont dans [le guide de mise à jour](upgrade.md). Les scripts
privés propres à un NAS ne sont pas des procédures publiques. Après ouverture,
préserver les nouvelles écritures avant toute décision de reprise. Le plugin se
remplace séparément sans désinstallation. L’exploitant a confirmé le fonctionnement
de l’application et du plugin 2.14.4 avec SQLite25 ; les tests de préparation utilisent
des données fictives, sans accès à la production.
