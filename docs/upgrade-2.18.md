# Mettre à jour vers OpenFabLab 2.18

**Depuis la dernière stable publique 2.16.1 / SQLite 28, le ZIP 2.18
n’est pas installable directement par l’OTA.** Le manifeste du ZIP validé
accepte uniquement une base déjà au schéma **29**. Un agent 1.2 peut
annoncer la nouvelle release, mais refuse sa préparation sur 28 avant tout
arrêt (`SOURCE_SCHEMA_NOT_SUPPORTED`). Un agent d’origine 1.1.0 peut
refuser le numéro à deux composants lui-même. Ne renommez pas le ZIP
et ne modifiez ni son manifeste ni les reçus de l’agent.

## Choisir le parcours

| Vous partez de… | Parcours |
| --- | --- |
| Une installation neuve | Suivez le [guide d’installation](installation.md) : une base SQLite 29 sera créée. Agent et WordPress facultatifs. |
| 2.16.1 / SQLite 28 | Suivez le parcours manuel ci-dessous après essai sur copie. Ne cherchez pas une stable publique 2.17. |
| 2.17 privée / SQLite 29, agent 1.2 sain | OTA officielle ou import du ZIP 2.18. Pas de migration SQLite. |
| Une installation plus ancienne | Rejoignez d’abord 2.16.1 au schéma 28 par les [parcours historiques](upgrade.md#archives-des-procédures), selon votre version ; aucun saut universel n’est garanti. |

Téléchargez la [release v2.18](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.18)
et comparez l’empreinte SHA-256 du ZIP applicatif au fichier
`SHA256SUMS`. Le plugin et les kits d’agent ne sont pas des ZIP applicatifs.

## Depuis 2.16.1 : migration manuelle de 28 vers 29

Avec l’aide de la personne qui administre le serveur si nécessaire :

1. Relevez version, schéma et montages. Conservez l’ancien runtime ou
   l’image, la configuration, les données privées et une [sauvegarde
   complète et vérifiée](backup-restore.md). Gardez l’ancienne image sous
   une référence distincte. Ne remplacez pas le Compose personnalisé par
   le Compose vierge de l’archive.
2. Extrayez le ZIP dans un dossier séparé. Essayez d’abord la 2.18 sur une
   **restauration isolée** (autres volumes et port local, envois et sorties
   externes bloqués). Au démarrage, le programme fait la migration
   additive 28 → 29. Vérifiez santé, intégrité SQLite et clés étrangères,
   inscrits, attentes, présences, familles et réglages. L’espace usager
   n’est pas activé par la migration.
3. En maintenance, assurez-vous qu’aucun travail OTA ne tourne. Mettez
   l’agent de côté pour la mise à jour manuelle (aucune réinitialisation
   de son état ni des secrets), arrêtez l’ancien service, et réalisez une
   **PRE froide** cohérente. Démarrez la 2.18 avec les montages et les
   réglages de l’installation existante. Les deux versions ne doivent
   jamais ouvrir simultanément cette même base.
4. Vérifiez les mêmes témoins et le schéma **29** avant réouverture,
   puis réalisez une **POST**. Ne réactivez pas pour autant une politique
   d’agent devenue incohérente : un déploiement manuel ne met pas ses
   reçus de runtime à jour. Continuez en manuel tant qu’un
   administrateur n’a pas préparé et vérifié une configuration d’agent
   compatible avec ce runtime. Voir [agent et limites](update-agent.md).
5. Si vous utilisez WordPress, remplacez ensuite le plugin sans le
   désinstaller ni changer le secret ; suivez [la mise à jour
   WordPress](wordpress.md).

Ce parcours a été vérifié avec les ZIP exacts 2.16.1 et 2.18 et une copie
SQLite fictive. Ce n’est pas une certification de votre hôte, de Docker
ou de vos montages.

## Si la 2.17 / SQLite 29 est déjà saine

L’agent **1.2** doit être connecté, avec une politique et un reçu source
valides. Dans **Réglages → Système et sauvegardes → Mises à jour**,
recherchez la stable ou importez le ZIP local vérifié, préparez puis
confirmez. Contrôlez `UPDATE_SUCCESS`, PRE, POST, la version 2.18, le pied
de page V2.18 et le schéma 29. Mettez à jour WordPress seulement ensuite.

## Revenir en arrière

Ne réimportez pas un ZIP plus ancien via l’OTA. En cas de refus avant arrêt,
préservez le diagnostic, sans restaurer par réflexe. Si l’installation a
déjà démarré, préservez aussi les écritures intervenues depuis la PRE.
Un retour à 2.16.1 exige **le runtime, les réglages, la base au schéma 28
et les fichiers privés** d’une même sauvegarde de cette version. Ne
redémarrez jamais 2.16.1 sur la base migrée au schéma 29.
