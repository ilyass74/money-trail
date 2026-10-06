"""Money Trail — interface locale d'investigation financière."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime,timezone
from html import escape
import json
import os
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
import streamlit as st
from money_trail import ui_service as service
from money_trail.investigation import serializable,markdown_dossier
from money_trail.workflow import WorkflowError
from money_trail.local_auth import PERMISSIONS
from money_trail.presentation import LOGO,summary,pill,timeline

st.set_page_config(page_title='Money Trail · Votre contrôle financier',page_icon='◈',layout='wide')
st.markdown('<style>'+(ROOT/'ui/styles.css').read_text(encoding='utf-8')+'</style>',unsafe_allow_html=True)

LABELS={'ecart':'Écart à investiguer','calcul_bloque':'Calcul bloqué','rapproche':'Rapproché',
        'solde_en_attente':'Solde en attente','soldee':'Soldée','en_retard':'En retard',
        'surpaiement':'Surpaiement','echeance_inconnue':'Échéance inconnue','versement_en_attente':'Versement en attente','delai_a_confirmer':'Délai à confirmer',
        'open':'Ouvert','in_review':'En investigation','awaiting_validation':'À valider',
        'approved':'Proposition approuvée','rejected':'Proposition rejetée','closed':'Clos','resolved':'Résolu après contrôle','accepted_with_justification':'Accepté avec justification',
        'complete':'Sources complètes','donnees_incompletes':'Données incomplètes','periode_non_close':'Période non close',
        'source_data_review':'Revue des données sources','allocation_review':'Revue d’affectation','accounting_review':'Revue comptable'}
AMOUNTS={'invoice_amount':'Montant facturé','allocated_amount':'Paiements affectés','credit_amount':'Avoirs comptabilisés',
         'balance':'Solde restant','captured_amount':'Paiements capturés','refunded_amount':'Remboursements',
         'fees_amount':'Frais','adjustments_amount':'Ajustements signés','expected_amount':'Versement attendu',
         'received_amount':'Crédits bancaires affectés','difference':'Écart : reçu − attendu'}


ENTITIES={'invoices':'Factures','invoice_allocations':'Paiements affectés aux factures','erp_payments':'Paiements Odoo','processor_payments':'Paiements du prestataire','refunds':'Remboursements','fees':'Frais','adjustments':'Ajustements','bank_movements':'Mouvements bancaires','bank_allocations':'Versements affectés','settlement_batches':'Lots de versements','credit_notes':'Avoirs','orders':'Commandes','control_on':'Date du contrôle','due_on':'Échéance','period_start':'Début de période','period_end':'Fin de période','expected_receipt_on':'Date de réception attendue'}
NAV={'Vue d’ensemble':'Vue d’ensemble','Dossiers':'Dossiers à suivre','Détail du dossier':'Examiner un résultat','Propositions et validation':'Décisions à valider','Qualité et imports':'Sources & fiabilité','Comparaison des règles':'Historique des contrôles'}
def label(value):return LABELS.get(value,ENTITIES.get(value,value))
def money(value):
    if value is None:return 'Inconnu'
    return format(Decimal(str(value)),',.2f').replace(',',' ').replace('.',',')+' '+st.session_state.get('mt_currency','MAD')
def publication_date(value):
    stamp=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return stamp.astimezone(timezone.utc).strftime('%d/%m/%Y à %H:%M UTC')
def publication_banner(view,selected):
    publication=view.get('publication')
    if not publication:return
    date_text=publication_date(publication['published_at'])
    st.caption(f"Version validée {publication['version']} · publiée le {date_text}")
    if selected.get('is_active') is False:
        st.info('Vous consultez une version historique. Ses montants et ses preuves sont conservés.')
    health=view.get('publication_health',{})
    latest=health.get('latest_run') or {}
    if latest.get('status')=='failed':
        st.warning('Le dernier calcul a échoué : aucune nouvelle version n’a été publiée. '
                   f'Les résultats affichés restent ceux de la version validée du {date_text}.')
    elif latest.get('status')=='building':
        st.info('Un nouveau calcul est en cours ou a été interrompu. '
                'Les résultats affichés restent ceux de cette version validée.')
    imports=health.get('imports_since_publication',[])
    if any(row['status']=='failed' for row in imports):
        st.warning('Un import récent a échoué. Les résultats de cette publication restent disponibles ; '
                   'consultez le journal dans Qualité et imports.')
    elif any(row['status']=='started' for row in imports):
        st.info('Un import est en cours ou interrompu. Il n’est pas inclus dans cette publication.')
def hero(kicker,title,description):
    st.markdown(f'<div class="mt-page-head"><div class="mt-kicker">{escape(kicker)}</div><h2>{escape(title)}</h2><p>{escape(description)}</p></div>',unsafe_allow_html=True)
def frame(rows):
    st.dataframe(serializable(rows),hide_index=True,width='stretch')
def go(page,object_key=None):
    st.session_state['nav_page']=page
    if object_key:st.session_state['detail_choice']=object_key


def mutate(token,case,verb,**kwargs):
    try:
        service.action(token,case['case_id'],verb,expected_revision=case['revision'],**kwargs)
    except WorkflowError as error:st.error(str(error))
    else:
        st.session_state['flash']='Action enregistrée dans l’historique.'
        st.rerun()


def login_page():
    st.markdown('<div class="mt-topline"><div class="mt-brand">'+LOGO+'''<div><div class="mt-brand-name">Money Trail</div><div class="mt-brand-sub">Contrôle &amp; investigation financière</div></div></div><div class="mt-top-meta"><span class="mt-dot"></span> Espace de travail sécurisé</div></div>''',unsafe_allow_html=True)
    left,right=st.columns([1.55,1],gap='large')
    with left:
        st.markdown('''<div class="mt-kicker">Pour les équipes finance et opérations</div><h1 class="mt-landing-title">Rapprochez vos flux.<br><span>Expliquez chaque écart.</span></h1><p class="mt-landing-copy">Un versement différent ne dit pas, à lui seul, ce qui s’est passé. Money Trail rapproche les montants, retrouve les lignes sources et vous aide à documenter la suite de l’investigation.</p><div class="mt-audience"><span>FACTURES &amp; PAIEMENTS</span><span>VERSEMENTS &amp; BANQUE</span><span>SUIVI DES DÉCISIONS</span></div>''',unsafe_allow_html=True)
        st.markdown('''<div class="mt-preview"><div class="mt-preview-head"><div><div class="mt-preview-eyebrow">Une différence, un dossier à comprendre</div><div class="mt-preview-id">Versement LOT001</div></div><span class="mt-pill warning">À investiguer</span></div><div class="mt-preview-metrics"><div><span>Montant attendu</span><strong>880,00<small>MAD</small></strong></div><div><span>Affecté en banque</span><strong>850,00<small>MAD</small></strong></div><div><span>Écart constaté</span><strong class="gap">−30,00<small>MAD</small></strong></div></div><div class="mt-preview-formula">1 000,00 capturés − 100,00 remboursés − 20,00 de frais = 880,00 MAD attendus.</div><div class="mt-preview-note">La cause reste à établir avec les pièces du prestataire et de la banque.</div></div><div class="mt-preview-footer">Exemple issu du jeu de démonstration. Aucun montant présenté ici ne provient d’un compte réel.</div>''',unsafe_allow_html=True)
    with right:
        with st.container(key='login_card'):
            st.markdown('''<div class="mt-login-overline">Votre espace Money Trail</div><div class="mt-login-title">Reprenez vos investigations.</div><div class="mt-login-copy">Connectez-vous pour retrouver vos dossiers, examiner leurs preuves et suivre les décisions de votre équipe.</div>''',unsafe_allow_html=True)
            with st.form('login',clear_on_submit=True):
                name=st.text_input('Identifiant',placeholder='Votre identifiant')
                password=st.text_input('Mot de passe',type='password',placeholder='Votre mot de passe')
                submitted=st.form_submit_button('Se connecter',type='primary',width='stretch')
            if submitted:
                token=service.sign_in(name,password)
                if token:st.session_state['mt_session']=token;st.rerun()
                else:st.error('Identifiant ou mot de passe incorrect.')
            with st.expander('Besoin d’aide pour vous connecter ?'):
                st.write('Utilisez le compte créé lors de la préparation de votre espace. Si vous ne connaissez pas vos accès, rapprochez-vous de la personne qui administre cette instance.')
            st.markdown('''<div class="mt-login-foot">Les actions disponibles dépendent de votre rôle. Les commentaires, propositions et décisions sont rattachés au compte connecté.</div>''',unsafe_allow_html=True)
    st.markdown('''<div class="mt-feature-row"><div class="mt-feature"><div class="mt-feature-n">01 / RAPPROCHER</div><h4>Comprendre les montants</h4><p>Comparez factures et paiements, puis versements attendus et crédits bancaires, avec des règles explicites.</p></div><div class="mt-feature"><div class="mt-feature-n">02 / INVESTIGUER</div><h4>Retrouver les preuves</h4><p>Consultez les composantes du calcul et leurs lignes sources. Une donnée manquante reste visible, sans devenir un faux zéro.</p></div><div class="mt-feature"><div class="mt-feature-n">03 / DOCUMENTER</div><h4>Suivre les décisions</h4><p>Conservez commentaires, propositions et validations dans un historique, sans confondre décision et correction appliquée.</p></div></div><div class="mt-bottom"><span>Money Trail — de l’écart à l’investigation documentée.</span><span>Votre espace finance · accès contrôlé</span></div>''',unsafe_allow_html=True)


def overview(view):
    data=view['dossiers'];settlements=[d for d in data if d['kind']=='settlement']
    hero('LE POINT SUR VOS FLUX','Chaque montant a une histoire.','Repérez ce qui demande votre attention, comprenez le calcul et retrouvez les pièces qui expliquent le résultat.')
    counts={(row['object_kind'],row['status']):row['count'] for row in view.get('pagination',{}).get('summary',[])}
    def count_status(statuses):
        return sum(v for (k,status),v in counts.items() if status in statuses) if counts else sum(d['result']['status'] in statuses for d in data)
    columns=st.columns(4)
    columns[0].metric('À examiner',count_status({'ecart','en_retard','surpaiement','echeance_inconnue','delai_a_confirmer'}),help='Écarts, retards, trop-perçus ou dates à confirmer. Un signal demande une vérification ; il ne prouve pas une erreur.')
    columns[1].metric('Données à compléter',count_status({'calcul_bloque'}),help='Le calcul ne peut pas aboutir avec les sources disponibles.')
    columns[2].metric('Soldés ou rapprochés',count_status({'rapproche','soldee'}),help='Résultats soldés ou rapprochés selon les règles du contrôle sélectionné.')
    columns[3].metric('Dossiers en cours',view.get('active_cases',sum(c['workflow_status'] not in ('closed','resolved','accepted_with_justification') for c in view['cases'])),help='Travail de suivi ouvert par l’équipe. Un résultat financier peut exister sans dossier de suivi.')
    st.caption('Indicateurs du périmètre sélectionné.' if counts else 'Indicateurs calculés sur les résultats affichés sur cette page.')
    st.markdown('<div class="mt-journey"><div><b>01</b><span>Repérer<small>Ce qui mérite votre attention</small></span></div><div><b>02</b><span>Comprendre<small>Le calcul et ses justificatifs</small></span></div><div><b>03</b><span>Décider<small>Une action, une trace écrite</small></span></div></div>',unsafe_allow_html=True)
    st.markdown('<div class="mt-section-head">À examiner en priorité</div><div class="mt-section-caption">Les résultats ci-dessous appellent une vérification. Ouvrez-en un pour connaître la prochaine étape.</div>',unsafe_allow_html=True)
    priorities=[d for d in data if d['result']['status'] in ('ecart','calcul_bloque','en_retard','surpaiement','echeance_inconnue','delai_a_confirmer')]
    if not priorities:st.success('Aucun signal prioritaire parmi les résultats affichés. Vous pouvez consulter les factures et versements ci-dessous.')
    for d in priorities[:6]:
        r=d['result']
        if r['status'] not in ('ecart','calcul_bloque','en_retard','surpaiement','echeance_inconnue','delai_a_confirmer'):continue
        with st.container(border=True):
            a,b=st.columns([5,1])
            with a:
                st.markdown('<div class="mt-object-heading"><strong>'+escape(d['object_id'])+'</strong>'+pill(label(r['status']),True)+'</div><p class="mt-object-copy">'+escape(summary(d))+'</p>',unsafe_allow_html=True)
                st.caption('Sources complètes · cause à identifier' if r['status']=='ecart' else 'Compléter les sources avant de recalculer' if r['status']=='calcul_bloque' else 'Confirmer le délai contractuel' if r['status']=='delai_a_confirmer' else 'Consulter les échéances et les affectations')
            with b:st.button('Examiner →',key='open_'+d['object_id'],on_click=go,args=('Détail du dossier',d['kind']+':'+d['object_id']))
    if len(priorities)>6:
        st.caption(f'{len(priorities)-6} autre(s) résultat(s) à examiner sur cette page.')
        st.button('Voir tous les résultats',on_click=go,args=('Détail du dossier',))
    st.subheader('Versements bancaires')
    if not settlements:st.info('Aucun résultat de versement bancaire dans cette sélection. Les factures ci-dessous ne suffisent pas à confirmer la réception des fonds en banque.')
    frame([{'Lot':d['object_id'],'Attendu':money(d['result']['expected_amount']),'Reçu':money(d['result']['received_amount']),
            'Écart':money(d['result']['difference']),'Résultat':label(d['result']['status'])} for d in settlements])
    st.subheader('Factures')
    frame([{'Facture':d['object_id'],'Facturé':money(d['result']['invoice_amount']),'Affecté':money(d['result']['allocated_amount']),
            'Solde':money(d['result']['balance']),'Échéance':str(d['result']['due_on']) if d['result']['due_on'] else 'À confirmer','Résultat':label(d['result']['status'])} for d in data if d['kind']=='invoice'])


def cases_page(view):
    hero('Portefeuille des investigations','Retrouvez chaque dossier et son avancement.','Filtrez les dossiers, repérez les revues en cours et accédez aux preuves. Le résultat financier reste distinct de l’avancement du travail.')
    if not view['cases']:
        st.markdown('<div class="mt-empty"><div class="mt-empty-icon">◎</div><h3>Vos résultats sont prêts. Le suivi reste à ouvrir.</h3><p>Un dossier rassemble le responsable, les commentaires et les décisions concernant une anomalie. Examinez un résultat, ou ouvrez les dossiers des anomalies avec l’action située en bas de page.</p></div>',unsafe_allow_html=True)
        st.button('Examiner les résultats',on_click=go,args=('Détail du dossier',),type='primary')
        return
    search=st.text_input('Rechercher un dossier',placeholder='LOT001, FAC001…')
    statuses=st.multiselect('État du suivi',list(dict.fromkeys(c['workflow_status'] for c in view['cases'])),format_func=label)
    rows=[c for c in view['cases'] if search.lower() in c['object_id'].lower() and (not statuses or c['workflow_status'] in statuses)]
    if not rows:st.info('Aucun dossier ne correspond à ces filtres.');return
    frame([{'Objet':c['object_id'],'Type':'Facture' if c['object_kind']=='invoice' else 'Versement','Résultat financier':label(c['business_status']),
            'Suivi':label(c['workflow_status']),'Révision':c['revision'],'Créé par':c['created_by']} for c in rows])
    selected=st.selectbox('Dossier à ouvrir',[c['object_kind']+':'+c['object_id'] for c in rows])
    st.button('Consulter le dossier',on_click=go,args=('Détail du dossier',selected),type='primary')


def case_for(view,d):
    return next((view['case_details'][str(c['case_id'])] for c in view['cases'] if c['object_kind']==d['kind'] and c['object_id']==d['object_id'] and c.get('rule_version',d['result']['rule_version'])==d['result']['rule_version']),None)


def workflow_panel(token,user,detail):
    if not detail:st.info('Aucun suivi n’a encore été ouvert pour ce résultat. Les calculs et justificatifs restent consultables. Un administrateur peut ouvrir les dossiers des anomalies depuis « Dossiers à suivre ».');return
    case=detail['case'];status=case['workflow_status'];permissions=PERMISSIONS[user['role']]
    st.subheader('Suivi de l’investigation')
    st.write(f"**{label(status)}** · Révision {case['revision']}")
    st.caption('Responsable : '+(case.get('assigned_name') or 'Non attribué'))
    if status in ('closed','resolved','accepted_with_justification'):
        st.info('Le traitement est terminé. Le résultat financier et l’historique restent consultables.');return
    if 'assign' in permissions and st.button('Prendre ce dossier'):
        service.governance_action(token,case['case_id'],'assign',assignee=user['username'],revision=case['revision']);st.rerun()
    if status=='approved' and 'record_execution' in permissions:
        with st.form('external_action'):
            reference=st.text_input('Référence de l’action réalisée dans l’ERP')
            file=st.file_uploader('Pièce justifiant l’action',type=['pdf','png','jpg','jpeg','txt'])
            if st.form_submit_button('Enregistrer la pièce'):
                if not file:st.warning('Joignez une pièce.')
                else:
                    service.governance_action(token,case['case_id'],'record_execution',reference=reference,filename=file.name,content=file.getvalue(),revision=case['revision']);st.rerun()
        st.caption('La pièce documente une action déclarée. La résolution demande un contrôle ultérieur sur de nouvelles sources.')
        with st.form('resolve_case'):
            publication=st.text_input('Référence du contrôle réalisé après correction')
            if st.form_submit_button('Vérifier la résolution'):
                service.governance_action(token,case['case_id'],'resolve',publication_id=publication,revision=case['revision']);st.rerun()
    if 'accept_gap' in permissions:
        with st.form('accept_gap'):
            justification=st.text_area('Justification de l’acceptation de l’écart')
            if st.form_submit_button('Accepter avec justification'):
                service.governance_action(token,case['case_id'],'accept_gap',note=justification,revision=case['revision']);st.rerun()
    if status in ('open','rejected') and 'start' in permissions:
        with st.form('start_case'):
            note=st.text_input('Motif de début ou de reprise')
            if st.form_submit_button('Commencer la revue',type='primary'):mutate(token,case,'start',note=note)
    if 'comment' in permissions:
        with st.form('comment_case',clear_on_submit=True):
            note=st.text_area('Ajouter un commentaire',placeholder='Pièce demandée, vérification effectuée, point à clarifier…')
            if st.form_submit_button('Enregistrer le commentaire'):mutate(token,case,'comment',note=note)
    if status=='in_review' and 'propose' in permissions:
        with st.form('propose_case'):
            kind=st.selectbox('Type de proposition',['source_data_review','allocation_review','accounting_review'],format_func=label)
            description=st.text_area('Proposition')
            justification=st.text_area('Justification et pièces')
            evidence=case['evidence']['line_evidence'];ids=list(dict.fromkeys(row['record_id'] for row in evidence))
            names={row['record_id']:f"{row['entity']} / {row['source_id']}" for row in evidence}
            refs=st.multiselect('Lignes citées',ids,format_func=lambda value:names[value])
            if st.form_submit_button('Soumettre à validation',type='primary'):
                mutate(token,case,'propose',proposal_type=kind,description=description,justification=justification,record_ids=refs)
        st.caption('La soumission crée une proposition. Elle ne modifie aucun montant ni aucune écriture comptable.')
    if status=='awaiting_validation':
        pending=[p for p in detail['proposals'] if p['decision'] is None]
        if pending:
            proposal=pending[0]
            st.markdown(f"**Proposition {proposal['proposal_number']} · {label(proposal['proposal_type'])}**")
            st.write(proposal['description']);st.write(proposal['justification']);st.caption('Proposée par '+proposal['proposed_by'])
            if user['username'].casefold()==proposal['proposed_by'].casefold():st.info('Une autre personne doit examiner votre proposition.')
            elif 'approve' in permissions:
                with st.form('decide_case'):
                    decision=st.radio('Décision',['approve','reject'],format_func=lambda v:'Approuver' if v=='approve' else 'Rejeter')
                    note=st.text_area('Motif de décision')
                    if st.form_submit_button('Enregistrer la décision',type='primary'):mutate(token,case,decision,note=note)
            else:st.info('La proposition attend un compte autorisé à valider.')
    if status in ('approved','rejected') and 'close' in permissions:
        with st.form('close_case'):
            note=st.text_area('Conclusion administrative')
            if st.form_submit_button('Clore le dossier'):mutate(token,case,'close',note=note)
        st.caption('La clôture conserve le résultat financier d’origine ; elle ne certifie pas une résolution comptable.')


def detail_page(view,token,user):
    index={d['kind']+':'+d['object_id']:d for d in view['dossiers']}
    if st.session_state.get('detail_choice') not in index:st.session_state['detail_choice']=next(iter(index))
    selected=st.selectbox('Résultat à examiner',list(index),key='detail_choice',format_func=lambda key:index[key]['object_id'])
    d=index[selected];r=d['result'];e=d['explanation'];detail=case_for(view,d)
    hero('Investigation · '+label(r['status']),d['object_id'],summary(d))
    st.caption(f"{r['company_id']} · {r['currency']} · Contrôle du {r['control_on']} · {label(r['quality'])}")
    if r['status']=='calcul_bloque':st.warning('Le calcul reste bloqué. Les montants inconnus ne sont pas remplacés par zéro.')
    if d['kind']=='invoice':
        cols=st.columns(3)
        for col,key in zip(cols,['invoice_amount','allocated_amount','balance']):col.metric(AMOUNTS[key],money(r[key]))
        st.write('**Échéance :**',str(r['due_on']) if r['due_on'] else 'Inconnue')
    else:
        cols=st.columns(3)
        for col,key in zip(cols,['expected_amount','received_amount','difference']):col.metric(AMOUNTS[key],money(r[key]))
        st.write('**Réception attendue :**',str(r['expected_receipt_on']) if r['expected_receipt_on'] else 'Inconnue')
    tabs=st.tabs(['Comprendre le calcul','Preuves sources','Actions et historique'])
    with tabs[0]:
        st.subheader('Comment le montant est obtenu')
        st.write(e['formula'])
        st.markdown('<div class="mt-equation">'+escape(e['worked_calculation'])+'</div>',unsafe_allow_html=True)
        if d['kind']=='settlement':
            pieces=[('Paiements capturés','captured_amount'),('− Remboursements','refunded_amount'),('− Frais','fees_amount'),('+ Ajustements signés','adjustments_amount')]
            st.markdown('<div class="mt-rail">'+''.join('<div class="mt-rail-card"><span>'+escape(title)+'</span><strong>'+escape(money(r[key]))+'</strong></div>' for title,key in pieces)+'</div>',unsafe_allow_html=True)
        frame([{'Composante':AMOUNTS.get(key,key),'Montant':money(value)} for key,value in e['values'].items()])
        st.subheader('La prochaine vérification utile')
        if e['suggested_checks']:
            for i,check in enumerate(e['suggested_checks'],1):st.write(f'{i}. {check}')
        else:st.success('Aucune vérification supplémentaire n’est proposée pour ce résultat rapproché.')
        if e['missing_sources']:st.warning('Sources manquantes : '+', '.join(e['missing_sources']))
        if r.get('cause')=='non_identifiee':st.info('La cause de l’écart reste non identifiée. Le calcul constate une différence ; il n’en prouve pas l’origine.')
        st.subheader('Périmètre du calcul')
        frame([{'Repère':label(key),'Valeur':str(value)} for key,value in e['date_facts'].items()])
    with tabs[1]:
        st.subheader('Lignes reliées au résultat')
        rows=d['line_evidence']
        frame([{'Source':label(row['entity']),'Identifiant':row['source_id'],'Fichier':row['source_filename'],
                'Ligne de données':row['data_row_number'],'Montant source':money(row['raw_payload'].get('amount',row['raw_payload'].get('total_amount'))),
                'Contribution':'Contexte' if row['role']=='context' else 'Incluse' if row['included_in_observed_sum'] else 'Exclue',
                'Motif d’exclusion':' '.join(row.get('exclusion_reasons',[]))} for row in rows])
        st.caption('Les paiements parents et mouvements bancaires servent de contexte ; ils ne sont pas additionnés une seconde fois.')
        st.subheader('Couverture déclarée des sources')
        coverage=d['source_coverage']
        frame([{'Source':label(key),'Couverture':'Complète' if value else 'Incomplète'} for key,value in coverage.items()] if isinstance(coverage,dict)
              else [{'Source':label(c['entity']),'Couverture':'Complète' if c['complete'] else 'Incomplète','Preuve':c['evidence']} for c in coverage])
        with st.expander('Identifiants et empreintes de traçabilité'):
            st.json(serializable({'snapshot':d['snapshot'],'règle':r['rule_version'],'build_dbt':d['dbt_build_evidence']}))
            st.json(serializable(rows))
        a,b=st.columns(2)
        a.download_button('Télécharger le dossier JSON',json.dumps(serializable(d),ensure_ascii=False,indent=2),file_name='dossier.json',mime='application/json')
        b.download_button('Télécharger l’explication',markdown_dossier(d),file_name='explication.md',mime='text/markdown')
    with tabs[2]:
        if d['kind']=='settlement' and st.button('Chercher des crédits candidats'):
            candidates=service.candidates(token,str(d['snapshot']['batch_id']),view['publication']['publication_id'],d['object_id'])
            st.caption('Propositions à vérifier : aucune affectation automatique. Un montant identique ne confirme pas une identité.')
            if candidates:frame(candidates)
            else:st.info('Aucun candidat disponible dans le périmètre et la fenêtre de dates.')
        workflow_panel(token,user,detail)
        if detail:
            if detail.get('successions'):
                st.subheader('Dossiers liés à cette revue')
                frame(detail['successions'])
                st.caption('Les décisions du dossier précédent restent conservées. Cette revue possède son propre état.')
            st.subheader('Le fil de l’investigation')
            st.markdown(timeline(detail['events']),unsafe_allow_html=True)
            if detail['proposals']:
                st.subheader('Propositions conservées')
                for p in detail['proposals']:
                    with st.expander(f"Proposition {p['proposal_number']} · {label(p['decision']) if p['decision'] else 'En attente'}"):
                        st.write(p['description']);st.write(p['justification'])
                        st.write('Proposée par : '+p['proposed_by'])
                        if p['decision_note']:st.write('Décision : '+p['decision_note'])


def validation_page(view,token,user):
    hero('Revue des propositions','Une décision qui garde sa justification.','Lisez la proposition, examinez les pièces du dossier, puis enregistrez une décision motivée avec un compte autorisé à valider.')
    pending=[c for c in view['cases'] if c['workflow_status']=='awaiting_validation']
    if not pending:
        st.markdown('''<div class="mt-empty"><div class="mt-empty-icon">✓</div><h3>Aucune proposition à examiner pour ce contrôle.</h3><p>Les investigations se poursuivent dans les dossiers. Dès qu’une proposition est soumise, elle apparaît ici pour une revue motivée.</p></div>''',unsafe_allow_html=True)
        st.button('Consulter les dossiers',on_click=go,args=('Dossiers',))
        return
    selected=st.selectbox('Proposition à examiner',[str(c['case_id']) for c in pending],format_func=lambda key:view['case_details'][key]['case']['object_id'])
    detail=view['case_details'][selected]
    st.button('Voir les preuves du dossier',on_click=go,args=('Détail du dossier',detail['case']['object_kind']+':'+detail['case']['object_id']))
    workflow_panel(token,user,detail)


def imports_page(view):
    hero('Sources et couverture','Comprendre la fiabilité de chaque calcul.','Examinez ce qui a été reçu et la couverture déclarée pour chaque lot. Un fichier présent peut couvrir certains versements et laisser les autres incomplets.')
    files=view['dossiers'][0]['source_files']
    frame([{'Source':label(f['entity']),'Fichier':f['source_filename'],'Lignes reçues':f['row_count']} for f in files])
    st.subheader('Couverture des versements')
    frame([{'Lot':d['object_id'],'Source':label(c['entity']),'Couverture':'Complète' if c['complete'] else 'Incomplète','Preuve':c['evidence']}
           for d in view['dossiers'] if d['kind']=='settlement' for c in d['source_coverage']])
    if view.get('extractions'):
        st.subheader('Extractions et fraîcheur des sources')
        frame([{'Source':r.get('source','—'),'Dernière lecture':r.get('source_as_of') or 'Date inconnue','État':{'complete':'Terminée','success':'Réussie','failed':'Échec','started':'En cours'}.get(r.get('status'),r.get('status','—')),'Lignes reçues':r.get('row_count'),'Lignes à vérifier':r.get('quarantined_rows')} for r in view['extractions']])
        st.caption('La fraîcheur utilise un seuil de 24 heures. Une date inconnue reste inconnue ; les lignes rejetées restent en quarantaine.')
    st.subheader('Tentatives associées à ce chargement')
    frame([{'État':{'success':'Réussi','failed':'Échec','started':'En cours'}.get(r.get('status'),r.get('status','—')),'Début':r.get('started_at'),'Fin':r.get('finished_at'),'Lignes importées':r.get('inserted_records')} for r in view['attempts']])
    if view['unassigned_attempts']:
        st.subheader('Tentatives sans lot confirmé')
        st.caption('Ces tentatives concernent l’ensemble des imports ; elles ne sont pas rattachées au chargement sélectionné.')
        frame([{'Import':r.get('dataset_label','—'),'État':{'failed':'Échec','started':'En cours'}.get(r.get('status'),r.get('status','—')),'Début':r.get('started_at')} for r in view['unassigned_attempts']])
    with st.expander('Preuves du calcul publié et journal des tentatives'):
        st.json(serializable({'publication':view.get('publication'),'build':view['build'],
                              'tentatives':view.get('publication_health',{}),'sources':files,'imports':view['attempts'],'extractions':view.get('extractions',[])}))


def main():
    oidc=os.environ.get('MT_AUTH_MODE','local')=='oidc'
    if oidc:
        if not st.user.is_logged_in:
            st.session_state.pop('mt_session',None)
            hero('Money Trail','Votre espace finance sécurisé.','Connectez-vous avec votre compte professionnel pour consulter les résultats et les preuves autorisées.')
            st.button('Se connecter avec le compte professionnel',on_click=st.login);return
        if not st.session_state.get('mt_session'):
            st.session_state['mt_session']=service.oidc_session(st.user.get('iss'),st.user.get('sub'))
    token=st.session_state.get('mt_session')
    user=service.session_user(token) if token else None
    if not user:
        st.session_state.pop('mt_session',None)
        if oidc:st.logout();return
        login_page();return
    with st.sidebar:
        st.markdown('<div class="mt-sidebar-brand">'+LOGO+'<div><strong>Money Trail</strong><span>Votre espace de contrôle</span></div></div>',unsafe_allow_html=True)
        role={'admin':'Administrateur','analyst':'Analyste','reviewer':'Validateur','viewer':'Lecteur'}.get(user['role'],user['role'])
        st.markdown('<div class="mt-account">'+escape(user['username'])+'<span>'+escape(role)+'</span></div>',unsafe_allow_html=True)
        choices=['Vue d’ensemble','Dossiers','Détail du dossier','Propositions et validation','Qualité et imports','Comparaison des règles']
        page=st.radio('Navigation',choices,key='nav_page',format_func=lambda v:NAV[v],label_visibility='collapsed')
        batches=service.snapshots(token)
        if not batches:st.info('Aucune version validée disponible. Exécutez la préparation des publications.');return
        lookup={(str(row.get('publication_id',''))+':'+str(row['batch_id'])):row for row in batches}
        def choice_label(key):
            row=lookup[key]
            prefix=f"Version {row['version']} · " if 'version' in row else ''
            return prefix+'contrôle '+str(row['control_on'])
        selection=st.selectbox('Version des résultats',list(lookup),format_func=choice_label)
        selected=lookup[selection];batch_id=str(selected['batch_id'])
        st.caption(selected['company_id']+' · '+selected['currency'])
        st.caption('Les montants correspondent à cette version du contrôle.')
        if st.button('Actualiser'):st.rerun()
        if st.button('Se déconnecter'):
            service.sign_out(token);st.session_state.clear()
            if oidc:st.logout()
            st.rerun()
    if 'flash' in st.session_state:st.success(st.session_state.pop('flash'))
    if st.session_state.get('_mt_selected')!=selection:
        st.session_state.pop('detail_choice',None);st.session_state['page_number']=1
        st.session_state['_mt_selected']=selection
    st.session_state['mt_currency']=selected['currency']
    publication_id=selected.get('publication_id')
    with st.sidebar:
        with st.expander('Affiner les résultats',expanded=False):
            server_search=st.text_input('Rechercher dans tous les résultats',key='server_search')
            server_statuses=st.multiselect('Résultat financier',['ecart','calcul_bloque','rapproche','solde_en_attente','soldee','en_retard','surpaiement','echeance_inconnue','versement_en_attente','delai_a_confirmer'],format_func=label,key='server_statuses')
            server_kind=st.selectbox('Type de résultat',['Tous','Facture','Versement'],key='server_kind')
            min_amount=st.text_input('Montant connu minimum',key='min_amount')
            max_amount=st.text_input('Montant connu maximum',key='max_amount')
            assigned=st.text_input('Responsable (identifiant)',key='assigned_filter')
            server_sort=st.selectbox('Trier les résultats',['Identifiant','Montant décroissant'],key='server_sort')
            page_size=st.selectbox('Résultats par page',[25,50,100],key='page_size')
            page_number=st.number_input('Page',min_value=1,step=1,key='page_number')
    query=dict(limit=page_size,offset=(page_number-1)*page_size,search=server_search,statuses=server_statuses)
    try:
        for key,value in [('min_amount',min_amount),('max_amount',max_amount)]:
            if value:
                amount=Decimal(value.replace(',','.'))
                if not amount.is_finite():raise ValueError('Montant non fini')
                query[key]=str(amount)
    except (ValueError,ArithmeticError):st.warning('Indiquez un montant numérique dans les filtres.');return
    query.update(kind={'Tous':None,'Facture':'invoice','Versement':'settlement'}[server_kind],assigned=assigned or None,sort='amount' if server_sort=='Montant décroissant' else 'object')
    if page=='Propositions et validation':query['workflow_statuses']=['awaiting_validation']
    if page=='Détail du dossier' and st.session_state.get('detail_choice'):
        kind,oid=st.session_state['detail_choice'].split(':',1)
        query.update(kind=kind,object_id=oid,offset=0,search='',statuses=[],min_amount=None,max_amount=None,assigned=None)
    view=service.load_snapshot(token,batch_id,publication_id,page=query)
    st.markdown('<div class="mt-topline"><div class="mt-top-meta"><span class="mt-dot"></span> '+escape(selected['company_id'])+' · '+escape(selected['currency'])+'</div><div class="mt-top-meta">Contrôle du '+escape(str(selected['control_on']))+'</div></div>',unsafe_allow_html=True)
    publication_banner(view,selected)
    if view.get('pagination'):
        p=view['pagination'];st.caption(f"{p['total']} résultat(s) · page {page_number} · affichage limité à {page_size}")
    if view['dossiers']:
        import csv,io
        export=io.StringIO(newline='');fields=['kind','object_id','company_id','currency','control_on','rule_version','status','balance','expected_amount','received_amount','difference']
        writer=csv.DictWriter(export,fieldnames=fields);writer.writeheader()
        for d in view['dossiers']:
            r=serializable(d['result']);writer.writerow({key:(d[key] if key in ('kind','object_id') else r.get(key,'')) for key in fields})
        st.download_button('Exporter cette page filtrée',export.getvalue(),file_name='money-trail-resultats.csv',mime='text/csv')
    if not view['dossiers'] and page=='Propositions et validation':
        validation_page(view,token,user);return
    if not view['dossiers']:
        st.info('Aucun résultat sur cette page. Modifiez les filtres ou revenez à la page 1.');return
    if page=='Vue d’ensemble':overview(view)
    elif page=='Dossiers':cases_page(view)
    elif page=='Détail du dossier':detail_page(view,token,user)
    elif page=='Propositions et validation':validation_page(view,token,user)
    elif page=='Comparaison des règles':
        hero('Historique des règles','Comparer deux calculs sur les mêmes sources.','Chaque comparaison conserve les résultats avant et après, la tolérance et les changements de statut.')
        comparisons=view.get('comparisons',[])
        if not comparisons:st.info('Aucun changement de règle à comparer pour ce contrôle. Les comparaisons apparaîtront lorsqu’un nouveau calcul sera effectué sur les mêmes sources avec une règle différente.')
        for row in comparisons:
            with st.expander(row['object_id']+' · '+row['object_kind']):st.json(row['comparison'])
    else:imports_page(view)
    if user['role']=='admin':
        with st.expander('Ouvrir les dossiers des nouvelles anomalies',expanded=page=='Dossiers' and not view['cases']):
            st.caption('Les dossiers existants et leur historique sont conservés.')
            if st.button('Synchroniser les dossiers'):
                result=service.synchronize(token,batch_id,publication_id);st.session_state['flash']=f"{result['created']} dossier(s) créé(s), {result['existing']} conservé(s).";st.rerun()


try:main()
except WorkflowError as error:st.error(str(error))
except Exception as error:
    st.error(f'Chargement impossible ({type(error).__name__}). Vérifiez PostgreSQL et les étapes de préparation dans PowerShell.')
