"""
DAG: pipeline_correccion_transcripciones

Scoring determinista de transcripciones — CPU, solo Gaspar.
Calcula métricas de WhisperX (avg_logprob, words, speaker balance)
y clasifica cada (audio, grupo) en correcto / reprocesar / invalido.

Triggereado desde el dashboard via:
    POST /pipeline/etapa/correccion_transcripciones/ejecutar
"""
import os
from datetime import datetime

import psycopg2
from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator


def _leer_num_instancias() -> int:
    try:
        db_url = os.environ["SCORING_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")
        with psycopg2.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT valor FROM pipeline_params WHERE clave = %s",
                    ("correccion_transcripciones",),
                )
                row = cur.fetchone()
                if row and row[0]:
                    return int(row[0].get("num_instancias", 1))
    except Exception:
        pass
    return 1


_NUM_INSTANCIAS = _leer_num_instancias()

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

    for i in range(_NUM_INSTANCIAS):
        SSHOperator(
            task_id=f"correccion_determinista_{i}",
            ssh_conn_id="ssh_gaspar",
            command=f'cd /d "{RUTA_GASPAR}" && "{PYTHON}" "{SCRIPT}"',
            conn_timeout=15,
            cmd_timeout=3600,   # 1 hora máximo
        )
