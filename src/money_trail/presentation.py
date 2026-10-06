"""Présentation client et libellés de l'interface ; aucun calcul métier."""
from decimal import Decimal
from html import escape

LOGO='''<svg width="40" height="40" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><rect width="48" height="48" rx="12" fill="#087f72"/><path d="M13 32V24H22V15H34M22 24H34V32" fill="none" stroke="#d5f4e8" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="13" cy="32" r="2.8" fill="#d5f4e8"/><circle cx="34" cy="15" r="2.8" fill="#d5f4e8"/></svg>'''


def money(value,currency="MAD"):
    if value is None:return 'Inconnu'
    return format(Decimal(str(value)),',.2f').replace(',',' ').replace('.',',')+' '+currency


def summary(dossier):
    r=dossier['result'];status=r['status']
    def amount(value):return money(value,r.get('currency','MAD'))
    if dossier['kind']=='settlement':
        if status=='ecart':return (f"Le versement attendu est de {amount(r['expected_amount'])}, contre {amount(r['received_amount'])} affectés en banque. "
                                  f"L’écart de {amount(r['difference'])} doit être expliqué à partir des pièces du prestataire et de la banque.")
        if status=='calcul_bloque':
            if r['quality']=='periode_non_close':return 'La période du versement n’est pas encore close. Le montant attendu pourra être calculé après sa clôture.'
            names={'fees':'frais','processor_payments':'paiements capturés','refunds':'remboursements','adjustments':'ajustements','bank_movements':'mouvements bancaires','bank_allocations':'affectations bancaires'}
            missing=', '.join(names.get(name,name) for name in dossier['explanation']['missing_sources'])
            return f"La couverture des sources est incomplète pour ce lot : {missing or 'source à confirmer'}. Le rapprochement reste bloqué jusqu’à réception et confirmation des données manquantes."
        if status=='rapproche':return f"Le montant reçu de {amount(r['received_amount'])} reste dans la tolérance déclarée par rapport au versement attendu. L’écart observé est de {amount(r['difference'])}."
        if status=='delai_a_confirmer':return 'La date de réception attendue est inconnue. Confirmez le délai contractuel avant de conclure à un retard bancaire.'
        return 'La date de réception attendue n’est pas encore atteinte. Le versement reste à suivre.'
    if status=='solde_en_attente':return f"Il reste {amount(r['balance'])} à payer. À la date de contrôle, la facture n’a pas encore dépassé son échéance."
    if status=='en_retard':return f"Un solde de {amount(r['balance'])} subsiste après l’échéance. Vérifiez les paiements et les avoirs avant de préparer une relance."
    return dossier['explanation']['summary']


def pill(text,warning=False):
    return '<span class="mt-pill'+(' warning' if warning else '')+'">'+escape(text)+'</span>'


def timeline(events):
    labels={'created':'Dossier ouvert','start':'Revue commencée','comment':'Commentaire ajouté','propose':'Proposition soumise',
            'approve':'Proposition approuvée','reject':'Proposition rejetée','close':'Dossier clos','assigned':'Responsable attribué','external_action_recorded':'Pièce d’action enregistrée','resolved':'Résolution confirmée par un nouveau contrôle','accepted_with_justification':'Écart accepté avec justification','reopened_from_source':'Nouvelle revue après changement'}
    chunks=[]
    for event in reversed(events):
        note=event['details'].get('note')
        if not note:
            if event['action']=='propose':note='Proposition n° '+str(event['details'].get('proposal_number',''))
            elif event['action']=='created':note='Le résultat financier et ses preuves ont été conservés à l’ouverture.'
            else:note='Action enregistrée dans le suivi du dossier.'
        chunks.append('<div class="mt-timeline-item"><div class="mt-timeline-top"><span>'+escape(str(event['actor']))+
                      '</span><span>Révision '+escape(str(event['revision']))+'</span></div><div class="mt-timeline-title">'+
                      escape(labels.get(event['action'],event['action']))+'</div><div class="mt-timeline-body">'+escape(str(note))+
                      '</div><div class="mt-object-meta">'+escape(str(event['occurred_at']))+'</div></div>')
    return ''.join(chunks)
