# Mettre à jour OpenFabLab

## Vers la stable 2.10.1 depuis 2.10.0

Utiliser les [ZIP officiels et SHA256SUMS](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.10.1).
Vérifier leurs empreintes avant toute intervention. Conserver les configurations,
volumes, données et personnalisations existants ; ne pas remplacer `.env` ou les secrets.

SQLite reste en schéma **21** : ne pas rejouer la migration 20 → 21.
Sauvegarder le runtime, les volumes, paramètres et données en PRE21, arrêter
proprement, puis remplacer uniquement les fichiers applicatifs. Contrôler la
version, l’intégrité SQLite, les volumes, préférences et la santé HTTP avant
réouverture. Conserver une POST21 et l’image précédente. Après toute tentative
publique, ne jamais restaurer automatiquement une ancienne base.

Mettre à jour l’application d’abord, puis le plugin facultatif Reservations
2.10.1 par remplacement du ZIP dans WordPress, sans désinstallation ni changement
de secret. Les combinaisons transitoires avec le plugin 2.9.0 et l’application
2.10.0 utilisent toujours le protocole 4/révision 3. [Détails](corrections-2.10.1.md).

Depuis **2.9.0 / schéma 20**, la distribution complète 2.10.1 conserve le parcours
additif 20 → 21 décrit ci-dessous : PRE20 complète, validation isolée, arrêt
propre, contrôle après migration et POST21. Utiliser le runtime 2.10.1 pour la
version cible. Ne jamais rouvrir une base 21 avec le runtime 2.9.0.


## Référence historique : vers la stable 2.10.0, schéma 20 → 21

Utiliser la [release 2.10.0](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.10.0)
et vérifier `SHA256SUMS`. Elle contient tous les développements et les finitions
de la corrective 1. Ne pas confondre version applicative et étiquette d’image.

Depuis **2.9.0 / SQLite 20** : vérifier version, intégrité et clés étrangères,
faire une sauvegarde complète **PRE20** avec runtime/image et configuration,
puis préparer et tester le nouveau runtime sur une copie isolée, sans services
externes. Arrêter proprement l’instance et compléter par une copie froide des
dernières écritures. Installer les seuls fichiers applicatifs, sans remplacer
Compose, `.env`, volumes, branding, PIN, secrets ni fichiers privés.

L’initialisation 2.10.0 effectue la migration additive transactionnelle **20 → 21**
(droits/crédits, notes par occurrence, incidents de synchronisation et reçus de
pointage). Les données métier et les préférences existantes restent conservées.
Le module Abonnements reste désactivé tant que la structure ne l’active pas.
Les défauts sonores sont activé/50 % pour les clés absentes ; toute valeur déjà
enregistrée reste inchangée, y compris une désactivation.

Avant réouverture : contrôler HTTP/santé, version **2.10.0**, schéma **21**,
`integrity_check`, `foreign_key_check`, utilisateurs/familles, réservations,
factures, préférences, montages et fichiers privés. Vérifier le catalogue et la
relève des demandes Normal/Test si WordPress est utilisé, sans réservation
fictive automatique. Conserver une sauvegarde complète **POST21**.

**Déjà en 2.10.0 / schéma 21** : ne pas rejouer la migration 20 → 21. Identifier
le runtime exact, conserver PRE21 et l’image précédente, remplacer seulement
le runtime corrigé puis vérifier schéma et données inchangés ; conserver POST21.

Le plugin facultatif **Reservations 2.9.0 est inchangé** : aucune réinstallation
nécessaire. Protocole 4/révision 3 et cadences enregistrées conservés. Le plugin
2.8.5 conserve sa compatibilité historique sans les nouveaux affichages d’attente.

Un retour contrôlé à 2.9.0 exige sa PRE20 et son runtime cohérents, uniquement
avant toute première tentative de démarrage public et après décision humaine.
**Ne jamais lancer 2.9.0 sur une base 21.** Après une tentative publique ou de
nouvelles écritures potentielles : préserver l’état, diagnostiquer et décider,
sans restauration destructive automatique. Les scripts privés d’une installation
particulière ne sont pas distribués. Voir [guide 2.10.0](evolution-2.10.0.md).

