# OpenFabLab 2.15.0 — guide de la candidate

Candidate locale issue de la stable publique 2.14.4. Elle n’est pas publiée ni
installée par l’agent de développement. SQLite 26 ; plugin facultatif 2.15.0 ;
protocole 4/révision 3 inchangé. Tous les modules restent facultatifs.

## À l’accueil de l’administration

**Résumé** affiche quelques compteurs, À traiter, Prochainement et les dernières
informations, selon les modules et droits. Les trente derniers passages restent
repliés. Une facture envoyée depuis plus de trente jours est présentée comme
« à vérifier » selon la règle disponible, pas comme une échéance contractuelle
inventée. Un devis à suivre n’est pas présenté comme envoyé sans preuve.

La loupe de l’en-tête, `⌘ K` ou `Ctrl K`, recherche localement les usagers,
ressources, activités, réservations et interventions. Devis/factures sont réservés
aux administrateurs. Les modules désactivés ne sont pas interrogés. Les résultats
ne contiennent pas de coordonnées ; Échap ferme et efface la saisie.

## Locations et participations

Une réservation future ne signifie pas que le matériel est sorti. Utiliser
**Remettre le matériel**, puis **Confirmer le retour** à sa restitution réelle.
La fin prévue ne rend jamais une ressource disponible automatiquement. Un retour
en retard reste signalé ; une panne ou maintenance reste prioritaire et n’est
pas écrasée par le retour. Les contrats et réservations liés ne sont comptés
qu’une fois. Pour un contrat ancien sans usager rattaché, effectuer un choix
explicite : aucune correspondance n’est déduite d’un nom ou d’une adresse e-mail.

Les sections de la fiche usager restent repliées et respectent les droits.
Une annulation n’est pas une absence. L’absence n’est comptée qu’après l’activité
et lorsqu’elle a été effectivement renseignée ; une présence inconnue le reste.
Un indicateur saisi prématurément sur une activité future ne prouve pas sa tenue.
L’administrateur peut limiter temporairement les nouvelles réservations avec
dates, motif et révocation tracés. Aucune sanction automatique, aucun blocage
du pointage au FabLab. Une location passant minuit s’affiche dans la bande
multijours du calendrier, avec ses heures exactes dans les détails.

## Une seule fiche par ressource

**Activités → Ressources** rassemble les informations générales, la disponibilité,
la publication, les réservations et locations, les interventions, les rappels,
le QR Code et les documents. Les sections se replient ; le calendrier et la
recherche ouvrent directement la section utile. Les anciennes adresses de
maintenance restent utilisables. Les modérateurs conservent leurs droits
d’entretien et de remise/retour ; tarifs et actions sensibles restent administratifs.

La visibilité publique est un choix indépendant : case décochée, aucune publication
sur la borne, les fiches QR ou WordPress. Une ancienne permission limitée à un seul
écran n’est pas élargie par la mise à jour. Les valeurs historiques restent tracées.
WordPress reçoit un remplacement complet du catalogue au prochain échange réussi ;
actualiser ensuite la page. Les notes internes et bénéficiaires ne sont pas publiés.

Choisir **Disponible** pour l’usage habituel au FabLab ou **Disponible à la location**
pour un équipement à prêter/louer. Ce choix ne rend pas la ressource publique,
n’active pas sa réservation et ne change aucun prix. Une remise effective la rend
En prêt, puis le retour confirmé rétablit son mode habituel ; panne et maintenance
restent prioritaires. Les anciennes ressources gardent Disponible par défaut.

Le classement des ressources est alphabétique naturel, indépendant de leur état :
accents et casse ignorés, Machine 2 avant Machine 10. L’ordre manuel des catégories
reste conservé. Archiver/restaurer et supprimer sans dépendances restent protégés.

## QR et tutoriels

Dans **Réglages → Ressources et maintenance**, définir l’adresse HTTPS effective
du service. L’adresse utilise l’UUID existant, sans secret ni droit intégré ; elle
ne change pas lors d’un renommage. La publication des fiches QR est facultative
et désactivée initialement. Elle respecte aussi la visibilité de chaque ressource.
L’équipe retrouve ses actions après authentification, avec retour sur la ressource.

Importer des PDF dans **Documents et tutoriels** : titre, langue et choix public
ou équipe. Limites : 16 Mio et 200 pages, validation isolée, refus des PDF chiffrés,
scripts, actions et pièces jointes. Une empreinte identique réutilise le document
sans élargir sa visibilité. On peut l’associer à plusieurs ressources. Remplacer
un document partagé conserve ses liens et demande confirmation. Retirer une
association ne supprime pas les historiques de la ressource.

Les documents sont conservés dans les données persistantes et inclus dans les
sauvegardes complètes. Le lecteur natif conserve la mise en page, le paysage,
le zoom et toutes les pages. Les PDF internes restent protégés, même si leur URL
est connue. Lire un tutoriel ne remplace pas la formation ou l’habilitation.
Ne rendre public qu’un document que votre structure a le droit de diffuser.

## Langues, réglages et premier lancement

FR, EN, DE, ES et FI utilisent des catalogues intégrés, sans connexion à un
traducteur. Les noms, titres personnalisés et modèles d’e-mails ne sont pas
traduits automatiquement. Les préférences existantes sont conservées. Sur une
borne partagée, le retour à la langue principale et le masquage du sélecteur
restent disponibles. La caméra QR conserve sa surface utile.

Huit groupes rangent les réglages par usage, sans supprimer les options. Les
formulaires sont indépendants. L’assistant apparaît automatiquement uniquement
sur une vraie installation neuve après le PIN initial. **Enregistrer et reprendre
plus tard** conserve les champs valides ; le rouvrir volontairement sur une
ancienne installation ne réinitialise pas ses préférences.

## Mises à jour et recette

Lire [l’agent séparé](update-agent.md), [la migration](upgrade-2.15.0.md) et
[WordPress](wordpress-2.15.0.md). La candidate initiale demande une installation
manuelle contrôlée ; l’agent facultatif est ensuite autorisé une fois par le
responsable du serveur. Le web ne reçoit ni identifiants DSM ni socket Docker.

Tests locaux sur données fictives : SQLite, fichiers, restauration, socket Unix,
HTTP Gunicorn et navigateurs sont réels. Docker/DSM, transport WordPress et caméra
sont modélisés. Aucun NAS n’est certifié par ces tests. Les traductions nécessitent
encore une relecture d’usage, idéalement par des locuteurs natifs. Avant installation,
effectuer uniquement le contrôle DSM fourni puis examiner son rapport.
