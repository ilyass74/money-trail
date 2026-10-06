"""Consulter ou exporter les preuves des résultats Money Trail, sans écrire en base."""
from pathlib import Path
from uuid import UUID
from datetime import datetime,timezone
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from money_trail.importer import local_config,prepare_bundle
from money_trail.investigation import serializable,markdown_dossier
from money_trail.publication import read_publication


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind',choices=['all','invoice','settlement'])
    parser.add_argument('object_id',nargs='?')
    parser.add_argument('--batch-id',type=UUID)
    parser.add_argument('--publication-id',type=UUID)
    parser.add_argument('--export',action='store_true')
    args=parser.parse_args()
    if args.kind!='all' and not args.object_id:parser.error('Indiquer un identifiant, par exemple FAC001 ou LOT001.')
    if args.kind=='all' and args.object_id:parser.error('Ne pas indiquer d identifiant avec all.')
    try:
        import psycopg
        with psycopg.connect(**local_config(),autocommit=True) as connection:
            with connection.transaction():
                connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                if args.batch_id:batch_id=args.batch_id
                else:
                    fingerprint=prepare_bundle(ROOT/'data/reference_v1').fingerprint
                    row=connection.execute('SELECT batch_id FROM meta.import_batches WHERE fingerprint=%s',(fingerprint,)).fetchone()
                    if not row:raise ValueError('Jeu de reference non importe.')
                    batch_id=row[0]
                result=read_publication(connection,batch_id,args.publication_id,None if args.kind=='all' else args.kind,args.object_id)['dossiers']
        if args.export:
            directory=ROOT/'reports'/('investigation_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
            directory.mkdir(parents=True,exist_ok=False)
            # Sequential filenames avoid source identifiers becoming filesystem paths.
            for index,item in enumerate(result,1):
                prefix=f'{index:03d}_{item["kind"]}'
                (directory/f'{prefix}.json').write_text(json.dumps(serializable(item),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                (directory/f'{prefix}.md').write_text(markdown_dossier(item),encoding='utf-8')
            print(json.dumps({'status':'INVESTIGATION_EXPORTED','dossiers':len(result),'directory':str(directory)},indent=2))
        else:
            for item in result:print(markdown_dossier(item))
            print('INVESTIGATION_OK')
        return 0
    except Exception as error:
        print(f'ECHEC investigation ({type(error).__name__}). Verifier le build dbt, le snapshot et l identifiant. Aucun changement en base.',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
