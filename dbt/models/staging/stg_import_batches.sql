select batch_id as import_batch_id, company_id, currency, control_on,
       manifest, fingerprint, ingested_at
from {{ source('meta', 'import_batches') }}
where contract_version in ('reference-v1','finance-v1')
{% if var('mt_batch_ids', []) %}
  and batch_id in (
  {% for batch_id in var('mt_batch_ids') %}
    '{{ batch_id }}'::uuid{{ ',' if not loop.last }}
  {% endfor %}
  )
{% endif %}
