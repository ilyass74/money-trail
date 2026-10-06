# Vérifications de préparation — publication v1

Exécution : 2026-10-05T19:02:54.512244+00:00.
Environnement : Linux, Python 3.12.14.
Code contrôlé SHA-256 : `aaa70c10dcd38f73d9aeab77b053adafd43e0dec28c5e36606c0e36fd123d3bf`.

| Contrôle | Résultat observé |
|---|---|
| Tests Python, contrats et artefacts de publication | 65 réussis |
| Parcours Streamlit, messages d’échec et versions archivées | 18 réussis |
| Parsing dbt normal et avec schémas candidats | 2 réussis |
| Syntaxe PostgreSQL, sans exécution | 5 migrations et 120 requêtes constantes acceptées |
| Migrations 001 à 004 | Octets identiques aux paquets déjà livrés |
| Tests PostgreSQL/dbt supplémentaires | 13 découverts ; non exécutés ici |
| Recette complète prévue sur le PC | 179 tests, dont 94 nécessitent PostgreSQL |
| PowerShell | Scripts relus ; non exécutés sur Linux |

Total réellement exécuté dans cet environnement : **85 tests réussis, 0 échec**.
Le marqueur local est `VERIFICATIONS_LOCALES_OK_SQL_NON_EXECUTE`.
Les nouveaux tests SQL, le rollback réel, la concurrence et la restauration des
publications restent à exécuter sur le PC. Le script arrête l’installation avant
la publication du projet si un groupe échoue ou est incomplet.

Les 152 tests du paquet précédent ont réussi sur le PC de l’utilisateur,
sans test ignoré, selon son rapport du 2026-10-05T18:15:55.071452Z.
Cette preuve concerne la version précédente ; elle ne valide pas les ajouts SQL.

A12 reste partiel (Odoo, fraîcheur, quarantaine), A13/A18 restent partiels.
Les limites détaillées sont dans `fixtures/acceptance_matrix.json`.
La lecture des archives garde les versions de règles actuelles v1 ; aucune
comparaison de nouvelles règles ni réouverture automatique n’est annoncée.
