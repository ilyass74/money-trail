# Moteur métier SQL et dbt — première version

Ce paquet complète le projet existant. Il ne remplace ni `.env`, ni les sources,
ni le volume PostgreSQL. Il construit les résultats à partir des imports validés.

## Exécution sous Windows

Décompresser le paquet dans `C:\Users\HP\Documents\money-trail`, puis exécuter :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_business.ps1
```

Le script installe dbt dans le Python existant du projet, analyse le projet dbt,
exécute les tests métier dans une base temporaire distincte, puis construit et
teste les modèles sur la base Money Trail. Il s'arrête dès qu'une étape échoue.
La base temporaire `moneytrail_dbt_test_<identifiant>` est supprimée à la fin.
Elle exige le droit de créer une base, disponible avec l'utilisateur initial
du conteneur de développement. Un arrêt brutal peut nécessiter un nettoyage
ultérieur de cette seule base temporaire.

Le test négatif de surallocation affiche intentionnellement un test dbt `FAIL`.
Il est attendu uniquement dans la base temporaire : le test Python doit ensuite
afficher `OK` et `BUSINESS_INTEGRATION_OK`. Le build final sur Money Trail doit
réussir et afficher `REFERENCE_RESULTS_OK`.

Pour afficher de nouveau les résultats de référence :

```powershell
.\.venv\Scripts\python.exe .\scripts\run_dbt.py results
```

## Modèles et responsabilité des outils

- Python prépare la connexion, lance dbt et vérifie les résultats attendus.
- Les modèles SQL contiennent les calculs métier ; PostgreSQL les exécute.
- dbt construit les modèles dans l'ordre de leurs dépendances et exécute les tests.
- `staging.stg_*` extrait les champs JSONB et convertit montants, dates et heures.
- `core.core_invoice_amounts` et `core.core_settlement_amounts` agrègent chaque
  composante séparément avant les jointures.
- `marts.invoice_reconciliation` et `marts.settlement_reconciliation` exposent
  montants, statuts, qualité, versions de règles et provenance.

Chaque résultat a pour grain : **import_batch_id + company_id + currency +
identifiant métier**. Toutes les versions importées restent distinctes.
Ne jamais additionner les résultats de plusieurs snapshots d'une même source.
Le script de vérification choisit le snapshot correspondant exactement aux
empreintes des fichiers de référence, et non le dernier import arbitraire.

## Règles implémentées

Facture : montant facturé moins affectations confirmées de paiements confirmés,
moins avoirs comptabilisés. Une affectation ne compte que si le paiement est
antérieur à la fin de la date de contrôle UTC ; un avoir ne compte que si sa date
est au plus celle du contrôle. Les frais du prestataire ne réduisent jamais la
créance client. Solde positif et échéance future : `solde_en_attente` ; échéance
passée : `en_retard`. Une échéance absente reste `echeance_inconnue`.

Versement : captures éligibles moins remboursements moins frais plus ajustements
signés documentés. Les lignes doivent appartenir à la même entreprise, devise,
version d'import et lot métier, et se situer dans la période `[début, fin)`.
Le montant reçu vient des affectations confirmées à des crédits bancaires dont
les dates de comptabilisation et de valeur sont au plus la date de contrôle.
Écart = reçu moins attendu. Un écart ne prouve pas sa cause : `non_identifiee`.
La période doit être close ; avant la date de réception attendue, un écart est
classé `versement_en_attente`.

Couverture manquante : montant concerné et écart restent NULL, `calcul_bloque`.
La somme vide est utilisable comme zéro uniquement si la couverture du périmètre
est déclarée complète. Les sommes observées dans `core` sont des composantes de
travail ; utiliser les colonnes validées de `marts` pour communiquer un résultat.
Les modèles conservent le `record_id` de la facture ou du lot, le snapshot,
la devise, la date de contrôle et la version de règle. Les lignes détaillées
se retrouvent dans les vues staging par ce même snapshot et les identifiants.

Les montants utilisent NUMERIC(20,2), sans float. Tolérance v1 : 0,00 MAD.
Règles : `invoice-v1` et `settlement-v1`. Les marts sont reconstruits, sans ajout
de lignes à chaque relance. Ils ne constituent pas un historique des exécutions
du moteur ; les traces dbt locales apportent les résultats d'exécution.

## Résultats de référence attendus

| Objet | Attendu | Reçu / affecté | Solde / écart | Statut |
|---|---:|---:|---:|---|
| FAC001 | 1 000,00 | 900,00 | 100,00 | solde_en_attente |
| LOT001 | 880,00 | 850,00 | −30,00 | ecart |
| LOT002 | 880,00 | 880,00 | 0,00 | rapproche |
| LOT003 | inconnu | 950,00 | inconnu | calcul_bloque |
| LOT004 | 1 000,00 | 1 000,00 | 0,00 | rapproche |

## Vérification et limites

La suite métier isolée contrôle les résultats écrits à la main dans
`fixtures/expected_results.json`, les avoirs, le retard, plusieurs frais et
remboursements sans multiplication des sommes, la séparation des snapshots,
la couverture incomplète des avoirs, la coupure temporelle des paiements et de
la banque, un ajustement négatif, la relance sans doublons et le rejet d'une
surallocation. Les tests SQL contrôlent aussi les grains, périodes, plafonds
d'affectation, plafonds de remboursement et cohérence du lot des remboursements.

Un build dbt échoué n'est pas une publication de résultats validés. Certains
modèles peuvent avoir été construits avant l'échec : ne pas exploiter leurs
résultats tant que le build complet n'a pas réussi.

Cette version s'applique au contrat synthétique `reference-v1`, une entreprise,
MAD et un contrôle quotidien UTC. Le mapping Odoo réel, les états additionnels,
les corrections comptables, l'interface, le workflow humain, l'orchestration et
le déploiement restent à développer. Aucune écriture comptable source n'est faite.

## Sources techniques

- dbt Labs : modèles SQL — https://docs.getdbt.com/docs/build/sql-models
- dbt Labs : tests de données — https://docs.getdbt.com/docs/build/data-tests
- dbt Labs : variables et secrets — https://docs.getdbt.com/reference/dbt-jinja-functions/env_var
- dbt-postgres, métadonnées du mainteneur — https://pypi.org/project/dbt-postgres/1.11.0/
- PostgreSQL 17 : types numériques — https://www.postgresql.org/docs/17/datatype-numeric.html
- Règles et chiffres de démonstration : contrats et fixtures du projet Money Trail.
# Mise à jour : publication fiable

Depuis la mise à jour `publication-v1`, `run_dbt.py build` construit un candidat
isolé et archive les résultats validés avant de les rendre visibles. Le résultat
attendu est `PUBLICATION_PUBLISHED`, accompagné de `REFERENCE_RESULTS_OK` pour
le jeu de référence. Les étapes et les tests actuels sont dans
[14_publication_fiable.md](14_publication_fiable.md). La documentation historique
du moteur ci-dessous décrit les formules et ses premiers tests.
