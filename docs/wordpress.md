# Reservations 2.13.0 et OpenFabLab 2.13.0

Le plugin facultatif est réellement modifié : visibilité avant ouverture,
mention « Inscriptions à venir » avec horaire, cartes « Animation terminée »
conservées 24 heures et classées après les animations à venir. Les délais sont
appliqués côté serveur à chaque lecture, y compris sur un catalogue en cache.
L’attribution des places reste exclusivement dans OpenFabLab.

Capacité optionnelle : `publication_visibility_v1`. Protocole **4/révision 3**,
HTTPS signé, environnements Normal/Test, secrets et parcours familiaux conservés.
Le numéro du plugin est indépendant de celui du protocole. Aucune reconfiguration
ni désinstallation requise pour mettre à jour les fichiers du plugin.

L’ancien plugin 2.11.0 conserve ses échanges mais n’affiche pas les animations
terminées selon les nouvelles règles. Le nouveau plugin accepte aussi les anciens
catalogues explicitement dépourvus des nouveaux champs. Sans WordPress,
le catalogue de la borne utilise les mêmes règles de publication de l’application.

[Plugin installable 2.13.0](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.13.0/openfablab-reservations-2.13.0.zip) ·
[Release et SHA256SUMS](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.13.0).
La mise à jour de l'application n'installe pas le plugin : remplacer séparément
l'extension sur WordPress, puis vérifier sa version et les échanges Normal/Test.

---

# Application OpenFabLab 2.12.0 et Reservations 2.11.0

Le plugin facultatif **2.11.0 reste intégralement inchangé** : aucun nouveau ZIP
ni remplacement WordPress n'est nécessaire pour l'application 2.12.0. Protocole
4/révision 3, capacités, ressources et signatures restent compatibles. Ne pas
imposer d'égalité stricte des versions pour synchroniser. Une future modification
réelle du plugin disposera de son propre incrément et de ses métadonnées cohérentes.
Préserver configuration et secrets. OpenFabLab fonctionne sans WordPress.
Conserver le [téléchargement officiel existant du plugin 2.11.0](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.11.0/openfablab-reservations-2.11.0.zip)
et ses [empreintes](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.11.0/SHA256SUMS).
Il n'est ni reconstruit ni republié dans la release applicative 2.12.0.
Les références stables précédentes sont conservées ci-dessous.

---

# OpenFabLab Reservations 2.11.0 — plugin facultatif stable

Application et plugin facultatif Reservations 2.11.0, protocole 4/révision 3
inchangé. La modification du numéro public n’impose aucune égalité stricte des
versions pour synchroniser. Les présences aux animations restent internes au
moteur OpenFabLab : elles ne créent pas de réservation ni d’e-mail WordPress.
[Guide](evolution-2.11.0.md) ·
[Plugin installable 2.11.0](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.11.0/openfablab-reservations-2.11.0.zip) ·
[SHA256SUMS](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.11.0/SHA256SUMS).
OpenFabLab fonctionne entièrement sans WordPress. Mettre à jour l’application
d’abord, puis remplacer le plugin sans désinstallation ni changement des secrets.
Le moteur, les capacités et les ressources du relais sont conservés depuis 2.10.1.
Les mentions de préparation du ZIP figé sont historiques ; ce guide fait référence.

---

## Référence historique : OpenFabLab Reservations 2.10.1

Application **OpenFabLab 2.10.1**, plugin **Reservations 2.10.1**. OpenFabLab
fonctionne entièrement sans WordPress. [Télécharger le plugin installable](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.10.1/openfablab-reservations-2.10.1.zip)
et vérifier les [empreintes officielles](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.10.1/SHA256SUMS).
Le ZIP approuvé reste inchangé ; ses mentions de préparation sont historiques.

Le plugin 2.10.1 apporte les libellés de créneaux, les compteurs et le
récapitulatif explicite. Application et plugin ont désormais le même numéro
public, sans contrôle d’égalité imposé au relais. Protocole 4/révision 3 et
`waitlist_limits_v1` inchangés. Mettre à jour l’application avant le plugin,
en conservant les paramètres et sans désinstaller l’extension.
Le plugin 2.9.0 reste utilisable pendant la transition avec son ancien affichage.
Le plugin 2.10.1 accepte le catalogue de l’application 2.10.0.
Voir le [guide de cette correction](corrections-2.10.1.md).

## Référence historique : Reservations 2.9.0

