# Agent local de mise à jour — installation et secours

## Choisir son mode

La mise à jour manuelle reste possible. Le web fonctionne sans agent. Pour les
mises à jour intégrées, l’administrateur du serveur installe et autorise une fois
un agent séparé. Il dispose du socket Docker : c’est un composant privilégié,
dont les fichiers et la politique doivent être protégés comme un accès root.
Ne jamais monter ce socket dans le conteneur web.

L’API Unix authentifiée n’accepte que vérifier, préparer, suivre, annuler une
préparation, importer un ZIP et installer après confirmation. Aucun terminal, URL, chemin, commande,
montage ou secret fourni par le navigateur. Les opérations de récupération et
d’installation de l’agent ne sont pas accessibles à cette API.

## Installation initiale sur 2.15.2

Le ZIP applicatif validé conserve son installateur historique 2.15.0.
Sur une installation 2.15.2 sans agent, utiliser le kit séparé
`OpenFabLab-Agent-Setup-2.15.2.zip`, avec le ZIP applicatif officiel de la
[release 2.15.2](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.15.2).
Suivre [le guide du kit](../tools/agent-setup-2.15.2/README.md) :
vérifier, préparer, puis activer avec confirmation explicite. Le kit ne
migre pas la base et ne remplace pas l’image web. Un agent déjà connecté
n’a pas besoin d’être réinstallé. Une installation sans agent peut
continuer à fonctionner et être mise à jour manuellement.

Pour un runtime 2.15.1, utiliser uniquement son
[kit historique](../tools/agent-setup-2.15.1/README.md).

### Procédure historique sur 2.15.0 uniquement

Précondition : **application 2.15.0 installée et saine, SQLite 26**, manifeste
exact de son archive approuvée. La migration initiale 25→26 est une autre opération.
Un paquet DSM privé peut fixer les chemins de l’exploitant ; ne pas réutiliser
ses valeurs sur un autre serveur.

Sur une autre installation Docker/Compose, le responsable prépare une politique
JSON privée, appartenant à root, sans écriture groupe/autres. Champs obligatoires :
`protocol` (1), `project`, `compose_file`, `service`, `data`, `database`, `backups`,
`state`, `socket`, `token_file`, `repository_id` (1399693198), `docker`, `docker_root`,
`enabled` (booléen), `web_gid` (groupe effectif du processus web).

Les chemins sont absolus, sans lien symbolique, et approuvés localement. La base
canonique est `data/openfablab.db`. État agent, canal Unix, sauvegardes et données
doivent être indépendants. Le canal contient uniquement socket et jeton : groupe
web autorisé en lecture/connexion, sans écriture dans le répertoire. Les autres
fichiers agent restent root privés. Le responsable doit connaître le vrai service
Compose et disposer du Docker CLI et du plugin Compose compatibles du serveur.
Les agencements complexes sont refusés, pas devinés.

L’entrée opérateur réellement fournie est `python -m updater_agent`, avec options
globales `--policy CHEMIN_POLITIQUE --helper-image ID_IMAGE_SHA256`, puis :

- `setup-check --manifest CHEMIN_MANIFESTE` : lecture de production, SQLite,
  empreintes distinctes image/conteneur/stockage, Compose, espace et Normal/Test.
- `setup-prepare --manifest CHEMIN_MANIFESTE --docker-cli CHEMIN_CLI --compose-cli CHEMIN_COMPOSE` :
  construit une image agent séparée et teste ses clients, sans arrêter le web.
- `setup-install --manifest CHEMIN_MANIFESTE --confirm AUTHORIZE-LOCAL-AGENT-2.15.0` :
  exige l’image préparée et son reçu, réalise PRE, ajoute seulement deux variables
  et un canal Unix monté en lecture seule, redémarre **la même** application,
  contrôle santé/données/Normal-Test et réalise POST.

Cette installation initiale interrompt brièvement le web. Le Compose résolu peut
contenir des valeurs auparavant interpolées : il est conservé en mode root 0600,
jamais joint à un rapport public. L’original et l’image sont préservés en PRE.
Les environnements privilégiés/volumes inconnus, un agent déjà présent ou une
normalisation inattendue de Compose provoquent un refus avant arrêt.

