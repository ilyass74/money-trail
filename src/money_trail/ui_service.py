"""Accès aux données de l'interface : une vue cohérente, un snapshot explicite."""
from contextlib import contextmanager
from pathlib import Path
from .importer import local_config
from .investigation import _rows
from .publication import published_snapshots,read_publication,publication_health
from .workflow import list_cases,show_case,sync_cases,WorkflowError
from .local_auth import login,logout,active_user,authenticated_action,authorize

ROOT=Path(__file__).resolve().parents[2]


@contextmanager
def connect():
    import psycopg
    with psycopg.connect(**local_config(),autocommit=True) as connection:yield connection


def sign_in(name,password):
    with connect() as db:return login(db,name,password)


def session_user(token):
    with connect() as db:return active_user(db,token)


def sign_out(token):
    with connect() as db:logout(db,token)


def snapshots(token):
    with connect() as db:
        if not active_user(db,token):raise WorkflowError('Session expiree.')
        return published_snapshots(db)


def load_snapshot(token,batch_id,publication_id=None,page=None):
    with connect() as db:
        with db.transaction():
            db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            if not active_user(db,token):raise WorkflowError('Session expiree.')
            if page is None:archive=read_publication(db,batch_id,publication_id)
            else:
                from .paging import page_records
                archive=page_records(db,batch_id,publication_id,**page)
            evidence=archive['dossiers'];proof=archive['build']
            health=publication_health(db,archive['publication']['published_at'])
            if page is None:cases=list_cases(db,batch_id)
            else:
                keys=[(d['kind'],d['object_id'],d['result']['rule_version']) for d in evidence]
                cases=_rows(db,'''SELECT case_id,object_kind,object_id,rule_version,business_status,workflow_status,revision,created_by
                    FROM app.investigation_cases WHERE import_batch_id=%s AND (object_kind,object_id,rule_version) IN
                    (SELECT * FROM unnest(%s::text[],%s::text[],%s::text[])) ORDER BY object_kind,object_id''',
                    (batch_id,[k[0] for k in keys],[k[1] for k in keys],[k[2] for k in keys]))
            active_cases=db.execute("""SELECT count(*) FROM app.investigation_cases c JOIN app.published_dossiers d
                ON d.batch_id=c.import_batch_id AND d.object_kind=c.object_kind AND d.object_id=c.object_id AND d.rule_version=c.rule_version
                WHERE d.batch_id=%s AND d.publication_id=%s AND c.workflow_status NOT IN ('closed','resolved','accepted_with_justification')""",
                (batch_id,archive['publication']['publication_id'])).fetchone()[0]
            comparisons=_rows(db,'SELECT * FROM app.rule_comparisons WHERE new_publication_id=%s AND batch_id=%s ORDER BY object_kind,object_id LIMIT 100',(archive['publication']['publication_id'],batch_id))
            extraction_company=str(archive['dossiers'][0]['snapshot']['company_id']).removeprefix('ODOO:') if archive['dossiers'] else ''
            extractions=_rows(db,'''SELECT extraction_id,source,company_id,status,started_at,finished_at,source_as_of,row_count,error_code,
                (SELECT count(*) FROM meta.quarantined_rows q WHERE q.extraction_id=e.extraction_id) AS quarantined_rows
                FROM meta.source_extractions e WHERE company_id=ANY(%s) ORDER BY started_at DESC LIMIT 20''',
                ([extraction_company,'ODOO:'+extraction_company],))
            from .odoo_source import freshness
            from datetime import datetime,timezone
            for extraction in extractions:extraction['freshness']=freshness(extraction['source_as_of'],datetime.now(timezone.utc))
            details={str(row['case_id']):show_case(db,row['case_id']) for row in cases}
            attempts=_rows(db,'''SELECT attempt_id,status,started_at,finished_at,inserted_records,error_code
                FROM meta.import_attempts WHERE batch_id=%s ORDER BY started_at DESC''',(batch_id,))
            failures=_rows(db,'''SELECT attempt_id,dataset_label,status,started_at,error_code
                FROM meta.import_attempts WHERE batch_id IS NULL AND status IN ('failed','started') ORDER BY started_at DESC LIMIT 100''')
    return dict(dossiers=evidence,cases=cases,case_details=details,attempts=attempts,unassigned_attempts=failures,
                extractions=extractions,pagination={key:archive[key] for key in ('total','offset','limit','summary') if key in archive},active_cases=active_cases,comparisons=comparisons,
                build=proof,publication=archive['publication'],publication_health=health)


def action(token,case_id,verb,**kwargs):
    with connect() as db:return authenticated_action(db,token,case_id,verb,**kwargs)


def synchronize(token,batch_id,publication_id=None):
    from .investigation import payload_hash
    from .publication import PublicationError
    with connect() as db:
        with db.transaction():
            user=active_user(db,token)
            if not user:raise WorkflowError('Session expiree.')
            authorize(user['role'],'sync')
            archive=read_publication(db,batch_id,publication_id,limit=1)
            pub=archive['publication']['publication_id']
            counts={'created':0,'existing':0,'ignored':0}
            with db.cursor(name='mt_case_sync') as cursor:
                cursor.execute('SELECT dossier,dossier_sha256 FROM app.published_dossiers WHERE publication_id=%s AND batch_id=%s ORDER BY object_kind,object_id',(pub,batch_id))
                while True:
                    rows=cursor.fetchmany(100)
                    if not rows:break
                    items=[]
                    for item,digest in rows:
                        if payload_hash(item)!=digest or item['publication']!=archive['publication']:raise PublicationError('Archive invalide.')
                        items.append(item)
                    result=sync_cases(db,items,user['username'])
                    for key in counts:counts[key]+=result[key]
            return counts


def candidates(token,batch_id,publication_id,object_id):
    from .matching import bank_candidates
    with connect() as db:
        if not active_user(db,token):raise WorkflowError('Session expiree.')
        return bank_candidates(db,batch_id,publication_id,object_id)


def governance_action(token,case_id,verb,**kwargs):
    from .governance import assign,record_external_action,resolve,accept_gap
    functions={'assign':assign,'record_execution':record_external_action,'resolve':resolve,'accept_gap':accept_gap}
    if verb not in functions:raise WorkflowError('Action inconnue.')
    with connect() as db:return functions[verb](db,token,case_id,**kwargs)


def oidc_session(issuer,subject):
    from .oidc_auth import trusted_identity_session
    with connect() as db:return trusted_identity_session(db,issuer,subject)
