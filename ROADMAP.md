# OpenFabLab — Roadmap et conception future

Cadrage du 4 octobre 2026. Document de travail, **pas une fonctionnalité disponible en OpenFabLab 2.7.1**. Les propositions ci-dessous ne constituent pas un engagement de version ; voir la [version stable actuelle](README.md).

## Familles, mineurs et personnes rattachées

**Statut : orientation fonctionnelle demandée, architecture proposée, décisions métier encore ouvertes.** Aucune version cible attribuée : une évolution 2.7.x ultérieure ou une version plus importante sera choisie après estimation du modèle de données. Aucun engagement pour une 2.7.2.

Périmètre de ce chantier futur : documentation et conception seulement. Il n’ajoute aucune fonction au runtime 2.7.1 ni au plugin Reservations 2.7.0 ; il n’impose aucune nouvelle migration ou modification des archives approuvées.

### 1. Objectif et rôles

Permettre une réservation compréhensible pour une famille, sans transformer chaque enfant en compte usager complet. Une seule demande regroupe les personnes concernées et rend leurs rôles explicites.

| Notion | Fonction cible |
| --- | --- |
| Compte OpenFabLab | Compte usager existant, avec ses fonctions propres : identifiant, QR Code, passages. Pas de création automatique pour un enfant. |
| Responsable de réservation | Personne qui effectue la demande et reçoit les informations. Peut être le titulaire du compte ou un visiteur identifié pour cette réservation ; ne participe pas nécessairement. |
| Profil participant | Identité minimale d'une personne susceptible de participer, éventuellement reliée à un compte existant. |
| Personne rattachée / enfant | Profil participant géré par un titulaire autorisé. Pas d'identifiant public, de QR Code ni d'historique autonome imposés. |
| Participant | Personne prenant réellement part à l'animation. Être participant autonome ne signifie pas être majeur. |
| Adulte accompagnateur | Personne accompagnant un ou plusieurs participants selon les règles de l'animation. Peut être usager, visiteur, responsable de réservation ou autre adulte. |

Une personne peut cumuler des rôles sans être dupliquée. Un rattachement de profil n'établit pas automatiquement une autorité parentale ; les permissions et responsabilités doivent être définies. Les exemples ci-dessous sont fictifs.

### 2. Autonomie, âge et accompagnement

- Réglage de structure : **« Âge minimal sans accompagnateur »**, valeur par défaut proposée **15 ans**, modifiable par chaque FabLab. Réutiliser le réglage existant d'accompagnement plutôt que créer une deuxième valeur concurrente.
- Sous ce seuil : **accompagnateur requis**. À partir du seuil : **participant autonome**, sans accompagnateur obligatoire. Un jeune de 15 à 17 ans ne devient jamais « majeur » dans les données ou l'interface.
- La qualité d'adulte accompagnateur est contrôlée séparément : franchir le seuil d'autonomie ne suffit pas à devenir accompagnateur. Définir les critères d'éligibilité et les exceptions autorisées avant implémentation.
- Aide dynamique : « Pour les participants de moins de {{age_autonomie}} ans, un adulte accompagnateur doit également être inscrit. » Intitulé : « Accompagnateur requis » puis « Ajouter l'adulte accompagnateur ».
- L'âge d'admission à une animation et le seuil d'autonomie sont deux règles différentes. Être accompagné ne dispense pas des restrictions d'admission de l'animation.
- Calculer l'âge à la date de l'animation, selon une convention explicitement choisie : les fiches actuelles utilisent une année de naissance, qui ne permet pas de connaître l'âge exact avant/après l'anniversaire. Décider si elle suffit ou si une date complète est nécessaire aux cas limites ; ne jamais inventer de date à partir d'une année. Prévoir le cas d'un âge inconnu.
- Réutiliser les paramètres d'animation existants. Décider de l'héritage du réglage de structure et des éventuelles dérogations par animation, sans réécrire les configurations anciennes.

Exemples avec un seuil configuré à 15 ans et un âge établi selon la convention retenue : 10 ou 14 ans → accompagnateur obligatoire ; 15 ou 17 ans → accompagnateur facultatif, participant toujours mineur. « Pour un enfant » peut donc conduire à une participation autonome.

