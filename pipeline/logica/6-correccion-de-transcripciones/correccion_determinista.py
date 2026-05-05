"""
Etapa 6a — Corrección de transcripciones (scoring determinista).

Para cada (audio, grupo) pendiente:
  1. Descarga el JSON de transcripción desde MinIO
  2. Calcula métricas de calidad basadas en la salida de WhisperX
  3. Aplica filtros duros (invalido inmediato) y score compuesto
  4. Guarda el resultado en etapas.correccion_transcripciones.<grupo>

Corre solo en Gaspar (CPU).

Uso:
    python correccion_determinista.py

Requiere:
    - .env.tuberia en la raíz del proyecto
    - pip install minio psycopg2-binary python-dotenv
"""

import json
import logging
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from minio import Minio
from minio.error import S3Error

from config_determinista import DEFAULTS

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


# ─── Parámetros ───────────────────────────────────────────────────────────────
def obtener_params() -> dict:
    try:
        with psycopg2.connect(SCORING_DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT valor FROM pipeline_params WHERE clave = 'correccion_transcripciones'"
                )
                row = cur.fetchone()
        if row and row[0]:
            params = DEFAULTS.copy()
            params.update(row[0])
            log.info("Params cargados desde Postgres")
            return params
    except Exception as e:
        log.warning("No se pudo leer pipeline_params: %s — usando DEFAULTS", e)
    return DEFAULTS.copy()


# ─── Query SKIP LOCKED ────────────────────────────────────────────────────────
def obtener_siguiente_audio(conn, params: dict) -> dict | None:
    """
    Obtiene el siguiente (audio, grupo) de transcripción pendiente de evaluación.

    Por cada entrada en el array etapas.transcripcion con estado='correcto'
    que no tenga aún su clave en etapas.correccion_transcripciones.

    Usa SELECT FOR UPDATE SKIP LOCKED para evitar procesamiento doble.
    """
    estados_filtrados = [e for e in params.get("estados", ["correcto"])
                         if e in ("correcto", "reprocesar")]
    if not estados_filtrados:
        estados_filtrados = ["correcto"]

    estados_sql = ", ".join(f"'{e}'" for e in estados_filtrados)

    dur_col   = "COALESCE(duracion_conversacion_seg, duracion_audio_seg, 0)"
    dur_conds = ""
    if params.get("duracion_desde") is not None:
        dur_conds += f" AND {dur_col} >= {int(params['duracion_desde'])}"
    if params.get("duracion_hasta") is not None:
        dur_conds += f" AND {dur_col} <= {int(params['duracion_hasta'])}"

    query = f"""
        SELECT
            apj.id,
            apj.nombre_archivo,
            apj.etapa_actual,
            apj.etapas,
            apj.duracion_conversacion_seg,
            tr_entry.value AS tr_entry
        FROM audio_pipeline_jobs apj,
             jsonb_array_elements(
               COALESCE(apj.etapas->'transcripcion', '[]'::jsonb)
             ) AS tr_entry
        WHERE apj.etapa_actual IN ('transcripcion', 'correccion_transcripciones')
          AND apj.estado_global != 'en_proceso'
          AND tr_entry.value->>'estado' = 'correcto'
          {dur_conds}
          AND NOT (
            COALESCE(apj.etapas->'correccion_transcripciones', '{{}}'::jsonb)
            ? (tr_entry.value->>'grupo')
          )
        ORDER BY apj.created_at
        FOR UPDATE OF apj SKIP LOCKED
        LIMIT 1
    """

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query)
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE audio_pipeline_jobs SET estado_global = 'en_proceso' WHERE id = %s",
                (str(row["id"]),)
            )
    conn.commit()
    return dict(row) if row else None


