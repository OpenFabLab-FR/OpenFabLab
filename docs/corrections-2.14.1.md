> Référence historique de l’étape 2.14.1, intégrée à la stable 2.14.4.
> Pour une installation actuelle : [utilisation](utilisation.md), [WordPress](wordpress-2.14.4.md)
> et [mise à jour](upgrade.md). Les mentions de candidate ci-dessous décrivent leur époque.

# OpenFabLab 2.14.1 — consolidation des fonctions 2.14

## Un seul registre de ressources

**Activités → Gestion des ressources** centralise les noms, catégories, descriptions,
couleurs et options de réservation. **Maintenance**, juste à droite, suit l’état,
les interventions et les rappels de ces mêmes fiches. Les anciennes adresses de
maintenance redirigent vers les nouvelles. Aucun rapprochement par nom n’est fait.
Les équipements de location conservent leur lien `legacy_machine_key`, leurs
identifiants et leurs associations de facturation. Deux équipements similaires
restent distincts. Une salle ou une catégorie personnalisée peut aussi être suivie.

**Disponible** indique l’état de la ressource, pas sa possibilité de réservation.
Le champ **Activer la réservation de cette ressource** reste indépendant. Une
indisponibilité bloque les nouvelles réservations selon les règles existantes et
signale celles à examiner, sans les annuler. Les anciens dossiers et tarifs restent
préservés. La couleur se choisit dans une palette ; Couleur par défaut réutilise la catégorie.

## Suivi des ressources

La fiche regroupe l’état de la ressource, l’historique des interventions et les
rappels à venir. Les formulaires d’ajout sont repliés. Une ressource disponible
n’affiche pas les champs d’indisponibilité. Une ancienne panne reste dans
l’historique ; son motif et sa date ne sont pas repris lors d’une nouvelle panne.

Une seule option, **Afficher cette ressource aux usagers**, contrôle la visibilité
commune à la borne et au catalogue WordPress. Les réglages généraux restent
prioritaires : le catalogue du plugin doit être activé, et la borne peut masquer
les informations de ressources. Une ressource disponible n’émet jamais une annonce
d’indisponibilité. Les interventions et notes internes restent privées.

Les anciennes options distinctes restent stockées pour la traçabilité, sans
nouveau stockage parallèle. Une ancienne visibilité limitée à un seul canal
conserve exactement son périmètre antérieur tant qu’un membre de
l’équipe ne confirme pas explicitement la case unique. Par exemple, une ressource
disponible autorisée uniquement sur WordPress continue d’y apparaître sans
déclencher d’annonce sur la borne. Aucun canal public
supplémentaire n’est ouvert silencieusement. Une ancienne date non publiée n’est
pas préremplie dans le champ destiné à la publication.

Les types proposés sont Entretien / prévention, Réparation, Vérification et Autre.
Les anciennes interventions « Maintenance préventive » conservent leur valeur et
restent consultables et corrigeables. Enregistrer un travail ne change plus l’état
de la ressource : celui-ci se règle dans la section dédiée. Les dates et actions
de l’historique sont lisibles dans le fuseau configuré ; la trace originale reste en base.

## Du rappel à l’intervention

Créer un rappel demande seulement une date et un objet. Il est « À venir » et
apparaît au calendrier. **Enregistrer l’intervention** ouvre le formulaire pour
la bonne ressource et le rappel choisi. La validation réussie marque uniquement
ce rappel comme traité et conserve un lien vers le travail effectué.

Reporter, annuler ou classer sans intervention sont des actions distinctes.
Les mises à jour vérifient la révision et l’état du rappel : un double envoi ou
une intervention refusée ne crée pas une deuxième intervention ou un rappel
faussement traité. Discord ne termine jamais les rappels. Administrateurs et
modérateurs habilités conservent leurs droits et les contrôles CSRF.

## Calendrier et réglages

Le filtre **Afficher entretiens et rappels** a un état explicite, conservé entre
semaines et mois. Il ne supprime aucune donnée. Les **Horaires exceptionnels**
couvrent les fermetures, ouvertures supplémentaires et changements ponctuels.
Une fermeture retire l’OpenLab habituel du calendrier public sans case de
publication supplémentaire. Les horaires et options inutiles sont masqués.

Les réglages **Suivi des ressources** et **Programme des OpenLab** sont compacts,
avec formulaires indépendants. Les statistiques et passages restent inchangés.

## Langues

Le choix FR/EN est compact, avec un menu Français / English. Dans Borne,
**Permettre aux usagers de changer de langue** est actif par défaut si plusieurs
langues sont proposées. Sa désactivation masque le sélecteur public et rétablit
la langue principale, sans modifier la langue de l’administration.

Le plugin conserve son option existante, renommée **Permettre aux visiteurs de
changer de langue**. Désactivée, elle masque le sélecteur des réservations,
du calendrier et des machines, et ignore une ancienne langue publique mémorisée.
Les textes personnalisés par la structure ne sont jamais traduits automatiquement.

