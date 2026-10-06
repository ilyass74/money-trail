"""Publier un calcul validé sans exposer les tables d'un build en cours."""
from pathlib import Path
from datetime import timezone
from uuid import UUID,uuid4
import hashlib
import json
import re

from .investigation import (_rows,dossiers,serializable,payload_hash,
                            build_evidence_from_bytes)

ROOT=Path(__file__).resolve().parents[2]
PUBLICATION_LOCK=732084652


class PublicationError(ValueError):pass
class PublicationBusy(PublicationError):pass


def validate_prefix(value):
    if not isinstance(value,str) or not re.fullmatch(r'mtpub_[0-9a-f]{32}_',value):
        raise PublicationError('Espace de calcul candidat invalide.')
    return value


def validate_variables(variables):
    if not {'mt_schema_prefix','mt_batch_ids'} <= set(variables) or set(variables)-{'mt_schema_prefix','mt_batch_ids','mt_rule_policy'}:
        raise PublicationError('Parametres de publication invalides.')
    if 'mt_rule_policy' in variables:
        from .rules import validate_policy
        validate_policy(variables['mt_rule_policy'])
    validate_prefix(variables['mt_schema_prefix'])
    ids=variables['mt_batch_ids']
    if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)):
        raise PublicationError('Snapshots candidats absents ou dupliques.')
    for value in ids:
        if not isinstance(value,str) or str(UUID(value))!=value:
            raise PublicationError('Identifiant de snapshot invalide.')


def code_fingerprint():
    digest=hashlib.sha256()
    for folder in ('src','scripts','tests','fixtures','dbt','ui','sql'):
        for path in sorted((ROOT/folder).rglob('*')):
            if not path.is_file() or any(part in {'__pycache__','target','logs','dbt_packages'} for part in path.parts):
                continue
            digest.update(path.relative_to(ROOT).as_posix().encode()+b'\0')
            digest.update(path.read_bytes()+b'\0')
    return digest.hexdigest()


def publication_context(pub):
    result=serializable({key:pub[key] for key in ('publication_id','version','published_at','code_sha256')})
    result['published_at']=pub['published_at'].astimezone(timezone.utc).isoformat()
    return result


def setup_publications(connection):
    content=(ROOT/'sql/005_publications.sql').read_bytes()
    checksum=hashlib.sha256(content).hexdigest()
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(732084651::bigint)')
        row=connection.execute('SELECT sha256 FROM meta.schema_migrations WHERE version=%s',('005_publications',)).fetchone()
        if row:
            if row[0]!=checksum:raise PublicationError('Empreinte de la migration 005 differente.')
        else:
            connection.execute(content.decode('utf-8'))
            connection.execute('INSERT INTO meta.schema_migrations(version,sha256) VALUES (%s,%s)',('005_publications',checksum))

    from .operations import setup_operations
    setup_operations(connection)


def candidate_inputs(connection,batch_ids=None):
    """Une version source par périmètre ; les anciens snapshots restent archivés."""
    if batch_ids is None:
        rows=_rows(connection,"""SELECT DISTINCT ON (company_id,currency) *
          FROM meta.import_batches WHERE contract_version IN ('reference-v1','finance-v1')
          ORDER BY company_id,currency,ingested_at DESC,batch_id DESC""")
    else:
        ids=[str(UUID(str(value))) for value in batch_ids]
        if not ids or len(ids)!=len(set(ids)):raise PublicationError('Choisir des snapshots distincts.')
        rows=_rows(connection,"SELECT * FROM meta.import_batches WHERE batch_id=ANY(%s::uuid[]) ORDER BY batch_id",(ids,))
        if len(rows)!=len(ids):raise PublicationError('Snapshot candidat absent.')
    if not rows:raise PublicationError('Aucun import disponible pour publication.')
    scopes=[(row['company_id'],row['currency'],row['contract_version']) for row in rows]
    if len(scopes)!=len(set((company,currency) for company,currency,contract in scopes)):raise PublicationError('Choisir un seul snapshot par entreprise, devise et contrat.')
    if any((contract=='reference-v1' and (company,currency)!=('DEMO_MA','MAD')) or
           contract not in ('reference-v1','finance-v1') or
           (contract=='finance-v1' and (not company or currency not in ('MAD','EUR','USD','GBP')))
           for company,currency,contract in scopes):
        raise PublicationError('Perimetre non supporte par le moteur de demonstration.')
    return rows


