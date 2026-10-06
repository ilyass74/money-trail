"""Politiques de tolérance explicites : aucune conversion de devise implicite."""
from decimal import Decimal
import re


def validate_policy(policy):
    if not isinstance(policy,dict) or set(policy)!={'version','invoice_tolerance','settlement_tolerance'}:
        raise ValueError('Politique de regle invalide.')
    if policy['version'] not in ('v1','v2'):raise ValueError('Version de regle inconnue.')
    for key in ('invoice_tolerance','settlement_tolerance'):
        value=policy[key]
        if not isinstance(value,str) or not re.fullmatch(r'\d{1,3}\.\d{2}',value) or Decimal(value)>100:
            raise ValueError('Tolerance attendue entre 0.00 et 100.00, en devise du dossier.')
        if policy['version']=='v1' and Decimal(value)!=0:raise ValueError('La regle v1 conserve une tolerance nulle.')
    return policy


def register_policy(db,policy):
    from psycopg.types.json import Jsonb
    policy=validate_policy(policy)
    with db.transaction():
        db.execute('SELECT pg_advisory_xact_lock(732084653::bigint)')
        db.execute('INSERT INTO meta.rule_policies(version,policy) VALUES(%s,%s) ON CONFLICT DO NOTHING',(policy['version'],Jsonb(policy)))
        stored=db.execute('SELECT policy FROM meta.rule_policies WHERE version=%s',(policy['version'],)).fetchone()[0]
        if stored!=policy:raise ValueError('Cette version de regle est deja enregistree avec une autre tolerance.')
