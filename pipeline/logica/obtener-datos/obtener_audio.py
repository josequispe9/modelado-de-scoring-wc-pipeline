"""
Consulta la info completa de un audio en Postgres por UUID o nombre_archivo.

Uso:
    python obtener_audio.py <id_o_nombre>

Devuelve un JSON con todos los campos del registro más las ubicaciones
en MinIO extraídas del JSONB de etapas para fácil referencia.
"""
import sys
import json
import os
import psycopg2
import psycopg2.extras
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[3] / ".env.tuberia", override=True)

SCORING_DB_URL = os.environ["SCORING_DB_URL"]

# Solo etapas que generan archivos físicos nuevos en MinIO
ETAPAS_CON_UBICACION = [
    "descarga",
    "normalizacion",
    "transcripcion",
    "analisis",
]


def _extraer_ubicaciones_minio(etapas: dict) -> dict:
    """Recorre el JSONB de etapas y extrae todas las keys de MinIO."""
    ubicaciones = {}

    for etapa in ETAPAS_CON_UBICACION:
        entrada = etapas.get(etapa)
        if not entrada:
            continue

        if isinstance(entrada, list):
            for item in entrada:
                if not isinstance(item, dict):
                    continue
                grupo = item.get("grupo", "?")
                key = (item.get("ubicacion") or {}).get("key")
                if key:
                    ubicaciones[f"{etapa}/{grupo}"] = key
        elif isinstance(entrada, dict):
            key = (entrada.get("ubicacion") or {}).get("key")
            if key:
                ubicaciones[etapa] = key
            for grupo, item in entrada.items():
                if not isinstance(item, dict):
                    continue
                key = (item.get("ubicacion") or {}).get("key")
                if key:
                    ubicaciones[f"{etapa}/{grupo}"] = key

    return ubicaciones


def obtener_audio(identificador: str) -> dict | None:
    """
    Busca por UUID o nombre_archivo.
    Retorna dict con todos los campos + ubicaciones_minio, o None si no existe.
    """
    import uuid as uuid_mod
    try:
        uuid_mod.UUID(identificador)
        where = "id = %s"
    except ValueError:
        where = "nombre_archivo = %s"

    with psycopg2.connect(SCORING_DB_URL) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"SELECT * FROM audio_pipeline_jobs WHERE {where}",
                (identificador,)
            )
            row = cur.fetchone()

    if not row:
        return None

    resultado = dict(row)
    # Serializar campos no-JSON
    for campo in ("id", "fecha_llamada", "created_at", "fecha_ultima_actualizacion"):
        if resultado.get(campo) is not None:
            resultado[campo] = str(resultado[campo])

    resultado["ubicaciones_minio"] = _extraer_ubicaciones_minio(resultado.get("etapas") or {})
    return resultado


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python obtener_audio.py <id_o_nombre_archivo>")
        sys.exit(1)

    datos = obtener_audio(sys.argv[1])
    if not datos:
        print(f"No se encontró audio con identificador: {sys.argv[1]}")
        sys.exit(1)

    print(json.dumps(datos, ensure_ascii=False, indent=2, default=str))
