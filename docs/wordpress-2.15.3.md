# Reservations 2.15.3 avec OpenFabLab 2.16.0

Le [ZIP Reservations 2.15.3](https://github.com/OpenFabLab-FR/OpenFabLab/releases/download/v2.15.5/openfablab-reservations-2.15.3.zip)
est fourni sans reconstruction. Si cette version est déjà installée,
ne la réinstallez pas. L’extension reste facultative et s’installe
séparément de l’application.

La version 2.15.3 sait afficher l’état **Indisponible** sans l’assimiler à
une panne. L’affichage est négocié par capacité et le protocole reste
**4 / révision 3**. Les plans de maintenance restent internes.

Pour la mise à jour du plugin, conserver les réglages et la clé partagée,
puis contrôler les échanges **Normal** et **Test** séparément. Les
[shortcodes, blocs Gutenberg, catégories et langues](wordpress-2.15.2.md)
restent ceux du guide précédent.

### Installer et publier

1. Dans WordPress, ouvrir **Extensions → Ajouter → Téléverser une
   extension**, choisir le ZIP Reservations, puis activer. En mise à jour,
   remplacer la version existante sans la désinstaller.
2. Configurer [la connexion sécurisée](wordpress-2.14.4.md) dans les deux
   administrations. Employer HTTPS vers WordPress et une clé privée
   propre à l’environnement. Tester d’abord sur **Test**, puis sur **Normal**.
3. Dans Gutenberg, ajouter un bloc **Code court** par affichage. Sans
   paramètre, les shortcodes ci-dessous utilisent l’environnement public
   de production : `[openfablab_reservations]`, `[openfablab_calendar]`,
   `[openfablab_machines]`. `[openfablab_resources]` est un alias du dernier.
4. Activer les affichages souhaités et vérifier la page en visite anonyme.
   Vérifier les animations publiées, les disponibilités et motifs publics ;
   ni dossiers administratifs, ni notes internes, ni noms de participants.

Ces trois usages ont été vérifiés avec Reservations 2.15.3 au FougèresLab
après passage à OpenFabLab 2.16.0. Aucun changement de version du plugin.
