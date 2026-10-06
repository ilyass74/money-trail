select record_id from {{ ref('stg_settlement_batches') }}
where period_end<=period_start
