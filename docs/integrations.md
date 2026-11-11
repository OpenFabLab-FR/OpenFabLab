# WordPress, Discord et e-mails : les intégrations facultatives

OpenFabLab fonctionne sans service externe. Activez uniquement ce qui vous
est utile. Avant tout test avec un service tiers, utilisez des noms fictifs
et un espace de test séparé de la production.

## WordPress

Installer [Reservations 2.15.3](wordpress-2.15.3.md) et suivre le guide de
connexion. Le serveur OpenFabLab contacte le site en HTTPS ; il n’est pas
nécessaire de publier DSM ou l’administration OpenFabLab.

Le [catalogue](wordpress-2.15.3.md#installer-et-publier), le calendrier et les
inscriptions sont des affichages distincts. Séparer Normal et Test, utiliser
les identifiants partagés uniquement dans les réglages privés, contrôler
l’échange et vérifier les pages en visite anonyme. Les états publics
proviennent d’OpenFabLab. Les interventions, présences nominatives, devis et
documents internes ne doivent pas être publiés.

## Discord

Dans **Réglages → Communication → Notifications**, configurer un webhook
du canal choisi et sélectionner les événements utiles. Parmi les événements
disponibles figurent les rappels de maintenance et les signalements QR
lorsque ces options sont activées. Vérifier les autorisations des personnes
ayant accès au canal. Ne pas activer de contenu nominatif sans besoin défini.

Utiliser d’abord **Envoyer un test** vers un canal privé (aucune donnée
d’usager), puis essayer un rappel fictif si nécessaire pour vérifier la
date et le fuseau. Ne pas coller le webhook dans un rapport. Si
le test échoue, vérifier HTTPS sortant, permissions et sélection de l’événement
avant de modifier d’autres réglages. En cas de fuite, révoquer le webhook.

## SMTP

Dans **Réglages → Communication → Notifications**, ouvrir **E-mails SMTP**. Indiquer
l’hôte et le port fournis par votre opérateur, TLS ou STARTTLS selon son
guide, le compte (si requis) et une adresse d’expéditeur autorisée.
Conserver le mot de passe dans le réglage privé, pas dans Compose ou Git.

Envoyer le message de test vers une boîte autorisée, puis vérifier la
réception et les éventuels indésirables. Activer ensuite seulement les
notifications voulues. Les [modèles d’e-mails](email-templates.md) et les
réglages de réservation expliquent quels messages dépendent de la
configuration. Une prise en charge du SMTP n’est pas une garantie de
livraison : vérifier chiffrement, expéditeur et politique du fournisseur.

Dans une copie de recette, bloquer les envois externes **avant** de restaurer
des réglages. Voir [sauvegarde et restauration](backup-restore.md).
