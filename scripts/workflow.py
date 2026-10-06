"""Suivi local des investigations. Les noms d'acteurs sont déclaratifs, sans authentification."""
from pathlib import Path
from uuid import UUID
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from money_trail.importer import local_config,prepare_bundle
from money_trail.investigation import serializable
from money_trail.publication import read_publication
from money_trail.workflow import setup_workflow,sync_cases,list_cases,resolve_case,show_case,act,WorkflowError


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['setup','sync','list','show','start','comment','propose','approve','reject','close'])
    p.add_argument('--actor');p.add_argument('--case-id',type=UUID);p.add_argument('--batch-id',type=UUID)
    p.add_argument('--publication-id',type=UUID)
    p.add_argument('--kind',choices=['invoice','settlement'],default='settlement');p.add_argument('--object')
    p.add_argument('--note');p.add_argument('--type',dest='proposal_type')
    p.add_argument('--description');p.add_argument('--justification');p.add_argument('--record-id',type=int,action='append',default=[])
    p.add_argument('--revision',type=int)
    args=p.parse_args()
    try:
        import psycopg
        with psycopg.connect(**local_config(),autocommit=True) as connection:
            if args.action=='setup':
                setup_workflow(connection);result={'status':'WORKFLOW_SCHEMA_READY'}
            else:
                batch_id=args.batch_id
                if not batch_id and not args.case_id:
                    fingerprint=prepare_bundle(ROOT/'data/reference_v1').fingerprint
                    row=connection.execute('SELECT batch_id FROM meta.import_batches WHERE fingerprint=%s',(fingerprint,)).fetchone()
                    if not row:raise WorkflowError('Jeu de reference non importe.')
                    batch_id=row[0]
                if args.action=='sync':
                    if not batch_id:raise WorkflowError('Indiquer --batch-id pour synchroniser.')
                    with connection.transaction():
                        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                        evidence=read_publication(connection,batch_id,args.publication_id)['dossiers']
                    result=sync_cases(connection,evidence,args.actor)
                elif args.action=='list':
                    if not batch_id:raise WorkflowError('Indiquer --batch-id pour lister.')
                    result={'cases':list_cases(connection,batch_id)}
                else:
                    case_id=args.case_id
                    if not case_id:
                        if not args.object:raise WorkflowError('Indiquer --object ou --case-id.')
                        case_id=resolve_case(connection,batch_id,args.kind,args.object)
                    if args.action=='show':
                        with connection.transaction():
                            connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                            result=show_case(connection,case_id)
                    else:
                        result=act(connection,case_id,args.action,args.actor,args.note,args.proposal_type,
                                   args.description,args.justification,args.record_id,args.revision)
        print(json.dumps(serializable(result),ensure_ascii=False,indent=2));return 0
    except WorkflowError as error:
        print('WORKFLOW_REFUSE: '+str(error),file=sys.stderr);return 1
    except Exception as error:
        print(f'ECHEC workflow ({type(error).__name__}). Verifier la migration et le build dbt.',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
