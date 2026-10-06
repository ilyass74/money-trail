"""Le DAG planifie ; le worker isolé importe et publie après contrôles."""
from datetime import datetime,timedelta,timezone
from airflow.sdk import DAG,task

with DAG(dag_id='money_trail_daily',start_date=datetime(2026,10,5,tzinfo=timezone.utc),schedule='0 6 * * *',catchup=False,
         max_active_runs=1,default_args={'retries':2,'retry_delay':timedelta(minutes=5)},tags=['finance','money-trail']) as dag:
    @task
    def import_and_publish():
        import subprocess
        subprocess.run(['/opt/moneytrail-venv/bin/python','/opt/money-trail/scripts/pipeline.py'],check=True)
    import_and_publish()
