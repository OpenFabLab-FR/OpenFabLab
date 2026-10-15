# OpenFabLab Reservations 2.9.0

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
