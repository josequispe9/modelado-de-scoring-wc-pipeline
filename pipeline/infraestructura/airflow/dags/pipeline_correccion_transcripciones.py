"""
DAG: pipeline_correccion_transcripciones

Scoring determinista de transcripciones — CPU, solo Gaspar.
Calcula métricas de WhisperX (avg_logprob, words, speaker balance)
y clasifica cada (audio, grupo) en correcto / reprocesar / invalido.

Triggereado desde el dashboard via:
    POST /pipeline/etapa/correccion_transcripciones/ejecutar
"""
from datetime import datetime

from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator

RUTA_GASPAR = r"C:\Users\qjose\Desktop\modelado de scoring WC"
PYTHON      = r"pipeline\venv\Scripts\python.exe"
SCRIPT      = r"pipeline\logica\6-correccion-de-transcripciones\correccion_determinista.py"

with DAG(
    dag_id="pipeline_correccion_transcripciones",
    description="Scoring determinista de transcripciones (CPU, Gaspar)",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "etapa-6", "correccion-transcripciones"],
) as dag:

    SSHOperator(
        task_id="correccion_determinista",
        ssh_conn_id="ssh_gaspar",
        command=f'cd /d "{RUTA_GASPAR}" && "{PYTHON}" "{SCRIPT}"',
        conn_timeout=15,
        cmd_timeout=3600,   # 1 hora máximo
    )