def validate_build(run_bytes,manifest_bytes,prefix,batch_ids,policy=None):
    """Refuse les exécutions partielles et les preuves d'un autre candidat."""
    variables=dict(mt_schema_prefix=prefix,mt_batch_ids=batch_ids)
    if policy is not None:variables['mt_rule_policy']=policy
    validate_variables(variables)
    report=json.loads(run_bytes);manifest=json.loads(manifest_bytes)
    proof=build_evidence_from_bytes(run_bytes)
    invocation=proof['invocation_id']
    if not invocation or manifest.get('metadata',{}).get('invocation_id')!=invocation:
        raise PublicationError('Les artefacts ne proviennent pas de la meme execution.')
    observed=report.get('args',{}).get('vars',{})
    if isinstance(observed,str):observed=json.loads(observed)
    if observed!=variables:raise PublicationError('Les artefacts ne prouvent pas le perimetre candidat.')
    models={f'model.money_trail.{path.stem}':path for path in (ROOT/'dbt/models').rglob('*.sql')}
    nodes=manifest.get('nodes',{})
    manifest_models={key for key,node in nodes.items() if node.get('resource_type')=='model'}
    tests={key for key,node in nodes.items() if node.get('resource_type')=='test'}
    outcomes=report['results'];actual={row['unique_id'] for row in outcomes}
    if manifest_models!=set(models) or actual!=set(models)|tests or len(actual)!=len(outcomes) or len(tests)<21:
        raise PublicationError('Le build doit executer tous les modeles et controles dbt.')
    singular={Path(node.get('original_file_path','')).as_posix() for node in nodes.values() if node.get('resource_type')=='test'}
    if not {path.relative_to(ROOT/'dbt').as_posix() for path in (ROOT/'dbt/tests').glob('*.sql')}<=singular:
        raise PublicationError('Un controle metier dbt est absent du manifeste.')
    for key,path in models.items():
        schema=path.relative_to(ROOT/'dbt/models').parts[0]
        if nodes[key].get('schema')!=prefix+schema:
            raise PublicationError('Un modele candidat ecrit hors de son espace reserve.')
    proof.update(manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                 schema_prefix=prefix,input_batch_ids=batch_ids)
    return proof


def failed_checks(path):
    if not path.exists():return []
    try:
        return [{'unique_id':row['unique_id'],'status':row['status']} for row in json.loads(path.read_bytes()).get('results',[])
                if row.get('status') not in ('success','pass')]
    except (ValueError,KeyError,TypeError):return []


def cleanup_candidate(connection,prefix):
    from psycopg import sql
    validate_prefix(prefix)
    with connection.transaction():
        for schema in ('marts','core','staging'):
            connection.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(prefix+schema)))


def recover_interrupted(connection):
    """Appelé uniquement avec le verrou de publication détenu par cette session."""
    interrupted=_rows(connection,"SELECT run_id,schema_prefix FROM meta.publication_runs WHERE status='building'")
    connection.execute("""UPDATE meta.publication_runs SET status='failed',finished_at=clock_timestamp(),
      failure_phase='interrupted',error_code='InterruptedPublication' WHERE status='building'""")
    pending=_rows(connection,"SELECT run_id,schema_prefix FROM meta.publication_runs WHERE cleanup_status<>'complete' AND status<>'building'")
    for row in pending:
        try:cleanup_candidate(connection,row['schema_prefix']);state='complete'
        except Exception:state='failed'
        connection.execute('UPDATE meta.publication_runs SET cleanup_status=%s WHERE run_id=%s',(state,row['run_id']))
    return len(interrupted)


