select
  r.record_id,
  r.file_id,
  f.batch_id as import_batch_id,
  r.row_number,
  r.company_id,
  r.source_system,
  r.source_id,
  b.control_on,
  r.payload->>'order_id' as order_id,
  r.payload->>'state' as state,
  r.payload->>'currency' as currency,
  (r.payload->>'total_amount')::numeric(20,2) as total_amount,
  nullif(r.payload->>'issued_on', '')::date as issued_on,
  nullif(r.payload->>'due_on', '')::date as due_on
from {{ source('raw', 'source_records') }} r
join {{ source('meta', 'import_files') }} f on f.file_id = r.file_id
join {{ ref('stg_import_batches') }} b on b.import_batch_id = f.batch_id
where f.entity = 'invoices'
