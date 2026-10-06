# Cas de référence du premier jalon

Les résultats sont écrits à la main dans `fixtures/expected_results.json`. Le générateur ne les calcule pas. Ils seront comparés aux modèles SQL et dbt lors du jalon du moteur métier.

| Objet | Entrées principales | Résultat attendu au 5 octobre 2026 |
|---|---|---|
| FAC001 | Facture 1 000 ; paiements alloués 600 et 300 ; échéance 20 octobre | Solde 100 MAD, en attente. Aucune alerte de retard. |
| LOT001 | Capture 1 000 ; remboursement 100 ; frais 20 ; banque 850 | Attendu 880, écart -30 MAD, cause non identifiée. |
| LOT002 | Capture 1 000 ; remboursement 100 ; frais 20 ; banque 880 | Attendu 880, écart nul, rapproché. |
| LOT003 | Capture 1 000 ; banque 950 ; source de frais incomplète | Calcul bloqué. Attendu et écart restent inconnus. |
| LOT004 | Capture 1 000 ; aucun remboursement ni frais ; couverture complète ; banque 1 000 | Attendu 1 000, écart nul, rapproché. |

Le contrôle facture est distinct du contrôle de versement. Des frais de prestataire ne sont pas soustraits du montant dû par le client.

## Correspondance avec le cahier des charges

- FAC001 prépare A01 et les règles R01 à R04.
- LOT002 prépare A05 ; LOT001 prépare A06.
- LOT003 et LOT004 préparent A07 et R10.

Cette table décrit le premier jalon. La [recette étendue](12_recette_complete.md)
ajoute 47 scénarios financiers et une matrice de couverture A01 à A18.
Les critères non réalisés restent indiqués dans le rapport ; ce premier lot
ne constitue pas la recette complète du MVP.

## Ce qui est vérifié à ce stade

Le vérificateur contrôle les formats, références, empreintes, nombres de lignes et déclarations de couverture. Les tests vérifient aussi qu'un fichier modifié, un lien absent ou une couverture supprimée sont détectés. Ils ne démontrent pas encore l'exécution des futurs calculs dans PostgreSQL.
