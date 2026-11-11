# Première activation de l’agent OpenFabLab

**Kit facultatif pour OpenFabLab 2.16.0.** Il ne migre pas la base et n’installe pas l’application.
Utilisez-le uniquement sur OpenFabLab 2.16.0 en état de marche, SQLite 28,
sans agent connecté. Un agent compatible déjà installé n’est pas réinstallé.
Le kit embarque l’agent **1.1.0** ; son protocole local reste en version 1,
distincte du numéro d’OpenFabLab. Un ancien agent compatible peut ne pas
renvoyer de numéro de version : sa connexion et sa capacité ZIP restent visibles.

L’agent est facultatif et privilégié. Son socket Docker n’est jamais monté
dans le service web : seuls le socket Unix de l’agent et son jeton sont
partagés en lecture seule. Le kit n’expose pas de port. Protégez son répertoire,
ses journaux et ses sauvegardes comme des fichiers d’administration.

## Préparer le serveur

1. Vérifier l’empreinte des **deux** ZIP à partir du fichier d’empreintes
   approuvé reçu séparément, avant extraction ou exécution en root.
   Extraire le ZIP du kit dans un répertoire privé sous contrôle de root.
2. Déployer et configurer l’application. Le service Compose local doit être
   `application`, dans `compose.yaml`, avec `data/openfablab.db` et un
   répertoire distinct pour les sauvegardes. Contrôler la santé et réaliser
   une sauvegarde complète dont la restauration a été essayée à l’écart.
3. Préparer un répertoire agent indépendant, sous contrôle de root, contenant
   `state` et `shared`. Aucun des trois répertoires ne doit être modifiable
   par le groupe ou par les autres. Ne modifier ni les ACL de la base ni
   les droits du dossier des données pour satisfaire un contrôle.
4. Repérer les chemins réels et canoniques (sans lien) du client Docker,
   du binaire Compose et l’ID `sha256:…` de l’image web en cours. Ne pas
   déduire cet ID du nom du conteneur ou d’une étiquette d’image.

## Vérifier, préparer, autoriser

Depuis le dossier privé du kit, avec un compte système administrateur Linux
ou une tâche DSM ponctuelle root, remplacer **tous** les paramètres par ceux
de l’installation. Répéter la commande pour chaque mode, après examen du
rapport précédent :

```sh
bash ./activate.sh "$ZIP_APP" "$PROJET" "$SAUVEGARDES" "$AGENT" \
  "$DOCKER_CLI" "$COMPOSE_CLI" "$IMAGE_WEB" --check "$SHA_ZIP_APP" 2.16.0
bash ./activate.sh "$ZIP_APP" "$PROJET" "$SAUVEGARDES" "$AGENT" \
  "$DOCKER_CLI" "$COMPOSE_CLI" "$IMAGE_WEB" --prepare "$SHA_ZIP_APP" 2.16.0
bash ./activate.sh "$ZIP_APP" "$PROJET" "$SAUVEGARDES" "$AGENT" \
  "$DOCKER_CLI" "$COMPOSE_CLI" "$IMAGE_WEB" --install "$SHA_ZIP_APP" 2.16.0 \
  --confirm AUTHORIZE-LOCAL-AGENT-2.16.0
```

`--check` vérifie les capacités, le runtime en cours, SQLite, les montages,
Compose et les intégrations configurées sans écrire dans le projet.
`--prepare` construit et vérifie l’image agent séparée sans arrêt.
La dernière commande seule interrompt brièvement le web ; elle requiert une
préparation conforme, protège l’état PRE et vérifie l’état POST. Examiner
ensuite **Réglages → Système et sauvegardes → Mises à jour**.

En cas de refus, conserver les rapports privés. Ne pas effacer les reçus,
réécrire Compose ni relancer l’installation après un arrêt. Voir le guide
`docs/update-agent.md` de l’application pour le diagnostic hors interface.

La validation locale ne certifie pas Container Manager ni tous les modèles
Synology ou Raspberry Pi. La V2.16.0 doit encore passer `--check` et
`--prepare` sur le serveur concerné avant d’envisager l’activation.

Une future mise à niveau de l’agent lui-même exige une procédure locale
distincte et approuvée pour cet agent. Ce kit ne remplace pas une instance
connectée et n’expose pas de commande système dans le navigateur.
