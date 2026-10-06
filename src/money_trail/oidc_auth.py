"""Relier une identité validée par Streamlit à un compte explicitement autorisé."""
import hashlib
import secrets
from .workflow import WorkflowError


def trusted_identity_session(db,issuer,subject):
    if not isinstance(issuer,str) or not issuer.startswith('https://') or not isinstance(subject,str) or not subject:
        raise WorkflowError('Identite OIDC incomplete.')
    row=db.execute('''SELECT u.user_id FROM app.external_identities i JOIN app.local_users u USING(user_id)
      WHERE i.issuer=%s AND i.subject=%s AND u.active''',(issuer,subject)).fetchone()
    if not row:raise WorkflowError('Cette identite ne possede aucun compte autorise.')
    token=secrets.token_hex(32)
    db.execute("INSERT INTO app.local_sessions(token_hash,user_id,expires_at) VALUES(%s,%s,CURRENT_TIMESTAMP+INTERVAL '4 hours')",
               (hashlib.sha256(token.encode()).hexdigest(),row[0]))
    return token
