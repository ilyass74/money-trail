"""Lance dbt avec les secrets en mémoire puis vérifie le jeu de référence."""
from pathlib import Path
from decimal import Decimal
import argparse
import json
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from money_trail.importer import local_config,prepare_bundle


def invoke_dbt(action, config, artifact_dir=None, variables=None):
    environment={'MT_HOST':config['host'],'MT_PORT':str(config['port']),
                 'MT_USER':config['user'],'MT_DATABASE':config['dbname'],
                 'DBT_ENV_SECRET_MT_PASSWORD':config['password'],
                 'DBT_SEND_ANONYMOUS_USAGE_STATS':'false'}
    args=[sys.executable,str(ROOT/'scripts/dbt_worker.py'),action,
          '--project-dir',str(ROOT/'dbt'),'--profiles-dir',str(ROOT/'dbt'),
          '--no-partial-parse','--no-use-colors']
    if artifact_dir:
        artifact_dir=Path(artifact_dir).resolve()
        args+=['--target-path',str(artifact_dir/'target'),'--log-path',str(artifact_dir/'logs')]
    if variables:
        from money_trail.publication import validate_variables
        validate_variables(variables)
        args+=['--vars',json.dumps(variables)]
    # Wait for process exit before temporary-directory cleanup, especially on Windows.
    result=subprocess.run(args,env={**os.environ,**environment},check=False)
    return result.returncode==0


def verify_reference(connection, batch_id, schema_prefix=''):
    expected=json.loads((ROOT/'fixtures/expected_results.json').read_text(encoding='utf-8'))
    from psycopg.rows import dict_row
    from psycopg import sql
    if schema_prefix:
        from money_trail.publication import validate_prefix
        validate_prefix(schema_prefix)
    output={}
    for kind,table,key in [('invoice','invoice_reconciliation','invoice_id'),
                           ('settlement','settlement_reconciliation','batch_id')]:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(sql.SQL('SELECT * FROM {}.{} WHERE import_batch_id=%s ORDER BY {}').format(
                sql.Identifier(schema_prefix+'marts'),sql.Identifier(table),sql.Identifier(key)),(batch_id,))
            rows=cursor.fetchall()
        targets=expected[kind+'_results']
        if len(rows)!=len(targets):raise AssertionError('Nombre de résultats différent du contrat.')
        index={row[key]:row for row in rows}
        for target in targets:
            row=index[target[key]]
            for column,value in target.items():
                if column in ('rule_refs','missing_source'):continue
                actual=row[column]
                if isinstance(actual,Decimal) and value is not None:value=Decimal(value)
                if actual!=value:raise AssertionError(f'{target[key]} / {column}: {actual} != {value}')
            if target.get('missing_source') and target['missing_source'] not in (row['missing_sources'] or '').split(', '):
                raise AssertionError('Source manquante non expliquée.')
            if row['company_id']!=expected['company_id'] or row['currency']!=expected['currency']:
                raise AssertionError('Périmètre différent.')
        output[kind+'_results']=rows
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['parse','build','results'])
    parser.add_argument('--batch-id',action='append',help='Snapshot à publier ; par défaut le dernier import du périmètre.')
    parser.add_argument('--rule-version',choices=['v1','v2'],default='v1')
    parser.add_argument('--invoice-tolerance',default='0.00')
    parser.add_argument('--settlement-tolerance',default='0.00')
    args=parser.parse_args()
    try:
        if args.action=='parse':
            config=dict(host='127.0.0.1',port=55432,user='offline',password='offline',dbname='offline')
        else:config=local_config()
        if args.action=='parse':
            return 0 if invoke_dbt('parse',config) else 1
        if args.action=='build':
            from money_trail.publication import run_publication
            from money_trail.rules import validate_policy
            policy=dict(version=args.rule_version,invoice_tolerance=args.invoice_tolerance,settlement_tolerance=args.settlement_tolerance)
            validate_policy(policy)
            reference_fingerprint=prepare_bundle(ROOT/'data/reference_v1').fingerprint
            verified=[]
            def validate(db,inputs,prefix):
                for row in inputs:
                    if row['fingerprint']==reference_fingerprint and policy['version']=='v1':
                        verify_reference(db,row['batch_id'],prefix);verified.append(str(row['batch_id']))
            result=run_publication(config,lambda cfg,path,variables:invoke_dbt('build',cfg,path,variables),
                                   batch_ids=args.batch_id,validate_results=validate,policy=policy)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            if verified:print('REFERENCE_RESULTS_OK')
        else:
            import psycopg
            from money_trail.publication import read_publication,published_snapshots
            with psycopg.connect(**config,autocommit=True) as connection:
                with connection.transaction():
                    connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                    snapshots=[row for row in published_snapshots(connection) if row['is_active']]
                    if not snapshots:raise ValueError('Aucune publication validee.')
                    result=[read_publication(connection,row['batch_id'],row['publication_id']) for row in snapshots]
            print(json.dumps({'status':'PUBLISHED_RESULTS_OK','results':result},default=str,ensure_ascii=False,indent=2))
        return 0
    except Exception as error:
        print(f'ECHEC du calcul ({type(error).__name__}). La publication precedente est conservee. '
              'Consulter les journaux dans reports/publication_runs et la sortie ci-dessus.',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