## Vers la stable 2.9.0 : schéma 19 → 20

Télécharger l’archive complète de la [release 2.9.0](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.9.0)
et vérifier `SHA256SUMS`. Depuis **2.8.6 / schéma 19** : sauvegarde complète
PRE19 et runtime/image 2.8.6 requis,
construction et essai isolé avant arrêt, puis copie froide des dernières écritures.
Migration additive transactionnelle ; aucune donnée supprimée. Contrôler SQLite
intégrité/FK, version2.9.0/schéma20, réglages, volumes et fichiers privés avant
ouverture ; conserver une POST20. Voir [le guide](evolution-2.9.0.md).

Le plugin facultatif 2.9.0 s’installe par remplacement du ZIP après sauvegarde,
**sans désinstallation** : secret, options et file des demandes conservés. Il
accepte le catalogue antérieur. Le moteur peut continuer avec le plugin2.8.5,
sans les nouveaux états visuels ni compteurs `waitlist_limits_v1`. Protocole
4/révision 3 conservé, tout comme les cadences enregistrées (notamment 90s/15s).
Aucune réinstallation n’est nécessaire si le plugin est déjà en 2.9.0.

**Déjà en 2.9.0 / schéma 20** : aucune nouvelle migration 19 → 20. Conserver une
sauvegarde complète **PRE20**, puis une copie froide des dernières écritures et
le runtime 2.9.0 réellement utilisé. Remplacer uniquement le runtime, sans
écraser Compose, configuration, secrets ni volumes. Contrôler version, schéma 20,
intégrité/clés étrangères, données, réglages et santé, puis conserver une POST20.
Ne pas utiliser une procédure de migration depuis 2.8.6 dans ce parcours.
Le secours éventuel doit rester compatible schéma 20 ; aucune restauration PRE19.

Avant toute reprise publique seulement, un secours contrôlé peut restaurer
PRE19/runtime2.8.6 complet après preuve d’absence d’écritures. Après une première
tentative publique, préserver l’état20 et décider humainement d’une reprise
compatible ; jamais de restauration destructrice automatique. Ne jamais lancer
2.8.6 sur une base20. Le paquet NAS spécifique reste privé.

## Référence historique : vers la stable 2.8.6

Télécharger l'archive complète depuis la [release 2.8.6](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.8.6)
et vérifier `SHA256SUMS`. Aucune installation intermédiaire 2.8.5 n'est nécessaire.

- **Depuis la stable publique 2.8.4 / schéma 18** : sauvegarde complète PRE18 et
  runtime 2.8.4 ; migration additive et transactionnelle vers **19**, décrite
  ci-dessous. Destination réelle : **2.8.6**, incluant tous les apports 2.8.5.
- **Depuis une installation locale 2.8.5 / schéma 19** : sauvegarde PRE19 et runtime
  2.8.5 ; aucun changement de schéma. Seuls les nouveaux réglages Discord manquants
  sont initialisés, sans écraser les préférences. Voir la section 2.8.5 → 2.8.6.

Préserver données, familles, réservations, factures, historiques, secrets/PIN,
fichiers privés, branding, Compose et volumes. Préparer/tester le runtime avant
arrêt, sauvegarder à froid les dernières écritures, vérifier l'intégrité et les
clés étrangères, puis contrôler **2.8.6 / schéma 19**, les données et le relais
Normal/Test. Les cadences enregistrées restent inchangées.

Le plugin **Reservations 2.8.5** est distribué avec cette release, sans changement
pour la 2.8.6. Il reste facultatif et ne nécessite pas de réinstallation s'il est
déjà en 2.8.5. Depuis 2.8.2 : sauvegarder WordPress puis remplacer le ZIP **sans
désinstallation**, conserver ses tables/options/secret et vérifier les échanges.

Conserver une POST19 cohérente. Un retour à PRE18 exige son runtime 2.8.4 et n'est
envisageable qu'avant toute première tentative publique ; ne jamais lancer
2.8.4 sur une base 19. Depuis 2.8.5, le secours est PRE19/runtime 2.8.5. Après une
tentative publique ou une nouvelle écriture potentielle, préserver l'état actuel
et obtenir une décision humaine : jamais de restauration destructive automatique.
Les ZIP validés ne sont pas reconstruits ; la documentation de ce tag fait référence.

