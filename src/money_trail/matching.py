"""Candidats explicables ; aucune affectation ni décision automatique."""
from decimal import Decimal
from .publication import read_publication
from .investigation import _rows


def bank_candidates(db,batch_id,publication_id,object_id,limit=20):
    if type(limit) is not int or not 1<=limit<=50:raise ValueError('Limite invalide.')
    d=read_publication(db,batch_id,publication_id,kind='settlement',object_id=object_id)['dossiers'][0]
    r=d['result']
    if r['expected_amount'] is None or r['received_amount'] is None:return []
    remaining=Decimal(r['expected_amount'])-Decimal(r['received_amount'])
    if remaining<=0:return []
    # Restes disponibles : les allocations pending ne sont jamais doublement proposées.
    rows=_rows(db,'''WITH allocations AS (
      SELECT payload->>'movement_id' AS movement_id,sum((payload->>'amount')::numeric) AS reserved
      FROM raw.source_records a JOIN meta.import_files f USING(file_id)
      WHERE f.batch_id=%s AND f.entity='bank_allocations' AND a.payload->>'state' IN ('confirmed','pending')
      GROUP BY 1
    ), available AS (
      SELECT m.record_id,m.source_id,m.payload,
        (m.payload->>'amount')::numeric-coalesce(a.reserved,0) AS available
      FROM raw.source_records m JOIN meta.import_files f USING(file_id)
      LEFT JOIN allocations a ON a.movement_id=m.source_id
      WHERE f.batch_id=%s AND f.entity='bank_movements' AND m.company_id=%s AND m.payload->>'currency'=%s
       AND (m.payload->>'booked_on')::date<=%s::date AND (m.payload->>'value_on')::date<=%s::date
    ) SELECT *, (payload->>'reference'=%s) AS exact_reference,abs(available-%s::numeric) AS amount_delta
      FROM available WHERE available>0
      AND (%s::date IS NULL OR abs((payload->>'value_on')::date-%s::date)<=14)
      ORDER BY (payload->>'reference'=%s) DESC,abs(available-%s::numeric),source_id LIMIT %s''',
      (batch_id,batch_id,r['company_id'],r['currency'],r['control_on'],r['control_on'],object_id,str(remaining),
       r['expected_receipt_on'],r['expected_receipt_on'],object_id,str(remaining),limit))
    return [dict(record_id=row['record_id'],movement_id=row['source_id'],available=str(row['available']),
                 amount_delta=str(row['amount_delta']),reference=row['payload']['reference'],
                 confidence='reference_exacte_a_verifier' if row['exact_reference'] else 'montant_date_uniquement_identite_non_confirmee',
                 rank=i,reasons=['Même entreprise et devise','Crédit disponible après allocations',
                                 'Référence exacte' if row['exact_reference'] else 'Identité à confirmer'],
                 automatic_allocation=False) for i,row in enumerate(rows,1)]
