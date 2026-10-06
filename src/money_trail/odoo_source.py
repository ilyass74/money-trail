"""Extraction Odoo JSON-2 en lecture seule, journalisée et contrôlée."""
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from uuid import uuid4
import json
import os
import urllib.request
from urllib.parse import urlparse
from .investigation import payload_hash

MODELS={
 'account.move':['id','company_id','currency_id','name','move_type','state','amount_total','invoice_date','invoice_date_due','reversed_entry_id','invoice_line_ids','write_date'],
 'account.move.line':['id','company_id','currency_id','move_id','name','quantity','price_subtotal','price_total','display_type','amount_currency','balance','date','payment_id','write_date'],
 'account.payment':['id','company_id','currency_id','amount','state','date','payment_type','partner_type','move_id','write_date'],
 'account.partial.reconcile':['id','company_id','debit_move_id','credit_move_id','amount','debit_amount_currency','credit_amount_currency','max_date','write_date'],
}
SALES_MODELS={'sale.order':['id','company_id','currency_id','name','partner_id','amount_total','date_order','state','write_date'],
              'sale.order.line':['id','company_id','currency_id','order_id','write_date']}

class ExtractionError(ValueError):pass


def relation(value):
    return value[0] if isinstance(value,list) and len(value)==2 and type(value[0]) is int else value if type(value) is int else None