## Étape historique 2.8.4 → 2.8.5 : schéma 18 → 19

La même migration est incluse dans la mise à jour directe 2.8.4 → 2.8.6.


Sauvegarder complètement **PRE18**, y compris SQLite cohérente, fichiers privés, branding, PIN, secrets et configuration ; conserver le runtime/image exacts 2.8.4. Construire la nouvelle image avant interruption, puis arrêter proprement et compléter par une copie froide incluant les dernières écritures. Ne pas copier une SQLite ouverte sans son protocole de sauvegarde.

La migration transactionnelle ajoute seulement `information_url` aux animations et le journal technique Discord. Les anciennes colonnes et lignes métier, réglages et intervalles enregistrés sont conservés. Les modèles d’e-mails sont des réglages optionnels : les modèles par défaut s’appliquent lorsqu’aucune personnalisation n’existe. Vérifier version 2.8.5, schéma 19, intégrité/FK, données, paramètres et volumes avant réouverture ; POST19 après reprise.

Le plugin **2.8.5**, désormais distribué avec la release 2.8.6, améliore la gestion personnelle et reçoit le lien informatif après négociation. Sauvegarder WordPress, puis remplacer le plugin via le ZIP installable sans désinstallation/destruction de ses données. Il peut être mis à jour avant ou après OpenFabLab : il accepte l'ancien catalogue ; l'application ne transmet pas de champ inconnu au plugin 2.8.2. Protocole 4/révision 3, secret et stockage WordPress inchangés.

Avant toute tentative publique, un retour contrôlé exige **PRE18 froide + runtime 2.8.4**. Ne jamais lancer 2.8.4 sur une base 19. Après une tentative publique ou une nouvelle écriture potentielle, aucun rollback automatique destructif : arrêter, sauvegarder l’état 19, diagnostiquer et décider humainement. Un runtime corrigé peut reprendre la base actuelle ; une ancienne PRE ne doit pas l’écraser sans analyse.

Guides : [corrections 2.8.5](corrections-2.8.5.md), [plateformes](platform-compatibility.md), [exploitation commune](installation-common.md). Les lanceurs d’un NAS particulier restent privés et ne sont jamais inclus dans la distribution publique.

## 2.8.3 → 2.8.4 stable, schéma 18 inchangé

Voir [le guide 2.8.4](corrections-2.8.4.md). Vérifier le ZIP officiel avec son `SHA256SUMS`. Conserver le runtime 2.8.3 et une PRE18 complète vérifiée, puis une copie froide après arrêt. Construire le nouveau runtime avant l'interruption. Cette mise à jour n'effectue aucune migration de schéma ni remplacement de configuration ou de secrets ; seules des empreintes temporaires d'inscription utiliseront le registre existant après utilisation.

Vérifier intégrité, clés étrangères, version, schéma 18, données, volumes et paramètres avant/après. Le plugin 2.8.2 et les cadences 15/90 secondes restent inchangés. Après démarrage public, sauvegarder POST18. N'envisager un retour contrôlé PRE18 + runtime 2.8.3 qu'avant toute tentative de démarrage public ; ensuite conserver l'état en échec, arrêter et demander une décision humaine pour ne pas perdre de nouvelles écritures.

L'archive approuvée reste inchangée, y compris ses guides de préparation. La documentation publique du tag `v2.8.4` fait référence. Les outils spécifiques à une infrastructure ne font pas partie de la distribution.

## 2.8.2 → 2.8.3 stable, schéma 17 → 18

La mise à jour ajoute deux champs d'affiliation des usagers et deux réglages ; les tables de réservations restent inchangées. Les données et paramètres existants sont conservés, notamment l'attribution discrète de l'identifiant public. Le plugin WordPress 2.8.2, protocole 4 / révision 3, reste inchangé : aucune réinstallation ni rotation de secret.

