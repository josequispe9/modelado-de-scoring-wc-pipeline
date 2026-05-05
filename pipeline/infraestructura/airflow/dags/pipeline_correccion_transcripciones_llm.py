"""
DAG: pipeline_correccion_transcripciones_llm

Scoring con vLLM de transcripciones — GPU, 3 PCs en paralelo.
Corre después de pipeline_correccion_transcripciones (determinista).

Cada PC corre el script dentro de un contenedor Docker con GPU (imagen pipeline-vllm).
Las 3 tareas corren en paralelo — se reparten el trabajo via SKIP LOCKED
según el grupo configurado en pipeline_params (correccion_transcripciones_llm_G/M/B).

Prerequisitos por PC:
  - Docker Desktop instalado
  - Imagen construida: docker build -t pipeline-vllm -f pipeline\\infraestructura\\docker\\vllm\\Dockerfile .
  - El modelo se descarga en el primer run y queda cacheado en el disco configurado

Conexión a Postgres:
  - Gaspar: red interna Docker (--network airflow_default → postgres:5432)
  - Melchor/Baltazar: LAN (192.168.9.115:5432, requiere portproxy activo en Gaspar)

Triggereado desde el dashboard via:
    POST /pipeline/etapa/correccion_transcripciones_llm/ejecutar
"""
from datetime import datetime

from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator

WORKERS = {
    "G": {
        "conn_id":    "ssh_gaspar",
        "ruta":       r"C:\Users\qjose\Desktop\modelado de scoring WC",
        "hf_cache":   r"D:\.cache\huggingface",
        "vllm_cache": r"D:\.cache\vllm",
        # Gaspar: Postgres accesible por red interna Docker
        "db_url":     "postgresql://scoring:scoring@postgres/scoring",
        "network":    "--network airflow_default",
    },
    "M": {
        "conn_id":    "ssh_melchor",
        "ruta":       r"C:\Users\JUAN-T3\Desktop\modelado de scoring WC",
        "hf_cache":   r"E:\.cache\huggingface",
        "vllm_cache": r"E:\.cache\vllm",
        # Melchor: Postgres en Gaspar por LAN (portproxy activo en Gaspar :5432)
        "db_url":     "postgresql://scoring:scoring@192.168.9.115:5432/scoring",
        "network":    "",
    },
    "B": {
        "conn_id":    "ssh_pc_franco",
        "ruta":       r"C:\Users\Bases\Desktop\modelado de scoring WC",
        "hf_cache":   r"J:\.cache\huggingface",
        "vllm_cache": r"J:\.cache\vllm",
        # Baltazar: igual que Melchor
        "db_url":     "postgresql://scoring:scoring@192.168.9.115:5432/scoring",
        "network":    "",
    },
}

IMAGEN  = "pipeline-vllm"
SCRIPT  = "/proyecto/pipeline/logica/6-correccion-de-transcripciones/correccion_llm.py"


def cmd_llm(cuenta: str) -> str:
    cfg = WORKERS[cuenta]
    return (
        f'docker run --rm --gpus all {cfg["network"]} '
        f'-v "{cfg["ruta"]}:/proyecto" '
        f'-v "{cfg["hf_cache"]}:/root/.cache/huggingface" '
        f'-v "{cfg["vllm_cache"]}:/root/.vllm" '
        f'--env-file "{cfg["ruta"]}\\.env.tuberia" '
        f'-e CUENTA={cuenta} '
        f'-e SCORING_DB_URL={cfg["db_url"]} '
        f'-e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True '
        f'{IMAGEN} python3 {SCRIPT}'
    )


with DAG(
    dag_id="pipeline_correccion_transcripciones_llm",
    description="Scoring LLM de transcripciones con vLLM (Docker GPU, 3 PCs en paralelo)",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "etapa-6", "correccion-transcripciones", "llm"],
) as dag:

    for cuenta in ("G", "M", "B"):
        SSHOperator(
            task_id=f"correccion_llm_{cuenta}",
            ssh_conn_id=WORKERS[cuenta]["conn_id"],
            command=cmd_llm(cuenta),
            conn_timeout=15,
            cmd_timeout=7200,   # 2 horas por PC
        )
