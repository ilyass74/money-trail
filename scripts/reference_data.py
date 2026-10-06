"""Commandes du jeu synthétique : create ou check. Bibliothèque standard seule."""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from money_trail.reference import create_reference, check_reference


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['create', 'check'])
    parser.add_argument('--directory', type=Path, default=ROOT / 'data' / 'reference_v1')
    args = parser.parse_args()
    try:
        if args.action == 'create':
            create_reference(args.directory)
        print(json.dumps(check_reference(args.directory), indent=2, ensure_ascii=False))
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        print(f'ECHEC : {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
