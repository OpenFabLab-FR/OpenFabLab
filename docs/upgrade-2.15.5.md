# Mettre à jour vers OpenFabLab 2.15.5

Téléchargez le [ZIP applicatif et SHA256SUMS](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.15.5).
La mise à jour intégrée requiert un agent compatible et **SQLite 28**.
Si vous partez d’un autre schéma, suivez le [parcours manuel](upgrade.md).

Depuis une V2.15.4 avec l’agent connecté, ouvrez **Réglages → Système et
sauvegardes → Mises à jour → Importer un ZIP**. Sélectionnez l’archive
applicative sans la décompresser, puis **Vérifier le ZIP**.
Confirmez hors séance si l’écran annonce **2.15.5 · SQLite 28 · Aucune
migration de schéma**.

Après reconnexion, vérifiez **V2.15.5**, `UPDATE_SUCCESS` et les sauvegardes
PRE et POST. En cas d’échec, conservez le rapport et les sauvegardes avant
toute nouvelle tentative. Ne réinstallez ni l’agent ni le plugin WordPress.

Le jour d’un retour estimé n’est pas une journée de maintenance prévue.
Si la ressource reste déclarée indisponible ce jour-là, son état constaté
reste affiché : aucune remise en service n’est automatique. Les vraies
interventions et les rappels gardent leurs entrées.
