"""Workflow local : propositions et décisions, sans appliquer de correction source."""
from pathlib import Path
from uuid import uuid4
import hashlib

ROOT=Path(__file__).resolve().parents[2]
ISSUES={'ecart','calcul_bloque','en_retard','surpaiement','echeance_inconnue','delai_a_confirmer'}
PROPOSAL_TYPES={'source_data_review','allocation_review','accounting_review'}


class WorkflowError(ValueError):pass


def actor_name(value):
    value=(value or '').strip()
    if not value or len(value)>100:raise WorkflowError('Indiquer un acteur local de 1 a 100 caracteres.')
    return value


def require_text(value,label):
    value=(value or '').strip()
    if not value:raise WorkflowError(f'{label} obligatoire.')
    return value


def transition(status,action):
    rules={'start':{'open':'in_review','rejected':'in_review'},
           'propose':{'in_review':'awaiting_validation'},
           'approve':{'awaiting_validation':'approved'},
           'reject':{'awaiting_validation':'rejected'},
           'close':{'approved':'closed','rejected':'closed'}}
    if action=='comment':
        if status in ('closed','resolved','accepted_with_justification'):raise WorkflowError('Le dossier clos ne peut plus recevoir de commentaire.')
        return status
    if status not in rules.get(action,{}):raise WorkflowError(f'Transition {action} impossible depuis {status}.')
    return rules[action][status]


def check_reviewer(proposed_by,reviewer):
    if actor_name(proposed_by).casefold()==actor_name(reviewer).casefold():
        raise WorkflowError('Le proposant ne peut pas valider ou rejeter sa propre proposition.')


def setup_workflow(connection):
    content=(ROOT/'sql/003_workflow.sql').read_bytes();digest=hashlib.sha256(content).hexdigest()
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(732084651::bigint)')
        row=connection.execute('SELECT sha256 FROM meta.schema_migrations WHERE version=%s',('003_workflow',)).fetchone()
        if row:
            if row[0]!=digest:raise WorkflowError('La migration 003 existante a une autre empreinte.')
        else:
            connection.execute(content.decode('utf-8'))
            connection.execute('INSERT INTO meta.schema_migrations(version,sha256) VALUES (%s,%s)',('003_workflow',digest))


def _event(connection,case_id,revision,action,actor,before,after,details):
    from psycopg.types.json import Jsonb
    connection.execute('''INSERT INTO app.case_events
      (case_id,revision,action,actor,from_status,to_status,details) VALUES (%s,%s,%s,%s,%s,%s,%s)''',
      (case_id,revision,action,actor,before,after,Jsonb(details)))


def sync_cases(connection,dossiers,actor):
    from psycopg.types.json import Jsonb
    from .investigation import serializable
    actor=actor_name(actor);created=0;existing=0;ignored=0
    with connection.transaction():
        for dossier in dossiers:
            result=dossier['result']
            if result['status'] not in ISSUES:ignored+=1;continue
            key=(result['import_batch_id'],result['company_id'],result['currency'],dossier['kind'],dossier['object_id'],result['rule_version'])
            case_id=uuid4()
            row=connection.execute('''INSERT INTO app.investigation_cases
                (case_id,import_batch_id,company_id,currency,object_kind,object_id,rule_version,business_status,evidence,created_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (import_batch_id,company_id,currency,object_kind,object_id,rule_version) DO NOTHING RETURNING case_id''',
                (case_id,*key,result['status'],Jsonb(serializable(dossier)),actor)).fetchone()
            if row:
                _event(connection,case_id,0,'created',actor,None,'open',{'business_status':result['status']})
                created+=1
            else:existing+=1
    return dict(created=created,existing=existing,ignored=ignored)


def list_cases(connection,batch_id):
    from psycopg.rows import dict_row
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute('''SELECT case_id,object_kind,object_id,business_status,workflow_status,revision,created_by
            FROM app.investigation_cases WHERE import_batch_id=%s ORDER BY object_kind,object_id''',(batch_id,))
        return cursor.fetchall()


def resolve_case(connection,batch_id,kind,object_id):
    rows=connection.execute('''SELECT case_id FROM app.investigation_cases
      WHERE import_batch_id=%s AND object_kind=%s AND object_id=%s''',(batch_id,kind,object_id)).fetchall()
    if len(rows)!=1:raise WorkflowError('Dossier absent ou ambigu ; utiliser son case_id.')
    return rows[0][0]


