# Mettre à jour vers OpenFabLab 2.15.2

Source : OpenFabLab 2.15.1, SQLite 26 et agent local compatible et connecté.
La mise à jour conserve SQLite 26. Sans agent compatible, suivre le
[parcours par version](upgrade.md). Pour une installation neuve, voir
[le guide d’installation](installation.md).

## Depuis GitHub

Dans **Réglages → Système et sauvegardes → Mises à jour**, lancer la recherche
de mises à jour. Vérifier que la version officielle et les résultats
correspondent à la cible attendue, puis suivre les actions proposées.
L’agent vérifie la release et le ZIP. Aucune installation ne se déclenche
à la simple recherche : elle exige votre confirmation.

## Par import d’un ZIP

1. Télécharger le ZIP applicatif de la [release officielle](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.15.2)
   et vérifier son SHA-256, sans l’extraire. Ne pas sélectionner le ZIP
   WordPress, le kit agent ni le ZIP automatique du code source.
2. Ouvrir **Réglages → Système et sauvegardes → Mises à jour**.
3. Choisir **Importer un ZIP**, sélectionner `OpenFabLab-2.15.2.zip`,
   puis cliquer sur **Vérifier le ZIP**.
4. Si la vérification réussit, relire la cible et les détails. En dehors
   d’une séance, autoriser l’installation dans le bloc de confirmation.
   L’essai isolé et les contrôles préalables interviennent avant l’arrêt
   du service. Suivre la progression dans l’administration.
5. Après redémarrage, vérifier **V2.15.2**, **SQLite 26**, l’agent connecté,
   `UPDATE_SUCCESS` et les sauvegardes PRE/POST dans l’historique.

## En cas de refus ou d’échec

Conserver le rapport et les sauvegardes.
Ne pas relancer aveuglément ni restaurer par-dessus les données courantes.
Voir [le guide de l’agent](update-agent.md) pour le diagnostic et le secours.

## Validation réelle et plugin WordPress

L’import ZIP 2.15.1 → 2.15.2 a abouti à `UPDATE_SUCCESS` sur le Synology du
FougèresLab. Ce retour ne couvre ni une activation neuve de l’agent 2.15.2
ni le téléchargement de cette mise à jour par l’agent depuis GitHub sur ce NAS.
[Reservations 2.15.2](wordpress-2.15.2.md) s’installe séparément ; le ZIP
applicatif ne modifie pas WordPress.
