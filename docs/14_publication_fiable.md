# Publication fiable — version 1

Une tentative de calcul travaille dans trois schémas PostgreSQL propres à son
identifiant. Elle ne remplace pas les tables utilisées par l'interface. Après le
build complet, Money Trail vérifie les 18 modèles, tous les tests dbt, les
identifiants des sources, leurs octets et les contributions de chaque dossier.
Une seule transaction archive les résultats, leurs preuves et la publication
visible. Une erreur avant son commit laisse la publication précédente visible.

## Installer sur le projet existant

Arrêter Streamlit avec **Ctrl+C** dans son terminal ; laisser Docker Desktop et
PostgreSQL ouverts. Télécharger l'archive avant d'exécuter :

```powershell
Set-Location C:\Users\HP\Documents\money-trail
Expand-Archive -LiteralPath "$HOME\Downloads\money-trail-publication-v1.zip" -DestinationPath . -Force
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\publication_demo.ps1
```

Le script lance la recette complète dans des bases temporaires. Il applique
ensuite la nouvelle migration **005_publications** au projet et publie son
dernier import. Les migrations 001 à 004, les sources de référence, `.env`,
le compte existant et les dossiers ne sont pas modifiés. Aucune synchronisation
du workflow n'est déclenchée par la publication. Aucun mot de passe à recréer.

Attendre `RECETTE_IMPLEMENTEE_OK`, puis `PUBLICATION_PUBLISHED`. Si le dernier
import est toujours la référence, `REFERENCE_RESULTS_OK` apparaît également.
Une erreur interrompt le script ; ne pas conclure à une publication réussie à
partir de la seule présence d'un dossier de rapport.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\refresh_interface.ps1
```

L'interface affiche la version publiée et son heure **UTC**, ainsi qu'un sélecteur
des versions historiques. Un calcul échoué ou en cours affiche un message et
laisse les dossiers archivés consultables. Les imports échoués depuis cette
publication sont signalés séparément du résultat financier. Un montant inconnu
reste inconnu ; un calcul validé peut contenir un dossier financièrement bloqué
par une couverture incomplète.

## Sources et versions

Le candidat prend le dernier snapshot importé de chaque périmètre supporté,
selon `ingested_at`, avec une seule version par entreprise/devise/contrat.
La démonstration reste limitée à `DEMO_MA`, MAD et `reference-v1`. Les anciens
imports, y compris un import refusé par dbt, ne sont pas additionnés au nouveau
snapshot. Une nouvelle source valide peut ainsi rétablir la publication.

Pour republier explicitement une source historique :

```powershell
.\.venv\Scripts\python.exe .\scripts\run_dbt.py build --batch-id IDENTIFIANT_DU_SNAPSHOT
```

Chaque publication crée une nouvelle version, même si sa source est identique.
Les numéros de version peuvent comporter des trous après un rollback ; seule
une publication effectivement validée apparaît dans le sélecteur.

Les dossiers contiennent l'identifiant et la date de publication, la version
de règle, l'empreinte du code, les lignes sources, les formules et les preuves
du build correspondant. `run_results.json` et `manifest.json` sont conservés en
base avec leurs empreintes. La consultation ne dépend plus de `dbt/target`, ni
des vues candidates nettoyées après chaque tentative.

Les commandes `investigate.py` et `workflow.py sync` utilisent la dernière
publication validée contenant le snapshot demandé. Leur option
`--publication-id` permet de choisir une publication précise. Les dossiers
existants gardent leur preuve d'ouverture et leur historique ; une nouvelle
publication ne modifie aucune décision ni écriture comptable.

## Concurrence et reprise

Un verrou de session PostgreSQL sérialise les publications de la même base.
Un deuxième lancement est refusé sans démarrer dbt. Après interruption du
processus, le lancement suivant marque l'ancienne tentative en échec et nettoie
ses espaces de calcul. Un échec de nettoyage est consigné et réessayé au lancement
suivant. Le nettoyage ne supprime que les schémas générés pour une tentative.

Les archives rejettent les modifications ordinaires. Ce garde protège des
accidents ; il ne limite pas le superutilisateur PostgreSQL utilisé pour cette
instance locale. Les scripts CLI historiques gardent un acteur déclaratif.

## Tests inclus

La recette ajoute 13 scénarios avec le véritable PostgreSQL/dbt : build en échec,
lecture pendant un calcul et avant commit, reprise avec une nouvelle source,
conservation des versions et du workflow, rollback juste avant commit, source
corrompue, import échoué, deuxième publication concurrente, processus interrompu,
lecture indépendante des sources courantes, intégrité des archives, lecture avec
session réelle et restauration réelle dans une autre base.

Les contrôles Python refusent les artefacts partiels, les périmètres mélangés et
les modèles hors du schéma candidat. AppTest vérifie les messages d'échec et de
calcul en cours, la date, les valeurs archivées et la sélection de deux versions
du même snapshot. Les tests de rejet échouent volontairement au niveau dbt et
ne passent que si la publication visible et ses archives sont conservées.

La preuve d'exécution sur le PC est `reports/acceptance_.../report.md` et ses
journaux. Les tests SQL ajoutés ne sont pas présentés comme exécutés sur Linux
sans serveur PostgreSQL. Le script Windows et la migration restent à vérifier
sur le PC avant de conclure au succès de la mise à jour.

A12 reste partiel : connecteur Odoo, fraîcheur par source et quarantaine par
ligne absents. A13/A18 : comparaison de règles, succession et réouverture de
dossiers restent à développer. Aucun benchmark ou déploiement entreprise
n'est ajouté dans cette étape.

Références :

- [dbt — schémas personnalisés](https://docs.getdbt.com/docs/build/custom-schemas).
- [dbt — variables](https://docs.getdbt.com/reference/dbt-jinja-functions/var).
- [PostgreSQL 17 — transactions](https://www.postgresql.org/docs/17/tutorial-transactions.html).
- [PostgreSQL 17 — verrous](https://www.postgresql.org/docs/17/explicit-locking.html).
