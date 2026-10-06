# Recette Money Trail — cas métier et limites connues

La mise à jour actuelle est [publication-v1](14_publication_fiable.md) : utiliser
son archive et `publication_demo.ps1` pour tester puis publier dans le projet.
La recette comprend désormais 179 tests, dont 13 scénarios de publication réelle.
Les commandes d'installation ci-dessous restent celles du premier paquet de recette.

Cette mise à jour teste le contrat synthétique `reference-v1` : une entreprise
`DEMO_MA`, des montants en MAD, les règles facture et versement v1 et l’instance
locale. Les attentes financières sont écrites à la main dans
`fixtures/acceptance_cases.json`, indépendamment des modèles SQL.
La matrice `fixtures/acceptance_matrix.json` relie la recette aux critères
A01 à A18 du cahier des charges. Aucun benchmark ou connecteur absent n’est
présenté comme validé.

## Exécuter sur Windows

Arrêter Streamlit avec Ctrl+C dans son terminal. Garder PostgreSQL et Docker
Desktop démarrés. Télécharger `money-trail-recette-v1.zip`, puis :

```powershell
Set-Location C:\Users\HP\Documents\money-trail
Expand-Archive -LiteralPath "$HOME\Downloads\money-trail-recette-v1.zip" -DestinationPath . -Force
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test_all.ps1
```

Le paquet complète le projet existant. Il ne contient ni `.env`, ni compte,
ni migration modifiée, ni CSV de référence à remplacer. Le script installe
ensemble les dépendances déjà verrouillées de dbt et Streamlit, puis lance
tous les groupes de recette. Prévoir plusieurs minutes selon le PC.

Tous les tests PostgreSQL écrivent dans des bases temporaires avec un nom
unique. Ces bases sont supprimées à la fin de leur groupe. Le script n’importe
pas les 47 scénarios dans la base métier et ne synchronise pas les dossiers
réels. Les empreintes de ses tables et séquences sont comparées avant/après.
Garder l’interface arrêtée évite qu’une autre session change ces empreintes.

Des builds dbt échouent volontairement pour tester les surallocations et les
sources incohérentes. Ces tests réussissent seulement si le contrôle attendu
signale le snapshot invalide. La fin doit afficher :

```text
RECETTE_IMPLEMENTEE_OK
```

Ce marqueur signifie que les tests des fonctions présentes ont réussi. Il ne
signifie pas que la totalité du MVP est livrée. Lire le rapport A01 à A18.
Un test ignoré, une préparation impossible ou un échec entraîne un code de
sortie non nul et le marqueur `RECETTE_ECHEC_OU_INCOMPLETE`.

Pour ouvrir le dernier rapport, après la recette :

```powershell
$LatestAcceptance = Get-ChildItem .\reports -Directory -Filter 'acceptance_*' | Sort-Object Name -Descending | Select-Object -First 1
Get-Content -LiteralPath (Join-Path $LatestAcceptance.FullName 'report.md')
```

Chaque exécution produit un dossier neuf dans `reports/acceptance_<date UTC>/` :

- `report.md` : bilan lisible, critères, limites et durées.
- `report.json` : tests détaillés, statuts, versions installées et empreinte du code.
- Un journal par groupe ; les erreurs restent consultables même après un échec.
- `business/artifacts/observed/` : attentes et résultats SQL des 47 scénarios.
- `business/artifacts/restore/measures.json` : durée de sauvegarde/restauration,
  taille et confirmation de concordance, si la restauration a été exécutée.

## Cas financiers

| Cas | Ce qui est vérifié |
|---|---|
| Factures | Avant/après échéance, échéance du jour ou absente, annulation et brouillon, facture future, avoir comptabilisé, avoir futur ou brouillon, surpaiement |
| Paiements | Plusieurs paiements par facture, paiement partagé, affectation annulée, paiement annulé/en attente, montants non affectés, coupure UTC et fuseaux |
| Versements | Captures éligibles, autorisation exclue, remboursements/frais multiples, ajustements signés, séparation des agrégations |
| Banque | Crédit partagé entre lots, lot reçu en deux crédits, affectation non confirmée, dates comptable/de valeur futures, deux candidats sans choix automatique |
| Couverture | Chaque composante peut être inconnue ; un fichier vide ne vaut zéro que si sa couverture est complète ; période non close |
| Dates et précision | Début inclus/fin exclue, minuit UTC exclu, jour contractuel de réception inclus dans l’attente, délai inconnu, exactitude au centime |
| Versions | Donnée reçue tardivement dans un nouveau snapshot ; ancienne source et investigation conservées |

