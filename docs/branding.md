# Identité, logos et badges privés

Dans Réglages → Structure et modules → Identité de la structure, quatre usages sont indépendants :

| Réglage | Destination | Stockage persistant |
| --- | --- | --- |
| Logo de la structure (en-tête) | Gauche de l’interface ; logo OpenFabLab si aucun personnalisé | `data/branding/wordmark.png` |
| Logo institutionnel d’en-tête | Droite, avant le réseau | `data/branding/header_institution.png` |
| Logo de réseau | Droite, avant météo et verrouillage | `data/branding/network.png` |
| Logo des documents administratifs | Factures/devis, jamais l’en-tête | `data/branding/institution.png` |

Les trois usages d’en-tête peuvent être masqués complètement : pas d’image ni d’emplacement vide. Les téléversements acceptent PNG/JPEG/WebP (2 Mo) et sont convertis en PNG. Le champ vide ne change rien ; un bouton séparé, avec confirmation, retire le logo de son usage. Le fichier désactivé reste récupérable jusqu’à son remplacement. Le logo complémentaire historique `main.png` et la signature `signature.png` restent exclusivement dédiés aux documents. Sans logos configurés, les documents sont générés sans image de logo. Aucun logo de document n’est automatiquement adopté par l’en-tête après configuration initiale.

## Badge personnalisé

Sans configuration privée, le modèle public générique est utilisé. Un administrateur peut téléverser un gabarit SVG autonome dans les ressources complémentaires. Il est conservé dans `data/branding/badge-template.svg` ; le réglage `structure_badge_template` vaut alors `badge-template.svg`. La sélection ne dépend jamais du nom de la structure.

Le SVG doit avoir `viewBox="0 0 54 86"`, les textes `user-id`, `first-name`, `category` (avec x/y/font-size), et un groupe `qr-code` non transformé. Le QR encode exclusivement `public_id`, sur la zone x=5.25, y=40, taille=43.5. Les transformations des autres éléments et les logos vectoriels intégrés sont conservés. Le fond `card-background`, s’il existe, est retiré. Les textes sont échappés et les prénoms longs ajustés. Le PNG est rendu depuis ce même SVG, avec transparence. Scripts, événements, images externes, liens externes et entités XML sont refusés.

Un modèle privé configuré mais absent/invalide produit une erreur explicite : aucun remplacement silencieux par le badge générique. La prévisualisation administrative utilise un usager fictif. Un gabarit peut embarquer une banque de tracés vectoriels (`badge-glyphs`) pour stabiliser sa typographie entre SVG et PNG ; ces ressources restent privées et leurs droits relèvent de l’installation. Aucune police propriétaire n’est fournie par OpenFabLab.

## Responsable du traitement

Renseigner séparément la personne morale, son adresse, son représentant et la fonction du représentant. La page Gestion des données affiche ces informations dans une carte distincte du DPO, dont les coordonnées sont dédiées et non déduites du contact général. Une installation neuve n’impose ni organisme ni personne ; un avertissement invite à compléter ces champs.

## Ressources complémentaires et DPO (2.6.3)

Dans OpenFabLab 2.7.0, les ressources graphiques restent dans **Réglages → Structure**. La protection des données (responsable, représentant, DPO) est regroupée dans **Réglages → Données**, avec conservation des mêmes clés, du profil et de la page publique.

Les trois ressources complémentaires sont présentées dans des cartes visibles, sans section repliée. Le logo complémentaire est réservé aux documents qui prévoient deux logos ; la signature est destinée aux bilans de facturation PDF/Excel. Son aperçu est réservé à l’administrateur et n’est pas exposé comme image publique. Le badge privé remplace le modèle générique uniquement lorsque **Utiliser le modèle de badge personnalisé** est coché. Désactiver une ressource conserve son nom de fichier, ses données et sa prévisualisation administrative ; elle peut être réactivée sans téléversement. Le retrait explicite reste une action séparée avec confirmation.

Les clés `structure_use_main_logo`, `structure_use_signature` et `structure_use_badge_template` sont initialisées à `1` uniquement si elles manquent, pour conserver le rendu antérieur. Une clé déjà personnalisée, y compris `0`, reste inchangée. Un badge privé activé mais invalide/absent produit toujours une erreur claire ; un badge privé volontairement désactivé utilise le modèle générique.

Les champs `structure_dpo`, `structure_dpo_email` et `structure_dpo_phone` sont indépendants de l’e-mail général. Le texte DPO est entièrement libre. Les anciennes clés explicites `structure_dpo_name`, `dpo_name`, `dpo`, `data_protection_officer`, `dpo_email`, `data_protection_officer_email`, `dpo_phone` et `data_protection_officer_phone` peuvent initialiser les nouveaux champs absents. Aucun nom de personne/structure ni aucune ancienne coordonnée codée en dur n’est fourni par le logiciel public. Les réglages canoniques existants, même vides, restent prioritaires.

Le profil privé conserve ces champs, les trois cases d’utilisation et les ressources configurées, même désactivées. Les profils antérieurs sans ces nouveaux champs restent importables. Le schéma SQLite reste 13 ; aucune donnée métier n’est migrée ou supprimée.

## Mise à jour 2.6.1 → 2.6.2

Les évolutions de branding 2.6.2/2.6.3 conservaient le schéma **13** ; OpenFabLab 2.7.0 utilise le schéma **14** pour les nouvelles fonctions métier, sans modifier les ressources privées existantes. Les réglages restent additifs et les valeurs existantes gagnent. Lorsque le nouveau réglage d’en-tête n’existe pas encore, l’ancien logo institutionnel présent est copié une seule fois vers un fichier distinct, sans modifier le logo documentaire. L’entité juridique et l’adresse déjà configurées initialisent les champs du responsable du traitement. Aucun réseau ou badge institutionnel n’est choisi par déduction du nom du FabLab.

Conserver tout `data`, les secrets et le montage `./data:/data`. Les nouveaux fichiers survivent aux redémarrages, images Docker et mises à jour. L’export/import `.openfablab-profile.zip` inclut logos, badge et champs d’identité ; ce profil est **privé** et ne doit jamais être publié. Son import n’emporte pas de secrets et conserve la règle existante de désactivation/reconfiguration WordPress/Discord. Une sauvegarde SQLite seule ne contient pas les fichiers : sauvegarder aussi `data/branding` et les fichiers privés séparément, avec accès restreint.
