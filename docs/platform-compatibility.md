# Architectures, prérequis et portée des validations

OpenFabLab : Python 3.10+ ; image actuelle **Python 3.12 slim Bookworm**, Flask/Gunicorn, SQLite, Pillow, resvg_py, python-docx, ReportLab et Segno. Les deux derniers rendent les documents et QR ; plusieurs dépendances possèdent des extensions natives. Les nouvelles installations documentées exigent un OS **64 bits**.

L’image Python de base est décrite dans la [liste officielle docker-library](https://github.com/docker-library/official-images/blob/master/library/python). Docker sait cibler [AMD64 et ARM64 sur Linux](https://docs.docker.com/engine/install/). Les métadonnées PyPI des versions épinglées offrent des wheels Linux AMD64 et ARM64 pour les dépendances directes, notamment [Pillow](https://pypi.org/project/Pillow/11.3.0/) et [resvg_py](https://pypi.org/project/resvg-py/0.2.0/). Cela établit une possibilité de construction, **pas** une validation d’exécution multiarchitecture.

| Environnement | Portée réelle |
|---|---|
| macOS ARM64, Python et navigateurs locaux | Environnement des tests applicatifs et simulations. Pas une image Linux. |
| Synology 64 bits | Fonctionnement 2.13.0 / SQLite 22 confirmé par l’exploitant sur son installation ; migration 21 → 22 réalisée auparavant en 2.11.0. Validation d'usage, sans nouveau rapport technique final de déploiement reçu. Ce retour ne certifie pas tous les modèles ou architectures. |
| Linux AMD64 / ARM64 | Guides et métadonnées de dépendances vérifiés ; pas de nouveau build Docker ni essai Linux réel ici. |
| Raspberry Pi 3/4/5 64 bits | Étude conditionnelle, sans essai physique ni certification. |
| Windows 11 + WSL2/Docker Desktop | Guide préparé, non exécuté matériellement. |
| Windows Server + VM Linux | Recommandation d’architecture, pas d’essai ni promesse Docker Desktop. |
| OS 32 bits | Non recommandé et non annoncé compatible. |

Construire le Dockerfile unique sur la cible et vérifier imports, QR/PDF, santé, persistance, charge et restauration avant tout usage réel. Aucun registre d’images OpenFabLab multiarchitecture testé n’est publié. Ne pas déduire la compatibilité ARM64 du seul processeur du NAS ou du Mac ; examiner OS, image, toutes les dépendances et volumes.

L’affichage est vérifié sur Chromium/WebKit redimensionnés : pas un substitut à Safari iPhone, tablette, caméra physique ou aux clients Apple/Outlook/Google natifs. Les exports ICS sont contrôlés structurellement ; l’import dans chaque client cible reste un contrôle terrain.
