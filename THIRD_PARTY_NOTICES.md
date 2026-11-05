# Ressources tierces redistribuées

La licence MIT d'OpenFabLab ne remplace pas les licences ci-dessous. Les logos institutionnels, logos de structures, ancien logo du réseau FabLab, signatures et polices propriétaires de l'installation historique ne sont pas distribués.

## jsQR 1.4.0 — Apache License 2.0

Auteur : Cosmo Wolfe. Source : [cozmo/jsQR](https://github.com/cozmo/jsQR). Les copies JavaScript sont conservées dans `static/vendor/` et `wordpress/openfablab-reservations/assets/`, accompagnées chacune du texte complet `jsQR-LICENSE.txt`. Le copyright présent dans le composant est conservé. Aucun changement à cette bibliothèque.

## Libre Franklin — SIL Open Font License 1.1

Copyright (c) 2015, Impallari Type. Auteurs crédités par le projet : Pablo Impallari, Rodrigo Fuenzalida, Nhung Nguyen et Alexei Vanyashin. [Source de l'auteur](https://github.com/impallari/Libre-Franklin), révision `5e76d2f48045806a2d6827622df023aec97cd59e`.

Seules **Regular (400)** et **Bold (700)** sont distribuées, sans modification des fontes, dans `static/fonts/`. Le copyright et le texte complet SIL OFL 1.1 sont dans `static/fonts/OFL.txt`, les crédits amont dans `AUTHORS.txt`. La provenance et les empreintes sont dans `SOURCE.md`. Ces fontes restent sous OFL, pas sous MIT. Aucun fichier Franklin Gothic propriétaire n'est inclus.

## Dépendances installées, non vendorizées

Flask, Werkzeug, Jinja, segno, Pillow, resvg_py, python-docx, ReportLab, Gunicorn et tzdata sont installés par les fichiers de dépendances, pas copiés dans la source ou les ZIP. Leurs distributions installées conservent leurs licences respectives. Playwright et PHP WebAssembly sont des outils de développement installés séparément ; `node_modules/` n'est pas distribué. Une image Docker construite inclut les distributions Python avec leurs métadonnées/licences : ne pas les supprimer lors d'une redistribution de l'image.
# Catalogues 2.15.0 et PDF

Les catalogues natifs DE/ES/FI/EN ont été préparés hors ligne avec des modèles
Helsinki-NLP OPUS-MT, puis corrigés pour les libellés métiers et contrôlés pour
les variables/nombres : [opus-mt-en-de](https://huggingface.co/Helsinki-NLP/opus-mt-en-de)
et [opus-mt-en-fi](https://huggingface.co/Helsinki-NLP/opus-mt-en-fi) (CC BY 4.0),
[opus-mt-fr-es](https://huggingface.co/Helsinki-NLP/opus-mt-fr-es) et
[opus-mt-fr-en](https://huggingface.co/Helsinki-NLP/opus-mt-fr-en) (Apache 2.0).
Les poids et outils d’apprentissage ne sont pas distribués ou requis au runtime.
Aucune donnée personnelle n’a servi à ces traductions. Une relecture par des
locuteurs natifs reste souhaitable ; aucune certification linguistique annoncée.
Les contenus propres à une structure ne sont jamais traduits artificiellement.

pypdf (BSD-3-Clause) sert à vérifier les PDF importés, en processus isolé ;
ReportLab (BSD) et segno (BSD) restent utilisés pour les documents et QR.
Les licences des dépendances installées restent dans leurs distributions.

