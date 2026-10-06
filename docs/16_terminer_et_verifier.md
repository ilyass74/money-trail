# Money Trail — fonctions restantes et vérifications

Cette version complète le code local après `money-trail-publication-v1.zip`.
Le succès des contrôles consignés ici ne certifie pas encore le MVP entier.

## Installer sur le PC existant

Arrêter Streamlit avec Ctrl+C ; garder Docker Desktop et PostgreSQL démarrés.
L’archive est une mise à jour : elle ne contient ni `.env`, ni comptes, ni données réelles,
ni volume PostgreSQL. Les migrations 001 à 005 conservent leurs octets ; 006 et 007
ajoutent les nouvelles fonctions. Aucun mot de passe local à recréer.

```powershell
Set-Location C:\Users\HP\Documents\money-trail
Expand-Archive -LiteralPath "$HOME\Downloads\money-trail-completion-v1.zip" -DestinationPath . -Force
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\complete.ps1
```

Le script lance la recette native dans des bases temporaires puis publie le dernier
snapshot de chaque périmètre. Un échec interrompt la mise à jour et conserve la
publication valide précédente. Lire `reports/acceptance_.../report.md` avant de
conclure. `mvp_ready: false` reste possible lorsque les critères externes ne sont
pas tous exécutés.

Pour ajouter les trois benchmarks sur le PC :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\complete.ps1 -Benchmark
```

Ils peuvent durer longtemps et consommer beaucoup de mémoire. Chaque niveau a sa
base temporaire, ses cardinalités et son rapport, y compris en cas d’échec.
Les mesures ne constituent pas une capacité de production garantie.

## Fonctions ajoutées

| Fonction | Comportement |
|---|---|
| Règles | v1 conserve zéro tolérance. v2 possède des tolérances explicites, enregistrées une fois et immuables. |
| Comparaison | Une nouvelle règle sur un même snapshot conserve les résultats avant/après, les changements et leurs publications. |
| Succession | Un objet déjà suivi reçoit une nouvelle revue si ses sources, sa date de contrôle ou sa règle changent. Les décisions antérieures restent intactes ; le responsable est conservé. |
| Pagination | PostgreSQL filtre et trie ; l’interface charge 25, 50 ou 100 dossiers. Les indicateurs globaux utilisent des comptes archivés. |
| Filtres et export | Type, statut, identifiant, montant connu et responsable ; sélection de l’entreprise/devise/date par version ; export CSV de la page filtrée. |
| Candidats bancaires | Classement par référence explicite puis distance de montant. Une identité non confirmée est signalée. Aucune allocation automatique. |
| Attribution | Compte autorisé, révision contrôlée et événement d’historique. |
| Actions | Le validateur peut joindre une pièce d’action externe après approbation. Il ne modifie aucune écriture ERP. |
| Résolution | Pièce requise et publication ultérieure sur de nouvelles sources confirmant `soldee` ou `rapproche`. La même source recalculée avec une tolérance différente ne suffit pas. |
| Écart accepté | Un validateur peut accepter un écart connu avec justification. Le résultat financier reste inchangé. |
| Sources | Extraction JSON-2 Odoo, contrôle de stabilité, quarantaine et date de fraîcheur. CSV : quarantaine optionnelle, conservation de l’original et propagation aux dépendances. |
| Périmètres | Un snapshot par entreprise/devise ; finance-v1 supporte MAD/EUR/USD/GBP au centime, sans conversion FX. |
| Airflow | DAG quotidien avec reprises ; publication uniquement après succès. Base de métadonnées distincte. |
| Cloud | Profil HTTPS/OIDC, identité explicitement liée à un compte et rôles PostgreSQL distincts pour l’interface et le pipeline. |

## Odoo local 19

Le connecteur utilise JSON-2 et refuse toute méthode d’écriture. Il vérifie les
champs effectifs avec `fields_get` et extrait `account.move`, `account.move.line`,
`account.payment`, `account.partial.reconcile`. Il faut vérifier ces droits et
champs sur l’instance locale. L’accès à une offre Odoo hébergée dépend de son plan.

Définir `ODOO_URL`, `ODOO_API_KEY`, et éventuellement `ODOO_DATABASE` dans
l’environnement du terminal. Ne jamais les ajouter au dépôt. Puis :

```powershell
.\.venv\Scripts\python.exe .\scripts\odoo_extract.py --company-id 1 --output .\data\odoo_premiere_extraction --import-bundles
.\.venv\Scripts\python.exe .\scripts\run_dbt.py build
```

Choisir un dossier de sortie neuf à chaque extraction. Les factures et leurs lignes
restent distinctes. Les liens de paiement proviennent des rapprochements comptables
explicites, jamais de montants semblables. Les avoirs sont comptés par leur allocation.
Une contrepartie non gérée ou multidevise rend la couverture incomplète.
Les quantités conservent leur précision. Les montants à une précision non supportée
sont rejetés.

`orders.csv` de cet adaptateur contient des **contextes de factures**, explicitement
nommés `DOC:...`, pas des commandes commerciales Odoo. L’intégration des vraies
commandes de vente et de leurs relations reste une extension à vérifier sur
l’instance. Les extractions complètes retrouvent les modifications tardives ; il
n’y a pas encore de checkpoint incrémental ni de fenêtre de recouvrement.

Les rescans détectent les modifications observables entre appels. JSON-2 effectue
une transaction par appel : cette extraction multi-appels n’est pas un snapshot
transactionnel global d’Odoo. L’essai sur l’instance locale reste obligatoire.

## CSV invalides

L’import normal conserve son comportement strict. L’isolation des lignes s’effectue
explicitement avant import :

```powershell
.\.venv\Scripts\python.exe .\scripts\quarantine_csv.py --source .\data\lot_a_controler --output .\data\lot_controle --import-bundle
```

Les doublons ambigus sont tous exclus ; les enfants sans parent valide sont isolés.
Le fichier original, les lignes rejetées et leurs motifs sont conservés en base.
La couverture des sources concernées devient incomplète. Un fichier avec une
empreinte ou des colonnes incohérentes reste refusé en entier.

## Comparer une règle

```powershell
.\.venv\Scripts\python.exe .\scripts\run_dbt.py build --batch-id IDENTIFIANT_SOURCE --rule-version v2 --invoice-tolerance 0.01 --settlement-tolerance 30.00
```

Les tolérances sont en devise du dossier. **30.00 est un exemple de démonstration,
pas une recommandation finance.** La première politique v2 enregistrée est conservée ;
une tentative de changer sa tolérance sous le même nom est refusée. La comparaison
apparaît dans « Comparaison des règles ». Un écart toléré reste affiché.
Deux règles sur le même import peuvent créer deux dossiers ; la CLI demande alors
le `case_id` explicite pour éviter une décision sur le mauvais dossier.

## Airflow et cloud

Les fichiers fournis sont à construire et tester dans l’environnement cible.
Ils n’ont pas été déployés sur ta VM. Le DAG a été chargé avec Airflow 3.3.1 ;
l’exécution Docker et l’authentification avec un fournisseur OIDC restent à vérifier.
Les images Python, Airflow et Caddy sont figées par digest.

```powershell
.\.venv\Scripts\python.exe .\scripts\deploy_setup.py --roles
docker compose -f compose.yaml -f compose.airflow.yaml --profile airflow up -d --build
```

L’interface Airflow est liée à `127.0.0.1:8081`. Le mode `standalone` sert à cette
**démonstration locale**, pas à un déploiement de production. La base Airflow est
séparée. Son mot de passe est généré sans remplacer le mot de passe du projet.
Le DAG importe `data/reference_v1` ; pour des sources actualisées, utiliser le
script `pipeline.py --source CHEMIN` avec leur manifeste. Une source non synthétique
inconnue ou périmée bloque ce pipeline. Le jeu de référence reste explicitement
synthétique et sa date de contrôle ne change pas automatiquement.

Pour Azure : vérifier d’abord la taille de VM après benchmark, puis DNS, domaine,
accès réseau et fournisseur OIDC. Copier `deploy/secrets.toml.example` vers
`deploy/secrets.toml` et renseigner les valeurs réelles ; ajouter `MT_DOMAIN` dans
`.env`. La redirection est `https://DOMAINE/oauth2callback`.

