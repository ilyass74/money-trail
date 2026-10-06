# Dossiers d'investigation — données explicatives pour la future interface

Cette étape ajoute la consultation et l'export de preuves des résultats existants.
Elle ne modifie pas les données PostgreSQL et ne constitue pas encore l'interface.
Le dossier doit répondre à : quel problème, quel calcul, quelles pièces sources,
quelles données manquent et que faut-il vérifier ?

## Exécution

Après extraction du paquet dans le projet existant :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\investigation_demo.ps1
```

Le script exécute les tests Python, explique LOT001 et LOT003, puis exporte les
cinq dossiers de référence dans un nouveau sous-dossier de `reports`.
Il doit afficher `INVESTIGATION_EXPORTED` et `dossiers: 5`.

Pour consulter un objet :

```powershell
.\.venv\Scripts\python.exe .\scripts\investigate.py invoice FAC001
.\.venv\Scripts\python.exe .\scripts\investigate.py settlement LOT001
.\.venv\Scripts\python.exe .\scripts\investigate.py settlement LOT003
```

Pour exporter un seul dossier ou tous les dossiers :

```powershell
.\.venv\Scripts\python.exe .\scripts\investigate.py settlement LOT001 --export
.\.venv\Scripts\python.exe .\scripts\investigate.py all --export
```

Par défaut le snapshot est celui correspondant aux empreintes des sources de
référence. `--batch-id <UUID>` permet de sélectionner explicitement un autre
snapshot du contrat `reference-v1` ; les versions ne sont jamais fusionnées.

Chaque dossier possède un fichier Markdown lisible et un JSON structuré. Les
fichiers portent des numéros séquentiels ; les identifiants sources ne servent
pas de noms de fichiers. Chaque export crée un dossier distinct sans écraser
les exports précédents. Les dossiers contiennent des données financières et
des payloads bruts : dans un usage réel, limiter leur accès aux personnes
autorisées. Le dossier `reports` est déjà exclu du suivi Git du projet.

## Contenu du dossier

- Résultat dbt, statut, qualité, devise et version de règle.
- Formule et substitution des montants, sans convertir les inconnus en zéro.
- Dates de contrôle et d'échéance, ou période du versement et réception attendue.
- Couverture déclarée dans le manifeste et sources manquantes.
- Lignes sources avec identifiants, payloads bruts, numéro de ligne de données
  (hors en-tête CSV), fichier, empreinte de fichier et empreinte de payload.
- Pour les contributions : inclusion dans la somme observée et critères
  d'exclusion. Les paiements ERP et mouvements bancaires parents sont fournis
  comme contexte, sans les compter une seconde fois dans la somme.
- Vérifications proposées ; aucune cause financière ou correction inventée.

Exemple LOT001 : `1000 - 100 - 20 + 0 = 880 MAD`, puis
`850 - 880 = -30 MAD`. Le dossier constate l'écart, mais sa cause reste
`non_identifiee`. Vérifier l'avis de versement, les composantes du prestataire
et l'affectation du crédit bancaire avant de proposer une correction.

Exemple LOT003 : les frais ne sont pas disponibles pour ce lot. L'attendu et
l'écart restent inconnus, même si le crédit bancaire de 950 MAD est observable.
Il faut obtenir les frais et confirmer la couverture de ce périmètre avant de
recalculer. L'absence de ligne n'est pas une preuve de frais nuls.

FAC001 : le solde est de 100 MAD au 5 octobre 2026, avec une échéance au
20 octobre 2026 ; il n'est donc pas qualifié de retard à cette date.

## Vérifications et limites

L'export exige un journal du dernier build dbt réussi avec les deux modèles de
résultats et des tests. Il conserve l'identifiant d'exécution et l'empreinte du
journal local. Il contrôle les empreintes des fichiers et payloads conservés,
puis vérifie avec Decimal que les contributions détaillées correspondent aux
montants des résultats et que les formules concordent. Le résultat dbt reste
la source du montant présenté ; ces recomptages servent à vérifier les preuves.

Les lectures s'effectuent dans une transaction REPEATABLE READ READ ONLY afin
de garder une vue cohérente du résultat et de ses lignes sources. Un dernier
build échoué ou une incohérence de preuves bloque l'export.

Les empreintes démontrent la cohérence des pièces conservées ; elles ne prouvent
pas leur authenticité externe ni leur exactitude comptable. Le journal dbt local
n'est pas une signature et ne remplace pas l'historique d'exécution centralisé
prévu ultérieurement. Les exports reflètent les résultats lus au moment de
la génération ; les fichiers déjà exportés ne se mettent pas à jour.

La gestion des dossiers (responsable, commentaires, décisions, corrections
proposées, validation humaine et historique) viendra dans les tables `app`,
séparément des résultats recalculés. Aucun de ces workflows n'est implémenté
ici. Aucun LLM n'est nécessaire pour ces explications déterministes.

Vérification avant livraison : 21 tests Python réussis, dont 7 nouveaux contrôles
sur les explications, les dates, les montants inconnus et le refus d'un build
échoué. Les cinq dossiers ont aussi été générés à partir des résultats dbt
transmis et des fixtures, avec les lectures de base simulées. Cette vérification
ne remplace pas l'exécution de l'export sur PostgreSQL : elle reste à confirmer
avec `investigation_demo.ps1` sur le PC du projet.

## Sources

- Règles et scénarios : contrats Money Trail, modèles SQL et fixtures de référence.
- PostgreSQL 17, SET TRANSACTION : https://www.postgresql.org/docs/17/sql-set-transaction.html
- Python, Decimal : https://docs.python.org/3/library/decimal.html
- Python, hashlib : https://docs.python.org/3/library/hashlib.html
