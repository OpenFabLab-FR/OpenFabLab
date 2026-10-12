# Installer OpenFabLab sur Raspberry Pi

**Guide de préparation expérimental : aucun Raspberry Pi physique n'a été testé pour cette version.** Les wheels des dépendances sont examinées pour Linux ARM64 ; cela ne prouve ni leur exécution ni la performance sur un Pi.

Choisir Raspberry Pi OS **Lite 64 bits**, sans bureau inutile, depuis [Raspberry Pi Imager et les images officielles](https://www.raspberrypi.com/software/). Les [documents système](https://www.raspberrypi.com/documentation/computers/os.html) distinguent Lite et 64 bits. Pi 3 dispose d’une architecture AArch64, mais les modèles plus anciens ne doivent pas être assimilés à des plateformes 64 bits. [Référence Raspberry Pi](https://www.raspberrypi.com/news/raspberry-pi-os-64-bit/).

## Dimensionner sans surpromesse

| Matériel | Position à confirmer par un essai réel |
|---|---|
| Pi 3B, 1 Go | Expérimental ; mémoire et construction de l’image contraignantes, pas de compatibilité officielle annoncée. |
| Pi 4, 2 Go | Point de départ minimal envisagé, sous réserve de validation de la charge et des dépendances. |
| Pi 4, 4 Go | Marge plus confortable à évaluer, pas une mesure de performance validée. |
| Pi 5 | Davantage de marge pour une installation neuve, sans obligation ni garantie de débit. |

Une installation existante rapporte environ 206–218 Mo pour le conteneur, hors système, avec une charge CPU variable. Ce n’est ni une mesure Pi ni une garantie sur 1 Go. Prévoir aussi le pic mémoire du build, les rapports PDF et les sauvegardes. Éviter de compenser durablement un manque de RAM par des écritures intensives sur microSD.

Pour un usage permanent, privilégier un SSD externe fiable, une alimentation adaptée et des sauvegardes sur un autre support. La microSD peut servir à l’installation initiale ; tenir compte des écritures SQLite et de la durabilité. Mettre le stockage persistant sur le SSD, pas dans une couche éphémère du conteneur.

## Préparer puis vérifier

Configurer utilisateur/SSH via Imager, sans identifiants prédéfinis. Après démarrage :

```sh
uname -m
getconf LONG_BIT
df -h
```

Attendus : `aarch64` et `64`. Installer Docker et le plugin Compose selon [Docker Debian](https://docs.docker.com/engine/install/debian/) pour une base Debian 64 bits, avec le bon nom de distribution ; ne pas suivre le guide Raspberry Pi 32 bits. Puis suivre [Linux](installation-linux.md) et [les opérations communes](installation-common.md) : build, volumes, initialisation, démarrage automatique, arrêt/reprise, journaux, PRE/POST et restauration isolée.

Avant de qualifier l’installation : santé HTTP, QR et PDF, persistance après redémarrage, intégrité/FK, réservations/attente, charge et restauration doivent être vérifiées **sur le Pi cible**. Aucun nouveau système de synchronisation ou build multiarchitecture publié n’est nécessaire : le Dockerfile unique est construit sur la machine cible, sous réserve de validation.
