# Utiliser OpenFabLab 2.15.1

- **Résumé** : personnes présentes, visiteurs du jour, créneaux confirmés
  en cours, matériels remis non rendus, indisponibilités et tâches. Les cinq
  dernières identifications et activités sont visibles, avec **Voir plus**.
- **Recherche** : ouvrir la loupe ou utiliser Cmd/Ctrl+K. Les résultats se
  limitent aux modules et aux droits du compte. Les fiches clients et leurs
  dossiers réellement liés sont réservés à l’administration habilitée.
- **Calendrier** : filtrer les événements et ouvrir leur fiche au clic. Les
  locations multijours ont une bande continue en vue semaine. Sur mobile,
  faire défiler la grille horizontalement pour consulter les autres jours.
- **Ressources** : ouvrir [la fiche unifiée](resources-maintenance.md) pour
  suivre une remise, une restitution, un entretien ou un tutoriel.
- **Personnalisation** : cinq langues standards locales, sélection publique
  facultative et langue d’administration indépendante. Les titres, noms,
  descriptions et e-mails personnalisés ne sont pas traduits automatiquement.

Les chapitres suivants conservent les parcours historiques.

---

# Utiliser OpenFabLab 2.14.4 au quotidien

Les fonctions sont modulaires : une option absente peut simplement être désactivée.
L’administration et les parcours publics n’ont pas les mêmes autorisations.

## Accueillir et identifier

La borne affiche les personnes présentes et les visiteurs anonymes. Un usager
s’identifie avec son QR Code, son identifiant ou le parcours manuel autorisé.
Le départ suit la confirmation existante, éventuellement avec compte à rebours.
« Finalement, je reste » annule immédiatement cette confirmation. Pendant une
fenêtre bloquante, les commandes d’arrière-plan et les langues sont inactives.

La création de compte conserve la saisie lorsqu’une validation échoue. Un identifiant
de quatre chiffres déjà attribué est signalé sous le champ ; il peut être remplacé
sans recommencer. Le serveur vérifie l’unicité même en cas de demandes simultanées.
Une erreur de connexion n’est pas annoncée comme un identifiant occupé. Aucun
compte partiel ni notification de succès n’est créé. La confirmation de création
permet ensuite de s’identifier ; elle ne constitue pas automatiquement une arrivée.

La borne partagée efface les données non enregistrées et les autorisations
temporaires après annulation, abandon ou expiration. Ne pas enregistrer ces
informations dans un gestionnaire de formulaires sur un poste public.

## Familles et langue

Chaque personne conserve son compte et son historique. Les responsables autorisés
peuvent réserver pour les personnes rattachées selon l’âge et les règles configurées.
Une personne participante consomme une place ; un groupe n’est pas artificiellement
divisé pour contourner la capacité. [Règles familiales](families-2.8.md).

Réglages → Borne : choisir langue principale, langues proposées et « Permettre aux
usagers de changer de langue ». Le choix public est indépendant de l’administration.
Si le sélecteur est désactivé, la borne revient à la langue principale. L’inactivité
réinitialise le parcours ; les délais propres à l’inscription restent prioritaires.
Les catalogues locaux traduisent les textes standards, pas les titres personnalisés,
noms de ressources, descriptions ou modèles d’e-mails de l’équipe.

## Calendrier et animations

Semaine et Mois conservent événements métier et notes internes par occurrence.
Administrateurs et modérateurs autorisés peuvent ajouter, modifier ou effacer une
note en vidant son texte. Elle n’est transmise ni à WordPress ni à Discord.

Les horaires habituels des OpenLab restent distincts de leur publication.
« Horaires exceptionnels » gère fermeture complète, ouverture supplémentaire ou
changement ponctuel. Une fermeture retire l’OpenLab habituel du calendrier public,
sans supprimer les passages. « Afficher entretiens et rappels » ne change que la vue.

Une animation peut avoir des créneaux et une capacité. Les six indicateurs
distinguent confirmations, attentes et places disponibles. Une proposition temporaire
peut réserver des places sans encore ajouter de participants confirmés : son échéance
explique cette différence. Le serveur reste l’autorité lors de demandes simultanées.

Plafonds d’attente, propositions, acceptations, expirations et annulations conservent
leurs règles. Une inscription confirmée n’est pas une présence constatée : Présent,
Absent et À confirmer sont distincts. Les corrections manuelles sont prioritaires
sur la présence automatique des seuls inscrits confirmés effectivement identifiés
pendant leur séance. Les participants non inscrits/anonymes restent distincts.

Les animations autorisées peuvent être annoncées avant l’ouverture des inscriptions.
Le catalogue les conserve 24 heures après leur fin, sans nouvelle réservation passée.
Le mois d’historique WordPress est une projection différente, avec ses
[restrictions de publication](wordpress.md). L’export ICS ne publie pas de participants.

## Rappels et calendriers personnels

Le rappel e-mail d’animation est facultatif, configurable, initialement à48 heures,
et réservé aux confirmations réelles. Le créneau et le groupe familial font référence.
Attente, proposition non acceptée, annulation et échéance passée ne deviennent pas
des rappels de confirmation. La mise à jour n’active pas de rattrapage rétroactif.

Après confirmation, les options de calendrier personnel proposent un fichier ICS
et un lien Google. Aucun accès au compte Google n’est demandé ; importer un ICS
ne promet pas une synchronisation automatique dans tous les lecteurs. Les fichiers
publics ne contiennent ni personne ni jeton de gestion.

SMTP et Discord sont facultatifs ; une configuration n’est pas une preuve d’envoi.
La temporisation Discord WordPress évite les alertes de microcoupure, avec
rétablissement facultatif et protection des doublons. Les rappels de ressources
sont décrits dans le [guide du suivi](resources-maintenance.md).

## Gestion, bilans et droits

Formations/habilitations, abonnements/crédits, locations et facturation sont
configurables. Les abonnements sont désactivés par défaut, sans paiement bancaire
en ligne. Les devis/factures PDF et DOCX utilisent le préfixe AAAAMMJJ ; leur date
imprimée conserve sa présentation normale.

Statistiques, six CSV, bilan visuel PDF et rapport annuel restent distincts. Les
petits effectifs agrégés du PDF interne sont visibles : examiner le document avant
diffusion extérieure. Les animations futures ne sont pas des présences ; période
réellement couverte et données manquantes doivent rester compréhensibles.

Les modérateurs n’obtiennent pas de droits généraux d’administration en utilisant
calendrier ou suivi. Sauvegardes, réglages sensibles et suppression des ressources
gardent leurs contrôles serveur. [Maintenance de l’installation](maintenance.md).