## Avec la stable antérieure OpenFabLab 2.10.0

Plugin compatible facultatif : **OpenFabLab Reservations 2.9.0**, strictement
inchangé par rapport à la release 2.9.0. Aucun nouveau plugin 2.10.0, aucune
réinstallation nécessaire. [Télécharger le ZIP 2.9.0](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.10.0/openfablab-reservations-2.9.0.zip)
et vérifier les [empreintes](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.10.0/SHA256SUMS).

Protocole **4/révision 3**, `waitlist_limits_v1` et réservations, familles,
annulations, listes d’attente et chiffrement conservés. OpenFabLab seul attribue
les places ; WordPress met les demandes en file, sans devenir un moteur métier.
Communication HTTPS **sortante depuis OpenFabLab**, aucun port entrant à ouvrir
sur son serveur. Les cadences et secrets existants ne changent pas.
OpenFabLab reste utilisable sans WordPress. Les notes internes et les données
d’abonnement ne sont pas publiées dans le catalogue. Voir [architecture](architecture.md).


## Référence historique : OpenFabLab 2.9.0

Avec OpenFabLab 2.9.0 / SQLite 20, le plugin annonce `waitlist_limits_v1` pour les
compteurs et états d’attente reçus du moteur. Les cartes gardent les informations
de disponibilité sous les horaires et le bouton au pied. Protocole 4 / révision 3,
stockage du relais, secret et protections inchangés. Aucun accès entrant au NAS.
Voir [guide 2.9.0](evolution-2.9.0.md). Réinstaller par remplacement du ZIP 2.9.0,
sans désinstallation, après sauvegarde WordPress. Le plugin 2.8.5 reste compatible
avec ses anciens affichages ; il ne présente pas les nouveaux états.

Application stable **2.9.0**, plugin **2.9.0** : télécharger le
[ZIP officiel installable](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.9.0/openfablab-reservations-2.9.0.zip)
et vérifier les [empreintes](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.9.0/SHA256SUMS).
Le plugin est inchangé depuis la candidate validée ; aucune reconstruction ni
réinstallation s’il est déjà en 2.9.0. OpenFabLab fonctionne sans WordPress.
Les guides embarqués des ZIP sont figés avec les archives approuvées ; ce guide
du tag `v2.9.0` constitue la référence stable.

## Référence historique de la stable publique 2.8.6

## Avec OpenFabLab 2.8.6

Application stable : **OpenFabLab 2.8.6 / SQLite 19**. Plugin compatible :
**Reservations 2.8.5**, publié sans reconstruction comme asset facultatif de la
[release 2.8.6](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.8.6).
OpenFabLab reste totalement utilisable sans WordPress.

Le plugin **2.8.5** apporte les détails de la réservation personnelle, l'annulation en deux étapes, l'attente jusqu'au résultat moteur et le lien d'information facultatif du catalogue. Il conserve les tables, le secret, le protocole **4 / révision 3** et toutes les protections du relais. Aucun moteur WordPress de places n'est ajouté. La capacité facultative `animation_information_v1` est annoncée dans la réponse signée : OpenFabLab n'envoie ce champ qu'au plugin qui l'annonce. Le plugin 2.8.5 accepte aussi le catalogue de l'application 2.8.4 ; le plugin antérieur 2.8.2 reste compatible avec les fonctions antérieures, sans les nouveaux détails d'interface.

La compatibilité est négociée, pas déduite d'une version silencieusement modifiée.
Télécharger le [ZIP officiel 2.8.5](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.8.6/openfablab-reservations-2.8.5.zip).
S'il est déjà installé, aucune mise à jour du plugin n'est nécessaire pour la
2.8.6. Sinon : sauvegarder WordPress, importer le ZIP par Extensions → Ajouter →
Téléverser, remplacer la version existante **sans désinstallation**, garder
réglages/tables/secret et vérifier Normal/Test. Aucune régénération de secret.
Les mentions de préparation du README embarqué restent conservées pour maintenir
l'empreinte approuvée ; ce guide du tag stable est la référence à jour.

Nouveaux défauts OpenFabLab : 10 s pour les demandes et 60 s pour le catalogue uniquement sans configuration existante. Les valeurs enregistrées 15/90 ou personnalisées restent intactes. Le plugin ne choisit pas la cadence du moteur. Aucun accès entrant au NAS, aucun port public supplémentaire. Les e-mails et leurs modèles restent entièrement natifs OpenFabLab.

