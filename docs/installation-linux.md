# Installer OpenFabLab sur Linux

Serveur ou mini-PC **Debian/Ubuntu Server 64 bits**, AMD64 ou ARM64 : architecture envisagée, pas nouvelle certification matérielle de cette version. Lire [compatibilité](platform-compatibility.md). Docker + Compose évitent une variante applicative par distribution.

## Installer Docker

Sur une machine neuve, suivre le dépôt officiel adapté au système : [Debian](https://docs.docker.com/engine/install/debian/), [Ubuntu](https://docs.docker.com/engine/install/ubuntu/). Ne pas exécuter un script d’installation trouvé ailleurs ni désinstaller aveuglément les paquets d’un serveur existant. Les commandes apt ci-dessous supposent le dépôt et sa clé déjà configurés suivant ce guide officiel.

```sh
uname -m
getconf LONG_BIT
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl status docker
sudo docker run --rm hello-world
sudo docker compose version
```

Les commandes d’installation système n’ont pas été exécutées sur le Mac de validation. L’accès au groupe Docker équivaut à un privilège élevé ; conserver `sudo` ou étudier le mode rootless, sans changer les permissions globales du socket. Les ports Docker peuvent contourner certaines règles de pare-feu : examiner le réseau réellement publié, pas seulement une règle UFW. [Précautions Docker](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

## Installer et exploiter

Créer un dossier dédié sur disque local fiable, vérifier l’archive et extraire application et guides. Conserver l’ensemble du contenu de `data`, fichiers cachés inclus. Utiliser le Compose fourni, indépendant de Synology, avec un port choisi selon [le guide commun](installation-common.md). Depuis ce dossier :

```sh
sudo docker compose config --quiet
sudo docker compose build application
sudo docker compose up -d application
sudo docker compose ps
sudo docker compose logs --tail=100 application
```

Compléter les paramètres de structure et comptes protégés. Arrêt, reprise, sauvegarde complète cohérente, restauration sur copie, mise à jour et diagnostic suivent [les opérations communes](installation-common.md). Ne pas exposer le serveur de développement Python ni ouvrir un port WAN pour WordPress. Les données sont conservées par les volumes, pas par le conteneur recréable.
