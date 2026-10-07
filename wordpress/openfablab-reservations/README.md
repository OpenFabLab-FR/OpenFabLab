# OpenFabLab Reservations 2.8.2 — version stable

Plugin facultatif pour OpenFabLab **2.8.2**, protocole **4 / révision 3**.
OpenFabLab contacte ce site en HTTPS signé pour publier le catalogue, relever
les demandes et retourner les décisions. WordPress ne décide jamais des places.
Aucune adresse entrante du NAS ni reverse proxy n’est nécessaire.

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
demandes, sauvegarder WordPress (base/options/secret) et OpenFabLab (PRE 16/image).
Extensions → Ajouter → Téléverser le ZIP → remplacer la version existante,
**sans désinstaller** et sans changer le secret. Mettre à jour OpenFabLab et
attendre le premier catalogue Normal/Test avant réouverture. Le plugin révision
3 ne fonctionne pas avec le moteur 2.8.1 révision 2 ; l’attente est normale
pendant la bascule. Lire `docs/reservations-2.8.2.md` dans l’application.
