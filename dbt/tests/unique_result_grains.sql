select 'invoice' as kind,import_batch_id,company_id,currency,invoice_id as id
from {{ ref('invoice_reconciliation') }} group by 1,2,3,4,5 having count(*)<>1
union all
select 'settlement',import_batch_id,company_id,currency,batch_id
from {{ ref('settlement_reconciliation') }} group by 1,2,3,4,5 having count(*)<>1
