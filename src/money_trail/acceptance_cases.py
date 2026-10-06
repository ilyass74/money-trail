"""Scénarios de recette synthétiques et attentes écrites indépendamment du SQL."""
from copy import deepcopy
import csv
import hashlib
from pathlib import Path
from .reference import ROOT, HEADERS, create_reference, read_json, write_json

CATALOG = ROOT / 'fixtures' / 'acceptance_cases.json'


def cases():
    entries = read_json(CATALOG)['cases']
    identifiers = [entry['id'] for entry in entries]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('Identifiant de scenario duplique.')
    return entries


def create_case(destination: Path, case: dict):
    """N'écrase jamais un dossier ; met à jour les empreintes des CSV modifiés."""
    manifest = create_reference(destination)
    changed = {}
    for patch in case.get('patches', []):
        entity = patch['entity']
        if entity not in HEADERS:
            raise ValueError('Entite de scenario inconnue.')
        if entity not in changed:
            with (destination / (entity + '.csv')).open(encoding='utf-8', newline='') as stream:
                changed[entity] = list(csv.DictReader(stream))
        rows = changed[entity]
        if 'append' in patch:
            rows.append(deepcopy(patch['append']))
            continue
        matching = [row for row in rows if row['source_id'] == patch['id']]
        if len(matching) != 1:
            raise ValueError('Cible de modification absente ou ambigue.')
        if patch.get('delete'):
            rows.remove(matching[0])
        else:
            matching[0].update(patch['set'])
    for entity, rows in changed.items():
        file = destination / (entity + '.csv')
        with file.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=HEADERS[entity], lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        item = next(item for item in manifest['files'] if item['entity'] == entity)
        item.update(sha256=hashlib.sha256(file.read_bytes()).hexdigest(), row_count=len(rows))
    manifest['invoice_coverage'].update(case.get('invoice_coverage', {}))
    for change in case.get('settlement_coverage', []):
        item = next(item for item in manifest['settlement_coverage']
                    if item['batch_id'] == change['batch_id'] and item['entity'] == change['entity'])
        item['complete'] = change['complete']
        item['evidence'] = 'scenario_synthetique_declare' if change['complete'] else 'source_absente_pour_ce_lot'
    if 'control_on' in case:
        manifest['control_on'] = case['control_on']
    write_json(destination / 'manifest.json', manifest)
    return manifest


def expected(case):
    """Fusion de valeurs de référence manuelles, sans calcul financier."""
    base = read_json(ROOT / 'fixtures' / 'expected_results.json')
    targets = {'invoice': {row['invoice_id']: deepcopy(row) for row in base['invoice_results']},
               'settlement': {row['batch_id']: deepcopy(row) for row in base['settlement_results']}}
    # Ces composantes viennent de la recette de référence écrite à la main.
    for object_id, row in targets['settlement'].items():
        row.update(captured_amount='1000.00', refunded_amount='100.00' if object_id in ('LOT001', 'LOT002') else '0.00',
                   fees_amount='20.00' if object_id in ('LOT001', 'LOT002') else None if object_id == 'LOT003' else '0.00',
                   adjustments_amount='0.00', quality=row.get('quality', 'complete'), cause=row.get('cause'))
    targets['invoice']['FAC001']['quality'] = 'complete'
    for kind, changes in case.get('expected', {}).items():
        for object_id, update in changes.items():
            if update is None:
                targets[kind].pop(object_id)
            else:
                key = 'invoice_id' if kind == 'invoice' else 'batch_id'
                targets[kind].setdefault(object_id, {key: object_id}).update(deepcopy(update))
                if update.get('quality') == 'complete':
                    targets[kind][object_id].pop('missing_source', None)
    return targets
