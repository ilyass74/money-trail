"""Comparaison immuable des règles et succession sans effacer les décisions."""
from pathlib import Path
from uuid import uuid4
import hashlib
from .investigation import _rows,payload_hash,serializable
from .workflow import setup_workflow,_event

ROOT=Path(__file__).resolve().parents[2]


def setup_operations(db):
    setup_workflow(db)
    content=(ROOT/'sql/006_operations.sql').read_bytes();digest=hashlib.sha256(content).hexdigest()
    with db.transaction():
        db.execute('SELECT pg_advisory_xact_lock(732084651::bigint)')
        old=db.execute('SELECT sha256 FROM meta.schema_migrations WHERE version=%s',('006_operations',)).fetchone()
        if old:
            if old[0]!=digest:raise ValueError('Empreinte de migration 006 differente.')
        else:
            db.execute(content.decode())
            db.execute('INSERT INTO meta.schema_migrations(version,sha256) VALUES(%s,%s)',('006_operations',digest))

    from .governance import setup_governance
    setup_governance(db)


def result_changes(old,new):
    # Les temps de calcul et identifiants techniques ne sont pas des différences financières.
    keys=(set(old)|set(new))-{'calculated_at','import_batch_id','invoice_record_id','settlement_record_id'}
    return {key:{'before':old.get(key),'after':new.get(key)} for key in sorted(keys) if old.get(key)!=new.get(key)}


def archive_comparisons(db,publication_id):
    from psycopg.types.json import Jsonb
    rows=_rows(db,'''SELECT n.*,o.publication_id AS old_publication_id,o.dossier AS old_dossier
      FROM app.published_dossiers n
      JOIN LATERAL (SELECT p.* FROM app.published_dossiers p
       JOIN app.result_publications v USING(publication_id)
       WHERE p.batch_id=n.batch_id AND p.object_kind=n.object_kind AND p.object_id=n.object_id
        AND p.publication_id<>n.publication_id
        AND v.version < (SELECT version FROM app.result_publications WHERE publication_id=n.publication_id)
        AND p.rule_version<>n.rule_version ORDER BY v.version DESC LIMIT 1) o ON true
      WHERE n.publication_id=%s''',(publication_id,))
    for row in rows:
        before=row['old_dossier']['result'];after=row['dossier']['result']
        db.execute('''INSERT INTO app.rule_comparisons(old_publication_id,new_publication_id,batch_id,object_kind,object_id,comparison)
          VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
          (row['old_publication_id'],publication_id,row['batch_id'],row['object_kind'],row['object_id'],
           Jsonb({'before':before,'after':after,'changes':result_changes(before,after),'same_source_snapshot':True})))
    return len(rows)


def evidence_signature(item):
    coverage=item['source_coverage']
    if isinstance(coverage,list):coverage=sorted(coverage,key=lambda c:(c['entity'],c.get('batch_id','')))
    return payload_hash({'lines':sorted((r['entity'],r['source_id'],r['payload_sha256']) for r in item['line_evidence']),
                         'coverage':coverage,'control_on':serializable(item['result']['control_on'])})


def successors(db,publication_id,actor):
    from psycopg.types.json import Jsonb
    # Seuls les objets déjà suivis reçoivent une nouvelle revue automatique.
    rows=_rows(db,'SELECT * FROM app.published_dossiers WHERE publication_id=%s ORDER BY object_kind,object_id',(publication_id,))
    count=0
    for row in rows:
        item=row['dossier'];r=item['result']
        previous=_rows(db,'''SELECT c.* FROM app.investigation_cases c
          JOIN meta.import_batches b ON b.batch_id=c.import_batch_id
          WHERE c.company_id=%s AND c.currency=%s AND c.object_kind=%s AND c.object_id=%s
          ORDER BY b.ingested_at DESC,c.created_at DESC,c.case_id DESC LIMIT 1 FOR UPDATE OF c''',
          (r['company_id'],r['currency'],item['kind'],item['object_id']))
        if not previous:continue
        old=previous[0]
        if str(old['import_batch_id'])==str(row['batch_id']) and old['rule_version']==row['rule_version']:continue
        # Une republication historique ne succède jamais à des sources plus récentes.
        newer=db.execute('SELECT ingested_at >= (SELECT ingested_at FROM meta.import_batches WHERE batch_id=%s) FROM meta.import_batches WHERE batch_id=%s',
                         (old['import_batch_id'],row['batch_id'])).fetchone()[0]
        if not newer:continue
        source_changed=evidence_signature(old['evidence'])!=evidence_signature(item)
        rule_changed=old['rule_version']!=row['rule_version']
        if not source_changed and not rule_changed:continue
        reason='source_and_rule_changed' if source_changed and rule_changed else 'source_changed' if source_changed else 'rule_changed'
        case_id=uuid4()
        inserted=db.execute('''INSERT INTO app.investigation_cases
          (case_id,import_batch_id,company_id,currency,object_kind,object_id,rule_version,business_status,evidence,created_by,assigned_to)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
          ON CONFLICT(import_batch_id,company_id,currency,object_kind,object_id,rule_version) DO NOTHING RETURNING case_id''',
          (case_id,row['batch_id'],r['company_id'],r['currency'],item['kind'],item['object_id'],row['rule_version'],r['status'],Jsonb(item),actor,old.get('assigned_to'))).fetchone()
        if not inserted:continue
        db.execute('INSERT INTO app.case_successions(previous_case_id,successor_case_id,publication_id,reason) VALUES(%s,%s,%s,%s)',
                   (old['case_id'],case_id,publication_id,reason))
        _event(db,case_id,0,'reopened_from_source',actor,None,'open',{'previous_case_id':str(old['case_id']),'reason':reason,
                'business_status':r['status'],'accounting_correction_applied':False})
        count+=1
    return count
