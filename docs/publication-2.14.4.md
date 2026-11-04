# Vérifications de publication — OpenFabLab 2.14.4

La validation fonctionnelle sur Synology, SQLite25 et WordPress2.14.4 est confirmée
par l’exploitant. Elle n’est pas assimilée à un rapport technique final SUCCESS
que l’agent aurait reçu. Aucun accès au NAS ou au WordPress de production n’a été
nécessaire pour préparer la publication.

Les contrôles de développement conservés comprennent 98 tests Python,379 contrôles
PHP et1746 assertions Chromium/WebKit. Les115 scénarios DSM et34 revérifications
du ZIP privé sont des simulations locales, pas une validation matérielle DSM.
Seuls les contrôles utiles à la publication sont réexécutés, pas toutes les suites.

Pour cette publication, des bases fictives créées avec les runtimes2.13.0/22,
2.14.0/23 et2.14.3/24 ont été migrées vers25 par le moteur approuvé : sauvegarde,
interruption transactionnelle, intégrité/FK, conservation des anciennes valeurs,
réexécution et démarrage HTTP. Les compléments historiques d’observation d’âge
et de composante anonyme manquante ne réécrivent pas les données existantes.
Aucune communication externe n’est autorisée pendant ces essais.

Les archives approuvées sont conservées dans l’historique privé. Le conditionnement
stable actualise seulement la documentation et l’étiquette de version Compose ;
Python, PHP, JS, CSS, templates, traductions, dépendances et schémas restent identiques
octet par octet aux fichiers validés. Les nouveaux tests publics ne font pas partie
du runtime. Les empreintes officielles sont celles des assets et de SHA256SUMS,
pas celles d’une ancienne candidate documentaire.

La distribution ne contient aucun paquet DSM privé, sauvegarde, base SQLite,
profil de structure, journal réel ou capture nominative. Les noms/adresses des
tests sont fictifs. Les sons sont synthétisés localement par le moteur existant,
sans ajout de fichiers audio tiers. La licence MIT et les avis des polices et
dépendances sont conservés.

Les guides de plateforme ne certifient pas tous les NAS, navigateurs matériels,
Raspberry Pi ou Windows. Vérifier la cible réelle, le build Docker, les volumes,
la restauration et les services optionnels avant toute réouverture.
