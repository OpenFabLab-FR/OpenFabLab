# OpenFabLab 2.15.5

**Le quotidien du FabLab, plus simple.**

OpenFabLab est un logiciel libre, modulaire et auto-hébergeable pour accueillir
les usagers, suivre la fréquentation et organiser les activités d’un FabLab.
Vous gardez la maîtrise de votre installation et de vos données.

Chaque structure choisit ses outils : la borne fonctionne sans WordPress,
sans Discord et sans gestion d’abonnement. Activez seulement les modules utiles
à votre équipe, qu’elle soit composée de FabManagers, de bénévoles ou des deux.

**Version stable 2.15.5 · SQLite 28 · FR / EN / DE / ES / FI · Licence MIT**

La V2.15.5 a été installée et vérifiée sur Synology via l’import du ZIP
depuis l’administration. Elle conserve SQLite 28 sans migration.

[Téléchargements et empreintes](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.15.5) ·
[Choisir le bon parcours de mise à jour](docs/upgrade.md) ·
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

Les textes standards disposent de cinq catalogues locaux. Les noms,
descriptions et e-mails personnalisés restent dans leur langue d’origine : aucun
service de traduction automatique n’est utilisé.

Le module **Abonnements et crédits est désactivé par défaut**. OpenFabLab ne
propose ni paiement bancaire en ligne, ni Stripe/PayPal, ni prélèvement ou
renouvellement payant automatique. La gestion des droits reste indépendante
d’un système bancaire.

## Ce qu’apporte OpenFabLab 2.15.5

Le calendrier affiche les maintenances multijours d’un seul tenant, sans
ajouter de journée au retour estimé. Le Résumé affiche jusqu’à quinze
événements si l’espace le permet, ainsi que huit identifications
d’emblée (jusqu’à quarante au total). La série 2.15 améliore aussi la
lisibilité des horaires locaux, le suivi des mises à jour et les
signalements facultatifs depuis les fiches QR des ressources.

## Ce qu’a apporté OpenFabLab 2.15.2

L’en-tête de gestion tient sur deux rangées en portrait sur smartphone.
Le Résumé modernise la présentation des indicateurs, listes et alertes
sans changer les chiffres, les droits ou les données. Au FougèresLab, la mise
à jour depuis la 2.15.1 a réussi sur Synology par import du ZIP dans
l’administration, sans passer par DSM. SQLite reste au schéma 26.

## Ce qu’a apporté OpenFabLab 2.15.1

L’administration accepte un ZIP OpenFabLab fourni par l’administrateur ou
une version stable officielle de GitHub. Les deux parcours partagent le moteur
de sauvegarde, de vérification et d’installation. Aucun ne démarre seul.

Le Résumé distingue les créneaux confirmés en cours des matériels effectivement
remis. Les prêts gratuits comptent, les retours à traiter sont accessibles
directement et les cinq dernières identifications sont visibles d’emblée.
La recherche retrouve les clients et leurs dossiers liés. Le calendrier affiche
une bande par location multijour et reste défilable sur mobile. Les étiquettes
QR peuvent utiliser une adresse de réseau privé ou une adresse HTTPS.

## Les bases posées en 2.15.0

Un nouveau **Résumé** rassemble les informations utiles à l’équipe. La recherche
locale retrouve les fiches autorisées. Les réglages sont rangés par usage et les
installations neuves disposent d’un assistant, sans réinitialiser les anciennes.

Les remises et retours explicites rendent les prêts visibles jusqu’à restitution,
y compris en retard. Les fiches usagers réunissent locations et participations,
sans confondre annulation et absence. Les locations multijours quittent la grille
horaire. Chaque ressource possède une adresse QR permanente et peut recevoir des
tutoriels PDF partagés, publics ou réservés à l’équipe. Une fiche unique réunit
configuration et entretien. Le mode Disponible à la location reste distinct d’un
prêt réel ; le tri des ressources est alphabétique naturel. La visibilité publique
est cohérente avec la case affichée, sans élargir les anciennes permissions.

Un **agent local séparé et facultatif** prépare les futures mises à jour officielles
depuis l’administration. Son installation initiale demande l’autorisation du
responsable du serveur ; le web ne reçoit jamais le socket Docker. La procédure
manuelle reste disponible. [Installation, sécurité et secours](docs/update-agent.md).

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

**Depuis la 2.15.4 : SQLite 28 conservé.** Avec un agent compatible et
connecté, rechercher la version officielle ou [importer le ZIP vérifié](docs/upgrade-2.15.5.md).
Depuis la stable publique précédente 2.15.2 (SQLite 26) ou un autre schéma
antérieur, suivre le [parcours manuel par version et schéma](docs/upgrade.md).
Pour une installation neuve, suivre le [guide d’installation](docs/installation.md) :
l’application fonctionne sans agent. Les anciens kits d’activation sont
propres à leur version et ne doivent pas être utilisés sur la 2.15.5.

[Procédure de mise à jour](docs/upgrade.md) · [Sauvegarde et restauration](docs/backup-restore.md) ·
[Maintenance](docs/maintenance.md) · [Sécurité](SECURITY.md)

## Plugin WordPress facultatif

**[OpenFabLab Reservations 2.15.3](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.15.5/openfablab-reservations-2.15.3.zip)** s’installe
séparément. La mise à jour du serveur OpenFabLab ne met pas à jour
WordPress. Conservez les options et la clé partagée lors du remplacement du ZIP.
Le catalogue affiche le badge de disponibilité devant chaque nom ; l’affichage
des catégories se règle indépendamment du titre de la liste.

Trois shortcodes principaux, à insérer dans des blocs **Code court** Gutenberg :

```text
[openfablab_reservations environment="production"]
[openfablab_calendar environment="production" view="week"]
[openfablab_machines environment="production"]
```

Les fonctionnalités publiques et le choix de langue s’activent dans les réglages
du plugin. Un seul sélecteur à cinq langues pilote les composants d’une même page.
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