1. Conserver le runtime exact 2.8.2 et réaliser une sauvegarde complète **PRE17**, incluant base, fichiers privés, branding, PIN et configurations. Une copie froide après arrêt doit inclure les dernières écritures.
2. Vérifier le ZIP 2.8.3 avec `SHA256SUMS`, construire et contrôler le nouveau runtime isolément avant l'interruption. Migrer une copie de données et comparer les anciennes colonnes et valeurs, intégrité et clés étrangères.
3. Arrêter proprement, sauvegarder à froid, remplacer uniquement le runtime et laisser l'initialisation effectuer la migration additive et transactionnelle. Ne pas forcer le numéro du schéma.
4. Avant remise en service, vérifier 2.8.3 / schéma 18, les données, fichiers et réglages préexistants, volumes, santé et interface. Les échanges WordPress restent exclusivement sortants, 15 s et 90 s par défaut.
5. Après reprise, vérifier Normal/Test, premier catalogue et relève, puis sauvegarder **POST18**. Une restauration PRE17 avec son runtime 2.8.2 n'est automatique que tant qu'aucun démarrage public n'a été tenté. Après toute écriture potentielle, arrêter et sauvegarder l'état, puis décider humainement ; ne jamais ouvrir une base 18 avec 2.8.2.

Voir [les fonctionnalités et le détail du schéma 18](usability-2.8.3.md). Les ZIP approuvés conservent leurs documents embarqués antérieurs à la publication pour maintenir leur empreinte exacte ; les documents de ce tag stable font référence. Les lanceurs propres à une infrastructure restent privés.

## Références des mises à jour antérieures

## 2.8.1 → 2.8.2 stable, schéma 16 → 17

Voir la [procédure 2.8.2](reservations-2.8.2.md) et vérifier les ZIP officiels avec leur `SHA256SUMS`.
Application et plugin 2.8.2 doivent passer ensemble au protocole 4 / révision 3.
PRE 16 complète à froid, image 2.8.1 conservée, page WordPress temporairement
fermée et demandes terminées avant bascule. Nouvelle colonne nullable et réglage
sans compte facultatif par défaut ; aucune donnée métier supprimée.
Retour seulement avec PRE 16 et ancien runtime, avant nouvelles écritures.
Après utilisation, conserver une POST et décider humainement, sans downgrade.
Les sections suivantes restent la documentation des mises à jour antérieures.

## Depuis une installation prépublication déjà en 2.8.2 / schéma17

La distribution finale comprend les badges pastel et le réglage d'affichage des
visiteurs anonymes. Si l'installation est déjà en 2.8.2/schéma17, ne pas refaire
le parcours 16 → 17 : sauvegarder à froid une **PRE17 complète**, conserver l'ID
exact du runtime précédent et remplacer uniquement les fichiers applicatifs.
Compose, volumes, secrets, PIN et configuration existante restent conservés.
Le plugin final 2.8.2/révision3 est inchangé par cette finition : aucune
réinstallation ni rotation du secret si son contenu est déjà celui de la release.

Contrôler version, schéma17, intégrité/FK, réglages, fichiers persistants,
service et relais Normal/Test avant ouverture. Un retour nécessite la PRE17 et
son runtime exact, uniquement avant toute possibilité de nouvelles écritures.
Dès qu'un redémarrage public a pu écrire, conserver l'état et décider humainement
d'une reprise ; jamais de downgrade2.8.1, restaurationPRE16 ou rollback automatique.
Aucun lanceur propre à une infrastructure privée n'est distribué publiquement.

## Depuis une installation prépublication déjà en 2.8.1

La stable 2.8.1 inclut le correctif de suppression d'animation, validé en conditions réelles. Le schéma reste **16** : aucune nouvelle migration ni suppression automatique de données. Seule une suppression administrative explicitement confirmée retire l'animation et ses dépendances terminées ; une inscription active, une attente, une proposition, un dossier incohérent ou facturé reste protégé.

