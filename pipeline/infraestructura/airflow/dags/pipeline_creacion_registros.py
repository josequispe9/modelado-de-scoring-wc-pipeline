"""
DAG: pipeline_creacion_registros

Lista todos los WAV en MinIO (audios/) y crea una fila en audio_pipeline_jobs
por cada audio que todavía no tenga registro. Lee los metadatos de los CSV
generados por la etapa 1 (audios/YYYY-MM-DD/metadatos_G/M/B.csv).

Corre solo en gaspar. Idempotente: re-ejecutar no duplica registros.

Triggereado manualmente desde el dashboard via:
    POST /pipeline/etapa/creacion_registros/ejecutar
"""
from datetime import datetime

from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator

RUTA_GASPAR = r"C:\Users\qjose\Desktop\modelado de scoring WC"
PYTHON       = r"pipeline\venv\Scripts\python.exe"
SCRIPT       = r"pipeline\logica\2-creacion-de-registros\creacion_de_registros.py"

with DAG(
    dag_id="pipeline_creacion_registros",
    description="Crea registros en audio_pipeline_jobs para los audios nuevos en MinIO",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "etapa-2", "creacion-registros"],
) as dag:

    SSHOperator(
        task_id="creacion_registros",
        ssh_conn_id="ssh_gaspar",
        command=f'cd /d "{RUTA_GASPAR}" && "{PYTHON}" "{SCRIPT}"',
        conn_timeout=15,
        cmd_timeout=1800,   # 30 minutos máximo
    )
