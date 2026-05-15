"""
Lista y opcionalmente borra:
  - Registros de PostgreSQL cuyo nombre_archivo contenga 'sup' o 'calidad'
  - Objetos en MinIO (cualquier carpeta, cualquier extensión) cuyo nombre de archivo contenga 'sup' o 'calidad'

Uso:
    # Solo listar (dry-run)
    python limpiar_registros_sup.py

    # Borrar de verdad
    python limpiar_registros_sup.py --borrar
"""

import argparse
import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from minio import Minio

ROOT_DIR = Path(__file__).parents[3]
load_dotenv(ROOT_DIR / ".env.tuberia")

DATABASE_URL = os.environ["SCORING_DB_URL"]
MINIO_BUCKET  = "modelado-de-scoring-wc"

minio_client = Minio(
    os.environ["MINIO_ENDPOINT"],
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=False,
)


# ─── PostgreSQL ───────────────────────────────────────────────────────────────

def stats_postgres():
    query = """
        SELECT
            COUNT(*) FILTER (WHERE duracion_audio_seg < 10)              AS "< 10s",
            COUNT(*) FILTER (WHERE duracion_audio_seg BETWEEN 10 AND 30) AS "10-30s",
            COUNT(*) FILTER (WHERE duracion_audio_seg BETWEEN 31 AND 60) AS "30s-1min",
            COUNT(*) FILTER (WHERE duracion_audio_seg BETWEEN 61 AND 300) AS "1-5min",
            COUNT(*) FILTER (WHERE duracion_audio_seg > 300)             AS "> 5min",
            COUNT(*) FILTER (WHERE duracion_audio_seg IS NULL)           AS "sin duracion",
            COUNT(*)                                                      AS total
        FROM audio_pipeline_jobs
        WHERE nombre_archivo ILIKE '%sup%' OR nombre_archivo ILIKE '%calidad%'
    """
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            cols = [d[0] for d in cur.description]
            row  = cur.fetchone()
    print("\n── Distribución por duración (registros con 'sup' o 'calidad') ──")
    for col, val in zip(cols, row):
        print(f"  {col:>15}: {val}")


def borrar_postgres():
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM audio_pipeline_jobs WHERE nombre_archivo ILIKE '%sup%' OR nombre_archivo ILIKE '%calidad%'")
            deleted = cur.rowcount
        conn.commit()
    print(f"\n  PostgreSQL: {deleted} registros eliminados.")


# ─── MinIO ────────────────────────────────────────────────────────────────────

def listar_minio_sup():
    """Devuelve lista de keys cuyo basename (sin ruta) contiene 'sup' o 'calidad'."""
    objetos = minio_client.list_objects(MINIO_BUCKET, recursive=True)
    matches = []
    for obj in objetos:
        basename = obj.object_name.split("/")[-1].lower()
        if "sup" in basename or "calidad" in basename:
            matches.append(obj.object_name)
    return matches


def stats_minio(keys):
    print(f"\n── Objetos MinIO con 'sup' o 'calidad' en el nombre: {len(keys)} ──")
    # Agrupar por carpeta raíz
    from collections import Counter
    carpetas = Counter(k.split("/")[0] for k in keys)
    for carpeta, n in sorted(carpetas.items()):
        print(f"  {carpeta:>40}: {n}")


def borrar_minio(keys):
    from minio.deleteobjects import DeleteObject
    delete_list = [DeleteObject(k) for k in keys]
    errors = list(minio_client.remove_objects(MINIO_BUCKET, iter(delete_list)))
    if errors:
        print(f"\n  MinIO: {len(keys) - len(errors)} eliminados, {len(errors)} errores:")
        for e in errors:
            print(f"    ERROR: {e}")
    else:
        print(f"\n  MinIO: {len(keys)} objetos eliminados.")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--borrar", action="store_true", help="Ejecutar el borrado real")
    args = parser.parse_args()

    # PostgreSQL
    stats_postgres()

    # MinIO
    print("\nEscaneando MinIO (puede tardar unos segundos)...")
    keys = listar_minio_sup()
    stats_minio(keys)

    if not args.borrar:
        print("\n[DRY-RUN] Pasá --borrar para ejecutar el borrado real.")
        return

    confirm = input("\n¿Confirmar borrado en PostgreSQL y MinIO? (s/N): ").strip().lower()
    if confirm != "s":
        print("Cancelado.")
        return

    borrar_postgres()
    if keys:
        borrar_minio(keys)
    else:
        print("  MinIO: nada que borrar.")

    print("\nListo.")


if __name__ == "__main__":
    main()
