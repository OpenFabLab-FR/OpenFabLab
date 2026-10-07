# E-mails et liens personnels — 2.8.1

Les confirmations, attentes, propositions, modifications et annulations sont envoyées par le moteur SMTP **OpenFabLab**, avec son journal durable. WordPress n'envoie plus d'e-mails de réservation et ne fournit plus de modèles ni de rappels métier indépendants. Les anciennes options peuvent subsister sans être utilisées.

Configurer SMTP, les coordonnées de la structure et les délais de proposition dans OpenFabLab. Le message de bienvenue conserve son modèle personnalisable et un QR Code unique. Voir [familles, réservations et e-mails](families-2.8.md).

En mode WordPress ou automatique avec un site configuré, les liens d'annulation et de proposition reviennent au site WordPress. Aucune URL publique NAS n'est requise et aucune redirection de secours vers le NAS n'est faite si la liaison n'est pas validée dans le bon environnement.

Le jeton signé, limité à son action et à son environnement, est dans le fragment du lien, absent de la requête HTTP et du Referer. Le chargement GET ne confirme ni n'annule rien. Une case de confirmation et un POST protégé déposent l'action dans le relais ; seul OpenFabLab applique la décision et l'expiration. Un clic tardif suivi d'une coupure peut être traité après l'expiration : le dépôt ne garantit pas l'acceptation.

Normal et Test restent séparés ; aucun e-mail réel en Test. Les anciens liens natifs OpenFabLab restent lisibles. Les installations sans WordPress peuvent utiliser les liens natifs avec leur propre accès contrôlé, sans ouverture réseau automatique. Voir [relève, conservation et limites](outbound-2.8.1.md).

Une coupure après acceptation par SMTP peut exceptionnellement répéter un e-mail, jamais doubler une réservation. Ne copier aucun jeton, secret ou contenu privé dans un journal public.
# Candidate 2.8.2 : inscriptions sans compte

Les confirmations, propositions et annulations utilisent les mêmes e-mails et
liens personnels protégés que les comptes. Aucun compte n’est requis pour
répondre à son lien ; aucune action métier par GET. En mode WordPress, les liens
reviennent au site WordPress sans accès entrant NAS. Voir [le guide 2.8.2](reservations-2.8.2.md).
