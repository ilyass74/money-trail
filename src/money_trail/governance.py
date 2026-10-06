"""Responsables et pièces d'action ; la résolution exige un nouveau contrôle."""
from pathlib import Path
from uuid import uuid4
import hashlib
from .workflow import WorkflowError,_event,actor_name
from .local_auth import active_user,authorize,setup_accounts
from .investigation import _rows

ROOT=Path(__file__).resolve().parents[2]


def setup_governance(db):
    setup_accounts(db)
    content=(ROOT/'sql/007_governance.sql').read_bytes();digest=hashlib.sha256(content).hexdigest()
    with db.transaction():
        db.execute('SELECT pg_advisory_xact_lock(732084651::bigint)')
        old=db.execute('SELECT sha256 FROM meta.schema_migrations WHERE version=%s',('007_governance',)).fetchone()
        if old:
            if old[0]!=digest:raise ValueError('Empreinte de migration 007 differente.')
        else:
            db.execute(content.decode());db.execute('INSERT INTO meta.schema_migrations(version,sha256) VALUES(%s,%s)',('007_governance',digest))


def locked_case(db,token,case_id,permission,revision):
    user=active_user(db,token)
    if not user:raise WorkflowError('Session expiree.')
    authorize(user['role'],permission)
    rows=_rows(db,'SELECT * FROM app.investigation_cases WHERE case_id=%s FOR UPDATE',(case_id,))
    if not rows:raise WorkflowError('Dossier absent.')
    case=rows[0]
    if type(revision) is not int or revision!=case['revision']:raise WorkflowError('Le dossier a change ; le relire.')
    return user,case


def event_update(db,case,actor,action,details,status=None):
    revision=case['revision']+1;status=status or case['workflow_status']
    db.execute('UPDATE app.investigation_cases SET revision=%s,workflow_status=%s,updated_at=clock_timestamp() WHERE case_id=%s',
               (revision,status,case['case_id']))
    _event(db,case['case_id'],revision,action,actor,case['workflow_status'],status,details)
    return dict(revision=revision,workflow_status=status,accounting_correction_applied=False)


def assign(db,token,case_id,assignee,revision):
    with db.transaction():
        user,case=locked_case(db,token,case_id,'assign',revision)
        if case['workflow_status'] in ('closed','resolved','accepted_with_justification'):raise WorkflowError('Dossier termine.')
        target=_rows(db,"SELECT user_id,username,role,active FROM app.local_users WHERE username=%s AND active AND role IN ('analyst','reviewer','admin')",(assignee,))
        if len(target)!=1:raise WorkflowError('Responsable actif habilite requis.')
        if user['role']!='admin' and target[0]['user_id']!=user['user_id']:raise WorkflowError('Prendre votre propre dossier ou contacter l administrateur.')
        db.execute('UPDATE app.investigation_cases SET assigned_to=%s WHERE case_id=%s',(target[0]['user_id'],case_id))
        return event_update(db,case,user['username'],'assigned',{'assignee':assignee})


def record_external_action(db,token,case_id,reference,filename,content,revision):
    if not isinstance(content,bytes) or not 1<=len(content)<=10*1024*1024:raise WorkflowError('Piece requise, limite 10 Mo.')
    if Path(filename).suffix.lower() not in ('.pdf','.png','.jpg','.jpeg','.txt'):raise WorkflowError('Format de piece non supporte.')
    reference=actor_name(reference)
    with db.transaction():
        user,case=locked_case(db,token,case_id,'record_execution',revision)
        if case['workflow_status']!='approved':raise WorkflowError('Une proposition approuvee est requise.')
        proposals=_rows(db,"SELECT * FROM app.correction_proposals WHERE case_id=%s AND decision='approved' ORDER BY proposal_number DESC LIMIT 1",(case_id,))
        if not proposals:raise WorkflowError('Proposition approuvee absente.')
        if proposals[0]['proposed_by'].casefold()==user['username'].casefold():raise WorkflowError('Un acteur distinct confirme la piece.')
        action_id=uuid4();digest=hashlib.sha256(content).hexdigest()
        db.execute('''INSERT INTO app.external_action_evidence(action_id,case_id,proposal_id,external_reference,filename,evidence_bytes,evidence_sha256,recorded_by)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''',(action_id,case_id,proposals[0]['proposal_id'],reference,Path(filename).name,content,digest,user['username']))
        return event_update(db,case,user['username'],'external_action_recorded',{'action_id':str(action_id),'external_reference':reference,'sha256':digest,'execution_attested_by':user['username']})


def resolve(db,token,case_id,publication_id,revision):
    from psycopg.types.json import Jsonb
    with db.transaction():
        user,case=locked_case(db,token,case_id,'resolve',revision)
        if case['workflow_status']!='approved':raise WorkflowError('Proposition approuvee requise avant resolution.')
        actions=_rows(db,'SELECT * FROM app.external_action_evidence WHERE case_id=%s ORDER BY recorded_at DESC LIMIT 1',(case_id,))
        if not actions:raise WorkflowError('Piece d action externe requise.')
        action=actions[0]
        # Un changement de tolérance sur les mêmes sources ne prouve pas l'exécution d'une correction.
        rows=_rows(db,'''SELECT d.dossier FROM app.published_dossiers d
          JOIN app.published_snapshots s USING(publication_id,batch_id)
          JOIN app.result_publications p USING(publication_id)
          WHERE d.publication_id=%s AND d.object_kind=%s AND d.object_id=%s
          AND s.company_id=%s AND s.currency=%s AND s.batch_id<>%s
          AND s.ingested_at>%s AND p.published_at>%s''',
          (publication_id,case['object_kind'],case['object_id'],case['company_id'],case['currency'],case['import_batch_id'],action['recorded_at'],action['recorded_at']))
        if len(rows)!=1 or rows[0]['dossier']['result']['status'] not in ('soldee','rapproche'):
            raise WorkflowError('Un nouveau controle valide apres l action doit confirmer le rapprochement.')
        if hashlib.sha256(bytes(action['evidence_bytes'])).hexdigest()!=action['evidence_sha256']:raise WorkflowError('Integrite de la piece non confirmee.')
        db.execute('INSERT INTO app.case_resolutions(case_id,action_id,publication_id,result,confirmed_by) VALUES(%s,%s,%s,%s,%s)',
                   (case_id,action['action_id'],publication_id,Jsonb(rows[0]['dossier']['result']),user['username']))
        return event_update(db,case,user['username'],'resolved',{'publication_id':str(publication_id),'action_id':str(action['action_id'])},'resolved')


def accept_gap(db,token,case_id,note,revision):
    note=(note or '').strip()
    if not note:raise WorkflowError('Justification obligatoire.')
    with db.transaction():
        user,case=locked_case(db,token,case_id,'accept_gap',revision)
        if case['workflow_status'] not in ('open','in_review','rejected','approved') or case['business_status'] not in ('ecart','surpaiement','en_retard'):raise WorkflowError('Etat ou resultat incompatible avec une acceptation d ecart.')
        return event_update(db,case,user['username'],'accepted_with_justification',{'note':note,'financial_result_unchanged':True},'accepted_with_justification')
