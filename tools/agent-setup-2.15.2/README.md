# Activer l’agent sur OpenFabLab 2.15.2

Ce kit séparé sert **une seule fois**, sur une installation Docker Compose
2.15.2 qui fonctionne déjà avec SQLite 26. Il ne migre pas la base, ne modifie
pas le ZIP applicatif et ne réinstalle pas un agent déjà connecté. Sur
Windows ou sans Docker, l’application peut fonctionner sans cet agent.

## Avant de commencer

- Télécharger le kit, le ZIP applicatif officiel et `SHA256SUMS` depuis
  la [release 2.15.2](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.15.2).
  Vérifier leurs SHA-256 avant toute exécution privilégiée. Extraire le kit
  dans un dossier de confiance inaccessible en écriture aux autres comptes.
- Effectuer et vérifier une sauvegarde indépendante. Prévoir une fenêtre
  d’intervention : seule la dernière commande redémarre l’application.
- Sur le serveur Linux ou dans une tâche DSM ponctuelle **root**, relever
  les chemins absolus réels du ZIP, du projet, des sauvegardes, du Docker CLI
  et du binaire Compose fourni par l’hôte. Utiliser les cibles réelles
  (`readlink -f`), pas leurs liens symboliques. Les chemins de cette procédure
  ne contiennent ni espaces ni virgules. Le projet doit avoir le service
  `application`, le fichier `compose.yaml` et la base `data/openfablab.db`.
- Relever l’ID complet `sha256:…` de l’image déjà vérifiée et construite avec
  le ZIP officiel. Dans Container Manager, vérifier que le conteneur actif
  utilise cette image. En ligne de commande, avec le nom réel du conteneur :
  `docker inspect --type container --format '{{.Image}}' NOM_DU_CONTENEUR`.
  L’étiquette d’image ne suffit pas à identifier la version.
- Créer un dossier indépendant pour l’agent, hors projet, données et
  sauvegardes, avec ses sous-dossiers `state` et `shared`. Ils doivent
  appartenir à root et ne pas être modifiables par les autres comptes.
  Exemple pour une installation neuve, avec un chemin à adapter :
  `install -d -m 0700 /srv/openfablab-agent /srv/openfablab-agent/state /srv/openfablab-agent/shared`.
  Ne pas changer les droits des dossiers existants pour forcer un contrôle.

## Les trois commandes, dans l’ordre

Remplacer les huit valeurs d’exemple (script, ZIP, projet, sauvegardes,
dossier agent, Docker, Compose et image) par celles du serveur. Exécuter
d’abord uniquement la commande suivante :

```bash
/bin/bash /chemin/du/kit/activate.sh /chemin/OpenFabLab-2.15.2.zip /chemin/projet /chemin/sauvegardes /chemin/agent /chemin/docker /chemin/docker-compose SHA256_IMAGE_COMPLETE --check
```

1. **Vérifier** : `--check` doit réussir. Les montages du projet et des
   sauvegardes sont en lecture seule ; seul l’état privé de l’agent reçoit
   les rapports et les essais fictifs. Vérifier le rapport `SETUP_RESULT-…log`.
2. **Préparer** : reprendre la même commande avec `--prepare` à la place de
   `--check`. Elle construit et vérifie l’image séparée de l’agent, sans
   interrompre l’application. Conserver l’état de préparation et le rapport.
3. **Activer** : seulement après vérification des deux rapports, remplacer
   `--prepare` par `--install --confirm AUTHORIZE-LOCAL-AGENT-2.15.2`.
   La procédure réalise PRE, ajoute le canal local en lecture seule,
   redémarre le même runtime, vérifie l’application puis réalise POST.

Ne pas exposer l’administration DSM ni le socket Docker sur le réseau.
Seuls le contrôleur local et l’agent séparé ont accès au socket Docker ;
le serveur web n’en dispose pas. Aucun port entrant n’est ouvert par le kit.
L’accès sortant nécessaire aux contrôles WordPress et aux releases officielles
reste distinct des aides isolées de sauvegarde/migration.

## Vérification et secours

Vérifier `AGENT_INSTALLATION_SUCCESS` dans l’état privé de l’agent, la santé
de l’application, les sauvegardes PRE/POST et l’état « Agent local connecté »
dans **Réglages → Système et sauvegardes → Mises à jour**. Tester d’abord
une recherche de mises à jour sans demander d’installation.

En cas de refus, conserver les dossiers et les rapports. Ne pas effacer le
jeton, modifier manuellement la configuration ou relancer `--install` après
une interruption sans diagnostic. Aucun retour arrière destructeur n’est
automatique. Voir le
[guide de secours](https://github.com/OpenFabLab-FR/OpenFabLab/blob/v2.15.2/docs/update-agent.md).

Cette activation neuve a été vérifiée localement avec des données fictives et
Docker simulé. Elle reste à vérifier sur un vrai Synology. Au FougèresLab,
l’import du ZIP 2.15.2 depuis la 2.15.1 a réussi sur Synology, avec un agent
déjà connecté : c’est un autre parcours que l’activation initiale.
