from datetime import date,datetime,timezone
from decimal import Decimal
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from money_trail.investigation import eligibility,explanation,payload_hash,read_build_evidence,serializable


class InvestigationTests(unittest.TestCase):
    def test_invoice_payment_at_cutoff_is_excluded(self):
        result={'control_on':date(2026,10,5)}
        row={'state':'confirmed'}
        payment={'state':'confirmed','paid_at':datetime(2026,10,6,tzinfo=timezone.utc)}
        self.assertFalse(eligibility('invoice_allocations',row,result,payment)['included_in_observed_sum'])
        payment['paid_at']=datetime(2026,10,5,23,59,59,tzinfo=timezone.utc)
        self.assertTrue(eligibility('invoice_allocations',row,result,payment)['included_in_observed_sum'])

    def test_period_end_is_exclusive(self):
        result={'control_on':date(2026,10,5),'period_start':datetime(2026,9,28,tzinfo=timezone.utc),'period_end':datetime(2026,9,29,tzinfo=timezone.utc)}
        row={'charged_at':result['period_start']}
        self.assertTrue(eligibility('fees',row,result)['included_in_observed_sum'])
        row['charged_at']=result['period_end']
        self.assertFalse(eligibility('fees',row,result)['included_in_observed_sum'])

    def test_bank_booking_and_value_dates_are_checked(self):
        result={'control_on':date(2026,10,5)}
        movement={'amount':Decimal('850.00'),'booked_on':date(2026,10,5),'value_on':date(2026,10,6)}
        decision=eligibility('bank_allocations',{'state':'confirmed'},result,movement)
        self.assertFalse(decision['included_in_observed_sum'])
        self.assertTrue(any('valeur' in text for text in decision['exclusion_reasons']))

    def test_missing_fees_remain_unknown_without_inventing_cause(self):
        result=dict(status='calcul_bloque',quality='donnees_incompletes',control_on=date(2026,10,5),
                    period_start=datetime(2026,9,28,tzinfo=timezone.utc),period_end=datetime(2026,9,29,tzinfo=timezone.utc),
                    expected_receipt_on=date(2026,10,2),captured_amount=Decimal('1000.00'),refunded_amount=Decimal('0.00'),
                    fees_amount=None,adjustments_amount=Decimal('0.00'),expected_amount=None,received_amount=Decimal('950.00'),difference=None,cause=None)
        e=explanation('settlement',result,[dict(entity='fees',complete=False)])
        self.assertIsNone(e['values']['expected_amount'])
        self.assertIsNone(e['cause'])
        self.assertEqual(e['missing_sources'],['fees'])
        self.assertIn('inconnu',e['worked_calculation'])
        self.assertFalse(e['accounting_correction_applied'])

    def test_not_due_invoice_is_not_described_as_overdue(self):
        result=dict(status='solde_en_attente',control_on=date(2026,10,5),due_on=date(2026,10,20),invoice_amount=Decimal('1000.00'),allocated_amount=Decimal('900.00'),credit_amount=Decimal('0.00'),balance=Decimal('100.00'))
        e=explanation('invoice',result,{'invoices':True,'erp_payments':True,'invoice_allocations':True,'credit_notes':True})
        self.assertEqual(e['date_facts']['days_overdue'],0)
        self.assertIn('n est pas en retard',e['summary'])
        self.assertEqual(e['worked_calculation'],'1000.00 - 900.00 - 0.00 = 100.00 MAD')

    def test_failed_build_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'run_results.json'
            path.write_text(json.dumps({'results':[{'status':'fail','unique_id':'test.money_trail.allocation_limits'}]}))
            with self.assertRaises(ValueError):read_build_evidence(path)

    def test_amounts_are_exported_as_decimal_strings(self):
        self.assertEqual(serializable({'amount':Decimal('880'),'missing':None}),{'amount':'880.00','missing':None})
        self.assertEqual(payload_hash({'amount':'880.00','id':'a'}),payload_hash({'id':'a','amount':'880.00'}))
        self.assertNotEqual(payload_hash({'amount':'880.00'}),payload_hash({'amount':'850.00'}))


if __name__=='__main__':unittest.main()
