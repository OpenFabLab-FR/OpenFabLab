# OpenFabLab 2.10.0 — abonnements, calendrier, alertes et sons

Base : stable 2.9.0. Migration additive SQLite 20 →21, sans modification des
usagers, familles, réservations ou factures existantes. Sauvegarde complète
privée indispensable. Module Abonnements et crédits désactivé par défaut.
La version stable inclut la corrective 1. Sons activés par défaut à 50 % uniquement pour les préférences
absentes. Toutes les valeurs déjà enregistrées, notamment un arrêt volontaire
ou un volume personnalisé, sont conservées. L’ancienne candidate ne distinguait
pas une valeur initialisée automatiquement d’un choix explicite : aucun réglage
existant n’est donc réactivé ou réinitialisé rétroactivement.
Les réglages enregistrés ne sont pas remplacés par les valeurs par défaut.

## Abonnements et crédits

Activer dans Réglages → Modules. L’espace dédié est réservé à l’administration.
La fiche usager ouvre ses droits. Recherche initialement vide, sans annuaire
chargé dans le navigateur. Désactiver conserve les données mais arrête les
contrôles, débits et notifications. Aucun droit n’est attribué automatiquement.

Une cotisation/adhésion de période est distincte d’un carnet consommable. Les
formules définissent librement nom, prix, durée, périmètre individuel ou familial,
unité et quantité. Prix et conditions sont conservés à l’attribution ; une
modification ou un archivage du catalogue ne change pas les droits précédents.

### Exemples de formules possibles

Les montants suivants sont purement illustratifs, choisis par chaque structure :
ce ne sont pas des tarifs officiels d’OpenFabLab.

| Exemple | Configuration |
|---|---|
| Cotisation individuelle à 30 €/an | Droit de période individuel, validité d’un an |
| Cotisation familiale à 50 €/an | Droit de période familial, bénéficiaires explicitement rattachés |
| Carnet de 10 demi-journées | Crédits individuels ou familiaux, quantité 10, plages locales configurées |
| Forfait de 5 crédits horaires | Crédits horaires, quantité 5, durée d’un crédit fixée à 60 minutes par exemple |

Les crédits horaires sont consommés selon la présence constatée : ils ne
réservent pas automatiquement cinq créneaux du calendrier. Les prix sont une
information de gestion, pas un encaissement. **Aucun paiement bancaire en ligne,
prélèvement automatique, renouvellement payant automatique, Stripe ou PayPal.**

La fin est inclusive dans le fuseau de la structure. Un mois débutant le 31 janvier
est borné à fin février ; une année débutant le 29 février finit le 28 février
suivant. Un renouvellement commence après la période courante ou à la date
demandée si elle est ultérieure. Pas de renouvellement ni paiement automatique.

Les bénéficiaires familiaux sont explicitement sélectionnés parmi les vrais liens
enregistrés. Aucun compte n’est fusionné, aucun nouveau membre couvert d’office.
Le solde d’un carnet collectif est commun ; chaque débit est sérialisé dans la
transaction du passage. L’équipe choisit le carnet principal ; pas de débit
simultané de carnets d’unités hétérogènes ni de choix financier public.

| Unité | Décompte |
|---|---|
| Passage | À l’arrivée enregistrée ; retour sans nouveau débit dans le délai configurable |
| Séance | Une session de fréquentation, pas une réservation d’animation |
| Horaire | Au départ réel, durée UTC en secondes ; durée d’un crédit configurable |
| Demi-journée | Au départ, une fois par plage locale réellement traversée, par personne et carnet |

Exemple : arrivée à 9h30, départ à 12h = une plage matin. Revenir dans cette même plage
ne la débite pas à nouveau. Traverser matin et après-midi consomme deux plages.
Les plages locales sont configurables, sans chevauchement, sur la même journée.
Une session excessivement longue est signalée plutôt que facturée aveuglément.

Si la durée dépasse le solde : débit du disponible et complément à régulariser,
sans solde négatif. Un mode alternatif permet une régularisation entière manuelle.
**Le départ n’est jamais refusé pour un droit ou un solde insuffisant.** Une
clôture automatique ou une session ouverte n’invente pas de durée payante.
Vérifier les heures dans Fréquentation puis valider le décompte. Les corrections
de dates demandent une régularisation explicite. Supprimer une session n’efface
pas les mouvements : une compensation motivée est nécessaire si approprié.

Historique : date, quantité, solde, origine système/administrateur, session et
motif. Les corrections et annulations ajoutent des écritures, sans réécriture
silencieuse. Transactions, clés stables et hashes protègent les reprises/concurrences.

### Contrôle et confidentialité

