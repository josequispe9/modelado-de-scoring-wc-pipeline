"""
DAG: pipeline_descarga

Dispara la descarga de audios desde Mitrol en las 3 PCs en paralelo.
Cada PC usa su propia cuenta Mitrol (G, M, B) y sus propios parámetros
almacenados en pipeline_params (claves: descarga_G, descarga_M, descarga_B).

Triggereado manualmente desde el dashboard via:
    POST /pipeline/etapa/descarga/ejecutar

El script corre nativamente en el Windows de cada PC (Chrome visible).
Airflow usa SSHOperator para lanzarlo — el navegador queda abierto para auditar.
"""
from datetime import datetime

from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator

# ─── Configuración por PC ─────────────────────────────────────────────────────

WORKERS = {
    "G": {
        "conn_id":  "ssh_gaspar",
        "ruta":     r"C:\Users\qjose\Desktop\modelado de scoring WC",
    },
    "M": {
        "conn_id":  "ssh_melchor",
        "ruta":     r"C:\Users\JUAN-T3\Desktop\modelado de scoring WC",
    },
    "B": {
        "conn_id":  "ssh_pc_franco",
        "ruta":     r"C:\Users\Bases\Desktop\modelado de scoring WC",
    },
}

SCRIPT = r"pipeline\logica\1-descarga-de-audios\scraping_mitrol.py"
PYTHON = r"pipeline\venv\Scripts\python.exe"


def cmd_descarga(ruta: str) -> str:
    """Comando Windows (cmd.exe) para correr el script con el venv de cada PC."""
    return f'cd /d "{ruta}" && "{PYTHON}" "{SCRIPT}"'


# ─── DAG ─────────────────────────────────────────────────────────────────────

with DAG(
    dag_id="pipeline_descarga",
    description="Descarga audios desde Mitrol en gaspar (G), melchor (M) y pc-franco (B) en paralelo",
    schedule=None,       # solo ejecución manual
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "etapa-1", "descarga"],
) as dag:

    for cuenta, cfg in WORKERS.items():
        SSHOperator(
            task_id=f"descarga_{cuenta}",
            ssh_conn_id=cfg["conn_id"],
            command=cmd_descarga(cfg["ruta"]),
            conn_timeout=15,
            cmd_timeout=7200,         # 2 horas máximo por descarga
        )
