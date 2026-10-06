"""Extraire Odoo, exporter les périmètres et importer sans modifier Odoo."""
from pathlib import Path
from uuid import UUID
import argparse
import os
import sys
import json

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from money_trail.importer import setup_database,local_config,import_directory
from money_trail.publication import setup_publications
from money_trail.odoo_source import OdooClient,run_extraction
from money_trail.odoo_bundle import create_bundles
from money_trail.investigation import payload_hash


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--company-id',type=int,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--accounting-only',action='store_true',help='Ne pas extraire les commandes de vente.')
    p.add_argument('--import-bundles',action='store_true')
    args=p.parse_args()
    import psycopg
    try:
        client=OdooClient(os.environ.get('ODOO_URL',''),os.environ.get('ODOO_API_KEY',''),os.environ.get('ODOO_DATABASE'))
        with psycopg.connect(**local_config(),autocommit=True) as db:
            setup_database(db);setup_publications(db)
            result=run_extraction(db,client,args.company_id,include_sales=not args.accounting_only)
            row=db.execute('SELECT payload,payload_sha256 FROM meta.source_extractions WHERE extraction_id=%s',(UUID(result['extraction_id']),)).fetchone()
            if payload_hash(row[0])!=row[1]:raise ValueError('Extraction corrompue.')
            payload={**row[0],'extraction_id':result['extraction_id']}
            paths=create_bundles(payload,args.output)
            imports=[import_directory(db,path) for path in paths] if args.import_bundles else []
        print(json.dumps({'extraction':result,'directories':[str(path) for path in paths],'imports':imports},indent=2));return 0
    except Exception as error:
        print('EXTRACTION_REFUSEE: '+type(error).__name__+'. La derniere publication reste disponible.',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
