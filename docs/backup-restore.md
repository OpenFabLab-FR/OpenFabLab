# Sauvegarde et restauration

Depuis OpenFabLab 2.7.0, **Réglages → Données** distingue trois niveaux.

## 1. Sauvegarde SQLite

Exporte les données métier et réglages présents dans la base. Elle ne contient
pas nécessairement les fichiers privés externes : PIN dérivés, clé Flask,
secrets de synchronisation, SMTP, logos, signatures et modèle de badge.
Elle reste utile, mais ne reproduit pas à elle seule une installation complète.

## 2. Sauvegarde complète privée

Transporte la base cohérente et le dossier persistant, avec les fichiers requis
par l’installation. Un manifeste indique version du format, OpenFabLab, schéma,
type, composants et taille/SHA-256 de chaque fichier, sans recopier les valeurs
des secrets dans le manifeste. La restauration vérifie ces éléments et SQLite,
crée un état de sécurité puis remplace l’installation sans fusion arbitraire.

**Cette archive peut contenir données personnelles, dérivations PIN, clé Flask,
secrets WordPress, webhook Discord et mot de passe SMTP. Elle n’est pas chiffrée :
stockage protégé et accès restreint sont indispensables. Ne jamais la publier.**
Conserver séparément le runtime et sa configuration externe au dossier persistant.

## 3. Copie privée pour test/diagnostic

Conserve données, historique, identité et ressources disponibles, avec les PIN
dérivés pour éviter une nouvelle initialisation. WordPress et ses workers,
Discord, SMTP et météo sont neutralisés ; secrets d’intégration retirés et clé
de session renouvelée. Le marqueur persistant bloque les connexions externes,
même après réactivation accidentelle d’un réglage. Une restauration de type
test réimpose cette isolation.

Cette copie **reste privée** puisqu’elle conserve des données personnelles et
l’authentification locale. Ne jamais l’inclure dans GitHub, un ZIP public, un
rapport public ou une capture. Pour un diagnostic local, utiliser ce format
plutôt qu’une sauvegarde complète avec ses intégrations de production.

Voir [le format, les exclusions et la restauration](private-backup.md).
Le profil de structure ne remplace aucun de ces niveaux : il ne contient pas
les données métier ni tous les secrets d’une installation.

## Ce qui doit être conservé

- `openfablab.db`, avec tout éventuel WAL/journal lors d'une copie à froid.
- Fichiers privés persistants : clé Flask, dérivations PIN, webhook, secret de synchronisation, ressources `branding/`, signature et autres fichiers utilisés par l'installation.
- Configuration de déploiement, `.env` privé, version du code/image et archives correspondantes.

Un export SQLite **n'inclut pas** les secrets séparés. Un profil `.openfablab-profile.zip` contient des réglages/assets mais n'est pas une sauvegarde métier ni de credentials. Ces deux types d'export doivent rester privés.

OpenFabLab 2.7.0 ajoute `.openfablab_smtp.json` aux fichiers privés du dossier de données, inclus dans la sauvegarde complète mais neutralisé dans la copie de test. Ne jamais le joindre à un export public ni à un profil. Le profil version 1 accepte désormais les catégories/types et les préférences d’inscription/bienvenue/Discord ; les profils anciens restent compatibles. La copie SQLite de sécurité `migration-backups/` ne remplace pas la sauvegarde complète à froid. Voir [migration et contrôles 2.7](evolution-2.7.md).

## Sauvegardes de l'application

Dans **Réglages → Données**, choisir la racine montée par l'administrateur et le sous-dossier pour les sauvegardes SQLite automatiques. Par défaut : `OpenFabLab` à l'intérieur de `/nas-backups` dans Docker, soit `./backups/OpenFabLab` avec le compose fourni. Aucun emplacement Synology absolu n'est requis. Les nouveaux fichiers utilisent `openfablab-sauvegarde-*`. Ces sauvegardes automatiques SQLite restent distinctes des archives complètes privées.

Pour une sauvegarde complète avant mise à jour, arrêter proprement l'application et copier **tout** le dossier persistant vers un dossier de sauvegarde distinct, sans déplacer ni supprimer l'original. Protéger les permissions et stocker une copie hors machine selon vos besoins.

## Contrôles

Sur une copie isolée de la sauvegarde, avec SQLite :

```sql
PRAGMA user_version;
PRAGMA integrity_check;
PRAGMA foreign_key_check;
```

Attendus : version compatible, `ok`, aucune ligne FK. Comparer également les volumes/données métier ; un contrôle d'intégrité ne prouve pas à lui seul l'absence de perte. Conserver les empreintes et les rapports sans coordonnées ni secrets.

## Restauration

Tester d'abord dans un environnement isolé, avec réseau/scheduler désactivés et sans synchronisation vers le WordPress réel. L'interface Admin conserve la restauration SQLite explicite avec copie de sécurité et propose une restauration complète privée avec confirmation `RESTAURER INSTALLATION`. Le manifeste, les empreintes, versions, intégrité et clés étrangères sont vérifiés avant remplacement ; une archive invalide est refusée. Le type test reste isolé après restauration. Réauthentification avec le PIN de l’archive après une restauration complète.

Avec SQLite seul, restaurer séparément les fichiers privés nécessaires pour une reprise complète. Ne jamais restaurer un schéma plus récent dans une ancienne version : utiliser la sauvegarde cohérente correspondant à la version choisie. Les ensembles de fichiers sont journalisés pour récupération en cas d’interruption ; ils ne constituent pas une transaction unique de système de fichiers. Voir [les limites et la récupération hors ligne](private-backup.md).

Les anciens noms de sauvegardes/base restent reconnus pour migration ; ne pas renommer ou nettoyer une ancienne archive pour la rendre artificiellement « nouvelle ».
## Ressources privées

Depuis 2.6.3, le profil privé inclut le contact DPO libre, son e-mail/téléphone et les cases d’utilisation du logo complémentaire, de la signature et du badge privé. Les ressources configurées mais désactivées sont également exportées/importées. Une sauvegarde complète du dossier `data` conserve leurs fichiers, leurs paramètres et les secrets séparés. Les profils précédents restent importables sans convertir ni effacer leurs données métier.

Conserver également `data/branding/` : logos d’en-tête, de réseau, de documents, signature et éventuel `badge-template.svg`. Une sauvegarde SQLite ne suffit pas à restaurer ces fichiers. Le profil privé exporte l’identité et ces ressources, mais pas les secrets ni les données métier ; il doit rester confidentiel. Voir [Branding](branding.md).
