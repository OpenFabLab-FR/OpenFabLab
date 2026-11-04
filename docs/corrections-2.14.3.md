> Référence historique de l’étape 2.14.3, intégrée à la stable 2.14.4.
> Pour une installation actuelle : [utilisation](utilisation.md), [WordPress](wordpress-2.14.4.md)
> et [mise à jour](upgrade.md). Les mentions de candidate ci-dessous décrivent leur époque.

# OpenFabLab 2.14.3 — candidate de finition

Depuis la 2.14.2 : SQLite **24 → 24**, sans migration ni nouvelle préférence.

## Catalogue public WordPress

La catégorie précède immédiatement le nom et le statut le suit, dans un même
groupe aligné à gauche. Espacements courts, retour à la ligne pour les noms longs,
catégories personnalisées conservées. Le motif et le retour estimé restent dessous.
Les couleurs de statut, les identifiants et les règles de publication ne changent pas.

## Moyennes OpenLab

Présentation compacte : « Mercredi : 6 usagers · 3 visiteurs en moyenne », suivie
de « Moyenne calculée sur les 12 derniers mois ». Jour et effectifs restent
dynamiques, singuliers/pluriels FR/EN respectés. Aucun changement du calcul,
des seuils de confidentialité, des exceptions ou de la fenêtre glissante. La
formulation désigne toujours des fréquentations enregistrées, pas un recensement
exhaustif. L’ancienne projection 26 semaines reste acceptée avec sa propre légende.
Le sélecteur FR/EN reste unique sur une page réunissant les trois shortcodes.

## Borne et calendrier interne

Sous les modules d’identification, chaque commande est centrée sous sa carte,
avec les mêmes colonnes et espacements. Les commandes passent en colonne sur
smartphone. Caméra, scanner, saisie, pointage et choix de
visibilité ne changent pas. Sans indisponibilité, le bouton reste absent.

La seconde ligne du calendrier est rapprochée de la première (8 px visés), avec
la plage à gauche et les événements masqués à droite ; retour à la ligne adapté.
Les filtres et les vues Semaine/Mois conservent exactement leur fonctionnement.

### Présence manuelle

La page « Choisissez votre nom » ne présente plus de commande ni de fenêtre
d’indisponibilité des ressources. La recherche et le pointage restent identiques.
Ces informations restent sur l’accueil et l’identification classique, selon les
choix de visibilité déjà enregistrés.

### Création de compte sur la borne

Un identifiant déjà attribué est refusé avec un message sous le champ, mis en
évidence et sélectionné : « Cet identifiant est déjà utilisé. Choisissez-en un
autre. » Les autres champs restent dans le formulaire actif, sans stockage dans
le navigateur. Corriger les quatre chiffres suffit pour réessayer. Les erreurs
de validation, de serveur et de connexion sont distinguées, en français/anglais.
La vérification serveur, l’unicité SQLite et la transaction sont conservées :
aucun compte partiel, aucune notification de création après un refus. Pas de
nouveau service de recherche d’identifiants. Annulation, abandon, réussite et
expiration effacent le formulaire ; la durée de validité n’est pas prolongée.
Après une coupure dont le résultat est incertain, demander à l’équipe de vérifier
avant de recommencer. Sans JavaScript, le rendu HTML conserve les champs lors
d’un refus serveur ; une panne réseau ne peut alors pas être prise en charge
par le logiciel de la même manière.

### Confirmation du départ

La fenêtre utilise la couche modale native du navigateur, hors des contextes
d’empilement de l’en-tête. Le voile couvre aussi les logos et le sélecteur FR/EN.
Le menu des langues se referme à l’ouverture d’une fenêtre modale ; l’arrière-plan
ne peut pas recevoir de clic ou de focus. Tabulation limitée aux deux actions,
annulation immédiate et restitution du focus à la carte d’origine. Dimensions,
thèmes, compte à rebours de dix secondes, validation et protection contre les
doubles départs conservés. Repli isolant l’arrière-plan si showModal manque,
sans augmenter le z-index historique.

## Dates des rappels Discord

Les échéances sont présentées en **03/11/2026** en français ou **3 Nov 2026** en
anglais. La langue suit la langue principale configurée de l’installation
(`kiosk_language`), indépendamment de la langue temporaire d’un visiteur ou de
l’administration. Aucun réglage supplémentaire.

Une échéance `due_on` est une date civile du fuseau de la structure : elle n’est
pas reconvertie comme un minuit UTC, ce qui évite de changer le jour affiché.
Le moteur continue à sélectionner le jour et l’heure dans le fuseau configuré,
y compris aux changements d’heure. Stockage ISO, déduplication, état du rappel,
liaison avec l’intervention, canal et planification restent inchangés.

## Installation

Application et plugin sont réellement modifiés en 2.14.3. Protocole **4/révision 3**,
capacités et compatibilités inchangés. Le plugin s’installe séparément par
téléversement/remplacement du ZIP, sans désinstallation ni changement de secret.

Le paquet DSM privé **révision r2** est exclusivement adapté à **2.14.2/24 → 2.14.3/24**.
Exécuter d’abord --check, examiner son rapport avant toute installation. Ne pas
réutiliser les anciennes migrations. PRE24/POST24 et état récent préservés ; aucune
restauration automatique pouvant écraser de nouvelles écritures.
