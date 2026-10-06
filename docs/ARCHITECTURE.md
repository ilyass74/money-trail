# Architecture and calculation semantics

## Data and publication

Python imports source bundles with manifests and coverage declarations. PostgreSQL preserves source records and file evidence. dbt builds staging views, component aggregates and reconciliation results. Publication archives a validated result version for the UI; failed later processing keeps the earlier publication available.

| Schema | Purpose |
|---|---|
| raw | Imported source records |
| staging | Typed and normalized input |
| core | Component amounts |
| marts | Reconciliation results |
| app | Human workflow and accounts |
| meta | Import metadata and coverage |

Published runs can use isolated version-specific schemas in addition to these logical layers. Do not combine different source snapshots as if they were additional business activity.

## Invoice balance

Invoice amount minus eligible confirmed payment allocations minus eligible credit notes equals remaining balance. Eligibility includes source states and control-date rules. Payment context records are evidence, not an additional payment contribution.

## Settlement reconciliation

Captured payments minus refunds minus fees plus signed adjustments produces the expected amount. Confirmed allocations linked to eligible positive bank movements produce the received amount. Received minus expected is the difference.

Company, currency, source scope and relevant dates constrain the calculation. Incomplete coverage can block the calculation; a missing component must not silently become a known zero. Bank candidates use available amounts, references and date criteria, but are not automatically allocated.

## Human workflow

The case preserves comments, cited records, proposals and decisions. Updates use expected revisions to detect stale edits. Server-side permissions and separation of proposer/reviewer constrain decisions. Administrative closure, acceptance with justification and resolution after control carry distinct meanings.

## Source code entry points

- `src/money_trail/importer.py`: source import
- `src/money_trail/odoo_source.py`, `odoo_bundle.py`: Odoo extraction and conversion
- `dbt/models/core/`: component aggregation
- `dbt/models/marts/`: final status and amount rules
- `src/money_trail/publication.py`: publication lifecycle
- `src/money_trail/investigation.py`: explanation and evidence
- `src/money_trail/local_auth.py`, `workflow.py`: permissions and workflow
- `src/money_trail/matching.py`: bank candidate suggestions
- `ui/app.py`: interface
