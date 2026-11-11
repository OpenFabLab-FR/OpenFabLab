# OpenFabLab

**Le logiciel qui facilite l’accueil, l’organisation et le suivi de votre FabLab.**

Né au FougèresLab, OpenFabLab a été conçu pour les équipes qui accueillent du
public, organisent des ateliers et entretiennent un parc de machines. Le
logiciel est libre (MIT), modulaire et auto-hébergeable : vous choisissez les
fonctions utiles à votre atelier et l’équipement qui héberge vos données.

[Site officiel](https://openfablab.fr) ·
[Télécharger OpenFabLab 2.16.0](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.16.0) ·
[Documentation](docs/index.md) · [Licence MIT](LICENSE)

## Pour quels lieux ?

FabLabs associatifs ou municipaux, tiers-lieux et ateliers partagés.
Commencez avec les modules dont votre équipe a besoin, que l’accueil soit
assuré par des bénévoles, des FabManagers ou les deux.

## Au quotidien

- **Accueillir les personnes** : comptes usagers et familles, accueil de visiteurs
  sans compte et prise en charge par l’équipe.
- **Suivre les passages** : arrivées et départs sur la borne tactile, par QR Code
  ou identifiant ; fréquentation et occupation.
- **Organiser les activités** : OpenLab, horaires exceptionnels, calendrier,
  animations, inscriptions et listes d’attente.
- **Réserver et prêter** : créneaux, locations gratuites ou payantes ; une
  réservation ne vaut pas remise du matériel.
- **Gérer les ressources** : machines, salles, équipements, tutoriels PDF et
  fiches accessibles par QR Code.
- **Assurer la maintenance** : états, interventions, signalements facultatifs,
  rappels et suivi des remises en service.
- **Suivre l’activité** : devis, tarifs, factures, bilans et statistiques.
  Abonnements et crédits sont facultatifs.
- **Adapter le logiciel** : modules, identité visuelle, cinq langues, rôles et
  [intégrations facultatives](docs/integrations.md).

Les cinq langues de l’interface sont FR, EN, DE, ES et FI. Les contenus que
vous rédigez ne sont pas traduits automatiquement. WordPress, Discord,
les e-mails, les annonces vocales et l’agent de mise à jour restent facultatifs.
La borne est conçue pour le tactile et l’administration s’adapte aux petits
écrans ; aucune conformité générale RGAA ou WCAG n’est revendiquée.

## Installer ou mettre à jour

1. Vérifiez les [prérequis](docs/platform-compatibility.md) de votre serveur :
   [Synology](docs/installation-synology.md), [Linux](docs/installation-linux.md),
   [Raspberry Pi 64 bits](docs/installation-raspberry-pi.md) ou
   [Windows avec environnement Linux](docs/installation-windows.md).
2. Téléchargez `OpenFabLab-2.16.0.zip`, vérifiez son SHA-256 et suivez le
   [démarrage sur un stockage neuf](docs/installation.md).
3. Créez le premier PIN sur le réseau autorisé, suivez l’assistant, puis
   [configurez la borne et ouvrez les modules utiles](docs/prise-en-main-2.16.md).

Pour une instance existante, commencez par une [sauvegarde vérifiée](docs/backup-restore.md)
et choisissez [la procédure de mise à jour](docs/upgrade.md). Le kit
d’activation est séparé ; [l’agent](docs/update-agent.md) est facultatif et le
service web n’accède pas au socket Docker.

La **2.16.0** conserve SQLite **28**. La mise à jour par ZIP depuis la
2.15.5 a réussi sur le Synology du FougèresLab avec un agent déjà installé
et les sauvegardes PRE/POST. Une première installation a été vérifiée
en environnement isolé, pas sur chaque plateforme.
[Notes et procédure de version](docs/upgrade-2.16.0.md).

## Participer

[Contribuer](CONTRIBUTING.md) · [Signaler un problème](https://github.com/OpenFabLab-FR/OpenFabLab/issues) ·
[Historique](CHANGELOG.md) · [Roadmap](ROADMAP.md) · [Sécurité](SECURITY.md).
Ne joignez ni base, ni sauvegarde, ni données personnelles à un ticket public.

L’auto-hébergement donne la main sur le stockage, les accès et les
sauvegardes. Il ne garantit pas à lui seul la conformité au RGPD :
la structure reste responsable des informations qu’elle recueille et
de leur conservation. Il n’y a pas d’intégration de paiement bancaire
en ligne ; HelloAsso reste à l’étude.
