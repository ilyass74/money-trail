"""Bases temporaires appartenant au test, sans suppression de base métier."""
from uuid import uuid4
import hashlib
import json
import re
import psycopg
from psycopg import sql
from money_trail.importer import local_config


class TemporaryDatabase:
    def __init__(self, prefix='moneytrail_acceptance_', config=None):
        if not re.fullmatch(r'moneytrail_[a-z_]+_',prefix):
            raise ValueError('Prefixe de base temporaire invalide.')
        original=config or local_config()
        self.name=prefix+uuid4().hex
        self.config={**original,'dbname':self.name}
        self.admin=psycopg.connect(**original,autocommit=True)
        self.db=None;self.created=False
        try:
            self.admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(self.name)))
            self.created=True
            self.db=psycopg.connect(**self.config,autocommit=True)
        except Exception:
            self.close();raise

    def close(self):
        if self.db is not None and not self.db.closed:self.db.close()
        try:
            if self.created:
                self.admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(self.name)))
                self.created=False
        finally:
            self.admin.close()

    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def table_fingerprints(connection):
    """Empreintes seulement, sans exposer les données ou les mots de passe."""
    tables=connection.execute("""SELECT n.nspname,c.relname FROM pg_class c
      JOIN pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname IN ('meta','raw','marts','app') AND c.relkind='r'
      ORDER BY 1,2""").fetchall()
    output={}
    for schema,name in tables:
        query=sql.SQL('SELECT row_to_json(t)::text FROM {}.{} t ORDER BY row_to_json(t)::text').format(sql.Identifier(schema),sql.Identifier(name))
        digest=hashlib.sha256();count=0
        for row in connection.execute(query):
            digest.update(row[0].encode('utf-8')+b'\n');count+=1
        output[schema+'.'+name]={'rows':count,'sha256':digest.hexdigest()}
    sequences=connection.execute("""SELECT schemaname,sequencename,last_value FROM pg_sequences
      WHERE schemaname IN ('meta','raw','marts','app') ORDER BY 1,2""").fetchall()
    output['sequences_sha256']=hashlib.sha256(json.dumps(sequences,default=str).encode()).hexdigest()
    return output
