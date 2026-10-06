"""Connexion Odoo 18 en lecture seule. Diagnostic par défaut, extraction explicite."""
from pathlib import Path
import argparse
import getpass
import json
import sys
import urllib.request
from decimal import Decimal
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

class Odoo18Client:
    allowed = {'account.move', 'account.move.line', 'account.payment',
               'account.partial.reconcile', 'sale.order', 'sale.order.line', 'res.company'}
    def __init__(self, url, database, login, secret):
        parsed = urlparse(url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Adresse invalide')
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1')):
            raise ValueError('HTTPS requis hors localhost')
        self.url, self.database, self.secret = url.rstrip('/'), database, secret
        self.version = self.rpc('common', 'version', [])
        if self.version.get('server_version_info', [None])[0] != 18:
            raise ValueError('Ce connecteur cible Odoo 18')
        self.uid = self.rpc('common', 'authenticate', [database, login, secret, {}])
        if type(self.uid) is not int or self.uid <= 0:
            raise ValueError('Authentification refusee')

    def rpc(self, service, method, args):
        request = urllib.request.Request(self.url + '/jsonrpc', data=json.dumps({
            'jsonrpc': '2.0', 'method': 'call', 'id': 1,
            'params': {'service': service, 'method': method, 'args': args}
        }).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.load(response, parse_float=Decimal)
            if 'error' in result or 'result' not in result:
                raise ValueError('Appel refuse')
            return result['result']
        except Exception:
            raise ValueError('Odoo inaccessible ou appel refuse ; verifier adresse, base, identifiants et droits.') from None

    def call(self, model, method, values):
        if model not in self.allowed or method not in ('fields_get', 'search_read'):
            raise ValueError('Operation non autorisee')
        return self.rpc('object', 'execute_kw', [self.database, self.uid, self.secret, model, method, [], values])

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default='http://localhost:8069')
    p.add_argument('--database', default='ckrdb')
    p.add_argument('--extract', action='store_true')
    p.add_argument('--company-id', type=int)
    p.add_argument('--output', type=Path)
    p.add_argument('--import-bundles', action='store_true')
    args = p.parse_args()
    if args.extract and (not args.company_id or args.output is None):
        p.error('--extract exige --company-id et --output')
    if args.import_bundles and not args.extract:
        p.error('--import-bundles exige --extract')
    try:
        client = Odoo18Client(args.url, args.database, input('Identifiant Odoo : ').strip(), getpass.getpass('Mot de passe ou cle API Odoo (masque) : '))
        companies = client.call('res.company', 'search_read', {'domain': [], 'fields': ['id', 'name'], 'limit': 100})
        print(json.dumps({'status': 'CONNEXION_OK', 'version': client.version['server_version'], 'database': args.database, 'companies': companies}, ensure_ascii=False, indent=2))
        if not args.extract:
            return 0
        from money_trail.odoo_source import run_extraction
        from money_trail.odoo_bundle import create_bundles
        from money_trail.importer import setup_database, local_config, import_directory
        from money_trail.publication import setup_publications
        from money_trail.investigation import payload_hash
        import psycopg
        from uuid import UUID
        if args.output.exists():
            raise ValueError('Choisir un dossier de sortie neuf')
        with psycopg.connect(**local_config(), autocommit=True) as db:
            setup_database(db)
            setup_publications(db)
            class ExtractionConnection:
                def execute(self, query, params=None):
                    if query.startswith('INSERT INTO meta.source_extractions'):
                        query = query.replace("'odoo-json2'", "'odoo18-jsonrpc'")
                    return db.execute(query, params)
                def transaction(self):
                    return db.transaction()
            result = run_extraction(ExtractionConnection(), client, args.company_id, include_sales=False)
            row = db.execute('SELECT payload,payload_sha256 FROM meta.source_extractions WHERE extraction_id=%s', (UUID(result['extraction_id']),)).fetchone()
            if payload_hash(row[0]) != row[1]:
                raise ValueError('Empreinte extraction invalide')
            paths = create_bundles({**row[0], 'extraction_id': result['extraction_id']}, args.output)
            imports = [import_directory(db, path) for path in paths] if args.import_bundles else []
        print(json.dumps({'extraction': result, 'directories': list(map(str, paths)), 'imports': imports}, default=str, indent=2))
        return 0
    except Exception as error:
        if type(error).__name__ == "ExtractionError":
            print("DETAIL :", str(error), file=sys.stderr)
        # Never emit server responses or credentials.
        print('CONNEXION_OU_EXTRACTION_REFUSEE (' + type(error).__name__ + '). Verifier les identifiants, droits et champs Odoo. Aucun detail secret affiche.', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
