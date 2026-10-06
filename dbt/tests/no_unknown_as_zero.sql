select 'invoice' as kind,invoice_id as id from {{ ref('invoice_reconciliation') }}
where quality='donnees_incompletes' and (balance is not null or status<>'calcul_bloque')
union all
select 'settlement',batch_id from {{ ref('settlement_reconciliation') }}
where quality='donnees_incompletes' and (difference is not null or status<>'calcul_bloque')
