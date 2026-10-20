# OpenFabLab Reservations 2.11.0 — plugin facultatif stable

Application et plugin OpenFabLab 2.11.0, protocole 4/révision 3 inchangé.
Cette version actualise le numéro public et la documentation ; le moteur du
relais, ses signatures, ses capacités et ses ressources restent inchangés depuis
2.10.1. Les présences automatiques restent internes à OpenFabLab : elles ne
déclenchent ni inscription ni courriel de réservation. Installer sans désinstaller
l’extension ni changer les secrets. Aucune connexion entrante vers OpenFabLab
n’est nécessaire. Les paragraphes suivants sont les références historiques.

[Release officielle](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.11.0) ·
[Guide WordPress](https://github.com/OpenFabLab-FR/OpenFabLab/blob/v2.11.0/docs/wordpress.md).
L’archive approuvée est distribuée à l’identique, sans reconstruction.
OpenFabLab reste utilisable sans WordPress ; les mentions de préparation dans
le README figé du ZIP sont historiques. La documentation de ce tag fait référence.

---

## Référence historique : OpenFabLab Reservations 2.10.1

Extension libre sous licence MIT. [Release officielle](https://github.com/OpenFabLab-FR/OpenFabLab/releases/tag/v2.10.1)
et [guide WordPress à jour](https://github.com/OpenFabLab-FR/OpenFabLab/blob/v2.10.1/docs/wordpress.md).
Le ZIP approuvé est distribué à l’identique : son README figé peut garder une
mention de préparation. La documentation de ce tag fait référence.

Plugin facultatif pour OpenFabLab 2.10.1 ; catalogue 2.10.0 accepté pendant la
transition. Protocole 4 / révision 3, capacité `waitlist_limits_v1` inchangés.
Présentation par créneau : places disponibles, attente ouverte ou saturée,
états fermés, récapitulatif distinguant réservation et attente. Le moteur
OpenFabLab conserve seul l’attribution transactionnelle des places.

Mettre à jour OpenFabLab avant le plugin. Sauvegarder les deux installations,
puis remplacer le ZIP du plugin sans désinstaller ni changer ses secrets.
Le numéro public du plugin suit désormais celui de l’application ; il ne sert
pas de condition d’authentification ou de compatibilité du relais.

## Référence historique : Reservations 2.9.0

Plugin facultatif pour OpenFabLab **2.9.0**, protocole **4 / révision 3**.
Capacité optionnelle `waitlist_limits_v1` : compteur d’attente et états de
fermeture transmis par OpenFabLab, indicateurs pastel sous les horaires et
boutons au pied des cartes. Le catalogue antérieur reste accepté explicitement.
OpenFabLab contacte ce site en HTTPS signé pour publier le catalogue, relever
les demandes et retourner les décisions. WordPress ne décide jamais des places.
Aucune adresse entrante du NAS ni reverse proxy n’est nécessaire.
Plugin facultatif : OpenFabLab reste utilisable sans WordPress. Le ZIP officiel
2.9.0 est distribué sans modification ; les instructions stables sont disponibles
dans le [guide WordPress](../../docs/wordpress.md) du dépôt.

PHP 8.1+, OpenSSL AES-GCM, InnoDB, REST, HTTPS et JavaScript nécessaires.
Shortcodes : `[openfablab_reservations environment="production"]` pour Normal,
`[openfablab_reservations environment="test"]` pour Test.

Le réglage OpenFabLab « Compte obligatoire » est désactivé par défaut : réservation
familiale avec compte ou inscription individuelle autonome sans compte, coordonnées
et date de naissance. Aucun compte n’est créé. E-mail requis, téléphone selon
la règle OpenFabLab. Un compte se retrouve par QR quatre chiffres ou saisie,
toujours avec vérification d’e-mail/téléphone. Caméra frontale préférée, images
traitées localement, aucune capture ni transmission. Saisie manuelle disponible.

Avant remplacement, fermer temporairement la page publique, laisser finir les
demandes, sauvegarder WordPress (base/options/secret) et OpenFabLab (PRE 19/image).
Extensions → Ajouter → Téléverser le ZIP → remplacer la version existante,
**sans désinstaller** et sans changer le secret. Mettre à jour OpenFabLab et
attendre le premier catalogue Normal/Test avant réouverture. Le plugin révision
3 ne fonctionne pas avec le moteur 2.8.1 révision 2 ; l’attente est normale
pendant la bascule. Lire `docs/reservations-2.8.2.md` dans l’application.

Les apports 2.8.5 conservés enrichissent la page personnelle « Gérer ma réservation » et ajoutent
le lien facultatif « En savoir plus » reçu du moteur. La révision reste 3 : la
capacité `animation_information_v1` est annoncée explicitement. OpenFabLab 2.8.5
reste compatible avec le plugin officiel 2.8.2 (sans ce lien de catalogue) ; le
plugin 2.8.5 accepte aussi le catalogue 2.8.4. Le stockage WordPress est inchangé.
Annuler passe par une deuxième étape et une confirmation explicite. Aucun GET ne
déclenche d’annulation et WordPress attend la décision du moteur.