# ─── Métricas de calidad ──────────────────────────────────────────────────────
def calcular_metricas(data: dict) -> dict:
    """
    Calcula métricas de calidad a partir del JSON de WhisperX.

    Retorna dict con:
      avg_logprob, total_words, low_score_ratio, speaker_dominance, num_hablantes
    """
    segments = data.get("segments", [])
    metadata = data.get("metadata", {})

    # avg_logprob: promedio de todos los segmentos
    logprobs = [s["avg_logprob"] for s in segments if "avg_logprob" in s]
    avg_logprob = sum(logprobs) / len(logprobs) if logprobs else -1.0

    # Palabras totales y ratio de palabras con score bajo
    all_words = [w for s in segments for w in s.get("words", [])]
    total_words = len(all_words)
    low_score_words = sum(1 for w in all_words if w.get("score", 1.0) < 0.15)
    low_score_ratio = low_score_words / total_words if total_words > 0 else 1.0

    # Speaker dominance: fracción del speaker con más segmentos
    speaker_ids = [s.get("speaker") for s in segments if s.get("speaker")]
    if speaker_ids:
        counts = Counter(speaker_ids)
        speaker_dominance = max(counts.values()) / len(speaker_ids)
    else:
        speaker_dominance = 1.0

    num_hablantes = metadata.get("num_hablantes_detectados", len(set(speaker_ids)))

    return {
        "avg_logprob":       round(avg_logprob, 4),
        "total_words":       total_words,
        "low_score_ratio":   round(low_score_ratio, 4),
        "speaker_dominance": round(speaker_dominance, 4),
        "num_hablantes":     num_hablantes,
    }


def clasificar(metricas: dict, params: dict) -> tuple[float, str, str | None]:
    """
    Aplica filtros duros y calcula score compuesto.

    Retorna (score, clasificacion, motivo_invalido).
    """
    avg_logprob       = metricas["avg_logprob"]
    total_words       = metricas["total_words"]
    low_score_ratio   = metricas["low_score_ratio"]
    speaker_dominance = metricas["speaker_dominance"]
    num_hablantes     = metricas["num_hablantes"]

    # ── Filtros duros ─────────────────────────────────────────────────────────
    if num_hablantes < 2:
        return 0.0, "invalido", f"num_hablantes={num_hablantes} < 2"

    if total_words < params["umbral_words_min"]:
        return 0.0, "invalido", f"total_words={total_words} < {params['umbral_words_min']}"

    if avg_logprob < params["umbral_logprob_invalido"]:
        return 0.0, "invalido", f"avg_logprob={avg_logprob:.3f} < {params['umbral_logprob_invalido']}"

    if speaker_dominance > params["umbral_speaker_dominance"]:
        return 0.0, "invalido", f"speaker_dominance={speaker_dominance:.3f} > {params['umbral_speaker_dominance']}"

    if low_score_ratio > params["umbral_low_score_ratio"]:
        return 0.0, "invalido", f"low_score_ratio={low_score_ratio:.3f} > {params['umbral_low_score_ratio']}"

    # ── Score continuo ────────────────────────────────────────────────────────
    # logprob normalizado: [-0.6, -0.4] → [0, 1], fuera del rango se satura
    lp_min, lp_max = params["umbral_logprob_invalido"], params["umbral_logprob_reprocesar"]
    score_logprob = min(1.0, max(0.0, (avg_logprob - lp_min) / (lp_max - lp_min)))

    # words: saturar en 500 palabras → 1.0
    score_words = min(1.0, total_words / 500.0)

    # speaker_balance: dominance=0.5 → 1.0, dominance=0.95 → 0.0
    dom_min, dom_max = 0.5, params["umbral_speaker_dominance"]
    score_speaker = min(1.0, max(0.0, 1.0 - (speaker_dominance - dom_min) / (dom_max - dom_min)))

    score = (
        params["peso_logprob"]        * score_logprob +
        params["peso_words"]          * score_words +
        params["peso_speaker_balance"] * score_speaker
    )
    score = round(float(score), 4)

    if score >= params["umbral_score_correcto"]:
        clasificacion = "correcto"
    elif score >= params["umbral_score_reprocesar"]:
        clasificacion = "reprocesar"
    else:
        clasificacion = "invalido"

    return score, clasificacion, None


