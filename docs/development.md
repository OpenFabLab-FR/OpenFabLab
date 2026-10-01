# Développement et contrôles reproductibles

Prérequis : Python 3.10+ avec `venv`/pip, Node.js **24.18+**, npm **11.16+**, PHP CLI 8.1+ recommandé. Les versions Node/npm sont celles exigées par l'alternative PHP WebAssembly choisie. Les dépendances applicatives sont figées dans `requirements.txt` ; les dépendances complémentaires de développement sont dans `requirements-dev.txt`. Les outils Node sont verrouillés par `package-lock.json`.
`requirements-dev.lock` fige aussi les dépendances transitives de l'environnement Python 3.12 utilisé pour cette édition ; l'installer à la place de `requirements-dev.txt` pour reproduire cet environnement précis.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci
npx playwright install chromium
.venv/bin/python tools/run_checks.py
```

Le runner crée un espace temporaire pour les bases, secrets fictifs, sauvegardes et sorties. Il désactive scheduler et météo lors de l'import, n'utilise aucun dossier privé voisin et refuse une configuration héritée de production. PHP WebAssembly 8.1 est utilisé uniquement si PHP natif est absent ; ce n'est pas un test d'intégration MySQL ou d'un WordPress réel. `PHP_TEST_COMMAND` peut sélectionner un exécutable PHP explicite. `TEST_CHROME` peut sélectionner un navigateur local pour Playwright, sinon son Chromium installé est utilisé. `TEST_PYTHON` désigne le Python isolé utilisé par les fixtures UI.

Les tests couvrent parcours, droits, schémas, fictive migration 12 → 13, réservations classiques/créneaux, capacité/attente, accompagnants, préremplissage, e-mails, maintenance Test, exports et responsive. Les tests PHP utilisent un stockage simulé et les tests navigateur bloquent les appels externes. Aucun vrai secret, PIN historique, base ou ZIP ancien n'est requis.

Exécution ciblée :

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
php tests/test_wordpress_bookings.php
node tests/test_participants_ui.js
```

Pour un lancement direct de Python, utiliser les variables d'isolation décrites dans `tools/run_checks.py` : ne pas importer `app.py` dans un environnement contenant un chemin réel de base. Préférer le runner complet.

## Packaging

```sh
.venv/bin/python build_openfablab.py
.venv/bin/python build_wordpress_plugin.py
.venv/bin/python tests/check_v26_archives.py
```

Les constructeurs utilisent des listes autorisées et des dates/permissions ZIP fixes. Les deux ZIP doivent être identiques lors de deux constructions dans le même environnement. Pour une reconstruction strictement octet-identique, utiliser la même version de Python/zlib ; la compression peut différer entre versions. Le contrôleur compare également les octets des membres aux sources publiques et génère `dist/SHA256SUMS`. `dist/` n'est pas un contenu à committer.

## Docker

`docker compose config --quiet`, puis `docker compose build application` sur une machine isolée. Sans Docker local, seule une validation statique est possible : l'indiquer, ne pas annoncer un build d'image réussi. Aucune procédure DSM historique ne fait partie de cette suite publique.