## Plugin publié 2.8.2 — référence stable antérieure

L'application stable **2.8.4 / schéma 18** conserve exactement le plugin **2.8.2** et le protocole **4 / révision 3**. Aucune mise à jour du plugin ni rotation du secret n'est nécessaire ; catalogue et relève sortante restent indépendants (90 s et 15 s par défaut). Pour une nouvelle installation, utiliser le [ZIP officiel 2.8.2](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.8.2/openfablab-reservations-2.8.2.zip), sans attendre de plugin nommé 2.8.4.

Les applications **2.8.3 et 2.8.4 / schéma 18** utilisent ce même plugin **2.8.2 inchangé**, au protocole **4 / révision 3**. Aucun changement du parcours public ni réinstallation du plugin n'est nécessaire ; les options d'identifiant concernent l'inscription locale des comptes, pas la vérification de coordonnée WordPress. Voir [le guide 2.8.3](usability-2.8.3.md) et [les corrections 2.8.4](corrections-2.8.4.md).

La version 2.8.2 ajoute le choix avec/sans compte selon la règle OpenFabLab,
le scanner QR local avec saisie manuelle et vérification de coordonnée.
Compatibilité historique application/plugin **2.8.2**, protocole **4 / révision 3**, schéma **17** :
[parcours, compatibilité et mise à jour](reservations-2.8.2.md).
Aucune URL publique du NAS, port entrant ou deuxième moteur de réservation.
La révision 2 n’est pas compatible avec le catalogue révision 3 : mettre à jour
l'application et le plugin ensemble. Le parcours sans compte réserve pour une
personne autonome avec coordonnées et date de naissance, sans créer de fiche usager.

## Plugin facultatif, moteur commun

Le couple actuel **OpenFabLab 2.9.0 / Reservations 2.9.0** utilise le **protocole 4, révision 3**, avec SQLite 20. **OpenFabLab initie les échanges HTTPS vers WordPress**, pas l'inverse. Il reste l'autorité pour animations, comptes liés, participants, capacité et liste d'attente. WordPress affiche un catalogue public et conserve temporairement des demandes/actions chiffrées. Il ne décide jamais des places. La borne réserve directement sans WordPress. Les compatibilités historiques des plugins 2.8.5 et 2.8.2 sont décrites plus haut.

Une personne sélectionnée = une place ; un responsable rattaché éligible doit participer avec un membre non autonome. Un adulte et deux enfants demandent trois places. S'il en reste deux, le groupe entier attend. E-mail valide obligatoire, téléphone selon le réglage de structure. SMTP, propositions, réponses et expirations sont gérés par OpenFabLab. Voir [familles](families-2.8.md).

## Préparer le raccordement

Sauvegarder WordPress et OpenFabLab avant toute intervention ; essayer d'abord sur une installation séparée. Le ZIP `openfablab-reservations-2.9.0.zip` de la [release stable 2.9.0](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.9.0) est installable par les extensions WordPress. PHP 8.1+, OpenSSL AES-GCM, InnoDB, HTTPS, REST et JavaScript sont nécessaires. Aucun secret n'est fourni. Lire [les instructions de mise à jour](upgrade.md).

Conserver le secret partagé existant dans le plugin et dans les fichiers privés OpenFabLab. Dans OpenFabLab, renseigner l'URL HTTPS du **site WordPress**, puis vérifier la liaison dans Normal et Test. Aucun champ d'adresse du moteur n'est utilisé. Une option d'une ancienne installation peut rester comme donnée inactive, mais aucune requête ne l'utilise. **Ne pas ouvrir de port NAS ni modifier le réseau pour ce flux.**

Les deux versions doivent négocier `outbound_actions_v1`. La version stable annonce aussi `transport_only_v1` et `relay_revision: 3` ; sa révision de stockage est `2.8.2-relay3`. Un plugin 2.8.0/2.7 ne traite pas les nouvelles actions ; aucune reprise de son ancien moteur de capacité. Une installation neuve reste neutre, modules à activer par l'équipe.

## Pages publiques

- Normal : `[openfablab_reservations environment="production"]`.
- Test : `[openfablab_reservations environment="test"]`.

Le nom de la page n'indique pas l'environnement. Une page appelée « Test » avec un shortcode production reste Normal. Aucun contenu réel n'est corrigé automatiquement.

