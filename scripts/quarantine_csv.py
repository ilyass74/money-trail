from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from money_trail.importer import local_config,setup_database,import_directory
from money_trail.publication import setup_publications
from money_trail.quarantine import quarantine_directory
p=argparse.ArgumentParser(description='Conserver les rejets CSV sans masquer la couverture incomplete.')
p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
p.add_argument('--import-bundle',action='store_true');args=p.parse_args()
import psycopg
try:
 with psycopg.connect(**local_config(),autocommit=True) as db:
  setup_database(db);setup_publications(db)
  result=quarantine_directory(db,args.source,args.output)
  if args.import_bundle:result['import']=import_directory(db,args.output)
 print(json.dumps(result,indent=2))
except Exception as error:
 print('QUARANTAINE_REFUSEE: '+type(error).__name__,file=sys.stderr);raise SystemExit(1)
