-- Le contrat v1 lie les objets par entreprise, devise et identifiant.
-- Deux systèmes ne doivent pas rendre cet identifiant ambigu.
with identities as (
{% for entity in ['orders','invoices','erp_payments','invoice_allocations','credit_notes','settlement_batches','processor_payments','refunds','fees','adjustments','bank_movements','bank_allocations'] %}
select '{{ entity }}' as entity,import_batch_id,company_id,currency,source_id
from {{ ref('stg_' ~ entity) }}
{% if not loop.last %}union all{% endif %}
{% endfor %}
)
select entity,import_batch_id,company_id,currency,source_id
from identities group by 1,2,3,4,5 having count(*)<>1