### 3. Parcours cible, progressif et simple

1. Choisir l'animation.
2. « Pour qui souhaitez-vous réserver ? » : **« Pour moi » / « Pour un enfant »**.
3. Participant : pour soi, reprendre le parcours usager/visiteur ; pour un enfant, choisir un profil déjà rattaché au compte ou proposer l'ajout si autorisé. Demander seulement prénom, nom, information de naissance retenue et informations nécessaires à l'animation.
4. Si requis, identifier l'adulte accompagnateur : « Moi », usager existant, visiteur ou autre adulte. Vérifier son éligibilité et les relations d'accompagnement ; ne pas le recréer s'il est déjà identifié.
5. Choisir le créneau éventuel. Toute capacité et toute présence d'accompagnateur concernent le créneau effectivement demandé.
6. Récapitulatif : responsable et contact, participants, accompagnateur(s), personnes accompagnées, créneau, places demandées et règle appliquée.
7. Confirmation ou **« Demande envoyée / en attente de confirmation »**, selon le résultat réel du moteur. Ne jamais confondre dépôt local et place garantie.

Si « Pour moi » concerne un participant sous le seuil, l'étape accompagnateur reste obligatoire. Un responsable visiteur doit pouvoir réserver sans être obligé de créer un compte famille ; la persistance de ses profils rattachés reste à décider.

Conserver les saisies au retour à l'étape précédente, afficher les erreurs près des champs, éviter les doubles envois et proposer une annulation compréhensible. Objectifs : tablette 10 pouces paysage, smartphone portrait, tactile, clavier/souris, focus visible et annonces accessibles. Formulaires progressifs utilisables sans dépendance JavaScript inutile ; ne pas exposer une liste d'enfants sur la borne par simple saisie d'un identifiant public.

### 4. Groupe de réservation et capacité

**Un groupe de réservation**, lié à une animation et éventuellement un créneau, comprend un responsable, des participants et des relations d'accompagnement. Les personnes peuvent avoir des lignes distinctes pour la présence, mais restent rattachées à la même demande.

Le moteur distingue **places demandées** et **places effectivement retenues** selon le statut : une demande de borne en attente de transmission ne garantit aucune place ; confirmation, offres de liste d'attente, annulation et expiration suivent les règles de capacité existantes.

- Un participant autonome seul : 1 place.
- Un enfant nécessitant un adulte : 2 places si l'adulte consomme une place, conformément à la règle actuelle à conserver par défaut.
- Deux enfants accompagnés par le même adulte : **ne pas multiplier automatiquement en deux paires / quatre places**. Si cet accompagnement partagé est autorisé et si chacun consomme une place, trois personnes distinctes représentent 3 places. Ce cas est une illustration, pas une autorisation déjà décidée.
- Un adulte présent seulement comme contact, sans participation ni accompagnement effectif, ne consomme pas de place.
- Un adulte qui participe et accompagne ne doit pas compter deux fois sur une même animation/créneau. Ne pas dédupliquer sur les seuls noms ou coordonnées partagés : une famille peut utiliser un même contact pour des personnes différentes.

À définir : accompagnement partagé autorisé, nombre d'enfants par adulte, éventuelle règle propre à l'animation, comptage des adultes non participants et créneaux compatibles. **Proposition de départ : confirmation et promotion de liste d'attente atomiques du groupe**, sans séparer enfant et adulte requis. Si une réservation partielle est souhaitée, la rendre explicite et préserver systématiquement l'accompagnement obligatoire. Définir aussi annulation partielle, remplacement d'accompagnateur, offres/expiration et FIFO des groupes de tailles différentes, sans contournement silencieux de la file.

### 5. Moteur commun borne / WordPress / administration

État de référence 2.7.1, inchangé : la borne enregistre une demande durable puis la transmet au moteur transactionnel WordPress pour la réservation publique ; les places affichées localement sont indicatives. L'administration possède aussi un parcours local d'ajout sur place, transmis ensuite à WordPress. **Ces parcours ne constituent pas encore un moteur famille unifié.**