# ─── Actualización de Postgres ────────────────────────────────────────────────
def actualizar_registro(conn, audio_id: str, etapa_actual_previa: str,
                        grupo: str, score: float, clasificacion: str,
                        metricas: dict, input_key: str,
                        fecha_inicio: str, error: str | None) -> None:
    resultado_grupo = {
        "score_determinista":          score,
        "clasificacion_determinista":  clasificacion,
        "metricas":                    metricas,
        "fecha_inicio":                fecha_inicio,
        "fecha_fin":                   datetime.now(timezone.utc).isoformat(),
        "ubicacion_transcripcion":     {"bucket": MINIO_BUCKET, "key": input_key},
        "error":                       error,
    }

    with conn.cursor() as cur:
        cur.execute(
            "SELECT etapas->'correccion_transcripciones' FROM audio_pipeline_jobs WHERE id = %s",
            (audio_id,)
        )
        row = cur.fetchone()
        correccion = row[0] if row and row[0] else {}
        if not isinstance(correccion, dict):
            correccion = {}

        correccion[grupo] = resultado_grupo

        if etapa_actual_previa == "transcripcion":
            cur.execute("""
                UPDATE audio_pipeline_jobs
                SET etapas       = jsonb_set(etapas, '{correccion_transcripciones}', %s::jsonb),
                    etapa_actual = 'correccion_transcripciones',
                    estado_global = %s,
                    fecha_ultima_actualizacion = now()
                WHERE id = %s
            """, (json.dumps(correccion), clasificacion, audio_id))
        else:
            cur.execute("""
                UPDATE audio_pipeline_jobs
                SET etapas       = jsonb_set(etapas, '{correccion_transcripciones}', %s::jsonb),
                    estado_global = %s,
                    fecha_ultima_actualizacion = now()
                WHERE id = %s
            """, (json.dumps(correccion), clasificacion, audio_id))

    conn.commit()


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    params     = obtener_params()
    correctos  = 0
    reprocesar = 0
    invalidos  = 0
    errores    = 0

    with psycopg2.connect(SCORING_DB_URL) as conn:
        while True:
            audio = obtener_siguiente_audio(conn, params)
            if not audio:
                break

            audio_id          = str(audio["id"])
            nombre            = audio["nombre_archivo"]
            etapa_actual_prev = audio["etapa_actual"]
            tr_entry          = audio["tr_entry"]

            if not tr_entry:
                log.warning("Sin tr_entry correcto para %s — omitiendo", nombre)
                continue

            grupo     = tr_entry.get("grupo")
            input_key = (tr_entry.get("ubicacion") or {}).get("key")

            if not grupo or not input_key:
                log.warning("Datos incompletos en transcripcion para %s — omitiendo", nombre)
                continue

            fecha_inicio = datetime.now(timezone.utc).isoformat()
            log.info("Evaluando: %s [grupo=%s]", nombre, grupo)

            with tempfile.TemporaryDirectory() as tmp:
                json_tmp = str(Path(tmp) / "transcripcion.json")

                try:
                    minio_client.fget_object(MINIO_BUCKET, input_key, json_tmp)
                except S3Error as e:
                    log.error("Error descargando %s: %s", input_key, e)
                    actualizar_registro(conn, audio_id, etapa_actual_prev,
                                        grupo, 0.0, "invalido", {}, input_key,
                                        fecha_inicio, f"descarga fallida: {e}")
                    errores += 1
                    continue

                try:
                    with open(json_tmp, encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    log.error("Error leyendo JSON %s: %s", input_key, e)
                    actualizar_registro(conn, audio_id, etapa_actual_prev,
                                        grupo, 0.0, "invalido", {}, input_key,
                                        fecha_inicio, f"json invalido: {e}")
                    errores += 1
                    continue

            metricas = calcular_metricas(data)
            score, clasificacion, motivo = clasificar(metricas, params)

            if motivo:
                log.warning("Invalido %s [grupo=%s]: %s", nombre, grupo, motivo)
            else:
                log.info("OK: %s [grupo=%s score=%.4f → %s]", nombre, grupo, score, clasificacion)

            actualizar_registro(conn, audio_id, etapa_actual_prev,
                                grupo, score, clasificacion,
                                metricas, input_key, fecha_inicio,
                                motivo)

            if clasificacion == "correcto":
                correctos += 1
            elif clasificacion == "reprocesar":
                reprocesar += 1
            elif clasificacion == "invalido":
                invalidos += 1

    log.info("Finalizado — correcto: %d | reprocesar: %d | invalido: %d | errores: %d",
             correctos, reprocesar, invalidos, errores)


if __name__ == "__main__":
    main()