Sauvegarder à froid une **PRE 16 complète**, conserver le runtime/image exact précédent et vérifier les empreintes avant de remplacer uniquement l'application. Ne pas appliquer une procédure exigeant un départ 2.8.0/schéma 15 sur une installation déjà en 16. Le plugin final 2.8.1, protocole 4/révision 2, est inchangé par ce correctif : pas de réinstallation ni de rotation de secret si ce plugin final est déjà installé. Avant réouverture, contrôler données, réglages, intégrité, clés étrangères, volumes et service. Restaurer la PRE 16 avec son runtime correspondant uniquement avant toute possibilité de nouvelles écritures ; après ouverture, préserver l'état et décider humainement d'une reprise.

## 2.8.0 → 2.8.1 stable, schéma 15 → 16

Tester la version sur une copie isolée et préparer une procédure propre à l'installation avant de déployer. Installer le plugin 2.8.1 (révision de relais 2), puis le moteur : l'attente du premier catalogue est normale. Les deux composants passent ensemble au protocole 4 ; conserver leurs secrets existants. Aucun accès entrant, reverse proxy ni port public OpenFabLab n'est nécessaire pour cette liaison. Voir [le flux et ses limites](outbound-2.8.1.md).

1. Sauvegarder WordPress et relever version/schéma, volumes, réglages, comptes et compteurs métier. Préparer et vérifier les artefacts publics sur une copie isolée.
2. Arrêter proprement OpenFabLab ; sauvegarder à froid **PRE 15 complète**, avec base, fichiers privés, PIN, secrets, branding, réglages et configuration externe. Vérifier intégrité/FK et hashes ; conserver le runtime 2.8.0.
3. La migration normale ajoute deux tables techniques et les réglages manquants ; aucune purge historique. Ne pas forcer `user_version`. WordPress gère trois tables techniques : catalogue, actions/résultats et nonces anti-rejeu. Les cinq anciennes tables métier sont retirées uniquement si toutes sont vides, sous verrou ; aucune donnée non vide n'est effacée.
4. Avant réouverture, comparer les données PRE/POST, contrôler schéma 16, intégrité/FK, santé/version, persistant et protocole 4 dans Normal/Test. Exclure les routes REST et la page personnelle du cache WordPress. Vérifier le shortcode Test explicitement.
5. Réouvrir puis sauvegarder **POST 16**. Avant nouvelles écritures, un retour exige le runtime 2.8.0 avec **PRE 15 correspondante**, jamais le runtime ancien sur une base 16. Après écritures, aucun retour automatique destructif : préserver l'état et demander une décision humaine.

La distribution publique ne contient aucune commande ni configuration propre à une installation privée. Préparer séparément sa procédure d'exploitation. Les paragraphes suivants décrivent les versions historiques, pas la configuration du relais 2.8.1.

## 2.7.1 → 2.8.0 stable, schéma 14 → 15

La migration est additive et transactionnelle. Aucune animation, réservation passée, statistique, fiche usager ou facture OpenFabLab n'est supprimée ni réinterprétée. L'ancien mécanisme d'accompagnateur reste lisible pour l'historique ; les nouvelles demandes utilisent les comptes rattachés. Une migration d'une copie réelle puis le déploiement 2.8.0 ont été validés au FougèresLab ; chaque structure doit néanmoins vérifier sa propre installation.

1. Relever version 2.7.1/schéma 14, montages, fichiers privés, configuration et compteurs métier. Vérifier intégrité, clés étrangères et espace disque ; conserver le runtime/image 2.7.1.
2. Vérifier les empreintes des ZIP 2.8.0, préparer le runtime puis essayer la migration sur une copie privée isolée, jamais sur l'unique base réelle. Voir [le guide](candidate-2.8-guide.md).
3. Arrêter proprement le service avant la migration réelle. Créer une sauvegarde **PRE 14** complète et cohérente : SQLite, fichiers privés, PIN dérivés, clés/secrets, réglages, branding et configuration externe. Calculer les empreintes et conserver cette PRE après la bascule. La copie automatique dans `migration-backups/` ne la remplace pas.
4. Installer uniquement le nouveau runtime en conservant le persistant réel. L'initialisation normale applique 14 → 15 ; ne pas forcer `user_version`, réinitialiser la base ou rejouer une migration historique. Les protections d'une copie de test ne doivent pas remplacer la configuration réelle.
5. Avant réouverture, contrôler schéma 15, `integrity_check = ok`, zéro erreur FK, données anciennes/compteurs, volumes, branding, droits et HTTP/version. Vérifier les seuils/coordonnées et SMTP sans créer de fausse réservation réelle.
6. Réouvrir le service puis créer une sauvegarde **POST 15** distincte. Après réouverture ou toute nouvelle écriture, **aucun rollback automatique** vers la PRE : préserver l'état courant et décider explicitement d'une reprise.

