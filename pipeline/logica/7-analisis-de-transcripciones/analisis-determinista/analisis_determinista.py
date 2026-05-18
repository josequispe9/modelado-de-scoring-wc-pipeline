"""
Etapa 7 — Análisis determinista de transcripciones.

Para cada audio elegible (con transcripción formateada disponible):
  1. Descarga el JSON de transcripción desde MinIO
  2. Ejecuta cada clasificador determinista seleccionado
  3. Acumula detecciones en memoria
  4. Al terminar todos los audios: sube un JSON de resultados por script/fecha a MinIO
  5. Actualiza el JSONB por audio en PostgreSQL
  6. Avanza etapa_actual = 'analisis', estado_global = 'correcto' (o 'error')

Uso:
    python analisis_determinista.py

Requiere:
    - .env.tuberia en la raíz del proyecto (3 niveles arriba)
    - pip install minio psycopg2-binary python-dotenv
"""

import importlib
import json
import logging
import os
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from minio import Minio
from minio.error import S3Error

# ─── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR   = SCRIPT_DIR.parents[3]

# Permite importar desde clasificadores/ usando import relativo al script
sys.path.insert(0, str(SCRIPT_DIR))

# ─── Env ──────────────────────────────────────────────────────────────────────
load_dotenv(ROOT_DIR / ".env.tuberia")

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Constantes ───────────────────────────────────────────────────────────────
MINIO_BUCKET   = "modelado-de-scoring-wc"
SCORING_DB_URL = os.environ["SCORING_DB_URL"]

from config import DEFAULTS_ANALISIS_DETERMINISTA  # noqa: E402


# ─── Clientes externos ────────────────────────────────────────────────────────
def _make_minio() -> Minio:
    return Minio(
        os.environ["MINIO_ENDPOINT"],
        access_key=os.environ["MINIO_ACCESS_KEY"],
        secret_key=os.environ["MINIO_SECRET_KEY"],
        secure=False,
    )


# ─── Parámetros ───────────────────────────────────────────────────────────────
def obtener_params() -> dict:
    """Lee pipeline_params clave 'analisis_determinista'. Usa DEFAULTS si no existe."""
    try:
        with psycopg2.connect(SCORING_DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT valor FROM pipeline_params WHERE clave = 'analisis_determinista'"
                )
                row = cur.fetchone()
        if row and row[0]:
            params = {k: v for k, v in DEFAULTS_ANALISIS_DETERMINISTA.items()}
            params.update({
                k: v for k, v in row[0].items()
                if k in DEFAULTS_ANALISIS_DETERMINISTA
            })
            log.info("Params cargados desde Postgres (analisis_determinista)")
            return params
    except Exception as exc:
        log.warning("No se pudo leer pipeline_params: %s — usando DEFAULTS", exc)
    return {k: v for k, v in DEFAULTS_ANALISIS_DETERMINISTA.items()}


# ─── Fecha desde nombre de archivo ────────────────────────────────────────────
def fecha_desde_nombre(nombre: str) -> str:
    """
    Extrae la fecha del nombre del archivo.
    Ejemplo: amza10_1_260406102630288_ACD_41467 → '2026-04-06'
    """
    try:
        d = nombre.split("_")[2][:6]  # YYMMDD
        return f"20{d[:2]}-{d[2:4]}-{d[4:6]}"
    except (IndexError, ValueError):
        return datetime.now().strftime("%Y-%m-%d")


