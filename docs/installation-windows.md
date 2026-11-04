## Version stable 2.14.4 — SQLite 25

Télécharger la [release officielle](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.14.4)
et vérifier SHA256SUMS avant extraction. Une installation neuve utilise SQLite 25.
Pour une installation existante, lire [le parcours de mise à jour](upgrade.md) :
22→25 depuis 2.13.0, 23→25 ou 24→25 selon la source, avec sauvegardes et essai isolé.
Ne jamais utiliser une ancienne application sur une base migrée. Le plugin
Reservations 2.14.4 reste facultatif et se remplace séparément sans désinstallation.
[Utilisation](utilisation.md) · [WordPress](wordpress-2.14.4.md) · [Compatibilité](platform-compatibility.md).
Les exemples d’anciennes versions conservés ci-dessous sont des références historiques ;
les opérations générales restent à adapter à votre serveur et à sa configuration.

---

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
