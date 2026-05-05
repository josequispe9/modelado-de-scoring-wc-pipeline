"""
Etapa 4b — Selección del grupo ganador.

Para cada audio con etapa_actual='correccion_normalizacion' y sin ganador aún:
  1. Verifica que todos los grupos normalizados ya tienen su score en el JSONB
  2. Compara los scores y elige el grupo con mayor score entre los 'correcto'
     (si ninguno es correcto, elige el mejor entre 'reprocesar')
  3. Elimina de MinIO los audios normalizados de los grupos perdedores (audios-raw/)
  4. Marca ganador en etapas.correccion_normalizacion y actualiza estado_global

El audio ganador permanece en audios-raw/ — no se mueve ni duplica.
Se corre manualmente después de auditar los outputs de correccion_normalizacion.py.

Uso:
    python seleccionar_ganador.py

Requiere:
    - .env.tuberia en la raíz del proyecto
    - pip install minio psycopg2-binary python-dotenv
"""

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
    que aún no tienen ganador en el JSONB.
    """
    query = """
        SELECT id, nombre_archivo, etapas,
               etapas->'normalizacion'           AS normalizacion,
               etapas->'correccion_normalizacion' AS correccion
        FROM audio_pipeline_jobs
        WHERE etapa_actual  = 'correccion_normalizacion'
          AND estado_global != 'en_proceso'
          AND (etapas->'correccion_normalizacion'->>'ganador') IS NULL
        ORDER BY created_at
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query)
        return [dict(r) for r in cur.fetchall()]


# ─── Verificación de completitud ─────────────────────────────────────────────
def todos_los_grupos_evaluados(normalizacion: list[dict], correccion: dict) -> bool:
    """
    Verifica que todos los grupos con estado='correcto' en normalizacion
    ya tienen su entrada en correccion_normalizacion.
    """
    grupos_norm = {e["grupo"] for e in normalizacion if e.get("estado") == "correcto"}
    grupos_corr = {k for k in correccion if k != "ganador"}
    return grupos_norm <= grupos_corr


# ─── Selección del ganador ────────────────────────────────────────────────────
def elegir_ganador(correccion: dict) -> tuple[str, dict] | None:
    """
    Elige el grupo con mayor score.
    Prioriza 'correcto' sobre 'reprocesar'. Ignora 'invalido'.
    Retorna (grupo, entrada) o None si no hay candidatos.
    """
    grupos = {k: v for k, v in correccion.items() if k != "ganador"}
    candidatos = {k: v for k, v in grupos.items() if v.get("estado") in ("correcto", "reprocesar")}
    if not candidatos:
        return None

    correctos = {k: v for k, v in candidatos.items() if v.get("estado") == "correcto"}
    elegibles = correctos if correctos else candidatos
    grupo_ganador = max(elegibles, key=lambda k: elegibles[k].get("score") or 0.0)
    return grupo_ganador, elegibles[grupo_ganador]


# ─── Operaciones en MinIO ─────────────────────────────────────────────────────
def borrar_objeto(key: str) -> None:
    try:
        minio_client.remove_object(MINIO_BUCKET, key)
        log.info("Eliminado: %s", key)
    except S3Error as e:
        log.warning("No se pudo eliminar %s: %s", key, e)


# ─── Actualización de Postgres ────────────────────────────────────────────────
def marcar_ganador(conn, audio_id: str, grupo_ganador: str, estado_final: str) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE audio_pipeline_jobs
            SET etapas        = jsonb_set(
                                    etapas,
                                    '{correccion_normalizacion,ganador}',
                                    %s::jsonb
                                ),
                estado_global = %s
            WHERE id = %s
        """, (f'"{grupo_ganador}"', estado_final, audio_id))
    conn.commit()


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    procesados  = 0
    sin_ganador = 0
    incompletos = 0

    with psycopg2.connect(SCORING_DB_URL) as conn:
        audios = obtener_audios_pendientes(conn)
        log.info("Audios pendientes de selección: %d", len(audios))

        for audio in audios:
            audio_id     = str(audio["id"])
            nombre       = audio["nombre_archivo"]
            correccion   = audio["correccion"] or {}
            normalizacion = audio["normalizacion"] or []

            if not isinstance(correccion, dict):
                log.warning("Estructura inesperada en correccion_normalizacion para %s — omitiendo", nombre)
                sin_ganador += 1
                continue

            if not todos_los_grupos_evaluados(normalizacion, correccion):
                log.info("Grupos aún pendientes de evaluación para %s — omitiendo", nombre)
                incompletos += 1
                continue

            resultado = elegir_ganador(correccion)
            if not resultado:
                log.warning("Ningún grupo apto para %s — todos invalidos", nombre)
                sin_ganador += 1
                continue

            grupo_ganador, entrada_ganadora = resultado
            estado_final = entrada_ganadora.get("estado", "correcto")

            log.info("Ganador: %s → grupo=%s score=%.2f",
                     nombre, grupo_ganador, entrada_ganadora.get("score") or 0.0)

            # Eliminar perdedores de audios-raw/
            grupos_perdedores = {k: v for k, v in correccion.items()
                                 if k != "ganador" and k != grupo_ganador}
            for grupo, entrada in grupos_perdedores.items():
                key = (entrada.get("ubicacion") or {}).get("key")
                if key:
                    borrar_objeto(key)

            marcar_ganador(conn, audio_id, grupo_ganador, estado_final)
            procesados += 1

    log.info("Finalizado — seleccionados: %d | sin ganador: %d | incompletos: %d",
             procesados, sin_ganador, incompletos)


if __name__ == "__main__":
    main()
