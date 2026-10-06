"""Installer les tables, importer le contrat de référence ou inspecter le résultat."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / 'src'))
from money_trail.importer import local_config,setup_database,import_directory,inspect_database


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['setup','import','inspect'])
    parser.add_argument('--directory',type=Path,default=ROOT / 'data' / 'reference_v1')
    args=parser.parse_args()
    try:
        import psycopg
    except ImportError:
        print('Installer requirements-import.txt avec le Python du projet.',file=sys.stderr)
        return 1
    try:
        with psycopg.connect(**local_config(),autocommit=True) as connection:
            if args.action=='setup':
                setup_database(connection)
                result={'status':'SCHEMA_READY','migration':'002_import'}
            elif args.action=='import':
                result=import_directory(connection,args.directory)
            else:
                result=inspect_database(connection)
        print(json.dumps(result,indent=2,ensure_ascii=False))
    except Exception as error:
        # Message bref sans divulguer le mot de passe, les octets bruts ou le DSN.
        print(f'ECHEC ({type(error).__name__}). Verifier .env, PostgreSQL et le manifeste ; '
              'voir meta.import_attempts si une tentative a pu etre demarree.',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
