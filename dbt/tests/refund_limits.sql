select r.import_batch_id,r.payment_id
from {{ ref('stg_refunds') }} r
join {{ ref('stg_processor_payments') }} p
on p.import_batch_id=r.import_batch_id and p.company_id=r.company_id
and p.currency=r.currency and p.source_id=r.payment_id
group by r.import_batch_id,r.company_id,r.currency,r.payment_id,p.amount
having sum(r.amount)>p.amount
