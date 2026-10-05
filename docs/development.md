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

Les tests 2.7.0 comprennent une fixture schéma 13 → 14 avec contrôle des colonnes/volumes/fichiers, sauvegarde pré-initialisation et rollback de migration ; catégories/default/réaffectation, borne/CSRF/limitation/session, SMTP simulé/QR et Discord minimal, ressources/concurrence/facturation/habilitations, calendrier et profils. `tests/test_private_backup.py` couvre sauvegarde complète, copie de test, restauration, PIN dérivés, intégrité, isolation réseau et refus des archives altérées. Les tests navigateur couvrent neuf largeurs (1440, 1024, 820, 768, 430, 390, 375, 360 et 320 px) et bloquent les requêtes externes. `tests/test_wordpress_reconciliation.php` couvre snapshots, conservation des transactions et confirmations/nonce/droits. Ces fixtures ne remplacent pas un test WordPress/InnoDB réel ni une vérification de délivrabilité SMTP chez chaque fournisseur.

Exécution ciblée :

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
php tests/test_wordpress_bookings.php
node tests/test_participants_ui.js
```

Pour un lancement direct de Python, utiliser les variables d'isolation décrites dans `tools/run_checks.py` : ne pas importer `app.py` dans un environnement contenant un chemin réel de base. Préférer le runner complet.

## Packaging

La validation 2.8.0 comprend **451 tests Python, 724 contrôles PHP et 622 contrôles JavaScript**. Elle couvre familles/responsables, migration/restauration 14 → 15, capacité et concurrence, groupes indivisibles, attente/offres/réponses/expiration, SMTP simulé, droits, borne sans WordPress et relais WordPress simulé. Les contrôles additionnels Chromium/WebKit couvrent 320, 360, 375, 390, 430, 480, 720, 768, 820, 1024, 1280 et 1440 px : 818 contrôles de pages/parcours, 696 de footer, 120 de typographie et 146 de contacts/liste d'attente/réponses. Installer WebKit avec `npx playwright install webkit`. Les fixtures et captures automatisées sont fictives. La vérification d'une copie privée de migration reste hors du dépôt, sans diffusion de ses données ni rapports d'exploitation.

NAS, migration réelle et liaison WordPress 2.8 ont été validés par l'exploitant du FougèresLab. Les suites locales ne constituent pas un test WordPress/MySQL réel ni un build Docker ; SMTP et SQL PHP y sont simulés. La concordance ID/contact n'est pas une authentification à usage unique ; la délivrabilité et HTTPS se vérifient par installation.

```sh
.venv/bin/python build_openfablab.py
.venv/bin/python build_wordpress_plugin.py
.venv/bin/python tests/check_v26_archives.py
```

Les constructeurs utilisent des listes autorisées et des dates/permissions ZIP fixes. Les deux ZIP doivent être identiques lors de deux constructions dans le même environnement. Pour une reconstruction strictement octet-identique, utiliser la même version de Python/zlib ; la compression peut différer entre versions. Le contrôleur compare également les octets des membres aux sources publiques et génère `dist/SHA256SUMS`. `dist/` n'est pas un contenu à committer.

Pour la release stable **2.8.0**, les ZIP applicatif et plugin validés ne sont pas reconstruits pour actualiser la documentation. Les guides embarqués peuvent encore porter la mention de candidate ; les documents du tag sont la référence stable. **Tous les fichiers runtime et le plugin sont identiques aux archives approuvées**. Seuls les guides, manifestes de développement et leur test de statut sont actualisés dans Git. La référence de téléchargement est l'asset de release et son `SHA256SUMS` ; reconstruire depuis Git avec les guides actualisés produirait une autre empreinte.

## Docker

`docker compose config --quiet`, puis `docker compose build application` sur une machine isolée. Sans Docker local, indiquer cette limite et ne pas annoncer un build d’image réussi. Les tests de publication reconstruisent le jeu de fichiers des instructions `COPY`, démarrent l’entrée WSGI et vérifient qu’un module manquant est détecté : ce contrôle runtime local ne remplace pas un build Docker. Aucune procédure DSM historique ne fait partie de cette suite publique.
