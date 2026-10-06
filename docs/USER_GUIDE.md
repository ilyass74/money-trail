# Using Money Trail

Select a published result version in the sidebar. All conclusions depend on that version's source data and control date. Refresh reloads the app; it does not re-extract Odoo.

| Screen (French UI) | Purpose |
|---|---|
| Vue d’ensemble | Review financial indicators and priorities |
| Dossiers à suivre | Find opened cases and their progress |
| Examiner un résultat | Inspect amounts, calculations, evidence and case actions |
| Décisions à valider | Review submitted proposals |
| Sources & fiabilité | Inspect imported files, coverage and import outcomes |
| Historique des contrôles | Inspect available rule comparisons |

## A review from start to finish

1. Select an invoice or settlement from the overview.
2. Read **Comprendre le calcul** and inspect **Preuves sources**. Context records are not counted again as contributions.
3. If needed, an administrator opens cases using **Synchroniser les dossiers**. This preserves existing case history.
4. In **Actions et historique**, take ownership and start the review with a reason.
5. Record actual checks and supporting evidence. Submit a proposal only after explaining the proposed action and citing relevant records.
6. A different reviewer approves or rejects it with a reason.
7. If action is performed in the ERP, document it separately. Approval alone does not change accounting data. Resolution requires the application's subsequent-control process.

A remaining balance does not establish its cause. A zero count on the pending-decisions page does not mean the whole dataset is empty. Financial status and workflow progress are different fields.

## Roles

| Role | Core permissions |
|---|---|
| viewer | Read and download |
| analyst | Assign, start, comment, propose and administratively close |
| reviewer | Assign, comment, approve/reject, document execution, verify resolution, justify acceptance |
| admin | Synchronize cases and perform analyst actions; no financial approval/rejection |

Availability also depends on case state. Self-approval is prohibited. The server checks permissions; the UI is not the sole control.

Missing values remain unknown. Do not interpret missing coverage as a zero amount. The app's bank candidate suggestions do not prove that a payment belongs to a particular invoice.