Les rejets SQL concernent les paiements et crédits suralloués, un débit utilisé
comme crédit, un remboursement supérieur à sa capture, un remboursement lié au
mauvais lot, une période invalide et une identité métier ambiguë.
Les contrats rejettent notamment identifiant absent, lien orphelin, devise ou
entreprise étrangère au contrat, montant négatif interdit, NaN, trois décimales,
dépassement de NUMERIC(20,2), état inconnu et horodatage sans fuseau.

## Corrections incluses

Les totaux de paiements/avoirs et chacune des composantes de versement restent
NULL quand leur couverture nécessaire est incomplète. Les lignes présentes
restent visibles comme preuves observées ; elles ne certifient pas un total
complet. Une couverture manquante bloque toujours le solde ou l’écart.

Une date de réception vide est désormais acceptée par le contrat, puis affichée
« Délai à confirmer » si le versement n’est pas rapproché. Le jour de réception
prévu reste en attente jusqu’à sa fin ; la comparaison intervient après ce jour.
La règle de coupure est le minuit UTC suivant la date de contrôle.

Le rôle `admin` conserve revue, commentaires, propositions, clôture et
synchronisation, mais ne valide plus financièrement. Il faut le rôle `reviewer`
avec un compte distinct du proposant. Pour créer ce compte local si nécessaire :

```powershell
.\.venv\Scripts\python.exe .\scripts\interface_setup.py --username validateur --role reviewer
```

Le mot de passe est saisi interactivement. Le compte `ilyass` et son mot de passe
restent présents. Les comptes créés par les tests restent uniquement dans leurs
bases temporaires. Le CLI de développement conserve un accès direct à la base ;
ce paquet ne fournit pas encore les droits PostgreSQL et SSO de production.

Les preuves contrôlent maintenant la concordance entre payload, empreinte,
numéro de ligne et octets du CSV conservé, puis le manifeste et le fingerprint
du snapshot. Un payload et son hash modifiés sans changer le fichier source
ne peuvent plus être présentés comme une ligne d’origine vérifiée.
Ce contrôle de cohérence ne rend pas l’audit inviolable face à un administrateur
de base pouvant remplacer toutes les sources et empreintes.

## Sauvegarde et concurrence

La restauration utilise les outils PostgreSQL présents dans le conteneur,
`pg_dump --format=custom` puis `pg_restore --exit-on-error`. L’archive contient
uniquement une base temporaire synthétique ; la destination est une deuxième
base temporaire. Les contenus des tables et les séquences sont comparés,
y compris comptes, décisions, historique, résultats, fichiers et lignes brutes.
Le test vérifie également que les dossiers peuvent être reconstruits après
restauration. Si Docker CLI manque, ce test est explicitement non exécuté.

Deux threads avec connexions distinctes soumettent le même import simultanément :
un import et un doublon ignoré doivent être observés. Un autre test soumet
approbation et rejet simultanément sur la même révision : une seule décision
est enregistrée ; l’autre reçoit un conflit. Les délais de ces tests sont bornés.

## Ce qui reste dans le cahier des charges

A04 reste partiel pour les lignes détaillées de facture. A09 reste partiel pour
le classement de candidats et le multi-entreprises/multi-devises. A12 reste
partiel pour Odoo, fraîcheur et quarantaine par ligne. La publication atomique
est ajoutée dans publication-v1 et doit réussir ses tests PostgreSQL sur le PC.
A13 ne compare pas encore deux versions de règle.
A15 requiert une recette navigateur/base réelle et clavier.
A17 n’a pas encore de benchmark des trois volumes ni de pagination serveur.
A18 conserve les versions, mais ne relie ni ne rouvre automatiquement les
investigations après changement de source. Ces points restent des travaux à
réaliser, pas des succès de test.

## Vérifications avant livraison

Les tests sans PostgreSQL et les parcours AppTest sont exécutés dans l’environnement
de préparation ; leurs résultats exacts sont consignés dans le paquet.
La syntaxe SQL et le parsing dbt sont vérifiés. Aucun serveur PostgreSQL n’est
disponible ici : la recette métier, les accès réels, la concurrence et la
restauration doivent être exécutés sur le PC avec le script fourni.

Pour une exécution sans base (qui ne valide pas le moteur SQL) :

```powershell
.\.venv\Scripts\python.exe .\scripts\acceptance.py run
```

Pour relancer l’interface après les tests :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\refresh_interface.ps1
```

## Sources

- Cahier des charges Money Trail, critères A01 à A18, modèles et fixtures du projet.
- [PostgreSQL 17 — pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html).
- [PostgreSQL 17 — pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).
- [Streamlit — AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).
