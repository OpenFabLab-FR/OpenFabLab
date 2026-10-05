# Familles et réservations — OpenFabLab 2.8.0

Fonctions disponibles dans la version stable 2.8.0, avec le plugin facultatif
Reservations 2.8.0. OpenFabLab reste la source de vérité, quel que soit le canal.

## Une personne, un compte, une place

Chaque participant possède un véritable compte OpenFabLab, y compris les enfants.
Les rattachements relient les comptes à un ou plusieurs responsables, sans créer
de catégorie « famille ». Un responsable qui réserve sans participer ne consomme
pas de place ; s'il participe, il est sélectionné comme toute autre personne.
Un adulte et deux enfants sélectionnés consomment donc trois places.

Les réglages **Usagers → Âges, autonomie et familles** définissent l'âge minimal
sans responsable et l'âge permettant d'être responsable (valeurs initiales :
15 et 18 ans). Ces seuils ne constituent pas une déclaration de majorité juridique.
Les coordonnées exigées sont configurables par niveau. Les nouveaux mineurs
renseignent une date de naissance complète ; les comptes historiques conservent
leur année de naissance et le calcul historique de l'âge dans l'année.

Un participant non autonome doit réserver avec au moins un responsable éligible
rattaché à son compte. Le même responsable peut participer avec plusieurs membres
dans une demande : il reste une seule personne, donc une seule place. Un responsable
inactif ou dont les coordonnées requises manquent n'est pas éligible. Devenir autonome
ne supprime ni le compte ni ses rattachements ; l'équipe peut terminer manuellement
un rattachement tout en conservant sa trace.

## Moteur commun

La borne, l'administration et le plugin WordPress 2.8 utilisent le moteur
transactionnel OpenFabLab. La capacité est vérifiée après validation de tous les
participants, dans la même transaction SQLite que les inscriptions. Le groupe est
entièrement confirmé ou entièrement en liste d'attente ; aucune confirmation
partielle n'est autorisée. Chaque créneau dispose de son propre contrôle.

Une clé de demande permet de répéter une transmission dont la réponse a été perdue
sans créer de doublon. L'ajout ultérieur d'une personne vérifie à nouveau la capacité
et les responsables ; le retrait d'un responsable laissant seul un membre non autonome
est refusé. Les confirmations et annulations concernent toute la demande, les
présences restent individuelles.

La borne identifie le compte par son identifiant et une coordonnée déjà connue avant
de présenter les comptes liés. WordPress n'héberge plus d'annuaire familial : il
relaie des appels privés signés vers OpenFabLab via HTTPS. Des autorisations courtes,
des choix opaques, une limitation des tentatives et une protection anti-rejeu sont
vérifiés côté serveur. Ni dates de naissance ni identifiants internes des membres
ne sont exposés dans le catalogue public. Les écrans identifiés ne sont pas mis en cache.

OpenFabLab fonctionne sans WordPress et sans Internet lorsque le serveur local reste
accessible. À l'inverse, la réservation WordPress exige que ce serveur soit joignable :
une coupure ne doit jamais être présentée comme une confirmation.

## Liste d’attente automatique et e-mail

Un e-mail valide est obligatoire pour toute nouvelle demande, quel que soit son
canal. Un enfant peut utiliser les coordonnées d’un responsable rattaché éligible,
sans les recopier sur son compte. Après identification, un compte sans e-mail valide
est invité à le compléter. Sans aucune coordonnée déjà connue pour identifier le
compte, l’équipe doit d’abord compléter la fiche : l’identifiant seul ne dévoile pas
une famille. Le téléphone est facultatif par défaut ; une option indépendante
« Téléphone obligatoire pour réserver une animation » peut l’exiger.

La file suit l’ancienneté des demandes, en sélectionnant le plus ancien groupe
qui tient **entièrement** dans les places libres. Un groupe trop grand est sauté,
sans perdre sa priorité chronologique. Une proposition bloque temporairement une
place par participant ; aucune autre demande ne peut consommer ces places. Le
groupe accepte ou refuse par son lien personnel reçu par e-mail. Un GET, aperçu
de messagerie ou scanner de liens ne confirme rien : la réponse exige un POST
protégé. La répétition d’une acceptation ne crée pas de place supplémentaire.

Une annulation, un refus, une expiration ou une augmentation de capacité relance
la file automatiquement. L’équipe peut intervenir exceptionnellement, mais la
confirmation manuelle n’est pas le parcours normal. Le traitement périodique local
fonctionne sans WordPress, toutes les 30 secondes environ ; les actions de libération
et modifications d’équipe recalculent aussi la file après validation. Ce délai
n’est pas une garantie de livraison des e-mails.

