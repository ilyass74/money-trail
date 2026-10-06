"""Comptes locaux de l'interface. Les scripts CLI historiques restent déclaratifs."""
from pathlib import Path
from uuid import uuid4
import hashlib
import hmac
import re
import secrets
from .workflow import WorkflowError,act

ROOT=Path(__file__).resolve().parents[2]
ITERATIONS=600_000
PERMISSIONS={'viewer':set(),'analyst':{'start','comment','propose','close','assign'},
             'reviewer':{'comment','assign','approve','reject','record_execution','resolve','accept_gap'},
             'admin':{'start','comment','propose','close','sync','assign'}}


def username(value):
    name=(value or '').strip().lower()
    if not re.fullmatch(r'[a-z0-9_.-]{3,40}',name):raise WorkflowError('Identifiant : 3 a 40 lettres minuscules, chiffres, point, tiret ou underscore.')
    return name


def hash_password(password):
    if len(password)<12:raise WorkflowError('Choisir un mot de passe d au moins 12 caracteres.')
    salt=secrets.token_bytes(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),salt,ITERATIONS)
    return f'pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}'


def verify_password(password,encoded):
    try:
        method,iterations,salt,stored=encoded.split('$')
        if method!='pbkdf2_sha256' or not (100_000<=int(iterations)<=2_000_000):return False
        calculated=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),bytes.fromhex(salt),int(iterations))
        return hmac.compare_digest(calculated.hex(),stored)
    except (ValueError,TypeError):return False


def setup_accounts(connection):
    content=(ROOT/'sql/004_local_accounts.sql').read_bytes();digest=hashlib.sha256(content).hexdigest()
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(732084651::bigint)')
        row=connection.execute('SELECT sha256 FROM meta.schema_migrations WHERE version=%s',('004_local_accounts',)).fetchone()
        if row:
            if row[0]!=digest:raise WorkflowError('Empreinte de la migration 004 differente.')
        else:
            connection.execute(content.decode('utf-8'))
            connection.execute('INSERT INTO meta.schema_migrations(version,sha256) VALUES (%s,%s)',('004_local_accounts',digest))


def create_user(connection,name,password,role):
    name=username(name)
    if role not in PERMISSIONS:raise WorkflowError('Role inconnu.')
    encoded=hash_password(password)
    return connection.execute('''INSERT INTO app.local_users(user_id,username,password_hash,role)
      VALUES (%s,%s,%s,%s) ON CONFLICT(username) DO NOTHING RETURNING user_id''',
      (uuid4(),name,encoded,role)).fetchone() is not None


def login(connection,name,password):
    from psycopg.rows import dict_row
    try:name=username(name)
    except WorkflowError:return None
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute('SELECT * FROM app.local_users WHERE username=%s AND active',(name,));user=cursor.fetchone()
    if not user or not verify_password(password,user['password_hash']):return None
    token=secrets.token_hex(32)
    connection.execute('''INSERT INTO app.local_sessions(token_hash,user_id,expires_at)
      VALUES (%s,%s,CURRENT_TIMESTAMP + INTERVAL '4 hours')''',
      (hashlib.sha256(token.encode()).hexdigest(),user['user_id']))
    return token


def active_user(connection,token):
    from psycopg.rows import dict_row
    if not token:return None
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute('''SELECT u.user_id,u.username,u.role FROM app.local_sessions s
          JOIN app.local_users u ON u.user_id=s.user_id
          WHERE s.token_hash=%s AND s.expires_at>CURRENT_TIMESTAMP AND u.active''',
          (hashlib.sha256(token.encode()).hexdigest(),))
        return cursor.fetchone()


def authorize(role,action):
    if action not in PERMISSIONS.get(role,set()):raise WorkflowError('Votre role ne permet pas cette action.')


def logout(connection,token):
    connection.execute('DELETE FROM app.local_sessions WHERE token_hash=%s',(hashlib.sha256(token.encode()).hexdigest(),))


def authenticated_action(connection,token,case_id,action,**kwargs):
    with connection.transaction():
        user=active_user(connection,token)
        if not user:raise WorkflowError('Session expiree. Reconnectez-vous.')
        authorize(user['role'],action)
        return act(connection,case_id,action,user['username'],**kwargs)
