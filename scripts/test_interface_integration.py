"""Tests comptes, sessions et autorisation dans une base temporaire distincte."""
from pathlib import Path
from uuid import uuid4
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import psycopg
from psycopg import sql
from money_trail.importer import local_config,setup_database,import_directory
from money_trail.reference import create_reference
from money_trail.workflow import setup_workflow,sync_cases,resolve_case,show_case,WorkflowError
from money_trail.local_auth import setup_accounts,create_user,login,active_user,logout,authenticated_action


class InterfaceIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        source=Path(self.tmp.name)/'data';create_reference(source)
        config=local_config();self.test_db='moneytrail_ui_test_'+uuid4().hex
        self.admin=psycopg.connect(**config,autocommit=True);self.addCleanup(self.admin.close)
        self.admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(self.test_db)));self.addCleanup(self.drop_database)
        self.db=psycopg.connect(**{**config,'dbname':self.test_db},autocommit=True);self.addCleanup(self.db.close)
        setup_database(self.db);setup_workflow(self.db);setup_accounts(self.db)
        batch=import_directory(self.db,source)['batch_id']
        sync_cases(self.db,[{'kind':'settlement','object_id':'LOT001','result':dict(import_batch_id=batch,company_id='DEMO_MA',currency='MAD',rule_version='settlement-v1',status='ecart'),
                            'line_evidence':[]}],'fixture-creator')
        self.case=resolve_case(self.db,batch,'settlement','LOT001')
        self.password='fixture-password-only'
        for name,role in [('analyst-demo','analyst'),('reviewer-demo','reviewer'),('viewer-demo','viewer'),('admin-demo','admin')]:create_user(self.db,name,self.password,role)

    def drop_database(self):self.admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(self.test_db)))

    def test_login_logout_and_migration_repeat(self):
        setup_accounts(self.db)
        self.assertIsNone(login(self.db,'analyst-demo','wrong'))
        token=login(self.db,'analyst-demo',self.password)
        self.assertEqual(active_user(self.db,token)['role'],'analyst')
        logout(self.db,token);self.assertIsNone(active_user(self.db,token))
        self.assertFalse(create_user(self.db,'analyst-demo','replacement-password','admin'))
        self.assertEqual(self.db.execute('SELECT count(*) FROM meta.schema_migrations').fetchone()[0],3)

    def test_authenticated_roles_and_actor(self):
        viewer=login(self.db,'viewer-demo',self.password)
        with self.assertRaises(WorkflowError):authenticated_action(self.db,viewer,self.case,'start',note='Forbidden')
        analyst=login(self.db,'analyst-demo',self.password)
        authenticated_action(self.db,analyst,self.case,'start',note='Revue du test',expected_revision=0)
        authenticated_action(self.db,analyst,self.case,'propose',proposal_type='source_data_review',description='Revoir la source',justification='Justification du test',expected_revision=1)
        with self.assertRaises(WorkflowError):authenticated_action(self.db,analyst,self.case,'approve',note='Forbidden')
        reviewer=login(self.db,'reviewer-demo',self.password)
        authenticated_action(self.db,reviewer,self.case,'approve',note='Decision du test',expected_revision=2)
        detail=show_case(self.db,self.case)
        self.assertEqual(detail['events'][1]['actor'],'analyst-demo')
        self.assertEqual(detail['proposals'][0]['decided_by'],'reviewer-demo')
        self.assertEqual(self.db.execute('SELECT count(*) FROM raw.source_records').fetchone()[0],26)

    def test_expired_session_cannot_write(self):
        token=login(self.db,'analyst-demo',self.password)
        self.db.execute("UPDATE app.local_sessions SET expires_at=CURRENT_TIMESTAMP - INTERVAL '1 second'")
        with self.assertRaises(WorkflowError):authenticated_action(self.db,token,self.case,'comment',note='Forbidden')
        self.assertEqual(show_case(self.db,self.case)['case']['revision'],0)

    def test_admin_cannot_approve_or_reject_financial_proposal(self):
        analyst=login(self.db,'analyst-demo',self.password)
        authenticated_action(self.db,analyst,self.case,'start',note='Revue')
        authenticated_action(self.db,analyst,self.case,'propose',proposal_type='source_data_review',description='Verifier la source',justification='Recette')
        token=login(self.db,'admin-demo',self.password)
        for action in ('approve','reject'):
            with self.assertRaises(WorkflowError):authenticated_action(self.db,token,self.case,action,note='Interdit')
        self.assertEqual(show_case(self.db,self.case)['case']['revision'],2)

    def test_deactivated_user_loses_existing_session(self):
        token=login(self.db,'analyst-demo',self.password)
        self.db.execute("UPDATE app.local_users SET active=false WHERE username='analyst-demo'")
        self.assertIsNone(active_user(self.db,token))
        with self.assertRaises(WorkflowError):authenticated_action(self.db,token,self.case,'comment',note='Interdit')
        self.assertEqual(show_case(self.db,self.case)['case']['revision'],0)

    def test_session_token_is_not_stored_in_cleartext(self):
        import hashlib
        token=login(self.db,'analyst-demo',self.password)
        stored=self.db.execute('SELECT token_hash FROM app.local_sessions').fetchone()[0]
        self.assertNotEqual(stored,token)
        self.assertEqual(stored,hashlib.sha256(token.encode()).hexdigest())


if __name__=='__main__':unittest.main(verbosity=2)
