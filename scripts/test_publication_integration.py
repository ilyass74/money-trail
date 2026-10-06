"""Scénarios réels PostgreSQL/dbt, uniquement dans une base temporaire."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from money_trail.acceptance_cases import cases,create_case
from money_trail.importer import setup_database,import_directory
from money_trail.investigation import _rows
from money_trail.publication import (setup_publications,run_publication,read_publication,
    published_snapshots,publication_health,PublicationError,PublicationBusy,PUBLICATION_LOCK,code_fingerprint)
from money_trail.workflow import setup_workflow,sync_cases,resolve_case,show_case,act
from money_trail.local_auth import setup_accounts,create_user,login
from money_trail import ui_service
from run_dbt import invoke_dbt,verify_reference
from testing_database import TemporaryDatabase,table_fingerprints


def runner(config,directory,variables):return invoke_dbt('build',config,directory,variables)


class PublicationIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.directory=Path(cls.tmp.name)
        cls.artifacts=Path(os.environ.get('MT_ACCEPTANCE_ARTIFACTS',cls.tmp.name))/'publication_runs'
        cls.sandbox=TemporaryDatabase(prefix='moneytrail_publication_');cls.addClassCleanup(cls.sandbox.close)
        cls.db=cls.sandbox.db;setup_database(cls.db);setup_workflow(cls.db);setup_accounts(cls.db);setup_publications(cls.db)
        cls.db.execute('CREATE TABLE marts.legacy_sentinel(value text)')
        cls.db.execute("INSERT INTO marts.legacy_sentinel VALUES ('ancienne-table-preservee')")
        create_user(cls.db,'publication-admin','synthetic-password-only','admin')
        cls.token=login(cls.db,'publication-admin','synthetic-password-only')
        cls.reference_path=cls.directory/'reference';create_case(cls.reference_path,cases()[0])
        cls.first_batch=import_directory(cls.db,cls.reference_path)['batch_id']
        def reference_check(db,inputs,prefix):verify_reference(db,inputs[0]['batch_id'],prefix)
        print('\nConstruction dbt : première publication réelle et archive de cinq dossiers.',flush=True)
        cls.first=run_publication(cls.sandbox.config,runner,actor='test',artifact_parent=cls.artifacts,validate_results=reference_check)
        cls.first_archive=read_publication(cls.db,cls.first_batch,cls.first['publication_id'])
        sync_cases(cls.db,cls.first_archive['dossiers'],'test-analyst')
        cls.case_id=resolve_case(cls.db,cls.first_batch,'settlement','LOT001')
        act(cls.db,cls.case_id,'start','test-analyst',note='Investigation avant le nouveau calcul')
        cls.case_before=show_case(cls.db,cls.case_id)
        bad=deepcopy(cases()[0]);bad['patches']=[dict(entity='invoice_allocations',id='A001',set={'amount':'601.00'})]
        bad_path=cls.directory/'invalid';create_case(bad_path,bad)
        cls.bad_batch=import_directory(cls.db,bad_path)['batch_id']
        cls.head_before=cls.db.execute('SELECT publication_id FROM app.publication_head').fetchone()[0]
        cls.archive_before=cls.archive_fingerprints()
        print('Build dbt volontairement invalide : la version publiée doit rester lisible.',flush=True)
        cls.observed_during_build=False
        def failing_runner(config,directory,variables):
            with psycopg.connect(**config,autocommit=True) as other:
                if other.execute('SELECT publication_id FROM app.publication_head').fetchone()[0]!=cls.head_before:
                    raise AssertionError('La publication visible a change pendant le build.')
                if read_publication(other,cls.first_batch)['dossiers']!=cls.first_archive['dossiers']:
                    raise AssertionError('Les preuves visibles ont change pendant le build.')
                cls.observed_during_build=publication_health(other,cls.first['published_at'])['latest_run']['status']=='building'
            return runner(config,directory,variables)
        try:
            run_publication(cls.sandbox.config,failing_runner,actor='test',artifact_parent=cls.artifacts)
        except PublicationError:pass
        else:raise AssertionError('Un build invalide a ete publie.')
        cls.failed_run=_rows(cls.db,"SELECT * FROM meta.publication_runs WHERE status='failed' ORDER BY started_at DESC LIMIT 1")[0]
        cls.head_after_failure=cls.db.execute('SELECT publication_id FROM app.publication_head').fetchone()[0]
        cls.archive_after_failure=cls.archive_fingerprints()
        cls.health_after_failure=publication_health(cls.db,cls.first['published_at'])
        revised=next(item for item in cases() if item['id']=='C42_late_fees_received')
        fixed_path=cls.directory/'revised';create_case(fixed_path,revised)
        cls.second_batch=import_directory(cls.db,fixed_path)['batch_id']
        cls.commit_observed=False
        def observe_commit(db,run_id):
            with psycopg.connect(**cls.sandbox.config,autocommit=True) as other:
                if other.execute('SELECT publication_id FROM app.publication_head').fetchone()[0]!=cls.head_before:
                    raise AssertionError('Un lecteur voit la nouvelle version avant le commit.')
                if other.execute('SELECT count(*) FROM app.result_publications').fetchone()[0]!=1:
                    raise AssertionError('Une archive partielle est visible avant le commit.')
                if len(read_publication(other,cls.first_batch)['dossiers'])!=5:raise AssertionError('Ancienne archive illisible.')
                cls.commit_observed=True
        print('Construction dbt : nouvelle source valide, historique invalide exclu du candidat.',flush=True)
        cls.second=run_publication(cls.sandbox.config,runner,actor='test',artifact_parent=cls.artifacts,before_commit=observe_commit)

    @classmethod
    def archive_fingerprints(cls):
        return {key:value for key,value in table_fingerprints(cls.db).items()
                if key.startswith(('app.result_publications','app.published_','app.publication_head'))}

    def publish(self,**kwargs):
        return run_publication(self.sandbox.config,runner,actor='test',artifact_parent=self.artifacts,**kwargs)

    def test_P01_failed_build_keeps_last_publication_and_archives(self):
        self.assertEqual(self.head_after_failure,self.head_before)
        self.assertEqual(self.archive_after_failure,self.archive_before)
        self.assertEqual(self.failed_run['failure_phase'],'dbt')
        self.assertTrue(any('allocation_limits' in row['unique_id'] and row['status']=='fail' for row in self.failed_run['failed_checks']))
        self.assertEqual(self.health_after_failure['latest_run']['status'],'failed')

    def test_P02_running_build_reads_old_version_until_commit(self):
        self.assertTrue(self.observed_during_build);self.assertTrue(self.commit_observed)
        self.assertEqual(self.db.execute('SELECT publication_id FROM app.publication_head').fetchone()[0],uuid_from(self.second['publication_id']))

    def test_P03_new_valid_source_recovers_without_rebuilding_invalid_history(self):
        archive=read_publication(self.db,self.second_batch,self.second['publication_id'])
        self.assertEqual(archive['build']['input_batch_ids'],[self.second_batch])
        self.assertNotIn(self.bad_batch,archive['build']['input_batch_ids'])
        lot=next(item for item in archive['dossiers'] if item['object_id']=='LOT003')
        self.assertEqual((lot['result']['expected_amount'],lot['result']['difference'],lot['result']['status']),('950.00','0.00','rapproche'))

    def test_P04_previous_publication_and_workflow_history_are_preserved(self):
        self.assertEqual(read_publication(self.db,self.first_batch,self.first['publication_id']),self.first_archive)
        observed=show_case(self.db,self.case_id)
        for key in ('case','proposals','events'):self.assertEqual(observed[key],self.case_before[key])
        self.assertEqual(len(published_snapshots(self.db)),2)

    def test_P05_error_just_before_commit_rolls_back_every_visible_write(self):
        before=self.archive_fingerprints();head=self.db.execute('SELECT publication_id FROM app.publication_head').fetchone()[0]
        def fail(db,run_id):raise RuntimeError('injected-test-before-commit')
        with self.assertRaises(RuntimeError):self.publish(before_commit=fail)
        self.assertEqual(self.archive_fingerprints(),before)
        self.assertEqual(self.db.execute('SELECT publication_id FROM app.publication_head').fetchone()[0],head)
        run=_rows(self.db,'SELECT * FROM meta.publication_runs ORDER BY started_at DESC LIMIT 1')[0]
        self.assertEqual((run['status'],run['failure_phase'],run['error_code']),('failed','commit','RuntimeError'))
        self.assertEqual(len(read_publication(self.db,self.second_batch)['dossiers']),5)

    def test_P06_source_integrity_failure_cannot_publish(self):
        before=self.archive_fingerprints()
        original=self.db.execute("SELECT source_bytes FROM meta.import_files WHERE batch_id=%s AND entity='fees'",(self.second_batch,)).fetchone()[0]
        def corrupt(config,directory,variables):
            result=runner(config,directory,variables)
            self.db.execute("UPDATE meta.import_files SET source_bytes=source_bytes || decode('20','hex') WHERE batch_id=%s AND entity='fees'",(self.second_batch,))
            return result
        try:
            with self.assertRaisesRegex(ValueError,'Integrite du fichier'):
                run_publication(self.sandbox.config,corrupt,artifact_parent=self.artifacts)
        finally:
            self.db.execute("UPDATE meta.import_files SET source_bytes=%s WHERE batch_id=%s AND entity='fees'",(original,self.second_batch))
        self.assertEqual(self.archive_fingerprints(),before)
        self.assertEqual(_rows(self.db,'SELECT failure_phase FROM meta.publication_runs ORDER BY started_at DESC LIMIT 1')[0]['failure_phase'],'evidence')

    def test_P07_failed_import_does_not_hide_published_results(self):
        path=self.directory/'broken_csv';create_case(path,cases()[0]);(path/'invoices.csv').write_text('broken',encoding='utf-8')
        with self.assertRaises(ValueError):import_directory(self.db,path)
        archive=read_publication(self.db,self.second_batch,self.second['publication_id'])
        self.assertTrue(any(row['status']=='failed' for row in publication_health(self.db,archive['publication']['published_at'])['imports_since_publication']))
        self.assertEqual(len(archive['dossiers']),5)

    def test_P08_second_publisher_is_refused_without_calling_dbt(self):
        self.db.execute('SELECT pg_advisory_lock(%s::bigint)',(PUBLICATION_LOCK,))
        try:
            with self.assertRaises(PublicationBusy):
                run_publication(self.sandbox.config,lambda *args:self.fail('dbt ne doit pas demarrer'),artifact_parent=self.artifacts)
        finally:self.db.execute('SELECT pg_advisory_unlock(%s::bigint)',(PUBLICATION_LOCK,))

    def test_P09_interrupted_run_is_audited_and_its_schemas_cleaned(self):
        run_id=uuid4();prefix='mtpub_'+run_id.hex+'_'
        self.db.execute("""INSERT INTO meta.publication_runs(run_id,status,actor,schema_prefix,input_batch_ids,code_sha256)
          VALUES (%s,'building','test',%s,%s,%s)""",(run_id,prefix,Jsonb([self.second_batch]),code_fingerprint()))
        self.db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(prefix+'marts')))
        # L'échec injecté après reprise évite un sixième build ; aucune donnée métier simulée.
        with self.assertRaises(RuntimeError):
            run_publication(self.sandbox.config,lambda *args:(_ for _ in ()).throw(RuntimeError('interruption-test')),artifact_parent=self.artifacts)
        row=_rows(self.db,'SELECT status,failure_phase,cleanup_status FROM meta.publication_runs WHERE run_id=%s',(run_id,))[0]
        self.assertEqual(row,dict(status='failed',failure_phase='interrupted',cleanup_status='complete'))
        self.assertIsNone(self.db.execute('SELECT to_regnamespace(%s)',(prefix+'marts',)).fetchone()[0])

    def test_P10_archive_is_read_without_live_models_or_sources(self):
        with self.db.transaction(force_rollback=True):
            self.db.execute("UPDATE meta.import_files SET source_bytes=decode('00','hex') WHERE batch_id=%s",(self.first_batch,))
            self.assertEqual(read_publication(self.db,self.first_batch,self.first['publication_id']),self.first_archive)
        self.assertEqual(self.db.execute('SELECT value FROM marts.legacy_sentinel').fetchone()[0],'ancienne-table-preservee')
        self.assertEqual(self.db.execute("SELECT count(*) FROM pg_namespace WHERE nspname ~ '^mtpub_[0-9a-f]{32}_'").fetchone()[0],0)

    def test_P11_archives_reject_updates_and_artifact_tampering(self):
        with self.db.transaction(force_rollback=True):
            with self.assertRaises(psycopg.Error):
                with self.db.transaction():self.db.execute("UPDATE app.published_dossiers SET dossier='{}'::jsonb")
        with self.db.transaction(force_rollback=True):
            self.db.execute("UPDATE meta.publication_runs SET run_results_bytes=decode('00','hex') WHERE run_id=%s",(self.first['publication_id'],))
            with self.assertRaisesRegex(PublicationError,'artefacts'):read_publication(self.db,self.first_batch,self.first['publication_id'])

    def test_P12_authenticated_service_reads_selected_archive(self):
        @contextmanager
        def connect():
            with psycopg.connect(**self.sandbox.config,autocommit=True) as db:yield db
        with patch('money_trail.ui_service.connect',connect):
            versions=ui_service.snapshots(self.token)
            view=ui_service.load_snapshot(self.token,self.first_batch,self.first['publication_id'])
            self.assertEqual(len(versions),2);self.assertEqual(view['dossiers'],self.first_archive['dossiers'])
            self.assertEqual(view['case_details'][str(self.case_id)],self.case_before)

    def test_P13_publications_survive_real_backup_and_restore(self):
        if not shutil.which('docker'):self.skipTest('Docker CLI absent : restauration non executee.')
        original=table_fingerprints(self.db);archive=self.directory/'published_backup.dump'
        command=['docker','compose','exec','-T','postgres','pg_dump','-U',self.sandbox.config['user'],'--format=custom','--dbname',self.sandbox.name]
        with archive.open('wb') as stream:result=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.PIPE,timeout=120)
        self.assertEqual(result.returncode,0,msg=result.stderr.decode(errors='replace')[-1200:])
        with TemporaryDatabase(prefix='moneytrail_publication_restore_') as restored:
            command=['docker','compose','exec','-T','postgres','pg_restore','-U',restored.config['user'],'--exit-on-error','--dbname',restored.name]
            with archive.open('rb') as stream:result=subprocess.run(command,cwd=ROOT,stdin=stream,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120)
            self.assertEqual(result.returncode,0,msg=result.stderr.decode(errors='replace')[-1200:])
            self.assertEqual(table_fingerprints(restored.db),original)
            self.assertEqual(read_publication(restored.db,self.first_batch,self.first['publication_id']),self.first_archive)
            self.assertEqual(len(read_publication(restored.db,self.second_batch)['dossiers']),5)
        print('RESTORATION_PUBLICATIONS_OK '+json.dumps({'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'tables_and_sequences_identical':True}),flush=True)


def uuid_from(value):
    from uuid import UUID
    return UUID(value)


if __name__=='__main__':unittest.main(verbosity=2)
