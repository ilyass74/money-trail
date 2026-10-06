# Contrats des sources de référence

Version `reference-v1`. Entreprise fictive `DEMO_MA`, devise MAD, contrôle au **5 octobre 2026**. Toutes les données sont synthétiques. Les horodatages sont en UTC et les échéances sont des dates métier. La tolérance du jeu est nulle.

Ces conventions décrivent le simulateur. Les champs exacts d'Odoo seront vérifiés avant d'écrire le connecteur ; aucun fichier ici n'est présenté comme un export Odoo réel.

## Granularités

| Fichier | Une ligne représente | Clés et liens |
|---|---|---|
| orders.csv | Une commande | source_id ; contexte commercial |
| invoices.csv | Une facture | source_id ; order_id vers orders |
| erp_payments.csv | Un règlement confirmé dans l'ERP | source_id |
| invoice_allocations.csv | Un montant affecté à une facture | invoice_id et payment_id |
| credit_notes.csv | Un avoir imputé à une facture | invoice_id |
| settlement_batches.csv | Un lot de versement | source_id ; période et date attendue |
| processor_payments.csv | Un paiement capturé et éligible au lot | batch_id |
| refunds.csv | Un remboursement du lot | batch_id et payment_id |
| fees.csv | Des frais documentés du lot | batch_id |
| adjustments.csv | Un ajustement signé documenté | batch_id ; reason |
| bank_movements.csv | Un mouvement bancaire | source_id ; reference |
| bank_allocations.csv | Un montant bancaire affecté à un lot | batch_id et movement_id |

Chaque identifiant est associé à `company_id` et `source_system`. Les relations doivent respecter l'entreprise et la devise. Les données du prestataire et les règlements ERP constituent deux jeux de contrôle indépendants ; une liaison entre ces jeux sera ajoutée après validation du mapping des sources.

## Formats et signes

- CSV UTF-8, séparateur virgule, décimale point, montant écrit comme chaîne avec deux décimales.
- Montants de factures, paiements, allocations, remboursements et frais positifs. Les remboursements et frais seront soustraits par la règle de versement.
- Les ajustements et mouvements bancaires peuvent être signés ; le jeu initial contient uniquement des crédits bancaires.
- Une date vide n'est pas remplacée par la date du jour. Le contrat autorise une échéance de facture inconnue.
- Un fichier sans événements conserve son en-tête. Son existence ne suffit pas à conclure qu'il couvre une période.

## Manifeste de couverture

`manifest.json` décrit le nombre de lignes et l'empreinte SHA-256 de chaque fichier. Il déclare aussi la couverture des sources nécessaires par lot. Dans ce simulateur, cette couverture est fournie par le scénario, pas déduite du nombre de lignes.

Pour `LOT003`, la couverture de `fees` est fausse : les frais sont **inconnus**. Pour `LOT004`, elle est vraie et il n'existe aucune ligne de frais : les frais sont **zéro confirmé**. Le futur moteur doit bloquer le calcul de LOT003 et accepter le zéro de LOT004.

Les avoirs et ajustements ont zéro événement dans ce jeu, avec couverture déclarée complète. Les variantes plus complexes seront ajoutées avec leurs résultats attendus dans les prochains jalons.

## Conservation et versions

Le générateur refuse d'écraser un dossier non vide. Les données de référence sont versionnées avec le code et servent à la recette. Les futurs imports réels conserveront les preuves et les versions dans la couche brute ; ils n'écraseront pas ces fixtures.
