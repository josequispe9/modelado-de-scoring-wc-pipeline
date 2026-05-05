"""
DAG: pipeline_seleccionar_ganador_transcripciones

Elige el grupo ganador por audio en la etapa 6, construye el JSON de salida
formateado y lo sube a MinIO bajo transcripciones-formateadas/.
Corre solo en gaspar — no requiere GPU.

Triggereado desde el dashboard via:
    POST /pipeline/etapa/correccion_transcripciones/limpiar
"""
from datetime import datetime

from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator

RUTA_GASPAR = r"C:\Users\qjose\Desktop\modelado de scoring WC"
PYTHON      = r"pipeline\venv\Scripts\python.exe"
SCRIPT      = r"pipeline\logica\6-correccion-de-transcripciones\seleccionar_ganador.py"

with DAG(
    dag_id="pipeline_seleccionar_ganador_transcripciones",
    description="Selecciona ganador de transcripción y genera JSON formateado en MinIO",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "etapa-6b", "seleccionar-ganador-transcripciones"],
) as dag:

    SSHOperator(
        task_id="seleccionar_ganador_transcripciones",
        ssh_conn_id="ssh_gaspar",
        command=f'cd /d "{RUTA_GASPAR}" && "{PYTHON}" "{SCRIPT}"',
        conn_timeout=15,
        cmd_timeout=1800,   # 30 minutos máximo
    )
