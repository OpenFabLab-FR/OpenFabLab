> Référence historique de l’étape 2.14.0, intégrée à la stable 2.14.4.
> Pour une installation actuelle : [utilisation](utilisation.md), [WordPress](wordpress-2.14.4.md)
> et [mise à jour](upgrade.md). Les mentions de candidate ci-dessous décrivent leur époque.

# Reservations 2.14.0 — calendriers, machines et langues

Le plugin reste facultatif. Son numéro évolue ici parce que son code a réellement
changé. La mise à jour du NAS ne l’installe pas sur WordPress.

## Installation et activation

Sauvegarder WordPress. Remplacer l’extension par le ZIP 2.14.0 sans désinstallation,
sans changer la clé partagée. Contrôler séparément Normal et Test. Le protocole
reste 4/révision 3 ; les numéros publics des deux composants ne sont pas comparés
pour autoriser une communication compatible.

Le shortcode de réservation existant est conservé. Dans Réglages → OpenFabLab
Reservations, le calendrier, la liste des machines et le multilingue possèdent
leurs propres activations, toutes désactivées initialement.

## Calendrier public

```text
[openfablab_calendar environment="production" view="week"]
```

La semaine est présentée en grille sur ordinateur et par jour sur mobile, avec
précédente, suivante et Aujourd’hui. Seuls les OpenLab autorisés et les animations
publiées apparaissent. Les fermetures et horaires exceptionnels sont pris en compte.
L’interface respecte l’ouverture des inscriptions et le maintien de 24 h après fin.

Une page de réservation facultative permet de rejoindre le parcours existant ;
le lien d’information public de l’animation est privilégié lorsqu’il existe.
WordPress ne décide jamais des places. Les disponibilités affichées restent celles
du dernier échange, et OpenFabLab recontrôle toute demande.

Les projections couvrent environ trois mois, avec une semaine antérieure.
Une période non couverte et un échange vieux de plus de quinze minutes sont
signalés. Ce calendrier n’est pas une vue illimitée des archives internes.

## Machines

```text
[openfablab_machines environment="production"]
```

Le choix des machines, l’annonce d’indisponibilité et la date de retour publiable
se règlent dans OpenFabLab. Seuls le nom, l’état, le motif public et l’éventuelle
date estimative autorisée sont reçus. Aucune note, auteur, intervention ou identité.
Opérationnelle ne signifie pas immédiatement libre ou réservable.

Les deux nouveaux shortcodes peuvent être utilisés seuls ou ensemble. Remplacer
`production` par `test` pour une page de test explicite. Les projections et leurs
dates de réception sont stockées séparément par environnement.

## Langues et calendrier personnel

Le réglage de langue du plugin est indépendant du NAS et de la borne. Choisir
FR ou EN par défaut ; le visiteur peut changer lorsque le multilingue est activé.
Un changement volontaire prévient avant l’effacement d’un formulaire rempli.
Les descriptions personnalisées restent dans leur langue d’origine.

Une réservation confirmée peut présenter un fichier `.ics` et Google Agenda,
sans accès aux comptes de calendrier. Un groupe en attente n’obtient pas de
confirmation de calendrier. Les liens personnels restent privés et temporaires ;
ils ne sont jamais inclus dans les nouveaux flux publics.

## Sécurité et compatibilité

Les capacités `public_calendar_v1`, `public_machines_v1` et
`participant_calendar_v1` sont optionnelles et négociées. HTTPS, signatures,
horodatages, nonces, protections des formulaires et relais exclusivement sortant
sont conservés. Aucun port entrant vers le NAS n’est demandé.

Le calendrier interne n’est jamais sérialisé pour ces flux. Les listes publiques
sont préparées explicitement et validées par liste blanche côté WordPress.
Les interfaces continuent à fonctionner sans les nouveaux shortcodes.

Avec un plugin 2.13, les réservations, annulations, listes d’attente et publications
antérieures restent possibles selon les capacités négociées. Les nouveaux écrans
publics nécessitent le plugin 2.14. Une publication ou une archive locale ne prouve
pas que cette version est réellement installée sur un site.
