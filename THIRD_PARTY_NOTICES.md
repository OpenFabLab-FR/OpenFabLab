# Ressources tierces redistribuées

La licence MIT d'OpenFabLab ne remplace pas les licences ci-dessous. Les logos institutionnels, logos de structures, ancien logo du réseau FabLab, signatures et polices propriétaires de l'installation historique ne sont pas distribués.

## jsQR 1.4.0 — Apache License 2.0

Auteur : Cosmo Wolfe. Source : [cozmo/jsQR](https://github.com/cozmo/jsQR). Les copies JavaScript sont conservées dans `static/vendor/` et `wordpress/openfablab-reservations/assets/`, accompagnées chacune du texte complet `jsQR-LICENSE.txt`. Le copyright présent dans le composant est conservé. Aucun changement à cette bibliothèque.

## Libre Franklin — SIL Open Font License 1.1

Copyright (c) 2015, Impallari Type. Auteurs crédités par le projet : Pablo Impallari, Rodrigo Fuenzalida, Nhung Nguyen et Alexei Vanyashin. [Source de l'auteur](https://github.com/impallari/Libre-Franklin), révision `5e76d2f48045806a2d6827622df023aec97cd59e`.

Seules **Regular (400)** et **Bold (700)** sont distribuées, sans modification des fontes, dans `static/fonts/`. Le copyright et le texte complet SIL OFL 1.1 sont dans `static/fonts/OFL.txt`, les crédits amont dans `AUTHORS.txt`. La provenance et les empreintes sont dans `SOURCE.md`. Ces fontes restent sous OFL, pas sous MIT. Aucun fichier Franklin Gothic propriétaire n'est inclus.

## Dépendances installées, non vendorizées

Flask, Werkzeug, Jinja, segno, Pillow, resvg_py, python-docx, ReportLab, Gunicorn et tzdata sont installés par les fichiers de dépendances, pas copiés dans la source ou les ZIP. Leurs distributions installées conservent leurs licences respectives. Playwright et PHP WebAssembly sont des outils de développement installés séparément ; `node_modules/` n'est pas distribué. Une image Docker construite inclut les distributions Python avec leurs métadonnées/licences : ne pas les supprimer lors d'une redistribution de l'image.