Mode informatif par défaut ; avertissement autorise l’entrée ; strict refuse
seulement la validation d’une nouvelle entrée non éligible, jamais la reconnaissance
du compte ni une sortie. La borne ne pilote pas une porte. La structure choisit
si elle exige période, crédits ou les deux. Exemptions de catégories explicites,
aucune catégorie prédéfinie privilégiée ; exemption individuelle motivée.
Pas d’API publique de soldes ni d’historique financier affiché sur la borne.

Le rattachement explicite à un dossier existant réutilise la facturation. Un droit
attribué ne prouve pas un paiement ; aucune facture ni écriture bancaire automatique.
Devis, taxes et règlements restent dans le moteur de facturation existant.

SMTP et Discord sont facultatifs et indépendants : échéance proche/expirée,
solde faible/épuisé, régularisation. Confirmations de recharge/renouvellement
facultatives, jamais de fausse confirmation de paiement. Modèle personnalisable :
`{structure_name}`, `{evenement}`, `{nom_formule}`, `{date_expiration}`,
`{credits_restants}` seulement. Le destinataire SMTP est l’adresse actuelle du
titulaire, jamais une adresse familiale déduite. Aucune coordonnée copiée dans le
journal ni durée de conservation prolongée. Discord administratif reste générique,
sans nom, solde individuel, téléphone ou e-mail. Envoi ambigu : pas de renvoi aveugle.

## Discord : alertes de synchronisation

Réglages → Notifications : 10 minutes par défaut, 0 = immédiat. Une coupure résolue
avant le seuil ne produit aucune alerte. Une panne persistante produit une alerte
par incident, regroupant catalogue et relève. États durables séparés Normal/Test ;
la politique existante de non-envoi Discord en Test est conservée. Rétablissement
facultatif, uniquement après une alerte réellement envoyée. Les erreurs critiques
de validation/protocole restent immédiates. Aucun intervalle ni traitement de
réservation n’est retardé.

## Calendrier : notes internes

Administrateur et modérateur : ajout, modification, suppression par texte vidé,
dans la fenêtre d’une occurrence. Texte simple, maximum 2000 caractères, petit
indicateur. Une note sur un OpenLab ne se répète pas les semaines suivantes.
Elle ne change ni fermeture ni réservation. Jamais dans WordPress, ICS, e-mails,
Discord ou flux public. Base et sauvegarde complète restent privées.

## Retour sonore de la borne

Réglages → Borne et horaires. Activé par défaut, volume initial 50 % pour les
préférences absentes ; valeurs déjà enregistrées conservées. Classique,
Halloween, Noël ; automatique reprend le thème visuel sélectionné. Autres thèmes
→ classique, sans second calendrier. Panneau de tests volontaires, aucun son à
l’ouverture des réglages. Volume choisi commun à tous les sons.

- Usager/visiteur : clic de sélection ; Gestion : ouverture, pas authentification.
- Arrivée : tonalités ascendantes ; départ : descendantes ; visiteur : carillon.
- Erreur : signal neutre ; avertissement de droit uniquement si le module le justifie.
- Aucun son par chiffre. Confirmation positive seulement après transaction validée.

Un jeton temporaire et un reçu transactionnel évitent le double pointage et la
double confirmation d’une requête réémise. Aucune copie de nom ou coordonnées.
Web Audio synthétique local : pas de microphone, flux, CDN, fichiers audio ou
bibliothèque tierce. Code sous la licence du projet, pas de licence sonore tierce.
Moteur non initialisé si coupé ; geste volontaire requis, restrictions du navigateur
respectées. Une panne audio ne bloque jamais le pointage. Navigation sans attente
audio : certains appareils peuvent couper un son en changeant de page. Confirmer
volume et audibilité sur la vraie borne ; un navigateur automatisé ne valide pas
un haut-parleur physique. Les confirmations visuelles sont toujours conservées.

## Compatibilité et secours

Sauvegarde PRE20 complète + image/runtime 2.9 conservés ; contrôle d’intégrité et
clés étrangères avant/après, POST21. Tester la restauration en instance isolée,
transports neutralisés. Ne jamais ouvrir une base21 avec 2.9. Après une tentative
de démarrage public, ne jamais restaurer automatiquement une ancienne base :
arrêt prudent, état conservé et décision humaine.

Plugin facultatif Reservations **2.9.0 inchangé**, protocole 4/révision 3,
`waitlist_limits_v1`. OpenFabLab seul attribue les places, HTTPS exclusivement
sortant, aucun port entrant à ouvrir. Les réglages/cadences15s et90s existants sont
conservés. Aucun accès ou changement de production pendant ce développement.
