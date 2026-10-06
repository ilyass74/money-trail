select 'payment' as kind,a.import_batch_id,a.payment_id as id
from {{ ref('stg_invoice_allocations') }} a
join {{ ref('stg_erp_payments') }} p on p.import_batch_id=a.import_batch_id
 and p.company_id=a.company_id and p.currency=a.currency and p.source_id=a.payment_id
where a.state='confirmed'
group by a.import_batch_id,a.company_id,a.currency,a.payment_id,p.amount
having sum(a.amount)>p.amount
union all
select 'bank',a.import_batch_id,a.movement_id
from {{ ref('stg_bank_allocations') }} a
join {{ ref('stg_bank_movements') }} m on m.import_batch_id=a.import_batch_id
 and m.company_id=a.company_id and m.currency=a.currency and m.source_id=a.movement_id
where a.state='confirmed'
group by a.import_batch_id,a.company_id,a.currency,a.movement_id,m.amount
having sum(a.amount)>m.amount or m.amount<=0
