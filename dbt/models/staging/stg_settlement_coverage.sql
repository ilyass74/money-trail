select b.import_batch_id, c->>'company_id' as company_id,
       c->>'currency' as currency, c->>'batch_id' as settlement_id,
       c->>'entity' as entity, (c->>'complete')::boolean as complete,
       c->>'evidence' as evidence
from {{ ref('stg_import_batches') }} b
cross join lateral jsonb_array_elements(b.manifest->'settlement_coverage') c
