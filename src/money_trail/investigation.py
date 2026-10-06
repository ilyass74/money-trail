"""Dossiers explicatifs vérifiables, à partir des résultats dbt et de leurs sources."""
from datetime import date,datetime,time,timedelta,timezone
from decimal import Decimal
from pathlib import Path
import hashlib
import json
from uuid import UUID
import csv
import io
from .reference import HEADERS,EXTRA_HEADERS


def serializable(value):
    if isinstance(value,Decimal):return format(value,'.2f')
    if isinstance(value,(datetime,date)):return value.isoformat()
    if isinstance(value,UUID):return str(value)
    if isinstance(value,dict):return {key:serializable(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):return [serializable(item) for item in value]
    return value


def cutoff(control_on):
    return datetime.combine(control_on+timedelta(days=1),time.min,tzinfo=timezone.utc)


def eligibility(entity,row,result,parent=None):
    """Explique les mêmes filtres que core v1, sans attribuer de cause financière."""
    reasons=[]
    limit=cutoff(result['control_on'])
    if entity=='invoice_allocations':
        if row['state']!='confirmed':reasons.append('Affectation non confirmee.')
        if parent is None:raise ValueError('Paiement lie absent ou ambigu.')
        if parent['state']!='confirmed':reasons.append('Paiement non confirme.')
        if parent['paid_at']>=limit:reasons.append('Paiement posterieur a la date de controle UTC.')
    elif entity=='credit_notes':
        if row['state']!='posted':reasons.append('Avoir non comptabilise.')
        if row['issued_on']>result['control_on']:reasons.append('Avoir posterieur a la date de controle.')
    elif entity=='bank_allocations':
        if row['state']!='confirmed':reasons.append('Affectation bancaire non confirmee.')
        if parent is None:raise ValueError('Mouvement bancaire lie absent ou ambigu.')
        if parent['amount']<=0:reasons.append('Mouvement non crediteur.')
        if parent['booked_on']>result['control_on']:reasons.append('Comptabilisation bancaire posterieure au controle.')
        if parent['value_on']>result['control_on']:reasons.append('Date de valeur bancaire posterieure au controle.')
    else:
        stamp={'processor_payments':'captured_at','refunds':'refunded_at',
               'fees':'charged_at','adjustments':'adjusted_at'}[entity]
        if entity=='processor_payments' and row['state']!='captured':reasons.append('Paiement non capture.')
        if not (result['period_start']<=row[stamp]<result['period_end']):
            reasons.append('Horodatage hors periode du lot [debut, fin).')
        if row[stamp]>=limit:reasons.append('Horodatage posterieur a la date de controle UTC.')
    return {'included_in_observed_sum':not reasons,'exclusion_reasons':reasons}


def explanation(kind,result,coverage):
    status=result['status'];actions=[]
    if kind=='invoice':
        formula='montant facture - paiements affectes - avoirs comptabilises = solde'
        values={key:result[key] for key in ('invoice_amount','allocated_amount','credit_amount','balance')}
        missing=sorted(key for key,value in coverage.items() if value is not True)
        if status=='calcul_bloque':
            summary='Le solde est inconnu : la couverture des sources est incomplete.'
            actions=['Completer les sources manquantes et confirmer leur couverture avant de recalculer.']
        elif status=='soldee':summary='La facture est soldee selon les affectations et avoirs disponibles.'
        elif status=='en_retard':
            summary='Un solde positif subsiste apres la date d echeance.'
            actions=['Verifier les paiements non affectes et les avoirs dans l ERP.',
                     'Si le solde est confirme, soumettre la relance client au responsable.']
        elif status=='surpaiement':
            summary='Les paiements affectes et avoirs depassent le montant de la facture.'
            actions=['Verifier les affectations et les avoirs avant toute proposition de correction.']
        elif status=='echeance_inconnue':
            summary='Un solde positif subsiste, mais l echeance est inconnue.'
            actions=['Verifier l echeance contractuelle ; le retard ne peut pas etre etabli.']
        else:
            summary='Un solde positif subsiste ; la facture n est pas en retard a la date du controle.'
            actions=['Suivre le paiement jusqu a l echeance sans classer ce solde comme un retard.']
        due=result.get('due_on')
        facts={'control_on':result['control_on'],'due_on':due,
               'days_overdue':(result['control_on']-due).days if status=='en_retard' and due else 0 if due else None}
    else:
        formula='captures - remboursements - frais + ajustements signes = attendu ; recu - attendu = ecart'
        values={key:result[key] for key in ('captured_amount','refunded_amount','fees_amount',
                    'adjustments_amount','expected_amount','received_amount','difference')}
        missing=sorted({item['entity'] for item in coverage if item['complete'] is not True})
        if status=='calcul_bloque':
            if result['quality']=='periode_non_close':
                summary='La periode du lot n est pas encore close a la date du controle.'
                actions=['Attendre la cloture de la periode avant de recalculer.']
            else:
                summary='Le rapprochement est bloque par des sources incompletes ; un montant inconnu reste inconnu.'
                actions=['Obtenir les sources manquantes et confirmer leur couverture pour ce lot.',
                         'Importer une nouvelle version puis recalculer ; ne pas remplacer l inconnu par zero.']
        elif status=='rapproche':summary='Le montant bancaire affecte correspond au versement attendu dans la tolerance declaree de '+str(result.get('tolerance','0.00'))+' '+result['currency']+'.'
        elif status=='versement_en_attente':
            summary='Un ecart est observe avant la fin du jour de reception attendu.'
            actions=['Suivre la reception bancaire jusqu a la date attendue.']
        elif status=='delai_a_confirmer':
            summary='Un ecart est observe, mais la date de reception attendue est inconnue.'
            actions=['Obtenir le delai contractuel de versement ; aucun retard bancaire ne peut etre etabli.']
        else:
            summary='Le montant recu differe du montant attendu. La cause n est pas identifiee.'
            actions=['Comparer l avis de versement du prestataire et ses lignes de frais, remboursements et ajustements.',
                     'Verifier la reference et l affectation du credit bancaire.',
                     'Documenter les pieces avant de soumettre une proposition de correction a validation humaine.']
        facts={'control_on':result['control_on'],'period_start':result['period_start'],
               'period_end_exclusive':result['period_end'],'expected_receipt_on':result['expected_receipt_on']}
    def amount(name):
        value=values[name]
        return format(value,'.2f') if value is not None else 'inconnu'
    if kind=='invoice':
        worked=f"{amount('invoice_amount')} - {amount('allocated_amount')} - {amount('credit_amount')} = {amount('balance')} {result.get('currency','MAD')}"
    else:
        worked=(f"{amount('captured_amount')} - {amount('refunded_amount')} - {amount('fees_amount')} + ({amount('adjustments_amount')}) = {amount('expected_amount')} {result.get('currency','MAD')} ; "
                f"{amount('received_amount')} - {amount('expected_amount')} = {amount('difference')} {result.get('currency','MAD')}")
    return {'summary':summary,'formula':formula,'worked_calculation':worked,'values':values,'date_facts':facts,
            'missing_sources':missing,'suggested_checks':actions,
            'cause':result.get('cause'),'accounting_correction_applied':False}


def payload_hash(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()


def read_build_evidence(path:Path):
    return build_evidence_from_bytes(path.read_bytes())


def build_evidence_from_bytes(content):
    report=json.loads(content)
    outcomes=report.get('results',[])
    if not outcomes or any(item['status'] not in ('success','pass') for item in outcomes):
        raise ValueError('Le dernier build dbt doit avoir reussi avant l investigation.')
    model_ids={item['unique_id'] for item in outcomes if item['status']=='success'}
    if not {'model.money_trail.invoice_reconciliation','model.money_trail.settlement_reconciliation'}<=model_ids:
        raise ValueError('Le journal ne contient pas les deux resultats metier.')
    tests=[item for item in outcomes if item['unique_id'].startswith('test.')]
    if not tests:raise ValueError('Le journal ne contient aucun test dbt.')
    return {'invocation_id':report['metadata'].get('invocation_id'),
            'generated_at':report['metadata'].get('generated_at'),
            'artifact_sha256':hashlib.sha256(content).hexdigest(),
            'successful_models':len(model_ids),'passed_tests':len(tests)}


def _rows(connection,query,params=()):
    from psycopg.rows import dict_row
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query,params);return cursor.fetchall()


def dossiers(connection,batch_id,build_evidence,kind=None,object_id=None,schema_prefix=''):
    """Le caller doit ouvrir une transaction REPEATABLE READ READ ONLY."""
    from psycopg import sql
    if schema_prefix:
        from .publication import validate_prefix
        validate_prefix(schema_prefix)
    batches=_rows(connection,'SELECT * FROM meta.import_batches WHERE batch_id=%s',(batch_id,))
    if len(batches)!=1:raise ValueError('Snapshot absent.')
    batch=batches[0]
    if batch['contract_version'] not in ('reference-v1','finance-v1'):raise ValueError('Contrat non supporte par l explicateur v1.')
    manifest=batch['manifest']
    if (batch['company_id'],batch['currency'],batch['contract_version'],batch['control_on'].isoformat())!=(
            manifest['company_id'],manifest['currency'],manifest['contract_version'],manifest['control_on']):
        raise ValueError('Metadonnees du snapshot incoherentes avec le manifeste.')
    files=_rows(connection,'SELECT * FROM meta.import_files WHERE batch_id=%s ORDER BY entity',(batch_id,))
    file_index={row['file_id']:row for row in files}
    required=set(HEADERS)
    if batch['contract_version']=='finance-v1':required.update(item['entity'] for item in manifest['files'] if item['entity'] in EXTRA_HEADERS)
    if {row['entity'] for row in files} != required or len(files)!=len(required):
        raise ValueError('Liste des fichiers sources incomplete ou ambigue.')
    file_rows={}
    declarations={row['entity']:row for row in batch['manifest']['files']}
    for row in files:
        if hashlib.sha256(bytes(row['source_bytes'])).hexdigest()!=row['sha256']:
            raise ValueError('Integrite du fichier source non confirmee.')
        declared=declarations[row['entity']]
        if (row['sha256'],row['row_count'],row['source_filename'])!=(declared['sha256'],declared['row_count'],declared['file']):
            raise ValueError('Fichier conserve incoherent avec son manifeste.')
        reader=csv.DictReader(io.StringIO(bytes(row['source_bytes']).decode('utf-8'),newline=''))
        if reader.fieldnames!=(HEADERS|EXTRA_HEADERS)[row['entity']]:raise ValueError('Colonnes du fichier conserve invalides.')
        file_rows[row['file_id']]=list(reader)
        if len(file_rows[row['file_id']])!=row['row_count']:raise ValueError('Nombre de lignes sources incoherent.')
    manifest_bytes=bytes(batch['manifest_bytes'])
    if not manifest_bytes or json.loads(manifest_bytes)!=batch['manifest']:
        raise ValueError('Le manifeste conserve differe de sa version structuree.')
    fingerprint=hashlib.sha256(manifest_bytes)
    for row in files:
        fingerprint.update(row['entity'].encode('utf-8')+b'\0'+bytes.fromhex(row['sha256']))
    if fingerprint.hexdigest()!=batch['fingerprint']:raise ValueError('Empreinte du snapshot non confirmee.')
    raw=_rows(connection,'''SELECT r.* FROM raw.source_records r
        JOIN meta.import_files f ON f.file_id=r.file_id WHERE f.batch_id=%s''',(batch_id,))
    raw_index={row['record_id']:row for row in raw}
    if len(raw)!=sum(len(rows) for rows in file_rows.values()):raise ValueError('Nombre de lignes brutes incoherent.')
    for row in raw:
        if payload_hash(row['payload'])!=row['payload_sha256']:raise ValueError('Integrite de la ligne brute non confirmee.')
        if any(row[key]!=row['payload'][key] for key in ('company_id','source_system','source_id')):
            raise ValueError('Identite brute incoherente avec la ligne source.')
        source_rows=file_rows[row['file_id']]
        index=row['row_number']-1
        if index<0 or index>=len(source_rows) or source_rows[index]!=row['payload']:
            raise ValueError('La ligne brute ne correspond pas aux octets du fichier source.')
    source_metadata=[{key:row[key] for key in ('file_id','entity','source_filename','sha256','row_count')} for row in files]
    tables={}
    for entity in ('invoices','invoice_allocations','erp_payments','credit_notes','settlement_batches',
                   'processor_payments','refunds','fees','adjustments','bank_allocations','bank_movements'):
        tables[entity]=_rows(connection,sql.SQL('SELECT * FROM {}.{} WHERE import_batch_id=%s ORDER BY source_id').format(sql.Identifier(schema_prefix+'staging'),sql.Identifier('stg_'+entity)),(batch_id,))
    from collections import defaultdict
    parent_index={entity:{(row['company_id'],row['currency'],row['source_id']):row for row in rows} for entity,rows in tables.items()}
    child_index=defaultdict(list)
    invoice_entities={'invoice_allocations','credit_notes'}
    for entity,rows in tables.items():
        if entity in invoice_entities or entity in {'processor_payments','refunds','fees','adjustments','bank_allocations'}:
            field='invoice_id' if entity in invoice_entities else 'batch_id'
            for row in rows:child_index[(entity,row['company_id'],row['currency'],row[field])].append(row)
    line_index=defaultdict(list)
    for original in raw:
        if file_index[original['file_id']]['entity'] in ('invoice_lines','invoice_order_links'):
            line_index[(original['company_id'],original['payload']['currency'],original['payload']['invoice_id'])].append(original)
    coverage_index=defaultdict(list)
    for c in manifest['settlement_coverage']:coverage_index[(c['company_id'],c['currency'],c['batch_id'])].append(c)
    def scoped(entity,result):
        oid=result['invoice_id'] if entity in invoice_entities else result['batch_id']
        return child_index[(entity,result['company_id'],result['currency'],oid)]
    def parent(entity,result,source_id):
        key=(result['company_id'],result['currency'],source_id)
        if key not in parent_index[entity]:raise ValueError('Reference source absente ou ambigue.')
        return parent_index[entity][key]
    output=[]
    for result_kind,table,key in [('invoice','invoice_reconciliation','invoice_id'),('settlement','settlement_reconciliation','batch_id')]:
        if kind and kind!=result_kind:continue
        results=_rows(connection,sql.SQL('SELECT * FROM {}.{} WHERE import_batch_id=%s ORDER BY {}').format(sql.Identifier(schema_prefix+'marts'),sql.Identifier(table),sql.Identifier(key)),(batch_id,))
        for result in results:
            if object_id and object_id!=result[key]:continue
            if result['rule_version'] not in (result_kind+'-v1',result_kind+'-v2'):raise ValueError('Version de regle non supportee.')
            evidence=[];components={}
            def add(entity,row,contribution=None,linked=None):
                original=raw_index[row['record_id']];file=file_index[original['file_id']]
                entry={'entity':entity,'record_id':row['record_id'],'source_id':row['source_id'],
                       'source_system':row['source_system'],'source_filename':file['source_filename'],
                       'file_id':file['file_id'],'data_row_number':original['row_number'],
                       'file_sha256':file['sha256'],'payload_sha256':original['payload_sha256'],
                       'raw_payload':original['payload'],'role':'contribution' if contribution else 'context',
                       'integrity_verified':True}
                if contribution:
                    decision=eligibility(entity,row,result,linked)
                    entry.update(decision);entry['observed_amount']=row['amount']
                    components[contribution]=components.get(contribution,Decimal('0.00'))+(row['amount'] if decision['included_in_observed_sum'] else Decimal('0.00'))
                evidence.append(entry)
            if result_kind=='invoice':
                add('invoices',parent('invoices',result,result[key]))
                for original in line_index[(result['company_id'],result['currency'],result[key])]:
                    add(file_index[original['file_id']]['entity'],{'record_id':original['record_id'],'source_id':original['source_id'],'source_system':original['source_system']})
                payments={}
                for row in scoped('invoice_allocations',result):
                    if row['invoice_id']==result[key]:
                        p=parent('erp_payments',result,row['payment_id']);payments[p['source_id']]=p
                        add('invoice_allocations',row,'allocated_amount',p)
                for p in payments.values():add('erp_payments',p)
                for row in scoped('credit_notes',result):
                    if row['invoice_id']==result[key]:add('credit_notes',row,'credit_amount')
                for name in ('allocated_amount','credit_amount'):
                    if result[name] is not None and components.get(name,Decimal('0.00'))!=result[name]:raise ValueError('Les preuves ne concordent pas avec le resultat dbt.')
                if result['balance'] is not None and result['balance']!=result['invoice_amount']-result['allocated_amount']-result['credit_amount']:
                    raise ValueError('Solde incoherent avec ses composantes.')
                coverage=batch['manifest']['invoice_coverage']
            else:
                add('settlement_batches',parent('settlement_batches',result,result[key]))
                for entity,name in [('processor_payments','captured_amount'),('refunds','refunded_amount'),('fees','fees_amount'),('adjustments','adjustments_amount')]:
                    for row in scoped(entity,result):
                        if row['batch_id']==result[key]:add(entity,row,name)
                movements={}
                for row in scoped('bank_allocations',result):
                    if row['batch_id']==result[key]:
                        p=parent('bank_movements',result,row['movement_id']);movements[p['source_id']]=p
                        add('bank_allocations',row,'received_amount',p)
                for p in movements.values():add('bank_movements',p)
                for name in ('captured_amount','refunded_amount','fees_amount','adjustments_amount','received_amount'):
                    if result[name] is not None and components.get(name,Decimal('0.00'))!=result[name]:raise ValueError('Les preuves ne concordent pas avec le resultat dbt.')
                if result['expected_amount'] is not None and result['expected_amount']!=result['captured_amount']-result['refunded_amount']-result['fees_amount']+result['adjustments_amount']:
                    raise ValueError('Montant attendu incoherent.')
                if result['difference'] is not None and result['difference']!=result['received_amount']-result['expected_amount']:
                    raise ValueError('Ecart incoherent.')
                coverage=coverage_index[(result['company_id'],result['currency'],result[key])]
            output.append({'dossier_version':'investigation-v1','kind':result_kind,'object_id':result[key],
                'snapshot':{key:batch[key] for key in ('batch_id','fingerprint','contract_version','company_id','currency','control_on','ingested_at')},
                'dbt_build_evidence':build_evidence,'result':result,'explanation':explanation(result_kind,result,coverage),
                'source_coverage':coverage,'source_files':source_metadata,'line_evidence':evidence,
                'evidence_matches_components':True,'generated_at':datetime.now(timezone.utc)})
    if not output:raise ValueError('Aucun resultat trouve pour cet objet et ce snapshot.')
    return output


def markdown_dossier(dossier):
    d=serializable(dossier);r=d['result'];e=d['explanation']
    lines=[f"# {d['object_id']} — dossier d'investigation",'',e['summary'],'',
           f"- Statut : `{r['status']}` ; qualité : `{r['quality']}`.",
           f"- Entreprise : {r['company_id']} ; devise : {r['currency']}.",
           f"- Contrôle : {r['control_on']} ; règle : {r['rule_version']}.",
           f"- Snapshot : `{d['snapshot']['batch_id']}`.",'','## Calcul','',e['formula'],'',
           e['worked_calculation'],'',f"| Composante | Montant {r['currency']} |",'|---|---:|']
    if d.get('publication'):
        pub=d['publication']
        lines[4:4]=[f"- Publication validée : version {pub['version']} ; publiée le {pub['published_at']}.",
                    f"- Identifiant de publication : `{pub['publication_id']}` ; code SHA-256 : `{pub['code_sha256']}`."]
    for name,value in e['values'].items():lines.append(f"| {name} | {value if value is not None else 'Inconnu'} |")
    lines+=['','## Couverture et vérifications','']
    lines.append('Sources manquantes : '+(', '.join(e['missing_sources']) or 'aucune déclarée.'))
    for action in e['suggested_checks']:lines.append('- '+action)
    lines+=['','Aucune correction comptable appliquée.','','## Lignes sources','',
            f"| Entité | Identifiant source | Ligne de données | Montant source {r['currency']} | Inclusion dans la somme observée |",
            '|---|---|---:|---:|---|']
    for row in d['line_evidence']:
        included='Oui' if row.get('included_in_observed_sum') else 'Non' if row['role']=='contribution' else 'Contexte'
        payload=row['raw_payload'];value=payload.get('amount',payload.get('total_amount','—'))
        lines.append(f"| {row['entity']} | {row['source_id']} | {row['data_row_number']} | {value} | {included} |")
    excluded=[row for row in d['line_evidence'] if row.get('exclusion_reasons')]
    if excluded:
        lines+=['','Motifs d’exclusion :','']
        for row in excluded:lines.append('- '+row['source_id']+' : '+' '.join(row['exclusion_reasons']))
    lines+=['','Les montants inconnus restent inconnus même si aucune ligne correspondante n’est disponible.',
            'Le fichier JSON contient les payloads bruts, empreintes, critères d’exclusion et preuves du build dbt.',
            '',f"Généré : {d['generated_at']}"]
    return '\n'.join(lines)+'\n'
