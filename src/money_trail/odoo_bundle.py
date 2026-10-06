"""Adapter les identités comptables Odoo, sans inventer de lien avec une vente."""
import csv
import hashlib
from collections import defaultdict
from datetime import date,datetime,timezone
from decimal import Decimal
from pathlib import Path
from .reference import HEADERS,EXTRA_HEADERS,write_json,check_reference
from .odoo_source import relation,money,ExtractionError


def currency(row):
    value=row.get('currency_id')
    if not isinstance(value,list) or len(value)!=2 or value[1] not in ('MAD','EUR','USD','GBP'):
        raise ExtractionError('Devise Odoo absente ou non supportee.')
    return value[1]


def create_bundles(payload,destination,control_on=None):
    if destination.exists() and any(destination.iterdir()):raise ValueError('Choisir un dossier de sortie vide.')
    destination.mkdir(parents=True,exist_ok=True)
    company='ODOO:'+str(payload['company_id']);control_on=control_on or date.today().isoformat()
    date.fromisoformat(control_on)
    models=payload['models'];moves={r['id']:r for r in models['account.move']}
    lines={r['id']:r for r in models['account.move.line']}
    payments={r['id']:r for r in models['account.payment']}
    scopes={}
    sale_orders={r['id']:r for r in models.get('sale.order',[])}
    sale_lines={r['id']:r for r in models.get('sale.order.line',[])}
    seen_orders=set()
    for move in moves.values():
        if move['move_type']!='out_invoice':continue
        if move.get('state')=='draft' and not move.get('invoice_date'):continue
        c=currency(move)
        if c not in scopes:scopes[c]={k:[] for k in HEADERS|EXTRA_HEADERS}
        data=scopes[c];oid='INV:'+str(move['id'])
        common=dict(company_id=company,source_system='odoo',currency=c)
        state={'posted':'posted','draft':'draft','cancel':'cancelled'}.get(move['state'])
        if state is None:raise ExtractionError('Etat de facture Odoo inconnu.')
        issued=move.get('invoice_date')
        if not issued:raise ExtractionError('Date de facture absente : traitement manuel requis.')
        explicit_orders=set()
        for lid in move['invoice_line_ids']:
            if lid not in lines:raise ExtractionError('Ligne de facture absente.')
            for sid in lines[lid].get('sale_line_ids',[]):
                if sid not in sale_lines or relation(sale_lines[sid]['company_id'])!=payload['company_id']:raise ExtractionError('Lien de vente absent ou hors entreprise.')
                order_id=relation(sale_lines[sid]['order_id'])
                if order_id not in sale_orders:raise ExtractionError('Commande explicite absente.')
                order=sale_orders[order_id]
                if relation(order['company_id'])!=payload['company_id'] or currency(order)!=c:raise ExtractionError('Commande hors perimetre.')
                explicit_orders.add(order_id)
        for order_id in sorted(explicit_orders):
            order=sale_orders[order_id]
            if (c,order_id) not in seen_orders:
                stamp=datetime.fromisoformat(order['date_order']).replace(tzinfo=timezone.utc).isoformat()
                data['orders'].append({**common,'source_id':'ORDER:'+str(order_id),'customer_ref':'PARTNER:'+str(relation(order['partner_id'])),
                    'total_amount':money(order['amount_total']),'ordered_at':stamp})
                seen_orders.add((c,order_id))
            data['invoice_order_links'].append({**common,'source_id':'INV_ORDER:'+str(move['id'])+':'+str(order_id),'invoice_id':oid,'order_id':'ORDER:'+str(order_id)})
        # Le parent direct unique est réel ; les relations multiples restent dans leur table séparée.
        parent_id='ORDER:'+str(next(iter(explicit_orders))) if len(explicit_orders)==1 else 'DOC:'+str(move['id'])
        if len(explicit_orders)!=1:data['orders'].append({**common,'source_id':'DOC:'+str(move['id']),'customer_ref':'CONTEXTE_FACTURE:'+str(move['id']),
                               'total_amount':money(move['amount_total']),'ordered_at':issued+'T00:00:00Z'})
        data['invoices'].append({**common,'source_id':oid,'order_id':parent_id,'state':state,
                                'total_amount':money(move['amount_total']),'issued_on':issued,'due_on':move.get('invoice_date_due') or ''})
        for lid in move['invoice_line_ids']:
            if lid not in lines:raise ExtractionError('Ligne de facture absente de l extraction.')
            line=lines[lid]
            if relation(line['move_id'])!=move['id'] or relation(line['company_id'])!=payload['company_id'] or currency(line)!=c:
                raise ExtractionError('Ligne de facture hors perimetre.')
            if line['display_type'] not in ('product',False,None):continue
            data['invoice_lines'].append({**common,'source_id':'LINE:'+str(lid),'invoice_id':oid,'description':line.get('name') or '',
                'quantity':str(line['quantity']),'subtotal_amount':money(line['price_subtotal']),'total_amount':money(line['price_total'])})
    complete={c:bool(payload['complete']) for c in scopes};payment_ids=defaultdict(set)
    for partial in models['account.partial.reconcile']:
        debit=lines.get(relation(partial['debit_move_id']));credit=lines.get(relation(partial['credit_move_id']))
        if not debit or not credit:
            for c in complete:complete[c]=False
            continue
        inv=moves.get(relation(debit['move_id']))
        if not inv or inv['move_type']!='out_invoice':continue
        c=currency(inv)
        if c not in scopes:continue
        common=dict(company_id=company,source_system='odoo',currency=c)
        if currency(debit)!=c or currency(credit)!=c:
            complete[c]=False;continue
        amount=money(partial['debit_amount_currency']);oid='INV:'+str(inv['id'])
        counterpart=moves.get(relation(credit['move_id']))
        if counterpart and counterpart['move_type']=='out_refund':
            if counterpart['state']!='posted':complete[c]=False;continue
            scopes[c]['credit_notes'].append({**common,'source_id':'CREDIT_ALLOC:'+str(partial['id']),'invoice_id':oid,
                'state':'posted','amount':amount,'issued_on':partial['max_date']})
        else:
            payment=payments.get(relation(credit.get('payment_id')))
            if not payment or currency(payment)!=c or payment['payment_type']!='inbound' or payment['partner_type']!='customer':
                complete[c]=False;continue
            if payment['state'] not in ('paid','in_process','posted'):
                complete[c]=False;continue
            pid='PAY:'+str(payment['id'])
            if payment['id'] not in payment_ids[c]:
                scopes[c]['erp_payments'].append({**common,'source_id':pid,'state':'confirmed','amount':money(payment['amount']),
                                                'paid_at':payment['date']+'T00:00:00Z'})
                payment_ids[c].add(payment['id'])
            scopes[c]['invoice_allocations'].append({**common,'source_id':'ALLOC:'+str(partial['id']),'invoice_id':oid,'payment_id':pid,
                                                     'amount':amount,'state':'confirmed'})
    output=[]
    for c,data in scopes.items():
        path=destination/c;path.mkdir();files=[]
        for entity,headers in (HEADERS|EXTRA_HEADERS).items():
            file=path/(entity+'.csv')
            with file.open('w',encoding='utf-8',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=headers,lineterminator='\n');writer.writeheader();writer.writerows(data[entity])
            files.append(dict(entity=entity,file=file.name,row_count=len(data[entity]),sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
        manifest=dict(contract_version='finance-v1',synthetic=False,company_id=company,currency=c,control_on=control_on,files=files,
                      invoice_coverage={key:complete[c] for key in ('invoices','erp_payments','invoice_allocations','credit_notes')},settlement_coverage=[],
                      source_extraction_id=payload.get('extraction_id'),source_as_of=payload['source_as_of'],
                      context_note='ORDER: identites de ventes explicites ; DOC: contexte de facture si aucun parent commercial unique. Les liens multiples sont dans invoice_order_links.')
        write_json(path/'manifest.json',manifest);check_reference(path);output.append(path)
    return output
