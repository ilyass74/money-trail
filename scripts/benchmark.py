"""Benchmark natif isolé : 1 000 / 100 000 commandes, 1 million de transactions."""
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
import threading
import time
import statistics
import tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from money_trail.reference import HEADERS,write_json,check_reference
from money_trail.importer import setup_database,import_directory
from money_trail.publication import setup_publications,run_publication,read_publication
from money_trail.paging import page_records
from run_dbt import invoke_dbt
from testing_database import TemporaryDatabase


def generate(path,orders,transactions):
    """Génère en flux ; les volumes mesurés sont explicitement nommés."""
    path.mkdir();files=[]
    common=dict(company_id='BENCHMARK',source_system='synthetic',currency='MAD')
    for entity,headers in HEADERS.items():
        file=path/(entity+'.csv');count=0
        with file.open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=headers,lineterminator='\n');writer.writeheader()
            if entity=='orders':
                for i in range(orders):writer.writerow({**common,'source_id':f'O{i}','customer_ref':f'C{i}','total_amount':'1.00','ordered_at':'2026-10-01T00:00:00Z'});count+=1
            elif entity=='invoices':
                for i in range(orders):writer.writerow({**common,'source_id':f'I{i}','order_id':f'O{i}','state':'posted','total_amount':'1.00','issued_on':'2026-10-01','due_on':'2026-10-20'});count+=1
            elif entity=='erp_payments':
                for i in range(orders):writer.writerow({**common,'source_id':f'P{i}','state':'confirmed','amount':'1.00','paid_at':'2026-10-02T00:00:00Z'});count+=1
            elif entity=='invoice_allocations':
                for i in range(orders):writer.writerow({**common,'source_id':f'A{i}','invoice_id':f'I{i}','payment_id':f'P{i}','amount':'1.00','state':'confirmed'});count+=1
            elif entity=='settlement_batches':
                writer.writerow({**common,'source_id':'B1','period_start':'2026-10-01T00:00:00Z','period_end':'2026-10-02T00:00:00Z','expected_receipt_on':'2026-10-03'});count=1
            elif entity=='processor_payments':
                for i in range(transactions):writer.writerow({**common,'source_id':f'T{i}','batch_id':'B1','state':'captured','amount':'1.00','captured_at':'2026-10-01T12:00:00Z'});count+=1
            elif entity=='bank_movements':
                writer.writerow({**common,'source_id':'M1','reference':'B1','amount':f'{transactions}.00','value_on':'2026-10-03','booked_on':'2026-10-03'});count=1
            elif entity=='bank_allocations':
                writer.writerow({**common,'source_id':'BA1','movement_id':'M1','batch_id':'B1','amount':f'{transactions}.00','state':'confirmed'});count=1
        files.append(dict(entity=entity,file=file.name,row_count=count,sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
    write_json(path/'manifest.json',dict(contract_version='finance-v1',synthetic=True,company_id='BENCHMARK',currency='MAD',control_on='2026-10-05',files=files,
        invoice_coverage={key:True for key in ('invoices','erp_payments','invoice_allocations','credit_notes')},
        settlement_coverage=[{**common,'batch_id':'B1','entity':entity,'complete':True,'evidence':'synthetic_benchmark'} for entity in ('processor_payments','refunds','fees','adjustments','bank_movements','bank_allocations')]))
    return sum(item['row_count'] for item in files)


def measured(operation):
    import psutil
    process=psutil.Process();stop=threading.Event();samples=[]
    def sample():
        while not stop.is_set():
            family=[process]+process.children(recursive=True);rss=cpu=0
            for p in family:
                try:
                    rss+=p.memory_info().rss;t=p.cpu_times();cpu+=t.user+t.system
                except (psutil.NoSuchProcess,psutil.AccessDenied):pass
            samples.append((rss,cpu));stop.wait(.1)
    monitor=threading.Thread(target=sample,daemon=True);monitor.start();started=time.perf_counter()
    try:value=operation()
    finally:stop.set();monitor.join()
    return value,dict(wall_seconds=round(time.perf_counter()-started,3),peak_client_family_rss_bytes=max((r for r,c in samples),default=0),
        client_cpu_sample_delta_seconds=round(max((c for r,c in samples),default=0)-min((c for r,c in samples),default=0),3),
        server_cpu_ram='not_included_in_client_metrics')


def server_stats(config):
    # Docker stats ne journalise ni données métier ni credentials.
    try:
        run=subprocess.run(['docker','compose','stats','--no-stream','--format','json','postgres'],cwd=ROOT,capture_output=True,text=True,check=True,timeout=20)
        return {'docker_stats':run.stdout.strip(),'scope':'server_container_after_stage'}
    except Exception:return {'server_resource_measurement':'unavailable'}


def one_level(name,orders,transactions,output):
    folder=output/name;folder.mkdir();report=dict(level=name,orders=orders,processor_transactions=transactions,
        started_at=datetime.now(timezone.utc).isoformat(),status='running',hardware=dict(os=platform.platform(),machine=platform.machine(),cpu_count=os.cpu_count()))
    report_path=folder/'measurements.json'
    try:
        with TemporaryDatabase(prefix='moneytrail_benchmark_') as sandbox:
            version=sandbox.db.execute('SELECT version()').fetchone()[0];report['database']=version
            if 'PGlite' in version:raise ValueError('Mesurer les trois niveaux uniquement sur PostgreSQL natif.')
            setup_database(sandbox.db);setup_publications(sandbox.db)
            count,report['generate']=measured(lambda:generate(folder/'data',orders,transactions));report['raw_rows']=count
            _,report['validation']=measured(lambda:check_reference(folder/'data'))
            imported,report['import']=measured(lambda:import_directory(sandbox.db,folder/'data'))
            report['server_after_import']=server_stats(sandbox.config)
            published,report['publication']=measured(lambda:run_publication(sandbox.config,lambda cfg,path,variables:invoke_dbt('build',cfg,path,variables),
                batch_ids=[imported['batch_id']],artifact_parent=folder/'artifacts'))
            report['server_after_publication']=server_stats(sandbox.config)
            samples=[]
            for _ in range(20):
                start=time.perf_counter();page=page_records(sandbox.db,imported['batch_id'],published['publication_id'],limit=25);samples.append((time.perf_counter()-start)*1000)
                if len(page['dossiers'])>25 or page['total']!=orders+1:raise AssertionError('Pagination incoherente.')
            report['page_read_ms']=dict(median=statistics.median(samples),p95=sorted(samples)[18],samples=samples)
            report['database_size_bytes']=sandbox.db.execute('SELECT pg_database_size(current_database())').fetchone()[0]
            report['status']='passed'
    except Exception as error:report['status']='failed';report['error_code']=type(error).__name__;raise
    finally:write_json(report_path,report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--levels',nargs='+',choices=['small','medium','million'],default=['small','medium','million'])
    p.add_argument('--output',type=Path,default=ROOT/'reports'/('benchmark_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')))
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    levels={'small':(1000,1000),'medium':(100000,100000),'million':(100000,1000000)}
    results=[]
    for name in args.levels:
        print('BENCHMARK '+name,flush=True);results.append(one_level(name,*levels[name],args.output))
    write_json(args.output/'report.json',{'results':results,'production_capacity_certified':False})
    print('BENCHMARK_EXECUTED: '+str(args.output))


if __name__=='__main__':main()
