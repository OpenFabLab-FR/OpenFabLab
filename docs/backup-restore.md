# Sauvegarde et restauration

## Ce qui doit être conservé

- `openfablab.db`, avec tout éventuel WAL/journal lors d'une copie à froid.
- Fichiers privés persistants : clé Flask, dérivations PIN, webhook, secret de synchronisation, ressources `branding/`, signature et autres fichiers utilisés par l'installation.
- Configuration de déploiement, `.env` privé, version du code/image et archives correspondantes.

Un export SQLite **n'inclut pas** les secrets séparés. Un profil `.openfablab-profile.zip` contient des réglages/assets mais n'est pas une sauvegarde métier ni de credentials. Ces deux types d'export doivent rester privés.

## Sauvegardes de l'application

Dans **Réglages → Données et sauvegardes**, choisir la racine montée par l'administrateur et le sous-dossier. Par défaut : `OpenFabLab` à l'intérieur de `/nas-backups` dans Docker, soit `./backups/OpenFabLab` avec le compose fourni. Aucun emplacement Synology absolu n'est requis. Les nouveaux fichiers utilisent `openfablab-sauvegarde-*`.

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

Tester d'abord dans un environnement isolé, avec réseau/scheduler désactivés et sans synchronisation vers le WordPress réel. L'interface Admin propose une restauration SQLite explicite avec copie de sécurité. Restaurer séparément les fichiers privés nécessaires pour une reprise complète. Ne jamais restaurer un schéma plus récent dans une ancienne version : utiliser la sauvegarde cohérente correspondant à la version choisie.

Les anciens noms de sauvegardes/base restent reconnus pour migration ; ne pas renommer ou nettoyer une ancienne archive pour la rendre artificiellement « nouvelle ».
# Ressources privées 2.6.2

Conserver également `data/branding/` : logos d’en-tête, de réseau, de documents, signature et éventuel `badge-template.svg`. Une sauvegarde SQLite ne suffit pas à restaurer ces fichiers. Le profil privé exporte l’identité et ces ressources, mais pas les secrets ni les données métier ; il doit rester confidentiel. Voir [Branding](branding.md).
