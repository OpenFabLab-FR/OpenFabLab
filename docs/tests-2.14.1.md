# Vérifications de la candidate 2.14.1

Les essais utilisent uniquement des données fictives et des environnements isolés.
La candidate n’est ni publiée ni déployée automatiquement. Les rapports et captures
complets accompagnent la livraison locale ; aucun rapport privé NAS n’est public.

## Campagnes ciblées exécutées

- 108 tests Python : 63 contrôles des ressources, rappels, droits, préférences et
  migration, plus 45 régressions des familles, listes d’attente, facturation,
  pointage et e-mails simulés.
- 394 contrôles Chromium/WebKit : 379 principaux et 15 supplémentaires, FR/EN,
  largeurs 320, 390, 768, 1024 et 1440 px. Dix comparaisons avant/après de la zone QR,
  huit thèmes de borne, hôte WordPress clair/sombre, tactile et clavier.
- 307 contrôles PHP : initialisation des shortcodes et routes REST, cycle de blocs
  Shortcode modélisé, données publiques, cache, signatures et familles.
- 82 tests de préparation DSM, puis 18 revérifications après extraction du paquet
  final : confirmations, refus, source/cible, sauvegardes et restauration isolée,
  migration fictive 23 → 24 et préservation des écritures après ouverture.

Les tests de migration vérifient les valeurs, identifiants, rowids, index, liens,
contraintes et clés étrangères. Une erreur restaure la transaction et laisse le
schéma 23 cohérent ; un schéma inconnu ou une dépendance entrante inconnue est refusé.
Aucun changement de schéma supplémentaire ne vient des compléments de ressources.

## Frontières de validation

SQLite, les fichiers et les sauvegardes/restaurations ont réellement été utilisés
sur des fixtures fictives. Les navigateurs sont les vrais moteurs Chromium/WebKit.
En revanche, Docker/DSM et les transports WordPress sont simulés ; le cycle
Gutenberg est modélisé avec les vrais fichiers PHP, pas avec une installation
WordPress complète. La caméra est simulée : ses dimensions sont comparées, pas
sa capacité matérielle de lecture sur un iPhone ou une tablette physique.

Le prochain contrôle réel de l’installation reste nécessaire avant une décision
de mise à jour. Une page qui s’affiche ne prouve pas à elle seule la réussite des
contrôles de données, de sauvegarde ou de synchronisation.

## Points particuliers

Les ressources historiques conservent leurs identifiants et leurs liens au
catalogue de location. Les projections publiques préservent les permissions
antérieures, sans ajout de canal implicite. La cause exacte de l’absence d’un
équipement sur une installation réelle ne peut pas être affirmée sans ses preuves.

La moyenne publique facultative est désactivée par défaut, ne transmet aucune
donnée individuelle et possède des seuils explicites. Les anciens horaires
habituels n’étant pas versionnés, le créneau actuel et les exceptions conservées
servent de référence ; voir [la méthode et ses limites](corrections-2.14.1.md).
