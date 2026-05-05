# Imagen para etapas LLM del pipeline (6b, 7, 8)
#
# Basada en la imagen oficial de vLLM que ya trae:
#   - CUDA toolkit correcto
#   - vLLM instalado como librería
#   - PyTorch con soporte GPU
#
# Se agrega solo lo que necesitan los scripts del pipeline:
#   psycopg2, minio, python-dotenv
#
# Build (desde la raíz del proyecto):
#   docker build -t pipeline-vllm -f pipeline\infraestructura\docker\vllm\Dockerfile .
#
# El código no se copia en la imagen — se monta como volumen en docker run.

FROM vllm/vllm-openai:latest

RUN pip install --no-cache-dir \
    psycopg2-binary \
    minio \
    python-dotenv

# Sin ENTRYPOINT ni CMD — el DAG pasa el comando explícitamente
ENTRYPOINT []