Lier le `iss` et le `sub` exacts d’un utilisateur du fournisseur à un compte local
préexistant, sans déduire l’identité depuis son email :

```powershell
.\.venv\Scripts\python.exe .\scripts\deploy_setup.py --username ilyass --issuer https://EMETTEUR --subject IDENTIFIANT_OIDC
docker compose -f compose.yaml -f compose.cloud.yaml --profile cloud up -d --build
```

Le démarrage cloud refuse les modèles de secrets et exige OIDC/HTTPS. Le port de
l’application n’est pas publié directement. Les rôles DB sont limités aux opérations
nécessaires ; les migrations s’appliquent avec le compte d’installation avant le
lancement des services. Ne pas exposer PostgreSQL ou Airflow à Internet.

## Validations restantes dans les environnements cibles

- Recette native PostgreSQL 17 sous Windows, avec les tests de concurrence et restauration.
- Connexion et jeux de démonstration sur Odoo local réel, y compris commandes de vente.
- Les trois benchmarks avec RAM/CPU serveur et temps de réponse ; vérifier les grandes pièces sources, qui restent archivées intégralement.
- Parcours navigateur sur PostgreSQL natif, revue finance et navigation clavier complète.
- Construction des conteneurs, exécution Airflow, fournisseur OIDC, HTTPS et restauration sur Azure.
- Validation des règles de frais, tolérances, conservation et périmètres par le référent finance.

## Sources

- Cahier des charges du projet, version du 5 octobre 2026 ; code, fixtures et journaux livrés.
- [Odoo 19 — External JSON-2 API](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html).
- [Odoo 19 — account.partial.reconcile](https://github.com/odoo/odoo/blob/19.0/addons/account/models/account_partial_reconcile.py).
- [Streamlit — authentification et autorisation](https://docs.streamlit.io/develop/concepts/connections/authentication).
- [Airflow 3.3.1 — Docker](https://airflow.apache.org/docs/apache-airflow/3.3.1/howto/docker-compose/).
- [PostgreSQL 17 — privilèges](https://www.postgresql.org/docs/17/ddl-priv.html).
- [Docker — Compose](https://docs.docker.com/compose/).
