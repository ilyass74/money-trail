with captured as (
 select s.import_batch_id,s.company_id,s.currency,s.batch_id,sum(s.amount) as amount
 from {{ ref('stg_processor_payments') }} s
 join {{ ref('stg_settlement_batches') }} b
 on b.import_batch_id=s.import_batch_id and b.company_id=s.company_id
 and b.currency=s.currency and b.source_id=s.batch_id
 where s.state='captured' and s.captured_at >= b.period_start and s.captured_at < b.period_end
 and s.captured_at < ((s.control_on+1)::timestamp at time zone 'UTC')
 group by 1,2,3,4
),
refunded as (
 select s.import_batch_id,s.company_id,s.currency,s.batch_id,sum(s.amount) as amount
 from {{ ref('stg_refunds') }} s
 join {{ ref('stg_settlement_batches') }} b
 on b.import_batch_id=s.import_batch_id and b.company_id=s.company_id
 and b.currency=s.currency and b.source_id=s.batch_id
 where true and s.refunded_at >= b.period_start and s.refunded_at < b.period_end
 and s.refunded_at < ((s.control_on+1)::timestamp at time zone 'UTC')
 group by 1,2,3,4
),
fees as (
 select s.import_batch_id,s.company_id,s.currency,s.batch_id,sum(s.amount) as amount
 from {{ ref('stg_fees') }} s
 join {{ ref('stg_settlement_batches') }} b
 on b.import_batch_id=s.import_batch_id and b.company_id=s.company_id
 and b.currency=s.currency and b.source_id=s.batch_id
 where true and s.charged_at >= b.period_start and s.charged_at < b.period_end
 and s.charged_at < ((s.control_on+1)::timestamp at time zone 'UTC')
 group by 1,2,3,4
),
adjustments as (
 select s.import_batch_id,s.company_id,s.currency,s.batch_id,sum(s.amount) as amount
 from {{ ref('stg_adjustments') }} s
 join {{ ref('stg_settlement_batches') }} b
 on b.import_batch_id=s.import_batch_id and b.company_id=s.company_id
 and b.currency=s.currency and b.source_id=s.batch_id
 where true and s.adjusted_at >= b.period_start and s.adjusted_at < b.period_end
 and s.adjusted_at < ((s.control_on+1)::timestamp at time zone 'UTC')
 group by 1,2,3,4
),
received as (
 select a.import_batch_id,a.company_id,a.currency,a.batch_id,sum(a.amount) as amount
 from {{ ref('stg_bank_allocations') }} a
 join {{ ref('stg_bank_movements') }} m
 on m.import_batch_id=a.import_batch_id and m.company_id=a.company_id
 and m.currency=a.currency and m.source_id=a.movement_id
 where a.state='confirmed' and m.amount>0 and m.booked_on<=a.control_on
 and m.value_on<=a.control_on
 group by 1,2,3,4
),
coverage as (
 select import_batch_id,company_id,currency,settlement_id,
 bool_and(complete) filter (where entity='processor_payments') as captured_complete,
 bool_and(complete) filter (where entity='refunds') as refunds_complete,
 bool_and(complete) filter (where entity='fees') as fees_complete,
 bool_and(complete) filter (where entity='adjustments') as adjustments_complete,
 count(*) filter (where entity in ('processor_payments','refunds','fees','adjustments'))=4
 and bool_and(complete) filter (where entity in ('processor_payments','refunds','fees','adjustments')) as expected_complete,
 count(*) filter (where entity in ('bank_movements','bank_allocations'))=2
 and bool_and(complete) filter (where entity in ('bank_movements','bank_allocations')) as bank_complete,
 string_agg(entity, ', ' order by entity) filter (where not complete) as missing_sources
 from {{ ref('stg_settlement_coverage') }} group by 1,2,3,4
)
select b.import_batch_id,
b.company_id,
b.currency,
b.source_id as batch_id,
b.record_id as settlement_record_id,
b.control_on,
b.period_start,
b.period_end,
b.expected_receipt_on,
c.expected_complete,
c.bank_complete,
c.captured_complete,
c.refunds_complete,
c.fees_complete,
c.adjustments_complete,
c.missing_sources,
coalesce(captured.amount,0::numeric) as captured_amount,
coalesce(refunded.amount,0::numeric) as refunded_amount,
coalesce(fees.amount,0::numeric) as fees_amount,
coalesce(adjustments.amount,0::numeric) as adjustments_amount,
coalesce(received.amount,0::numeric) as received_amount
from {{ ref('stg_settlement_batches') }} b
left join coverage c on c.import_batch_id=b.import_batch_id and c.company_id=b.company_id and c.currency=b.currency and c.settlement_id=b.source_id
left join captured on captured.import_batch_id=b.import_batch_id and captured.company_id=b.company_id and captured.currency=b.currency and captured.batch_id=b.source_id
left join refunded on refunded.import_batch_id=b.import_batch_id and refunded.company_id=b.company_id and refunded.currency=b.currency and refunded.batch_id=b.source_id
left join fees on fees.import_batch_id=b.import_batch_id and fees.company_id=b.company_id and fees.currency=b.currency and fees.batch_id=b.source_id
left join adjustments on adjustments.import_batch_id=b.import_batch_id and adjustments.company_id=b.company_id and adjustments.currency=b.currency and adjustments.batch_id=b.source_id
left join received on received.import_batch_id=b.import_batch_id and received.company_id=b.company_id and received.currency=b.currency and received.batch_id=b.source_id