Un retour avant réouverture exige le runtime 2.7.1 **avec la PRE 14 et ses fichiers privés correspondants**, service arrêté. **Ne jamais lancer 2.7.1 sur la base 15.**

Le plugin **2.8.0** est mis à jour séparément et devient un relais HTTPS vers OpenFabLab ; le plugin 2.7 ne traite pas les nouvelles demandes familiales. Vérifier la nouvelle URL OpenFabLab et le secret partagé, puis les environnements Test/Normal. Le nettoyage du stockage historique WordPress est une opération volontaire distincte, avec sauvegarde, jamais un préalable automatique ni une suppression de données OpenFabLab. S'il existe des réservations WordPress actives, arrêter et préparer leur traitement avant tout nettoyage. Voir [le guide WordPress](wordpress.md).

Les procédures ci-dessous concernent les anciennes versions.

## 2.7.0 → 2.7.1

SQLite reste au **schéma 14** et Reservations au **2.7.0**. L’initialisation normalise les ordres des catégories et initialise l’ordre des habilitations dans la configuration existante. Elle ajoute l’option de demandes d’animations depuis la borne, désactivée par défaut, et remplace une fois l’ancienne cadence de deux minutes par 1,5 minute ; les autres intervalles personnalisés sont préservés. Elle ne migre pas les données métier, ne remplace pas les ressources privées et ne modifie pas les PIN ou les secrets. Les nouvelles ressources et catégories restent configurées par la structure, sans valeurs institutionnelles imposées. Les demandes publiques utilisent l’outbox existante, sans nouvelle table.

Conserver une sauvegarde complète privée et le runtime précédent. Tester la nouvelle version avec une copie privée de test isolée, puis contrôler santé, intégrité/FK, données, droits, catégories, ressources et branding. Ne rejouer aucune migration historique. OpenFabLab 2.7.1 est stable et a été déployé en conditions réelles au FougèresLab ; cette validation ne dispense pas des contrôles sur chaque installation. Voir [les corrections](corrections-2.7.1.md).

Les configurations de production, fichiers privés et intégrations doivent être conservés. Ne jamais importer une base de test ou ses protections dans la production. Reservations 2.7.0 reste inchangé : aucun redéploiement WordPress nécessaire pour cette seule mise à jour. Après de nouvelles écritures, ne restaurer aucune sauvegarde PRE automatiquement : conserver l’état courant et décider d’une reprise explicite.

## 2.6.x / schéma 13 → 2.7.0 / schéma 14

Le persistant complet, pas seulement SQLite, doit être sauvegardé avant migration.
Le [format privé complet](private-backup.md) distingue production et copie de test
neutralisée. Les paquets d'exploitation privés peuvent automatiser préflight,
build avant interruption, PRE/POST complets, essai hors réseau, migration,
validation et rollback avant exposition en une seule commande. Après exposition
potentiellement suivie d'écritures, aucune ancienne sauvegarde n'est restaurée
automatiquement. Les chemins et scripts propres à une infrastructure restent
privés ; ils ne font pas partie de la distribution publique.

Le plugin associé est **Reservations 2.7.0**, sans changement de schéma WordPress. Les anciennes clés de catégories et leurs affectations restent conservées. Le mécanisme normal migre transactionnellement et crée aussi une copie SQLite pré-initialisation ; celle-ci ne remplace pas une sauvegarde complète.

