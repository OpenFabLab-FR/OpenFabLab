# Recette de la candidate 2.14.0

La recette utilise exclusivement des données fictives et des répertoires temporaires
isolés. Interdire le réseau externe et désactiver planificateur/météo avant tout
import de l’application. Ne jamais exécuter ces scénarios sur une base de production.

Les nouvelles suites publiques sont `test_v214_core`, `test_v214_languages`,
`test_v214_reminders`, `test_v214_edges`, `test_v214_compatibility`, `test_v214_migration` et
`test_v214_wordpress.php`. Elles complètent les régressions ciblées des familles,
attentes, créneaux, e-mails, relais, inscriptions publiques et protections existantes.
Un test d’ancien schéma conserve son état source et son contrôle de refus ; seule
l’attente du schéma de sortie courant suit `family_model.SCHEMA`.

## Migration et restauration

Le test 22 → 23 utilise une base entièrement fictive créée par le véritable runtime
2.13.0. Fournir son chemin par `OFL_SCHEMA22_FIXTURE`. Sans cette base, la suite le
signale comme ignoré : ce n’est pas une migration vérifiée. Le scénario local de
livraison vérifie les valeurs de toutes les tables préexistantes, les préférences,
la sauvegarde 22, l’interruption transactionnelle, l’idempotence et l’intégrité.

La restauration crée une archive privée fictive, la contrôle, la restaure dans un
autre répertoire, ouvre la base, compare ses données et redémarre l’application
isolée. Le simple succès d’un décompactage ne vaut pas preuve de restauration.

## Interfaces et transports

Les contrôles navigateur utilisent les pages Flask réelles, Chromium et WebKit.
Comparer la géométrie de la caméra à la stable, vérifier les cinq largeurs, les
formulaires, les deux langues, les modales et les parcours publics. Les flux caméra
de tests sont simulés : la caméra physique d’une tablette reste à valider localement.

Les tests PHP exécutent les classes distribuées avec des options et transports
fictifs. Les tests navigateur du plugin contrôlent les scripts réels avec un relais
simulé. Cela ne prouve ni un thème WordPress précis ni la délivrabilité d’un SMTP
ou webhook réel. La production n’est jamais utilisée comme environnement d’essai.

Les bilans de livraison indiquent les commandes effectivement exécutées, nombres,
échecs éventuels, reprises et limites. Ne pas additionner plusieurs exécutions des
mêmes tests comme s’il s’agissait de scénarios distincts.
