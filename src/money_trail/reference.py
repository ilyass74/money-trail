"""Crée et contrôle le jeu synthétique, sans importer ni rapprocher en base."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'fixtures'
MONEY = re.compile(r'^-?\d+\.\d{2}$')
MAX_MONEY = Decimal('999999999999999999.99')
STATES = {
    'invoices': {'posted', 'draft', 'cancelled'},
    'erp_payments': {'confirmed', 'pending', 'cancelled'},
    'invoice_allocations': {'confirmed', 'pending', 'cancelled'},
    'credit_notes': {'posted', 'draft', 'cancelled'},
    'processor_payments': {'captured', 'authorized', 'cancelled', 'failed'},
    'bank_allocations': {'confirmed', 'pending', 'cancelled'},
}
COMMON = ['company_id', 'source_system', 'source_id']
HEADERS = {
    'orders': COMMON + ['customer_ref', 'currency', 'total_amount', 'ordered_at'],
    'invoices': COMMON + ['order_id', 'state', 'currency', 'total_amount', 'issued_on', 'due_on'],
    'erp_payments': COMMON + ['state', 'currency', 'amount', 'paid_at'],
    'invoice_allocations': COMMON + ['invoice_id', 'payment_id', 'currency', 'amount', 'state'],
    'credit_notes': COMMON + ['invoice_id', 'state', 'currency', 'amount', 'issued_on'],
    'settlement_batches': COMMON + ['currency', 'period_start', 'period_end', 'expected_receipt_on'],
    'processor_payments': COMMON + ['batch_id', 'state', 'currency', 'amount', 'captured_at'],
    'refunds': COMMON + ['batch_id', 'payment_id', 'currency', 'amount', 'refunded_at'],
    'fees': COMMON + ['batch_id', 'currency', 'amount', 'charged_at'],
    'adjustments': COMMON + ['batch_id', 'currency', 'amount', 'reason', 'adjusted_at'],
    'bank_movements': COMMON + ['reference', 'currency', 'amount', 'value_on', 'booked_on'],
    'bank_allocations': COMMON + ['batch_id', 'movement_id', 'currency', 'amount', 'state'],
}


EXTRA_HEADERS={'invoice_lines':COMMON+['invoice_id','currency','description','quantity','subtotal_amount','total_amount'],
               'invoice_order_links':COMMON+['invoice_id','order_id','currency']}

def validate_row(entity,row,company,currency,seen=None,business_keys=None):
    seen=seen if seen is not None else set()
    business_keys=business_keys if business_keys is not None else set()
    if None in row or any(value is None for value in row.values()):
        raise ValueError(f'Ligne tronquee ou trop longue : {entity}')
    if row['company_id'] != company or row['currency'] != currency:
        raise ValueError(f'Entreprise ou devise inattendue : {entity}')
    key = tuple(row[column] for column in COMMON)
    if any(not value for value in key) or key in seen:
        raise ValueError(f'Identifiant absent ou duplique : {entity}')
    seen.add(key)
    business_key = (row['company_id'], row['currency'], row['source_id'])
    if business_key in business_keys:
        raise ValueError(f'Identifiant metier ambigu entre sources : {entity}')
    business_keys.add(business_key)
    if entity in STATES and row['state'] not in STATES[entity]:
        raise ValueError(f'Etat source inconnu : {entity}')
    for column in ('amount', 'total_amount','subtotal_amount'):
        if column in row:
            value = row[column]
            if (not MONEY.fullmatch(value) or abs(Decimal(value)) > MAX_MONEY
                    or (entity not in ('adjustments', 'bank_movements') and Decimal(value) < 0)):
                raise ValueError(f'Montant invalide : {entity}')
    for column, value in row.items():
        if not value:
            if (entity=='invoice_lines' and column=='description') or (entity == 'invoices' and column == 'due_on') or (
                    entity == 'settlement_batches' and column == 'expected_receipt_on'):
                continue
            raise ValueError(f'Champ absent {column} : {entity}')
        if column.endswith('_at') or column in ('period_start', 'period_end'):
            stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if stamp.utcoffset() is None:
                raise ValueError('Horodatage sans fuseau.')
        elif column.endswith('_on'):
            date.fromisoformat(value)

def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def create_reference(destination: Path) -> dict:
    """N'écrase aucun fichier. Les résultats attendus restent écrits à la main."""
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f'Le dossier {destination} contient deja des fichiers. Choisir un nouveau dossier.')
    destination.mkdir(parents=True, exist_ok=True)
    source = read_json(FIXTURES / 'reference_source.json')
    files = []
    for entity, headers in HEADERS.items():
        path = destination / f'{entity}.csv'
        rows = source[entity]
        with path.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=headers, lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        files.append({
            'entity': entity, 'file': path.name, 'row_count': len(rows),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    coverage = []
    for batch_id in ('LOT001', 'LOT002', 'LOT003', 'LOT004'):
        for entity in ('processor_payments', 'refunds', 'fees', 'adjustments', 'bank_movements', 'bank_allocations'):
            complete = not (batch_id == 'LOT003' and entity == 'fees')
            coverage.append({
                'company_id': 'DEMO_MA', 'currency': 'MAD', 'batch_id': batch_id,
                'entity': entity, 'complete': complete,
                'evidence': 'scenario_synthetique_declare' if complete else 'source_absente_pour_ce_lot',
            })
    manifest = {
        'contract_version': 'reference-v1', 'synthetic': True,
        'company_id': 'DEMO_MA', 'currency': 'MAD',
        'control_on': '2026-10-05', 'files': files,
        'invoice_coverage': {'invoices': True, 'erp_payments': True, 'invoice_allocations': True, 'credit_notes': True},
        'settlement_coverage': coverage,
    }
    write_json(destination / 'manifest.json', manifest)
    return manifest


def check_reference(destination: Path) -> dict:
    """Vérifie la structure, les empreintes et les liens ; aucun moteur financier."""
    manifest = read_json(destination / 'manifest.json')
    contract=manifest.get('contract_version')
    if contract not in ('reference-v1','finance-v1') or type(manifest.get('synthetic')) is not bool:
        raise ValueError('Manifeste de reference invalide.')
    company=manifest.get('company_id');currency=manifest.get('currency')
    if contract=='reference-v1':
        if manifest['synthetic'] is not True or company!='DEMO_MA' or currency!='MAD':raise ValueError('Perimetre du manifeste incoherent.')
    elif not isinstance(company,str) or not company.strip() or currency not in ('MAD','EUR','USD','GBP'):
        raise ValueError('Entreprise absente ou devise non supportee par finance-v1.')
    headers=dict(HEADERS)
    if contract=='finance-v1':headers.update({key:value for key,value in EXTRA_HEADERS.items() if any(item['entity']==key for item in manifest['files'])})
    date.fromisoformat(manifest['control_on'])
    invoice_coverage = manifest.get('invoice_coverage', {})
    if set(invoice_coverage) != {'invoices', 'erp_payments', 'invoice_allocations', 'credit_notes'} or any(
            type(value) is not bool for value in invoice_coverage.values()):
        raise ValueError('Couverture des sources de facture invalide.')
    expected_names = {f'{entity}.csv' for entity in headers}
    if {item['file'] for item in manifest['files']} != expected_names:
        raise ValueError('Liste de fichiers incomplete ou inattendue.')
    if len(manifest['files']) != len(headers):
        raise ValueError('Fichier declare plusieurs fois dans le manifeste.')
    data = {}
    for item in manifest['files']:
        entity = item['entity']
        if entity not in headers or item['file'] != f'{entity}.csv':
            raise ValueError('Nom ou entite de source invalide.')
        path = destination / item['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError(f'Empreinte differente : {path.name}')
        with path.open(encoding='utf-8', newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != headers[entity]:
                raise ValueError(f'Colonnes invalides : {path.name}')
            rows = list(reader)
        if len(rows) != item['row_count']:
            raise ValueError(f'Nombre de lignes invalide : {path.name}')
        seen = set()
        business_keys = set()
        for row in rows:
            validate_row(entity,row,company,currency,seen,business_keys)
        data[entity] = rows

    indexes={entity:{(row['company_id'],row['currency'],row['source_id']):row for row in rows} for entity,rows in data.items()}
    def lookup(entity, source_id, company, currency):
        key=(company,currency,source_id)
        if key not in indexes[entity]:raise ValueError(f'Reference absente ou ambigue : {entity}/{source_id}')
        return indexes[entity][key]

    relations = (
        ('invoices', 'order_id', 'orders'),
        ('invoice_allocations', 'invoice_id', 'invoices'),
        ('invoice_allocations', 'payment_id', 'erp_payments'),
        ('credit_notes', 'invoice_id', 'invoices'),
        ('processor_payments', 'batch_id', 'settlement_batches'),
        ('refunds', 'batch_id', 'settlement_batches'),
        ('refunds', 'payment_id', 'processor_payments'),
        ('fees', 'batch_id', 'settlement_batches'),
        ('adjustments', 'batch_id', 'settlement_batches'),
        ('bank_allocations', 'batch_id', 'settlement_batches'),
        ('bank_allocations', 'movement_id', 'bank_movements'),
    )
    if 'invoice_lines' in data:relations += (('invoice_lines','invoice_id','invoices'),)
    if 'invoice_order_links' in data:relations += (('invoice_order_links','invoice_id','invoices'),('invoice_order_links','order_id','orders'))
    for child, column, parent in relations:
        for row in data[child]:
            lookup(parent, row[column], row['company_id'], row['currency'])
    for row in data.get('invoice_lines',[]):
        q=Decimal(row['quantity'])
        if not q.is_finite():raise ValueError('Quantite invalide.')
    batches = {row['source_id'] for row in data['settlement_batches']}
    entities = {'processor_payments', 'refunds', 'fees', 'adjustments', 'bank_movements', 'bank_allocations'}
    keys = set()
    for item in manifest['settlement_coverage']:
        key = (item['batch_id'], item['entity'])
        if key in keys or item['batch_id'] not in batches or item['entity'] not in entities:
            raise ValueError('Couverture dupliquee ou inconnue.')
        if type(item['complete']) is not bool or not item['evidence']:
            raise ValueError('Declaration de couverture invalide.')
        if item['company_id'] != company or item['currency'] != currency:
            raise ValueError('Perimetre de couverture incoherent.')
        keys.add(key)
    if keys != {(batch, entity) for batch in batches for entity in entities}:
        raise ValueError('Couverture des sources non declaree pour un lot.')
    return {
        'status': 'REFERENCE_OK', 'contract_version': contract,
        'files_checked': len(data), 'rows_checked': sum(map(len, data.values())),
        'control_on': manifest['control_on'],
        'financial_engine_tested': False,
    }
