# Corrections OpenFabLab 2.8.6 — version stable

Correction ciblée de la 2.8.5 validée, distribuée avec tous ses apports depuis
la version publique 2.8.4, sans changement du moteur transactionnel,
du schéma SQLite 19 ou du plugin Reservations 2.8.5. Le numéro prévu 2.8.5.1 n’est
pas utilisé : la distribution et les sauvegardes exigent trois composantes.

## Recherche compacte des participants

Les deux sélecteurs, **Modifier les participants** et **Ajouter des participants**,
ne présentent pas de répertoire initial. Champ vide : invitation discrète, aucune
requête d’annuaire ni compteur de résultats. La recherche partielle, normalisée
pour les accents/la casse, et le code public sont conservés. 25 résultats au
maximum ; invitation à préciser au-delà. Après effacement, les résultats
disparaissent, les sélections restent et une réponse périmée ne peut réafficher
une ancienne recherche. JavaScript est nécessaire à ce composant administratif.
Les droits Administrateur/Modérateur et les règles du moteur restent inchangés.

## Notifications utiles, identité sur choix explicite

Titre réel et date/horaires français sont proposés par défaut, ainsi que les
participants et les places restantes. Prénom, nom complet et initiale restent
facultatifs et désactivés. Prénom + initiale donne « Camille E. » ; prénom + nom
complet donne « Camille EXEMPLE ». Ces options ne dépendent pas de celles de
création d’usager. Les libellés principaux des événements sont personnalisables
en texte simple, sans variables : aucun lien, mention ou retour à la ligne.

Le réservant est le compte à l’origine de la demande, distinct des participants.
Pour une demande sans compte, seule l’identité fournie dans sa propre réservation
est utilisée ; aucun rapprochement de noms ni nouvelle fiche. En cas d’identité
indisponible, la ligne est omise. Les autres membres de la famille ne sont pas
listés dans Discord. Une annulation partielle est explicitement indiquée et
compte les seules places effectivement libérées ; annuler une attente en libère
zéro. Une animation complète reste un événement global, sans identité. Les places
restantes reflètent le moment de l’envoi, la capacité atteinte son instantané.

E-mail, téléphone, adresse, naissance, identifiant public, jeton et lien personnel
ne sont jamais ajoutés aux messages. Les erreurs SMTP/synchronisation n’affichent
pas d’identité ou de titre susceptible de contenir une information personnelle.
Ne pas renseigner de données personnelles dans les libellés génériques.

Le journal Discord ne copie pas de nom ou de contact : les informations sont
résolues depuis les données de réservation et les instantanés d’e-mail durables
existants. Ceux-ci reçoivent seulement des compteurs/indicateurs nécessaires à
la notification, au sein de la même transaction, sans nouvelle table/colonne.
Les événements antérieurs sans instantané complet restent lisibles : une valeur
inconnue est omise, jamais inventée. Ils ne sont pas renotifiés rétrospectivement.

## Fiabilité et limites

Le déclenchement et la prise en charge post-commit restent ceux de la 2.8.5,
avec clés anti-doublon identiques et séparation Normal/Test. Discord ne permet
pas de garantir un envoi exactement une fois lorsqu’un accusé est perdu : comme
avant, une prise en charge ambiguë reste **incertaine** et n’est pas renvoyée
automatiquement. Le diagnostic de l’équipe reste nécessaire dans ce cas.

Les tests automatisés utilisent des données fictives et un webhook simulé. Ils
ont donné **93 tests Python, 371 contrôles Chromium/WebKit et 20 tests du lanceur
et des sauvegardes** réussis. Ce ne sont pas de nouvelles campagnes lors de la
publication. La version 2.8.6 et les notifications de réservation/annulation
Discord réelles ont ensuite été validées par l'exploitant sur une installation
Synology ; cette validation terrain est distincte des simulations locales.
Les résultats locaux
détaillés distinguent Chromium/WebKit, fenêtres mobile/tablette/desktop et
simulations Docker ; ils ne constituent pas des tests sur Safari matériel,
un téléphone réel ou une exécution DSM par l'assistant. Chaque autre structure
doit vérifier son installation avant ouverture. Aucun nouveau test de caméra
physique n'est revendiqué pour ces deux
corrections, le scanner étant inchangé.
