# OpenFabLab Reservations 2.15.2

Le plugin facultatif fonctionne avec OpenFabLab 2.15.1 et 2.15.2.
Le protocole reste 4, révision 3. Les environnements Normal et Test
restent séparés ; les shortcodes et les règles de publication ne changent pas.

## Mettre à jour sans désinstaller

1. Télécharger `openfablab-reservations-2.15.2.zip` et vérifier son SHA-256
   depuis la [release officielle](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.15.2).
2. Sauvegarder WordPress. Dans **Extensions → Ajouter une extension → Téléverser
   une extension**, sélectionner le ZIP puis remplacer l’extension existante.
   Ne pas désinstaller le plugin ni modifier la clé de synchronisation.
3. Vérifier les connexions Normal et Test et les pages qui contiennent des
   shortcodes. Pour une première installation, voir le
   [guide de configuration et des shortcodes](wordpress-2.15.0.md).

## Catalogue des ressources

Le badge de disponibilité précède le nom. Il conserve un libellé lisible :
vert pour **Disponible**, turquoise pour **Disponible à la location**, indigo
pour **En prêt** ou **Retour en retard**, ambre pour **En maintenance** et
rouge pour **Hors service**. Un motif ou une date estimée n’apparaît que
si OpenFabLab les publie.

Dans **Réglages → OpenFabLab Reservations → Calendrier, machines et langues
publiques**, la case **Afficher la catégorie des ressources** est indépendante
du titre de la liste. Une mise à jour conserve l’affichage précédent des
catégories ; une installation neuve les masque par défaut. Ce réglage n’a
aucun effet sur les données ou les filtres de catégorie.

Dans Gutenberg, utiliser des blocs **Code court** pour les composants :

```text
[openfablab_reservations environment="production"]
[openfablab_calendar environment="production" view="week"]
[openfablab_machines environment="production"]
```

Si activé, un seul sélecteur de langue pilote ces composants sur la page :
FR, EN, DE, ES et FI. Les noms et descriptions personnalisés ne sont pas
traduits automatiquement.