Sans configuration existante, catalogue toutes les 60 secondes et demandes toutes les 10 secondes (réglage OpenFabLab entier 10–60). Les valeurs enregistrées, notamment 90/15 secondes, sont conservées. Le visiteur voit une demande reçue puis la décision réelle ; un rechargement reprend le suivi de sa session. Une panne réseau retarde la réponse. Un catalogue de plus de 15 minutes bloque les nouvelles demandes. Capacité toujours recontrôlée transactionnellement par OpenFabLab.

Le navigateur n'accède qu'au même site WordPress. Après identification validée par OpenFabLab, il reçoit des choix opaques temporaires liés au compte, jamais un annuaire public. Les familles ne sont pas énumérables par un endpoint public. Une modification publique des participants n'est pas ajoutée : l'administration conserve ses droits et contrôles.

## Liens d'e-mail et caches

Le mode WordPress/automatique ramène les liens d'annulation et de proposition à la page dédiée du site. Jeton signé privé dans le fragment, retiré de l'adresse par le navigateur ; aucune donnée privée dans les journaux HTTP. GET de scanner sans mutation. Une case explicite et un POST protégé déposent l'action, ensuite appliquée par OpenFabLab. Une proposition est expirée selon l'heure de traitement du moteur, même si l'utilisateur a cliqué avant une coupure. Les anciens liens OpenFabLab restent compatibles.

Exclure les routes REST OpenFabLab, pages de réservation et `?openfablab_action=1` de tout cache HTML/CDN. La page dédiée n'appelle ni analytics ni thème, utilise no-store/noindex/no-referrer et une politique de contenu restrictive. Ne pas désactiver TLS ni le contrôle de session pour contourner un cache.

## Diagnostic et sauvegardes

Le panneau distingue catalogue reçu, dernière relève et dernier résultat pour Normal/Test. Les compteurs techniques ne sont pas des confirmations de capacité. Un contact signé en 2.8.0 ne prouve pas que le parcours public était raccordé ; la 2.8.1 vérifie explicitement le protocole sortant et le catalogue.

La sauvegarde WordPress inclut les trois tables techniques (catalogue, actions/résultats et nonces), options et secret ; la sauvegarde complète OpenFabLab inclut base et fichiers privés. Rotation du secret/sel pendant des actions en vol à éviter. Voir [conservation, sécurité et limites détaillées](outbound-2.8.1.md) et [migration/retour](upgrade.md).

## Administration et retrait de l'ancien moteur

Normal est prioritaire : badge de connexion, réception du catalogue, relève et résultat, compteurs de la file. Test et le diagnostic avancé sont repliables. « En attente du premier échange » est normal avant le raccordement du moteur. Les nombres affichés proviennent du catalogue reçu et du transport, jamais d'un calcul de capacité WordPress.

Le secret est présenté uniquement comme configuré ou manquant. Sa régénération est secondaire, protégée par droits administrateur, HTTPS, POST, nonce et confirmation. Elle est refusée pendant une demande ou un résultat encore utilisable. Le fichier téléchargé doit rester privé ; mettre la même clé dans OpenFabLab avant de reprendre les échanges. Ne jamais régénérer pour corriger l'absence du premier catalogue.

Les classes de réservation/capacité, annuaire, e-mails WordPress, anciens endpoints, cron métier et outils de nettoyage de l'ancien moteur ont été retirés du plugin. L'installation ne crée que les trois tables techniques. Les cinq anciennes tables métier ne sont supprimées que si toutes sont vides, sous verrou ; si des données subsistent, les tables restent intactes et inutilisées. La base et l'historique OpenFabLab ne sont jamais concernés.

La désinstallation conserve par défaut les données. L'option volontaire de suppression concerne uniquement le stockage du plugin : sauvegarder avant de l'activer.
# Compatibilité de la version 2.8.6

OpenFabLab 2.8.6 utilise **OpenFabLab Reservations 2.8.5 inchangé**, protocole 4,
révision 3. Le ZIP 2.8.5 approuvé est publié tel quel, sans plugin nommé 2.8.6.
Le relais continue d’être initié exclusivement par OpenFabLab en HTTPS ; aucun
accès entrant au NAS n’est nécessaire. Les cadences déjà enregistrées sont
conservées. Les réglages Discord restent privés à OpenFabLab et ne sont pas
publiés dans le catalogue WordPress. La réservation, ses places et sa décision
transactionnelle restent sous l’autorité unique du moteur OpenFabLab.
