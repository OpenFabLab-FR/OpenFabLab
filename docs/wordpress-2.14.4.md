# Installer et utiliser OpenFabLab Reservations 2.14.4

Le plugin complète votre site WordPress ; OpenFabLab fonctionne aussi sans lui.
L’application décide des disponibilités et des réservations. Le plugin reçoit
un catalogue public et relaie les demandes par HTTPS signé ; il ne duplique pas
l’annuaire privé et ne demande pas d’ouvrir un port entrant sur le NAS.

## Installer ou remplacer l’extension

1. Sauvegarder WordPress, sa base et les options de l’extension existante.
2. Télécharger le [ZIP officiel](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.14.4/openfablab-reservations-2.14.4.zip)
   et vérifier [SHA256SUMS](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.14.4/SHA256SUMS).
3. Extensions → Ajouter une extension → Téléverser : sélectionner le ZIP. Pour
   une mise à jour, remplacer la version existante **sans la désinstaller**.
4. Vérifier la version affichée et conserver options, files et secret partagé.
5. Dans les réglages Reservations, vérifier Normal et Test séparément, puis
   vérifier dans OpenFabLab un catalogue et une relève récents. Un ancien badge
   « Connecté » ne prouve pas le succès d’un échange actuel.

L’application et le plugin se mettent à jour séparément. Protocole4/révision3,
sans comparaison stricte des numéros publics. Le plugin2.13 reste utilisable pour
ses réservations négociées, mais les nouveaux écrans demandent la série2.14 ; le
mois complet d’historique demande l’application et le plugin2.14.4.

## Ajouter les blocs dans Gutenberg

Créer un bloc **Code court**, coller l’un des exemples suivants, enregistrer et
prévisualiser. Ne pas utiliser un bloc de code destiné à afficher du texte.

### Réservations d’animations

```text
[openfablab_reservations environment="production"]
```

Le parcours distingue compte/sans compte selon la structure, demandes familiales,
créneaux disponibles, attente ouverte, attente saturée et fermeture. Le récapitulatif
distingue confirmation et liste d’attente. Propositions de places, annulations et
liens personnels continuent à être contrôlés par OpenFabLab.

### Calendrier hebdomadaire

```text
[openfablab_calendar environment="production" view="week"]
```

### Catalogue des ressources

```text
[openfablab_machines environment="production"]
```

L’alias `[openfablab_resources environment="production"]` est aussi enregistré.
Le nom technique du shortcode reste stable même si le titre public est Machines,
Ressources, Équipements ou Salles. WordPress garde la main sur les titres éditoriaux,
textes, colonnes et position des blocs. Plusieurs shortcodes peuvent partager une page.

## Activations et langues indépendantes

Dans « Calendrier, machines et langues publiques », activer volontairement le
calendrier et/ou la liste publique. Choisir l’affichage OpenLab/animations et une
page de réservation facultative. Ces activations ne changent pas les horaires
internes, les ressources ou les réservations de l’application.

Choisir Français ou English par défaut et « Permettre aux visiteurs de changer
de langue ». Désactivée, cette option retire le sélecteur de tous les composants
et impose la langue par défaut ; elle est indépendante de la borne et de l’administration.
Activée, un seul sélecteur pilote la page : dans le calendrier s’il vient en premier,
sinon dans le premier composant visible. Sans titre de catalogue, il s’intègre à
la première ressource ; un catalogue vide n’ajoute pas de fausse barre.

Second clic, sélection, clic extérieur et Échap referment le menu. Le clavier et
le focus sont pris en charge ; une fenêtre bloquante ferme et neutralise le menu.
Un changement de langue prévient avant de perdre une saisie en cours. Les textes
standards utilisent les catalogues locaux ; aucune traduction automatique des
descriptions, catégories ou noms personnalisés n’est promise.

« Afficher le titre de la liste des ressources » utilise le nom public défini
dans OpenFabLab. Décochée, elle ne laisse ni titre ni marge vide ; ajouter son propre
bloc Titre reste possible. Le comportement antérieur est conservé à la mise à jour,
et une installation neuve démarre sans titre automatique.

## Publication des ressources

La structure choisit les ressources publiques dans OpenFabLab. Catégorie, nom et
état restent groupés ; motif et retour estimé ne sont montrés que lorsqu’ils sont
autorisés et pertinents. Une ressource archivée disparaît. Disponible ne veut pas
dire immédiatement libre ou réservable. Notes, interventions, historiques, auteurs
et données de personnes restent internes. [Guide des ressources](resources-maintenance.md).

## Calendrier, passé et fréquentation moyenne

La semaine actuelle est affichée par défaut. Le calendrier autorise un mois
calendaire glissant en arrière, selon le fuseau du FabLab : le3 novembre, limite
au3 octobre inclus. La semaine chevauchante reste consultable mais pas ses jours
antérieurs. Fins de mois et changements d’heure sont pris en compte ; l’API et le
navigateur appliquent la limite, pas seulement le bouton précédent.

Le survol et le focus soulignent les événements sans déplacer la grille. Le toucher
ouvre la même fenêtre d’information. Les horaires exceptionnels et fermetures
publiables sont respectés. Les périodes absentes ou les projections périmées sont
signalées : le calendrier n’invente pas des archives manquantes.

La règle de réservation des24 heures reste inchangée. Au-delà, seules les animations
encore publiques, du bon environnement, non masquées et avec participation positive
constatée peuvent être reprises en historique, sans nouvelle réservation. Le modèle
ne comporte pas de statut indépendant « réellement tenue » : une saisie absente
ou un zéro ne prouve pas qu’un événement a eu lieu. Aucun participant, présence
individuelle, note interne, contact ou jeton personnel n’est publié.

La moyenne publique des OpenLab est facultative et activée explicitement dans
OpenFabLab. Calcul sur les douze mois calendaires précédents, jusqu’à la veille,
même jour de semaine et créneau comparable. Il faut au moins six séances observées,
au moins cinq usagers distincts sur l’ensemble de la période et un total des
effectifs par séance au moins égal à cinq fois le nombre de séances retenues.
Un total de visiteurs compris entre un et quatre empêche aussi la publication.
Ce seuil est global : ce n’est pas un minimum de cinq personnes à chaque séance.
Les fermetures, créneaux modifiés
et séances sans données exploitables sont exclus ; aucune absence n’est assimilée
à zéro. Les usagers sont dédupliqués par séance, les visiteurs sont des entrées
anonymes et non des personnes dénombrables entre plusieurs visites. La présentation
reste statistique, sans croisement ni donnée individuelle. La fenêtre indique
« Moyenne calculée sur les12 derniers mois » quand une moyenne admissible existe.

## Normal, Test et sécurité

Les exemples précédents ciblent Normal (`production`). Pour une page de test,
remplacer explicitement par `environment="test"`. Catalogues, demandes et traces
restent séparés ; ne pas utiliser de données réelles pour des essais destructifs.
L’environnement Test n’est pas un outil d’anonymisation de données privées.

Le secret partagé ne doit jamais être mis dans un shortcode, une URL ou une page.
Les liens personnels sont privés ; ne pas les publier dans le calendrier. Réservations,
annulations et listes d’attente gardent les contrôles serveur, signatures, nonces
et règles de capacité. Les nouvelles capacités de présentation sont facultatives.
[Relais sortant](outbound-2.8.1.md) · [Sécurité](../SECURITY.md).