Architecture cible proposée : un contrat métier commun « réservation de groupe », avec validation des rôles, âges, accompagnements, doublons, capacité, créneau, liste d'attente et annulations. Les trois interfaces collectent les données et affichent le résultat ; elles ne réimplémentent pas chacune ces règles.

- Maintenir **une seule autorité transactionnelle de capacité** pour chaque animation/environnement/créneau. Le moteur WordPress actuel est le point de départ pour les animations publiques ; tout déplacement futur de cette autorité nécessitera une décision et une transition explicites.
- La borne et l'administration utilisent la même commande de groupe que le parcours public. Hors réseau, une nouvelle demande est conservée localement mais n'est pas annoncée comme confirmée. Le cas des ajouts sur place doit être cadré, sans laisser deux moteurs confirmer indépendamment la dernière place.
- Prévoir identifiant de commande idempotent, identifiant stable du groupe et des personnes, validation transactionnelle, événements canoniques et réconciliation après réponse perdue. Les répétitions ne créent ni seconde famille ni seconde occupation de places.
- Versionner le contrat et négocier une capability famille avec le futur plugin. Python et PHP ne partagent pas directement une implémentation : centraliser l'arbitrage effectif dans l'autorité choisie et tester les mêmes scénarios de contrat dans les adaptateurs. Toute validation locale préalable reste indicative.
- Garder le sens sortant OpenFabLab → HTTPS signé → WordPress, sans nouveau port entrant. Ne transmettre que les identités/relations nécessaires aux réservations ; ne pas publier ni répliquer par défaut tout l'annuaire des enfants.
- Le futur WordPress propose lui aussi « Réserver pour moi / Réserver pour un enfant ». Avec un plugin sans capability famille, conserver le parcours classique et désactiver les nouveaux groupes sur les canaux incompatibles, sans perte silencieuse de leurs relations.

La convergence du parcours d'administration, l'accès aux profils rattachés et le protocole de groupe font partie du chantier futur, **pas d'une modification du plugin 2.7.0 actuel**.

### 6. Données et migration envisagées

Concepts nécessaires, sans imposer à ce stade de nouvelles tables ni un numéro de schéma :

- profil participant léger ; lien facultatif avec un compte usager existant ;
- rattachement à un ou plusieurs titulaires autorisés, avec droits explicites ;
- groupe de réservation : animation/créneau, responsable/contact, origine, statut et références de synchronisation ;
- membres du groupe avec rôles ; relation « cet adulte accompagne ces participants » ;
- instantané minimal de l'identité et de la règle d'autonomie/capacité appliquée pour comprendre la réservation historique.

Réutiliser autant que possible les identifiants de réservation et de groupe déjà présents ; étudier les limites du modèle actuel avant de le généraliser. Ne pas attribuer automatiquement un compte complet à un profil enfant, ni un lien familial à deux noms identiques. Une transformation ultérieure d'un profil participant en compte usager doit être volontaire, éviter les doublons et conserver les références utiles sans inventer des passages.

Migration future **additive, contrôlée et réexécutable**, avec sauvegarde complète préalable, vérifications d'intégrité/FK et comparaison des réservations/statuts/places. Préserver comptes, visiteurs, animations, demandes de borne, réservations WordPress, créneaux, listes d'attente et historiques. Ne pas convertir arbitrairement une ancienne paire participant/accompagnateur en famille ou en lien parental ; ajouter seulement les relations explicitement connues. Prévoir la coexistence des réservations anciennes et nouvelles. Un changement de seuil ne doit pas reclasser ni annuler automatiquement l'historique : définir séparément sa prise d'effet sur les réservations futures déjà enregistrées.

### 7. Administration, données personnelles et conservation

Présentation cible d'une seule réservation, exemple fictif : **Atelier Exemple — Responsable : Camille Exemple ; Participante : Rose Exemple, 10 ans ; Accompagnateur : Camille Exemple ; Places consommées : 2 ; Statut : confirmé.** Les listes de participants distinguent rôles et relations, personnes présentes et places occupées. La liste d'attente et les exports conservent le groupe, pas plusieurs demandes artificiellement indépendantes.

