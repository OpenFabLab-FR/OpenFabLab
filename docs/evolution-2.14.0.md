> Référence historique de l’étape 2.14.0, intégrée à la stable 2.14.4.
> Pour une installation actuelle : [utilisation](utilisation.md), [WordPress](wordpress-2.14.4.md)
> et [mise à jour](upgrade.md). Les mentions de candidate ci-dessous décrivent leur époque.

# OpenFabLab 2.14.0 — guide de la candidate

Cette version est une candidate locale. La stable publique de référence reste
2.13.0 jusqu’à validation et publication explicites. Aucune installation de
production n’est modifiée par sa préparation.

## Français et anglais

Le sélecteur FR/EN suit le navigateur, pas les autres appareils. L’administration
possède son propre choix. Les textes natifs, messages, contrôles et aides utilisent
des catalogues locaux ; aucun service de traduction n’est appelé pendant l’utilisation.

Dans Réglages → Borne, choisir la langue principale, les langues proposées et
le retour après inactivité (10 minutes initialement, de 1 à 120). L’activité au
clavier ou au tactile prolonge le parcours. Une session publique abandonnée revient
à l’accueil et perd ses autorisations temporaires et informations non enregistrées.
Les protections et délais plus courts de l’inscription restent prioritaires.
L’administration n’utilise pas cette minuterie.

Les noms, catégories personnalisées, descriptions, notes et modèles d’e-mails
restent dans leur langue d’origine. Les clés, montants, statuts et données stockées
ne changent pas avec la langue. Les mots de confirmation sensibles, par exemple
`SUPPRIMER`, restent exactement ceux attendus par le serveur.

## Carnet de maintenance

Activer Maintenance des machines dans Réglages → Structure. Le module est
désactivé initialement et indépendant des réservations et habilitations.
Les machines du catalogue existant réutilisent leur identité de ressource,
sans duplication des locations, devis et factures.

Une fiche distingue trois états : Opérationnelle, En maintenance, Hors service.
Un état opérationnel ne garantit pas qu’un créneau soit libre. Une intervention
préventive ne change pas automatiquement l’état. Une indisponibilité technique
empêche une nouvelle réservation ou confirmation de ressource concernée, mais
ne supprime ni n’annule automatiquement les réservations existantes.

Administrateurs et modérateurs autorisés peuvent enregistrer une intervention
à sa date réelle, corriger son contenu avec historique, changer l’état et gérer
les rappels. Les corrections vérifient la version du formulaire : une modification
concurrente impose de recharger la fiche. L’auteur est le rôle authentifié connu
du système, pas une identité individuelle inventée. Les historiques ne comportent
pas de commande courante de suppression définitive.

Les descriptions d’intervention sont internes. Pour communiquer, cocher
« Signaler cette indisponibilité aux usagers » et saisir un motif public distinct.
L’inscription dans la liste WordPress et la publication d’une date estimative de
retour sont également explicites. Une annonce ne dépend pas de l’activation des
réservations horaires ; elle ne réactive pas une ressource réservable inactive.

## Borne et rappels

Le réglage Informations sur les machines propose Accueil et identification,
Accueil uniquement, Identification uniquement ou Ne pas afficher. Sans annonce,
aucun contrôle n’apparaît. Le bandeau ouvre une fenêtre, jamais automatiquement.
Sur l’identification, la fenêtre se superpose au parcours et ne remplace pas la
caméra. Les commandes sont compactes sur petit écran, avec libellés accessibles.

Un rappel peut être indépendant ou associé à une intervention. Il peut être
reporté, annulé ou traité. Il ne réserve pas de créneau, ne change pas l’état de
la machine et ne représente jamais une intervention effectuée.

Dans Notifications, les rappels Discord sont désactivés initialement et utilisent
l’intégration existante. L’heure initiale est 9 h dans le fuseau de la structure.
Seuls le nom, l’objet explicite du rappel et sa date sont envoyés, jamais les notes
du carnet. Un rappel échu pendant l’arrêt du serveur n’est pas envoyé rétroactivement.
Sans Discord, le carnet et les rappels locaux restent utilisables.

