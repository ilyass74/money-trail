"""Un artefact partiel ou d'un autre calcul ne peut autoriser une publication."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from money_trail.publication import validate_build,validate_variables,candidate_inputs,PublicationError


def build_artifacts():
    prefix='mtpub_'+uuid4().hex+'_';ids=[str(uuid4())]
    nodes={}
    for path in (ROOT/'dbt/models').rglob('*.sql'):
        nodes['model.money_trail.'+path.stem]=dict(resource_type='model',schema=prefix+path.parent.name)
    for path in (ROOT/'dbt/tests').glob('*.sql'):
        nodes['test.money_trail.'+path.stem]=dict(resource_type='test',original_file_path='tests/'+path.name)
    for index in range(12):nodes[f'test.money_trail.not_null_{index}']=dict(resource_type='test',original_file_path='models/schema.yml')
    manifest=dict(metadata={'invocation_id':'one-invocation'},nodes=nodes)
    report=dict(metadata={'invocation_id':'one-invocation','generated_at':'2026-10-05T00:00:00Z'},
                args={'vars':dict(mt_schema_prefix=prefix,mt_batch_ids=ids)},
                results=[dict(unique_id=key,status='success' if key.startswith('model.') else 'pass') for key in nodes])
    return report,manifest,prefix,ids


class PublicationProofTests(unittest.TestCase):
    def validate(self,report,manifest,prefix,ids):
        return validate_build(json.dumps(report).encode(),json.dumps(manifest).encode(),prefix,ids)

    def test_complete_build_proves_its_scope_and_invocation(self):
        report,manifest,prefix,ids=build_artifacts();proof=self.validate(report,manifest,prefix,ids)
        self.assertEqual(proof['passed_tests'],21);self.assertEqual(proof['successful_models'],18)
        self.assertEqual(proof['input_batch_ids'],ids)

    def test_partial_build_cannot_publish(self):
        report,manifest,prefix,ids=build_artifacts();report['results'].pop()
        with self.assertRaises(PublicationError):self.validate(report,manifest,prefix,ids)

    def test_failed_test_cannot_publish(self):
        report,manifest,prefix,ids=build_artifacts();report['results'][-1]['status']='fail'
        with self.assertRaises(ValueError):self.validate(report,manifest,prefix,ids)

    def test_mixed_invocations_cannot_publish(self):
        report,manifest,prefix,ids=build_artifacts();manifest['metadata']['invocation_id']='another-invocation'
        with self.assertRaises(PublicationError):self.validate(report,manifest,prefix,ids)

    def test_other_snapshot_cannot_publish(self):
        report,manifest,prefix,ids=build_artifacts();report['args']['vars']['mt_batch_ids']=[str(uuid4())]
        with self.assertRaises(PublicationError):self.validate(report,manifest,prefix,ids)

    def test_model_outside_candidate_schema_cannot_publish(self):
        report,manifest,prefix,ids=build_artifacts();manifest['nodes']['model.money_trail.invoice_reconciliation']['schema']='marts'
        with self.assertRaises(PublicationError):self.validate(report,manifest,prefix,ids)

    def test_identifiers_and_duplicate_inputs_are_rejected(self):
        for prefix,ids in [('marts; drop schema raw;', [str(uuid4())]),('mtpub_'+uuid4().hex+'_', ["x'::uuid)"]),
                           ('mtpub_'+uuid4().hex+'_', []),('mtpub_'+uuid4().hex+'_', ['a','a'])]:
            with self.assertRaises(ValueError):validate_variables(dict(mt_schema_prefix=prefix,mt_batch_ids=ids))

    def test_two_versions_of_the_same_scope_cannot_be_summed(self):
        ids=[str(uuid4()),str(uuid4())]
        rows=[dict(batch_id=value,company_id='DEMO_MA',currency='MAD',contract_version='reference-v1') for value in ids]
        with patch('money_trail.publication._rows',return_value=rows):
            with self.assertRaises(PublicationError):candidate_inputs(None,ids)
