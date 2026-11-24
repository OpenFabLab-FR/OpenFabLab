# Ouvrir un espace « Mon compte » dans son FabLab

Ce document décrit la candidate historique 2.17. Pour la stable 2.18,
suivez le [guide WordPress actuel](wordpress.md).

La borne et les réservations habituelles restent utilisables sans espace usager.
L’activation est volontaire. OpenFabLab conserve les comptes et les liens de famille ;
le plugin WordPress transporte les demandes, mais ne crée pas de comptes WordPress.

## Préparer un essai sans toucher aux inscriptions

1. Utiliser un WordPress HTTPS de test et une **autre installation OpenFabLab**,
   avec un volume, une base fictive, des clés et des sauvegardes propres. Ne
   jamais connecter cette paire au relais de production. Intercepter les e-mails
   dans une boîte locale de démonstration et désactiver les envois Discord.
2. Tester d’abord la transition et le retour arrière de l’agent sur un moteur
   Docker isolé, avec des données fictives. Une VM est une possibilité, pas un
   prérequis de l’application. Un test de processus seul ne valide pas le
   remplacement des conteneurs. L’agent 1.1.0 de
   la version de référence refuse « 2.17 » avant extraction. Ne pas renommer le ZIP,
   réinstaller le kit d’activation initiale ou contourner un refus.
3. Une fois l’agent adapté et vérifié : importer **l’application** dans les mises
   à jour, vérifier la source 2.16.1/28, la cible 2.17/29 et l’empreinte ; préparer,
   puis confirmer. Attendre le résultat final de l’agent et contrôler les sauvegardes
   PRE et POST. Restaurer un ensemble cohérent application/base/fichiers : ne jamais
   faire relire une base 29 par la version 2.16.1.
4. Vérifier les trois shortcodes historiques avec l’ancien plugin, puis remplacer
   le plugin **sur la copie de test** par le ZIP Reservations 2.16. L’OTA applicative
   ne le remplace pas. Laisser les réglages de réservations existants en place.

## Relier la page

Dans Gutenberg, insérer un bloc **Code court** sur une page « Mon compte ».
Utiliser **un seul** environnement par page :

    [openfablab_account environment="test"]

Pour l’activation ultérieure sur le site principal, remplacer « test » par
« production ». Le mode du shortcode n’isole pas SQLite. Pour le portail d’une
instance de test dédiée, définir OPENFABLAB_ONLINE_ENVIRONMENT=test sur son hôte
et sélectionner le même environnement dans les réglages. Aucune modification de
port, aucun accès Docker pour WordPress, aucun partage de la base avec WordPress.

Configurer le relais HTTPS sortant existant, le SMTP et le module Usagers. Dans
**Réglages → Usagers et permissions → Comptes en ligne**, renseigner l’adresse HTTPS
exacte de la page, sur le même WordPress que le relais. Activer l’espace et, si
souhaité, la création de comptes. Définir une notice de confidentialité sur
WordPress. Exclure la page et les routes privées du cache de page/CDN. Ne pas
faire publier une page par simple activation du plugin.

Pour préparer le menu, garder la page en brouillon et noter son emplacement :
« MON COMPTE » à côté de « RÉSERVATION ». N’ajouter le lien au menu affiché
qu’après validation. Sur un site neuf, enregistrer la page publiée avec le plugin
actif pour que le formulaire de réservation retrouve son adresse.

Chaque bloc de réservation utilise le lien de son propre environnement,
également lorsque plusieurs blocs sont présents sur une page. Le visiteur
retrouve l’animation sélectionnée. Les trois actions publiques de Mon compte
et le sélecteur de langue fonctionnent aussi sur une page sans autre shortcode.

## Choisir qui approuve

- **Manuel** : le visiteur vérifie son e-mail ; l’équipe examine la demande.
- **Automatique** : un nouvel adulte éligible sans doublon peut être activé.
  Un cas ambigu n’accorde aucun droit ; la personne est invitée à contacter l’équipe.
- **Conditionnel** : le même cas simple est activé ; une situation ambiguë est
  soumise à l’équipe. Une ancienne fiche n’est jamais revendiquée automatiquement
  par la seule connaissance d’une adresse partagée.

Les demandes à examiner sont accessibles par le lien du **Répertoire des usagers**
et le **Résumé**. Vérifier les rapprochements proposés et l’autorité du responsable
par un canal indépendant avant d’accepter un rattachement à une fiche existante.
Refuser ou révoquer un accès Internet ne supprime pas la fiche ni les présences.
Le compteur de l’en-tête se règle dans **Accueil et borne → Apparence et
affichage → Interface administrative**. Le masquer ne modifie pas le Résumé.
Les modérateurs ne peuvent pas approuver une demande à la place de l’administrateur.

## Parcours de l’usager

Pour créer un compte, renseigner les champs, prendre connaissance de la notice
et ouvrir le lien de confirmation dans le navigateur utilisé. Le lien ne réalise
aucune action avant confirmation. Le numéro à quatre chiffres est communiqué
privément ; il reste un identifiant de borne et non un mot de passe Internet.
Pour se connecter ou récupérer cet identifiant, demander un nouveau lien.
Sans contact vérifiable, demander de l’aide à l’équipe.

Depuis **Ma famille**, ajouter un enfant sans lui imposer sa propre adresse e-mail.
Chaque enfant conserve sa fiche individuelle. Une fiche existante doit être
rapprochée après vérification. Reprendre ensuite la réservation : sélectionner
l’adulte et l’enfant si un accompagnement est requis. Une place par participant ;
aucune place n’est bloquée pendant la création d’un compte. La confirmation
revérifie les âges, la capacité, les autorisations et la liste d’attente pour le
groupe entier. **Mes réservations** distingue les inscriptions à venir et passées.
Le responsable de la demande peut répondre à une proposition ou annuler le groupe.
Le réglage existant des animations avec/sans compte reste indépendant.

## Messages, données temporaires et incidents

Les e-mails de l’espace utilisent le SMTP du FabLab. Dans **Communication →
E-mails SMTP → Modèles d’e-mails automatiques**, choisir un modèle du groupe
**Comptes et familles** pour modifier son objet, son contenu et sa signature.
L’aperçu n’envoie aucun message et ne génère aucun lien réel. Le lien sécurisé
est ajouté automatiquement s’il manque dans le texte. Les personnalisations
de réservation restent indépendantes et ne sont pas remplacées.

Les quatre avis Discord sont facultatifs et se règlent dans **Communication →
Événements notifiés → Comptes et familles**. Garder des libellés génériques :
aucune donnée d’usager n’est ajoutée automatiquement. Une panne SMTP n’active
pas le compte ; contrôler l’expéditeur, le relais et la page des demandes,
puis demander un nouveau lien si nécessaire.

Le lien est à usage unique, lié au navigateur d’origine, valable 15 minutes par
défaut (réglable de 5 à 30). La session dure 20 minutes par défaut (5 à 60).
Après 10 minutes, une opération sensible peut exiger une nouvelle identification.
Une demande non vérifiée expire en un jour, une demande à examiner en trente.
Les messages non distribués sont temporaires ; les traces techniques de décisions
sont conservées au maximum 90 jours lorsque l’entretien du relais fonctionne.
Les sauvegardes complètes restent privées : une copie neutralisée pour test
n’est pas une base anonymisée. L’âge métier d’autonomie et l’âge minimal d’une
animation ne définissent pas des règles juridiques générales. Chaque structure
choisit les informations à fournir aux familles avec son référent à la protection
des données.