Un identifiant durable protège chaque rappel contre les doubles envois. Reporter
un rappel avant son premier envoi déplace son échéance. Après un premier envoi,
le modifier ne provoque pas un deuxième envoi : créer un nouveau rappel pour une
nouvelle notification. En cas d’envoi incertain ou d’interruption, aucun renvoi
automatique n’est tenté ; examiner l’incident avant de décider d’un nouvel envoi.

## Calendrier interne et ouvertures

Les vues Semaine et Mois sont conservées. Les interventions apparaissent à leur
date réelle, les rappels en journée entière, les maintenances en cours jusqu’à
aujourd’hui sans date de fin fabriquée. Couleurs, intitulés et filtre Maintenance
et rappels permettent de les distinguer. Un clic ouvre la fiche autorisée.

Ouvertures exceptionnelles permet de définir une fermeture, une ouverture
supplémentaire ou un changement d’horaires à une date. Revenir aux horaires
habituels retire uniquement cette exception. Une fermeture supprime l’annonce
publique de cet OpenLab. Les passages et statistiques historiques restent intacts.

Les horaires sont interprétés dans le fuseau de la structure. Les heures
inexistantes au changement d’heure sont refusées pour les nouvelles exceptions.
La publication des OpenLab est désactivée initialement dans Structure ; chaque
exception peut également rester interne.

## Réservations et calendriers personnels

Un seul rappel e-mail peut être activé dans Notifications. Le délai initial est
48 heures. L’installation neuve propose l’activation lorsque le SMTP est configuré ;
la migration depuis 2.13 conserve les choix existants et n’active pas un rattrapage
des rappels anciens. Une activation ultérieure ne rattrape pas les échéances déjà
passées. Les nouveaux rappels ne remplacent pas les autres courriels de réservation.

Seules les réservations réellement confirmées de l’environnement Normal sont
éligibles. Le créneau réservé fait référence, et une demande familiale ne reçoit
qu’un message commun. Attente, proposition non acceptée, annulation et animation
passée ne déclenchent pas de rappel. Le modèle Rappel est personnalisable dans
les modèles de réservation. Les transports sont neutralisés dans les copies de test.

L’option d’ajout au calendrier personnel est activée initialement. Après confirmation
directe ou acceptation réussie, le système ajoute un fichier `.ics` et un lien Google
aux courriels sans modifier le modèle personnalisé. La page de confirmation ou de
gestion personnelle propose aussi cet ajout. Le plugin 2.14 permet l’affichage
correspondant côté WordPress.

Le fichier ne comporte que le titre, le créneau, le fuseau, le lieu et les informations
publiques. Aucun participant, contact ou jeton de gestion. L’UID reste stable si le
titre change. Les modifications et annulations peuvent fournir un fichier mis à
jour ; l’import ne garantit pas une synchronisation automatique entre les lecteurs.
Google reçoit seulement un lien de création prérempli, pas un accès à un compte.

## Confirmation de compte et diagnostic

L’écran existant confirme clairement la création, conserve l’identifiant et le QR,
et propose M’identifier maintenant. Il ne crée pas de deuxième compte et ne pointe
pas automatiquement la personne. Le retour automatique existant d’une minute reste actif.

État de l’installation reste réservé aux administrateurs, en lecture seule. Les
observations distinguent base, sauvegardes, relève et catalogue WordPress Normal/Test,
SMTP, rappels et stockage. Une configuration n’atteste pas une livraison ; un fichier
ne prouve pas une restauration ; une revendication récente n’est pas un envoi réussi.
Les détails restent repliables et n’affichent ni secrets ni chemins privés complets.

## Compatibilité et mise à jour

Application 2.14.0, SQLite **23** après migration additive **22 → 23**, plugin
facultatif Reservations **2.14.0**, protocole **4/révision 3** inchangé.
Le plugin 2.13 conserve les échanges historiques négociés, mais pas les nouveaux
shortcodes, langues et liens de calendrier dans ses interfaces.

Conserver une sauvegarde complète avant migration, l’ancien runtime et une sauvegarde
après vérification. Ne jamais ouvrir la base 23 avec l’application 2.13. Après un
démarrage public, protéger toutes les écritures récentes avant toute reprise humaine.
Aucun retour arrière destructeur automatique. Voir [mise à jour](upgrade.md),
[WordPress](wordpress.md), [architecture](architecture.md) et [tests](tests-2.14.0.md).