Sur une page WordPress, un seul sélecteur s’intègre à l’en-tête du premier module
effectivement visible, quel que soit l’ordre des shortcodes. Il contrôle tous les
modules de cette page. Le choix est mémorisé pour cette page et cette session, sans
changer la langue du serveur ni celle d’un autre visiteur. Un changement recharge
les interfaces ensemble ; un formulaire en cours demande confirmation avant de
perdre sa saisie. Les demandes déjà envoyées conservent leur suivi existant.

## WordPress

Reservations 2.14.1 corrige l’enregistrement des shortcodes calendrier et machines
pendant `init`, indépendamment de `rest_api_init`. Le shortcode historique reste
disponible. Protocole 4/révision 3 inchangé ; aucune réinitialisation des secrets,
options ou demandes. Installer le ZIP dans WordPress en remplaçant la version
existante, sans désinstallation ; la mise à jour NAS ne le fait pas.

Le shortcode `[openfablab_machines]` est conservé ; `[openfablab_resources]` en est
un alias pour toutes les catégories autorisées. `category="machine"`, ou la clé
d’une catégorie personnalisée, permet de filtrer. Aucun catalogue vide ni sélecteur
orphelin ne s’affiche. Une véritable indisponibilité de synchronisation reste signalée.
Les instantanés signés sont remplacés lors des échanges, séparément pour Normal/Test ;
les lectures publiques demandent `no-store`. Recharger la page après un nouvel échange
permet de consulter le nouvel état. Aucune fiche historique n’a à être recréée.
Les ressources JavaScript/CSS publiques portent une empreinte de contenu, comme
les réservations, afin de ne pas garder les fichiers d’une ancienne candidate.
Si le site utilise un cache de pages supplémentaire, le rafraîchir après remplacement
du plugin, sans toucher aux files de demandes ni aux secrets.

Les périodes et dates sont localisées FR/EN. Les détails d’animation reprennent
la description publique déjà saisie et la capacité réelle du créneau, sans publier
les participants. Les longs textes restent défilables. Les nouveaux détails sont
négociés par la capacité facultative `public_resources_details_v1` ; protocole
4/révision 3 inchangé. Un ancien plugin reçoit toujours la projection historique.

## Moyenne publique OpenLab : option et méthode

L’option **Publier une moyenne de fréquentation des OpenLab**, dans Programme des
OpenLab, est **désactivée par défaut**. Le détail d’une ouverture peut alors présenter
une moyenne arrondie d’usagers identifiés et de visiteurs, jamais une présence en direct.

La période porte sur les 26 dernières semaines terminées la veille. On retient les
journées du même jour de semaine, dans le même créneau horaire configuré, où des
passages ont réellement été mesurés. Les fermetures et exceptions à horaires différents
sont exclues. Les usagers sont dédupliqués par journée à partir des arrivées dont la
présence est terminée ; les visiteurs correspondent aux déclarations anonymes dans
ce même créneau. Les journées sans mesure sont inconnues, pas des zéros supposés.

Publication uniquement avec au moins six journées observées, au moins cinq usagers
distincts dans l’ensemble et une moyenne d’au moins cinq usagers. S’il existe de un
à quatre visiteurs au total, la moyenne entière est également masquée. Seuls les
deux chiffres arrondis, la période et la méthode sont transmis, sans échantillon,
date individuelle, identifiant ou donnée brute. Aucun croisement démographique.

Limite : les anciens horaires habituels n’étant pas versionnés, le créneau actuel
sert de référence, corrigé par les exceptions conservées. Le libellé parle donc de
séances avec passages enregistrés, jamais d’un recensement exhaustif des ouvertures.
L’option peut rester désactivée si la structure juge cet historique peu représentatif.

## SQLite 24 : justification et précautions

La contrainte de SQLite 23 interdisait le nouveau type « Vérification ». Avec
l’accord de l’exploitant, 2.14.1 utilise SQLite **24**. La migration 23 → 24
élargit seulement cette contrainte. Le moteur de migration existant reconstruit
transactionnellement les tables concernées, conserve les colonnes, identifiants,
rowids, valeurs, liens, index et traces ; aucune catégorie historique n’est réécrite.
Aucune nouvelle table métier durable n’est créée. Le lien rappel/intervention
utilise la colonne déjà présente en 23.

Sauvegarder l’installation complète avant migration, vérifier l’intégrité et les
clés étrangères, puis produire POST24. **Ne jamais démarrer 2.14.0 sur une base 24.**
Ne pas utiliser les anciens paquets 22 → 23 ni les outils de reprise POST23.
Après ouverture publique, conserver les nouvelles écritures : aucune restauration
d’une ancienne base ne doit être automatique.

Les essais DSM/Docker restent des simulations locales ; l’exploitant doit d’abord
exécuter le contrôle privé `--check` puis transmettre son rapport. Aucun déploiement
ni publication ne fait partie de la préparation de cette candidate.
