"""Teste le workflow dans une base temporaire, sans modifier les dossiers réels."""
from pathlib import Path
from uuid import uuid4
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import psycopg
from psycopg import sql
from money_trail.reference import create_reference
from money_trail.importer import local_config,setup_database,import_directory,inspect_database
from money_trail.workflow import setup_workflow,sync_cases,resolve_case,show_case,act,WorkflowError


class WorkflowIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        path=Path(self.tmp.name)/'source';create_reference(path)
        config=local_config();self.config=config;self.test_db='moneytrail_workflow_test_'+uuid4().hex
        self.admin=psycopg.connect(**config,autocommit=True);self.addCleanup(self.admin.close)
        self.admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(self.test_db)))
        self.addCleanup(self.drop_database)
        self.db=psycopg.connect(**{**config,'dbname':self.test_db},autocommit=True);self.addCleanup(self.db.close)
        setup_database(self.db);setup_workflow(self.db)
        self.batch=import_directory(self.db,path)['batch_id']
        self.record=self.db.execute("SELECT record_id FROM raw.source_records WHERE source_id='BQ001'").fetchone()[0]
        self.before=inspect_database(self.db)['totals']
        self.raw_before=self.db.execute('SELECT record_id,payload_sha256,payload FROM raw.source_records ORDER BY record_id').fetchall()
        self.dossiers=[{'kind':'settlement','object_id':obj,'result':dict(import_batch_id=self.batch,company_id='DEMO_MA',currency='MAD',rule_version='settlement-v1',status=status),
                       'line_evidence':[{'record_id':self.record}]} for obj,status in [('LOT001','ecart'),('LOT002','rapproche'),('LOT003','calcul_bloque')]]
        sync_cases(self.db,self.dossiers,'creator-demo')
        self.case=resolve_case(self.db,self.batch,'settlement','LOT001')

    def tearDown(self):
        self.assertEqual(inspect_database(self.db)['totals'],self.before)
        self.assertEqual(self.db.execute('SELECT record_id,payload_sha256,payload FROM raw.source_records ORDER BY record_id').fetchall(),self.raw_before)

    def drop_database(self):
        self.admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(self.test_db)))

    def proposal(self,actor='analyst-demo',refs=None):
        return act(self.db,self.case,'propose',actor,proposal_type='allocation_review',description='Verifier affectation bancaire',
                   justification='Ecart observe dans le scenario de test',record_ids=[self.record] if refs is None else refs)

    def test_setup_and_sync_preserve_history(self):
        setup_workflow(self.db)
        act(self.db,self.case,'comment','analyst-demo',note='Piece demandee')
        self.assertEqual(sync_cases(self.db,self.dossiers,'creator-demo'),dict(created=0,existing=2,ignored=1))
        case=show_case(self.db,self.case)
        self.assertEqual(case['case']['revision'],1);self.assertEqual(len(case['events']),2)
        self.assertEqual(self.db.execute('SELECT count(*) FROM meta.schema_migrations').fetchone()[0],2)

    def test_decision_then_close_without_source_change(self):
        act(self.db,self.case,'start','analyst-demo',note='Investigation commencee')
        self.proposal()
        with self.assertRaises(WorkflowError):act(self.db,self.case,'approve','ANALYST-DEMO',note='Auto validation interdite')
        self.assertEqual(show_case(self.db,self.case)['case']['revision'],2)
        act(self.db,self.case,'approve','reviewer-demo',note='Proposition revue dans ce test')
        act(self.db,self.case,'close','analyst-demo',note='Suivi de test clos ; aucune ecriture appliquee')
        case=show_case(self.db,self.case)
        self.assertEqual(case['case']['workflow_status'],'closed')
        self.assertEqual(case['proposals'][0]['decision'],'approved')
        self.assertEqual(len(case['events']),5)

    def test_rejection_rework_and_concurrent_revision(self):
        act(self.db,self.case,'start','analyst-demo',note='Investigation commencee')
        self.proposal()
        act(self.db,self.case,'reject','reviewer-demo',note='Pieces insuffisantes dans ce test')
        act(self.db,self.case,'start','analyst-demo',note='Reprise avec nouvelles pieces')
        self.proposal()
        before=show_case(self.db,self.case)
        self.assertEqual(len(before['proposals']),2)
        self.assertEqual(before['proposals'][0]['decision'],'rejected')
        with self.assertRaises(WorkflowError):act(self.db,self.case,'comment','analyst-demo',note='Ancienne revision',expected_revision=0)
        self.assertEqual(show_case(self.db,self.case)['case']['revision'],before['case']['revision'])

    def test_foreign_evidence_rolls_back(self):
        act(self.db,self.case,'start','analyst-demo',note='Investigation commencee')
        with self.assertRaises(WorkflowError):self.proposal(refs=[999999])
        case=show_case(self.db,self.case)
        self.assertEqual(case['case']['workflow_status'],'in_review')
        self.assertEqual(case['proposals'],[])
        self.assertEqual(len(case['events']),2)

    def test_two_simultaneous_decisions_do_not_overwrite_each_other(self):
        act(self.db,self.case,'start','analyst-demo',note='Revue de recette')
        self.proposal();barrier=Barrier(2)
        def decision(action,reviewer):
            with psycopg.connect(**{**self.config,'dbname':self.test_db},autocommit=True) as db:
                db.execute("SET statement_timeout='20s'")
                barrier.wait(timeout=10)
                try:
                    act(db,self.case,action,reviewer,note='Decision concurrente de test',expected_revision=2)
                    return 'accepted'
                except WorkflowError:return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(decision,action,reviewer) for action,reviewer in [('approve','reviewer-one'),('reject','reviewer-two')]]
            outcomes=[future.result(timeout=30) for future in futures]
        self.assertEqual(sorted(outcomes),['accepted','conflict'])
        detail=show_case(self.db,self.case)
        self.assertEqual(detail['case']['revision'],3)
        self.assertEqual(len(detail['events']),4)
        self.assertIn(detail['proposals'][0]['decision'],['approved','rejected'])


if __name__=='__main__':unittest.main(verbosity=2)
