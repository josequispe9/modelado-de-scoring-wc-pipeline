"""
DAG: pipeline_normalizacion

Normaliza los audios pendientes en las 3 PCs en paralelo.
Cada PC lee su propia clave en pipeline_params (normalizacion_G/M/B)
para obtener sus params de ffmpeg y el grupo de carpeta destino en MinIO.

Triggereado manualmente desde el dashboard via:
    POST /pipeline/etapa/normalizacion/ejecutar
"""
from datetime import datetime

from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator

WORKERS = {
    "G": {
        "conn_id": "ssh_gaspar",
        "ruta":    r"C:\Users\qjose\Desktop\modelado de scoring WC",
    },
    "M": {
        "conn_id": "ssh_melchor",
        "ruta":    r"C:\Users\JUAN-T3\Desktop\modelado de scoring WC",
    },
    "B": {
        "conn_id": "ssh_pc_franco",
        "ruta":    r"C:\Users\Bases\Desktop\modelado de scoring WC",
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
        SSHOperator(
            task_id=f"normalizacion_{cuenta}",
            ssh_conn_id=cfg["conn_id"],
            command=f'cd /d "{cfg["ruta"]}" && set "MITROL_CUENTA={cuenta}" && "{PYTHON}" "{SCRIPT}"',
            conn_timeout=15,
            cmd_timeout=7200,   # 2 horas máximo
        )
