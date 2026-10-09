# OpenFabLab Reservations 2.8.2 — version stable

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

Le plugin 2.8.2 utilise le **protocole 4, révision 3**, avec OpenFabLab 2.8.2 / SQLite 17 ou OpenFabLab 2.8.3 et 2.8.4 / SQLite 18. **OpenFabLab initie les échanges HTTPS vers WordPress**, pas l'inverse. Il reste l'autorité pour animations, comptes liés, participants, capacité et liste d'attente. WordPress affiche un catalogue public et conserve temporairement des demandes/actions chiffrées. Il ne décide jamais des places. La borne réserve directement sans WordPress.

Une personne sélectionnée = une place ; un responsable rattaché éligible doit participer avec un membre non autonome. Un adulte et deux enfants demandent trois places. S'il en reste deux, le groupe entier attend. E-mail valide obligatoire, téléphone selon le réglage de structure. SMTP, propositions, réponses et expirations sont gérés par OpenFabLab. Voir [familles](families-2.8.md).

## Préparer le raccordement

Sauvegarder WordPress et OpenFabLab avant toute intervention ; essayer d'abord sur une installation séparée. Le ZIP `openfablab-reservations-2.8.2.zip` de la [release stable 2.8.2](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.8.2) est installable par les extensions WordPress. PHP 8.1+, OpenSSL AES-GCM, InnoDB, HTTPS, REST et JavaScript sont nécessaires. Aucun secret n'est fourni. Utiliser ce plugin avec OpenFabLab 2.8.2, 2.8.3 ou 2.8.4 et lire [les instructions de mise à jour](upgrade.md).

Conserver le secret partagé existant dans le plugin et dans les fichiers privés OpenFabLab. Dans OpenFabLab, renseigner l'URL HTTPS du **site WordPress**, puis vérifier la liaison dans Normal et Test. Aucun champ d'adresse du moteur n'est utilisé. Une option d'une ancienne installation peut rester comme donnée inactive, mais aucune requête ne l'utilise. **Ne pas ouvrir de port NAS ni modifier le réseau pour ce flux.**

Les deux versions doivent négocier `outbound_actions_v1`. La version stable annonce aussi `transport_only_v1` et `relay_revision: 3` ; sa révision de stockage est `2.8.2-relay3`. Un plugin 2.8.0/2.7 ne traite pas les nouvelles actions ; aucune reprise de son ancien moteur de capacité. Une installation neuve reste neutre, modules à activer par l'équipe.

## Pages publiques

- Normal : `[openfablab_reservations environment="production"]`.
- Test : `[openfablab_reservations environment="test"]`.

Le nom de la page n'indique pas l'environnement. Une page appelée « Test » avec un shortcode production reste Normal. Aucun contenu réel n'est corrigé automatiquement.

Catalogue toutes les 90 secondes par défaut, demandes toutes les 15 secondes (réglage OpenFabLab entier 10–60). Le visiteur voit une demande reçue puis la décision réelle ; un rechargement reprend le suivi de sa session. Une panne réseau retarde la réponse. Un catalogue de plus de 15 minutes bloque les nouvelles demandes. Capacité indiquée provisoire, toujours recontrôlée transactionnellement par OpenFabLab.

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
