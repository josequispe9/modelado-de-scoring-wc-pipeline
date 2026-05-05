"""
DAG: pipeline_transcripcion

Transcribe los audios normalizados en las 3 PCs en paralelo usando WhisperX.
Cada PC usa su venv GPU propio (env-gpu-transcripciones) y lee su propia clave
en pipeline_params (transcripcion_G, transcripcion_M, transcripcion_B) para
obtener sus params (modelo, compute_type, min/max speakers, grupo, etc.).

Las PCs del mismo grupo se reparten el trabajo a demanda usando
SELECT FOR UPDATE SKIP LOCKED — igual que la etapa 3.

Triggereado manualmente desde el dashboard via:
    POST /pipeline/etapa/transcripcion/ejecutar
"""
from datetime import datetime

from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator

# ─── Configuración por PC ─────────────────────────────────────────────────────

WORKERS = {
    "G": {
        "conn_id": "ssh_gaspar",
        "ruta":    r"C:\Users\qjose\Desktop\modelado de scoring WC",
        "python":  r"D:\env-gpu-transcripciones\Scripts\python.exe",
    },
    "M": {
        "conn_id": "ssh_melchor",
        "ruta":    r"C:\Users\JUAN-T3\Desktop\modelado de scoring WC",
        "python":  r"E:\env-gpu-transcripciones\Scripts\python.exe",
    },
    "B": {
        "conn_id": "ssh_pc_franco",
        "ruta":    r"C:\Users\Bases\Desktop\modelado de scoring WC",
        "python":  r"J:\env-gpu-transcripciones\Scripts\python.exe",
    },
}

SCRIPT = r"pipeline\logica\5-transcripcion-de-audios\transcribir_audios.py"

# ─── DAG ─────────────────────────────────────────────────────────────────────

with DAG(
    dag_id="pipeline_transcripcion",
    description="Transcribe audios con WhisperX en las 3 PCs en paralelo",
    schedule=None,       # solo ejecución manual
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "etapa-5", "transcripcion"],
) as dag:

    for cuenta, cfg in WORKERS.items():
        SSHOperator(
            task_id=f"transcripcion_{cuenta}",
            ssh_conn_id=cfg["conn_id"],
            command=(
                f'cd /d "{cfg["ruta"]}"'
                f' && set "MITROL_CUENTA={cuenta}"'
                f' && set "PATH=C:\\Users\\qjose\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\\ffmpeg-8.1-full_build\\bin;%PATH%"'
                f' && "{cfg["python"]}" "{SCRIPT}"'
            ),
            conn_timeout=15,
            cmd_timeout=14400,   # 4 horas — transcribir es lento
        )
