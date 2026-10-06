"""Échoue avant le démarrage cloud si les secrets OIDC sont des modèles."""
from pathlib import Path
import os,sys,tomllib
if os.environ.get('MT_AUTH_MODE')!='oidc':raise SystemExit('Le profil cloud exige OIDC.')
path=Path('/app/.streamlit/secrets.toml')
if not path.is_file():raise SystemExit('Configuration OIDC absente.')
auth=tomllib.loads(path.read_text())['auth']
for key in ('redirect_uri','cookie_secret','client_id','client_secret','server_metadata_url'):
 value=auth.get(key,'')
 if not value or 'YOUR_' in value or 'GENERATE_' in value:raise SystemExit('Configuration OIDC a completer.')
if not auth['redirect_uri'].startswith('https://') or not auth['server_metadata_url'].startswith('https://'):
 raise SystemExit('HTTPS requis pour OIDC.')
if len(auth['cookie_secret'])<32:raise SystemExit('Secret cookie trop court.')
os.execv(sys.executable,[sys.executable,'-m','streamlit','run','ui/app.py','--server.address=0.0.0.0','--server.port=8501'])
