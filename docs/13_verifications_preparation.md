# Vérifications de préparation — recette v1

Exécution locale : 2026-10-05T18:03:13.021843+00:00.
Environnement : Linux, Python 3.12.14.
Empreinte du code contrôlé : `9225fa5a33b6f91bea4a54ffaf423e11fd4346d86461f9074ed96316af295bb2`.

| Vérification | Résultat observé |
|---|---|
| Contrats, provenance, règles Python et rapport | 57 tests réussis |
| Parcours Streamlit avec services simulés | 13 tests réussis |
| Parsing du projet dbt sans base | 1 test réussi |
| Manifeste dbt | 18 modèles et 21 contrôles de données déclarés |
| Syntaxe PostgreSQL (parseur, sans exécution) | 31 fichiers SQL et 82 requêtes Python constantes acceptés |
| Préparation de groupe avec PostgreSQL inaccessible | Aucun succès financier annoncé ; 64 tests bloqués et groupe en échec explicite |
| Tests nécessitant PostgreSQL | 81 tests découverts, non exécutés dans cet environnement |
| Script PowerShell | Relu ; non exécuté sur Linux |

Le total prévu sur le PC est de 152 tests Python/Streamlit/PostgreSQL.
Les 21 contrôles dbt sont exécutés dans les builds des tests PostgreSQL.
Les résultats SQL, les courses concurrentes et la restauration ne sont pas
présentés comme réussis avant l’exécution sur le PC.

La recette est limitée au contrat synthétique actuel. Les exigences restantes
sont consignées dans `fixtures/acceptance_matrix.json`, A01 à A18. Aucun résultat
de benchmark, de connexion Odoo réelle, de pagination ou de réouverture
automatique n’est inventé.

Sources : journaux de la préparation, code du projet, cahier des charges A01–A18.
Les références des outils sont dans `docs/12_recette_complete.md`.
