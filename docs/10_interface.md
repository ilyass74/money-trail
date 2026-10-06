# Interface Money Trail — première version locale

Cette version fournit les cinq écrans d'investigation, reliés à PostgreSQL et au
workflow existant. Les règles de calcul restent dans les modèles dbt. Les preuves
et montants sont lus avec le moteur de dossiers d'investigation déjà vérifié.

## Lancement sous Windows

Extraire le paquet dans le projet existant, puis :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\interface.ps1
```

Le script installe les dépendances, exécute 32 tests Python, 8 tests de parcours
Streamlit avec des services simulés, puis 3 tests PostgreSQL dans des bases
temporaires distinctes. Il crée les tables des comptes avec la migration 004.
Au premier lancement, il demande deux fois un mot de passe d'au moins 12
caractères pour le compte `ilyass` (rôle `admin`). La saisie ne s'affiche pas
dans PowerShell. Le mot de passe n'est pas fourni dans les arguments de commande.
Un compte déjà présent conserve son mot de passe et son rôle.

L'interface est disponible sur http://127.0.0.1:8501. Garder PowerShell ouvert.
Se connecter avec `ilyass` et le mot de passe choisi. Ctrl+C arrête le serveur.
Cette adresse est celle du PC où le script tourne.

Pour relancer sans refaire l'installation et les tests :

```powershell
.\.venv\Scripts\python.exe -m streamlit run .\ui\app.py --global.developmentMode false --server.address 127.0.0.1 --server.port 8501 --browser.gatherUsageStats false --theme.base light --theme.primaryColor "#008879" --theme.backgroundColor "#f6f7fb" --theme.secondaryBackgroundColor "#ffffff" --theme.textColor "#16253b"
```

## Les cinq écrans

| Écran | Travail possible |
|---|---|
| Vue d'ensemble | Compter écarts, calculs bloqués, versements rapprochés et dossiers actifs ; accéder aux résultats à examiner |
| Dossiers | Rechercher et filtrer le statut de suivi, puis ouvrir un dossier |
| Détail du dossier | Lire la formule, ses montants, ses dates, les sources, les critères d'exclusion et les preuves ; télécharger JSON ou Markdown |
| Propositions et validation | Lire les propositions en attente et enregistrer une décision motivée si le compte possède le droit requis |
| Qualité et imports | Voir fichiers, empreintes, nombres de lignes, couvertures par lot et tentatives d'import |

Le détail comporte trois onglets : comprendre le calcul, preuves sources, actions
et historique. Le statut financier et le statut de suivi sont affichés séparément.
Le sélecteur de chargement montre une seule version d'import à la fois : aucun
total ne mélange les snapshots. La vue d'ensemble sépare factures et versements.
Les montants inconnus restent « Inconnu » et les frais manquants bloquent le calcul.

Pour LOT001, on doit lire : attendu 880,00 MAD, reçu 850,00 MAD, écart −30,00 MAD.
La cause reste non identifiée. Son dossier existant reste en investigation,
révision 2, avec les commentaires déjà enregistrés. Pour LOT003, l'attendu et
l'écart restent inconnus ; la couverture `fees` est incomplète pour ce lot.

## Comptes et permissions

Les mots de passe sont stockés sous forme d'empreintes PBKDF2-HMAC-SHA256 avec
un sel aléatoire et 600 000 itérations, un choix de cette version. Les sessions
expirent au bout de quatre heures. La déconnexion supprime la session en base.
Le rôle et l'acteur sont relus côté serveur : les formulaires n'acceptent pas
un nom d'acteur choisi librement par l'utilisateur.

| Rôle | Actions autorisées dans l'interface |
|---|---|
| viewer | Lecture et téléchargement des dossiers |
| analyst | Début/reprise, commentaires, propositions et clôture administrative |
| reviewer | Commentaires, approbation ou rejet d'une proposition d'un autre compte |
| admin | Début/reprise, commentaires, propositions, clôture administrative et synchronisation ; aucune approbation ni aucun rejet financier |

La validation exige le rôle `reviewer` et un compte distinct du proposant.
Un compte administrateur ne peut pas approuver ni rejeter une proposition.
L'approbation reste une décision sur la proposition ; elle ne corrige pas la
source et ne déclare pas l'anomalie financière résolue.

Pour créer un compte supplémentaire sur ce PC, depuis PowerShell :

```powershell
.\.venv\Scripts\python.exe .\scripts\interface_setup.py --username validateur --role reviewer
```

Le mot de passe est demandé interactivement. Le compte doit être utilisé par le
validateur auquel il est destiné. La version locale ne gère pas encore la
récupération de mot de passe ou une administration complète des utilisateurs.

Les scripts CLI antérieurs restent des outils de développement avec acteurs
déclaratifs et accès direct à PostgreSQL. Les permissions des comptes concernent
l'interface et ses services authentifiés ; elles ne retirent pas les droits de
l'utilisateur PostgreSQL de développement. La version fournie écoute uniquement
sur 127.0.0.1 ; l'accès partagé et l'authentification entreprise restent une phase
de déploiement distincte.

## Vérification avant livraison et sur le PC

La [recette étendue](12_recette_complete.md) complète les vérifications de cette
première version. Les nombres ci-dessous décrivent la livraison initiale.

Vérifié dans l'environnement de préparation :

- 32 tests Python réussis, dont les mots de passe et les permissions.
- 8 parcours Streamlit réussis avec des services simulés : cinq écrans,
  connexion, session expirée, montants inconnus, écart connu, commentaire avec
  révision attendue, compte lecteur, accès validateur et refus d'auto-validation.
- Le serveur démarre et répond HTTP 200 sur sa page et son contrôle de santé.
- Syntaxe de la migration et des requêtes de comptes vérifiée avec le parseur
  PostgreSQL ; résolution commune des dépendances Streamlit et dbt réussie.

Ces vérifications ne sont pas une validation visuelle par l'utilisateur ni une
exécution PostgreSQL locale ici. Les 3 tests PostgreSQL doivent passer sur le PC :
création sans écrasement de compte et relance de migration, connexion/déconnexion,
actions et acteurs authentifiés, permissions et expiration de session. Les bases
temporaires `moneytrail_ui_test_<identifiant>` sont supprimées en fin de test.

Parcours de recette dans l'interface :

1. Se connecter et vérifier les résultats de référence dans la vue d'ensemble.
2. Ouvrir LOT001, vérifier formule, lignes sources et historique de révision 2.
3. Ouvrir LOT003 et vérifier que le montant attendu ne devient pas zéro.
4. Ajouter un commentaire sur LOT001 et vérifier son auteur et sa révision.
5. Tester une proposition dans un contexte de démonstration, puis la lire avec
   un autre compte autorisé à valider. Vérifier que le proposant ne peut pas
   prendre sa propre décision.
6. Télécharger JSON et Markdown ; vérifier les montants et identifiants.

Si le chargement échoue, vérifier que PostgreSQL tourne et que le dernier build
dbt complet a réussi. La page refuse des preuves incohérentes ou un journal dbt
échoué. Les erreurs ne publient pas le mot de passe ou la chaîne de connexion.

Le rafraîchissement relit les données ; pas de cache partagé de preuves ou de
sessions. Le chargement reste adapté au jeu de référence : pagination et mesures
de performance sur les volumes cibles sont encore à réaliser. Orchestration,
mapping Odoo réel, résolution par nouvelle donnée et hébergement restent à venir.

## Sources

- Streamlit, version et compatibilité Python : https://pypi.org/project/streamlit/1.64.0/
- Streamlit, AppTest : https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest
- Python, PBKDF2 et hashlib : https://docs.python.org/3/library/hashlib.html
- PostgreSQL 17, transactions : https://www.postgresql.org/docs/17/sql-set-transaction.html
- Chiffres et règles métier : modèles, fixtures et dossiers Money Trail.
