# Deuxième jalon importer les sources

Cette mise à jour ajoute des fichiers au projet existant. Elle ne contient ni `.env` ni données PostgreSQL, et ne change pas `compose.yaml`.

## Installer et importer dans PowerShell

Depuis le dossier du projet :

Cette commande réalise l'installation, les douze tests locaux, les quatre tests PostgreSQL isolés, puis deux imports et leur bilan. Elle s'arrête à la première étape en échec :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\import_demo.ps1
```

Pour exécuter les étapes individuellement :

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements-import.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe .\scripts\import_data.py setup
.\.venv\Scripts\python.exe .\scripts\import_data.py import
.\.venv\Scripts\python.exe .\scripts\import_data.py import
.\.venv\Scripts\python.exe .\scripts\import_data.py inspect
```

Il n'est pas nécessaire d'activer le venv : les commandes utilisent son Python explicitement. La première installation affiche `SCHEMA_READY`. Le premier import affiche `success` et 26 enregistrements. Le deuxième affiche `skipped_duplicate` et zéro enregistrement ajouté. Le bilan conserve 1 lot, 12 fichiers et 26 enregistrements bruts.

## Ce que l'import conserve

`meta.import_attempts` conserve chaque tentative et son état. `meta.import_batches` conserve les imports confirmés, le manifeste, sa couverture et la date métier de contrôle. `meta.import_files` conserve les octets originaux, leur empreinte et leur nombre de lignes. `raw.source_records` conserve chaque ligne, son identifiant source et sa référence au fichier.

Les montants restent des chaînes dans les données brutes. Les modèles SQL/dbt les convertiront ensuite vers NUMERIC avec les règles de contrôle.

## Reprises et versions

L'import valide une copie des octets qui seront chargés. Il charge le lot dans une transaction : un échec n'en publie aucune partie. Une tentative échouée reste visible dans le journal. Un verrou sur l'empreinte sérialise les imports identiques concurrents, et une contrainte unique empêche deux lots confirmés portant la même empreinte.

Un lot identique est ignoré et sa tentative est enregistrée. Un manifeste ou des fichiers différents forment une nouvelle version brute. Les prochaines transformations sélectionneront la version pertinente : elles ne devront pas sommer toutes les versions historiques d'un même événement.

Une interruption brutale du processus peut laisser une tentative à l'état `started` ; elle devra être qualifiée lors de l'exploitation. Aucun horodatage de modification source n'est inventé : ce contrat CSV n'en fournit pas, et conserve les versions par leur empreinte.

Ce connecteur est limité au contrat synthétique `reference-v1`. Les futurs contrats Odoo et exports réels seront ajoutés explicitement. Un contrôle de structure manquant ou invalide fait échouer le lot ; le détail du rejet ligne par ligne est une évolution à réaliser.

## Vérification PostgreSQL isolée

```powershell
.\.venv\Scripts\python.exe .\scripts\test_import_integration.py
```

Les quatre tests créent des bases temporaires `moneytrail_test_...` distinctes, puis les suppriment. Ils vérifient l'import de 26 lignes, la relance sans doublon, le rejet d'une source modifiée, la reprise après échec partiel et l'installation répétée. Ils utilisent le compte d'initialisation local, qui doit avoir le droit de créer une base.

Ces tests PostgreSQL restent à exécuter sur le PC Windows. Le moteur Docker n'est pas disponible dans l'environnement de préparation. Douze tests des fixtures et de la préparation d'import ont été exécutés avec succès sans base.

Références : [Psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html), [transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html), [PostgreSQL INSERT](https://www.postgresql.org/docs/17/sql-insert.html).
