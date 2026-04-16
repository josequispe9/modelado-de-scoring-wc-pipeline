"""
Etapa 2 — Creación de registros en audio_pipeline_jobs.

Lista todos los WAV en MinIO (audios/) y crea una fila en audio_pipeline_jobs
por cada audio que todavía no tenga registro. Los metadatos se toman de los
CSV generados por la etapa 1 (audios/YYYY-MM-DD/metadatos_G/M/B.csv).

Corre solo en gaspar. Idempotente: re-ejecutar no duplica registros.

Uso:
    python creacion_de_registros.py
"""

import csv
import io
import logging
import os
import re
import psycopg2
import psycopg2.extras
from pathlib import Path
from dotenv import load_dotenv
from minio import Minio

ROOT_DIR = Path(__file__).parents[3]
load_dotenv(ROOT_DIR / ".env.tuberia")

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Clientes ─────────────────────────────────────────────────────────────────
minio_client = Minio(
    os.environ["MINIO_ENDPOINT"],
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=False,
)

MINIO_BUCKET = "modelado-de-scoring-wc"
SCORING_DB_URL = os.environ["SCORING_DB_URL"]


# ─── Helpers ──────────────────────────────────────────────────────────────────
def hms_a_segundos(valor: str) -> int | None:
    """Convierte 'HH:MM:SS' o 'MM:SS' a segundos enteros."""
    try:
        partes = valor.strip().split(":")
        if len(partes) == 3:
            return int(partes[0]) * 3600 + int(partes[1]) * 60 + int(partes[2])
        if len(partes) == 2:
            return int(partes[0]) * 60 + int(partes[1])
    except Exception:
        pass
    return None


def nombre_base(object_key: str) -> str:
    """
    Extrae el nombre base del audio sin sufijo de cuenta ni extensión.
    'audios/2026-04-14/amza90_1_260414103733673_ACD_15301_G.wav'
    → 'amza90_1_260414103733673_ACD_15301'
    """
    stem = Path(object_key).stem          # sin .wav
    return re.sub(r"_[GMB]$", "", stem)   # sin _G / _M / _B


# ─── Carga de metadatos desde CSVs ────────────────────────────────────────────
def cargar_metadatos() -> dict[str, dict]:
    """
    Descarga todos los metadatos_*.csv de MinIO y construye un dict
    keyed por nombre_base del archivo → fila del CSV.
    Si hay entradas de varias cuentas para el mismo audio, la última gana
    (el contenido es idéntico salvo el campo 'cuenta').
    """
    metadatos: dict[str, dict] = {}
    objetos = minio_client.list_objects(MINIO_BUCKET, prefix="audios/", recursive=True)

    for obj in objetos:
        if not obj.object_name.endswith(".csv"):
            continue
        log.info("Leyendo CSV: %s", obj.object_name)
        response = minio_client.get_object(MINIO_BUCKET, obj.object_name)
        contenido = response.read().decode("utf-8")
        response.close()

        reader = csv.DictReader(io.StringIO(contenido))
        for fila in reader:
            archivo = fila.get("archivo", "").strip()
            if archivo:
                metadatos[archivo] = fila

    log.info("Metadatos cargados: %d entradas", len(metadatos))
    return metadatos


# ─── Inserción ────────────────────────────────────────────────────────────────
def insertar_registro(cur, nombre: str, object_key: str, meta: dict) -> None:
    cur.execute("""
        INSERT INTO audio_pipeline_jobs (
            nombre_archivo, id_interaccion, url_fuente, cuenta,
            numero_telefono, inicio,
            agente, extension, empresa, campania, tipificacion, clase_tipificacion,
            duracion_audio_seg, duracion_conversacion_seg
        ) VALUES (
            %(nombre_archivo)s, %(id_interaccion)s, %(url_fuente)s, %(cuenta)s,
            %(numero_telefono)s, %(inicio)s,
            %(agente)s, %(extension)s, %(empresa)s, %(campania)s,
            %(tipificacion)s, %(clase_tipificacion)s,
            %(duracion_audio_seg)s, %(duracion_conversacion_seg)s
        )
        ON CONFLICT (nombre_archivo) DO NOTHING
    """, {
        "nombre_archivo":          nombre,
        "id_interaccion":          meta.get("id_interaccion", "").strip() or None,
        "url_fuente":              object_key,
        "cuenta":                  meta.get("cuenta", "").strip() or None,
        "numero_telefono":         meta.get("cliente", "").strip() or None,
        "inicio":                  meta.get("inicio", "").strip() or None,
        "agente":                  meta.get("agente", "").strip() or None,
        "extension":               meta.get("extension", "").strip() or None,
        "empresa":                 meta.get("empresa", "").strip() or None,
        "campania":                meta.get("campania", "").strip() or None,
        "tipificacion":            meta.get("tipificacion", "").strip() or None,
        "clase_tipificacion":      meta.get("clase_tipificacion", "").strip() or None,
        "duracion_audio_seg":      hms_a_segundos(meta.get("duracion_audio", "")),
        "duracion_conversacion_seg": hms_a_segundos(meta.get("duracion_total", "")),
    })


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    metadatos = cargar_metadatos()

    # Listar todos los WAV en audios/
    objetos_wav = [
        obj for obj in minio_client.list_objects(MINIO_BUCKET, prefix="audios/", recursive=True)
        if obj.object_name.endswith(".wav")
    ]
    log.info("WAV encontrados en MinIO: %d", len(objetos_wav))

    # Deduplicar por nombre base (un registro por audio, sin importar cuenta)
    audios: dict[str, str] = {}  # nombre_base → object_key
    for obj in objetos_wav:
        nb = nombre_base(obj.object_name)
        if nb not in audios:
            audios[nb] = obj.object_name

    log.info("Audios únicos a procesar: %d", len(audios))

    creados  = 0
    omitidos = 0
    sin_meta = 0

    with psycopg2.connect(SCORING_DB_URL) as conn:
        with conn.cursor() as cur:
            for nb, object_key in audios.items():
                meta = metadatos.get(nb, {})
                if not meta:
                    sin_meta += 1
                    log.warning("Sin metadatos para: %s — insertando con campos vacíos", nb)

                insertar_registro(cur, nb, object_key, meta)
                if cur.rowcount:
                    creados += 1
                else:
                    omitidos += 1

        conn.commit()

    log.info(
        "Finalizado — creados: %d | ya existían: %d | sin metadatos: %d",
        creados, omitidos, sin_meta,
    )


if __name__ == "__main__":
    main()
