"""Tests des parcours Streamlit avec services simulés ; aucun accès PostgreSQL."""
from pathlib import Path
from datetime import date,datetime,timezone
from decimal import Decimal
from copy import deepcopy
import json
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from streamlit.testing.v1 import AppTest
from money_trail.investigation import explanation,serializable


def fixture_view():
    expected=json.loads((ROOT/'fixtures/expected_results.json').read_text(encoding='utf-8'))
    source=json.loads((ROOT/'fixtures/reference_source.json').read_text(encoding='utf-8'))
    manifest=json.loads((ROOT/'data/reference_v1/manifest.json').read_text(encoding='utf-8'))
    snapshot={'batch_id':'fixture-batch','company_id':'DEMO_MA','currency':'MAD','control_on':date(2026,10,5),'ingested_at':datetime(2026,10,5,tzinfo=timezone.utc),'fingerprint':'fixture'}
    files=[dict(file_id=i,entity=entry['entity'],source_filename=entry['file'],sha256=entry['sha256'],row_count=entry['row_count']) for i,entry in enumerate(manifest['files'],1)]
    evidence=[]
    for kind,targets in [('invoice',expected['invoice_results']),('settlement',expected['settlement_results'])]:
        for target in targets:
            r={**target,'company_id':'DEMO_MA','currency':'MAD','import_batch_id':'fixture-batch','control_on':date(2026,10,5),
               'rule_version':kind+'-v1','quality':target.get('quality','complete'),'cause':target.get('cause')}
            key='invoice_id' if kind=='invoice' else 'batch_id';oid=r[key]
            for name in list(r):
                if name.endswith('_amount') or name in ('balance','difference'):
                    if r[name] is not None:r[name]=Decimal(r[name])
            if kind=='invoice':
                r['due_on']=date(2026,10,20);coverage=manifest['invoice_coverage']
                selected=[('invoices',source['invoices'][0],'context')]+[('invoice_allocations',row,'contribution') for row in source['invoice_allocations']]
            else:
                r.update(captured_amount=Decimal('1000.00'),refunded_amount=Decimal('100.00') if oid in ('LOT001','LOT002') else Decimal('0.00'),
                         fees_amount=Decimal('20.00') if oid in ('LOT001','LOT002') else None if oid=='LOT003' else Decimal('0.00'),adjustments_amount=Decimal('0.00'),
                         period_start=datetime(2026,9,28,tzinfo=timezone.utc),period_end=datetime(2026,9,29,tzinfo=timezone.utc),expected_receipt_on=date(2026,10,2))
                coverage=[item for item in manifest['settlement_coverage'] if item['batch_id']==oid]
                selected=[('settlement_batches',row,'context') for row in source['settlement_batches'] if row['source_id']==oid]
                for entity in ('processor_payments','refunds','fees','adjustments','bank_allocations'):
                    selected.extend((entity,row,'contribution') for row in source[entity] if row['batch_id']==oid)
                selected.extend(('bank_movements',row,'context') for row in source['bank_movements'] if row['reference']==oid)
            lines=[dict(entity=entity,source_id=row['source_id'],source_filename=entity+'.csv',source_system=row['source_system'],data_row_number=i,record_id=i,
                        file_id=i,file_sha256='fixture',payload_sha256='fixture',raw_payload=row,role=role,included_in_observed_sum=role=='contribution',exclusion_reasons=[])
                   for i,(entity,row,role) in enumerate(selected,1)]
            evidence.append(dict(kind=kind,object_id=oid,result=r,explanation=explanation(kind,r,coverage),snapshot=snapshot,source_files=files,
                                 source_coverage=coverage,line_evidence=lines,dbt_build_evidence={'passed_tests':19},generated_at='2026-10-05T16:00:00Z'))
    cases=[];details={}
    for oid,status,revision in [('LOT001','in_review',2),('LOT003','open',0)]:
        d=next(item for item in evidence if item['object_id']==oid)
        case=dict(case_id='case-'+oid,object_kind='settlement',object_id=oid,business_status=d['result']['status'],workflow_status=status,revision=revision,created_by='Ilyass',evidence=d)
        cases.append(case);details[case['case_id']]=dict(case=case,proposals=[],events=[dict(actor='Ilyass',action='created',revision=0,occurred_at='2026-10-05T16:00:00Z',details={'note':'Dossier de test'})])
    return snapshot,dict(dossiers=evidence,cases=cases,case_details=details,attempts=[dict(status='success',inserted_records=26)],unassigned_attempts=[],build={'passed_tests':19})