- Coordonnées du responsable suffisantes lorsque pertinentes : ni e-mail/téléphone propre à chaque enfant ni compte complet obligatoire. Pas de justificatif d'identité ajouté par défaut. Ne recueillir une date de naissance complète que si sa nécessité est retenue.
- Définir qui peut créer, consulter, modifier, rattacher/détacher et supprimer un profil. La vérification actuelle identifiant/contact ne prouve pas à elle seule l'autorité sur un enfant : choisir un contrôle adapté avant de permettre la gestion persistante des profils, avec refus génériques et protection contre l'énumération.
- Réserver identités/âges/relations à la famille autorisée et à l'équipe habilitée ; aucune liste publique de mineurs. Notifications au responsable ; ne pas ajouter de données d'enfants dans Discord par défaut.
- Inclure profils et relations dans les sauvegardes SQLite lorsqu'ils sont en base, et dans les sauvegardes complètes privées ainsi que les copies privées pour test. Les tests restent privés et leurs services externes neutralisés. Ces données métier ne sont pas un profil de branding/configuration de structure. **Aucune sauvegarde privée ne doit être publiée.**
- Prévoir un export autorisé des profils, rattachements et réservations groupées, sans exposer les autres familles. Documenter les durées de conservation distinctes des profils actifs, réservations et instantanés historiques, ainsi que l'effacement/anonymisation et leurs effets sur les relations, contacts partagés, exports et sauvegardes conservées.
- Ne pas supprimer en cascade un historique ou une référence de facturation sans examiner les obligations et règles de conservation applicables. La politique définitive est à valider avec la structure ; cette roadmap ne fixe pas une durée réglementaire.

### 8. Décisions à trancher avant implémentation

1. **Périmètre initial :** un enfant par demande ou plusieurs ; profils persistants seulement pour titulaires de compte, ou aussi pour visiteurs ; ajout public autorisé ou validation par l'équipe ?
2. **Gestion des rattachements :** qui peut accéder à un enfant, quel contrôle d'identité/autorisation, un ou plusieurs titulaires, transfert/détachement et lien futur avec un compte usager ?
3. **Âge :** année ou date complète, calcul à la date de l'activité, anniversaires/cas inconnus ; seuil de structure hérité ou dérogation par animation ; effet d'un changement sur les réservations à venir ?
4. **Accompagnateur :** critères d'adulte admissible, titulaire mineur réservant pour lui-même, accompagnateur visiteur/non participant et éventuelles exceptions auditées ?
5. **Capacité :** un adulte peut-il accompagner plusieurs enfants, combien, règle de structure ou d'animation ; consomme-t-il toujours une place ; accompagnement commun entre créneaux autorisé ?
6. **Cycle du groupe :** confirmation/attente indivisibles ou participation partielle explicite ; ordre FIFO, offres, annulation partielle, remplacement d'adulte et notifications ?
7. **Moteur et compatibilité :** autorité de capacité retenue, convergence des ajouts d'administration, commande idempotente, protocole/capability et ordre de mise à jour application/plugin ?
8. **Confidentialité :** informations réellement nécessaires, droits d'export/suppression, conservation des profils et historiques, traitement des copies et sauvegardes ?
9. **Extension ultérieure :** rester sur des profils enfants rattachés ou évoluer vers de véritables « comptes Famille », éventuellement pour d'autres personnes liées ?

### 9. Critères d'acceptation du chantier futur

Tester les mêmes règles sur borne, WordPress et administration : âges 14/15/17 au seuil par défaut, seuil modifié, anniversaire/âge inconnu, réservation pour soi sous le seuil, adulte uniquement responsable versus accompagnateur, deux enfants partageant un adulte, créneaux/capacité insuffisante, dernière place demandée simultanément, doublons et contact familial partagé, réponse réseau perdue/reprise, groupe en attente/offre/annulation partielle, ancien plugin et migration des réservations anciennes.

Vérifier accès aux profils et minimisation des notifications, sauvegardes/export/effacement cohérents, clavier et parcours tactile sur tablette et smartphone. Aucun test ne doit ajouter de famille fictive ou transmettre de données privées aux services de production.
