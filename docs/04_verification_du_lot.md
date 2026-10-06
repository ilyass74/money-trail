# Vérification du dossier de démarrage

Vérification réalisée le 5 octobre 2026 sur l'environnement de préparation.

| Contrôle | Résultat |
|---|---|
| Génération du jeu synthétique | REFERENCE_OK ; 12 CSV ; 26 lignes métier |
| Tests des fixtures | 7 tests réussis |
| Colonnes et types des sources | Contrôlés par le vérificateur |
| Liens entre documents | Contrôlés dans le même périmètre entreprise et devise |
| Empreintes des fichiers | Contrôlées à partir du manifeste |
| Source de frais inconnue face au zéro confirmé | Couvertures distinctes pour LOT003 et LOT004 |
| Configuration YAML | Lecture et contrôles statiques réalisés |
| Docker Desktop et PostgreSQL sur le PC Windows | À vérifier avec les commandes du README |
| Script PowerShell | Revu ; exécution à confirmer sur le PC Windows |
| Moteur SQL et dbt | Prochain jalon ; aucun résultat d'exécution annoncé |

L'environnement de préparation n'a pas de moteur Docker ni de PowerShell. Le dossier n'annonce donc pas un démarrage Windows déjà vérifié. La sortie de `docker compose ps` et la requête des six schémas fourniront cette confirmation.

Les résultats attendus sont des cas synthétiques documentés, pas des chiffres provenant d'une entreprise réelle.
