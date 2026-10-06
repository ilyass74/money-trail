"""Préparer un lot CSV contrôlé, avec conservation des rejets et couverture incomplète."""
from collections import Counter
from pathlib import Path
from uuid import uuid4
import csv
import hashlib
import json
from .reference import HEADERS,EXTRA_HEADERS,validate_row,write_json,check_reference
from .investigation import payload_hash

RELATIONS=[('invoices','order_id','orders'),('invoice_allocations','invoice_id','invoices'),
 ('invoice_allocations','payment_id','erp_payments'),('credit_notes','invoice_id','invoices'),
 ('processor_payments','batch_id','settlement_batches'),('refunds','batch_id','settlement_batches'),
 ('refunds','payment_id','processor_payments'),('fees','batch_id','settlement_batches'),
 ('adjustments','batch_id','settlement_batches'),('bank_allocations','batch_id','settlement_batches'),
 ('bank_allocations','movement_id','bank_movements'),('invoice_lines','invoice_id','invoices'),('invoice_order_links','invoice_id','invoices'),('invoice_order_links','order_id','orders')]


def prepare_quarantine(source,destination):
    if destination.exists() and any(destination.iterdir()):raise ValueError('Choisir un dossier vide.')
    manifest=json.loads((source/'manifest.json').read_bytes());company=manifest['company_id'];currency=manifest['currency']
    data={};original={};rejected=[];affected=set()
    headers=dict(HEADERS)
    if manifest['contract_version']=='finance-v1':headers.update({key:value for key,value in EXTRA_HEADERS.items() if any(item['entity']==key for item in manifest['files'])})
    if len(manifest['files'])!=len(headers) or {e['entity'] for e in manifest['files']}!=set(headers):raise ValueError('Manifeste incomplet ou duplique.')
    for entry in manifest['files']:
        entity=entry['entity']
        if entry['file']!=entity+'.csv':raise ValueError('Nom de fichier invalide.')
        content=(source/entry['file']).read_bytes()
        if hashlib.sha256(content).hexdigest()!=entry['sha256']:raise ValueError('Empreinte de fichier invalide : refus du lot entier.')
        original[entity]=content.decode('utf-8')
        import io
        reader=csv.DictReader(io.StringIO(original[entity],newline=''))
        if reader.fieldnames!=headers[entity]:raise ValueError('Colonnes invalides : refus du lot entier.')
        rows=list(reader)
        if len(rows)!=entry['row_count']:raise ValueError('Nombre de lignes incoherent.')
        duplicates=Counter((r.get('company_id'),r.get('currency'),r.get('source_id')) for r in rows)
        data[entity]=[]
        for number,row in enumerate(rows,1):
            try:
                validate_row(entity,row,company,currency)
                if duplicates[(row['company_id'],row['currency'],row['source_id'])]>1:raise ValueError('identite_ambigue')
                data[entity].append((number,row))
            except (ValueError,ArithmeticError,TypeError):
                rejected.append(dict(entity=entity,row_number=number,payload={str(k):v for k,v in row.items()},reason='contrat_ligne_invalide'))
                affected.add(entity)
    while True:
        removed=False;indices={entity:{r['source_id'] for _,r in rows} for entity,rows in data.items()}
        for child,field,parent in RELATIONS:
            if child not in data:continue
            retained=[]
            for number,row in data[child]:
                if row[field] not in indices[parent]:
                    rejected.append(dict(entity=child,row_number=number,payload=row,reason='reference_parent_rejetee_ou_absente'))
                    affected.add(child);removed=True
                else:retained.append((number,row))
            data[child]=retained
        if not removed:break
    destination.mkdir(parents=True,exist_ok=True)
    for entry in manifest['files']:
        entity=entry['entity'];path=destination/entry['file']
        with path.open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=headers[entity],lineterminator='\n');writer.writeheader();writer.writerows(row for _,row in data[entity])
        entry['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();entry['row_count']=len(data[entity])
    if affected & {'orders','invoices','invoice_lines','invoice_order_links','erp_payments','invoice_allocations','credit_notes'}:
        manifest['invoice_coverage']={key:False for key in manifest['invoice_coverage']}
    batches={row['source_id'] for _,row in data['settlement_batches']}
    manifest['settlement_coverage']=[c for c in manifest['settlement_coverage'] if c['batch_id'] in batches]
    for coverage in manifest['settlement_coverage']:
        if rejected and any(entity in affected for entity in ('settlement_batches',coverage['entity'])):
            coverage['complete']=False;coverage['evidence']='lignes_en_quarantaine'
    manifest['quarantine_count']=len(rejected);write_json(destination/'manifest.json',manifest)
    check_reference(destination)
    return dict(manifest=manifest,original_files=original,rejected=rejected)


def quarantine_directory(db,source,destination):
    from psycopg.types.json import Jsonb
    extraction_id=uuid4()
    db.execute("INSERT INTO meta.source_extractions(extraction_id,source,company_id,status) VALUES(%s,'csv-contract','pending','started')",(extraction_id,))
    try:
        prepared=prepare_quarantine(source,destination)
        prepared['manifest']['source_extraction_id']=str(extraction_id)
        write_json(destination/'manifest.json',prepared['manifest'])
        # Le lot original entier et les numéros de ligne sont conservés en base.
        payload={'original_files':prepared['original_files'],'complete':not prepared['rejected'],'output_manifest':prepared['manifest']}
        with db.transaction():
            for row in prepared['rejected']:
                db.execute('INSERT INTO meta.quarantined_rows(extraction_id,entity,row_number,payload,reason) VALUES(%s,%s,%s,%s,%s)',
                           (extraction_id,row['entity'],row['row_number'],Jsonb(row['payload']),row['reason']))
            db.execute("UPDATE meta.source_extractions SET status='success',company_id=%s,finished_at=clock_timestamp(),payload=%s,payload_sha256=%s WHERE extraction_id=%s",
                       (prepared['manifest']['company_id'],Jsonb(payload),payload_hash(payload),extraction_id))
        return dict(extraction_id=str(extraction_id),quarantined=len(prepared['rejected']),complete=not prepared['rejected'])
    except Exception as error:
        db.execute("UPDATE meta.source_extractions SET status='failed',finished_at=clock_timestamp(),error_code=%s WHERE extraction_id=%s",(type(error).__name__,extraction_id));raise
