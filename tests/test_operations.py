from pathlib import Path
import sys
import unittest
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from tempfile import TemporaryDirectory
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from money_trail.rules import validate_policy
from money_trail.operations import result_changes,evidence_signature
from money_trail.odoo_source import normalize_models,money,extract_models,MODELS,ExtractionError,freshness,OdooClient
from money_trail.odoo_bundle import create_bundles
from money_trail.reference import check_reference


def odoo_fixture():
    common=dict(company_id=[1,'Company'],currency_id=[1,'MAD'],write_date='2026-10-05 10:00:00')
    return {
     'account.move':[{**common,'id':1,'name':'INV/1','move_type':'out_invoice','state':'posted','amount_total':'120.00',
                      'invoice_date':'2026-10-01','invoice_date_due':'2026-10-20','reversed_entry_id':False,'invoice_line_ids':[1,2]}],
     'account.move.line':[{**common,'id':1,'move_id':[1,'INV/1'],'name':'A','quantity':'2.345','price_subtotal':'50.00','price_total':'60.00','display_type':'product','amount_currency':'60.00','balance':'60.00','date':'2026-10-01','payment_id':False},
       {**common,'id':2,'move_id':[1,'INV/1'],'name':'B','quantity':'1','price_subtotal':'50.00','price_total':'60.00','display_type':'product','amount_currency':'60.00','balance':'60.00','date':'2026-10-01','payment_id':False},
       {**common,'id':3,'move_id':[1,'INV/1'],'name':'Receivable','quantity':'0','price_subtotal':'0.00','price_total':'0.00','display_type':'payment_term','amount_currency':'120.00','balance':'120.00','date':'2026-10-01','payment_id':False},
       {**common,'id':4,'move_id':[2,'Payment'],'name':'Payment','quantity':'0','price_subtotal':'0.00','price_total':'0.00','display_type':False,'amount_currency':'-120.00','balance':'-120.00','date':'2026-10-02','payment_id':[1,'PAY/1']}],
     'account.payment':[{**common,'id':1,'amount':'120.00','state':'paid','date':'2026-10-02','payment_type':'inbound','partner_type':'customer','move_id':[2,'Payment']}],
     'account.partial.reconcile':[{**common,'id':1,'debit_move_id':[3,'Term'],'credit_move_id':[4,'Payment'],'amount':'120.00','debit_amount_currency':'120.00','credit_amount_currency':'120.00','max_date':'2026-10-02'}]}


class ReadOnlyAPI:
    def __init__(self,rows):self.rows=rows;self.calls=[];self.changed=False
    def call(self,model,method,args):
        self.calls.append((model,method,args))
        if method=='fields_get':return {k:{'type':'test'} for k in MODELS[model]}
        last=args['domain'][1][2]
        rows=[r for r in self.rows[model] if r['id']>last][:args['limit']]
        return [{k:r[k] for k in args['fields']} for r in rows]


