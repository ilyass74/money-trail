# Suivi des investigations — workflow local

Les dossiers explicatifs v1 sont conservés comme preuves initiales dans `app`.
Les commentaires, propositions et décisions survivent aux recalculs dbt.
Cette étape ne réalise aucune écriture dans l'ERP ou la banque et ne change
pas les montants des résultats métier.

## Démarrage

Extraire le paquet dans le projet existant, puis :

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\workflow_demo.ps1
```

Le script exécute les tests Python et quatre tests PostgreSQL dans des bases
temporaires distinctes, applique la migration 003 puis ouvre les dossiers des
anomalies de référence. Au premier lancement : deux créations (LOT001 et LOT003),
trois résultats ignorés. À la relance : zéro création et deux dossiers existants.
Les dossiers déjà suivis ne sont ni réinitialisés ni remplacés par la relance.

## Exemple de travail manuel

Commencer l'investigation et ajouter un commentaire :

```powershell
.\.venv\Scripts\python.exe .\scripts\workflow.py start --object LOT001 --actor Ilyass --note "Debut de comparaison des pieces du versement."
.\.venv\Scripts\python.exe .\scripts\workflow.py comment --object LOT001 --actor Ilyass --note "Avis de versement a obtenir pour expliquer les 30 MAD."
```

Consulter le dossier, ses propositions et son historique :

```powershell
.\.venv\Scripts\python.exe .\scripts\workflow.py show --object LOT001
```

La commande `show` affiche également les preuves JSON du calcul initial.
Les objets de type facture se sélectionnent avec `--kind invoice`.
`--batch-id <UUID>` choisit un autre snapshot ; `--case-id <UUID>` sélectionne
directement un dossier. Les identifiants UUID sont affichés par `list`.

## Propositions et décisions

Une proposition nécessite un dossier `in_review`, un acteur, une description
et une justification. Trois catégories distinctes :

| Type | Objet de la revue |
|---|---|
| source_data_review | Source absente, incomplète ou extraction à vérifier |
| allocation_review | Affectation d'un paiement ou crédit bancaire à vérifier |
| accounting_review | Proposition concernant une correction comptable à examiner |

Commande générique, à compléter avec les faits et pièces effectivement réunis :

```powershell
.\.venv\Scripts\python.exe .\scripts\workflow.py propose --object LOT001 --actor Ilyass --type allocation_review --description "Description de la proposition documentee" --justification "Pieces et raisonnement justifiant la proposition"
```

Des `--record-id <nombre>` peuvent citer les lignes déjà présentes dans le
dossier. Une référence étrangère est refusée. L'absence d'identifiant est permise
pour une source manquante : décrire alors la couverture manquante dans la justification.
Une proposition n'établit pas sa cause comme un fait et n'applique pas de correction.

Le validateur utilise `approve` ou `reject`, avec son propre `--actor` et un
`--note` obligatoire. Son nom doit différer du proposant. Une décision porte sur
la proposition, pas sur la résolution effective de l'anomalie. L'historique
conserve le motif de décision. Après rejet, `start` permet de reprendre la revue
et de déposer une nouvelle proposition sans effacer la précédente.

`close` exige une décision préalable (`approved` ou `rejected`) et une conclusion
dans `--note`. La clôture est administrative : elle ne change pas `business_status`
et ne prouve pas une correction en comptabilité. Un dossier clos est non modifiable
par ce CLI. La preuve d'une résolution effective par de nouvelles données reste
une étape distincte à développer.

## Statuts et garanties

Transitions : open → in_review → awaiting_validation → approved ou rejected
→ closed. Après rejected, retour possible vers in_review. Un commentaire conserve
le statut mais augmente la révision.

Chaque mutation verrouille le dossier en base et écrit sa modification et son
événement dans une même transaction. `--revision <nombre>` permet de refuser une
action fondée sur une révision devenue ancienne. Les propositions en attente sont
uniques par dossier. Les événements sont ajoutés, jamais remplacés par ce CLI.
Les preuves initiales ne sont pas mises à jour lors de la synchronisation ; un
nouveau snapshot ouvre un nouveau dossier, sans supprimer l'ancien.

Les noms d'acteurs sont **déclaratifs dans cette version locale**. La séparation
proposant/validateur contrôle ces noms, pas l'identité réelle de deux personnes.
Ce n'est pas une authentification ni une gestion des rôles. La future interface
devra fournir identités authentifiées et permissions avant un usage partagé.
L'utilisateur PostgreSQL de développement peut modifier directement les tables :
l'historique actuel n'est pas un registre inviolable.

## Vérification

Tests unitaires : transitions interdites, auto-validation, reprise après rejet,
clôture, acteurs et verrouillage logique d'un dossier clos. La suite PostgreSQL
vérifie la relance sans réinitialisation, la migration répétée, les décisions et
la clôture, le rejet et la nouvelle proposition, les révisions anciennes et le
rollback d'une preuve étrangère. Elle compare aussi les données brutes avant et
après les actions pour vérifier qu'elles restent inchangées.

Vérifications avant livraison : 27 tests Python réussis ; migration et 23
requêtes littérales vérifiées avec le parseur SQL PostgreSQL. Cette analyse de
syntaxe n'est pas une exécution en base. Les quatre tests PostgreSQL de cette
étape doivent être confirmés sur le PC du projet.

## Sources

- Règles fonctionnelles : cahier des charges et contrats Money Trail.
- PostgreSQL 17, verrous de lignes : https://www.postgresql.org/docs/17/explicit-locking.html
- PostgreSQL 17, contraintes : https://www.postgresql.org/docs/17/ddl-constraints.html
