with allocations as (
  select a.import_batch_id, a.company_id, a.currency, a.invoice_id,
         sum(a.amount) as allocated_amount
  from {{ ref('stg_invoice_allocations') }} a
  join {{ ref('stg_erp_payments') }} p
    on p.import_batch_id=a.import_batch_id and p.company_id=a.company_id
   and p.currency=a.currency and p.source_id=a.payment_id
  where a.state='confirmed' and p.state='confirmed'
    and p.paid_at < ((a.control_on + 1)::timestamp at time zone 'UTC')
  group by 1,2,3,4
), credits as (
  select import_batch_id, company_id, currency, invoice_id, sum(amount) as credit_amount
  from {{ ref('stg_credit_notes') }}
  where state='posted' and issued_on <= control_on
  group by 1,2,3,4
)
select i.import_batch_id, i.company_id, i.currency, i.source_id as invoice_id,
       i.record_id as invoice_record_id, i.control_on, i.due_on,
       i.total_amount as invoice_amount,
       coalesce(a.allocated_amount,0::numeric) as allocated_amount,
       coalesce(c.credit_amount,0::numeric) as credit_amount,
       (b.manifest->'invoice_coverage'->>'erp_payments')::boolean
       and (b.manifest->'invoice_coverage'->>'invoice_allocations')::boolean as allocations_complete,
       (b.manifest->'invoice_coverage'->>'credit_notes')::boolean as credits_complete,
       (b.manifest->'invoice_coverage'->>'invoices')::boolean
       and (b.manifest->'invoice_coverage'->>'erp_payments')::boolean
       and (b.manifest->'invoice_coverage'->>'invoice_allocations')::boolean
       and (b.manifest->'invoice_coverage'->>'credit_notes')::boolean as sources_complete
from {{ ref('stg_invoices') }} i
join {{ ref('stg_import_batches') }} b using (import_batch_id)
left join allocations a on a.import_batch_id=i.import_batch_id
  and a.company_id=i.company_id and a.currency=i.currency and a.invoice_id=i.source_id
left join credits c on c.import_batch_id=i.import_batch_id
  and c.company_id=i.company_id and c.currency=i.currency and c.invoice_id=i.source_id
where i.state='posted' and i.issued_on <= i.control_on
