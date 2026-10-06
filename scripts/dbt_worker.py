"""Un processus par appel dbt : les fichiers sont fermés à sa terminaison."""
import sys


def main():
    try:
        from dbt.cli.main import dbtRunner
        result=dbtRunner().invoke(sys.argv[1:])
        return 0 if result.success else 1
    except Exception as error:
        print(f'ECHEC du processus dbt ({type(error).__name__}).',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
