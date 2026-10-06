# Sécurité

## Signalement privé

Lorsqu'elle est activée sur le dépôt `OpenFabLab-FR/OpenFabLab`, utiliser la fonction GitHub **Security → Report a vulnerability** (Private Vulnerability Reporting). Son activation doit être vérifiée avant publication ; ce document ne prétend pas qu'elle est déjà active. Si elle n'est pas disponible, demander un canal privé au responsable du dépôt sans publier de détails exploitables dans une issue.

Décrire les versions concernées, les étapes reproductibles avec des données fictives et l'impact. Ne transmettre ni secret réel ni base nominative. Aucun SLA ou délai de réponse n'est garanti. La première publication publique est l'application 2.6.1 et Reservations 2.6.1 ; vérifier les versions annoncées dans les futures releases pour les correctifs.

## Protection d'une installation

- Utiliser HTTPS ; restreindre l'administration par une protection réseau adaptée, VPN ou dispositif d'accès contrôlé. **Les PIN à quatre chiffres ne constituent pas seuls une protection Internet suffisante.**
- Les liens de récupération du PIN et d'annulation sont privés. Ne pas les conserver dans des logs, captures ou documents publics.
- Protéger `data/`, les fichiers de dérivation PIN, la clé Flask, le secret WordPress, les webhooks, profils et sauvegardes. Ne pas les placer dans un répertoire servi publiquement.
- N'autoriser qu'une instance OpenFabLab à synchroniser un WordPress donné. Normal et Test isolent les données, pas deux serveurs maîtres concurrents.
- En 2.8.1, aucun annuaire n'est synchronisé vers WordPress : les demandes et réponses temporaires sont chiffrées, puis expurgées. Les tables historiques peuvent encore contenir des données privées et doivent rester protégées. ID + un contact concordant est le contrôle prévu côté OpenFabLab, **pas une preuve cryptographique de possession du contact**. Évaluer ce compromis, limiter les accès et informer les personnes.
- Le protocole 4 utilise uniquement des échanges sortants OpenFabLab → WordPress. N'ouvrir aucune route NAS pour ce parcours ; les liens publics reviennent vers la page WordPress dédiée. Les jetons sont des capacités privées : ne pas les partager, les journaliser ou les inclure dans les captures. Voir [sécurité et conservation du relais](docs/outbound-2.8.1.md).
- Mettre à jour le serveur, WordPress et leurs dépendances. Limiter les comptes administrateurs et tester les restaurations.

La licence MIT ne fournit aucune garantie. Chaque structure reste responsable de sa configuration, de ses contrôles d'accès et des règles de conservation applicables.
