"""Validation du projet dbt sans connexion à PostgreSQL."""
from pathlib import Path
import os
import json
from uuid import uuid4
import tempfile
import unittest
from run_dbt import invoke_dbt


class DbtParseTests(unittest.TestCase):
    def test_project_parses_without_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(os.environ.get('MT_ACCEPTANCE_ARTIFACTS',temporary))/'parse'
            self.assertTrue(invoke_dbt('parse',dict(host='127.0.0.1',port=55432,user='offline',password='offline',dbname='offline'),directory))

    def test_candidate_schemas_parse_without_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(os.environ.get('MT_ACCEPTANCE_ARTIFACTS',temporary))/'candidate_parse'
            prefix='mtpub_'+uuid4().hex+'_'
            variables=dict(mt_schema_prefix=prefix,mt_batch_ids=[str(uuid4())])
            self.assertTrue(invoke_dbt('parse',dict(host='127.0.0.1',port=55432,user='offline',password='offline',dbname='offline'),directory,variables))
            manifest=json.loads((directory/'target/manifest.json').read_bytes())
            nodes=[node for node in manifest['nodes'].values() if node['resource_type']=='model']
            self.assertEqual(len(nodes),18)
            for node in nodes:
                self.assertEqual(node['schema'],prefix+Path(node['original_file_path']).parts[1])


if __name__=='__main__':unittest.main(verbosity=2)