def run_publication(config,runner,actor='local-cli',batch_ids=None,artifact_parent=None,
                    validate_results=None,before_commit=None,policy=None):
    """runner construit réellement dbt ; hooks internes réservés aux vérifications."""
    import psycopg
    from psycopg.types.json import Jsonb
    from .rules import validate_policy
    if policy is not None:validate_policy(policy)
    if not isinstance(actor,str) or not actor.strip() or len(actor)>100:raise PublicationError('Acteur local invalide.')
    with psycopg.connect(**config,autocommit=True) as db:
        setup_publications(db)
        locked=db.execute('SELECT pg_try_advisory_lock(%s::bigint)',(PUBLICATION_LOCK,)).fetchone()[0]
        if not locked:raise PublicationBusy('Une publication est deja en cours. La version validee reste disponible.')
        run_id=None;prefix=None;phase='inputs';run_bytes=None;manifest_bytes=None;directory=None
        try:
            recover_interrupted(db)
            from .rules import register_policy
            effective_policy=policy or dict(version='v1',invoice_tolerance='0.00',settlement_tolerance='0.00')
            register_policy(db,effective_policy)
            inputs=candidate_inputs(db,batch_ids)
            run_id=uuid4();prefix='mtpub_'+run_id.hex+'_'
            ids=[str(row['batch_id']) for row in inputs];code_sha=code_fingerprint()
            db.execute("""INSERT INTO meta.publication_runs(run_id,status,actor,schema_prefix,input_batch_ids,code_sha256)
              VALUES (%s,'building',%s,%s,%s,%s)""",(run_id,actor.strip(),prefix,Jsonb(ids),code_sha))
            directory=Path(artifact_parent or ROOT/'reports/publication_runs')/str(run_id)
            directory.mkdir(parents=True,exist_ok=False)
            run_path=directory/'target/run_results.json';manifest_path=directory/'target/manifest.json'
            phase='dbt'
            variables=dict(mt_schema_prefix=prefix,mt_batch_ids=ids)
            if policy is not None:variables['mt_rule_policy']=policy
            success=runner(config,directory,variables)
            if run_path.exists():run_bytes=run_path.read_bytes()
            if manifest_path.exists():manifest_bytes=manifest_path.read_bytes()
            if not success:raise PublicationError('Le build candidat a echoue.')
            phase='evidence'
            if run_bytes is None or manifest_bytes is None:raise PublicationError('Artefacts du build absents.')
            proof=validate_build(run_bytes,manifest_bytes,prefix,ids,policy)
            if policy is not None:proof['rule_policy']=policy
            if code_sha!=code_fingerprint():raise PublicationError('Le code a change pendant le calcul.')
            proof['code_sha256']=code_sha
            frozen={}
            with db.transaction():
                db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                for row in inputs:
                    items=serializable(dossiers(db,row['batch_id'],proof,schema_prefix=prefix))
                    for item in items:
                        if any(item['snapshot'][key]!=serializable(row[key]) for key in
                               ('batch_id','fingerprint','company_id','currency','control_on','contract_version','ingested_at')):
                            raise PublicationError('Le snapshot source a change pendant le calcul.')
                    frozen[str(row['batch_id'])]=items
                if validate_results:validate_results(db,inputs,prefix)
            phase='commit'
            with db.transaction():
                pub=_rows(db,"""INSERT INTO app.result_publications(publication_id,code_sha256,build_evidence,snapshot_count,dossier_count)
                  VALUES (%s,%s,%s,%s,%s) RETURNING publication_id,version,published_at,code_sha256""",
                  (run_id,code_sha,Jsonb(proof),len(inputs),sum(len(items) for items in frozen.values())))[0]
                for row in inputs:
                    items=frozen[str(row['batch_id'])]
                    db.execute("""INSERT INTO app.published_snapshots
                      (publication_id,batch_id,company_id,currency,control_on,ingested_at,fingerprint,dossier_count)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                      (run_id,row['batch_id'],row['company_id'],row['currency'],row['control_on'],row['ingested_at'],row['fingerprint'],len(items)))
                    for item in items:
                        item['publication']=publication_context(pub)
                        db.execute("""INSERT INTO app.published_dossiers
                          (publication_id,batch_id,object_kind,object_id,rule_version,dossier,dossier_sha256)
                          VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                          (run_id,row['batch_id'],item['kind'],item['object_id'],item['result']['rule_version'],Jsonb(item),payload_hash(item)))
                db.execute("""INSERT INTO app.published_status_counts(publication_id,batch_id,object_kind,status,dossier_count)
                  SELECT publication_id,batch_id,object_kind,dossier->'result'->>'status',count(*) FROM app.published_dossiers
                  WHERE publication_id=%s GROUP BY 1,2,3,4""",(run_id,))
                db.execute("""UPDATE meta.publication_runs SET status='published',finished_at=clock_timestamp(),
                  run_results_bytes=%s,run_results_sha256=%s,manifest_bytes=%s,manifest_sha256=%s WHERE run_id=%s""",
                  (run_bytes,hashlib.sha256(run_bytes).hexdigest(),manifest_bytes,hashlib.sha256(manifest_bytes).hexdigest(),run_id))
                db.execute("""INSERT INTO app.publication_head(singleton,publication_id) VALUES (1,%s)
                  ON CONFLICT(singleton) DO UPDATE SET publication_id=excluded.publication_id""",(run_id,))
                from .operations import archive_comparisons,successors
                archive_comparisons(db,run_id)
                successors(db,run_id,actor.strip())
                if before_commit:before_commit(db,run_id)
            return {'status':'PUBLICATION_PUBLISHED',**serializable(pub),'snapshots':len(inputs),
                    'dossiers':sum(len(items) for items in frozen.values())}
        except Exception as error:
            if run_id:
                # Cette écriture survit au rollback de la transaction de publication.
                db.execute("""UPDATE meta.publication_runs SET status='failed',finished_at=clock_timestamp(),
                  failure_phase=%s,error_code=%s,failed_checks=%s,run_results_bytes=%s,run_results_sha256=%s,
                  manifest_bytes=%s,manifest_sha256=%s WHERE run_id=%s AND status='building'""",
                  (phase,type(error).__name__,Jsonb(failed_checks(directory/'target/run_results.json') if directory else []),
                   run_bytes,hashlib.sha256(run_bytes).hexdigest() if run_bytes else None,
                   manifest_bytes,hashlib.sha256(manifest_bytes).hexdigest() if manifest_bytes else None,run_id))
            raise
        finally:
            try:
                if prefix:
                    try:cleanup_candidate(db,prefix);state='complete'
                    except Exception:state='failed'
                    db.execute('UPDATE meta.publication_runs SET cleanup_status=%s WHERE run_id=%s',(state,run_id))
            finally:db.execute('SELECT pg_advisory_unlock(%s::bigint)',(PUBLICATION_LOCK,))


