"""Recette native des extensions : règles, dossiers, pages et sources Odoo."""
from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
from uuid import UUID
import sys
import json
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from money_trail.importer import setup_database,import_directory
from money_trail.publication import run_publication,read_publication,setup_publications
from money_trail.workflow import sync_cases,resolve_case,show_case,act
from money_trail.rules import register_policy
from money_trail.paging import page_records
from money_trail.matching import bank_candidates
from money_trail.reference import create_reference,write_json
from money_trail.local_auth import create_user,login,active_user
from money_trail.governance import assign,record_external_action,resolve,accept_gap
from money_trail.workflow import WorkflowError
from money_trail.oidc_auth import trusted_identity_session
from money_trail.odoo_source import run_extraction,ExtractionError
from money_trail.odoo_bundle import create_bundles
from test_operations import odoo_fixture,ReadOnlyAPI
from run_dbt import invoke_dbt
from testing_database import TemporaryDatabase


class OperationsIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);cls.path=Path(cls.tmp.name)
        cls.sandbox=TemporaryDatabase(prefix='moneytrail_operations_');cls.addClassCleanup(cls.sandbox.close)
        cls.db=cls.sandbox.db;setup_database(cls.db);setup_publications(cls.db)
        ref=cls.path/'reference';create_reference(ref)
        cls.batch=import_directory(cls.db,ref)['batch_id']
        cls.v1=cls.publish(cls.batch)
        sync_cases(cls.db,read_publication(cls.db,cls.batch,cls.v1['publication_id'])['dossiers'],'analyst')
        cls.old_case=resolve_case(cls.db,cls.batch,'settlement','LOT001')
        act(cls.db,cls.old_case,'start','analyst',note='Revue')
        act(cls.db,cls.old_case,'propose','analyst',proposal_type='source_data_review',description='Verifier',justification='Preuves')
        act(cls.db,cls.old_case,'approve','reviewer',note='Revue distincte')
        act(cls.db,cls.old_case,'close','analyst',note='Conclusion administrative')
        cls.old=show_case(cls.db,cls.old_case)
        cls.policy=dict(version='v2',invoice_tolerance='0.01',settlement_tolerance='30.00')
        cls.v2=cls.publish(cls.batch,policy=cls.policy)
        cls.extraction=run_extraction(cls.db,ReadOnlyAPI(odoo_fixture()),1)
        payload=cls.db.execute('SELECT payload FROM meta.source_extractions WHERE extraction_id=%s',(cls.extraction['extraction_id'],)).fetchone()[0]
        path=create_bundles(payload,cls.path/'odoo','2026-10-05')[0]
        cls.odoo_batch=import_directory(cls.db,path)['batch_id']
        cls.multi=run_publication(cls.sandbox.config,lambda cfg,path,variables:invoke_dbt('build',cfg,path,variables),
                    batch_ids=[cls.batch,cls.odoo_batch],policy=cls.policy,artifact_parent=cls.path/'artifacts')
        import shutil,csv,hashlib
        changed=cls.path/'changed';shutil.copytree(ref,changed)
        fee_file=changed/'fees.csv'
        with fee_file.open(newline='') as f:reader=csv.DictReader(f);headers=reader.fieldnames;rows=list(reader)
        next(r for r in rows if r['batch_id']=='LOT001')['amount']='10.00'
        with fee_file.open('w',newline='') as f:writer=csv.DictWriter(f,fieldnames=headers,lineterminator='\n');writer.writeheader();writer.writerows(rows)
        bank=changed/'bank_movements.csv'
        with bank.open(newline='') as f:reader=csv.DictReader(f);headers=reader.fieldnames;rows=list(reader)
        base=dict(company_id='DEMO_MA',source_system='bank_csv',currency='MAD',amount='40.00',value_on='2026-10-02',booked_on='2026-10-02')
        rows += [{**base,'source_id':'CANDIDATE_EXACT','reference':'LOT001'},{**base,'source_id':'CANDIDATE_AMOUNT_ONLY','reference':'OTHER'}]
        with bank.open('w',newline='') as f:writer=csv.DictWriter(f,fieldnames=headers,lineterminator='\n');writer.writeheader();writer.writerows(rows)
        manifest=json.loads((changed/'manifest.json').read_text())
        for entry in manifest['files']:
            path=changed/entry['file'];entry['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            with path.open() as f:entry['row_count']=len(list(csv.DictReader(f)))
        write_json(changed/'manifest.json',manifest)
        cls.changed_batch=import_directory(cls.db,changed)['batch_id']
        cls.changed=cls.publish(cls.changed_batch,policy=cls.policy)
        cls.reference_path=ref
        for name,role in [('analyst-ops','analyst'),('reviewer-ops','reviewer'),('viewer-ops','viewer'),('admin-ops','admin')]:
            create_user(cls.db,name,'Operations-Test-2026!',role)
        cls.tokens={name:login(cls.db,name,'Operations-Test-2026!') for name in ('analyst-ops','reviewer-ops','viewer-ops','admin-ops')}
        cls.action_case=cls.db.execute("SELECT case_id FROM app.investigation_cases WHERE import_batch_id=%s AND object_kind='settlement' AND object_id='LOT003' AND rule_version='settlement-v1'",(cls.batch,)).fetchone()[0]
        act(cls.db,cls.action_case,'start','analyst-ops',note='Revue')
        act(cls.db,cls.action_case,'propose','analyst-ops',proposal_type='source_data_review',description='Source manquante',justification='Completer les frais')
        act(cls.db,cls.action_case,'approve','reviewer-ops',note='Proposition justifiee')

    @classmethod
    def publish(cls,batch,**kwargs):
        return run_publication(cls.sandbox.config,lambda cfg,path,variables:invoke_dbt('build',cfg,path,variables),
                               batch_ids=[batch],artifact_parent=cls.path/'artifacts',**kwargs)

    def test_N01_new_rule_changes_status_with_same_amounts_and_sources(self):
        before=next(d for d in read_publication(self.db,self.batch,self.v1['publication_id'])['dossiers'] if d['object_id']=='LOT001')
        after=next(d for d in read_publication(self.db,self.batch,self.v2['publication_id'])['dossiers'] if d['object_id']=='LOT001')
        self.assertEqual((before['result']['difference'],after['result']['difference']),('-30.00','-30.00'))
        self.assertEqual((before['result']['status'],after['result']['status']),('ecart','rapproche'))
        self.assertEqual(before['snapshot'],after['snapshot']);self.assertIsNone(after['result']['cause'])

    def test_N02_comparisons_are_archived_and_immutable(self):
        rows=self.db.execute('SELECT comparison FROM app.rule_comparisons WHERE new_publication_id=%s',(self.v2['publication_id'],)).fetchall()
        self.assertEqual(len(rows),5);self.assertTrue(all(row[0]['same_source_snapshot'] for row in rows))
        with self.assertRaises(Exception):
            self.db.execute('DELETE FROM app.rule_comparisons WHERE new_publication_id=%s',(self.v2['publication_id'],))

    def test_N03_new_review_keeps_previous_closed_decision_unchanged(self):
        old=show_case(self.db,self.old_case)
        for key in ('case','events','proposals'):self.assertEqual(old[key],self.old[key])
        self.assertEqual(old['case']['workflow_status'],'closed');self.assertTrue(old['successions'])
        successor=show_case(self.db,old['successions'][0]['successor_case_id'])
        self.assertEqual(successor['case']['workflow_status'],'open');self.assertEqual(successor['case']['business_status'],'rapproche')
        self.assertEqual(successor['events'][0]['action'],'reopened_from_source')

    def test_N04_rules_reject_same_version_with_different_tolerance(self):
        with self.assertRaises(ValueError):register_policy(self.db,{**self.policy,'settlement_tolerance':'29.00'})

    def test_N05_pages_are_disjoint_ordered_filtered_and_have_full_totals(self):
        a=page_records(self.db,self.batch,self.v2['publication_id'],limit=2)
        b=page_records(self.db,self.batch,self.v2['publication_id'],limit=2,offset=2)
        self.assertEqual((len(a['dossiers']),len(b['dossiers']),a['total']),(2,2,5))
        self.assertFalse({(d['kind'],d['object_id']) for d in a['dossiers']} & {(d['kind'],d['object_id']) for d in b['dossiers']})
        c=page_records(self.db,self.batch,self.v2['publication_id'],search='LOT003',statuses=['calcul_bloque'])
        self.assertEqual(c['total'],1);self.assertEqual(c['dossiers'][0]['object_id'],'LOT003')
        self.assertEqual(page_records(self.db,self.batch,self.v2['publication_id'],search="%' OR true --")['total'],0)
        self.assertEqual(page_records(self.db,self.batch,self.v2['publication_id'],min_amount='1000.00',max_amount='1000.00')['total'],2)
        with self.assertRaises(ValueError):page_records(self.db,self.batch,self.v2['publication_id'],limit=1001)

    def test_N06_missing_expected_amount_has_no_invented_candidate(self):
        before=self.db.execute('SELECT count(*) FROM raw.source_records').fetchone()[0]
        self.assertEqual(bank_candidates(self.db,self.batch,self.v1['publication_id'],'LOT003'),[])
        self.assertEqual(self.db.execute('SELECT count(*) FROM raw.source_records').fetchone()[0],before)

    def test_N07_failed_extraction_does_not_replace_successful_source(self):
        class Broken:
            def call(self,*args):raise ExtractionError('failure')
        with self.assertRaises(ExtractionError):run_extraction(self.db,Broken(),1)
        self.assertEqual(self.db.execute('SELECT status FROM meta.source_extractions WHERE extraction_id=%s',(self.extraction['extraction_id'],)).fetchone()[0],'success')
        self.assertTrue(self.db.execute("SELECT 1 FROM meta.source_extractions WHERE status='failed'").fetchone())

    def test_N08_quarantined_rows_are_preserved_and_coverage_is_incomplete(self):
        rows=odoo_fixture();rows['account.payment'][0]['amount']='NaN'
        result=run_extraction(self.db,ReadOnlyAPI(rows),1)
        self.assertEqual((result['quarantined'],result['complete']),(1,False))
        payload=self.db.execute('SELECT payload FROM meta.quarantined_rows WHERE extraction_id=%s',(result['extraction_id'],)).fetchone()[0]
        self.assertEqual(payload['amount'],'NaN')

    def test_N09_odoo_lines_do_not_multiply_payment_or_invoice_total(self):
        d=read_publication(self.db,self.odoo_batch,self.multi['publication_id'])['dossiers'][0]
        self.assertEqual((d['result']['invoice_amount'],d['result']['allocated_amount'],d['result']['balance']),('120.00','120.00','0.00'))
        self.assertEqual(len([r for r in d['line_evidence'] if r['entity']=='invoice_lines']),2)
        self.assertEqual(len([r for r in d['line_evidence'] if r['entity']=='invoice_allocations']),1)
        self.assertEqual(d['snapshot']['company_id'],'ODOO:1')

    def test_N10_failed_commit_preserves_comparisons_cases_and_visible_version(self):
        head=self.db.execute('SELECT publication_id FROM app.publication_head').fetchone()[0]
        counts=[self.db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('app.rule_comparisons','app.case_successions','app.investigation_cases')]
        def fail(db,pub):raise RuntimeError('rollback-test')
        with self.assertRaises(RuntimeError):self.publish(self.batch,policy=self.policy,before_commit=fail)
        self.assertEqual(self.db.execute('SELECT publication_id FROM app.publication_head').fetchone()[0],head)
        self.assertEqual([self.db.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('app.rule_comparisons','app.case_successions','app.investigation_cases')],counts)

    def test_N11_corrected_source_opens_successor_without_changing_previous_review(self):
        case=resolve_case(self.db,self.changed_batch,'settlement','LOT001')
        detail=show_case(self.db,case)
        self.assertEqual(detail['case']['workflow_status'],'open')
        self.assertEqual(detail['case']['business_status'],'ecart')
        self.assertEqual(detail['successions'][0]['reason'],'source_changed')
        old=show_case(self.db,self.old_case)
        self.assertEqual(old['case']['workflow_status'],'closed')
        self.assertEqual(old['proposals'],self.old['proposals'])

    def test_N12_candidates_rank_reference_before_equal_amount_without_allocating(self):
        candidates=bank_candidates(self.db,self.changed_batch,self.changed['publication_id'],'LOT001')
        self.assertEqual([r['movement_id'] for r in candidates][:2],['CANDIDATE_EXACT','CANDIDATE_AMOUNT_ONLY'])
        self.assertTrue(all(r['automatic_allocation'] is False for r in candidates))
        self.assertEqual(candidates[1]['confidence'],'montant_date_uniquement_identite_non_confirmee')

    def test_N13_assignment_is_authenticated_revision_checked_and_viewer_refused(self):
        case=resolve_case(self.db,self.changed_batch,'settlement','LOT001');revision=show_case(self.db,case)['case']['revision']
        with self.assertRaises(WorkflowError):assign(self.db,self.tokens['viewer-ops'],case,'viewer-ops',revision)
        result=assign(self.db,self.tokens['analyst-ops'],case,'analyst-ops',revision)
        self.assertEqual(result['revision'],revision+1)
        with self.assertRaises(WorkflowError):assign(self.db,self.tokens['analyst-ops'],case,'analyst-ops',revision)

    def test_N14_external_evidence_requires_reviewer_and_preserves_hash(self):
        revision=show_case(self.db,self.action_case)['case']['revision']
        with self.assertRaises(WorkflowError):record_external_action(self.db,self.tokens['admin-ops'],self.action_case,'ERP:FIX:1','proof.txt',b'preuve',revision)
        result=record_external_action(self.db,self.tokens['reviewer-ops'],self.action_case,'ERP:FIX:1','proof.txt',b'preuve',revision)
        self.assertFalse(result['accounting_correction_applied'])
        self.assertEqual(show_case(self.db,self.action_case)['external_actions'][0]['external_reference'],'ERP:FIX:1')

    def test_N15_resolution_cannot_use_same_source_or_old_publication(self):
        revision=show_case(self.db,self.action_case)['case']['revision']
        with self.assertRaises(WorkflowError):resolve(self.db,self.tokens['reviewer-ops'],self.action_case,self.v1['publication_id'],revision)
        self.assertEqual(show_case(self.db,self.action_case)['case']['workflow_status'],'approved')

    def test_N16_acceptance_preserves_financial_gap_and_requires_justification(self):
        case=resolve_case(self.db,self.changed_batch,'settlement','LOT001');before=show_case(self.db,case)
        with self.assertRaises(WorkflowError):accept_gap(self.db,self.tokens['reviewer-ops'],case,'',before['case']['revision'])
        accept_gap(self.db,self.tokens['reviewer-ops'],case,'Ecart accepte et documente',before['case']['revision'])
        after=show_case(self.db,case)
        self.assertEqual(after['case']['evidence'],before['case']['evidence'])
        self.assertEqual(after['case']['workflow_status'],'accepted_with_justification')
        self.assertEqual(after['case']['business_status'],'ecart')

    def test_N17_oidc_identity_is_explicitly_mapped_without_guessing_email(self):
        with self.assertRaises(WorkflowError):trusted_identity_session(self.db,'https://issuer.example','unknown')
        uid=self.db.execute("SELECT user_id FROM app.local_users WHERE username='viewer-ops'").fetchone()[0]
        self.db.execute('INSERT INTO app.external_identities(issuer,subject,user_id) VALUES(%s,%s,%s)',('https://issuer.example','subject-ops',uid))
        token=trusted_identity_session(self.db,'https://issuer.example','subject-ops')
        self.assertEqual(active_user(self.db,token)['role'],'viewer')

    def test_N18_csv_quarantine_preserves_rejected_line_in_database(self):
        from money_trail.quarantine import quarantine_directory
        import shutil,csv,hashlib
        path=self.path/'invalid_csv';shutil.copytree(self.reference_path,path)
        f=path/'erp_payments.csv'
        with f.open() as stream:reader=csv.DictReader(stream);headers=reader.fieldnames;rows=list(reader)
        rows[0]['amount']='NaN'
        with f.open('w',newline='') as stream:writer=csv.DictWriter(stream,fieldnames=headers,lineterminator='\n');writer.writeheader();writer.writerows(rows)
        manifest=json.loads((path/'manifest.json').read_text());next(e for e in manifest['files'] if e['entity']=='erp_payments')['sha256']=hashlib.sha256(f.read_bytes()).hexdigest();write_json(path/'manifest.json',manifest)
        result=quarantine_directory(self.db,path,self.path/'clean_csv')
        self.assertFalse(result['complete']);self.assertGreater(result['quarantined'],0)
        self.assertTrue(self.db.execute('SELECT 1 FROM meta.quarantined_rows WHERE extraction_id=%s',(result['extraction_id'],)).fetchone())

    def test_N19_source_correction_after_external_action_can_confirm_resolution(self):
        import shutil,csv,hashlib
        path=self.path/'resolved_source';shutil.copytree(self.reference_path,path)
        file=path/'fees.csv'
        with file.open() as stream:reader=csv.DictReader(stream);headers=reader.fieldnames;rows=list(reader)
        rows.append(dict(company_id='DEMO_MA',source_system='processor_csv',source_id='FEE_LOT003_FIX',batch_id='LOT003',currency='MAD',amount='50.00',charged_at='2026-09-28T12:00:00Z'))
        with file.open('w',newline='') as stream:writer=csv.DictWriter(stream,fieldnames=headers,lineterminator='\n');writer.writeheader();writer.writerows(rows)
        manifest=json.loads((path/'manifest.json').read_text());entry=next(e for e in manifest['files'] if e['entity']=='fees');entry.update(sha256=hashlib.sha256(file.read_bytes()).hexdigest(),row_count=len(rows))
        for coverage in manifest['settlement_coverage']:
            if coverage['batch_id']=='LOT003' and coverage['entity']=='fees':coverage.update(complete=True,evidence='source_corrigee_apres_action')
        write_json(path/'manifest.json',manifest)
        batch=import_directory(self.db,path)['batch_id'];pub=self.publish(batch,policy=self.policy)
        revision=show_case(self.db,self.action_case)['case']['revision']
        result=resolve(self.db,self.tokens['reviewer-ops'],self.action_case,pub['publication_id'],revision)
        self.assertEqual(result['workflow_status'],'resolved')
        self.assertEqual(show_case(self.db,self.action_case)['resolutions'][0]['result']['status'],'rapproche')


if __name__=='__main__':unittest.main(verbosity=2)
