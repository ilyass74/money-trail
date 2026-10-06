"""Le lanceur attend la fin du processus et transmet les secrets hors arguments."""
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch
from subprocess import CompletedProcess

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from run_dbt import invoke_dbt


class ProcessTests(unittest.TestCase):
    def test_child_environment_and_exit_status(self):
        config=dict(host='127.0.0.1',port=55432,user='test',password='fixture_secret',dbname='isolated')
        before=dict(os.environ)
        with patch('run_dbt.subprocess.run',return_value=CompletedProcess([],0)) as run:
            self.assertTrue(invoke_dbt('build',config,Path('artifacts')))
        args=run.call_args.args[0]
        self.assertEqual(args[0],sys.executable)
        self.assertTrue(args[1].endswith('dbt_worker.py'))
        self.assertNotIn(config['password'],' '.join(args))
        self.assertEqual(run.call_args.kwargs['env']['DBT_ENV_SECRET_MT_PASSWORD'],config['password'])
        self.assertEqual(dict(os.environ),before)

    def test_failed_child_is_not_success(self):
        config=dict(host='127.0.0.1',port=55432,user='test',password='fixture_secret',dbname='isolated')
        with patch('run_dbt.subprocess.run',return_value=CompletedProcess([],1)):
            self.assertFalse(invoke_dbt('build',config))


if __name__=='__main__':unittest.main()