def show_case(connection,case_id):
    from psycopg.rows import dict_row
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute('SELECT * FROM app.investigation_cases WHERE case_id=%s',(case_id,));case=cursor.fetchone()
        if not case:raise WorkflowError('Dossier absent.')
        if case.get('assigned_to'):
            case['assigned_name']=connection.execute('SELECT username FROM app.local_users WHERE user_id=%s',(case['assigned_to'],)).fetchone()[0]
        else:case['assigned_name']=None
        cursor.execute('SELECT * FROM app.correction_proposals WHERE case_id=%s ORDER BY proposal_number',(case_id,));proposals=cursor.fetchall()
        cursor.execute('SELECT * FROM app.case_events WHERE case_id=%s ORDER BY revision',(case_id,));events=cursor.fetchall()
    links=[]
    if connection.execute("SELECT to_regclass('app.case_successions')").fetchone()[0]:
        links=_rows_successions(connection,case_id)
    actions=[];resolutions=[]
    if connection.execute("SELECT to_regclass('app.external_action_evidence')").fetchone()[0]:
        from .investigation import _rows
        actions=_rows(connection,'SELECT action_id,external_reference,filename,evidence_sha256,recorded_by,recorded_at FROM app.external_action_evidence WHERE case_id=%s ORDER BY recorded_at',(case_id,))
        resolutions=_rows(connection,'SELECT * FROM app.case_resolutions WHERE case_id=%s',(case_id,))
    return dict(case=case,proposals=proposals,events=events,successions=links,external_actions=actions,resolutions=resolutions)


def act(connection,case_id,action,actor,note=None,proposal_type=None,description=None,
        justification=None,record_ids=(),expected_revision=None):
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
    actor=actor_name(actor)
    with connection.transaction():
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute('SELECT * FROM app.investigation_cases WHERE case_id=%s FOR UPDATE',(case_id,));case=cursor.fetchone()
            if not case:raise WorkflowError('Dossier absent.')
            if expected_revision is not None and case['revision']!=expected_revision:
                raise WorkflowError('Le dossier a change ; le relire avant de poursuivre.')
            before=case['workflow_status'];after=transition(before,action)
            details={}
            if action=='propose':
                if proposal_type not in PROPOSAL_TYPES:raise WorkflowError('Type de proposition non supporte.')
                description=require_text(description,'Description');justification=require_text(justification,'Justification')
                allowed={row['record_id'] for row in case['evidence']['line_evidence']}
                if any(type(value) is not int or value not in allowed for value in record_ids):
                    raise WorkflowError('La preuve citee ne fait pas partie du dossier.')
                proposal_id=uuid4()
                number=cursor.execute('SELECT coalesce(max(proposal_number),0)+1 AS number FROM app.correction_proposals WHERE case_id=%s',(case_id,)).fetchone()['number']
                cursor.execute('''INSERT INTO app.correction_proposals
                  (proposal_id,case_id,proposal_number,proposal_type,description,justification,evidence_record_ids,proposed_by)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                  (proposal_id,case_id,number,proposal_type,description,justification,Jsonb(list(record_ids)),actor))
                details={'proposal_id':str(proposal_id),'proposal_type':proposal_type,'proposal_number':number}
            elif action in ('approve','reject'):
                note=require_text(note,'Motif de decision')
                pending=cursor.execute('SELECT * FROM app.correction_proposals WHERE case_id=%s AND decision IS NULL FOR UPDATE',(case_id,)).fetchall()
                if len(pending)!=1:raise WorkflowError('Une unique proposition en attente est requise.')
                proposal=pending[0];check_reviewer(proposal['proposed_by'],actor)
                cursor.execute('''UPDATE app.correction_proposals SET decision=%s,decided_by=%s,
                  decision_note=%s,decided_at=CURRENT_TIMESTAMP WHERE proposal_id=%s''',
                  (after,actor,note,proposal['proposal_id']))
                details={'proposal_id':str(proposal['proposal_id']),'note':note,'accounting_correction_applied':False}
            else:details={'note':require_text(note,'Commentaire ou conclusion')}
            revision=case['revision']+1
            cursor.execute('''UPDATE app.investigation_cases SET workflow_status=%s,revision=%s,
              updated_at=CURRENT_TIMESTAMP WHERE case_id=%s''',(after,revision,case_id))
            _event(connection,case_id,revision,action,actor,before,after,details)
    return {'case_id':str(case_id),'workflow_status':after,'revision':revision,'accounting_correction_applied':False}


def _rows_successions(connection,case_id):
    from .investigation import _rows
    return _rows(connection,'SELECT * FROM app.case_successions WHERE previous_case_id=%s OR successor_case_id=%s ORDER BY created_at',(case_id,case_id))