# ─── Audios elegibles ─────────────────────────────────────────────────────────
def obtener_audios_elegibles(conn, estados: list[str]) -> list[dict]:
    """
    Retorna audios con transcripción formateada disponible y estado elegible.
    Incluye etapa_actual='analisis' para permitir re-runs.
    """
    query = """
        SELECT id, nombre_archivo,
               etapas->'correccion_transcripciones'->'ganador'->'ubicacion'->>'key'
                   AS transcripcion_key,
               etapas->'analisis'->'determinista' AS analisis_det_actual
        FROM audio_pipeline_jobs
        WHERE etapa_actual IN ('correccion_transcripciones', 'analisis')
          AND estado_global = ANY(%s)
          AND etapas->'correccion_transcripciones'->'ganador'->'ubicacion'->>'key' IS NOT NULL
        ORDER BY created_at
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, (estados,))
        return [dict(r) for r in cur.fetchall()]


# ─── JSONB — inicio de etapa por audio ────────────────────────────────────────
def marcar_inicio(conn, audio_id: str, run_id: str) -> None:
    """
    Escribe estado=en_proceso, fecha_inicio y run_id en
    etapas.analisis.determinista. Incrementa intentos.
    """
    ahora = datetime.now(timezone.utc).isoformat()
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE audio_pipeline_jobs
            SET etapas = jsonb_set(
                    etapas,
                    '{analisis,determinista}',
                    COALESCE(
                        etapas->'analisis'->'determinista',
                        '{}'::jsonb
                    ) || jsonb_build_object(
                        'estado',       'en_proceso',
                        'fecha_inicio', %s::text,
                        'run_id',       %s,
                        'intentos',     COALESCE(
                            (etapas->'analisis'->'determinista'->>'intentos')::int, 0
                        ) + 1
                    ),
                    true
                ),
                estado_global              = 'en_proceso',
                fecha_ultima_actualizacion = now()
            WHERE id = %s
        """, (ahora, run_id, audio_id))
    conn.commit()


# ─── JSONB — cierre de etapa por audio ────────────────────────────────────────
def marcar_fin(conn, audio_id: str, run_id: str, estado: str,
               scripts_ejecutados: list[str], detecciones: list[str],
               error_msg: str | None = None) -> None:
    """
    Escribe estado final, fecha_fin, scripts_ejecutados y detecciones en
    etapas.analisis.determinista. Avanza etapa_actual y estado_global.
    """
    ahora = datetime.now(timezone.utc).isoformat()
    patch = {
        "estado":            estado,
        "fecha_fin":         ahora,
        "run_id":            run_id,
        "scripts_ejecutados": scripts_ejecutados,
        "detecciones":       detecciones,
    }
    if error_msg:
        patch["error"] = error_msg

    with conn.cursor() as cur:
        cur.execute("""
            UPDATE audio_pipeline_jobs
            SET etapas = jsonb_set(
                    etapas,
                    '{analisis,determinista}',
                    COALESCE(
                        etapas->'analisis'->'determinista',
                        '{}'::jsonb
                    ) || %s::jsonb,
                    true
                ),
                etapa_actual               = 'analisis',
                estado_global              = %s,
                fecha_ultima_actualizacion = now()
            WHERE id = %s
        """, (json.dumps(patch), estado, audio_id))
    conn.commit()


