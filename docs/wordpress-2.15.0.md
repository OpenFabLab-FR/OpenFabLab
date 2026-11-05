# Plugin OpenFabLab Reservations 2.15.0

Archive inchangée et compatible avec OpenFabLab 2.15.1. Si elle est
déjà installée et fonctionne, aucune opération WordPress n’est nécessaire.

Remplacer le plugin depuis **Extensions → Ajouter → Téléverser**, puis accepter
le remplacement du ZIP existant. Ne pas désinstaller, effacer les tables, changer
le secret ou recréer les pages. La mise à jour NAS ne l’installe pas sur WordPress.
Les sauvegardes WordPress habituelles restent nécessaires.

Les shortcodes et les environnements restent identiques :

```text
[openfablab_reservations environment="production"]
[openfablab_calendar environment="production" view="week"]
[openfablab_machines environment="production"]
```

L’alias `openfablab_resources` reste accepté. Utiliser un bloc **Code court**
Gutenberg. WordPress conserve la responsabilité des titres et textes éditoriaux.
L’option du titre automatique des ressources et son choix existant sont conservés.

Cinq langues locales : FR/EN/DE/ES/FI, un seul sélecteur pour les composants de
la page. Le choix public est indépendant de la langue de l’administration
WordPress, dont les nouveaux libellés suivent la langue du compte. Les noms et
descriptions personnalisés ne sont pas traduits automatiquement.

Le protocole reste **4/révision 3**. La capacité facultative
`resource_availability_v1` transporte Disponible à la location, En prêt et Retour
en retard. Le catalogue suit le nom affiché en ordre alphabétique naturel, sans
priorité aux pannes. Une ressource dont la visibilité est décochée disparaît au
prochain catalogue acquitté, puis à l’actualisation de la page. Les lectures ne
sont pas mises en cache par le plugin ; un cache extérieur doit respecter ces en-têtes.
Avec un ancien plugin, Disponible à la location est présenté comme Disponible,
et un prêt comme une indisponibilité, sans identité
de bénéficiaire. Les règles d’inscription, listes d’attente, signatures et files
durables ne changent pas. Les fiches QR/tutoriels sont servies par OpenFabLab,
pas téléversées ou synchronisées dans la base du plugin.

Après remplacement, contrôler Normal et Test dans OpenFabLab et WordPress,
ouvrir la page, changer plusieurs fois de langue et vérifier calendrier, catalogue
et formulaire de réservation. Ne pas utiliser un ancien « Connecté » comme preuve
d’un échange récent. Les essais de développement utilisent des demandes fictives,
pas de nouvelles réservations ou notifications destinées à de vrais usagers.

Les règles de la [version précédente](wordpress-2.14.4.md) restent applicables :
un mois d’historique admissible, retrait des réservations passées à 24 h,
moyennes publiques facultatives sur douze mois et aucune donnée individuelle.
