# Anciennes installations : compatibilité et migration

Les noms CompteurFablab, compteur-fablab, compteur_fablab et CompteurPassage sont historiques. Une installation neuve utilise uniquement OpenFabLab, `openfablab.db` et le sous-dossier de sauvegarde `OpenFabLab`.

La résolution des chemins détecte une ancienne `compteur_fablab.db`. Ne pas créer une base vide si une ancienne base attendue est présente. Les routines existantes contrôlent et sauvegardent avant migration ; la source historique doit rester intacte. Préparer une copie contrôlée dans un **nouveau** dossier de données, jamais déplacer destructivement l'unique source.

Le réglage de sauvegarde exactement égal à `CompteurPassage` devient `OpenFabLab`. Une autre valeur, potentiellement personnalisée, reste inchangée. Cette conversion ne renomme, ne supprime et ne déplace aucun dossier ni sauvegarde historique.

Si l'ancien PIN Admin dépendait d'une constante d'une archive applicative sauvegardée, l'outil `python -m openfablab migrate-legacy-admin-pin --database <copie-base> --archive <archive-privee>` existe pour le dériver sur la **copie**. Il ne fournit pas de PIN par défaut. Vérifier au préalable l'équivalence avec la configuration réelle de l'ancienne instance ; en cas d'incertitude, arrêter. Ne pas publier l'archive historique, un PIN ou la sortie d'une inspection complète du conteneur.

La distribution publique ne contient ni banque, logo, tarif ni coordonnées historiques d'une structure. Les valeurs déjà enregistrées en base sont conservées. Si une très ancienne version dépendait de constantes jamais enregistrées, exporter/renseigner explicitement ces informations dans le stockage privé avant transition ; ne pas attendre du code public qu'il les devine. Préserver les ressources visuelles privées nécessaires aux anciens documents.

Une migration historique se prépare installation par installation avec sauvegarde, intégrité, FK, comparaison métier et rollback. Ce guide n'est pas un journal de production ni un script d'opérations spécifique à un NAS.
