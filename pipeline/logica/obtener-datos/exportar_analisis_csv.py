"""
Exporta todas las detecciones de analisis-raw en MinIO a un único CSV.

Recorre todos los JSON bajo analisis-raw/ (determinista y LLM), extrae
cada detección y genera un CSV con columnas:
    tipificacion ; id_interaccion ; linea_cliente ; duracion_llamada ; fecha_llamada

La fecha_llamada se extrae del nombre del archivo de audio (id_interaccion).

Uso:
    python exportar_analisis_csv.py [output.csv]

    Si no se especifica archivo de salida, se crea 'analisis_detecciones.csv'
    en el directorio actual.

Requiere:
    - .env.tuberia en la raíz del proyecto (3 niveles arriba)
    - pip install minio python-dotenv
"""

import csv
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from minio import Minio
from minio.error import S3Error

# ─── Paths / env ──────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parents[3]
load_dotenv(ROOT_DIR / ".env.tuberia")

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Constantes ───────────────────────────────────────────────────────────────
MINIO_BUCKET = "modelado-de-scoring-wc"
PREFIX       = "analisis-raw/"
CSV_COLUMNS  = ["tipificacion", "id_interaccion", "linea_cliente",
                "duracion_llamada", "fecha_llamada"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_minio() -> Minio:
    return Minio(
        os.environ["MINIO_ENDPOINT"],
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=False,
    )


def limpiar_linea(linea) -> str:
    """
    Limpia el número de línea del cliente:
      1. Conserva solo dígitos.
      2. Elimina prefijo '0' o '90' si comienza con ellos.
      3. Elimina la primera aparición de '15'.
      4. Valida que queden exactamente 10 dígitos; si no, retorna cadena vacía.
    """
    if not linea:
        return ""

    # 1. Solo dígitos
    num = "".join(c for c in str(linea) if c.isdigit())

    # 2. Eliminar prefijo '90' antes que '0' (orden importa)
    if num.startswith("90"):
        num = num[2:]
    elif num.startswith("0"):
        num = num[1:]

    # 3. Eliminar primera aparición de '15'
    idx = num.find("15")
    if idx != -1:
        num = num[:idx] + num[idx + 2:]

    # 4. Validar longitud
    if len(num) != 10:
        return ""

    return num


def fecha_desde_nombre(nombre: str) -> str:
    """
    Extrae la fecha del nombre del archivo de audio.
    Ejemplo: amza10_1_260406102630288_ACD_41467 → '2026-04-06'
    Retorna cadena vacía si no se puede parsear.
    """
    try:
        d = nombre.split("_")[2][:6]   # YYMMDD
        return f"20{d[:2]}-{d[2:4]}-{d[4:6]}"
    except (IndexError, ValueError):
        return ""


def listar_json_keys(client: Minio) -> list[str]:
    """Retorna las keys de todos los objetos .json bajo analisis-raw/."""
    keys = []
    objects = client.list_objects(MINIO_BUCKET, prefix=PREFIX, recursive=True)
    for obj in objects:
        if obj.object_name.endswith(".json"):
            keys.append(obj.object_name)
    return keys


def leer_json(client: Minio, key: str) -> dict | None:
    """Descarga y parsea un JSON desde MinIO. Retorna None si falla."""
    try:
        response = client.get_object(MINIO_BUCKET, key)
        data = json.loads(response.read())
        response.close()
        response.release_conn()
        return data
    except S3Error as exc:
        log.error("Error descargando %s: %s", key, exc)
        return None
    except Exception as exc:
        log.error("Error parseando %s: %s", key, exc)
        return None


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    output_path = sys.argv[1] if len(sys.argv) > 1 else "analisis_detecciones.csv"

    client = make_minio()

    log.info("Listando objetos en %s/%s ...", MINIO_BUCKET, PREFIX)
    keys = listar_json_keys(client)
    log.info("Archivos JSON encontrados: %d", len(keys))

    if not keys:
        log.warning("No se encontraron archivos. Verificar bucket y prefix.")
        return

    filas: list[dict] = []
    ids_vistos: set[tuple] = set()   # (tipificacion, id_interaccion) para deduplicar

    for i, key in enumerate(sorted(keys), 1):
        log.info("[%d/%d] Procesando: %s", i, len(keys), key)
        data = leer_json(client, key)
        if data is None:
            continue

        tipificacion = data.get("script", "")
        detecciones  = data.get("detecciones", [])

        if not isinstance(detecciones, list):
            log.warning("Campo 'detecciones' inválido en %s — saltando", key)
            continue

        for det in detecciones:
            id_interaccion   = det.get("id_interaccion", "")
            linea_cliente    = limpiar_linea(det.get("linea_cliente", ""))
            duracion_llamada = det.get("duracion_llamada", "")
            fecha_llamada    = fecha_desde_nombre(str(id_interaccion))

            clave = (tipificacion, id_interaccion)
            if clave in ids_vistos:
                log.debug("Duplicado omitido: %s / %s", tipificacion, id_interaccion)
                continue
            ids_vistos.add(clave)

            filas.append({
                "tipificacion":    tipificacion,
                "id_interaccion":  id_interaccion,
                "linea_cliente":   linea_cliente,
                "duracion_llamada": duracion_llamada,
                "fecha_llamada":   fecha_llamada,
            })

    log.info("Total de detecciones (sin duplicados): %d", len(filas))

    # Ordenar por fecha_llamada y luego tipificacion para salida legible
    filas.sort(key=lambda r: (r["fecha_llamada"], r["tipificacion"], r["id_interaccion"]))

    # utf-8-sig agrega BOM para que Excel lo reconozca correctamente
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, delimiter=";")
        writer.writeheader()
        writer.writerows(filas)

    log.info("CSV exportado: %s (%d filas)", output_path, len(filas))


if __name__ == "__main__":
    main()
