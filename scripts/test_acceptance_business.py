"""Recette du véritable moteur PostgreSQL/dbt dans des bases temporaires."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from money_trail.acceptance_cases import cases,create_case,expected
from money_trail.importer import setup_database,import_directory,inspect_database
from money_trail.investigation import dossiers,read_build_evidence,serializable,payload_hash
from money_trail.workflow import setup_workflow,sync_cases,resolve_case,show_case,act
from money_trail.local_auth import setup_accounts,create_user
from run_dbt import invoke_dbt
from testing_database import TemporaryDatabase,table_fingerprints


def artifacts(temporary,name):
    parent=Path(os.environ.get('MT_ACCEPTANCE_ARTIFACTS',str(temporary)))
    parent.mkdir(parents=True,exist_ok=True)
    return parent/name


def read_dossiers(db,batch,proof):
    with db.transaction():
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        return dossiers(db,batch,proof)


class BusinessAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.directory=Path(cls.tmp.name)
        cls.sandbox=TemporaryDatabase();cls.addClassCleanup(cls.sandbox.close)
        cls.db=cls.sandbox.db;setup_database(cls.db);setup_workflow(cls.db);setup_accounts(cls.db)
        cls.ids={};cls.paths={}
        for case in cases():
            path=cls.directory/case['id'];create_case(path,case)
            cls.paths[case['id']]=path
            cls.ids[case['id']]=import_directory(cls.db,path)['batch_id']
        build=artifacts(cls.directory,'valid_build')
        print('\nConstruction dbt : 47 versions synthétiques dans une base temporaire.',flush=True)
        if not invoke_dbt('build',cls.sandbox.config,build):
            raise AssertionError('Le build des scenarios valides a echoue ; consulter les tests dbt.')
        cls.proof=read_build_evidence(build/'target/run_results.json')
        if cls.proof['passed_tests']<21:raise AssertionError('Les nouveaux controles dbt ne sont pas presents.')

    def check_case(self,case):
        targets=expected(case);batch=self.ids[case['id']]
        observed={}
        for kind,table,key in [('invoice','invoice_reconciliation','invoice_id'),('settlement','settlement_reconciliation','batch_id')]:
            with self.db.cursor(row_factory=dict_row) as cursor:
                cursor.execute(f'SELECT * FROM marts.{table} WHERE import_batch_id=%s',(batch,))
                rows={row[key]:row for row in cursor.fetchall()}
            self.assertEqual(set(rows),set(targets[kind]),msg=case['title'])
            for object_id,target in targets[kind].items():
                actual=rows[object_id]
                for column,value in target.items():
                    if column in ('rule_refs','missing_source'):continue
                    observed_value=actual[column]
                    if value is not None and isinstance(observed_value,Decimal):value=Decimal(value)
                    self.assertEqual(observed_value,value,msg=f"{case['id']} / {object_id} / {column}")
                if target.get('missing_source'):
                    self.assertIn(target['missing_source'],(actual['missing_sources'] or '').split(', '))
                self.assertEqual((actual['company_id'],actual['currency']),('DEMO_MA','MAD'))
            observed[kind]=rows
        evidence=read_dossiers(self.db,batch,self.proof)
        self.assertEqual(len(evidence),sum(len(rows) for rows in targets.values()))
        for dossier in evidence:
            self.assertTrue(dossier['evidence_matches_components'])
            self.assertFalse(dossier['explanation']['accounting_correction_applied'])
            if dossier['result']['status']=='ecart':self.assertEqual(dossier['explanation']['cause'],'non_identifiee')
            for line in dossier['line_evidence']:
                self.assertTrue(line['integrity_verified'])
                if line['role']=='contribution' and not line['included_in_observed_sum']:
                    self.assertTrue(line['exclusion_reasons'])
        folder=artifacts(self.directory,'observed');folder.mkdir(parents=True,exist_ok=True)
        (folder/(case['id']+'.json')).write_text(json.dumps(serializable({'case':case['id'],'title':case['title'],
          'acceptance':case['acceptance'],'snapshot_id':batch,'expected':targets,'observed':observed,
          'evidence_matches_components':True,'build_evidence':self.proof}),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    def test_D01_reimport_all_cases_is_idempotent(self):
        before=inspect_database(self.db)['totals']
        for case in cases():
            result=import_directory(self.db,self.paths[case['id']])
            self.assertEqual(result['status'],'skipped_duplicate')
            self.assertEqual(result['inserted_records'],0)
            self.assertEqual(result['batch_id'],self.ids[case['id']])
        self.assertEqual(inspect_database(self.db)['totals'],before)

    def test_D02_rebuild_preserves_values_and_raw_sources(self):
        before_sources=table_fingerprints(self.db)
        def amounts():
            result=[]
            for table in ('invoice_reconciliation','settlement_reconciliation'):
                result.extend(self.db.execute(f"SELECT (to_jsonb(t)-'calculated_at')::text FROM marts.{table} t ORDER BY import_batch_id,1").fetchall())
            return result
        before=amounts()
        self.assertTrue(invoke_dbt('build',self.sandbox.config,artifacts(self.directory,'repeat_build')))
        self.assertEqual(amounts(),before)
        after_sources=table_fingerprints(self.db)
        for name,value in before_sources.items():
            if not name.startswith('marts.'):self.assertEqual(after_sources[name],value)

    def test_D03_late_source_creates_distinct_preserved_snapshots(self):
        first=self.ids['C01_reference'];second=self.ids['C42_late_fees_received']
        self.assertNotEqual(first,second)
        def result(batch):return self.db.execute("SELECT expected_amount,difference,status FROM marts.settlement_reconciliation WHERE import_batch_id=%s AND batch_id='LOT003'",(batch,)).fetchone()
        self.assertEqual(result(first),(None,None,'calcul_bloque'))
        self.assertEqual(result(second),(Decimal('950.00'),Decimal('0.00'),'rapproche'))
        for batch,count in [(first,0),(second,1)]:
            found=self.db.execute("SELECT count(*) FROM raw.source_records r JOIN meta.import_files f USING(file_id) WHERE f.batch_id=%s AND r.source_id='FRLATE'",(batch,)).fetchone()[0]
            self.assertEqual(found,count)

    def test_D04_closing_case_does_not_remove_financial_discrepancy(self):
        batch=self.ids['C01_reference'];evidence=read_dossiers(self.db,batch,self.proof)
        sync_cases(self.db,evidence,'test-analyst');case=resolve_case(self.db,batch,'settlement','LOT001')
        frozen=deepcopy(show_case(self.db,case)['case']['evidence'])
        act(self.db,case,'start','test-analyst',note='Revue de recette')
        act(self.db,case,'propose','test-analyst',proposal_type='source_data_review',description='Demander le justificatif',justification='Ecart de 30 MAD observe')
        act(self.db,case,'approve','test-reviewer',note='Proposition de revue approuvee')
        act(self.db,case,'close','test-analyst',note='Suivi clos ; aucune ecriture comptable')
        sync_cases(self.db,evidence,'test-analyst')
        detail=show_case(self.db,case)
        self.assertEqual(detail['case']['workflow_status'],'closed')
        self.assertEqual(detail['case']['evidence'],frozen)
        self.assertEqual(self.db.execute("SELECT difference,status FROM marts.settlement_reconciliation WHERE import_batch_id=%s AND batch_id='LOT001'",(batch,)).fetchone(),(Decimal('-30.00'),'ecart'))

    def test_D05_revised_source_does_not_overwrite_historical_case(self):
        first=self.ids['C25_known_zero_fees'];second=self.ids['C42_late_fees_received']
        sync_cases(self.db,read_dossiers(self.db,first,self.proof),'test-analyst')
        old=resolve_case(self.db,first,'settlement','LOT003')
        act(self.db,old,'comment','test-analyst',note='Frais a confirmer sur cette version')
        before=show_case(self.db,old)
        sync_cases(self.db,read_dossiers(self.db,second,self.proof),'test-analyst')
        self.assertEqual(show_case(self.db,old),before)
        self.assertEqual(self.db.execute("SELECT count(*) FROM app.investigation_cases WHERE import_batch_id=%s AND object_id='LOT003'",(second,)).fetchone()[0],0)

    def test_D06_backup_and_restore_in_isolated_database(self):
        if not shutil.which('docker'):self.skipTest('Docker CLI absent : restauration PostgreSQL non executee.')
        create_user(self.db,'restore-test','synthetic-password-only','viewer')
        batch=self.ids['C24_signed_adjustments']
        sync_cases(self.db,read_dossiers(self.db,batch,self.proof),'restore-analyst')
        case=resolve_case(self.db,batch,'settlement','LOT004')
        act(self.db,case,'comment','restore-analyst',note='Historique a retrouver apres restauration')
        original=table_fingerprints(self.db)
        archive=self.directory/'synthetic_backup.dump'
        started=time.perf_counter()
        command=['docker','compose','exec','-T','postgres','pg_dump','-U',self.sandbox.config['user'],'--format=custom','--dbname',self.sandbox.name]
        with archive.open('wb') as stream:
            result=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.PIPE,timeout=120)
        backup_finished=time.perf_counter()
        self.assertEqual(result.returncode,0,msg=result.stderr.decode(errors='replace')[-1200:])
        self.assertGreater(archive.stat().st_size,0)
        with TemporaryDatabase(prefix='moneytrail_restore_') as restored:
            restore_started=time.perf_counter()
            command=['docker','compose','exec','-T','postgres','pg_restore','-U',restored.config['user'],'--exit-on-error','--dbname',restored.name]
            with archive.open('rb') as stream:
                result=subprocess.run(command,cwd=ROOT,stdin=stream,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
            restore_finished=time.perf_counter()
            self.assertEqual(result.returncode,0,msg=result.stderr.decode(errors='replace')[-1200:])
            self.assertEqual(table_fingerprints(restored.db),original)
            restored_evidence=read_dossiers(restored.db,self.ids['C01_reference'],self.proof)
            self.assertEqual(len(restored_evidence),5)
            measure=dict(backup_seconds=round(backup_finished-started,3),restore_seconds=round(restore_finished-restore_started,3),
                         archive_bytes=archive.stat().st_size,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                         tables_verified=len(original)-1,rows_and_sequences_identical=True)
            folder=artifacts(self.directory,'restore');folder.mkdir(parents=True,exist_ok=True)
            (folder/'measures.json').write_text(json.dumps(measure,indent=2)+'\n',encoding='utf-8')
            print('RESTORATION_ISOLEE_OK '+json.dumps(measure),flush=True)

    def test_D07_corrupted_source_file_is_refused(self):
        with self.db.transaction(force_rollback=True):
            self.db.execute("UPDATE meta.import_files SET source_bytes=source_bytes || decode('20','hex') WHERE batch_id=%s AND entity='fees'",(self.ids['C01_reference'],))
            with self.assertRaisesRegex(ValueError,'Integrite du fichier'):dossiers(self.db,self.ids['C01_reference'],self.proof)

    def test_D08_payload_and_hash_cannot_claim_different_source_bytes(self):
        batch=self.ids['C01_reference']
        with self.db.transaction(force_rollback=True):
            row=self.db.execute("SELECT record_id,payload FROM raw.source_records r JOIN meta.import_files f USING(file_id) WHERE f.batch_id=%s AND f.entity='invoices'",(batch,)).fetchone()
            modified={**row[1],'order_id':'INVENTED'}
            self.db.execute('UPDATE raw.source_records SET payload=%s,payload_sha256=%s WHERE record_id=%s',(Jsonb(modified),payload_hash(modified),row[0]))
            with self.assertRaisesRegex(ValueError,'octets du fichier'):dossiers(self.db,batch,self.proof)

    def test_D09_control_date_must_match_the_immutable_manifest(self):
        batch=self.ids['C01_reference']
        with self.db.transaction(force_rollback=True):
            self.db.execute('UPDATE meta.import_batches SET control_on=control_on+1 WHERE batch_id=%s',(batch,))
            with self.assertRaisesRegex(ValueError,'Metadonnees du snapshot'):dossiers(self.db,batch,self.proof)


def scenario_test(case):
    def test(self):self.check_case(case)
    test.__doc__=case['title']
    return test


for case in cases():setattr(BusinessAcceptance,'test_'+case['id'],scenario_test(case))


BAD_CASES=[
    ('I01_payment_overallocated','invoice_allocations','A001',{'amount':'601.00'},'allocation_limits'),
    ('I02_bank_overallocated','bank_allocations','AB001',{'amount':'851.00'},'allocation_limits'),
    ('I03_bank_debit','bank_movements','BQ001',{'amount':'-850.00'},'allocation_limits'),
    ('I04_refund_over_capture','refunds','REM001',{'amount':'1000.01'},'refund_limits'),
    ('I05_refund_wrong_batch','refunds','REM001',{'batch_id':'LOT002'},'refund_batch_consistency'),
    ('I06_invalid_period','settlement_batches','LOT004',{'period_end':'2026-09-28T00:00:00Z'},'valid_periods'),
]


class InvalidBusinessAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.directory=Path(cls.tmp.name);cls.sandbox=TemporaryDatabase(prefix='moneytrail_invalid_');cls.addClassCleanup(cls.sandbox.close)
        cls.db=cls.sandbox.db;setup_database(cls.db);cls.ids={}
        for name,entity,object_id,values,test_name in BAD_CASES:
            case=deepcopy(cases()[0]);case['patches']=[dict(entity=entity,id=object_id,set=values)]
            path=cls.directory/name;create_case(path,case)
            cls.ids[name]=import_directory(cls.db,path)['batch_id']
        path=cls.directory/'I07_ambiguous_source_id';create_case(path,cases()[0])
        cls.ids['I07_ambiguous_source_id']=import_directory(cls.db,path)['batch_id']
        # Injection uniquement dans cette base jetable : simule une source historique mal chargée.
        with cls.db.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT r.* FROM raw.source_records r JOIN meta.import_files f USING(file_id) WHERE f.batch_id=%s AND r.source_id='CAP004'",(cls.ids['I07_ambiguous_source_id'],))
            row=cursor.fetchone()
        modified={**row['payload'],'source_system':'second_demo'}
        cls.db.execute('''INSERT INTO raw.source_records(file_id,row_number,company_id,source_system,source_id,payload,payload_sha256)
          VALUES (%s,99,%s,%s,%s,%s,%s)''',(row['file_id'],row['company_id'],'second_demo',row['source_id'],Jsonb(modified),payload_hash(modified)))
        build=artifacts(cls.directory,'invalid_build')
        print('\nBuild dbt volontairement invalide : les controles doivent le refuser.',flush=True)
        if invoke_dbt('build',cls.sandbox.config,build):raise AssertionError('Le build invalide a ete accepte.')
        cls.build=build
        cls.report=json.loads((build/'target/run_results.json').read_text(encoding='utf-8'))
        manifest=json.loads((build/'target/manifest.json').read_text(encoding='utf-8'))
        cls.nodes={node['name']:node for node in manifest['nodes'].values() if node['resource_type']=='test'}

    def check_failure(self,name,test_name):
        failed={row['unique_id'] for row in self.report['results'] if row['status']=='fail'}
        node=self.nodes[test_name]
        self.assertIn(node['unique_id'],failed)
        with self.db.cursor(row_factory=dict_row) as cursor:
            cursor.execute(node['compiled_code']);violations=cursor.fetchall()
        matching=[]
        for row in violations:
            if 'import_batch_id' in row:matches=str(row['import_batch_id'])==self.ids[name]
            else:
                records={record[0] for record in self.db.execute('SELECT r.record_id FROM raw.source_records r JOIN meta.import_files f USING(file_id) WHERE f.batch_id=%s',(self.ids[name],))}
                matches=row.get('record_id') in records
            if matches:matching.append(row)
        self.assertTrue(matching,msg=name+' : le controle ne signale pas le snapshot invalide')

    def test_I07_ambiguous_identity_is_blocked(self):self.check_failure('I07_ambiguous_source_id','source_identity_grain')

    def test_I08_failed_build_cannot_be_used_as_evidence(self):
        with self.assertRaises(ValueError):read_build_evidence(self.build/'target/run_results.json')


def rejection_test(name,test_name):
    def test(self):self.check_failure(name,test_name)
    return test


for name,entity,object_id,values,test_name in BAD_CASES:
    setattr(InvalidBusinessAcceptance,'test_'+name,rejection_test(name,test_name))


if __name__=='__main__':unittest.main(verbosity=2)