class OperationTests(unittest.TestCase):
    def test_policy_has_bounded_decimal_precision_and_fixed_v1(self):
        for policy in [dict(version='v2',invoice_tolerance='NaN',settlement_tolerance='0.00'),dict(version='v1',invoice_tolerance='1.00',settlement_tolerance='0.00'),dict(version='v2',invoice_tolerance='100.01',settlement_tolerance='0.00')]:
            with self.assertRaises(ValueError):validate_policy(policy)
        self.assertEqual(validate_policy(dict(version='v2',invoice_tolerance='0.01',settlement_tolerance='30.00'))['version'],'v2')

    def test_comparison_excludes_execution_time_and_keeps_money_status(self):
        self.assertEqual(set(result_changes({'balance':'10.00','calculated_at':'one','status':'en_retard'},
                                          {'balance':'10.00','calculated_at':'two','status':'soldee'})),{'status'})

    def test_evidence_signature_ignores_row_ids_but_detects_corrected_sources(self):
        a={'result':{'control_on':'2026-10-05'},'line_evidence':[{'entity':'fees','source_id':'F1','payload_sha256':'a','record_id':1}],'source_coverage':[]}
        b=deepcopy(a);b['line_evidence'][0]['record_id']=2
        self.assertEqual(evidence_signature(a),evidence_signature(b));b['line_evidence'][0]['payload_sha256']='b'
        self.assertNotEqual(evidence_signature(a),evidence_signature(b))

    def test_extraction_keyset_read_only_and_complete_across_models(self):
        client=ReadOnlyAPI(odoo_fixture());stamp,rows=extract_models(client,1,page_size=2)
        self.assertEqual(rows,{model:[{k:r[k] for k in MODELS[model]} for r in items] for model,items in odoo_fixture().items()});self.assertIsNotNone(stamp.tzinfo)
        self.assertTrue(all(method in ('search_read','fields_get') for _,method,_ in client.calls))
        self.assertTrue(all(args.get('context',{}).get('allowed_company_ids')==[1] for _,_,args in client.calls))

    def test_model_change_during_extraction_is_refused(self):
        client=ReadOnlyAPI(odoo_fixture());original=client.call
        def changed(model,method,args):
            rows=original(model,method,args)
            if method=='search_read' and args['fields']==['id','company_id','write_date'] and rows:
                rows[0]['write_date']='2026-10-05 11:00:00'
            return rows
        client.call=changed
        with self.assertRaises(ExtractionError):extract_models(client,1)

    def test_quarantine_preserves_invalid_original_line(self):
        rows=odoo_fixture();rows['account.move'][0]['amount_total']='NaN'
        valid,rejected=normalize_models(rows,1)
        self.assertEqual(valid['account.move'],[]);self.assertEqual(rejected[0]['payload']['amount_total'],'NaN')

    def test_boolean_and_excess_precision_are_not_money(self):
        for value in [True,'Infinity','1.001','-1.00']:
            with self.assertRaises((ValueError,ArithmeticError)):money(value)

    def test_source_freshness_distinguishes_missing_old_and_future(self):
        now=datetime.now(timezone.utc)
        self.assertEqual(freshness(None,now),'inconnue')
        self.assertEqual(freshness(now-timedelta(hours=25),now),'obsolete')
        self.assertEqual(freshness(now+timedelta(seconds=1),now),'horodatage_futur')
        self.assertEqual(freshness(now,now),'fraiche')

    def test_bundle_retains_multiple_lines_and_one_payment_allocation(self):
        with TemporaryDirectory() as tmp:
            paths=create_bundles(dict(models=odoo_fixture(),company_id=1,source_as_of='2026-10-05T10:00:00+00:00',complete=True),Path(tmp)/'bundles','2026-10-05')
            checked=check_reference(paths[0]);self.assertEqual(checked['contract_version'],'finance-v1')
            import csv
            def rows(entity):
                with (paths[0]/(entity+'.csv')).open() as f:return list(csv.DictReader(f))
            self.assertEqual(len(rows('invoice_lines')),2);self.assertEqual(rows('invoice_lines')[0]['quantity'],'2.345')
            self.assertEqual(len(rows('invoice_allocations')),1);self.assertEqual(rows('invoice_allocations')[0]['amount'],'120.00')
            self.assertEqual(len(rows('erp_payments')),1)

    def test_unidentified_counterpart_blocks_coverage(self):
        rows=odoo_fixture();rows['account.move.line'][-1]['payment_id']=False
        with TemporaryDirectory() as tmp:
            path=create_bundles(dict(models=rows,company_id=1,source_as_of='2026-10-05T10:00:00+00:00',complete=True),Path(tmp)/'bundles')[0]
            import json
            self.assertFalse(json.loads((path/'manifest.json').read_text())['invoice_coverage']['invoice_allocations'])

    def test_remote_plain_http_and_write_methods_are_refused(self):
        with self.assertRaises(ExtractionError):OdooClient('http://example.com','x')
        client=OdooClient('http://localhost:8069','x')
        with self.assertRaises(ExtractionError):client.call('account.move','write',{})

    def test_csv_quarantine_invalid_parent_cascades_and_blocks_coverage(self):
        from money_trail.reference import create_reference,write_json
        from money_trail.quarantine import prepare_quarantine
        import csv,json,hashlib
        with TemporaryDirectory() as tmp:
            source=Path(tmp)/'raw';create_reference(source)
            file=source/'erp_payments.csv'
            with file.open() as f:reader=csv.DictReader(f);headers=reader.fieldnames;rows=list(reader)
            rows[0]['amount']='NaN'
            with file.open('w',newline='') as f:writer=csv.DictWriter(f,fieldnames=headers,lineterminator='\n');writer.writeheader();writer.writerows(rows)
            manifest=json.loads((source/'manifest.json').read_text())
            next(e for e in manifest['files'] if e['entity']=='erp_payments')['sha256']=hashlib.sha256(file.read_bytes()).hexdigest()
            write_json(source/'manifest.json',manifest)
            result=prepare_quarantine(source,Path(tmp)/'clean')
            self.assertTrue(any(r['entity']=='erp_payments' for r in result['rejected']))
            self.assertTrue(any(r['entity']=='invoice_allocations' for r in result['rejected']))
            self.assertTrue(all(not value for value in result['manifest']['invoice_coverage'].values()))
            self.assertIn('NaN',result['original_files']['erp_payments'])

    def test_csv_hash_mismatch_refuses_whole_file(self):
        from money_trail.reference import create_reference
        from money_trail.quarantine import prepare_quarantine
        with TemporaryDirectory() as tmp:
            source=Path(tmp)/'raw';create_reference(source)
            (source/'fees.csv').write_text('corrupted')
            with self.assertRaises(ValueError):prepare_quarantine(source,Path(tmp)/'clean')


if __name__=='__main__':unittest.main()
