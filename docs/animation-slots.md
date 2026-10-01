# Réservations classiques et par créneaux

## Mode classique

« Réservation pour toute l'animation » reste le mode de toutes les anciennes animations. La capacité concerne la plage globale, par exemple 10:00–12:00. Une réservation annulée/expirée ou uniquement en attente ne compte pas comme inscrite avec place ; une offre de place réserve sa capacité selon le modèle actuel. Présence et réservation restent indépendantes.

## Mode créneaux

Choisir « Réservation par créneaux horaires », durée usager, battement et capacité par créneau. Prévisualiser avant enregistrement. Exemple **Découverte casque VR** :

| Plage globale | Durée usager | Battement | Capacité par créneau |
| --- | --- | --- | --- |
| 10:00–12:00 | 20 min | 10 min | 1 |

Créneaux : **10:00–10:20, 10:30–10:50, 11:00–11:20, 11:30–11:50**. Quatre personnes au total. Avec deux places par créneau : huit personnes. Sans battement : six créneaux de vingt minutes. Le battement n'est pas affiché comme temps réservé ; aucun créneau ne dépasse la fin de l'animation.

Une clé `slot_uuid` stable identifie le créneau, selon animation, environnement et horaires. La géométrie ne dépend pas d'un libellé affiché. Les changements de capacité peuvent conserver les identifiants ; une modification qui invaliderait des réservations est refusée. Ne pas déplacer/supprimer silencieusement une inscription existante.

## Capacité, attente et accompagnants

Chaque créneau a sa propre capacité. Une réservation ne consomme rien sur les autres créneaux. Si un accompagnant occupe une place, il est dans le même créneau et consomme une place supplémentaire ; une paire ne tient pas dans une capacité de un. La liste d'attente et ses offres FIFO restent rattachées au créneau demandé. Une annulation ne libère/promote que ce créneau.

## Suivi et exports

Les inscriptions affichent et regroupent les créneaux, avec synthèse réservé/capacité et attente. CSV/PDF incluent « Créneau ». L'export calendrier reste **un seul événement global**.

Colonne Participants : classique `4 places / 3 inscrits / 2 présents` ; créneaux `4 créneaux / 3 inscrits / 2 présents`. Singuliers/pluriels adaptés. Une deuxième ligne d'attente n'apparaît que si elle est non nulle.

Commencer un test réel dans l'environnement Test, avec des participants consentants ; ne pas générer de faux comptes ou de réservations de production pour tester.
