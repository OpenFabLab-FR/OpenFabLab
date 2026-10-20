# OpenFabLab 2.11.0 — version stable

Cette version améliore la stable 2.10.1 et a été validée en utilisation réelle.
Vérifier les livrables et effectuer une sauvegarde complète avant installation.
Application et plugin facultatif Reservations : **2.11.0**. Le protocole reste
**4 / révision 3**, avec les capacités existantes, sans exigence d’égalité des versions.

[Release et SHA256SUMS](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.11.0).
Les ZIP approuvés sont distribués sans reconstruction ; leurs guides figés
peuvent conserver une mention de préparation. La documentation de ce tag fait référence.

## Présences aux animations

Dans Réglages → Structure, **Validation automatique des présences aux animations**
est activée par défaut, désactivable et exportable dans le profil de configuration.
Seule une inscription **déjà confirmée et rattachée de façon vérifiée au compte**
peut être marquée présente. La présence réelle à la borne doit chevaucher les
horaires de l’animation, ou du créneau réservé. L’arrivée et le départ sont pris
en compte. Un responsable ne pointe jamais à la place de ses enfants.

Un usager non inscrit, un visiteur, une personne en attente ou une inscription
annulée ne sont pas ajoutés. Aucune place supplémentaire, réservation, promotion,
confirmation par e-mail ou notification Discord n’est créée par cette détection.
Les animations simultanées ambiguës sont laissées à la validation manuelle.

Le contrôle intervient après les pointages et dans le cycle de maintenance
existant, toutes les 30 secondes environ, sans ouverture de la page Inscriptions.
Il porte sur la journée locale courante, à partir de l’installation de la
fonction ou de sa dernière réactivation : pas de recalcul des anciennes animations
ni de rattrapage des journées terminées. Les heures locales ambiguës ou inexistantes
au changement d’heure ne sont pas interprétées arbitrairement.

Les administrateurs et modérateurs autorisés peuvent choisir Présent, Absent
ou Non renseigné. Leur choix reste prioritaire, y compris Non renseigné : la borne
ne le remplace pas silencieusement. L’origine apparaît discrètement dans Inscriptions.
Désactiver la fonction conserve les présences acquises ; la réactiver ne rejoue
pas la période désactivée. Les modules Fréquentation, Usagers et Activités doivent
être actifs pour l’automatisation ; WordPress et Abonnements ne sont pas nécessaires.

## Capacités et participation réelle

Le seul champ principal **Places maximum** alimente la capacité des réservations.
Si les deux anciens champs étaient différents, la capacité de réservation déjà
appliquée est présentée à l’édition ; aucune valeur historique n’est réécrite à
l’installation. L’enregistrement explicite de la fiche harmonise les champs.
Les diminutions protégées par des inscriptions existantes restent refusées.
Quand le module de réservation est désactivé, ses capacités sont conservées.

En mode créneaux, le total est calculé à partir des créneaux. Les capacités
particulières déjà enregistrées sont conservées : modifier la capacité usuelle
ne remplace pas ces exceptions. Les horaires avec inscriptions restent protégés.

Le champ Participants sur place quitte la fiche d’animation. Dans **Inscriptions**,
le bloc repliable **Participants non inscrits** permet d’enregistrer un total
anonyme, de le corriger, ou de le remettre à zéro. La valeur proposée est 1 pour
un premier ajout. Il s’agit du **total**, pas d’un bouton de cumul : renvoyer
le même formulaire ne compte pas deux fois les personnes.

Les anciens comptages sont conservés. Il n’est demandé aucune identité et aucune
fiche, inscription ou session de fréquentation n’est créée. Une participation réelle
supérieure à la capacité reste possible, sans ouvrir de place publique supplémentaire.

- Encore attendus : confirmés dont la présence n’est pas renseignée.
- Participation réelle : inscrits présents + participants anonymes non inscrits.
- Une absence explicite n’est pas un participant encore attendu.

Les statistiques d’animations utilisent la participation réelle. L’export des
inscriptions conserve ses véritables lignes de réservation : il ne crée pas de
fausses lignes nominatives pour les anonymes. Les exports d’animations conservent
le total de participation réelle. Les statistiques de fréquentation quotidienne
restent indépendantes des comptages anonymes des animations.

## Borne et sons

Les cartes des présents offrent une hauteur minimale de 88 px, une surface
entièrement sélectionnable et un nom au-dessus de la catégorie. La confirmation
de départ, les compteurs, les thèmes et le timer existant sont conservés.

Deux ambiances synthétiques locales sont ajoutées : **Pâques**, carillons clairs
et légers ; **Saint-Valentin**, tonalités chaleureuses et brèves. Navigation,
arrivée, départ, visiteur, erreur, avertissement et compte à rebours conservent
leurs significations. Il n’y a ni fichier musical tiers, ni microphone, ni réseau.
Le code original est sous licence MIT ; les anciennes ambiances sont inchangées.

En automatique, les thèmes visuels existants sélectionnent leur ambiance ;
Dark utilise Classique. Un choix sonore manuel reste prioritaire. Volume,
désactivation et choix du compte à rebours sont conservés. Le volume initial
reste 50 %, les sons activés en absence de préférence explicite. Les restrictions
audio du navigateur sont respectées : une absence de son ne bloque jamais la borne.

## SQLite et mise à jour

**Schéma 21 → 22**, transactionnel et additif : deux petites tables pour l’origine
des présences et les comptages anonymes, index et maintien des totaux. Les tables
historiques gardent leurs colonnes, identifiants et lignes ; aucune présence ancienne
n’est recalculée pendant la migration. Une sauvegarde préalable et les contrôles
d’intégrité restent indispensables. Les réglages existants ne sont pas réinitialisés.

Ne jamais ouvrir une base 22 avec le runtime 2.10.1. Un éventuel retour arrière
nécessite une décision hors ligne portant sur un état complet cohérent ; aucune
restauration d’une ancienne base n’est autorisée après une reprise publique ayant
pu enregistrer des données nouvelles.

Le plugin 2.11.0 est installable comme les précédents ; son moteur et son protocole
ne changent pas. L’application fonctionne sans WordPress. Les abonnements restent
facultatifs et désactivés par défaut. Voir [mise à jour](upgrade.md), [sauvegardes](backup-restore.md)
et [compatibilité WordPress](wordpress.md).
