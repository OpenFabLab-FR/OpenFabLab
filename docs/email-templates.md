# Modèles d'e-mails WordPress

Dans **Réglages → OpenFabLab Reservations → Modèles d'e-mails**, personnaliser sujet/corps des six modèles : confirmation, inscription en liste d'attente, place disponible, premier rappel, deuxième rappel, confirmation d'annulation. Texte brut UTF-8, sans exécution de PHP ou HTML. Les variables inconnues sont signalées.

Les modèles et la signature commune appartiennent au site WordPress concerné, pas au serveur du FabLab. Nom/e-mail expéditeur, Répondre à, préfixe Test et lien de confidentialité restent configurables. Les valeurs distribuées sont génériques.

Variables proposées dans l'interface : `{{first_name}}`, `{{last_name}}`, `{{participant_name}}`, `{{public_id}}`, `{{public_id_or_not_provided}}`, `{{animation_title}}`, `{{date}}`, `{{time}}`, `{{duration_minutes}}`, `{{slot_details}}`, `{{minimum_age}}`, `{{accompaniment_age}}`, `{{age_rule}}`, `{{cancel_url}}`, `{{offer_url}}`, `{{offer_deadline}}`, `{{signature}}`. Utiliser celles disponibles pour le modèle choisi.

`{{public_id_or_not_provided}}` donne « non renseigné » en l'absence d'identifiant. `{{slot_details}}` donne une ligne de créneau uniquement en mode créneaux ; aucune ligne superflue pour une animation classique. La durée usager n'inclut pas le battement.

Exemple générique de confirmation :

```text
Bonjour {{first_name}} {{last_name}},

Réservation confirmée : {{animation_title}}
Date et heure : {{date}} à {{time}}
{{slot_details}}
Durée estimée : {{duration_minutes}} minutes
Participant : {{participant_name}}
Identifiant : {{public_id_or_not_provided}}
Âge minimum : {{age_rule}}

Vous ne pouvez pas venir ? Annulez ici :
{{cancel_url}}

{{signature}}
```

Prévisualiser avec les données fictives intégrées, puis envoyer un test explicite vers votre adresse d'administration si souhaité. Aucun test ne doit utiliser une réservation réelle. Le reset d'un modèle demande confirmation et remet uniquement ce modèle à sa valeur générique.

Les rappels ont des textes distincts et conservent les délais de l'animation ; deuxième rappel à zéro = désactivé. Pas de rappel pour une annulation ou une simple attente. La confirmation d'annulation concerne l'annulation normale par lien public, pas la maintenance Test ni une purge technique. Les tokens ne doivent jamais être copiés dans un journal public.
