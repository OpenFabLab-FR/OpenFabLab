# Liaison sortante — architecture introduite en 2.8.1

**Version actuelle : application/plugin 2.8.2, protocole 4 / révision 3, SQLite 17.**
L'architecture sortante décrite ici est conservée ; les mentions de révision 2
et de schéma 16 ci-dessous documentent la 2.8.1 historique. Pour les demandes
sans compte et la compatibilité actuelle, lire le [guide 2.8.2](reservations-2.8.2.md).

## Un seul moteur, aucun port entrant

Internet → WordPress : catalogue et dépôt d'une demande. OpenFabLab → WordPress : relève HTTPS signée, traitement local, retour du résultat. **WordPress n'appelle jamais OpenFabLab.** La borne et l'administration utilisent directement le même moteur sans WordPress. Chaque participant réel consomme une place ; un groupe est confirmé ou mis en attente entier. Les règles familiales et FIFO de la 2.8.0 sont inchangées.

Le protocole 4 négocie explicitement `outbound_actions_v1`. Application et plugin 2.8.1 sont nécessaires pour ce flux. Une ancienne version échoue clairement, sans moteur de capacité de secours. Le secret existant est conservé ; il n'est jamais transmis au navigateur.

Le plugin livré supprime les anciens moteurs, classes, routes de synchronisation, pages d'action et tâches de réservation WordPress. Aucune route de secours ne peut attribuer une place. Seuls trois stockages techniques sont gérés : nonces anti-rejeu, catalogue et actions. Les cinq anciennes tables métier WordPress sont retirées à l'installation uniquement si elles sont toutes vides, sous verrou ; une table non vide entraîne leur conservation intégrale, sans lecture ni moteur associé. Le secret et les demandes du relais ne sont jamais effacés par cette opération. Les anciens scénarios restent dans les fixtures de développement, exclues des deux ZIP.

L'administration présente Normal en priorité, Test et le diagnostic dans des sections repliables. Le secret n'est jamais affiché ; sa régénération exige un POST administrateur confirmé, sans demande/résultat encore utilisable. La clé est téléchargée en fichier privé puis doit être enregistrée manuellement dans OpenFabLab. La révision technique `2.8.1-relay2` permet la mise à jour d'une première candidate 2.8.1 ; le protocole reste 4, avec `transport_only_v1` et `relay_revision: 2`.

## Deux cadences distinctes

Le catalogue est actualisé toutes les **90 secondes** par défaut, avec le réglage existant par demi-minute. Les demandes/actions sont relevées toutes les **15 secondes**, réglage entier **10 à 60 secondes**. Une relève vide ne reconstruit ni catalogue ni annuaire. Un réseau indisponible peut augmenter le délai : « demande reçue » ne signifie jamais « réservation confirmée ». Un catalogue vieux de plus de 15 minutes ne permet plus de nouvelle réservation ; le moteur recontrôle toujours la capacité actuelle.

## File et reprise

Deux tables WordPress InnoDB stockent le catalogue public et les actions techniques ; une troisième conserve les nonces anti-rejeu. Aucun annuaire ni compteur de places autonome n'est créé. Chaque dépôt porte une clé propre à la session et à l'environnement. Les charges privées sont chiffrées AES-GCM avec une clé dérivée du secret et du sel WordPress. Une relève prend un bail de 60 secondes. Après une panne ou une réponse perdue, le bail permet une nouvelle livraison.

Côté SQLite, le changement métier et son reçu sont validés dans **une seule transaction**. Une répétition restitue le reçu sans réserver ni annuler deux fois. WordPress ne marque le résultat que pour le bon identifiant, contenu, environnement et bail ; une réponse HTTP seule n'est pas un acquittement métier.

