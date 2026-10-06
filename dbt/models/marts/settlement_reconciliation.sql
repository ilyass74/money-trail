{% set policy = var('mt_rule_policy', {'version':'v1','invoice_tolerance':'0.00','settlement_tolerance':'0.00'}) %}
{% set tolerance = policy['settlement_tolerance'] %}
with amounts as (
 select *, case when expected_complete is true
   and period_end <= ((control_on+1)::timestamp at time zone 'UTC')
   then captured_amount - refunded_amount - fees_amount + adjustments_amount end as expected_amount,
   case when bank_complete is true then received_amount end as bank_received_amount
 from {{ ref('core_settlement_amounts') }}
), differences as (
 select *, bank_received_amount - expected_amount as difference from amounts
)
select import_batch_id,company_id,currency,batch_id,settlement_record_id,control_on,
 period_start,period_end,expected_receipt_on,
 case when captured_complete is true then captured_amount end as captured_amount,
 case when refunds_complete is true then refunded_amount end as refunded_amount,
 case when fees_complete is true then fees_amount end as fees_amount,
 case when adjustments_complete is true then adjustments_amount end as adjustments_amount,
 expected_amount,bank_received_amount as received_amount,difference,
 missing_sources,
 case when expected_amount is null or bank_received_amount is null then 'calcul_bloque'
      when abs(difference) <= {{ tolerance }}::numeric then 'rapproche'
      when expected_receipt_on is null then 'delai_a_confirmer'
      when control_on <= expected_receipt_on then 'versement_en_attente'
      else 'ecart' end as status,
 case when expected_complete is not true or bank_complete is not true then 'donnees_incompletes'
      when expected_amount is null then 'periode_non_close' else 'complete' end as quality,
 case when abs(difference) > {{ tolerance }}::numeric then 'non_identifiee' end as cause,
 'settlement-{{ policy['version'] }}'::text as rule_version,{{ tolerance }}::numeric(20,2) as tolerance,
 current_timestamp as calculated_at
from differences