class OdooClient:
    def __init__(self,url,api_key,database=None,timeout=30):
        parsed=urlparse(url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:raise ExtractionError('URL Odoo invalide.')
        if parsed.scheme!='https' and not(parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1')):
            raise ExtractionError('HTTPS requis, sauf Odoo local.')
        if not api_key:raise ExtractionError('Cle Odoo absente.')
        self.url=url.rstrip('/');self.key=api_key;self.database=database;self.timeout=timeout

    def call(self,model,method,values):
        if model not in (MODELS|SALES_MODELS) or method not in ('search_read','fields_get'):raise ExtractionError('Appel non autorise.')
        headers={'Content-Type':'application/json','Authorization':'bearer '+self.key}
        if self.database:headers['X-Odoo-Database']=self.database
        body=json.dumps(values).encode()
        request=urllib.request.Request(self.url+'/json/2/'+model+'/'+method,data=body,headers=headers,method='POST')
        try:
            with urllib.request.urlopen(request,timeout=self.timeout) as response:return json.load(response,parse_float=Decimal)
        except Exception as error:
            # Ne jamais exposer la réponse serveur ni les credentials dans les journaux.
            raise ExtractionError('Appel Odoo refuse ou indisponible.') from None


def extract_models(client,company_id,page_size=500,include_sales=False):
    if type(company_id) is not int or company_id<=0:raise ExtractionError('Entreprise Odoo invalide.')
    if type(page_size) is not int or not 1<=page_size<=1000:raise ExtractionError('Taille de page invalide.')
    as_of=datetime.now(timezone.utc).replace(microsecond=0)
    cutoff=as_of.strftime('%Y-%m-%d %H:%M:%S')
    context={'allowed_company_ids':[company_id]}
    def scan(model,fields):
        rows=[];last=0
        while True:
            page=client.call(model,'search_read',dict(domain=[['company_id','=',company_id],['id','>',last]],
                fields=fields,order='id asc',limit=page_size,context=context))
            if not isinstance(page,list):raise ExtractionError('Reponse Odoo invalide.')
            if not page:break
            for row in page:
                if type(row.get('id')) is not int or row['id']<=last or relation(row.get('company_id'))!=company_id:
                    raise ExtractionError('Identite ou pagination Odoo incoherente.')
                stamp=datetime.fromisoformat(row['write_date']).replace(tzinfo=timezone.utc)
                if stamp>as_of:raise ExtractionError('Source modifiee apres le debut de l extraction.')
                last=row['id'];rows.append(row)
        return rows
    model_fields={key:list(value) for key,value in MODELS.items()}
    if include_sales:
        model_fields.update(SALES_MODELS)
        model_fields['account.move.line']=model_fields['account.move.line']+['sale_line_ids']
    result={}
    for model,fields in model_fields.items():
        available=client.call(model,'fields_get',{'attributes':['type'],'context':context})
        if not set(fields)<=set(available):raise ExtractionError('Schema Odoo incompatible : '+model)
        rows=scan(model,fields)
        # Chaque modèle est rescanné : insertions, suppressions et modifications détectées.
        check=scan(model,['id','company_id','write_date'])
        if [(r['id'],r['write_date']) for r in rows]!=[(r['id'],r['write_date']) for r in check]:
            raise ExtractionError('Les sources Odoo ont change pendant l extraction.')
        result[model]=rows
    # Le contrôle final couvre aussi les changements entre modèles.
    for model,rows in result.items():
        check=scan(model,['id','company_id','write_date'])
        if [(r['id'],r['write_date']) for r in rows]!=[(r['id'],r['write_date']) for r in check]:
            raise ExtractionError('Extraction Odoo non stable.')
    return as_of,result


def money(value):
    if isinstance(value,bool):raise ExtractionError('Montant booleen invalide.')
    result=Decimal(str(value))
    if not result.is_finite() or result<0 or result!=result.quantize(Decimal('0.01')):
        raise ExtractionError('Montant non fini, negatif ou precision non supportee.')
    return format(result,'.2f')


def normalize_models(models,company_id):
    """Conserve les lignes rejetées ; une quarantaine interdit une couverture complète."""
    valid={};quarantine=[]
    for model,rows in models.items():
        valid[model]=[];seen=set()
        for i,row in enumerate(rows,1):
            try:
                if type(row.get('id')) is not int or row['id'] in seen or relation(row.get('company_id'))!=company_id:
                    raise ExtractionError('identite_invalide_ou_dupliquee')
                seen.add(row['id'])
                for field in ('amount','amount_total','price_subtotal','price_total','debit_amount_currency','credit_amount_currency'):
                    if field in row:money(abs(Decimal(str(row[field]))) if model=='account.move.line' and field in ('price_subtotal','price_total') and any(m['id']==relation(row.get('move_id')) and m.get('move_type')=='entry' and relation(m.get('company_id'))==company_id for m in models.get('account.move',[])) else row[field])
                valid[model].append(row)
            except (ValueError,ArithmeticError,TypeError) as error:
                quarantine.append(dict(entity=model,row_number=i,payload=row,reason=type(error).__name__))
    return valid,quarantine


def run_extraction(db,client,company_id,include_sales=False):
    from psycopg.types.json import Jsonb
    from .investigation import serializable
    extraction_id=uuid4()
    db.execute("INSERT INTO meta.source_extractions(extraction_id,source,company_id,status) VALUES(%s,'odoo-json2',%s,'started')",(extraction_id,str(company_id)))
    try:
        as_of,raw=extract_models(client,company_id,include_sales=include_sales)
        valid,rejected=normalize_models(raw,company_id)
        def exact(value):
            if isinstance(value,Decimal):return format(value,'f')
            if isinstance(value,dict):return {k:exact(v) for k,v in value.items()}
            if isinstance(value,list):return [exact(v) for v in value]
            return serializable(value)
        payload=exact({'models':valid,'company_id':company_id,'source_as_of':as_of,'complete':not rejected})
        with db.transaction():
            for row in rejected:
                db.execute('INSERT INTO meta.quarantined_rows(extraction_id,entity,row_number,payload,reason) VALUES(%s,%s,%s,%s,%s)',
                           (extraction_id,row['entity'],row['row_number'],Jsonb(serializable(row['payload'])),row['reason']))
            db.execute("UPDATE meta.source_extractions SET status='success',finished_at=clock_timestamp(),source_as_of=%s,row_count=%s,payload=%s,payload_sha256=%s WHERE extraction_id=%s",
                       (as_of,sum(map(len,valid.values())),Jsonb(payload),payload_hash(payload),extraction_id))
        return dict(extraction_id=str(extraction_id),source_as_of=as_of.isoformat(),quarantined=len(rejected),complete=not rejected)
    except Exception as error:
        db.execute("UPDATE meta.source_extractions SET status='failed',finished_at=clock_timestamp(),error_code=%s WHERE extraction_id=%s",(type(error).__name__,extraction_id))
        raise


def freshness(as_of,now,max_age_hours=24):
    if as_of is None:return 'inconnue'
    if as_of.tzinfo is None or now.tzinfo is None:raise ValueError('Fuseau requis.')
    age=now-as_of
    if age<timedelta(0):return 'horodatage_futur'
    return 'fraiche' if age<=timedelta(hours=max_age_hours) else 'obsolete'
