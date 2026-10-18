# OpenFabLab 2.10.1 — version stable

Cette correction part de la stable 2.10.0, sans changement du schéma SQLite 21.
Les réservations, familles, crédits et règles de consommation restent inchangés.
Télécharger l’[application, le plugin facultatif et les empreintes](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.10.1).

## Réservations par créneaux

Le plugin Reservations 2.10.1 affiche les disponibilités et les listes d’attente
créneau par créneau. Le menu natif indique les places disponibles, l’attente
ouverte ou saturée et les inscriptions closes. Un récapitulatif rappelle le
créneau, le nombre de participants et le type de demande. Pour un groupe,
l’affichage tient compte des places nécessaires sans promettre une confirmation.

La disponibilité est un instantané : le récapitulatif avertit explicitement
qu’une demande peut rejoindre l’attente si les places ne suffisent plus à la
validation. Le résultat final reste celui du moteur transactionnel OpenFabLab.
WordPress ne distribue aucune place et ne crée aucun moteur de réservation.

Les notifications Discord conservent les horaires précis du créneau, y compris
dans les notifications différées de saturation. Leurs préférences et les règles
de confidentialité sont inchangées. Les événements globaux restent anonymes.

## Sons locaux

Deux ambiances synthétiques s’ajoutent aux trois existantes : Summer (tonalités
chaleureuses et percussions douces) et Steampunk (petits sons mécaniques).
Le mode automatique utilise le thème visuel existant, sans calendrier parallèle.
Aucun fichier audio tiers, microphone, bibliothèque ou serveur extérieur.

L’option « Son du compte à rebours » accompagne le timer de départ déjà présent
sur l’accueil. Attention : ce timer confirme réellement le départ au bout de
dix secondes ; il ne s’agit pas d’une simple fermeture d’écran. Aucun nouveau
départ ni timer n’est ajouté. Annuler, confirmer manuellement ou changer de page
arrête les sons. L’onglet masqué reste silencieux, sans rattrapage des sons.
L’option est activée initialement ; désactiver les sons coupe aussi ce retour.
Les choix existants et le volume logiciel restent conservés (50 % si absent).
Les restrictions audio du navigateur sont respectées ; les confirmations
visuelles et les opérations fonctionnent même si le son est indisponible.

## Calendrier

« Enregistrer » est placé dans l’en-tête « Note interne », avec le nom accessible
« Enregistrer la note ». La ligne de bouton sous le champ disparaît. Les actions
générales sont regroupées et leur hiérarchie préservée, sans agrandir la fenêtre.
Les notes restent internes, par occurrence, avec les mêmes permissions et CSRF.

## Compatibilité et installation

Application et plugin portent le numéro public 2.10.1. Ce numéro n’est pas une
condition d’authentification ni de compatibilité du relais. Protocole 4, révision 3,
capacité `waitlist_limits_v1` inchangés. Le plugin reste facultatif.

Ordre recommandé : sauvegarder, mettre à jour l’application 2.10.0 vers 2.10.1,
vérifier sa santé, puis installer le ZIP Reservations 2.10.1 dans WordPress.
Le plugin 2.9.0 reste utilisable pendant la transition, avec son ancienne
présentation des créneaux. Le nouveau plugin conserve le catalogue 2.10.0.
Une désynchronisation temporaire ne garantit jamais une place : le moteur
revalide toutes les demandes. Installer reste une décision de chaque structure.

SQLite reste en schéma 21 : aucune migration 20 → 21 à rejouer pour cette mise
à jour. Seule une préférence de présentation est ajoutée dans `app_settings`.
Le module Abonnements et crédits reste facultatif et désactivé par défaut.
