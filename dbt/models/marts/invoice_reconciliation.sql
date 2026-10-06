{% set policy = var('mt_rule_policy', {'version':'v1','invoice_tolerance':'0.00','settlement_tolerance':'0.00'}) %}
{% set tolerance = policy['invoice_tolerance'] %}
with amounts as (
  select *, case when sources_complete is true then
    invoice_amount - allocated_amount - credit_amount end as balance
  from {{ ref('core_invoice_amounts') }}
)
select import_batch_id,company_id,currency,invoice_id,invoice_record_id,control_on,due_on,
  invoice_amount,
  case when allocations_complete is true then allocated_amount end as allocated_amount,
  case when credits_complete is true then credit_amount end as credit_amount,
  sources_complete,balance,case
  when sources_complete is not true then 'calcul_bloque'
  when abs(balance) <= {{ tolerance }}::numeric then 'soldee'
  when balance<0 then 'surpaiement'
  when due_on is null then 'echeance_inconnue'
  when due_on < control_on then 'en_retard'
  else 'solde_en_attente' end as status,
  case when sources_complete is true then 'complete' else 'donnees_incompletes' end as quality,
  'invoice-{{ policy['version'] }}'::text as rule_version, {{ tolerance }}::numeric(20,2) as tolerance,
  current_timestamp as calculated_at
from amounts
