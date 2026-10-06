select import_batch_id,company_id,currency,settlement_id,entity
from {{ ref('stg_settlement_coverage') }}
group by 1,2,3,4,5 having count(*)<>1
