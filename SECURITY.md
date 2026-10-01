# Sécurité

## Signalement privé

Lorsqu'elle est activée sur le dépôt `OpenFabLab-FR/OpenFabLab`, utiliser la fonction GitHub **Security → Report a vulnerability** (Private Vulnerability Reporting). Son activation doit être vérifiée avant publication ; ce document ne prétend pas qu'elle est déjà active. Si elle n'est pas disponible, demander un canal privé au responsable du dépôt sans publier de détails exploitables dans une issue.

Décrire les versions concernées, les étapes reproductibles avec des données fictives et l'impact. Ne transmettre ni secret réel ni base nominative. Aucun SLA ou délai de réponse n'est garanti. La première publication publique est l'application 2.6.1 et Reservations 2.6.1 ; vérifier les versions annoncées dans les futures releases pour les correctifs.

## Protection d'une installation

- Utiliser HTTPS ; restreindre l'administration par une protection réseau adaptée, VPN ou dispositif d'accès contrôlé. **Les PIN à quatre chiffres ne constituent pas seuls une protection Internet suffisante.**
- Les liens de récupération du PIN et d'annulation sont privés. Ne pas les conserver dans des logs, captures ou documents publics.
- Protéger `data/`, les fichiers de dérivation PIN, la clé Flask, le secret WordPress, les webhooks, profils et sauvegardes. Ne pas les placer dans un répertoire servi publiquement.
- N'autoriser qu'une instance OpenFabLab à synchroniser un WordPress donné. Normal et Test isolent les données, pas deux serveurs maîtres concurrents.
- L'annuaire WordPress privé contient des coordonnées en clair nécessaires au préremplissage. ID + un contact concordant est le contrôle prévu, **pas une preuve cryptographique de possession du contact**. Évaluer ce compromis, limiter les accès et informer les personnes.
- Mettre à jour le serveur, WordPress et leurs dépendances. Limiter les comptes administrateurs et tester les restaurations.

La licence MIT ne fournit aucune garantie. Chaque structure reste responsable de sa configuration, de ses contrôles d'accès et des règles de conservation applicables.
