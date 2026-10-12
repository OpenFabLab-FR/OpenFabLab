# Apports développés en OpenFabLab 2.8.5, intégrés à la stable 2.8.6

Cette étape, développée depuis la stable 2.8.4 et utilisée localement, n'a pas
fait l'objet d'une release séparée. Ses apports sont distribués intégralement
dans **OpenFabLab 2.8.6**. Les descriptions ci-dessous conservent leur contexte
2.8.5 ; voir [les corrections complémentaires 2.8.6](corrections-2.8.6.md),
notamment l'identité Discord désormais facultative sur choix explicite. Le moteur
transactionnel, les familles, l'attente, l'idempotence et les échanges HTTPS
exclusivement sortants sont conservés.

## Corrections et utilisation

Les notifications Discord classiques ne changent pas. Les événements du moteur commun alimentent un journal après validation métier, quel que soit le parcours. Aucun nom, identifiant public, contact ou lien personnel n’est placé dans les messages de réservation. Les événements Test sont exclus des envois Discord. Les réglages activés/désactivés restent respectés.

Une réponse Discord perdue ne permet pas de garantir un envoi exactement une fois : l’événement est marqué **incertain**, sans retransmission automatique susceptible de créer un doublon. Une interruption après prise en charge suit la même règle. Aucun ancien événement 2.8.4 n’est renotifié rétrospectivement.

Les suggestions de communes réutilisent le référentiel et le JavaScript existants. L’API publique ne retourne aucune fiche usager ; elle est limitée et disponible uniquement lorsque l’inscription publique est ouverte. Les codes étrangers, une panne ou une commune inconnue conservent la saisie manuelle.

Dans Structure, près de SMTP, **Modèles d’e-mails de réservation** permet d’éditer sujet et texte, afficher un aperçu fictif et restaurer chaque modèle. Pas de code HTML exécuté. Variables : `{structure}`, `{animation}`, `{date}`, `{horaire}`, `{participants}`, `{places}`, `{lien_reservation}`, `{lien_information}`, `{date_limite}`. Les liens apparaissent une fois ; le lien informatif absent retire sa ligne. La date limite concerne les propositions. Les destinataires et les liens sont déterminés par le moteur, pas par le modèle. Les modèles sont inclus dans le profil de configuration privé ; les secrets SMTP restent exclus.

L’annulation personnelle demande d’abord de choisir l’action, puis de la confirmer. WordPress affiche l’attente et ne confirme rien avant le résultat OpenFabLab. Les sections Historique et Modifier les participants restent indépendantes ; la recherche équipe conserve les personnes sélectionnées et ne charge que 25 résultats à la fois. Aucun annuaire public n’est ajouté.

## Rattachement des inscriptions

La réservation avec compte vérifié utilise la clé interne permanente de chaque
participant, et non une ressemblance de nom ni le seul code public. Responsables
et enfants restent chacun liés à leur propre fiche. Le plugin officiel 2.8.2
conserve ce fonctionnement, sans évolution du protocole.

Dans Participants, **Rattacher à un compte usager** propose une recherche privée,
puis montre le participant inscrit et le compte choisi avant confirmation.
Administrateur et Modérateur sont autorisés ; CSRF, compte actif, âge/responsable
et doublons sont contrôlés dans une transaction. Aucun rapprochement automatique.
L’équipe doit vérifier que le compte choisi appartient bien à la personne inscrite.

Ce rapprochement ne crée ni réservation, fiche, passage ni place supplémentaire.
Noms/coordonnées de réservation, état, présence, dates, groupe, liens et historique
sont conservés. Seules la clé de compte, le code public et la trace de vérification
changent. Le journal existant `reservation_actions` enregistre
`link_account:<clé interne>` avec rôle/date ; l’historique familial reçoit un
événement « Compte rattaché ». Aucun nouveau champ/table pour ce complément.
Un compte déjà rattaché n’est pas remplacé automatiquement.

Le CSV bénévoles conserve son séparateur et les anciennes colonnes. La durée cumulée ne compte que les sessions clôturées et calculables ; une visite ouverte reste une visite dans le compteur existant, mais sa durée n’est pas extrapolée. L’export ne possède pas de filtre annuel : le cumul utilise donc, comme le nombre de visites, tout l’historique.

Dans l’ICS, confirmations et présence sont distinctes. Les places restantes excluent aussi les places temporairement proposées ; aucun nom de participant n’est exporté. Les UID et dates des événements gardent le même calcul.

## Compatibilité et migration

SQLite **19** : ajout `fablab_services.information_url TEXT NOT NULL DEFAULT ''` et table `reservation_discord_events` avec empreinte de clé d’événement, type, animation facultative, environnement, dates et état de livraison. Index de file technique. Aucun changement des tables de places, participants, familles ou factures. Migration et schéma transactionnels, sauvegarde PRE18 nécessaire ; ne jamais lancer 2.8.4 sur une base 19.

Les nouveaux défauts 10/60 secondes ne remplacent aucune valeur existante. Le plugin **2.8.5** est nécessaire pour la nouvelle présentation WordPress et le lien d’information. Le couple 2.8.5/2.8.2 reste compatible pour réserver : le champ supplémentaire n’est envoyé que si le plugin annonce `animation_information_v1`. Aucun changement arbitraire de révision : protocole **4 / révision 3**, formats et protections antérieurs conservés. Le plugin 2.8.5 accepte aussi le catalogue 2.8.4 sans ce champ. Aucune migration de tables WordPress ni régénération de secret.

Le lien informatif accepte uniquement HTTP/HTTPS publics, sans authentification ni secret dans les paramètres. Adresses privées littérales et domaines locaux refusés. Il n’est jamais téléchargé ni résolu côté serveur ; une validation syntaxique ne peut garantir la destination future d’un domaine modifié par un tiers.

Voir [mise à jour](upgrade.md), [e-mails](email-templates.md), [WordPress](wordpress.md) et [compatibilité des plateformes](platform-compatibility.md). Aucun abonnement ni fonctionnalité FIL n’est développé.