Configurer **Structure → Réservations publiques** : adresse HTTPS publique exacte
d’OpenFabLab (préfixe inclus) et délai de réponse en heures. Valeur initiale :
24 heures ; une valeur existante est conservée. L’échéance ne dépasse jamais la
clôture des inscriptions. Configurer également le SMTP natif de la structure.

Les confirmations, attentes, propositions, modifications et annulations utilisent
un journal d’envoi privé durable. Les erreurs réseau déclenchent des reprises
bornées, avec identifiant de message stable ; un redémarrage ne perd pas la demande.
SMTP ne garantit pas une livraison exactement une fois après un accusé perdu :
un message peut exceptionnellement être reçu deux fois, jamais les places.
Une panne SMTP ne doit pas être présentée comme un e-mail effectivement livré.
Les réservations Test ne déclenchent aucun envoi SMTP réel automatiquement.

L’administration distingue confirmés, places proposées, places libres et attente,
avec échéance et historique. Le groupe reste indivisible. Les valeurs historiques
de rappels du plugin sont conservées, mais ne déclenchent pas de relances 2.8 ;
le nouveau moteur assure ses propres notifications et propositions.

La nouvelle interface WordPress nécessite JavaScript ; le parcours borne et la
réponse aux propositions sont utilisables sans JavaScript.

## Données et migration

Le passage au schéma SQLite 15 est additif et transactionnel : deux champs de
naissance sur les usagers, rattachements avec dates de création/fin, demandes
familiales, autorisations temporaires, anti-rejeu, suivi des transitions d'âge et
visibilité du calendrier, états et historique des groupes, propositions et journal
d’e-mails. Une candidate locale antérieure déjà au schéma 15 reçoit ces tables
additionnelles avec une PRE cohérente ; aucune migration historique n’est rejouée.
Aucune ancienne réservation n'est convertie en compte,
réinterprétée ou supprimée. L'ancien « accompagnateur » est uniquement historique.
Une sauvegarde cohérente du schéma 14 précède la migration.

Les sauvegardes complètes incluent la base et donc ces nouvelles relations.
Les coordonnées du responsable suffisent lorsque la politique de structure le
permet ; celles des enfants ne sont pas recopiées dans les demandes. Les exports
nominatifs restent des documents privés pour l'équipe. L'export public d'un profil
de structure ne contient aucun compte ni rattachement. La durée de conservation
et les suppressions demandées restent à préciser dans la politique de la structure ;
terminer une relation n'efface pas l'historique métier des personnes.

## Passage du plugin WordPress 2.7 au plugin 2.8

**Seul le stockage historique du plugin WordPress peut être nettoyé. Toutes les
animations passées, inscriptions, statistiques, usagers et facturations OpenFabLab
restent conservés.** Les anciens liens et réservations propres au plugin ne sont
pas migrés vers sa nouvelle interface.

Le nettoyage n'est jamais automatique à l'installation. Il nécessite les droits
administrateur WordPress, une sauvegarde privée préalable téléchargée, une case de
confirmation et la saisie « NETTOYER LE PLUGIN ». Les six tables du plugin sont
explicitement ciblées, dans une transaction ; aucune API OpenFabLab n'est appelée.
Les options de configuration et le secret sont conservés. Garder également une
sauvegarde WordPress complète pour permettre une restauration de cet ancien stockage.
Ne procéder qu'après vérification qu'aucune réservation active n'est à reprendre.

Configurer l'adresse HTTPS d'OpenFabLab dans le plugin 2.8 et conserver le secret
privé partagé. Le couple application 2.8/plugin 2.7 n'est pas utilisable pour de
nouvelles réservations. Les anciens endpoints de synchronisation sont refusés,
afin d'empêcher deux moteurs indépendants de confirmer les mêmes places.

Les tests automatisés utilisent des données et transports fictifs. Le déploiement
NAS, le raccordement du plugin 2.8.0 et le nettoyage volontaire de son ancien stockage
ont été vérifiés par l'exploitant du FougèresLab. La publication ne modifie aucun de
ces services et ne remplace pas la validation SMTP/HTTPS de chaque structure.

## Évolutions ultérieures

Les règles d'âge et de responsabilité peuvent ensuite être réutilisées pour les
ressources, avec habilitations et contraintes propres à chaque machine. Cela reste
une évolution future : aucune règle universelle de réservation de machine n'est
déduite automatiquement des seuls rattachements familiaux.