Le conteneur agent utilise sa propre image, un socket Unix local et les seules
racines fixes de la politique. Aucun port réseau entrant n’est ouvert par l’agent.
Il doit accéder en HTTPS au dépôt officiel et, pour le contrôle signé, à WordPress.
Le build peut nécessiter l’accès au registre Python et aux dépendances épinglées.
Les aides de migration/test n’ont aucun accès réseau externe ni socket Docker.

## Mise à jour depuis l’administration

Dans **Réglages → Système et sauvegardes → Mises à jour** : vérifier, préparer,
examiner les étapes, puis confirmer l’installation. La confirmation expire après
trente minutes et ne sert qu’une fois. Fermer la page n’autorise rien de plus.
Une préparation peut être annulée avant toute interruption. L’agent ne lance
jamais une mise à jour automatiquement à l’arrivée d’une release.

Le téléchargement exige le dépôt officiel public identifié, HTTPS, une stable,
son tag/commit, l’URL exacte de l’asset, son digest SHA-256 fourni par GitHub et
un manifeste complet. Ce n’est pas une signature indépendante du compte GitHub :
la confiance repose sur le dépôt officiel et le transport TLS. Une ancienne
release sans ces métadonnées reste manuelle. L’[import ZIP local](upgrade-2.15.2.md)
est un mode séparé : manifeste obligatoire et provenance à vérifier par
l’administrateur, sans exiger une release GitHub.

Préparation : contrôle source/configuration, build sur base propre, budget de
couches, copie privée, migration isolée, vrai HTTP Gunicorn, source encore intacte.
Installation : écritures propres avant arrêt, sauvegarde chaude, arrêt, PRE froide
et image source, migration, intégrité/FK/historique/réglages, runtime, HTTP,
Normal/Test, POST et image cible. Chaque sauvegarde est restaurée et la base
ouverte en isolation ; la présence d’un ZIP seule n’est pas une validation.

Les rapports visibles n’exposent ni commandes libres ni valeurs de secrets. Les
preuves détaillées dans `state` sont privées ; ne pas publier les sauvegardes,
configurations ou empreintes de lignes issues d’une vraie installation.

## Révoquer ou récupérer indépendamment du web

Depuis une tâche administrateur locale, l’entrée opérateur fournit :

- `disable` : refuse les nouvelles mises à jour, sans tuer brutalement une
  opération déjà engagée ni supprimer la base ou les sauvegardes.
- `enable --confirm ENABLE-LOCAL-OPENFABLAB-AGENT` : réactivation explicite.
- `diagnose --job IDENTIFIANT` : état préservé, image/fichiers/base/volumes ;
  aucune restauration ou migration.
- `resume --job IDENTIFIANT --confirm RESUME-IDENTIFIANT` : uniquement la cible
  déjà installée et vérifiée, nouvelle ouverture puis contrôles et POST.

Ne pas effacer les reçus ou le verrou d’une opération active. Un arrêt brutal
reste une décision humaine : ne pas réexécuter l’installation ni remettre une
ancienne application sur une base migrée. Si la cible est incomplète ou si un
contrôle refuse, préserver les données, les images et toutes les preuves ; faire
examiner le diagnostic. Aucun retour arrière destructeur automatique n’existe.

## Références et limites

Au FougèresLab, l’exploitant confirme la mise à jour 2.15.1 → 2.15.2
par import du ZIP depuis l’administration sur Synology, sans passer par DSM :
`UPDATE_SUCCESS`, SQLite 26 inchangé. L’agent était déjà installé et connecté.
Cela ne valide pas une première activation du kit 2.15.2 sur ce NAS, ni une
installation réelle de la 2.15.2 par téléchargement depuis GitHub.

Le contrôle réel sur votre serveur demeure indispensable. Les essais Mac avec
Docker modélisé ne certifient pas Container Manager, une architecture CPU ou
les ACL de votre Synology. Le journal classe une panne Docker sans conserver
sa sortie brute potentiellement sensible ; une erreur inconnue reste inconnue.

[Montages Docker](https://docs.docker.com/engine/storage/bind-mounts/),
[sécurité du daemon](https://docs.docker.com/engine/security/),
[services Compose](https://docs.docker.com/reference/compose-file/services/) et
[projets Container Manager](https://kb.synology.com/en-global/DSM/help/ContainerManager/docker_project).