1. Relever version, schéma et état du service. Contrôler la base en lecture seule et vérifier l’espace disponible.
2. Conserver l’image/code 2.6.x, Compose, configuration et chemins de montage. Préparer la nouvelle image avant interruption lorsque possible ; la tester avec une base vierge, sans réseau ni workers.
3. Arrêter proprement puis sauvegarder **tout le persistant** : SQLite, PIN dérivés, clé Flask, secrets, branding, profils et autres fichiers privés. Sur 2.6.x, copier le dossier complet à froid puisque son interface ne propose pas encore le nouveau format. Conserver cette sauvegarde schéma 13 sans la modifier.
4. Tester la migration normale sur une copie isolée. Pour une migration hors ligne, désactiver les workers et actions externes et n’exposer aucun port public. Ne pas forcer `user_version` manuellement ni rejouer des migrations historiques/PIN.
5. Vérifier schéma 14, intégrité, clés étrangères, conservation des données et réglages, puis mettre en service avec le même persistant. Contrôler HTTP/HTTPS, droits, modules et ressources privées.
6. Après validation et redémarrage, créer une sauvegarde complète privée schéma 14, distincte de l’état schéma 13.

Contrôles SQLite avant et après :

```sql
PRAGMA user_version;
PRAGMA integrity_check;
PRAGMA foreign_key_check;
```

Attendus : 13 avant, 14 après ; `ok` ; aucune ligne FK. Comparer aussi les données métier : l’intégrité ne prouve pas à elle seule leur conservation.

**Ne jamais démarrer 2.6.x avec une base schéma 14.** Un rollback exige la sauvegarde froide **schéma 13 correspondante**, ses fichiers privés et son runtime. Après exposition ou écritures de workers, ne pas restaurer automatiquement cet état ancien : préserver la base 14 et décider explicitement de la reprise pour éviter une perte de nouvelles données. Voir [nouveautés et contrôles d’essai](evolution-2.7.md).

Pour les déploiements, privilégier lorsque raisonnable un paquet privé préparé, une commande ponctuelle, contrôles automatisés, sauvegarde, rollback prudent et rapport lisible. La distribution publique ne contient pas les scripts ni chemins propres à une infrastructure ; une migration complexe peut nécessiter une procédure distincte.

## 2.6.2 → 2.6.3

SQLite reste au **schéma 13**. Seuls six réglages manquants sont ajoutés : DPO libre, e-mail/téléphone DPO, utilisation du logo complémentaire, de la signature et du badge privé. Les trois cases sont activées par défaut pour conserver l’apparence actuelle. Les réglages existants, même vides ou désactivés, restent prioritaires ; aucun fichier privé n’est effacé. Des anciennes clés DPO explicites peuvent être reprises, jamais l’e-mail général ni des valeurs institutionnelles prédéfinies.

Sauvegarder à froid le dossier de données complet et la configuration, tester l’initialisation normale sur une copie isolée puis préserver ce même `data` pour la nouvelle image. Vérifier santé, SQLite, contenu métier, ressources, réglages DPO et profil privé avant remise en service. Ne rejouer aucune migration historique ou migration PIN. Le plugin Reservations reste 2.6.1.

Lorsqu’un paquet de mise à jour automatisé est préparé pour l’installation, privilégier une seule commande avec contrôles préalables, sauvegarde, essai isolé, bascule, vérifications et rollback prudent. Une migration plus complexe peut nécessiter des étapes supplémentaires. Ne jamais restaurer automatiquement une sauvegarde si cela risque de perdre de nouvelles écritures métier.

## 2.6.0 → première édition publique 2.6.1

SQLite reste au **schéma 13**. Les changements sont la préparation Open Source : valeurs initiales neutres, Libre Franklin, ressources génériques, documentation et tests. Pas de changement fonctionnel métier intentionnel. Les réglages déjà enregistrés, les usagers, dossiers, inscriptions et fichiers persistants doivent être conservés.

Avant de quitter une ancienne distribution, vérifier que vos logos/signature sont dans le stockage privé `data/branding/` et référencés par les réglages. Les logos institutionnels et signatures qui provenaient de fichiers embarqués historiques ne sont pas redistribués. Sauvegarder ces fichiers dans votre espace privé et les importer via l'interface de structure si nécessaire ; le logiciel ne reconstitue pas les images ou coordonnées supprimées de ses constantes publiques. Il ne remplace pas vos valeurs enregistrées par des valeurs neutres.

