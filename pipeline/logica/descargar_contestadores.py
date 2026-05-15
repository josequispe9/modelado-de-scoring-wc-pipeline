"""
Descarga desde MinIO todos los JSONs de transcripciones-formateadas/
cuya tipificacion corresponda a llamadas con contestador automático.

Uso:
    python descargar_contestadores.py

Salida:
    contestadores/<fecha>/<nombre>.json

Requiere:
    - .env.tuberia en la raíz del proyecto
    - pip install minio python-dotenv
"""

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from minio import Minio
from minio.error import S3Error

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parents[2]
load_dotenv(ROOT_DIR / ".env.tuberia")

MINIO_BUCKET = "modelado-de-scoring-wc"
PREFIX       = "transcripciones-formateadas/"
SALIDA_DIR   = Path(__file__).parent / "contestadores"

TIPIFICACIONES = {
    "atiende un contestador",
    "contestador",
}

minio_client = Minio(
    os.environ["MINIO_ENDPOINT"],
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=False,
)


def es_contestador(tipificacion: str | None) -> bool:
    if not tipificacion:
        return False
    return tipificacion.strip().lower() in TIPIFICACIONES


def main():
    descargados = 0
    ignorados   = 0
    errores     = 0

    objects = minio_client.list_objects(MINIO_BUCKET, prefix=PREFIX, recursive=True)

    for obj in objects:
        key = obj.object_name
        if not key.endswith(".json"):
            continue

        # Descargar en memoria
        try:
            response = minio_client.get_object(MINIO_BUCKET, key)
            data = json.loads(response.read())
        except (S3Error, json.JSONDecodeError) as e:
            log.error("Error leyendo %s: %s", key, e)
            errores += 1
            continue
        finally:
            try:
                response.close()
                response.release_conn()
            except Exception:
                pass

        tipificacion = (data.get("metadata_llamada") or {}).get("tipificacion")
        if not es_contestador(tipificacion):
            ignorados += 1
            continue

        # Guardar respetando la estructura de carpetas (fecha)
        # key: transcripciones-formateadas/2026-04-09/nombre.json
        partes     = key[len(PREFIX):]          # 2026-04-09/nombre.json
        dest       = SALIDA_DIR / partes
        dest.parent.mkdir(parents=True, exist_ok=True)

        with open(dest, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        log.info("Guardado: %s [%s]", dest.name, tipificacion)
        descargados += 1

    log.info(
        "Finalizado — descargados: %d | ignorados: %d | errores: %d",
        descargados, ignorados, errores,
    )


if __name__ == "__main__":
    main()
