# Préparation privée d’une image de l’agent 1.2

Ce kit séparé ne déploie pas OpenFabLab et ne change pas le conteneur actif. Ne pas importer ce ZIP dans l’interface OTA. Le protocole reste à 1. Ne pas réutiliser le kit de première activation sur l’installation existante.

La préparation conserve l’image locale de l’agent et ses dépendances ; deux fichiers seulement changent (comparateur de versions et numéro de l’agent). Elle vérifie leurs empreintes d’origine avant construction. Une source différente est refusée ; ne pas désactiver ce contrôle.

Sur un **hôte de test** compatible, vérifier le SHA-256 du kit, extraire dans un dossier privé puis exécuter « python3 prepare.py --docker /chemin/absolu/vers/docker ». Python 3.9+ et un moteur local permettant une construction classique depuis un ID d’image local sont requis. Les sondes n’ont aucun montage, aucune capacité ni réseau. Le résultat donne les deux ID d’image, sans jeton ni configuration privée.

Préparer n’est pas activer. Le basculement et le retour arrière doivent être répétés sur une réplique avant installation DSM. Ne jamais interrompre une opération prête, active ou en récupération. Ce kit ne constitue pas une instruction de déploiement sur le NAS.
