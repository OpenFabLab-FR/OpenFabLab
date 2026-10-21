# OpenFabLab 2.12.0 — consolidation

Application **2.12.0**, plugin facultatif Reservations **2.11.0 inchangé**. SQLite **22 conservé**,
sans migration supplémentaire. Protocole **4 / révision 3** et capacités inchangés.
Version stable. Toute installation ou mise à jour reste une action volontaire
de l'administrateur, avec sauvegardes et vérifications adaptées à sa plateforme.

## Gestion plus compacte

Dans la fiche d’animation, Places maximum rejoint la date, les horaires et l’âge
minimum ; la case de liste d’attente est une option simple, sans grande carte.
Les statuts de présence utilisent des boutons compacts accessibles au clavier,
avec coche et état sélectionné. **À confirmer** correspond exactement à l’ancienne
valeur Non renseigné, sans changement des données ou du moteur serveur.
L’accueil, ses cartes de présence, les thèmes et les sons ne sont pas modifiés.

## Des indicateurs explicites

**Animations passées** désigne les animations dont la date et l’heure de fin sont
dépassées dans le fuseau de la structure. En mode créneaux, on attend la fin du
dernier créneau : aucune participation de cette animation n’entre prématurément
dans le bilan de ses animations passées. Sans heure historique de fin, on attend
le lendemain. Une heure invalide reste indéterminée ; une ambiguïté de changement
d’heure est traitée prudemment en attendant la dernière interprétation possible.

Le modèle ne dispose pas d’un statut prouvant qu’une animation a été tenue ou
annulée : une date passée ne prouve donc pas sa réalisation. Les réservations
annulées restent distinctes de cette absence de statut pour l’animation elle-même.

**Participations renseignées** utilise le total réel conservé dans chaque animation
passée. Les participants anonymes y sont déjà inclus : ils ne sont pas ajoutés
une deuxième fois. Ni capacité, ni attente, ni réservation future ne constitue
une présence. Les anciennes valeurs manuelles sont conservées, sans recalcul
des inscriptions. Les présences incomplètes sont signalées. Un ancien zéro sans
preuve de saisie reste incertain : il n’est pas présenté comme une absence certaine
de participants. Le total renseigné peut donc être non exhaustif.

**Jours avec passages identifiés** remplace les formulations OpenLabs effectués.
Il s’agit des dates comportant au moins un usager identifié, pas d’un calendrier
exhaustif des ouvertures. Les moyennes horaires existantes sont conservées.

Le début et la dernière date des enregistrements de fréquentation sont calculés
sur sessions et visiteurs, distinctement des dates d’animations et de la date
d’installation. Les périodes partielles sont indiquées dans les synthèses.
L’absence d’enregistrement ne prouve ni fermeture ni absence de fréquentation.
Le fuseau configuré est utilisé pour les agrégations statistiques concernées.

Écran Statistiques, CSV Statistiques, rapport annuel PDF/DOCX et bilan visuel
réutilisent les mêmes fonctions. Les textes des anciens rapports enregistrés
ne sont pas modifiés : seule une nouvelle génération documentaire prend les
indicateurs corrigés. Les fichiers déjà exportés restent évidemment inchangés.

## Bilan visuel de fréquentation (PDF)

Dans Fréquentation → Exports, choisir une année ou Total puis le bilan visuel.
Les six CSV restent disponibles avec les mêmes colonnes ; seuls les libellés
statistiques inexacts sont précisés et les indications de couverture ajoutées.
Le PDF n’est pas un deuxième rapport annuel et ne contient pas de rédaction libre.

Chiffres clés, jours principaux, profils horaires existants, répartitions agrégées
et sessions/heures par catégorie, y compris les petits effectifs. Il est
généré en mémoire avec ReportLab et les polices libres déjà distribuées, sans API,
capture d’écran ni nouvelle dépendance de production. Pagination selon les données,
généralement une à quatre pages ; aucune page de remplissage imposée.

Le document n’inclut pas de comptes, identifiants, coordonnées, dates de naissance,
numéros de réservation ou journaux. Aucune donnée individuelle n’est transmise au
générateur. Les dimensions démographiques sont séparées, sans croisement. Ce bilan
est interne : aucun seuil 15/5 ni suppression de petits effectifs. Les données absentes
figurent en « Non renseigné ». Effectifs et pourcentages utilisent les résultats
statistiques existants, avec les valeurs manquantes dans les dénominateurs.
Les pourcentages sont arrondis à une décimale ; leur somme peut différer légèrement
de 100 %. Les communes/nationalités utilisent les répartitions complètes, pas les
listes limitées de l'écran. Pour limiter la longueur du document, les 20 communes
et les 20 nationalités renseignées les plus représentées sont détaillées ; le reste
est regroupé dans « Autres ». Le pourcentage de ce groupe est recalculé sur son
effectif cumulé et le dénominateur complet, pas par addition de pourcentages arrondis.
« Non renseigné » reste séparé, hors de cette limite. Les égalités sont départagées
par libellé, sans masquer les effectifs de 1. Catégories, genres et âges ne sont pas
limités. Libellés complets, tableaux à barres paginés et en-têtes
répétés conservent leur lisibilité. Examiner le contexte avant tout partage extérieur :
des données agrégées à petit effectif ne sont pas une garantie d'anonymat absolu.
Le nom public de la structure et ses libellés de catégories restent configurables.

Accès administrateur déjà habilité aux exports, module Fréquentation requis,
aucune route publique ; réponse `private, no-store`, sans copie PDF persistante.

## Diagnostic et maintenance

Réglages → Données → État de l’installation : lecture seule, version, schéma,
sauvegarde automatique réussie connue et observations du relais si utilisé.
Aucun contrôle SQLite lourd automatique : le logiciel ne conserve pas un dernier
résultat universel d’intégrité et l’indique explicitement. Un succès de sauvegarde
annoncé n’est pas une preuve de restauration réussie. Aucun secret ni détail brut
d’erreur n’est affiché dans ce diagnostic. [Guide pratique](maintenance.md).

La file `reservation_outbox` conserve des commandes historiques, dont certaines
sans date d’envoi, et des reçus d’anciens parcours locaux. Le protocole 4 actuel
utilise catalogue et `wordpress_action_receipts` pour les décisions transactionnelles.
Un acquittement perdu entraîne la relecture du même reçu, pas une deuxième réservation.
Les états distants pending/processing/retrying/failed correspondent au dernier
relevé authentifié et peuvent être périmés. Les reçus acquittés, récents non acquittés
et anciens non acquittés sont distingués des traces historiques. Une commande
historique peut encore participer aux protections de compatibilité : ne pas la
supprimer sur la seule absence de `sent_at`. Aucune purge, relance ou nouvelle
politique de retry n’est introduite ; moteur et protocole restent inchangés.

## Mise à jour

Depuis 2.11.0 / SQLite 22 : sauvegardes complètes PRE22 et POST22, contrôle des
volumes et empreintes, remplacement du runtime uniquement. Ne pas rejouer 21 → 22.
Conserver l’image précédente et les secrets. Après un démarrage public, préserver
les nouvelles écritures et diagnostiquer avant toute décision de retour arrière.
Le paquet privé d’un exploitant n’est pas une distribution publique générique.

Le module Abonnements et crédits reste facultatif et désactivé par défaut.
Aucun paiement bancaire, nouveau module métier ou nouveau calendrier d’ouverture.
