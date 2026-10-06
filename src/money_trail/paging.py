"""Pagination PostgreSQL : seuls les dossiers de la page sont désérialisés."""
from uuid import UUID
from .investigation import _rows,payload_hash
from .publication import read_publication,PublicationError


def page_records(db,batch_id,publication_id,limit=25,offset=0,search='',statuses=(),workflow_statuses=(),kind=None,object_id=None,min_amount=None,max_amount=None,assigned=None,sort='object'):
    if type(limit) is not int or not 1<=limit<=100 or type(offset) is not int or offset<0:
        raise ValueError('Pagination invalide.')
    if not isinstance(search,str) or len(search)>100:raise ValueError('Recherche trop longue.')
    # Validation des artefacts et d'un dossier seulement ; pas du snapshot complet.
    head=read_publication(db,batch_id,publication_id,limit=1)
    pub=UUID(head['publication']['publication_id']);bid=UUID(str(batch_id))
    clauses=['d.publication_id=%s','d.batch_id=%s'];args=[pub,bid]
    if search:
        clauses.append("d.object_id ILIKE %s ESCAPE '\\'")
        args.append('%'+search.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
    if statuses:clauses.append("d.dossier->'result'->>'status'=ANY(%s)");args.append(list(statuses))
    if kind:clauses.append('d.object_kind=%s');args.append(kind)
    if object_id:clauses.append('d.object_id=%s');args.append(object_id)
    if workflow_statuses:
        clauses.append('''EXISTS(SELECT 1 FROM app.investigation_cases c WHERE c.import_batch_id=d.batch_id
          AND c.object_kind=d.object_kind AND c.object_id=d.object_id AND c.rule_version=d.rule_version
          AND c.workflow_status=ANY(%s))''');args.append(list(workflow_statuses))
    from decimal import Decimal
    for operator,value in [('>=',min_amount),('<=',max_amount)]:
        if value is not None:
            amount=Decimal(str(value))
            if not amount.is_finite() or amount!=amount.quantize(Decimal('0.01')) or abs(amount)>Decimal('999999999999999999.99'):raise ValueError('Montant de filtre invalide.')
            clauses.append("(CASE WHEN d.object_kind='invoice' THEN d.dossier->'result'->>'invoice_amount' ELSE d.dossier->'result'->>'expected_amount' END)::numeric "+operator+' %s::numeric')
            args.append(str(amount))
    if assigned:
        clauses.append('''EXISTS(SELECT 1 FROM app.investigation_cases c JOIN app.local_users u ON u.user_id=c.assigned_to
            WHERE c.import_batch_id=d.batch_id AND c.object_kind=d.object_kind AND c.object_id=d.object_id AND c.rule_version=d.rule_version AND u.username=%s)''');args.append(assigned)
    orders={'object':'d.object_kind,d.object_id,d.rule_version',
            'amount':"(CASE WHEN d.object_kind='invoice' THEN d.dossier->'result'->>'invoice_amount' ELSE d.dossier->'result'->>'expected_amount' END)::numeric DESC NULLS LAST,d.object_kind,d.object_id,d.rule_version"}
    if sort not in orders:raise ValueError('Tri invalide.')
    where=' AND '.join(clauses)
    total=db.execute('SELECT count(*) FROM app.published_dossiers d WHERE '+where,args).fetchone()[0]
    rows=_rows(db,'SELECT d.* FROM app.published_dossiers d WHERE '+where+
               ' ORDER BY '+orders[sort]+' LIMIT %s OFFSET %s',(*args,limit,offset))
    evidence=[]
    for row in rows:
        item=row['dossier']
        if payload_hash(item)!=row['dossier_sha256'] or item['publication']!=head['publication']:
            raise PublicationError('Integrite du dossier archive non confirmee.')
        if item['snapshot']['batch_id']!=str(bid) or item['dbt_build_evidence']!=head['build']:
            raise PublicationError('Perimetre du dossier archive incoherent.')
        evidence.append(item)
    summary=_rows(db,'''SELECT object_kind,status,dossier_count AS count FROM app.published_status_counts WHERE publication_id=%s AND batch_id=%s''',(pub,bid))
    return dict(publication=head['publication'],build=head['build'],dossiers=evidence,total=total,
                offset=offset,limit=limit,summary=summary)
