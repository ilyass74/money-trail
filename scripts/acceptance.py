"""Lance la recette et consigne réussites, échecs, blocages et limites du MVP."""
from datetime import datetime,timezone
from pathlib import Path
import argparse
import fnmatch
import hashlib
import importlib
from importlib import metadata
import json
import os
import platform
import subprocess
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

SUITES=[
    ('unit','Contrats, provenance et règles Python',False),
    ('ui','Parcours de l’interface Streamlit',False),
    ('parse','Structure du projet dbt',False),
    ('imports','Imports PostgreSQL et concurrence',True),
    ('business','47 scénarios SQL, preuves et restauration',True),
    ('regression','Régressions du moteur précédent',True),
    ('workflow','Workflow et décisions concurrentes',True),
    ('accounts','Sessions et droits côté serveur',True),
    ('publication','Publication atomique, échecs et versions archivées',True),
    ('operations','Regles, succession, pagination, candidats et extraction Odoo',True),
]
MODULES={'ui':'test_interface_ui','parse':'test_dbt_parse','imports':'test_import_integration',
         'business':'test_acceptance_business','regression':'test_dbt_integration',
         'workflow':'test_workflow_integration','accounts':'test_interface_integration',
         'publication':'test_publication_integration','operations':'test_operations_integration'}


