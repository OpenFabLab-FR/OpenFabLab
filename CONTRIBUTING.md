# Contribuer à OpenFabLab

Les contributions ciblées, corrections, tests et améliorations documentaires sont bienvenues. Présenter le besoin, le comportement attendu et les vérifications effectuées ; éviter les refontes sans rapport avec la modification proposée.

- Utiliser uniquement des personnes, contacts et structures fictifs, par exemple le domaine `example.invalid`.
- Ne jamais joindre une base réelle, sauvegarde, profil privé, capture nominative, cookie, PIN, token, webhook ou secret. Nettoyer également les sorties de test et les archives.
- Exécuter les contrôles décrits dans [docs/development.md](docs/development.md), dont Python, PHP, JavaScript, syntaxe, migrations fictives et packaging. Ajouter des tests de non-régression proportionnés.
- Préserver les animations classiques, la séparation Normal/Test, la distinction réservation/présence et les permissions Administrateur/Modérateur.
- Concevoir les migrations de schéma de manière additive et idempotente. Ne jamais tester sur une production. Documenter sauvegarde et retour arrière.
- N'ajouter que des ressources dont les droits de redistribution sont explicites. Fournir copyright, licence et provenance ; mettre à jour les notices tierces.
- Construire les distributions depuis les listes autorisées, sans ajout global de fichiers locaux. Ne pas versionner `dist/`, les environnements de développement ou les données.

Les contributions acceptées sont distribuées sous la licence MIT du projet, sous réserve des composants tiers correctement identifiés. Aucun dépôt d'informations appartenant à un tiers sans autorisation.

Pour un problème de sécurité, suivre [SECURITY.md](SECURITY.md) plutôt que publier des détails exploitables ou des données privées dans une issue.
