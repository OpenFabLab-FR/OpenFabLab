> Référence historique de l’étape 2.14.2, intégrée à la stable 2.14.4.
> Pour une installation actuelle : [utilisation](utilisation.md), [WordPress](wordpress-2.14.4.md)
> et [mise à jour](upgrade.md). Les mentions de candidate ci-dessous décrivent leur époque.

# OpenFabLab 2.14.2 — candidate de consolidation

SQLite **24 reste 24**, sans migration. Aucun changement des réservations,
présences, factures, entretiens, rappels, secrets ou catégories enregistrées.

## Réglages mieux rangés

Structure commence par l’identité. Le suivi d’état et d’entretien se trouve dans
Modules, à côté des Ressources. Il reste indépendant des réservations et de
WordPress. Son bouton enregistre le suivi et le nom public, pas l’identité.
Le programme public des OpenLab et sa moyenne facultative sont regroupés dans
Connexion WordPress. Les horaires habituels restent dans Borne et ne changent pas.
Les formulaires, leurs permissions et leurs protections restent distincts.

Dans Borne, langues, titre personnalisé, sons, horaires et sécurités restent
disponibles. La visibilité des indisponibilités rejoint l’affichage de la borne.
Enregistrer les langues ne réinitialise pas ce choix.

## Ressources, machines, équipements ou salles

Le **Nom public des ressources** propose quatre appellations traduites localement
en français et anglais. Ressources reste le défaut, sans insertion au démarrage.
Ce choix concerne les titres et messages publics de la borne et du catalogue
WordPress. Il ne renomme aucune ressource ni catégorie et n’élargit pas sa visibilité.
L’anglais Equipment utilise des formulations adaptées aux effectifs.

À l’identification, le bouton d’indisponibilité rejoint l’aide « Je n’ai pas mon
badge ou mon identifiant », dans le contenu. Il passe à la ligne sur petit écran.
La caméra et les commandes principales ne sont pas réduites. Avec zéro ressource
indisponible, le bouton reste masqué comme auparavant.

## Moyennes OpenLab sur douze mois glissants

La période va de la date anniversaire de l’année précédente jusqu’à la veille de
la date locale de référence, pas du 1er janvier à aujourd’hui. Le 29 février est
ramené au 28 février lorsque nécessaire. Comparaison par jour de semaine et mêmes
horaires ; fermetures et changements exceptionnels exclus.

Le calcul conserve les séances avec données exploitables, au moins six séances,
les seuils de publication, les arrivées identifiées terminées dédupliquées par
usager/jour et les visiteurs anonymes. Un jour sans données n’est pas un zéro.
Les horaires habituels anciens ne sont pas versionnés : le calcul utilise les
horaires actuels et les exceptions enregistrées. Il mesure des passages enregistrés,
pas l’exhaustivité des personnes accueillies. Les moyennes sont arrondies ; aucune
donnée individuelle ni détail de l’échantillon n’est transmis.

La légende devient « Moyenne calculée sur les 12 derniers mois ». L’option demeure
facultative et désactivée si aucune préférence n’existe.

## Calendrier et sécurité

Les deux filtres du calendrier partagent la même présentation et restent
indépendants. La phrase technique sur l’extension horaire est retirée, sans
modifier le calcul de la plage. Les tentatives d’inscription et d’identification
familiale ont des libellés lisibles ; les codes conservés dans l’audit ne changent pas.

## Plugin et mise à jour

Reservations **2.14.2** est réellement modifié pour le titre public et les moyennes.
Protocole **4/révision 3** inchangé ; capacité facultative
`public_display_options_v1`. Aucun secret ni demande ne change. Avec un ancien
plugin, les nouvelles métadonnées et moyennes ne sont pas envoyées ; les échanges
historiques restent disponibles. Le nouveau plugin accepte aussi les anciens
instantanés 26 semaines, avec une légende adaptée à ces données historiques.
Un seul sélecteur FR/EN reste partagé entre les shortcodes.

Installer le plugin séparément, sans désinstallation. Le paquet DSM privé
2.14.1/24 → 2.14.2/24 ne l’installe pas. Exécuter d’abord son contrôle préalable,
puis examiner le rapport avant toute mise à jour. Ne pas relancer les anciens
paquets de migration. Après réouverture, préserver toutes les nouvelles écritures :
aucune restauration automatique d’une ancienne sauvegarde.
