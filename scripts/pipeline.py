"""Un seul lot : import contrôlé, publication, puis preuve de réussite."""
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
import argparse,json,os,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from money_trail.importer import local_config,setup_database,import_directory
from money_trail.publication import setup_publications,run_publication
from run_dbt import invoke_dbt
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,default=ROOT/'data/reference_v1');args=p.parse_args()
try:
 import psycopg
 config=local_config()
 with psycopg.connect(**config,autocommit=True) as db:
  setup_database(db);setup_publications(db)
  manifest=json.loads((args.source/'manifest.json').read_bytes())
  if not manifest.get('synthetic'):
   from money_trail.odoo_source import freshness
   stamp=manifest.get('source_as_of')
   as_of=datetime.fromisoformat(stamp.replace('Z','+00:00')) if stamp else None
   if freshness(as_of,datetime.now(timezone.utc))!='fraiche':raise ValueError('Source inconnue ou perimee : ne pas publier.')
  imported=import_directory(db,args.source)
 result=run_publication(config,lambda cfg,path,variables:invoke_dbt('build',cfg,path,variables),batch_ids=[imported['batch_id']],actor='daily-pipeline')
 print(json.dumps({'import':imported,'publication':result},indent=2))
except Exception as error:
 print('PIPELINE_FAILED: '+type(error).__name__+'. Publication precedente conservee.',file=sys.stderr);raise SystemExit(1)
