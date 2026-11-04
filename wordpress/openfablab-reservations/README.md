# OpenFabLab Reservations 2.14.4 — version stable

[Guide complet : installation, Gutenberg et trois shortcodes](https://github.com/OpenFabLab-FR/OpenFabLab/blob/main/docs/wordpress-2.14.4.md).
Le plugin est facultatif, libre sous licence MIT et se met à jour séparément.
Dans Gutenberg, utiliser des blocs Code court :

```text
[openfablab_reservations environment="production"]
[openfablab_calendar environment="production" view="week"]
[openfablab_machines environment="production"]
```

Remplacer production par test uniquement pour l’environnement Test, configuré
séparément. Ne jamais inclure de secret dans un shortcode ou une page.

Sélecteur unique intégré à la première ligne des ressources sans titre, menu
ouvrable/fermable au clic et au clavier, contraste isolé des thèmes, survol des
événements et consultation du calendrier jusqu’à un mois local en arrière.
Les réservations restent retirées après 24 h ; aucune nouvelle réservation
n’est proposée pour un événement passé. Les noms, descriptions et catégories
personnalisés ne sont pas traduits automatiquement.

Protocole 4/révision 3 inchangé. La capacité facultative `public_calendar_history_v1`
négocie une projection historique distincte, validée par liste blanche et limitée
à un mois aussi dans l’API publique. Avec une application 2.14.3, les améliorations
du menu fonctionnent, mais l’historique reste limité aux données déjà synchronisées
par celle-ci. Avec l’application 2.14.4, les anciennes versions du plugin continuent
à recevoir leur format habituel. Ne pas imposer l’égalité des versions pour communiquer.

Mettre à jour depuis 2.14.3 en remplaçant l’extension avec son ZIP, sans
désinstallation ni changement de secret. Conserver les options et files de demandes.

## Titre facultatif du catalogue public

Dans « Calendrier, machines et langues publiques », sous l’activation de la liste,
« Afficher le titre de la liste des ressources » utilise le nom public reçu
d’OpenFabLab (Ressources, Machines, Équipements ou Salles), en français/anglais.
Décochée, cette option n’ajoute ni titre automatique ni espace vide. Un titre
personnalisé peut être ajouté avec un bloc Titre de l’éditeur WordPress.

L’affichage existant est conservé après mise à jour. Une installation neuve
commence sans titre automatique. Le choix explicite est conservé lors d’une
réactivation. Cette préférence ne modifie ni la borne, ni les catégories,
ni la visibilité, ni les trois shortcodes, ni les échanges Normal/Test.
La commande de langue unique reste disponible, même si seul le catalogue est utilisé.
Le nouveau réglage et son aide sont préparés pour gettext WordPress ; le plugin
ne possède pas actuellement de catalogue PHP d’administration FR/EN livré.
Les titres publics prédéfinis utilisent les traductions locales existantes.

## Fonctions conservées depuis 2.14.2

Lorsqu’il est affiché, le titre public reprend l’appellation configurée dans l’application : Ressources,
Machines, Équipements ou Salles. Les moyennes OpenLab opt-in portent sur douze mois
glissants, avec une légende courte FR/EN. La capacité facultative
`public_display_options_v1` négocie ces données ; protocole 4/révision 3 inchangé.
Les anciennes projections restent acceptées, sans exiger l’égalité des versions.
Mise à jour séparée depuis 2.14.1, sans désinstallation ni modification des secrets.

## Fonctions conservées depuis 2.14.1

En 2.14.1, les shortcodes calendrier et machines sont disponibles dès init sur le
frontend et dans les blocs Shortcode Gutenberg, sans initialisation REST préalable.
Le même réglage « Permettre aux visiteurs de changer de langue » contrôle les trois
interfaces publiques. Protocole 4/révision 3, secrets et files durables inchangés.

Un seul sélecteur de langue par page contrôle tous les modules et s’intègre au
premier module visible. Les listes vides ne laissent aucun bloc ni sélecteur
orphelin ; une erreur de synchronisation reste distincte. Les dates suivent FR/EN.
Le calendrier reprend les descriptions publiques et capacités par créneau, ainsi
qu’un texte OpenLab informatif. Une moyenne agrégée peut être publiée uniquement
si la structure l’a explicitement activée et si les seuils statistiques sont remplis.
La capacité facultative `public_resources_details_v1` négocie ces détails ; le
numéro du protocole ne change pas.

Extension facultative, libre et gratuite sous licence MIT. Protocole 4/révision 3
conservé. Le moteur OpenFabLab décide toujours des places et des inscriptions.

Nouveaux shortcodes indépendants, à activer dans les réglages du plugin :

```text
[openfablab_calendar environment="production" view="week"]
[openfablab_machines environment="production"]
[openfablab_resources environment="production" category="machine"]
```

Le calendrier présente les seuls OpenLab autorisés et animations publiées.
La liste des ressources ne reçoit que les informations explicitement publiques.
`openfablab_resources` est un alias de `openfablab_machines`, qui reste compatible.
Le filtre `category` est facultatif et utilise la clé de catégorie de la structure.
Les échanges Normal/Test sont distincts ; une information ancienne est signalée.
Les notes internes et données des participants ne font pas partie de ces flux.

Le multilingue public est indépendant, désactivé par défaut : FR/EN, langue
initiale configurable et choix du navigateur. Les textes personnalisés restent
dans leur langue d’origine. Après confirmation réelle, la page personnelle peut
proposer .ics et Google Agenda, sans accès à un compte de calendrier.

Remplacer le plugin après sauvegarde, sans désinstallation ni changement du secret.
La mise à jour d’OpenFabLab sur un serveur ne l’installe pas sur WordPress.
Les instructions historiques et le shortcode de réservation restent ci-dessous.

---

# OpenFabLab Reservations 2.13.0 — plugin facultatif

Adaptation du catalogue à la visibilité avant ouverture et au maintien des
animations terminées pendant 24 heures. Aucun changement d’attribution des
places, de signatures ou de secrets. Protocole 4/révision 3 conservé ; capacité
optionnelle `publication_visibility_v1`.

À utiliser avec OpenFabLab 2.13.0 pour l’ensemble des affichages.
Les anciens catalogues restent acceptés. Les nouvelles règles d’ouverture et
la limite de 24 heures sont appliquées côté serveur aux instantanés signés.
Installer en remplacement, sans désinstallation ni changement du secret.
Ce plugin n’est pas obligatoire pour utiliser OpenFabLab.

[Release officielle 2.13.0](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.13.0) ·
[Documentation actuelle](https://github.com/OpenFabLab-FR/OpenFabLab/blob/v2.13.0/docs/wordpress.md).
L'archive validée est conservée octet pour octet ; les mentions de préparation
dans sa documentation figée ne changent pas son statut stable.
Les numéros de version publique sont indépendants du protocole.

---

## Référence historique : Reservations 2.11.0

Application et plugin OpenFabLab 2.11.0, protocole 4/révision 3 inchangé.
Cette version actualise le numéro public et la documentation ; le moteur du
relais, ses signatures, ses capacités et ses ressources restent inchangés depuis
2.10.1. Les présences automatiques restent internes à OpenFabLab : elles ne
déclenchent ni inscription ni courriel de réservation. Installer sans désinstaller
l’extension ni changer les secrets. Aucune connexion entrante vers OpenFabLab
n’est nécessaire. Les paragraphes suivants sont les références historiques.

[Release officielle](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.11.0) ·
[Guide WordPress](https://github.com/OpenFabLab-FR/OpenFabLab/blob/v2.11.0/docs/wordpress.md).
L’archive approuvée est distribuée à l’identique, sans reconstruction.
OpenFabLab reste utilisable sans WordPress ; les mentions de préparation dans
le README figé du ZIP sont historiques. La documentation de ce tag fait référence.

---

## Référence historique : OpenFabLab Reservations 2.10.1

Extension libre sous licence MIT. [Release officielle](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.10.1)
et [guide WordPress à jour](https://github.com/OpenFabLab-FR/OpenFabLab/blob/v2.10.1/docs/wordpress.md).
Le ZIP approuvé est distribué à l’identique : son README figé peut garder une
mention de préparation. La documentation de ce tag fait référence.

Plugin facultatif pour OpenFabLab 2.10.1 ; catalogue 2.10.0 accepté pendant la
transition. Protocole 4 / révision 3, capacité `waitlist_limits_v1` inchangés.
Présentation par créneau : places disponibles, attente ouverte ou saturée,
états fermés, récapitulatif distinguant réservation et attente. Le moteur
OpenFabLab conserve seul l’attribution transactionnelle des places.

Mettre à jour OpenFabLab avant le plugin. Sauvegarder les deux installations,
puis remplacer le ZIP du plugin sans désinstaller ni changer ses secrets.
Le numéro public du plugin suit désormais celui de l’application ; il ne sert
pas de condition d’authentification ou de compatibilité du relais.

## Référence historique : Reservations 2.9.0

Plugin facultatif pour OpenFabLab **2.9.0**, protocole **4 / révision 3**.
Capacité optionnelle `waitlist_limits_v1` : compteur d’attente et états de
fermeture transmis par OpenFabLab, indicateurs pastel sous les horaires et
boutons au pied des cartes. Le catalogue antérieur reste accepté explicitement.
OpenFabLab contacte ce site en HTTPS signé pour publier le catalogue, relever
les demandes et retourner les décisions. WordPress ne décide jamais des places.
Aucune adresse entrante du NAS ni reverse proxy n’est nécessaire.
Plugin facultatif : OpenFabLab reste utilisable sans WordPress. Le ZIP officiel
2.9.0 est distribué sans modification ; les instructions stables sont disponibles
dans le [guide WordPress](../../docs/wordpress.md) du dépôt.

PHP 8.1+, OpenSSL AES-GCM, InnoDB, REST, HTTPS et JavaScript nécessaires.
Shortcodes : `[openfablab_reservations environment="production"]` pour Normal,
`[openfablab_reservations environment="test"]` pour Test.

Le réglage OpenFabLab « Compte obligatoire » est désactivé par défaut : réservation
familiale avec compte ou inscription individuelle autonome sans compte, coordonnées
et date de naissance. Aucun compte n’est créé. E-mail requis, téléphone selon
la règle OpenFabLab. Un compte se retrouve par QR quatre chiffres ou saisie,
toujours avec vérification d’e-mail/téléphone. Caméra frontale préférée, images
traitées localement, aucune capture ni transmission. Saisie manuelle disponible.

Avant remplacement, fermer temporairement la page publique, laisser finir les
demandes, sauvegarder WordPress (base/options/secret) et OpenFabLab (PRE 19/image).
Extensions → Ajouter → Téléverser le ZIP → remplacer la version existante,
**sans désinstaller** et sans changer le secret. Mettre à jour OpenFabLab et
attendre le premier catalogue Normal/Test avant réouverture. Le plugin révision
3 ne fonctionne pas avec le moteur 2.8.1 révision 2 ; l’attente est normale
pendant la bascule. Lire `docs/reservations-2.8.2.md` dans l’application.

Les apports 2.8.5 conservés enrichissent la page personnelle « Gérer ma réservation » et ajoutent
le lien facultatif « En savoir plus » reçu du moteur. La révision reste 3 : la
capacité `animation_information_v1` est annoncée explicitement. OpenFabLab 2.8.5
reste compatible avec le plugin officiel 2.8.2 (sans ce lien de catalogue) ; le
plugin 2.8.5 accepte aussi le catalogue 2.8.4. Le stockage WordPress est inchangé.
Annuler passe par une deuxième étape et une confirmation explicite. Aucun GET ne
déclenche d’annulation et WordPress attend la décision du moteur.
