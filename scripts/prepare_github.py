"""Prepare a separate, inspectable Git tree from the current local project."""
from pathlib import Path
from datetime import datetime
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT.parent / ('money-trail-github-' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
ROOT_FILES = ['README.md', 'CONTRIBUTING.md', 'SECURITY.md', '.gitignore', '.gitattributes', '.dockerignore', '.env.example', 'compose.yaml', 'compose.airflow.yaml', 'compose.cloud.yaml']
DIRS = ['src', 'ui', 'sql', 'dbt', 'scripts', 'tests', 'fixtures', 'docs', 'airflow', 'deploy', 'data/reference_v1']
EXTENSIONS = {'.py', '.ps1', '.sql', '.yaml', '.yml', '.toml', '.txt', '.md', '.json', '.csv', '.css', '.html', '.example'}
EXCLUDED_DIRS = {'__pycache__', 'target', 'logs', 'dbt_packages', '.venv', 'node_modules', 'qa', 'screenshots', 'backups', 'reports', '.git', '.pytest_cache'}
SENSITIVE = re.compile(r'(-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16})')
# Flag literal credential assignments for manual inspection; never display their values.
ASSIGNMENT = re.compile(r'''(?im)^\s*(?:["']?)(?:password|passwd|api_key|api_token|access_token|client_secret|db_password|odoo_password)(?:["']?)\s*[:=]\s*["']([^"'\n]{8,})["']''')


def main():
    required = ['src/money_trail/odoo_source.py', 'src/money_trail/odoo_bundle.py', 'scripts/odoo18_connect.py', 'ui/app.py']
    missing = [p for p in required if not (ROOT / p).is_file()]
    if missing:
        raise SystemExit('Publication stopped: required current files missing: ' + ', '.join(missing))
    if not shutil.which('git'):
        raise SystemExit('Install Git for Windows, then run again.')
    paths = {ROOT / p for p in ROOT_FILES if (ROOT / p).is_file()}
    paths.update(ROOT.glob('requirements*.txt'))
    for folder in DIRS:
        for p in (ROOT / folder).rglob('*'):
            rel = p.relative_to(ROOT)
            if not p.is_file() or p.is_symlink() or any(x in EXCLUDED_DIRS for x in rel.parts):
                continue
            if '.bak' in p.name or p.name.startswith('.env') or p.name == 'secrets.toml':
                continue
            if p.suffix in EXTENSIONS or p.name.startswith('Dockerfile') or p.name == 'Caddyfile':
                paths.add(p)
    flagged = []
    for p in sorted(paths):
        content = p.read_text(encoding='utf-8-sig')
        if SENSITIVE.search(content):
            flagged.append(str(p.relative_to(ROOT)))
        # Test fixtures deliberately contain synthetic credentials. Do not scan
        # their assignment forms as if they were runtime configuration.
        if p.relative_to(ROOT).parts[0] not in {'tests', 'fixtures'} and not p.name.startswith('test_') and p.name != 'prepare_github.py':
            for match in ASSIGNMENT.finditer(content):
                value = match.group(1)
                if not any(x in value.lower() for x in ['example', 'placeholder', 'change', 'your_', 'demo', 'test', 'fixture', '${', '{{']):
                    flagged.append(str(p.relative_to(ROOT)))
    if flagged:
        raise SystemExit('Inspect possible credentials in these files before publishing (values withheld): ' + ', '.join(sorted(set(flagged))))
    TARGET.mkdir()
    for p in sorted(paths):
        out = TARGET / p.relative_to(ROOT)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, out)
    subprocess.run(['git', 'init', '-b', 'main'], cwd=TARGET, check=True)
    subprocess.run(['git', 'add', '--all'], cwd=TARGET, check=True)
    print('\nREADY FOR REVIEW: ' + str(TARGET))
    print('Original working project unchanged. No commit or push performed.')
    print('Review: git diff --cached --stat ; git diff --cached')
    print('Credential scanning is heuristic: manually review the staged content.')

if __name__ == '__main__':
    main()
