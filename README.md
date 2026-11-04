# OpenFabLab 2.14.4

**Le quotidien du FabLab, plus simple.**

OpenFabLab est un logiciel libre, modulaire et auto-hébergeable pour accueillir
les usagers, suivre la fréquentation et organiser les activités d’un FabLab.
Vous gardez la maîtrise de votre installation et de vos données.

Chaque structure choisit ses outils : la borne fonctionne sans WordPress,
sans Discord et sans gestion d’abonnement. Activez seulement les modules utiles
à votre équipe, qu’elle soit composée de FabManagers, de bénévoles ou des deux.

**Version stable 2.14.4 · SQLite 25 · Français / anglais · Licence MIT**

[Télécharger l’application](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.14.4/OpenFabLab-2.14.4.zip) ·
[Release et empreintes SHA-256](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.14.4) ·
[Installer OpenFabLab](docs/installation.md) · [Site officiel](https://openfablab.fr)

## Des outils qui s’adaptent à votre FabLab

- **Accueillir en autonomie** : borne tactile, QR Code ou identifiant, arrivées,
  départs et visiteurs anonymes ; comptes individuels et liens familiaux.
- **Organiser les activités** : OpenLab, horaires exceptionnels, animations,
  inscriptions, créneaux, listes d’attente, propositions de places et présences.
- **Suivre les ressources** : machines, salles et équipements, catégories,
  disponibilités techniques, interventions, rappels, historiques et archivage.
- **Gérer les accès** : formations et habilitations, règles de réservation et
  rôles administrateur/modérateur selon les autorisations existantes.
- **Préparer les bilans** : fréquentation, publics, temps de présence,
  statistiques, CSV, bilan visuel PDF et rapport annuel PDF/DOCX.
- **Gérer les dossiers** : devis, factures et règlements ; abonnements,
  cotisations familiales, pass et crédits lorsque ce module est activé.
- **Informer sans surcharger** : e-mails et Discord facultatifs, rappels
  configurables et confirmations sonores désactivables sur la borne.
- **Compléter votre site WordPress** : réservations, calendrier et catalogue
  public des ressources avec un plugin facultatif, sans exposer l’administration.

Les textes standards disposent de catalogues locaux français/anglais. Les noms,
descriptions et e-mails personnalisés restent dans leur langue d’origine : aucun
service de traduction automatique n’est utilisé.

Le module **Abonnements et crédits est désactivé par défaut**. OpenFabLab ne
propose ni paiement bancaire en ligne, ni Stripe/PayPal, ni prélèvement ou
renouvellement payant automatique. La gestion des droits reste indépendante
d’un système bancaire.

## Ce qu’apporte la version 2.14.4 depuis la 2.13.0

Cette stable réunit la grande évolution 2.14 et ses finitions validées : interface
FR/EN, suivi des ressources, rappels liés aux interventions, horaires exceptionnels,
publication WordPress choisie, calendrier public et ressources, interfaces plus
compactes et protection des parcours d’inscription et de départ.

Les ressources peuvent être archivées puis restaurées sans perdre leur historique.
Une suppression définitive reste réservée aux administrateurs, avec confirmation
et refus en présence de données associées. Le calendrier public permet de consulter
un mois d’historique admissible, sans rouvrir les réservations passées.

[Nouveautés détaillées](CHANGELOG.md) · [Guide d’utilisation](docs/utilisation.md) ·
[Ressources et maintenance](docs/resources-maintenance.md) · [Roadmap](ROADMAP.md)

## Installer et mettre à jour

Une installation demande un serveur compatible, un stockage persistant fiable,
des sauvegardes et une configuration réseau adaptée. Docker est proposé, sans
être obligatoire ; aucun service hébergé ni image multiarchitecture certifiée
n’est promis. Les guides décrivent les prérequis et leurs limites.

[Linux](docs/installation-linux.md) · [Synology DSM](docs/installation-synology.md) ·
[Raspberry Pi](docs/installation-raspberry-pi.md) · [Windows](docs/installation-windows.md) ·
[Compatibilité](docs/platform-compatibility.md)

**Mise à jour depuis 2.13.0 : SQLite 22 → 25.** Le moteur existant applique les
évolutions intermédiaires ; les parcours 22→25, 23→25 et 24→25 ont été vérifiés
sur des bases fictives issues des anciens runtimes. Cela ne remplace pas un essai
sur une copie isolée de votre installation ni les sauvegardes complètes PRE/POST.
Ne jamais redémarrer une ancienne application sur une base migrée au schéma25.

[Procédure de mise à jour](docs/upgrade.md) · [Sauvegarde et restauration](docs/backup-restore.md) ·
[Maintenance](docs/maintenance.md) · [Sécurité](SECURITY.md)

## Plugin WordPress facultatif

[OpenFabLab Reservations 2.14.4](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.14.4/openfablab-reservations-2.14.4.zip)
s’installe séparément. La mise à jour du serveur OpenFabLab ne met pas à jour
WordPress. Conservez les options et la clé partagée lors du remplacement du ZIP.

Trois shortcodes principaux, à insérer dans des blocs **Code court** Gutenberg :

```text
[openfablab_reservations environment="production"]
[openfablab_calendar environment="production" view="week"]
[openfablab_machines environment="production"]
```

Les fonctionnalités publiques et le choix de langue s’activent dans les réglages
du plugin. Un seul sélecteur FR/EN pilote les composants d’une même page.
OpenFabLab garde le contrôle des places ; WordPress reste responsable des titres
et de la mise en page éditoriale.

[Configurer WordPress et ses shortcodes](docs/wordpress.md)

Protocole **4 / révision 3**, inchangé ; compatibilité négociée par capacités,
sans obligation d’égalité des versions. Normal et Test restent séparés.

## Contribuer et conserver la maîtrise

[Contribuer](CONTRIBUTING.md) · [Architecture](docs/architecture.md) ·
[Développement](docs/development.md) · [Licence MIT](LICENSE) ·
[Mentions tierces](THIRD_PARTY_NOTICES.md)

Les anciennes releases, tags et documentations restent disponibles dans
[l’historique GitHub](https://github.com/OpenFabLab-FR/OpenFabLab/releases).
Les distributions publiques ne contiennent ni sauvegarde, ni configuration
privée d’une structure, ni paquet de dépannage propre à un NAS.