# ─── Construcción del JSON de output por script/fecha ─────────────────────────
def construir_json_output(script: str, run_id: str, fecha_ejecucion: str,
                          estados_procesados: list[str],
                          total_analizados: int,
                          detecciones_lista: list[dict],
                          palabras_clave: list[str]) -> dict:
    return {
        "script":              script,
        "tipo":                "determinista",
        "run_id":              run_id,
        "fecha_ejecucion":     fecha_ejecucion,
        "estados_procesados":  estados_procesados,
        "total_analizados":    total_analizados,
        "total_detectados":    len(detecciones_lista),
        "palabras_clave":      palabras_clave,
        "detecciones":         detecciones_lista,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────
def main() -> None:
    run_id         = datetime.now().strftime("%Y%m%d_%H%M%S")
    fecha_ejecucion = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    params              = obtener_params()
    scripts_seleccionados = params["scripts"]
    estados_a_procesar  = params["estados_a_procesar"]
    primeros_n_cfg      = params["primeros_n"]

    log.info("run_id=%s | scripts=%s | estados=%s",
             run_id, scripts_seleccionados, estados_a_procesar)

    # ── Importar módulos clasificadores dinámicamente ─────────────────────────
    modulos: dict = {}
    for nombre in scripts_seleccionados:
        try:
            mod = importlib.import_module(f"clasificadores.{nombre}")
            modulos[nombre] = mod
            log.info("Clasificador cargado: %s", nombre)
        except Exception as exc:
            log.error("Error importando clasificador '%s': %s — se omitirá", nombre, exc)

    if not modulos:
        log.error("Ningún clasificador cargado — abortando")
        return

    minio_client = _make_minio()

    # ── Acumuladores ──────────────────────────────────────────────────────────
    # detecciones_por_fecha_script[fecha][script] = [deteccion_dict, ...]
    detecciones_por_fecha_script: dict[str, dict[str, list[dict]]] = defaultdict(
        lambda: defaultdict(list)
    )
    # total_por_script[script] = int (total analizados, incluye no detectados)
    total_por_script: dict[str, int] = {n: 0 for n in modulos}

    # ── Resultado por audio (para el JSONB) ───────────────────────────────────
    # resultado_por_audio[audio_id] = {estado, scripts_ejecutados, detecciones, error}
    resultado_por_audio: dict[str, dict] = {}

    with psycopg2.connect(SCORING_DB_URL) as conn:
        audios = obtener_audios_elegibles(conn, estados_a_procesar)
        total  = len(audios)
        log.info("Audios elegibles: %d", total)

        LOG_CADA = max(1, total // 20)   # log cada ~5%

        for i, audio in enumerate(audios, 1):
            audio_id          = str(audio["id"])
            nombre            = audio["nombre_archivo"]
            transcripcion_key = audio["transcripcion_key"]
            fecha_audio       = fecha_desde_nombre(nombre)

            if i % LOG_CADA == 0 or i == total:
                procesados_ok  = sum(1 for r in resultado_por_audio.values() if r["estado"] == "correcto")
                procesados_err = sum(1 for r in resultado_por_audio.values() if r["estado"] == "error")
                pct = i / total * 100
                log.info("Progreso: %d/%d (%.0f%%) | ok=%d err=%d",
                         i, total, pct, procesados_ok, procesados_err)

            # Idempotencia: si ya tiene estado=correcto en este run_id, saltar
            analisis_det_actual = audio.get("analisis_det_actual") or {}
            if (isinstance(analisis_det_actual, dict)
                    and analisis_det_actual.get("estado") == "correcto"
                    and analisis_det_actual.get("run_id") == run_id):
                log.info("Ya procesado en este run: %s — omitiendo", nombre)
                continue

            marcar_inicio(conn, audio_id, run_id)

            # ── Leer JSON de transcripción desde MinIO (stream, sin disco) ────
            try:
                response = minio_client.get_object(MINIO_BUCKET, transcripcion_key)
                data     = json.loads(response.read())
                response.close()
                response.release_conn()
            except S3Error as exc:
                log.error("Error descargando %s: %s", transcripcion_key, exc)
                resultado_por_audio[audio_id] = {
                    "estado":            "error",
                    "scripts_ejecutados": [],
                    "detecciones":       [],
                    "error":             str(exc),
                }
                continue
            except Exception as exc:
                log.error("Error leyendo JSON de %s: %s", nombre, exc)
                resultado_por_audio[audio_id] = {
                    "estado":            "error",
                    "scripts_ejecutados": [],
                    "detecciones":       [],
                    "error":             str(exc),
                }
                continue

            conversacion  = data.get("conversacion", [])
            id_interaccion = data.get("nombre_archivo", nombre)
            linea_cliente  = (data.get("metadata_llamada") or {}).get("numero_telefono")
            duracion_seg   = (data.get("metadata_llamada") or {}).get("duracion_seg")
            n_turnos       = len(conversacion)

            scripts_ejecutados_audio: list[str] = []
            detecciones_audio:        list[str] = []

            # ── Ejecutar cada clasificador ────────────────────────────────────
            for nombre_script, mod in modulos.items():
                primeros_n = primeros_n_cfg.get(
                    nombre_script, mod.PRIMEROS_N_DEFAULT
                )
                total_por_script[nombre_script] += 1
                scripts_ejecutados_audio.append(nombre_script)

                try:
                    detectado, frase = mod.detectar(conversacion, primeros_n)
                except Exception as exc:
                    log.error("Error en clasificador '%s' para audio %s: %s",
                              nombre_script, nombre, exc)
                    # El script falló pero no detenemos los demás
                    continue

                if detectado:
                    detecciones_audio.append(nombre_script)
                    detecciones_por_fecha_script[fecha_audio][nombre_script].append({
                        "id_interaccion":   id_interaccion,
                        "linea_cliente":    linea_cliente,
                        "turnos":           n_turnos,
                        "frase":            frase,
                        "duracion_llamada": duracion_seg,
                    })
                    log.debug("Detectado [%s] en %s: %s",
                              nombre_script, nombre, (frase or "")[:60])

            resultado_por_audio[audio_id] = {
                "estado":            "correcto",
                "scripts_ejecutados": scripts_ejecutados_audio,
                "detecciones":       detecciones_audio,
                "error":             None,
            }

        # ── Subir JSONs de output a MinIO (antes de commitear Postgres) ─────────
        log.info("Subiendo JSONs de output a MinIO...")
        for fecha_audio, scripts_det in detecciones_por_fecha_script.items():
            for nombre_script, detecciones_lista in scripts_det.items():
                mod = modulos.get(nombre_script)
                palabras_clave = getattr(mod, "PALABRAS_CLAVE", []) if mod else []

                output_key = (
                    f"analisis-raw/{fecha_audio}/{nombre_script}_{run_id}.json"
                )
                json_output = construir_json_output(
                    script=nombre_script,
                    run_id=run_id,
                    fecha_ejecucion=fecha_ejecucion,
                    estados_procesados=estados_a_procesar,
                    total_analizados=total_por_script.get(nombre_script, 0),
                    detecciones_lista=detecciones_lista,
                    palabras_clave=palabras_clave,
                )

                try:
                    with tempfile.TemporaryDirectory() as tmp:
                        out_path = str(Path(tmp) / "output.json")
                        with open(out_path, "w", encoding="utf-8") as f:
                            json.dump(json_output, f, ensure_ascii=False, indent=2)
                        minio_client.fput_object(
                            MINIO_BUCKET, output_key, out_path,
                            content_type="application/json",
                        )
                    log.info("Subido: %s (%d detecciones)",
                             output_key, len(detecciones_lista))
                except Exception as exc:
                    log.error("Error subiendo %s: %s", output_key, exc)

        # ── Actualizar JSONB por audio ────────────────────────────────────────
        log.info("Actualizando JSONB para %d audios...", len(resultado_por_audio))
        for audio_id, res in resultado_por_audio.items():
            try:
                marcar_fin(
                    conn,
                    audio_id,
                    run_id,
                    estado=res["estado"],
                    scripts_ejecutados=res["scripts_ejecutados"],
                    detecciones=res["detecciones"],
                    error_msg=res.get("error"),
                )
            except Exception as exc:
                log.error("Error actualizando JSONB para audio_id=%s: %s",
                          audio_id, exc)

    # ── Log final ─────────────────────────────────────────────────────────────
    total_procesados = len(resultado_por_audio)
    total_errores    = sum(1 for r in resultado_por_audio.values()
                           if r["estado"] == "error")
    total_correctos  = total_procesados - total_errores

    resumen_detecciones = {
        nombre_script: sum(
            len(dets)
            for fecha_dets in detecciones_por_fecha_script.values()
            for s, dets in fecha_dets.items()
            if s == nombre_script
        )
        for nombre_script in modulos
    }

    log.info(
        "Finalizado run_id=%s | procesados=%d | correctos=%d | errores=%d",
        run_id, total_procesados, total_correctos, total_errores,
    )
    for nombre_script, n_det in resumen_detecciones.items():
        log.info(
            "  %-25s analizados=%-5d detectados=%d",
            nombre_script,
            total_por_script.get(nombre_script, 0),
            n_det,
        )


if __name__ == "__main__":
    main()
