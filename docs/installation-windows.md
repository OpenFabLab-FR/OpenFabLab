# Utiliser OpenFabLab sur Windows

Une seule application, dans un **conteneur Linux 64 bits**. Pas de version native Windows ni de validation matérielle Windows de cette version.

## Windows 11 : essai local ou démonstration

Vérifier les exigences actuelles de [Docker Desktop pour Windows](https://docs.docker.com/desktop/setup/install/windows-install/), virtualisation, WSL2 et conditions de licence. Ne pas confondre les besoins mémoire de Docker Desktop avec ceux du conteneur OpenFabLab. Depuis PowerShell administrateur, les [instructions Microsoft](https://learn.microsoft.com/en-us/windows/wsl/install) prévoient :

```powershell
wsl --install -d Ubuntu
wsl --list --verbose
```

Redémarrer si demandé et créer le compte Linux. Installer Docker Desktop depuis le site officiel, choisir les conteneurs Linux et activer l’intégration WSL de la distribution. Dans le terminal Ubuntu :

```sh
docker version
docker compose version
```

Extraire OpenFabLab dans le système de fichiers Linux de WSL, pas dans un dossier Windows synchronisé OneDrive ni un montage réseau. SQLite et ses fichiers persistants doivent rester sur un stockage local fiable. Suivre [les commandes communes](installation-common.md) depuis ce dossier. Accès local `http://localhost:5080/stat/` ; ne pas exposer cette démonstration sur Internet.

La fermeture de Docker Desktop ou de WSL peut interrompre le service. `restart: unless-stopped` ne remplace pas le lancement de l’environnement. Sauvegarder l’installation privée et la configuration avant les changements de Windows/WSL ; tester la restauration dans des volumes distincts. Les commandes système n’ont pas été exécutées sur le Mac de validation.

## Windows Server : hébergement permanent

Docker Desktop **n’est pas pris en charge sur Windows Server**. [Limite officielle Docker](https://docs.docker.com/desktop/troubleshoot-and-support/faqs/windowsfaqs/). Préférer une machine virtuelle Linux 64 bits administrée dans l’infrastructure existante, avec démarrage et stockage persistants, puis suivre [Linux](installation-linux.md). Valider hyperviseur, réseau, sauvegarde et mises à jour selon les règles de la structure ; aucune configuration automatique de l’hôte Windows n’est fournie.
