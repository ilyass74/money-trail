"""Tests PostgreSQL dans une base temporaire distincte, supprimée en fin de test."""
from pathlib import Path
import sys
import tempfile
import unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / 'src'))
import psycopg
from psycopg import sql
from money_trail.reference import create_reference
from money_trail.importer import local_config,setup_database,import_directory,inspect_database


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name) / 'reference'
        create_reference(self.path)
        self.config=local_config()
        self.test_db='moneytrail_test_'+uuid4().hex
        self.admin=psycopg.connect(**self.config,autocommit=True)
        self.addCleanup(self.admin.close)
        self.admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(self.test_db)))
        self.addCleanup(self.drop_test_database)
        self.connection=psycopg.connect(**{**self.config,'dbname':self.test_db},autocommit=True)
        self.addCleanup(self.connection.close)
        setup_database(self.connection)

    def drop_test_database(self):
        self.admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(self.test_db)))

    def test_first_import_and_duplicate(self):
        first=import_directory(self.connection,self.path)
        second=import_directory(self.connection,self.path)
        result=inspect_database(self.connection)
        self.assertEqual(first['inserted_records'],26)
        self.assertEqual(second['status'],'skipped_duplicate')
        self.assertEqual(second['inserted_records'],0)
        self.assertEqual(first['batch_id'],second['batch_id'])
        self.assertEqual(result['totals'],{'batches':1,'files':12,'records':26})

    def test_validation_failure_leaves_no_raw_records(self):
        (self.path / 'fees.csv').write_bytes(b'bad source')
        with self.assertRaises(ValueError):
            import_directory(self.connection,self.path)
        result=inspect_database(self.connection)
        self.assertEqual(result['totals'],{'batches':0,'files':0,'records':0})
        self.assertEqual(result['attempts'],[{'status':'failed','count':1}])

    def test_partial_database_failure_rolls_back_then_retry_succeeds(self):
        def fail(index):
            if index==3:
                raise RuntimeError('failure injected by isolated test')
        with self.assertRaises(RuntimeError):
            import_directory(self.connection,self.path,fail_hook=fail)
        self.assertEqual(inspect_database(self.connection)['totals'],{'batches':0,'files':0,'records':0})
        result=import_directory(self.connection,self.path)
        self.assertEqual(result['inserted_records'],26)

    def test_setup_can_be_repeated(self):
        setup_database(self.connection)
        self.assertEqual(self.connection.execute('SELECT count(*) FROM meta.schema_migrations').fetchone()[0],1)

    def test_two_simultaneous_imports_create_one_snapshot(self):
        barrier=Barrier(2)
        def attempt():
            with psycopg.connect(**{**self.config,'dbname':self.test_db},autocommit=True) as db:
                db.execute("SET statement_timeout='20s'")
                barrier.wait(timeout=10)
                return import_directory(db,self.path)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(attempt) for _ in range(2)]
            results=[future.result(timeout=30) for future in futures]
        self.assertEqual(sorted(row['status'] for row in results),['skipped_duplicate','success'])
        self.assertEqual(len({row['batch_id'] for row in results}),1)
        self.assertEqual(inspect_database(self.connection)['totals'],{'batches':1,'files':12,'records':26})


if __name__=='__main__':
    unittest.main(verbosity=2)