class RecordedResult(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.records={};self.started={}
    def startTest(self,test):
        self.started[test.id()]=time.perf_counter();super().startTest(test)
    def record(self,test,status,detail=None):
        self.records[test.id()]={'id':test.id(),'status':status,
            'seconds':round(time.perf_counter()-self.started.get(test.id(),time.perf_counter()),4),
            **({'detail':detail} if detail else {})}
    def addSuccess(self,test):self.record(test,'passed');super().addSuccess(test)
    def addFailure(self,test,err):self.record(test,'failed',self._exc_info_to_string(err,test));super().addFailure(test,err)
    def addError(self,test,err):self.record(test,'error',self._exc_info_to_string(err,test));super().addError(test,err)
    def addSkip(self,test,reason):self.record(test,'skipped',reason);super().addSkip(test,reason)
    def addSubTest(self,test,subtest,err):
        super().addSubTest(test,subtest,err)
        if err:self.record(test,'failed',self._exc_info_to_string(err,subtest))


def flatten(suite):
    for item in suite:
        if isinstance(item,unittest.TestSuite):yield from flatten(item)
        else:yield item


def child(suite_name,output):
    loader=unittest.TestLoader()
    if suite_name=='unit':suite=loader.discover(str(ROOT/'tests'))
    else:suite=loader.loadTestsFromModule(importlib.import_module(MODULES[suite_name]))
    planned=[test.id() for test in flatten(suite)]
    started=time.perf_counter()
    result=unittest.TextTestRunner(verbosity=2,resultclass=RecordedResult).run(suite)
    for identifier in planned:
        if identifier not in result.records:
            result.records[identifier]={'id':identifier,'status':'blocked','detail':'Non execute apres un echec de preparation du groupe.'}
    summary={'suite':suite_name,'tests_planned':len(planned),'tests_run':result.testsRun,
             'successful':result.wasSuccessful() and not result.skipped,
             'seconds':round(time.perf_counter()-started,3),'tests':list(result.records.values())}
    output.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if summary['successful'] else 1


def versions():
    result={'python':platform.python_version(),'system':platform.system(),'machine':platform.machine()}
    for package in ('dbt-core','dbt-postgres','psycopg','streamlit','protobuf'):
        try:result[package]=metadata.version(package)
        except metadata.PackageNotFoundError:result[package]='absent'
    return result


def code_fingerprint():
    digest=hashlib.sha256()
    for folder in ('src','scripts','tests','fixtures','dbt','ui'):
        for path in sorted((ROOT/folder).rglob('*')):
            relative=path.relative_to(ROOT)
            if path.is_file() and not {'__pycache__','target','logs'}.intersection(relative.parts):
                digest.update(str(relative).replace('\\','/').encode()+b'\0'+path.read_bytes())
    return digest.hexdigest()


def execute_group(name,title,directory):
    folder=directory/name;folder.mkdir()
    output=folder/'result.json';log=folder/'execution.log'
    print('\n'+title+'…',flush=True)
    environment={**os.environ,'PYTHONIOENCODING':'utf-8','PYTHONUNBUFFERED':'1',
                 'MT_ACCEPTANCE_ARTIFACTS':str(folder/'artifacts'),
                 'STREAMLIT_GLOBAL_DEVELOPMENT_MODE':'false','STREAMLIT_LOGGER_LEVEL':'error'}
    args=[sys.executable,str(Path(__file__).resolve()),'_child','--suite',name,'--output',str(output)]
    with log.open('w',encoding='utf-8') as stream:
        process=subprocess.Popen(args,cwd=ROOT,env=environment,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
        for line in process.stdout:
            stream.write(line);stream.flush()
            if line.startswith(('Ran ','OK','FAILED','Construction dbt','Build dbt','RESTORATION_ISOLEE_OK')):
                print(line.rstrip(),flush=True)
        returncode=process.wait()
    if output.exists():summary=json.loads(output.read_text(encoding='utf-8'))
    else:summary={'suite':name,'tests_run':0,'successful':False,'tests':[{'id':name+'.startup','status':'error','detail':'Le groupe ne s est pas termine. Consulter execution.log.'}]}
    summary['successful']=summary['successful'] and returncode==0
    summary.update(title=title,log=str(log.relative_to(directory)),log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
    count=sum(test['status']=='passed' for test in summary['tests'])
    print(('OK' if summary['successful'] else 'ECHEC OU TEST NON EXECUTE')+f' — {count} test(s) réussi(s). Journal : {log}',flush=True)
    return summary


def acceptance_matrix(groups):
    definitions=json.loads((ROOT/'fixtures/acceptance_matrix.json').read_text(encoding='utf-8'))['criteria']
    records=[test for group in groups for test in group.get('tests',[])]
    output=[]
    for definition in definitions:
        selected=[];missing=[]
        for pattern in definition['tests']:
            matching=[test for test in records if fnmatch.fnmatchcase(test['id'],pattern)]
            if matching:selected.extend(matching)
            else:missing.append(pattern)
        selected=list({row['id']:row for row in selected}.values())
        if any(row['status'] in ('failed','error') for row in selected):status='failed'
        elif missing or any(row['status'] in ('skipped','blocked') for row in selected):status='not_run'
        elif not selected:status='not_implemented'
        elif definition['remaining']:status='partial'
        else:status='validated_current_contract'
        output.append({**definition,'status':status,'test_results':[{'id':row['id'],'status':row['status']} for row in selected],
                       'tests_not_executed':missing})
    return output


def markdown_report(report):
    labels={'validated_current_contract':'Validé pour le contrat de démonstration','partial':'Partiel',
            'not_run':'Non exécuté','not_implemented':'Non réalisé','failed':'Échec'}
    lines=['# Money Trail — rapport de recette','',
      f"Exécuté : {report['generated_at']}",f"Environnement : {report['environment']['system']} / Python {report['environment']['python']}",
      f"Code contrôlé (SHA-256) : `{report['code_sha256']}`",'',
      f"Dans les groupes lancés : tests réussis **{report['counts']['passed']}** ; échecs/erreurs **{report['counts']['failed']}** ; tests non exécutés/ignorés **{report['counts']['not_run']}**.",
      f"Mode : {'PostgreSQL + dbt + interface' if report['database_requested'] else 'Sans PostgreSQL (SQL métier non exécuté)'}.",
      '','Le succès des tests exécutés ne certifie pas les fonctions encore absentes. La recette complète du MVP reste inachevée tant qu’un critère ci-dessous est partiel ou non réalisé.','',
      '| Critère | Scénario | Résultat | Reste à réaliser / vérifier |','|---|---|---|---|']
    for row in report['acceptance']:
        lines.append('| '+row['id']+' | '+row['title']+' | '+labels[row['status']]+' | '+('; '.join(row['remaining']) or '—')+' |')
    lines+=['','## Groupes exécutés','','| Groupe | Tests lancés | Réussis | Durée | Journal |','|---|---:|---:|---:|---|']
    for group in report['groups']:
        lines.append(f"| {group['title']} | {group['tests_run']} | {sum(row['status']=='passed' for row in group['tests'])} | {group.get('seconds','—')} s | {group.get('log','—')} |")
    if report.get('groups_not_executed'):
        lines+=['','Groupes non lancés : '+', '.join(report['groups_not_executed'])+'.']
    lines+=['','## Protection des données','',
      'Toutes les écritures de la recette vont dans des bases temporaires distinctes. La sauvegarde et sa restauration concernent exclusivement des données synthétiques.']
    if report.get('project_preserved') is True:lines.append('Les empreintes des tables et séquences de la base du projet sont identiques avant et après la recette.')
    elif report.get('project_preserved') is False:lines.append('La base du projet a changé pendant la recette : examiner le rapport avant de conclure. Une autre session peut avoir écrit pendant les tests.')
    else:lines.append('La conservation de la base du projet n’a pas été contrôlée dans ce mode.')
    for problem in report.get('problems',[]):lines.append('- '+problem)
    lines+=['','## Limites de la validation','',
      'AppTest contrôle les composants et les parcours avec services simulés. Les autres groupes PostgreSQL contrôlent le moteur, les preuves et les droits réels. La revue visuelle, le clavier, les données Odoo réelles et la charge ne sont pas certifiés par AppTest.',
      'Les tests de rejet utilisent volontairement des données invalides : un build dbt en échec est alors le résultat attendu. Le test passe seulement si le bon contrôle signale le bon snapshot.',
      'Les sorties détaillées des 47 scénarios sont dans `business/artifacts/observed/`. Les mesures de restauration sont dans `business/artifacts/restore/measures.json` si ce test a été exécuté.',
      '','## Sources','',
      '- Cahier des charges du projet : critères A01 à A18.',
      '- Catalogue manuel : `fixtures/acceptance_cases.json` ; code et journaux de cette exécution.',
      '- [PostgreSQL 17 — pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html).',
      '- [PostgreSQL 17 — pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).',
      '- [Streamlit — AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest).']
    return '\n'.join(lines)+'\n'


def run(database):
    now=datetime.now(timezone.utc)
    directory=ROOT/'reports'/('acceptance_'+now.strftime('%Y%m%dT%H%M%S%fZ'))
    directory.mkdir(parents=True)
    report={'generated_at':now.isoformat(),'database_requested':database,'environment':versions(),
            'code_sha256':code_fingerprint(),'groups':[],'problems':[],'project_preserved':None,'mvp_ready':False}
    before=None;config=None;database_available=False
    if database:
        try:
            import psycopg
            from money_trail.importer import local_config
            from testing_database import table_fingerprints
            config=local_config()
            with psycopg.connect(**config,autocommit=True) as db:
                with db.transaction():
                    db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                    before=table_fingerprints(db)
                    report['environment']['postgresql']=db.execute('SHOW server_version').fetchone()[0]
            database_available=True
        except Exception as error:
            report['problems'].append(f'PostgreSQL du projet inaccessible ({type(error).__name__}) : les groupes SQL ne seront pas executes.')
            print(report['problems'][-1],flush=True)
    try:
        for name,title,requires_db in SUITES:
            if requires_db and not database_available:continue
            try:report['groups'].append(execute_group(name,title,directory))
            except Exception as error:
                report['problems'].append(f'Groupe {name} interrompu ({type(error).__name__}).')
                print(report['problems'][-1],flush=True)
    finally:
        if database_available:
            try:
                with psycopg.connect(**config,autocommit=True) as db:
                    with db.transaction():
                        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                        after=table_fingerprints(db)
                report['project_preserved']=before==after
                if before!=after:report['problems'].append('Empreintes de la base du projet modifiees pendant les tests. Examiner les sessions actives.')
            except Exception as error:report['problems'].append(f'Controle final de conservation impossible ({type(error).__name__}).')
        report['acceptance']=acceptance_matrix(report['groups'])
        records=[row for group in report['groups'] for row in group['tests']]
        report['counts']={'passed':sum(row['status']=='passed' for row in records),
                          'failed':sum(row['status'] in ('failed','error') for row in records),
                          'not_run':sum(row['status'] in ('skipped','blocked') for row in records)}
        report['groups_not_executed']=[name for name,title,db in SUITES if name not in {group['suite'] for group in report['groups']}]
        required={name for name,title,requires_db in SUITES if database or not requires_db}
        completed={group['suite'] for group in report['groups']}
        report['tests_status']='passed' if (required<=completed and not report['problems']
            and all(group['successful'] for group in report['groups'])
            and (not database or database_available)) else 'failed_or_incomplete'
        (directory/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (directory/'report.md').write_text(markdown_report(report),encoding='utf-8')
    marker=('RECETTE_IMPLEMENTEE_OK' if database else 'VERIFICATIONS_LOCALES_OK_SQL_NON_EXECUTE') if report['tests_status']=='passed' else 'RECETTE_ECHEC_OU_INCOMPLETE'
    print('\n'+marker,flush=True)
    print(json.dumps({'tests':report['counts'],'report':str(directory/'report.md'),'mvp_ready':False},ensure_ascii=False,indent=2),flush=True)
    return 0 if report['tests_status']=='passed' else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['run','_child'])
    parser.add_argument('--database',action='store_true')
    parser.add_argument('--suite',choices=[row[0] for row in SUITES])
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.action=='_child':
        if not args.suite or not args.output:parser.error('--suite et --output requis pour le worker.')
        return child(args.suite,args.output)
    return run(args.database)


if __name__=='__main__':raise SystemExit(main())
