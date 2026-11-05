# Mise à jour vers la candidate 2.15.0

Parcours de livraison testé : **2.14.4 / SQLite 25 → 2.15.0 / SQLite 26**.
Réexécuter la migration déjà appliquée ne duplique pas les données. Un schéma
inconnu ou plus récent est refusé. Le moteur reste `family_model.migrate` ; pas
de second système de migration. Les anciennes versions doivent d’abord suivre
leur [parcours vers 2.14.4](upgrade.md#parcours-historique-vers-2144).

La migration ajoute le mode habituel de disponibilité aux ressources (valeur
initiale sur site, même si la réservation est activée), des colonnes aux réservations/contrats et trois tables pour
les restrictions manuelles et les documents partagés. Elle ne réécrit pas les
anciennes présences, locations, réglages ni secrets. Les nouvelles fiches QR
publiques restent désactivées. L’assistant n’est pas forcé sur les installations
existantes. Les rappels ne sont pas réémis par l’outil de migration isolé.

## Avant toute interruption

1. Vérifier l’archive et SHA256SUMS, le runtime réellement actif, le schéma,
   l’intégrité SQLite, les clés étrangères, les volumes et le projet Compose.
2. Vérifier les droits effectifs et l’espace. En mode contrôle, ne pas écrire de
   sonde dans les données ou les sauvegardes. Un simple bit POSIX ne prouve pas
   une impossibilité avec des ACL ; les écritures propres sont testées seulement
   après confirmation et avant arrêt.
3. Construire l’image cible sur une base Python propre, sans empiler l’ancienne.
   Tester migration et vrai HTTP sur une copie isolée, réseau externe bloqué.
4. Effectuer une sauvegarde cohérente à chaud. Obtenir la confirmation humaine.

## Installation volontaire

Arrêt contrôlé, PRE25 complète à froid avec configuration, données privées et
ancienne image, migration transactionnelle, comparaison de l’historique et des
préférences, installation du runtime et démarrage cible. Vérifier HTTP, volumes,
paramètres, fichiers privés et échanges signés WordPress Normal/Test. Terminer
par une POST26 complète réellement restaurée et ouverte en isolation.

**Ne jamais lancer la 2.14.4 sur une base 26.** Après une tentative publique,
aucune PRE25 ne doit être restaurée automatiquement : de nouvelles écritures
peuvent exister. En cas d’échec, préserver l’état et utiliser le diagnostic de
reprise cible, sans nouvelle migration ni ancienne image imposée.

Le paquet privé d’un exploitant n’est pas une procédure publique universelle.
Le contrôle `--check` n’effectue pas de construction Docker. Le diagnostic de
construction distinct prépare et teste avant arrêt, sans installer. Une réussite
du contrôle n’est pas une installation réussie.

L’agent facultatif est installé **après** la réussite de cette première transition,
par une autorisation indépendante. Le plugin WordPress 2.15.0 se remplace
séparément, sans désinstallation et sans changer la clé partagée.
