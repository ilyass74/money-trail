"""Contrôles des fixtures, distincts des futurs tests du moteur métier."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from money_trail.reference import create_reference, check_reference, read_json, write_json


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'reference'
        create_reference(self.path)

    def replace_csv(self, filename, before, after):
        path = self.path / filename
        path.write_text(path.read_text(encoding='utf-8').replace(before, after), encoding='utf-8')
        manifest = read_json(self.path / 'manifest.json')
        for item in manifest['files']:
            if item['file'] == filename:
                item['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        write_json(self.path / 'manifest.json', manifest)

    def test_valid_reference_and_counts(self):
        result = check_reference(self.path)
        self.assertEqual(result['status'], 'REFERENCE_OK')
        self.assertEqual(result['files_checked'], 12)
        self.assertEqual(result['rows_checked'], 26)
        self.assertFalse(result['financial_engine_tested'])

    def test_generation_is_deterministic_and_does_not_overwrite(self):
        second = Path(self.tmp.name) / 'second'
        create_reference(second)
        self.assertEqual({p.name: p.read_bytes() for p in self.path.iterdir()},
                         {p.name: p.read_bytes() for p in second.iterdir()})
        with self.assertRaisesRegex(ValueError, 'contient deja'):
            create_reference(self.path)

    def test_changed_source_is_detected(self):
        path = self.path / 'fees.csv'
        path.write_bytes(path.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'Empreinte'):
            check_reference(self.path)

    def test_orphan_reference_is_rejected(self):
        self.replace_csv('invoice_allocations.csv', 'FAC001', 'FAC999')
        with self.assertRaisesRegex(ValueError, 'Reference absente'):
            check_reference(self.path)

    def test_float_like_money_is_rejected(self):
        self.replace_csv('fees.csv', '20.00', '20.001')
        with self.assertRaisesRegex(ValueError, 'Montant invalide'):
            check_reference(self.path)

    def test_missing_coverage_is_rejected(self):
        manifest = read_json(self.path / 'manifest.json')
        manifest['settlement_coverage'].pop()
        write_json(self.path / 'manifest.json', manifest)
        with self.assertRaisesRegex(ValueError, 'Couverture des sources'):
            check_reference(self.path)

    def test_known_zero_and_unknown_fees_stay_distinct(self):
        manifest = read_json(self.path / 'manifest.json')
        coverage = {item['batch_id']: item['complete'] for item in manifest['settlement_coverage']
                    if item['entity'] == 'fees'}
        self.assertFalse(coverage['LOT003'])
        self.assertTrue(coverage['LOT004'])
        expected = read_json(ROOT / 'fixtures' / 'expected_results.json')
        batches = {item['batch_id']: item for item in expected['settlement_results']}
        self.assertIsNone(batches['LOT003']['expected_amount'])
        self.assertIsNone(batches['LOT003']['difference'])
        self.assertEqual(batches['LOT004']['difference'], '0.00')


if __name__ == '__main__':
    unittest.main()
