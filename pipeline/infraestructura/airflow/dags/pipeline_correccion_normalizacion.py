"""
DAG: pipeline_correccion_normalizacion

Scorea y clasifica cada audio normalizado (audios-raw/) en correcto / reprocesar / invalido.
Corre solo en gaspar — no requiere GPU, usa librosa/soundfile.

Triggereado manualmente desde el dashboard via:
    POST /pipeline/etapa/correccion_normalizacion/ejecutar
"""
from datetime import datetime

from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator

RUTA_GASPAR = r"C:\Users\qjose\Desktop\modelado de scoring WC"
PYTHON      = r"pipeline\venv\Scripts\python.exe"
SCRIPT      = r"pipeline\logica\4-correcion-de-normalizacion\correccion_normalizacion.py"

with DAG(
    dag_id="pipeline_correccion_normalizacion",
    description="Scorea audios normalizados y los clasifica en correcto/reprocesar/invalido",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "etapa-4", "correccion-normalizacion"],
) as dag:

    SSHOperator(
        task_id="correccion_normalizacion",
        ssh_conn_id="ssh_gaspar",
        command=f'cd /d "{RUTA_GASPAR}" && "{PYTHON}" "{SCRIPT}"',
        conn_timeout=15,
        cmd_timeout=3600,   # 1 hora máximo
    )
