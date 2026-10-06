select
  r.record_id,
  r.file_id,
  f.batch_id as import_batch_id,
  r.row_number,
  r.company_id,
  r.source_system,
  r.source_id,
  b.control_on,
  r.payload->>'state' as state,
  r.payload->>'currency' as currency,
  (r.payload->>'amount')::numeric(20,2) as amount,
  (r.payload->>'paid_at')::timestamptz as paid_at
from {{ source('raw', 'source_records') }} r
join {{ source('meta', 'import_files') }} f on f.file_id = r.file_id
join {{ ref('stg_import_batches') }} b on b.import_batch_id = f.batch_id
where f.entity = 'erp_payments'