class InterfaceUITests(unittest.TestCase):
    def setUp(self):
        self.snapshot,self.view=fixture_view()
        for function,value in [('session_user',dict(username='ilyass',role='admin')),('snapshots',[self.snapshot]),('load_snapshot',self.view)]:
            patcher=patch('money_trail.ui_service.'+function,return_value=value);patcher.start();self.addCleanup(patcher.stop)

    def app(self):
        at=AppTest.from_file(str(ROOT/'ui/app.py'),default_timeout=20)
        at.session_state['mt_session']='fixture-token';at.run();self.assert_ok(at);return at

    def assert_ok(self,at):
        self.assertEqual(len(at.exception),0)
        self.assertEqual(len(at.error),0)

    def test_login_is_shown_without_session(self):
        at=AppTest.from_file(str(ROOT/'ui/app.py'),default_timeout=20).run()
        self.assert_ok(at);self.assertTrue(any(item.label=='Se connecter' for item in at.button))

    def test_all_five_pages_render(self):
        at=self.app()
        for page in ['Dossiers','Détail du dossier','Propositions et validation','Qualité et imports','Vue d’ensemble']:
            at.radio(key='nav_page').set_value(page).run();self.assert_ok(at)

    def test_missing_fees_and_known_discrepancy_are_displayed(self):
        at=self.app();at.radio(key='nav_page').set_value('Détail du dossier').run()
        at.selectbox(key='detail_choice').set_value('settlement:LOT003').run();self.assert_ok(at)
        self.assertEqual(at.metric[0].value,'Inconnu');self.assertEqual(at.metric[2].value,'Inconnu')
        self.assertTrue(any('bloqué' in item.value for item in at.warning))
        at.selectbox(key='detail_choice').set_value('settlement:LOT001').run();self.assert_ok(at)
        self.assertEqual(at.metric[0].value,'880,00 MAD');self.assertEqual(at.metric[2].value,'-30,00 MAD')

    def test_comment_uses_session_and_expected_revision(self):
        at=self.app();at.radio(key='nav_page').set_value('Détail du dossier').run()
        at.selectbox(key='detail_choice').set_value('settlement:LOT001').run()
        comment=next(item for item in at.text_area if item.label=='Ajouter un commentaire')
        comment.set_value('Commentaire du test')
        with patch('money_trail.ui_service.action',return_value={'revision':3}) as action:
            next(item for item in at.button if item.label=='Enregistrer le commentaire').click().run()
        self.assert_ok(at)
        self.assertEqual(action.call_args.args,('fixture-token','case-LOT001','comment'))
        self.assertEqual(action.call_args.kwargs['expected_revision'],2)

    def test_viewer_has_no_mutation_buttons(self):
        with patch('money_trail.ui_service.session_user',return_value=dict(username='viewer-demo',role='viewer')):
            at=self.app();at.radio(key='nav_page').set_value('Détail du dossier').run()
            at.selectbox(key='detail_choice').set_value('settlement:LOT001').run();self.assert_ok(at)
            buttons={item.label for item in at.button}
            self.assertNotIn('Enregistrer le commentaire',buttons)
            self.assertNotIn('Soumettre à validation',buttons)
            self.assertNotIn('Synchroniser les dossiers',buttons)

    def test_expired_session_returns_to_login(self):
        with patch('money_trail.ui_service.session_user',return_value=None):
            at=self.app()
            self.assertTrue(any(item.label=='Se connecter' for item in at.button))

    def test_reviewer_can_see_pending_decision(self):
        detail=self.view['case_details']['case-LOT001'];detail['case']['workflow_status']='awaiting_validation'
        detail['proposals']=[dict(proposal_number=1,proposal_type='allocation_review',description='Proposition du test',
                                 justification='Pieces du test',decision=None,proposed_by='analyst-demo',decision_note=None)]
        with patch('money_trail.ui_service.session_user',return_value=dict(username='reviewer-demo',role='reviewer')):
            at=self.app();at.radio(key='nav_page').set_value('Propositions et validation').run();self.assert_ok(at)
            self.assertTrue(any(item.label=='Enregistrer la décision' for item in at.button))

    def test_self_decision_is_hidden(self):
        detail=self.view['case_details']['case-LOT001'];detail['case']['workflow_status']='awaiting_validation'
        detail['proposals']=[dict(proposal_number=1,proposal_type='allocation_review',description='Proposition du test',
                                 justification='Pieces du test',decision=None,proposed_by='ilyass',decision_note=None)]
        at=self.app();at.radio(key='nav_page').set_value('Propositions et validation').run();self.assert_ok(at)
        self.assertFalse(any(item.label=='Enregistrer la décision' for item in at.button))

    def test_overview_button_opens_the_same_financial_result(self):
        at=self.app();at.button(key='open_LOT001').click().run();self.assert_ok(at)
        self.assertEqual(at.radio(key='nav_page').value,'Détail du dossier')
        self.assertEqual(at.selectbox(key='detail_choice').value,'settlement:LOT001')
        self.assertEqual(at.metric[2].value,'-30,00 MAD')

    def test_search_and_workflow_filter_preserve_case_selection(self):
        at=self.app();at.radio(key='nav_page').set_value('Dossiers').run()
        next(item for item in at.text_input if item.label=='Rechercher un dossier').set_value('lot003').run()
        selected=next(item for item in at.selectbox if item.label=='Dossier à ouvrir')
        self.assertEqual(selected.options,['settlement:LOT003'])
        next(item for item in at.multiselect if item.label=='État du suivi').set_value(['open']).run()
        next(item for item in at.button if item.label=='Consulter le dossier').click().run();self.assert_ok(at)
        self.assertEqual(at.selectbox(key='detail_choice').value,'settlement:LOT003')
        self.assertEqual(at.metric[0].value,'Inconnu')

    def test_export_contains_selected_snapshot_amounts_and_sources(self):
        from streamlit.delta_generator import DeltaGenerator
        original=DeltaGenerator.download_button;exports=[]
        def capture(generator,label,data,*args,**kwargs):
            exports.append((label,data))
            return original(generator,label,data,*args,**kwargs)
        with patch.object(DeltaGenerator,'download_button',capture):
            at=self.app();at.radio(key='nav_page').set_value('Détail du dossier').run()
            at.selectbox(key='detail_choice').set_value('settlement:LOT001').run();self.assert_ok(at)
        content=json.loads(next(data for label,data in reversed(exports) if label=='Télécharger le dossier JSON'))
        self.assertEqual(content['object_id'],'LOT001')
        self.assertEqual(content['snapshot']['batch_id'],'fixture-batch')
        self.assertEqual(content['result']['difference'],'-30.00')
        self.assertEqual(content['result']['currency'],'MAD')
        self.assertTrue(content['line_evidence'])
        markdown=next(data for label,data in reversed(exports) if label=='Télécharger l’explication')
        self.assertIn('880.00',markdown);self.assertIn('-30.00',markdown)
        self.assertIn('settlement-v1',markdown)

    def test_admin_cannot_decide_another_users_proposal(self):
        detail=self.view['case_details']['case-LOT001'];detail['case']['workflow_status']='awaiting_validation'
        detail['proposals']=[dict(proposal_number=1,proposal_type='allocation_review',description='Proposition du test',
                                 justification='Pieces du test',decision=None,proposed_by='analyst-demo',decision_note=None)]
        at=self.app();at.radio(key='nav_page').set_value('Propositions et validation').run();self.assert_ok(at)
        self.assertFalse(any(item.label=='Enregistrer la décision' for item in at.button))

    def test_unknown_bank_deadline_is_displayed_without_claiming_delay(self):
        d=next(item for item in self.view['dossiers'] if item['object_id']=='LOT002')
        d['result'].update(status='delai_a_confirmer',expected_receipt_on=None,received_amount=Decimal('0.00'),difference=Decimal('-880.00'),cause='non_identifiee')
        d['explanation']=explanation('settlement',d['result'],d['source_coverage'])
        at=self.app();at.radio(key='nav_page').set_value('Détail du dossier').run()
        at.selectbox(key='detail_choice').set_value('settlement:LOT002').run();self.assert_ok(at)
        rendered=' '.join(item.value for item in at.markdown)
        self.assertIn('Délai à confirmer',rendered);self.assertIn('Inconnue',rendered)

    def test_invoice_only_shows_financial_metrics_and_bank_limit(self):
        self.view['dossiers']=[d for d in self.view['dossiers'] if d['kind']=='invoice']
        self.view['cases']=[]
        at=self.app()
        self.assertEqual(at.metric[0].label,'À examiner')
        self.assertTrue(any('ne suffisent pas' in x.value for x in at.info))

    def test_no_cases_explains_how_to_start_followup(self):
        self.view['cases']=[]
        at=self.app();at.radio(key='nav_page').set_value('Dossiers').run();self.assert_ok(at)
        self.assertTrue(any('Le suivi reste à ouvrir' in x.value for x in at.markdown))
        self.assertTrue(any(x.label=='Synchroniser les dossiers' for x in at.button))

    def test_empty_validation_shows_decision_specific_state(self):
        self.view['cases']=[];self.view['dossiers']=[]
        at=self.app();at.radio(key='nav_page').set_value('Propositions et validation').run();self.assert_ok(at)
        self.assertTrue(any('Aucune proposition' in x.value for x in at.markdown))

    def published_view(self):
        self.snapshot.update(publication_id='publication-one',version=1,is_active=True)
        self.view['publication']=dict(publication_id='publication-one',version=1,published_at='2026-10-05T16:00:00+00:00')
        self.view['publication_health']=dict(latest_run={'status':'published'},imports_since_publication=[])
        return self.view

    def test_failed_calculation_keeps_visible_archived_amounts(self):
        self.published_view()['publication_health']['latest_run']={'status':'failed','failure_phase':'dbt'}
        at=self.app();self.assertTrue(any('dernier calcul a échoué' in item.value for item in at.warning))
        at.radio(key='nav_page').set_value('Détail du dossier').run()
        at.selectbox(key='detail_choice').set_value('settlement:LOT001').run();self.assert_ok(at)
        self.assertEqual(at.metric[0].value,'880,00 MAD');self.assertEqual(at.metric[2].value,'-30,00 MAD')
        at.selectbox(key='detail_choice').set_value('settlement:LOT003').run()
        self.assertEqual(at.metric[0].value,'Inconnu')

    def test_running_calculation_displays_publication_date(self):
        self.published_view()['publication_health']['latest_run']={'status':'building'}
        at=self.app();self.assertTrue(any('calcul est en cours' in item.value for item in at.info))
        self.assertTrue(any('05/10/2026 à 16:00 UTC' in item.value for item in at.caption))

    def test_failed_import_keeps_validated_version_visible(self):
        self.published_view()['publication_health']['imports_since_publication']=[dict(status='failed')]
        at=self.app();self.assertTrue(any('import récent a échoué' in item.value for item in at.warning))

    def test_archived_json_values_render_all_pages(self):
        view=serializable(self.published_view())
        with patch('money_trail.ui_service.load_snapshot',return_value=view):
            at=self.app()
            for page in ['Dossiers','Détail du dossier','Propositions et validation','Qualité et imports']:
                at.radio(key='nav_page').set_value(page).run();self.assert_ok(at)

    def test_two_publications_of_same_snapshot_are_selectable(self):
        self.published_view()
        newer={**self.snapshot,'publication_id':'publication-two','version':2}
        self.snapshot['is_active']=False
        with patch('money_trail.ui_service.snapshots',return_value=[newer,self.snapshot]),patch('money_trail.ui_service.load_snapshot',return_value=self.view) as load:
            at=self.app()
            choice=next(item for item in at.selectbox if item.label=='Version des résultats')
            self.assertEqual(len(choice.options),2)
            choice.set_value('publication-one:fixture-batch').run();self.assert_ok(at)
            self.assertEqual(load.call_args.args,('fixture-token','fixture-batch','publication-one'))
            self.assertTrue(any('version historique' in item.value for item in at.info))


if __name__=='__main__':unittest.main(verbosity=2)
