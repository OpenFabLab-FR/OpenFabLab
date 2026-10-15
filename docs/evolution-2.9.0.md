# OpenFabLab 2.9.0 — version stable

## Finitions intégrées à la stable — 15 octobre 2026

Correction du registre de préférences Discord pour « Liste d’attente complète » :
la case est maintenant enregistrée et relue comme les autres options, sans
changer les valeurs déjà choisies. Présentation de Fréquentation → Usagers
harmonisée : filtres compacts, indicateurs équilibrés, historique en tableau
adaptatif, aides repliables et pluriels corrigés. Les calculs sont inchangés.
L’encart technique de fin de page est retiré, ses précisions restent ci-dessous.
Préavis placé après Conservation automatique, modèle plus spacieux ; filtres
clients alignés et plafond personnalisé affiché seulement dans le mode adapté.

Application 2.9.0, **SQLite 20 conservé**, plugin 2.9.0 inchangé. Le correctif
sur une installation déjà en 20 ne rejoue aucune migration 19 → 20. Sauvegarder
PRE20 et runtime 2.9.0 courant ; après la première tentative publique, conserver
l’état en cas d’échec et préparer une reprise compatible 20, jamais une PRE19.
Les durées de conservation et le délai personnalisé de préavis (par exemple
14 jours) ne sont pas remplacés. Purge, SMTP et ordonnancement inchangés.

Cette version part de la stable publique 2.8.6. Application 2.9.0, SQLite 20
(migration additive depuis 19), plugin facultatif Reservations 2.9.0,
protocole 4/révision 3. Ne pas installer sans sauvegarde et validation locale.

## Liste d’attente

Le réglage général propose automatique (100 % de la capacité réservée), plafond
personnalisé de 0 à 100 000 personnes, ou sans limite. La désactivation reste
distincte. Chaque animation peut suivre ce réglage, le remplacer ou être sans
limite. En mode créneaux, le plafond s’applique par créneau, comme la capacité.

Le moteur compte les personnes en attente, pas les dossiers. Les familles
restent indivisibles. Une proposition en cours occupe temporairement les places
réservables, pas l’attente. Réduire un plafond conserve les inscriptions,
l’ordre FIFO et les propositions ; cela ne retire aucune personne existante.
L’admission est revérifiée sous le verrou transactionnel, y compris par l’équipe.

## WordPress et Discord

Le plugin 2.9.0 reçoit les états de disponibilité et le nombre de personnes en
attente après négociation explicite de `waitlist_limits_v1`. Le moteur peut
continuer à communiquer avec le plugin 2.8.5, mais celui-ci ne présente pas ces
nouveaux états. Le protocole reste 4/révision 3 : aucun format d’action, jeton ou
accusé de traitement n’a été changé. Aucun accès entrant au NAS n’est nécessaire.
Catalogue et relève restent indépendants ; leurs cadences enregistrées sont
conservées, notamment 90 et 15 secondes sur les installations configurées ainsi.

Les cartes affichent titre, date/horaires, disponibilité pastel, attente si
nécessaire, description, lien d’information puis bouton au pied. Un état fermé
pour une échéance n’est pas présenté comme une capacité atteinte. WordPress ne
décide jamais des places et ne promet pas une confirmation avant la décision.

Discord « Liste d’attente complète » est un événement indépendant, configurable
et durable. Il annonce les totaux de l’animation/créneau, sans identité. Un
nouvel épisode de saturation peut notifier après une libération, pas chaque
synchronisation. Les préférences existantes de confidentialité sont préservées.

## Fréquentation → Usagers

Recherche privée et bornée, sans annuaire préchargé. Usager, catégorie historique
de session ou ensemble ; 30 jours, 3/12 mois, totalité ou dates personnalisées.
Les visites comptent les arrivées de sessions dans la période. Les durées
terminées sont limitées au chevauchement réel avec la période ; une session
ouverte n’a aucune durée inventée. La moyenne porte sur les visites avec départ
enregistré. Les 10 derniers passages se chargent progressivement.

Jours de visite, temps par heure, carte thermique et évolution sont calculés
dans le fuseau de la structure. La comparaison utilise une période précédente
de même durée effective ; une base à zéro n’a pas de pourcentage.

