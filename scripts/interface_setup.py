"""Créer un compte local sans mot de passe dans la commande ou les journaux."""
from pathlib import Path
import argparse
from getpass import getpass
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from money_trail.importer import local_config
from money_trail.local_auth import setup_accounts,create_user,username
from money_trail.workflow import WorkflowError


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--username',default='ilyass')
    p.add_argument('--role',choices=['admin','analyst','reviewer','viewer'],default='admin');a=p.parse_args()
    try:
        import psycopg
        name=username(a.username)
        with psycopg.connect(**local_config(),autocommit=True) as db:
            setup_accounts(db)
            if db.execute('SELECT user_id FROM app.local_users WHERE username=%s',(name,)).fetchone():
                print(f'COMPTE EXISTANT : {name}. Mot de passe et role conserves.');return 0
            password=getpass(f'Mot de passe du compte {name} (12 caracteres minimum) : ')
            if password!=getpass('Confirmer le mot de passe : '):raise WorkflowError('Les mots de passe ne correspondent pas.')
            if create_user(db,name,password,a.role):print(f'COMPTE CREE : {name} / {a.role}')
            else:print('Compte deja cree par une autre session ; compte conserve.')
        return 0
    except WorkflowError as error:print(str(error),file=sys.stderr);return 1
    except Exception as error:print(f'ECHEC comptes ({type(error).__name__}). Verifier la base du projet.',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
