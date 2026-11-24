# Sécurité

## Signalement privé

Lorsqu'elle est activée sur le dépôt `OpenFabLab-FR/OpenFabLab`, utiliser la fonction GitHub **Security → Report a vulnerability** (Private Vulnerability Reporting). Son activation doit être vérifiée avant publication ; ce document ne prétend pas qu'elle est déjà active. Si elle n'est pas disponible, demander un canal privé au responsable du dépôt sans publier de détails exploitables dans une issue.

Décrire les versions concernées, les étapes reproductibles avec des données fictives et l'impact. Ne transmettre ni secret réel ni base nominative. Aucun SLA ou délai de réponse n'est garanti. La première publication publique est l'application 2.6.1 et Reservations 2.6.1 ; vérifier les versions annoncées dans les futures releases pour les correctifs.

## Protection d'une installation

Version de référence : **OpenFabLab 2.18 / SQLite 29**, plugin facultatif
**Reservations 2.18 / protocole 4, révision 3**. Les informations nominatives des
notifications Discord de réservation sont désactivées par défaut et doivent
résulter d'un choix explicite, indépendant des notifications de création d'usager.
Ne pas inclure de coordonnées, jeton ou lien privé dans un libellé destiné à Discord.

Pour Mon compte, les limites par navigateur/adresse et par responsable,
la confirmation e-mail et les vérifications de doublons et de droits
familiaux réduisent les abus. La réponse publique de récupération ne révèle
pas si un compte existe. Le lien doit être confirmé dans le navigateur
d’origine et ne s’utilise qu’une fois ; l’ouverture seule n’active rien.
Le QR Code de borne n’est pas un secret de connexion. Ne jamais mettre en
cache partagé la page ou les réponses privées. Les comptes et liens
familiaux restent gérés dans OpenFabLab ; WordPress ne reçoit qu’une
file temporaire chiffrée. Voir [configuration WordPress](docs/wordpress.md).

- Utiliser HTTPS ; restreindre l'administration par une protection réseau adaptée, VPN ou dispositif d'accès contrôlé. **Les PIN à quatre chiffres ne constituent pas seuls une protection Internet suffisante.**
- Les liens de récupération du PIN et d'annulation sont privés. Ne pas les conserver dans des logs, captures ou documents publics.
- Protéger `data/`, les fichiers de dérivation PIN, la clé Flask, le secret WordPress, les webhooks, profils et sauvegardes. Ne pas les placer dans un répertoire servi publiquement.
- N'autoriser qu'une instance OpenFabLab à synchroniser chaque environnement WordPress donné. Normal et Test ne garantissent pas deux bases distinctes ; séparer les installations et le stockage pour les essais.
- En 2.8.1, aucun annuaire n'est synchronisé vers WordPress : les demandes et réponses temporaires sont chiffrées, puis expurgées. Les tables historiques peuvent encore contenir des données privées et doivent rester protégées. ID + un contact concordant est le contrôle prévu côté OpenFabLab, **pas une preuve cryptographique de possession du contact**. Évaluer ce compromis, limiter les accès et informer les personnes.
- Le protocole 4 utilise uniquement des échanges sortants OpenFabLab → WordPress. N'ouvrir aucune route NAS pour ce parcours ; les liens publics reviennent vers la page WordPress dédiée. Les jetons sont des capacités privées : ne pas les partager, les journaliser ou les inclure dans les captures. Voir [sécurité et conservation du relais](docs/outbound-2.8.1.md).
- Mettre à jour le serveur, WordPress et leurs dépendances. Limiter les comptes administrateurs et tester les restaurations.

Le bilan visuel de fréquentation est un document interne agrégé, accessible aux
administrateurs autorisés. Il affiche aussi les petits effectifs ; cette agrégation
ne garantit pas à elle seule l'anonymat lors d'une diffusion extérieure. Examiner
le contexte avant partage, sans joindre de base ou d'export nominatif.

La licence MIT ne fournit aucune garantie. Chaque structure reste responsable de sa configuration, de ses contrôles d'accès et des règles de conservation applicables.