Les charges de demandes expirent après 24 heures et sont effacées après acquittement. Les résultats d'identification, de coordonnées et de lecture de lien sont consultables 20 minutes ; les autres résultats 24 heures. Les tombes techniques expirent après sept jours dans WordPress. La maintenance est effectuée lors des relèves et par la tâche WordPress de cinq minutes lorsqu’elle fonctionne ; si celle-ci est désactivée et le moteur hors ligne, l’expurgation physique attend leur reprise, mais le suivi public refuse les résultats expirés. SQLite conserve les reçus d'idempotence, mais expurge les noms/jetons des résultats d'identification ou de refus après 20 minutes, lors de sa maintenance périodique (5 minutes). Sauvegardes privées : accès restreint et politique de conservation de la structure. Une rotation du secret ou du sel WordPress pendant des demandes en vol exige une procédure de maintenance ; ne pas les régénérer arbitrairement.

## Identification et sécurité

Le catalogue ne contient ni répertoire familial ni coordonnées. Après vérification par le moteur de l'identifiant et d'un contact concordant, seule une sélection autorisée, opaque et temporaire est renvoyée à cette session. Ce contrôle n'est **pas une preuve de possession du contact** ; le risque résiduel de contacts connus doit être évalué par la structure. Le serveur revalide les choix, les responsables, l'âge et la capacité.

HTTPS, cookie Secure/HttpOnly/SameSite, contrôle d'origine, jeton CSRF temporaire et quotas protègent les dépôts publics. Les requêtes et réponses privées portent HMAC, horodatage et nonce ; les redirections vers un autre serveur sont refusées. Aucun CORS permissif ni secret public. Les environnements `production` et `test` sont validés à chaque étape, jamais déduits du nom de page. Test n'envoie pas d'e-mail réel.

## Liens personnels d'e-mail

Le mode automatique utilise WordPress lorsqu'il est configuré et que la liaison correspondante est vérifiée. Le mode WordPress l'impose ; le mode local conserve les routes historiques pour une installation sans plugin disposant d'un accès contrôlé adapté. Une adresse publique du NAS n'est pas nécessaire en mode WordPress et n'est jamais ouverte automatiquement.

Le lien WordPress utilise une page dédiée `?openfablab_action=1` et un jeton signé dans le **fragment** (`#ofl=…`), absent des journaux HTTP et du Referer. La page est sans analytics, sans cache, sans indexation ni référence transmise. JavaScript retire le fragment de la barre d'adresse puis conserve le jeton en session au maximum 20 minutes pour la reprise. Il ne stocke pas les coordonnées ou la liste familiale. Les anciens liens/tokens OpenFabLab sont préservés.

Un GET de scanner n'annule et n'accepte rien. Une action exige une case explicite et un POST protégé, est déposée dans la file puis validée par OpenFabLab. L'expiration d'une proposition est jugée au moment du **traitement par OpenFabLab**, sans acceptation rétroactive. Le transport différé et une panne peuvent donc faire expirer une réponse déposée tardivement ; l'interface doit distinguer réception et décision réelle. SMTP reste côté OpenFabLab ; une coupure après acceptation par un serveur SMTP peut entraîner un doublon d'e-mail, sans doublon de réservation.

## Pages et limites

Normal : `[openfablab_reservations environment="production"]`. Test : `[openfablab_reservations environment="test"]`. Vérifier explicitement le shortcode de chaque page : le nom de la page ne détermine jamais son environnement. Tester sur une installation isolée avant de modifier un site réel.

Le parcours public WordPress nécessite JavaScript. Recharger reprend une demande encore connue de la session ; une demande dont le dépôt initial n'est pas arrivé doit être refaite après réidentification. Les modifications de participants restent dans l'administration avec les droits et contrôles existants : aucune nouvelle API publique générale n'est ajoutée. Les anciennes routes du plugin ne sont plus enregistrées et renvoient 404 ; les anciens liens OpenFabLab 2.8.0 restent lus par le moteur natif.

## Migration et retour arrière

Voir [la procédure de mise à jour](upgrade.md). Sauvegarder à froid **PRE schéma 15**, tout le persistant et WordPress avant changement. La migration vers 16 ajoute uniquement les tables techniques et réglages. Avant réouverture, un retour exige le runtime 2.8.0 **et** la PRE 15 correspondante ; ne jamais exécuter 2.8.0 sur une base 16. Après nouvelles écritures, préserver l'état et décider humainement d'une reprise. Les procédures propres à chaque installation restent privées et séparées de la distribution publique.
