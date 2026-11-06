# Référence : mise à jour vers OpenFabLab 2.15.3

Cette étape n’a pas de release publique distincte. Voir le
[parcours vers la version stable 2.15.5](upgrade.md).

Source : **OpenFabLab 2.15.2, SQLite 26**, avec l’agent déjà connecté. Ne
réinstallez pas l’agent.

1. Vérifiez le SHA-256 du ZIP applicatif. Ne le décompressez pas.
2. Dans **Réglages → Système et sauvegardes → Mises à jour → Importer un ZIP**,
   choisissez `OpenFabLab-2.15.3.zip`, puis **Vérifier le ZIP**.
3. Vérifiez la cible 2.15.3 et **SQLite 26 → 27**. Confirmez en dehors
   d’une séance et seulement après vérification. L’agent effectue l’essai
   isolé avant l’arrêt et conserve ses sauvegardes PRE26 et POST27.
4. Après reconnexion, rechargez la page : l’ancienne interface ne peut pas
   afficher le nouveau suivi. Vérifiez `UPDATE_SUCCESS`, V2.15.3, SQLite 27
   et les deux sauvegardes.

La migration élargit les statuts de ressources en conservant les anciennes
lignes. Elle ajoute les signalements, leurs décisions et un journal minimal
des modifications de compte. En cas d’échec, conservez le rapport et les
sauvegardes. **Ne démarrez jamais la V2.15.2 sur le schéma 27.**
Voir [Agent et récupération](update-agent.md).

## Signalements et WordPress

Dans **Réglages → Ressources et maintenance → Fiches QR et tutoriels publics**,
activez les signalements si vous souhaitez les recevoir. Ils sont désactivés
par défaut, privés, et ne changent ni le statut de la machine ni l’accès
réseau. Aucun compte ni e-mail requis. Les doublons proches et la fréquence
des envois sont limités. N’y saisissez pas de noms ni de coordonnées. Discord
est une option distincte ; elle respecte la configuration de notification.

Le plugin candidat Reservations 2.15.3 se met à jour séparément dans
WordPress, sans désinstallation ni changement de clé. Le protocole reste
4/révision 3. L’ancien plugin peut toujours synchroniser ; il présente
l’indisponibilité avec son badge générique et un motif.
