"""Créer les rôles DB de démonstration et lier explicitement une identité OIDC."""
from pathlib import Path
import argparse,os,secrets,sys,json,re
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from money_trail.importer import local_config,setup_database
from money_trail.publication import setup_publications
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--roles',action='store_true')
p.add_argument('--username');p.add_argument('--issuer');p.add_argument('--subject');args=p.parse_args()
import psycopg
from psycopg import sql
with psycopg.connect(**local_config(),autocommit=True) as db:
 setup_database(db);setup_publications(db)
 if args.roles:
  for role,suffix in [('mt_ui','ui'),('mt_pipeline','pipeline')]:
   path=ROOT/'deploy'/('.env.'+suffix)
   present=db.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone()
   if present and not path.exists():raise SystemExit('Role existant sans fichier de configuration : restaurer son secret.')
   if not present:
    password=secrets.token_hex(32)
    db.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
    path.write_text('MT_DB_USER='+role+'\nMT_DB_PASSWORD='+password+'\nMT_DB_NAME='+local_config()['dbname']+'\n')
    os.chmod(path,0o600)
   db.execute(sql.SQL('GRANT USAGE ON SCHEMA app,meta,raw TO {}').format(sql.Identifier(role)))
   db.execute(sql.SQL('GRANT SELECT ON ALL TABLES IN SCHEMA app,meta,raw TO {}').format(sql.Identifier(role)))
   db.execute(sql.SQL('REVOKE SELECT ON app.local_users FROM {}').format(sql.Identifier(role)))
   db.execute(sql.SQL('GRANT SELECT(user_id,username,role,active,created_at) ON app.local_users TO {}').format(sql.Identifier(role)))
   db.execute(sql.SQL('GRANT USAGE ON ALL SEQUENCES IN SCHEMA app,meta,raw TO {}').format(sql.Identifier(role)))
  db.execute('GRANT INSERT ON app.local_sessions,app.investigation_cases,app.case_events,app.correction_proposals,app.external_action_evidence,app.case_resolutions TO mt_ui')
  db.execute('GRANT DELETE ON app.local_sessions TO mt_ui')
  db.execute('GRANT UPDATE(workflow_status,revision,updated_at,assigned_to) ON app.investigation_cases TO mt_ui')
  db.execute('GRANT UPDATE(decision,decided_by,decision_note,decided_at) ON app.correction_proposals TO mt_ui')
  db.execute(sql.SQL('GRANT CREATE ON DATABASE {} TO mt_pipeline').format(sql.Identifier(local_config()['dbname'])))
  db.execute('GRANT INSERT ON meta.import_batches,meta.import_files,meta.import_attempts,meta.publication_runs,meta.rule_policies,meta.source_extractions,meta.quarantined_rows,raw.source_records TO mt_pipeline')
  db.execute('GRANT UPDATE ON meta.import_attempts,meta.publication_runs,meta.source_extractions TO mt_pipeline')
  db.execute('GRANT INSERT ON app.result_publications,app.published_snapshots,app.published_dossiers,app.publication_head,app.investigation_cases,app.case_events,app.case_successions,app.rule_comparisons,app.published_status_counts TO mt_pipeline')
  db.execute('GRANT UPDATE ON app.publication_head TO mt_pipeline')
  env=ROOT/'.env';content=env.read_text()
  if not re.search(r'^AIRFLOW_META_PASSWORD=',content,re.M):env.write_text(content.rstrip()+'\nAIRFLOW_META_PASSWORD='+secrets.token_hex(32)+'\n')
  print('DEPLOY_ROLES_CONFIGURED')
 if args.username or args.issuer or args.subject:
  if not all((args.username,args.issuer,args.subject)) or not args.issuer.startswith('https://'):raise SystemExit('username, issuer HTTPS et subject requis ensemble.')
  user=db.execute('SELECT user_id FROM app.local_users WHERE username=%s AND active',(args.username,)).fetchone()
  if not user:raise SystemExit('Compte actif absent : le creer avec interface_setup.py.')
  old=db.execute('SELECT user_id FROM app.external_identities WHERE issuer=%s AND subject=%s',(args.issuer,args.subject)).fetchone()
  if old and old[0]!=user[0]:raise SystemExit('Identite deja liee a un autre compte : modification refusee.')
  db.execute('INSERT INTO app.external_identities(issuer,subject,user_id) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(args.issuer,args.subject,user[0]))
  print('OIDC_IDENTITY_LINKED')