## 2.5.x (schéma 12) → 2.6.x (schéma 13)

La migration normale est additive : paramètres de mode de réservation, table de créneaux et rattachement optionnel des inscriptions. Les animations existantes deviennent `whole`, sans créneau requis, et les inscriptions classiques ne sont pas déplacées.

1. Vérifier santé, version, espace et image/code de rollback ; construire la nouvelle image avant interruption si possible, sans monter les données actives dans un conteneur d'essai.
2. Vérifier la base en lecture seule, arrêter proprement, sauvegarder à froid l'ensemble des données et fichiers privés dans un dossier distinct.
3. Tester la migration sur une copie ; vérifier schéma, integrity, FK et conservation des données. Aucun essai sur l'unique copie réelle.
4. Installer le nouveau code en préservant `data/` et configuration privée. L'initialisation normale applique les migrations. Désactiver réseau/scheduler pour un contrôle avant exposition si votre orchestration le permet.
5. Vérifier santé, versions, rôles, dossiers/documents, réservations classiques, créneaux Test, synchronisation, puis redémarrage et sauvegarde post-mise à jour.

Installer d'abord le plugin Reservations 2.6.1 : il conserve le parcours classique avec un serveur 2.5.0, puis fournit `animation_slots_v1` au serveur 2.6.x. Ne pas changer les secrets pour une simple mise à jour.

## Retour arrière

Conserver l'état problématique pour analyse. Si des écritures métier ont eu lieu depuis la bascule, arrêter et définir une reprise explicite pour ne pas les perdre. Une ancienne version ne doit **jamais** recevoir une base de schéma plus récent. Restaurer uniquement sa sauvegarde froide cohérente et ses fichiers privés ; conserver les anciennes images/dossiers jusqu'à validation durable. Aucun nettoyage automatique n'est prévu.
# Mise à jour 2.6.1 → 2.6.2

Le schéma reste 13. Ne rejouer aucune migration historique ni migration PIN. Sauvegarder la base à froid, tout `data`, `.env`, compose et l’image précédente ; préparer l’image avant interruption. Les nouvelles clés de logos/RGPD sont ajoutées sans écraser les réglages existants. Les ressources privées ne sont pas incluses dans le ZIP public et doivent rester persistantes. Après mise à jour, comparer les données métier, vérifier santé, identité, badges et documents. Ne revenir à l’ancienne sauvegarde qu’avant de nouvelles écritures métier ; sinon conserver l’état et décider explicitement. Voir [Branding](branding.md).
# Mise à jour 2.8.5 → 2.8.6 : schéma 19 inchangé

Cette correction conserve le **schéma 19** et le **plugin Reservations 2.8.5**,
protocole 4 / révision 3. Aucune migration de tables, réinstallation du plugin ou
nouvelle exposition réseau. Les nouveaux paramètres de présentation Discord
utilisent la configuration existante : insertion des seuls défauts manquants,
préférences enregistrées conservées, identité désactivée par défaut.

Avant tout changement, sauvegarder intégralement le persistant, les fichiers
privés, le runtime et la configuration du conteneur. Construire et essayer le
runtime isolément ; arrêter proprement avant la sauvegarde froide finale et la
copie des nouveaux fichiers. Ne jamais remplacer Compose, les secrets ou les
volumes avec les exemples de distribution. Vérifier HTTP, version 2.8.6,
schéma 19, intégrité/FK, paramètres, données et relais Normal/Test.

La sauvegarde POST doit être cohérente : la procédure préparée prévoit un arrêt
propre pour la copie complète, puis redémarre le même conteneur et revérifie les
échanges. C’est un instantané avant ce redémarrage, pas une couverture des
écritures ultérieures. Ne pas restaurer automatiquement une ancienne base après
une première tentative de démarrage public. Conserver l’état en échec et obtenir
une décision humaine. Les procédures NAS propres à une structure sont privées
et ne sont pas incluses dans l’archive générique.

Voir [le guide de cette micro-correction](corrections-2.8.6.md).
