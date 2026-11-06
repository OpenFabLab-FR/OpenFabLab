# Ressources et maintenance — 2.15.5

L’état d’une ressource, les créneaux de maintenance planifiés et les rappels
sont distincts. Les maintenances multijours apparaissent sur une bande
continue par semaine dans le calendrier interne. Une date de retour
estimée ne crée pas de journée supplémentaire et ne remet pas la ressource
en service automatiquement. Un signalement via le QR reste facultatif et
ne change pas l’état de la machine.

La fiche unifiée regroupe configuration, état, visibilité, réservations,
locations, interventions, rappels, documents et actions d’archivage selon les
droits. Le tri est alphabétique naturel. Une réservation confirmée n’est pas
une remise effective : enregistrer séparément la remise et le retour.
Les prêts gratuits apparaissent dans le Résumé comme les prêts payants.

Les QR permanents peuvent viser une fiche publique OpenFabLab sur le réseau
local ou via HTTPS. Choisir la visibilité des ressources et des tutoriels
séparément ; ne publier ni notes internes ni identité d’un emprunteur.
[QR et accès](upgrade-2.15.1.md#qr-des-ressources) · [Prêts, documents et rôles](evolution-2.15.0.md).
La suite conserve les références historiques de la 2.14.4.

---

# Ressources, état et maintenance — OpenFabLab 2.14.4

| Notion | Signification |
| --- | --- |
| Disponible | État technique ; ne prouve pas qu’un créneau est libre. |
| Réservation activée | Proposition possible selon droits, règles et disponibilités horaires. |
| En maintenance / Hors service | Indisponibilité temporaire, sans annulation silencieuse des réservations. |
| Archivée | Retirée des usages actifs/publics, conservée avec son historique. |

Une ressource disponible peut être non réservable, occupée ou soumise à habilitation.
L’archivage n’est pas un état de panne.

## Créer et organiser

Activités → Gestion des ressources : créer machine, salle ou catégorie personnalisée.
Définir séparément réservations, tarification, confirmations et habilitation requise.
Les ressources provenant des anciens catalogues de location conservent leur lien
historique ; ne pas les supprimer/recréer pour changer leur nom. Les dossiers
conservent leurs instantanés de tarifs.

Réglages → Structure → Modules distingue gestion des ressources et suivi
d’état/entretien. Le suivi ne dépend pas de WordPress. Le nom public se choisit
parmi Ressources, Machines, Équipements et Salles, avec pluriels FR/EN ; il ne
renomme ni les fiches ni leurs catégories.

## État et visibilité choisie

La fiche regroupe État, Historique des interventions et Rappels à venir ; les
formulaires se déplient à la demande. En maintenance ou Hors service permet de
préciser un motif public facultatif et une date estimée de retour pertinente.
Ces champs sont masqués lorsque la ressource est disponible ; une ancienne panne
n’est pas republiée automatiquement à l’occasion d’un nouvel incident.

« Afficher cette ressource aux usagers » autorise la borne et le catalogue
WordPress selon leurs activations globales. Les anciennes visibilités dissociées
ne sont pas élargies silencieusement : confirmer volontairement la visibilité
commune si nécessaire. Le catalogue doit aussi être activé dans le plugin.
Une ressource disponible n’annonce jamais de panne. Notes, auteurs, interventions
et historiques internes ne sont jamais publics.

La borne affiche les indisponibilités sur l’accueil, l’identification, les deux ou
aucun écran selon ses réglages. La liste de présence manuelle n’affiche plus ce
bouton. La caméra QR conserve son espace.

## Interventions et rappels

Administrateurs et modérateurs autorisés peuvent enregistrer date, type
Entretien/prévention, Réparation, Vérification ou Autre, et travail réalisé.
Les anciens types restent lisibles. Une intervention ne remet pas automatiquement
la machine en service : son état se modifie séparément, avec traçabilité.

Un rappel demande une date et un objet ; il devient À venir, apparaît au calendrier
et peut notifier Discord si cette option est activée. « Enregistrer l’intervention »
depuis ce rappel ouvre la bonne fiche et conserve l’association choisie. Le rappel
est traité seulement après réussite. Une intervention indépendante ne termine pas
tous les rappels de la ressource. Report, annulation et classement sans intervention
restent volontaires.

Discord ne termine pas les rappels. Les notifications respectent le fuseau local
et les protections durables anti-doublons ; une incertitude n’est pas rejouée
automatiquement. Les dates sont lisibles en FR/EN. La mise à jour ne rattrape pas
les anciennes échéances. La liste chronologique conserve détails et corrections.
L’auteur peut être le rôle authentifié connu, pas une identité nominative inventée.

## Archiver et restaurer

Administrateur → Autres actions → Archiver cette ressource. Refus tant qu’il reste
des demandes non traitées, des réservations confirmées non terminées, des locations
en cours/futures ou des rappels à traiter, même en retard. Les traiter ou annuler
volontairement dans leur espace habituel ; aucune suppression automatique.

L’archive disparaît des listes actives, nouvelles réservations/locations, catalogues
publics et annonces de la borne, sans supprimer ses dossiers. Le filtre « Afficher
les ressources archivées » permet de retrouver l’historique. L’administrateur peut
restaurer les réglages antérieurs sans réactivation forcée des réservations ou
élargissement de visibilité. Réactiver d’abord une habilitation inactive lorsqu’elle
est requise par la ressource réservée.

## Supprimer une fiche créée par erreur

Administrateur uniquement, avec confirmation explicite distincte. Le serveur
refuse toute dépendance : état/historique, intervention, rappel, réservation,
location, facture, lien au catalogue historique ou référence par clé étrangère.
Le refus propose l’archivage. Aucune cascade métier ; les audits de création et
suppression restent conservés. Les modérateurs gardent leurs droits de suivi,
sans pouvoir archiver, restaurer ou supprimer par ces commandes.

## SQLite 25

La colonne nullable `resources.archived_at` distingue l’archive de `active`, qui
contrôle déjà la réservation. Depuis le schéma24, c’est le seul ajout : aucune
ressource n’est archivée automatiquement, aucune ancienne valeur n’est réécrite.
Les sources plus anciennes utilisent le moteur de migration existant.
[Mise à jour et sauvegardes](upgrade.md).
