select
  r.record_id,
  r.file_id,
  f.batch_id as import_batch_id,
  r.row_number,
  r.company_id,
  r.source_system,
  r.source_id,
  b.control_on,
  r.payload->>'currency' as currency,
  (r.payload->>'period_start')::timestamptz as period_start,
  (r.payload->>'period_end')::timestamptz as period_end,
  nullif(r.payload->>'expected_receipt_on', '')::date as expected_receipt_on
from {{ source('raw', 'source_records') }} r
join {{ source('meta', 'import_files') }} f on f.file_id = r.file_id
join {{ ref('stg_import_batches') }} b on b.import_batch_id = f.batch_id
where f.entity = 'settlement_batches'
