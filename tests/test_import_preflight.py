from pathlib import Path
import sys
import tempfile
import unittest
import json

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / 'src'))
from money_trail.reference import create_reference
from money_trail.importer import prepare_bundle,local_config


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name) / 'reference'
        create_reference(self.path)

    def test_repeat_import_has_same_fingerprint(self):
        self.assertEqual(prepare_bundle(self.path).fingerprint,prepare_bundle(self.path).fingerprint)

    def test_snapshot_survives_a_source_change(self):
        bundle=prepare_bundle(self.path)
        path=self.path / 'fees.csv'
        before=path.read_bytes()
        path.write_bytes(b'modified')
        self.assertEqual(next(f.content for f in bundle.files if f.entity=='fees'),before)
        with self.assertRaises(ValueError):
            prepare_bundle(self.path)

    def test_empty_sources_remain_evidence(self):
        bundle=prepare_bundle(self.path)
        empty=next(f for f in bundle.files if f.entity=='adjustments')
        self.assertEqual(len(empty.rows),0)
        self.assertTrue(empty.content.startswith(b'company_id,'))
        self.assertEqual(len(bundle.files),12)
        self.assertEqual(sum(len(f.rows) for f in bundle.files),26)

    def test_env_config_keeps_password_out_of_dsn(self):
        path=Path(self.tmp.name) / '.env'
        path.write_text('POSTGRES_PASSWORD=example_test_only\nPOSTGRES_PORT=55432\n',encoding='utf-8')
        config=local_config(path)
        self.assertEqual(config['host'],'127.0.0.1')
        self.assertEqual(config['port'],55432)
        self.assertEqual(config['password'],'example_test_only')

    def test_manifest_cannot_claim_another_company(self):
        path=self.path / 'manifest.json'
        manifest=json.loads(path.read_text(encoding='utf-8'))
        manifest['company_id']='OTHER_COMPANY'
        path.write_text(json.dumps(manifest),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Perimetre'):
            prepare_bundle(self.path)


if __name__=='__main__':
    unittest.main()