def published_snapshots(connection):
    return _rows(connection,"""SELECT s.*,p.version,p.published_at,
      (h.publication_id=p.publication_id) AS is_active
      FROM app.published_snapshots s JOIN app.result_publications p USING(publication_id)
      LEFT JOIN app.publication_head h ON h.singleton=1
      ORDER BY p.version DESC,s.company_id,s.control_on DESC,s.batch_id""")


def read_publication(connection,batch_id,publication_id=None,kind=None,object_id=None,limit=None):
    """Lit les dossiers archivés, indépendamment des sources et fichiers dbt courants."""
    batch_id=UUID(str(batch_id))
    if publication_id is None:
        rows=_rows(connection,"""SELECT p.* FROM app.result_publications p
          JOIN app.published_snapshots s USING(publication_id)
          WHERE s.batch_id=%s ORDER BY p.version DESC LIMIT 1""",(batch_id,))
    else:
        rows=_rows(connection,'SELECT * FROM app.result_publications WHERE publication_id=%s',(UUID(str(publication_id)),))
    if len(rows)!=1:raise PublicationError('Aucune publication validee disponible pour ce chargement. Lancer publication_demo.ps1.')
    pub=rows[0];publication_id=pub['publication_id']
    runs=_rows(connection,'SELECT * FROM meta.publication_runs WHERE run_id=%s',(publication_id,))
    if len(runs)!=1 or runs[0]['status']!='published':raise PublicationError('Journal de publication invalide.')
    run=runs[0];proof=pub['build_evidence']
    for label in ('run_results','manifest'):
        content=run[label+'_bytes']
        if content is None or hashlib.sha256(bytes(content)).hexdigest()!=run[label+'_sha256']:
            raise PublicationError('Integrite des artefacts archives non confirmee.')
    archived_proof=build_evidence_from_bytes(bytes(run['run_results_bytes']))
    if any(proof.get(key)!=value for key,value in archived_proof.items()):raise PublicationError('Preuve archivee incoherente.')
    if (proof.get('manifest_sha256')!=run['manifest_sha256'] or proof.get('code_sha256')!=pub['code_sha256']
            or run['code_sha256']!=pub['code_sha256']):raise PublicationError('Empreinte de publication incoherente.')
    snapshots=_rows(connection,'SELECT * FROM app.published_snapshots WHERE publication_id=%s AND batch_id=%s',(publication_id,batch_id))
    if len(snapshots)!=1:raise PublicationError('Ce chargement ne figure pas dans la publication choisie.')
    total=connection.execute('SELECT count(*) FROM app.published_dossiers WHERE publication_id=%s AND batch_id=%s',(publication_id,batch_id)).fetchone()[0]
    if total!=snapshots[0]['dossier_count']:raise PublicationError('Archive de dossiers incomplete.')
    conditions=['publication_id=%s','batch_id=%s'];params=[publication_id,batch_id]
    if kind:conditions.append('object_kind=%s');params.append(kind)
    if object_id:conditions.append('object_id=%s');params.append(object_id)
    query='SELECT * FROM app.published_dossiers WHERE '+' AND '.join(conditions)+' ORDER BY object_kind,object_id,rule_version'
    if limit is not None:
        if type(limit) is not int or not 1<=limit<=100:raise PublicationError('Limite de lecture invalide.')
        query+=' LIMIT %s';params.append(limit)
    records=_rows(connection,query,params)
    context=publication_context(pub)
    evidence=[]
    for row in records:
        item=row['dossier']
        if payload_hash(item)!=row['dossier_sha256'] or item.get('publication')!=context:
            raise PublicationError('Integrite du dossier archive non confirmee.')
        if (item['snapshot']['batch_id']!=str(batch_id) or item['snapshot']['fingerprint']!=snapshots[0]['fingerprint']
                or item['dbt_build_evidence']!=proof):raise PublicationError('Perimetre du dossier archive incoherent.')
        if (not kind or kind==item['kind']) and (not object_id or object_id==item['object_id']):evidence.append(item)
    if not evidence:raise PublicationError('Aucun dossier archive pour cet objet.')
    return {'publication':context,'dossiers':evidence,'build':proof}


def publication_health(connection,published_at):
    runs=_rows(connection,"""SELECT run_id,status,started_at,finished_at,failure_phase,error_code,failed_checks,cleanup_status
      FROM meta.publication_runs ORDER BY started_at DESC,run_id DESC LIMIT 1""")
    attempts=_rows(connection,"""SELECT attempt_id,dataset_label,status,started_at,finished_at,error_code
      FROM meta.import_attempts WHERE status='started' OR (status='failed' AND COALESCE(finished_at,started_at)>%s)
      ORDER BY started_at DESC LIMIT 100""",(published_at,))
    return dict(latest_run=runs[0] if runs else None,imports_since_publication=attempts)