Les cohortes reposent sur la première visite **enregistrée encore disponible**,
pas la création du compte. Les horizons de 30/90 jours incomplets sont exclus.
Les retours d’au moins une/trois visites supplémentaires sont collectifs, sans
classement. En dessous de trois usagers distincts, les graphiques collectifs
détaillés sont masqués ; sous trois usagers observables, les retours ne sont pas
détaillés. Aucun nouvel export, motif de visite ou suivi d’assiduité.

Les réservations à venir et la présence aux animations sont distinctes des
sessions. Seule une présence effectivement renseignée compte ; aucune présence
n’est inférée par simultanéité. Chaque compte participant a sa propre ligne.
Les listes d’animations individuelles sont bornées à 50 et les événements à
venir à un an. Pour les agrégats d’animations par catégorie, seule la catégorie
actuelle du compte est disponible : cette limite est explicitement affichée.

Les catégories historiques de session existaient déjà. Certaines anciennes
migrations ont complété des instantanés manquants sans provenance : le logiciel
ne prétend pas reconstituer les catégories anciennes avec certitude. Aucun nom
n’est reconstitué après anonymisation. Accès administrateur/modérateur seulement.

## Annuaire des clients

Catégorie facultative, distincte de celle des usagers. Sept libellés initiaux
personnalisables, ajout/renommage/archivage et filtre. Les anciens clients restent
sans catégorie tant qu’ils ne sont pas volontairement classés. Archiver conserve
les liens. Aucun contrat, abonnement, droit ou tarif n’est créé. Les anciens
devis/factures gardent leurs instantanés ; le profil exporte les catégories et
les anciens profils restent importables.

## Préavis facultatif d’effacement des coordonnées

Désactivé par défaut, 7 jours avant l’échéance existante (1 à 90 configurables).
Les durées de conservation restent celles de chaque installation ; les défauts
historiques du logiciel sont 2/3/5 ans. Le modèle texte accepte seulement
`{structure_name}`, `{date_suppression}` et `{contact_equipe}`. L’adresse encore
présente du compte reçoit le préavis via le fournisseur SMTP choisi par
l’administrateur ; aucun responsable familial ni tiers n’est utilisé par défaut.
Le modèle ne contient ni QR, identifiant, réservation, téléphone ou lien privé.

L’échéance utilise exactement le calcul historique de purge (Europe/Paris,
y compris le 29 février), puis s’affiche dans le fuseau de la structure. Une
nouvelle activité ou politique annule l’ancienne échéance. Aucun envoi après
effacement, aucune copie d’adresse ou contenu dans le nouveau journal, aucune
prolongation de conservation. Aucun nouveau e-mail de désactivation/suppression.

Le suivi agrégé est réservé à l’administrateur dans Gestion des données et ses
réglages : opérations prochaines, prochaine date, préavis envoyés/erreurs.
Les préavis sont traités un à un par la maintenance existante, avant la purge,
pour les seules échéances futures. Un transport en échec n’empêche pas la purge.
Un transport interrompu ou ambigu reste « incertain » et n’est pas renvoyé
automatiquement : privilégier l’absence de doublon plutôt qu’un envoi hypothétique.
L’effacement n’est jamais bloqué par SMTP et le journal ne conserve que des
références techniques, échéances et états. Les essais utilisent uniquement SMTP simulé.

## Migration et secours

La migration 19 → 20 ajoute les réglages de plafond, l’état technique de saturation,
les catégories de clients, leur rattachement facultatif et le journal minimal
du préavis de coordonnées ; les indicateurs réutilisent les sessions existantes.
Des index de lecture sont ajoutés. Aucune réservation, famille, facture, passage,
catégorie d’usager, secret ou durée de conservation existante n’est supprimé.

Conserver une sauvegarde complète PRE19 avec le runtime 2.8.6. Après migration,
une base 20 ne doit jamais être ouverte par un runtime 2.8.6. Un retour à PRE19
n’est possible qu’avant toute reprise publique, avec vérification d’absence de
nouvelles écritures. Après une première tentative publique, préserver l’état
et décider humainement d’une reprise compatible 20 ; jamais de restauration
destructrice automatique. Le paquet NAS privé est distribué séparément.

## Hors périmètre et limites

« Abonnements et crédits » reste une proposition future de la roadmap, sans
table, interface, débit ni contrôle d’entrée anticipé. Les tests locaux utilisent
des données fictives et des transports simulés. WebKit n’est pas un essai sur
iPhone physique ; les commandes DSM sont préparées, jamais exécutées par l’agent.
