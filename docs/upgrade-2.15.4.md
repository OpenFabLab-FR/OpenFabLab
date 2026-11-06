# Référence : mise à jour vers OpenFabLab 2.15.4

Cette étape n’a pas de release publique distincte. Voir le
[parcours vers la version stable 2.15.5](upgrade.md).

Depuis une V2.15.3 avec l’agent connecté, allez dans **Réglages → Système et
sauvegardes → Mises à jour → Importer un ZIP**. Importez le ZIP applicatif
sans le décompresser, vérifiez son empreinte et cliquez sur **Vérifier le ZIP**.
L’écran doit annoncer **2.15.4 · SQLite 27 → 28**. Confirmez hors séance.

Après reconnexion, rechargez la page. Vérifiez **V2.15.4**, `UPDATE_SUCCESS`,
et la présence des sauvegardes **PRE27** et **POST28**. En cas d’erreur,
conservez le rapport et les sauvegardes. Ne redémarrez pas la V2.15.3 sur une
base au schéma 28. L’agent installé et le plugin WordPress Reservations 2.15.3
ne sont pas à remplacer.

## Maintenance planifiée

Dans la fiche d’une ressource, ouvrez **Maintenance planifiée → Planifier
une maintenance**. Avec les deux heures, une intervention courte apparaît
dans la grille. Sans heures, la date de fin est incluse. Cochez **Dates
prévisionnelles** tant que le créneau n’est pas confirmé. Un créneau ne
change ni l’état de la ressource ni ses réservations et n’est pas publié sur
WordPress. Le retour estimé reste distinct du créneau planifié ; un retour
sans date n’est pas projeté au-delà du dernier jour observé.

Les rappels restent indépendants : une échéance dépassée est affichée en
retard sans être marquée comme traitée. Discord conserve l’envoi éventuel au
jour prévu, sans rattrapage d’anciennes échéances.
