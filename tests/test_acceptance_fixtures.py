"""Contrats invalides et catalogue de recette ; les chiffres sont testés en SQL."""
from pathlib import Path
from copy import deepcopy
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from money_trail.acceptance_cases import cases,create_case,expected
from money_trail.reference import check_reference
from money_trail.importer import prepare_bundle
from money_trail.local_auth import authorize
from money_trail.workflow import WorkflowError


class AcceptanceFixtureTests(unittest.TestCase):
    def test_catalog_sources_validate_and_expected_amounts_are_strings(self):
        with tempfile.TemporaryDirectory() as temporary:
            for case in cases():
                with self.subTest(case=case['id']):
                    path=Path(temporary)/case['id'];create_case(path,case)
                    self.assertEqual(check_reference(path)['status'],'REFERENCE_OK')
                    self.assertEqual(len(prepare_bundle(path).files),12)
                    for rows in expected(case).values():
                        for row in rows.values():
                            for name,value in row.items():
                                if name.endswith('_amount') or name in ('balance','difference'):
                                    self.assertTrue(value is None or isinstance(value,str))

    def test_admin_cannot_validate_financial_proposals(self):
        authorize('admin','sync');authorize('admin','propose')
        for action in ('approve','reject'):
            with self.assertRaises(WorkflowError):authorize('admin',action)


INVALID_FIELDS=[
    ('negative_invoice','invoices','FAC001',{'total_amount':'-1.00'}),
    ('negative_refund','refunds','REM001',{'amount':'-1.00'}),
    ('nan_amount','fees','FR001',{'amount':'NaN'}),
    ('third_decimal','fees','FR001',{'amount':'20.001'}),
    ('decimal_comma','fees','FR001',{'amount':'20,00'}),
    ('overflow','fees','FR001',{'amount':'1000000000000000000.00'}),
    ('missing_id','fees','FR001',{'source_id':''}),
    ('wrong_currency','fees','FR001',{'currency':'EUR'}),
    ('wrong_company','fees','FR001',{'company_id':'OTHER'}),
    ('invalid_state','erp_payments','P001',{'state':'confirmedd'}),
    ('naive_timestamp','erp_payments','P001',{'paid_at':'2026-10-01T09:00:00'}),
    ('bad_date','invoices','FAC001',{'due_on':'2026-02-30'}),
    ('orphan_invoice','invoice_allocations','A001',{'invoice_id':'UNKNOWN'}),
    ('orphan_bank','bank_allocations','AB001',{'movement_id':'UNKNOWN'}),
    ('undocumented_adjustment','adjustments',None,{'company_id':'DEMO_MA','source_system':'psp_demo','source_id':'AD001','currency':'MAD','batch_id':'LOT004','amount':'-25.00','reason':'','adjusted_at':'2026-09-28T11:00:00Z'}),
]


def field_test(entity,object_id,values):
    def test(self):
        case=deepcopy(cases()[0])
        case['patches']=[{'entity':entity,'id':object_id,'set':values} if object_id else {'entity':entity,'append':values}]
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'invalid';create_case(path,case)
            with self.assertRaises(ValueError):prepare_bundle(path)
    return test


for name,entity,object_id,values in INVALID_FIELDS:
    setattr(AcceptanceFixtureTests,'test_reject_'+name,field_test(entity,object_id,values))


class IdentityTests(unittest.TestCase):
    def test_same_business_id_from_two_sources_is_rejected(self):
        case=deepcopy(cases()[0])
        case['patches']=[{'entity':'processor_payments','append':dict(company_id='DEMO_MA',source_system='second_demo',source_id='CAP004',currency='MAD',batch_id='LOT004',state='captured',amount='1.00',captured_at='2026-09-28T12:00:00Z')}]
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'ambiguous';create_case(path,case)
            with self.assertRaisesRegex(ValueError,'ambigu'):prepare_bundle(path)
