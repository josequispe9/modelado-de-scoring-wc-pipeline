"""
DAG: pipeline_analisis_determinista

Análisis determinista de transcripciones — CPU, solo Gaspar.
Detecta patrones en las conversaciones (cliente molesto, contestador,
línea de empresa, número equivocado, rellamado, vinculado al titular,
ya tiene Movistar) según los scripts configurados en pipeline_params.

Triggereado desde el dashboard via:
    POST /pipeline/etapa/analisis_determinista/ejecutar
"""
from datetime import datetime

from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator

RUTA_GASPAR = r"C:\Users\qjose\Desktop\modelado de scoring WC"
PYTHON      = r"pipeline\venv\Scripts\python.exe"
SCRIPT      = r"pipeline\logica\7-analisis-de-transcripciones\analisis-determinista\analisis_determinista.py"

with DAG(
    dag_id="pipeline_analisis_determinista",
    description="Análisis determinista de transcripciones (CPU, Gaspar)",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "etapa-7", "analisis-determinista"],
) as dag:

    SSHOperator(
        task_id="analisis_determinista",
        ssh_conn_id="ssh_gaspar",
        command=f'cd /d "{RUTA_GASPAR}" && "{PYTHON}" "{SCRIPT}"',
        conn_timeout=15,
        cmd_timeout=3600,
    )
