"""
DAG: pipeline_analisis_llm

Análisis con LLM de transcripciones — GPU, solo Gaspar.
Carga el modelo una sola vez y ejecuta los scripts LLM configurados
en pipeline_params (por ahora: problema_senal).

Triggereado desde el dashboard via:
    POST /pipeline/etapa/analisis_llm/ejecutar
"""
from datetime import datetime

from airflow import DAG
from airflow.providers.ssh.operators.ssh import SSHOperator

RUTA_GASPAR     = r"C:\Users\qjose\Desktop\modelado de scoring WC"
CACHE_HF        = r"D:\.cache\huggingface"
CACHE_VLLM      = r"D:\.cache\vllm"
DOCKER_IMAGE    = "pipeline-vllm"
SCRIPT_DOCKER   = "/app/pipeline/logica/7-analisis-de-transcripciones/analisis-llm/analisis_llm.py"

# Comando docker equivalente al usado en pruebas-calidad-llm
# Dentro del contenedor, localhost = el container, no Gaspar.
# host.docker.internal resuelve al host en Docker Desktop para Windows.
DB_URL_DOCKER = "postgresql://scoring:scoring@host.docker.internal:5432/scoring"

DOCKER_CMD = (
    f'docker run --rm --gpus all '
    f'-v "{RUTA_GASPAR}:/app" '
    f'-v "{CACHE_HF}:/root/.cache/huggingface" '
    f'-v "{CACHE_VLLM}:/root/.cache/vllm" '
    f'-e "SCORING_DB_URL={DB_URL_DOCKER}" '
    f'{DOCKER_IMAGE} '
    f'python3 {SCRIPT_DOCKER}'
)

with DAG(
    dag_id="pipeline_analisis_llm",
    description="Análisis con LLM de transcripciones (GPU, Gaspar)",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["pipeline", "etapa-7", "analisis-llm"],
) as dag:

    SSHOperator(
        task_id="analisis_llm",
        ssh_conn_id="ssh_gaspar",
        command=DOCKER_CMD,
        conn_timeout=15,
        cmd_timeout=7200,
    )
