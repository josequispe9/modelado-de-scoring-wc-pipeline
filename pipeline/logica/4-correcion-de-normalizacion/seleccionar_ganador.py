"""
Etapa 4b — Selección del grupo ganador.

Para cada audio con etapa_actual='correccion_normalizacion' y sin grupo_ganador en el JSONB:
  1. Compara los scores de todos los grupos evaluados
  2. Elige el grupo con mayor score entre los clasificados como 'correcto'
     (si ninguno es correcto, elige el mejor entre 'reprocesar')
  3. Renombra el archivo ganador en MinIO quitando la subcarpeta de grupo
  4. Elimina de MinIO los archivos de los grupos perdedores (audios_procesados + audios-raw)
  5. Marca grupo_ganador en el JSONB y actualiza estado_global

Se corre manualmente después de auditar los outputs de correccion_normalizacion.py.

Uso:
    python seleccionar_ganador.py

Requiere:
    - .env.tuberia en la raíz del proyecto
    - pip install minio psycopg2-binary python-dotenv
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
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

# ─── Configuración ────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parents[3]
load_dotenv(ROOT_DIR / ".env.tuberia")

MINIO_BUCKET   = "modelado-de-scoring-wc"
SCORING_DB_URL = os.environ["SCORING_DB_URL"]

minio_client = Minio(
    os.environ["MINIO_ENDPOINT"],
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=False,
)


# ─── Audios pendientes de selección ──────────────────────────────────────────
def obtener_audios_pendientes(conn) -> list[dict]:
    """
    Retorna todos los audios con etapa_actual='correccion_normalizacion'
    que aún no tienen grupo_ganador en el JSONB.
    """
    query = """
        SELECT id, nombre_archivo, etapas,
               etapas->'normalizacion'          AS normalizacion,
               etapas->'correccion_normalizacion' AS correccion
        FROM audio_pipeline_jobs
        WHERE etapa_actual  = 'correccion_normalizacion'
          AND estado_global != 'en_proceso'
          AND NOT (etapas ? 'grupo_ganador')
        ORDER BY created_at
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query)
        return [dict(r) for r in cur.fetchall()]


# ─── Selección del ganador ────────────────────────────────────────────────────
def elegir_ganador(correccion: list[dict]) -> dict | None:
    """
    Elige la entrada con mayor score.
    Prioriza 'correcto' sobre 'reprocesar'. Ignora 'invalido'.
    """
    candidatos = [e for e in correccion if e.get("estado") in ("correcto", "reprocesar")]
    if not candidatos:
        return None

    # Prefiere correctos; dentro de cada categoría, el de mayor score
    correctos   = [e for e in candidatos if e.get("estado") == "correcto"]
    elegibles   = correctos if correctos else candidatos
    return max(elegibles, key=lambda e: e.get("score") or 0.0)


# ─── Operaciones en MinIO ─────────────────────────────────────────────────────
def copiar_y_borrar(src_key: str, dst_key: str) -> bool:
    """Copia src → dst dentro del mismo bucket y borra src."""
    try:
        minio_client.copy_object(
            MINIO_BUCKET, dst_key,
            f"{MINIO_BUCKET}/{src_key}"
        )
        minio_client.remove_object(MINIO_BUCKET, src_key)
        log.info("Movido: %s → %s", src_key, dst_key)
        return True
    except S3Error as e:
        log.error("Error moviendo %s: %s", src_key, e)
        return False


def borrar_objeto(key: str) -> None:
    try:
        minio_client.remove_object(MINIO_BUCKET, key)
        log.info("Eliminado: %s", key)
    except S3Error as e:
        log.warning("No se pudo eliminar %s: %s", key, e)


# ─── Actualización de Postgres ────────────────────────────────────────────────
def marcar_ganador(conn, audio_id: str, ganador: dict,
                   output_key_final: str, estado_final: str) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE audio_pipeline_jobs
            SET etapas        = etapas
                                || jsonb_build_object('grupo_ganador', %s::jsonb),
                estado_global = %s
            WHERE id = %s
        """, (
            json.dumps({
                "grupo":      ganador["grupo"],
                "score":      ganador.get("score"),
                "ubicacion":  {"bucket": MINIO_BUCKET, "key": output_key_final},
                "fecha":      datetime.now(timezone.utc).isoformat(),
            }),
            estado_final,
            audio_id,
        ))
    conn.commit()


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    procesados = 0
    sin_ganador = 0

    with psycopg2.connect(SCORING_DB_URL) as conn:
        audios = obtener_audios_pendientes(conn)
        log.info("Audios pendientes de selección: %d", len(audios))

        for audio in audios:
            audio_id = str(audio["id"])
            nombre   = audio["nombre_archivo"]
            corr     = audio["correccion"] or []
            norm     = audio["normalizacion"] or []

            if not corr:
                log.warning("Sin entradas en correccion_normalizacion para %s — omitiendo", nombre)
                sin_ganador += 1
                continue

            ganador = elegir_ganador(corr)
            if not ganador:
                log.warning("Ningún grupo apto para %s — todos invalidos", nombre)
                sin_ganador += 1
                continue

            grupo_ganador    = ganador["grupo"]
            src_key_ganador  = ganador.get("ubicacion", {}).get("key")
            clasificacion    = ganador.get("estado", "correcto")

            if not src_key_ganador:
                log.warning("Sin ubicacion para ganador %s [%s]", nombre, grupo_ganador)
                sin_ganador += 1
                continue

            # Path final sin subcarpeta de grupo
            partes         = src_key_ganador.split("/")
            fecha_carpeta  = partes[2] if len(partes) > 3 else datetime.now().strftime("%Y-%m-%d")
            dst_key_final  = f"audios_procesados/{clasificacion}/{fecha_carpeta}/{nombre}.wav"

            log.info("Ganador: %s → grupo=%s score=%.2f",
                     nombre, grupo_ganador, ganador.get("score") or 0.0)

            # Mover ganador a path sin grupo
            ok = copiar_y_borrar(src_key_ganador, dst_key_final)
            if not ok:
                sin_ganador += 1
                continue

            # Eliminar perdedores de audios_procesados/
            for entrada in corr:
                if entrada["grupo"] == grupo_ganador:
                    continue
                key = entrada.get("ubicacion", {}).get("key")
                if key:
                    borrar_objeto(key)

            # Eliminar perdedores de audios-raw/
            grupos_norm = {e["grupo"]: e for e in norm if isinstance(e, dict)}
            for grupo, entry in grupos_norm.items():
                if grupo == grupo_ganador:
                    continue
                key = entry.get("ubicacion", {}).get("key")
                if key:
                    borrar_objeto(key)

            marcar_ganador(conn, audio_id, ganador, dst_key_final, clasificacion)
            procesados += 1

    log.info("Finalizado — seleccionados: %d | sin ganador: %d", procesados, sin_ganador)


if __name__ == "__main__":
    main()
