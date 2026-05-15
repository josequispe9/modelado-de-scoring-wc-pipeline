"""
DAG: pipeline_normalizacion

Normaliza los audios pendientes en las 3 PCs en paralelo.
Cada PC lee su propia clave en pipeline_params (normalizacion_G/M/B)
para obtener sus params de ffmpeg y el grupo de carpeta destino en MinIO.

Triggereado manualmente desde el dashboard via:
    POST /pipeline/etapa/normalizacion/ejecutar
"""
import os
from datetime import datetime

import psycopg2
from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator


def _leer_num_instancias() -> dict:
    """Lee num_instancias por PC desde pipeline_params. Si falla, usa 1 en todas."""
    defaults = {"G": 1, "M": 1, "B": 1}
    try:
        db_url = os.environ["SCORING_DB_URL"].replace("postgresql+psycopg2://", "postgresql://")
        with psycopg2.connect(db_url) as conn:
            with conn.cursor() as cur:
                for cuenta in ("G", "M", "B"):
                    cur.execute(
                        "SELECT valor FROM pipeline_params WHERE clave = %s",
                        (f"normalizacion_{cuenta}",),
                    )
                    row = cur.fetchone()
                    if row and row[0]:
                        defaults[cuenta] = int(row[0].get("num_instancias", 1))
    except Exception:
        pass
    return defaults


_NUM_INSTANCIAS = _leer_num_instancias()

WORKERS = {
    "G": {
        "conn_id":        "ssh_gaspar",
        "ruta":           r"C:\Users\qjose\Desktop\modelado de scoring WC",
        "num_instancias": _NUM_INSTANCIAS["G"],
    },
    "M": {
        "conn_id":        "ssh_melchor",
        "ruta":           r"C:\Users\JUAN-T3\Desktop\modelado de scoring WC",
        "num_instancias": _NUM_INSTANCIAS["M"],
    },
    "B": {
        "conn_id":        "ssh_pc_franco",
        "ruta":           r"C:\Users\Bases\Desktop\modelado de scoring WC",
        "num_instancias": _NUM_INSTANCIAS["B"],
    },
}

PYTHON = r"pipeline\venv\Scripts\python.exe"
SCRIPT = r"pipeline\logica\3-normalizacion-de-audios\preprocesar_audios.py"

with DAG(
    dag_id="pipeline_normalizacion",
    description="Normaliza audios con ffmpeg en las 3 PCs en paralelo",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "etapa-3", "normalizacion"],
) as dag:

    for cuenta, cfg in WORKERS.items():
        for i in range(cfg["num_instancias"]):
            SSHOperator(
                task_id=f"normalizacion_{cuenta}_{i}",
                ssh_conn_id=cfg["conn_id"],
                command=f'cd /d "{cfg["ruta"]}" && set "MITROL_CUENTA={cuenta}" && "{PYTHON}" "{SCRIPT}"',
                conn_timeout=15,
                cmd_timeout=7200,   # 2 horas máximo
            )
