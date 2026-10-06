"""Validation métier dans une base temporaire, jamais dans la base du projet."""
from pathlib import Path
from decimal import Decimal
from uuid import uuid4
import csv
import hashlib
import json
import shutil
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import psycopg
from psycopg import sql
from money_trail.reference import create_reference,HEADERS
from money_trail.importer import local_config,setup_database,import_directory
from run_dbt import invoke_dbt,verify_reference


def change_rows(path,entity,transform):
    file=path/f'{entity}.csv'
    with file.open(encoding='utf-8',newline='') as stream:rows=list(csv.DictReader(stream))
    transform(rows)
    with file.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=HEADERS[entity],lineterminator='\n')
        writer.writeheader();writer.writerows(rows)
    manifest=json.loads((path/'manifest.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        if item['entity']==entity:
            item['sha256']=hashlib.sha256(file.read_bytes()).hexdigest();item['row_count']=len(rows)
    (path/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')


class BusinessIntegration(unittest.TestCase):
    def test_business_scenarios_and_invalid_allocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp);base=directory/'base';create_reference(base)
            config=local_config();test_db='moneytrail_dbt_test_'+uuid4().hex
            with psycopg.connect(**config,autocommit=True) as admin:
                admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(test_db)))
                try:
                    test_config={**config,'dbname':test_db}
                    with psycopg.connect(**test_config,autocommit=True) as connection:
                        setup_database(connection)
                        original=import_directory(connection,base)['batch_id']
                        changed=directory/'changed';shutil.copytree(base,changed)
                        change_rows(changed,'invoices',lambda rows:rows[0].update(due_on='2026-10-01'))
                        change_rows(changed,'credit_notes',lambda rows:rows.append(dict(company_id='DEMO_MA',source_system='erp_demo',source_id='AV001',invoice_id='FAC001',state='posted',currency='MAD',amount='50.00',issued_on='2026-10-03')))
                        change_rows(changed,'fees',lambda rows:rows.append({**rows[1],'source_id':'FR003','amount':'5.00'}))
                        change_rows(changed,'refunds',lambda rows:rows.append({**rows[1],'source_id':'REM003','amount':'10.00'}))
                        changed_id=import_directory(connection,changed)['batch_id']
                        incomplete=directory/'incomplete';shutil.copytree(base,incomplete)
                        manifest=json.loads((incomplete/'manifest.json').read_text())
                        manifest['invoice_coverage']['credit_notes']=False
                        (incomplete/'manifest.json').write_text(json.dumps(manifest))
                        incomplete_id=import_directory(connection,incomplete)['batch_id']
                        cutoff=directory/'cutoff';shutil.copytree(base,cutoff)
                        change_rows(cutoff,'erp_payments',lambda rows:rows[1].update(paid_at='2026-10-06T09:00:00Z'))
                        change_rows(cutoff,'bank_movements',lambda rows:rows[1].update(booked_on='2026-10-06'))
                        change_rows(cutoff,'adjustments',lambda rows:rows.append(dict(company_id='DEMO_MA',source_system='psp_demo',source_id='AD001',batch_id='LOT004',currency='MAD',amount='-25.00',reason='correction_documentee',adjusted_at='2026-09-28T11:00:00Z')))
                        cutoff_id=import_directory(connection,cutoff)['batch_id']
                        self.assertTrue(invoke_dbt('build',test_config,directory/'valid'))
                        verify_reference(connection,original)
                        self.assertEqual(connection.execute('SELECT balance,status FROM marts.invoice_reconciliation WHERE import_batch_id=%s',(changed_id,)).fetchone(),(Decimal('50.00'),'en_retard'))
                        self.assertEqual(connection.execute("SELECT expected_amount FROM marts.settlement_reconciliation WHERE import_batch_id=%s AND batch_id='LOT002'",(changed_id,)).fetchone()[0],Decimal('865.00'))
                        self.assertEqual(connection.execute('SELECT balance,status FROM marts.invoice_reconciliation WHERE import_batch_id=%s',(incomplete_id,)).fetchone(),(None,'calcul_bloque'))
                        self.assertEqual(connection.execute('SELECT balance FROM marts.invoice_reconciliation WHERE import_batch_id=%s',(cutoff_id,)).fetchone()[0],Decimal('400.00'))
                        self.assertEqual(connection.execute("SELECT received_amount FROM marts.settlement_reconciliation WHERE import_batch_id=%s AND batch_id='LOT002'",(cutoff_id,)).fetchone()[0],Decimal('0.00'))
                        self.assertEqual(connection.execute("SELECT expected_amount FROM marts.settlement_reconciliation WHERE import_batch_id=%s AND batch_id='LOT004'",(cutoff_id,)).fetchone()[0],Decimal('975.00'))
                        # Rebuilding does not append duplicate results.
                        self.assertTrue(invoke_dbt('build',test_config,directory/'repeat'))
                        self.assertEqual(connection.execute('SELECT count(*) FROM marts.settlement_reconciliation').fetchone()[0],16)
                        bad=directory/'bad';shutil.copytree(base,bad)
                        change_rows(bad,'invoice_allocations',lambda rows:rows[0].update(amount='601.00'))
                        import_directory(connection,bad)
                        self.assertFalse(invoke_dbt('build',test_config,directory/'invalid'))
                        report=json.loads((directory/'invalid/target/run_results.json').read_text())
                        failures=[row for row in report['results'] if row['status']=='fail']
                        self.assertTrue(any('allocation_limits' in row['unique_id'] for row in failures))
                        print('BUSINESS_INTEGRATION_OK: reference, echeance, avoir, agregations, snapshots, incompletude, relance, surallocation refusee')
                finally:
                    admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(test_db)))


if __name__=='__main__':unittest.main(verbosity=2)
