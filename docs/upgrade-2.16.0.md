# OpenFabLab 2.16.0 — mise à jour, nouveautés et secours

Point de départ testé : **2.15.5 officielle, SQLite 28**. Le schéma reste
**28**. L’agent parle toujours le protocole **1** et WordPress
le protocole **4 / révision 3**. Conservez le plugin Reservations **2.15.3**
et l’agent déjà connecté. Aucune réinstallation n’est requise pour eux.

## Mettre à jour une 2.15.5 avec un agent connecté

1. Vérifier l’empreinte SHA-256 de `OpenFabLab-2.16.0.zip` et disposer
   d’une sauvegarde complète dont la restauration a été essayée sur une copie
   isolée. Conserver l’image et le ZIP de la version actuelle.
2. Dans **Réglages → Système et sauvegardes → Mises à jour**, choisir **ZIP local**.
   Sélectionner l’archive applicative, pas le kit agent ni le ZIP WordPress.
3. Vérifier puis préparer la mise à jour. La préparation contrôle le
   runtime, les volumes, SQLite, le démarrage isolé et les intégrations
   configurées. Un refus n’autorise pas à contourner un contrôle.
4. Après un résultat positif et dans un créneau d’interruption accepté,
   confirmer une seule fois. Attendre `UPDATE_SUCCESS`, vérifier la version,
   le schéma et les sauvegardes PRE/POST. Contrôler aussi les modules utilisés.

Le bouton GitHub cherche la version stable publiée sur le dépôt officiel.
Il vérifie les métadonnées et l’empreinte de l’asset ; voir le
[guide de l’agent](update-agent.md). L’import ZIP, lui, repose sur un fichier
choisi et vérifié par l’administrateur. Le chemin **ZIP local** a réussi sur
le Synology du FougèresLab (20 étapes, PRE/POST, sans migration) ; il ne valide
ni le téléchargement GitHub de cette version ni une première activation sur
ce NAS.

## Nouveau FabLab ou installation sans agent

Pour une installation neuve, utiliser un dossier et un stockage vides.
Vérifier les [prérequis](platform-compatibility.md), puis suivre le
[guide d’installation](installation.md). Après le PIN, l’assistant guide
la configuration de l’identité, du fuseau, des modules et des langues.
Les intégrations externes se configurent séparément.

Si la mise à jour intégrée est souhaitée, utiliser le
[kit d’activation 2.16.0](../tools/agent-setup/README.md), après démarrage
et contrôle de l’application. L’activation initiale requiert un compte
administrateur du serveur, Docker/Compose locaux et des chemins de stockage
stables. Le web ne reçoit jamais le socket Docker.

Pour une version antérieure ou une autre installation, suivre le
[parcours de mise à jour approprié](upgrade.md). Ne pas ouvrir une base
d’une version plus récente avec un ancien exécutable. Ne pas écraser les
volumes d’une installation existante avec l’exemple Compose neuf.

## Ressources

- **Informations et disponibilité** : identité, disponibilité habituelle,
  état technique et publication. Remettre une ressource en service efface
  le motif public et la date estimée du précédent incident, pas l’historique.
  Un prêt réellement sorti reste indisponible jusqu’au retour enregistré.
- **Maintenance et suivi technique** : consulter les signalements, les
  maintenances planifiées, les rappels, les interventions et les documents
  de l’équipe. La conversion d’un signalement reprend sa description.
  **Terminer la maintenance** enregistre le travail, clôt éventuellement
  le rappel choisi et remet en service uniquement après confirmation.
- **Réservations, prêts et documents** : planning, prêt ou location, QR
  permanent et tutoriels. Les actions sensibles et l’historique administratif
  restent distincts. WordPress reçoit la disponibilité via sa synchronisation.

## Tarifs et annonces vocales

Dans un dossier de devis, choisir un **tarif exceptionnel** ou **créer un
tarif permanent**. Indiquer la désignation, le montant unitaire et l’unité
(heure ou demi-journée). Le tarif permanent est ajouté au catalogue à
l’enregistrement ; le tarif exceptionnel ne concerne que ce dossier.
Un tarif à zéro est possible. Les montants enregistrés des dossiers signés
ou facturés ne sont pas recalculés à partir d’un nouveau tarif.

Dans **Réglages → Borne**, les annonces vocales sont désactivées par défaut.
Le bouton de test permet d’essayer une voix locale et de régler son volume.
Seul le prénom est prononcé pour un passage confirmé ; un visiteur anonyme
entend uniquement l’accueil. Les confirmations visuelles restent disponibles
si la voix de la langue manque ou si l’appareil refuse de la jouer.

## En cas de refus ou d’échec

Relever le résultat de l’agent, conserver les preuves et ne pas relancer à
l’aveugle. Une sauvegarde PRE protège l’état précédent ; après réouverture
au public, restaurer cet état pourrait effacer de nouvelles écritures.
Consulter [sauvegardes et restauration](backup-restore.md) et le
[diagnostic hors interface](update-agent.md#révoquer-ou-récupérer-indépendamment-du-web).
Ne pas rendre publics les rapports, sauvegardes ou données de recette réelles.
