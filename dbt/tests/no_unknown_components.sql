-- Un composant ne peut être présenté comme un total connu sans couverture.
select 'invoice' as kind,i.import_batch_id,i.invoice_id as object_id
from {{ ref('invoice_reconciliation') }} i
join {{ ref('stg_import_batches') }} b using(import_batch_id)
where (((b.manifest->'invoice_coverage'->>'erp_payments')::boolean is not true
     or (b.manifest->'invoice_coverage'->>'invoice_allocations')::boolean is not true)
     and i.allocated_amount is not null)
   or ((b.manifest->'invoice_coverage'->>'credit_notes')::boolean is not true and i.credit_amount is not null)
union all
select 'settlement',s.import_batch_id,s.batch_id
from {{ ref('settlement_reconciliation') }} s
join {{ ref('stg_settlement_coverage') }} c
on c.import_batch_id=s.import_batch_id and c.company_id=s.company_id
and c.currency=s.currency and c.settlement_id=s.batch_id
where c.complete is not true and (
 (c.entity='processor_payments' and s.captured_amount is not null)
 or (c.entity='refunds' and s.refunded_amount is not null)
 or (c.entity='fees' and s.fees_amount is not null)
 or (c.entity='adjustments' and s.adjustments_amount is not null)
 or (c.entity in ('bank_movements','bank_allocations') and s.received_amount is not null))
