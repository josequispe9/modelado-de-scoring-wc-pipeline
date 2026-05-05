"""
DAG: pipeline_seleccionar_ganador

Elige el grupo ganador para cada audio evaluado en la etapa 4.
Elimina de MinIO los audios de los grupos perdedores.
Corre solo en gaspar — no requiere GPU.

Triggereado manualmente desde el dashboard via:
    POST /pipeline/etapa/seleccionar_ganador/ejecutar
"""
from datetime import datetime

from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator

RUTA_GASPAR = r"C:\Users\qjose\Desktop\modelado de scoring WC"
PYTHON      = r"pipeline\venv\Scripts\python.exe"
SCRIPT      = r"pipeline\logica\4-correcion-de-normalizacion\seleccionar_ganador.py"

with DAG(
    dag_id="pipeline_seleccionar_ganador",
    description="Selecciona el grupo ganador por audio y elimina perdedores de MinIO",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "etapa-4b", "seleccionar-ganador"],
) as dag:

    SSHOperator(
        task_id="seleccionar_ganador",
        ssh_conn_id="ssh_gaspar",
        command=f'cd /d "{RUTA_GASPAR}" && "{PYTHON}" "{SCRIPT}"',
        conn_timeout=15,
        cmd_timeout=1800,   # 30 minutos máximo
    )
