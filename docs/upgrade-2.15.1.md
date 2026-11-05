# OpenFabLab 2.15.1 — mises à jour intégrées

## Première transition depuis la 2.15.0

La 2.15.0 ne dispose ni du bouton d’import ni de la commande correspondante
dans son agent. Un ZIP local ne peut donc pas être transmis par l’ancienne
interface. L’administrateur du serveur doit effectuer une transition unique :
mettre à niveau le logiciel de l’agent sans recréer son installation, puis lui
faire installer le ZIP 2.15.1. Sur DSM, utiliser la procédure privée adaptée à
l’installation. Ne pas réexécuter l’installateur 2.15.0 ni la migration 25 → 26.

Le manifeste de mise à jour intégrée de la 2.15.1 accepte comme source le schéma 26. L’installation de 2.15.1
ne change pas de schéma. Garder les sauvegardes précédentes et vérifier le
contrôle préalable avant toute interruption.

## Depuis Réglages → Système et sauvegardes → Mises à jour

1. Vérifier que l’agent est connecté.
2. Choisir **Importer un ZIP**, sélectionner le fichier puis cliquer **Vérifier le ZIP**. Utiliser une archive applicative OpenFabLab provenant
   d’une source de confiance, ou **Version officielle GitHub** pour rechercher
   la dernière stable. Le ZIP du plugin WordPress n’est pas un paquet applicatif.
3. Lire la version, les changements, la compatibilité SQLite et le résultat des
   contrôles. L’import ne construit et ne démarre pas la candidate. Après votre
   confirmation, l’agent la teste sur une copie isolée avant d’arrêter le service.
4. Confirmer une seule fois l’installation de la version préparée. Attendre le
   résultat. **Actualiser l’état de la mise à jour** ne fait que lire le suivi.
5. Dans l’historique, ouvrir les détails du contrôle et vérifier les sauvegardes
   PRE/POST. Les preuves détaillées restent dans l’état privé de l’agent.
   Vérifier la version affichée, l’état de l’agent et le dernier résultat dans
   l’historique. Si le navigateur a perdu la connexion pendant le redémarrage,
   rouvrir la page et lire l’état avant de prendre une autre décision.

Les versions officielles suivent l’identité du dépôt GitHub et l’empreinte de
l’asset officiel. Un ZIP importé n’est pas authentifié par GitHub : son manifeste
protège l’intégrité et vérifie la structure, pas la provenance. Un ZIP contient
du code qui, une fois installé, accède aux données de l’application. Ne jamais
importer une archive inconnue. Le serveur web ne reçoit pas les droits Docker.

Les deux modes exigent des sauvegardes vérifiées, un essai isolé, les contrôles
SQLite et HTTP et, lorsque WordPress est actif, les échanges Normal/Test.
En cas d’état préservé, consulter le [guide de secours](update-agent.md) :
aucune restauration automatique n’écrase les écritures intervenues depuis la
réouverture. Une mise à jour applicative ordinaire conserve l’agent ; une
évolution future de l’agent lui-même peut nécessiter une intervention distincte.

## QR des ressources

Dans **Réglages → Ressources et maintenance**, choisir l’adresse à inscrire
dans les QR. Exemple privé fictif : `http://192.168.50.10:5080/stat` ; exemple
public : `https://fablab.example/stat`. Conserver le chemin de l’application.
Le mode privé n’ouvre aucun port et ne restreint pas les routes existantes :
le réseau détermine qui peut joindre le serveur. HTTP n’est pas chiffré.
Les droits de publication des ressources et des tutoriels ne changent pas.
Tester l’adresse depuis le réseau concerné avant de réimprimer les étiquettes.
Les étiquettes déjà imprimées continuent de pointer vers l’ancienne adresse.
Pour HTTPS public, ne jamais exposer l’administration DSM.

Le plugin WordPress Reservations 2.15.0 n’a pas changé. Aucune réinstallation
ou modification des paramètres WordPress n’est nécessaire pour la 2.15.1.
