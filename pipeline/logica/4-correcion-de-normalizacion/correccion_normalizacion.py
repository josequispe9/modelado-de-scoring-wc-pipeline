"""
Etapa 4 — Corrección de normalización.

Para cada audio pendiente de evaluación:
  1. Descarga el WAV normalizado desde MinIO a un archivo temporal
  2. Valida umbrales duros (duración, sample rate, canales)
  3. Calcula métricas de calidad (SNR, duración ratio, RMS)
  4. Genera un score compuesto y clasifica: correcto / reprocesar / invalido
  5. Actualiza audio_pipeline_jobs con el resultado en etapas.correccion_normalizacion
     (el audio permanece en su ubicación original en MinIO, no se duplica)

Corre solo en gaspar.

Uso:
    python correccion_normalizacion.py

Requiere:
    - ffmpeg en el PATH
    - .env.tuberia en la raíz del proyecto
    - pip install minio psycopg2-binary python-dotenv librosa soundfile numpy
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import librosa
import numpy as np
import psycopg2
import psycopg2.extras
import soundfile as sf
from dotenv import load_dotenv
from minio import Minio
from minio.error import S3Error

from config import DEFAULTS

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
                    "SELECT valor FROM pipeline_params WHERE clave = 'correccion_normalizacion'"
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


# ─── Obtención a demanda ──────────────────────────────────────────────────────
def obtener_siguiente_audio(conn) -> dict | None:
    """
    Obtiene el siguiente (audio, grupo) pendiente de evaluación.

    Un audio puede tener múltiples grupos en etapas.normalizacion (G, M, B).
    Por cada grupo con estado='correcto' que aún no tenga su clave en
    etapas.correccion_normalizacion, genera una tarea de evaluación.

    Usa SELECT FOR UPDATE SKIP LOCKED para evitar procesamiento doble.
    """
    query = """
        SELECT
            apj.id,
            apj.nombre_archivo,
            apj.etapa_actual,
            apj.etapas,
            norm_entry.value AS norm_entry
        FROM audio_pipeline_jobs apj,
             jsonb_array_elements(
               COALESCE(apj.etapas->'normalizacion', '[]'::jsonb)
             ) AS norm_entry
        WHERE apj.etapa_actual  IN ('normalizacion', 'correccion_normalizacion')
          AND apj.estado_global != 'en_proceso'
          AND norm_entry.value->>'estado' = 'correcto'
          AND NOT (
            COALESCE(apj.etapas->'correccion_normalizacion', '{}'::jsonb)
            ? (norm_entry.value->>'grupo')
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
def calcular_snr(audio: np.ndarray) -> float:
    """SNR estimado: relación entre señal activa y ruido de fondo."""
    rms_total = np.sqrt(np.mean(audio ** 2))
    if rms_total == 0:
        return 0.0
    # Estima ruido como el percentil 10 de frames de energía — vectorizado
    frame_size = 512
    n_frames = len(audio) // frame_size
    if n_frames == 0:
        return 0.0
    frames_matrix = audio[:n_frames * frame_size].reshape(n_frames, frame_size)
    energias = np.sqrt(np.mean(frames_matrix ** 2, axis=1))
    ruido_rms = np.percentile(energias, 10)
    if ruido_rms == 0:
        return 40.0  # sin ruido detectable → score máximo
    snr = 20 * np.log10(rms_total / ruido_rms)
    return float(np.clip(snr, 0.0, 60.0))


def calcular_rms_dbfs(audio: np.ndarray) -> float:
    rms = np.sqrt(np.mean(audio ** 2))
    if rms == 0:
        return -100.0
    return float(20 * np.log10(rms))


def calcular_metricas(wav_path: str, duracion_original_seg: float, params: dict) -> dict:
    """
    Retorna dict con: valido (bool), motivo_invalido (str|None),
    snr, rms_dbfs, duracion_seg, duracion_ratio, score, clasificacion.
    """
    # ── Validación con soundfile (más rápido que librosa para metadata) ───────
    try:
        info = sf.info(wav_path)
    except Exception as e:
        return {"valido": False, "motivo_invalido": f"archivo ilegible: {e}"}

    if info.samplerate != params["sample_rate_esperado"]:
        return {"valido": False, "motivo_invalido": f"sample_rate={info.samplerate}"}

    if info.channels != params["canales_esperados"]:
        return {"valido": False, "motivo_invalido": f"canales={info.channels}"}

    duracion_seg = info.duration
    if duracion_seg < params["duracion_minima_seg"]:
        return {"valido": False, "motivo_invalido": f"duracion={duracion_seg:.1f}s < minimo"}

    if duracion_seg > params["duracion_maxima_seg"]:
        return {"valido": False, "motivo_invalido": f"duracion={duracion_seg:.1f}s > maximo"}

    # ── Carga de audio ────────────────────────────────────────────────────────
    try:
        audio, _ = sf.read(wav_path, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
    except Exception as e:
        return {"valido": False, "motivo_invalido": f"error cargando audio: {e}"}

    # ── Métricas ──────────────────────────────────────────────────────────────
    snr           = calcular_snr(audio)
    rms_dbfs      = calcular_rms_dbfs(audio)
    duracion_ratio = (
        duracion_seg / duracion_original_seg
        if duracion_original_seg > 0 else 0.0
    )

    # ── Score compuesto ───────────────────────────────────────────────────────
    score_snr = np.clip(
        (snr - params["snr_min"]) / (params["snr_max"] - params["snr_min"]),
        0.0, 1.0
    )

    desviacion_rms = abs(rms_dbfs - params["rms_ref_dbfs"])
    score_rms = np.clip(
        1.0 - desviacion_rms / params["rms_tolerancia_db"],
        0.0, 1.0
    )

    score_duracion = np.clip(
        (duracion_ratio - params["duracion_ratio_min"]) / (1.0 - params["duracion_ratio_min"]),
        0.0, 1.0
    )

    score = (
        params["peso_snr"]            * score_snr +
        params["peso_rms"]            * score_rms +
        params["peso_duracion_ratio"] * score_duracion
    )
    score = round(float(score), 4)

    if score >= params["umbral_correcto"]:
        clasificacion = "correcto"
    elif score >= params["umbral_reprocesar"]:
        clasificacion = "reprocesar"
    else:
        clasificacion = "invalido"

    return {
        "valido":          True,
        "motivo_invalido": None,
        "snr":             round(snr, 2),
        "rms_dbfs":        round(rms_dbfs, 2),
        "duracion_seg":    round(duracion_seg, 2),
        "duracion_ratio":  round(duracion_ratio, 4),
        "score":           score,
        "clasificacion":   clasificacion,
    }


# ─── Actualización de Postgres ────────────────────────────────────────────────
def actualizar_registro(conn, audio_id: str, etapa_actual_previa: str,
                        grupo: str, clasificacion: str,
                        input_key: str | None, metricas: dict,
                        fecha_inicio: str, error: str | None) -> None:
    resultado_grupo = {
        "estado":       clasificacion,
        "fecha_inicio": fecha_inicio,
        "fecha_fin":    datetime.now(timezone.utc).isoformat(),
        "ubicacion":    {"bucket": MINIO_BUCKET, "key": input_key} if input_key else None,
        "error":        error,
        "score":        metricas.get("score"),
        "metricas": {
            "snr":            metricas.get("snr"),
            "rms_dbfs":       metricas.get("rms_dbfs"),
            "duracion_seg":   metricas.get("duracion_seg"),
            "duracion_ratio": metricas.get("duracion_ratio"),
        } if metricas.get("valido") else None,
        "motivo_invalido": metricas.get("motivo_invalido"),
    }

    with conn.cursor() as cur:
        cur.execute(
            "SELECT etapas->'correccion_normalizacion' FROM audio_pipeline_jobs WHERE id = %s",
            (audio_id,)
        )
        row = cur.fetchone()
        correccion = row[0] if row and row[0] else {}
        if not isinstance(correccion, dict):
            correccion = {}

        correccion[grupo] = resultado_grupo
        if "ganador" not in correccion:
            correccion["ganador"] = None

        if etapa_actual_previa == "normalizacion":
            cur.execute("""
                UPDATE audio_pipeline_jobs
                SET etapas        = jsonb_set(etapas, '{correccion_normalizacion}', %s::jsonb),
                    etapa_actual  = 'correccion_normalizacion',
                    estado_global = %s
                WHERE id = %s
            """, (json.dumps(correccion), clasificacion, audio_id))
        else:
            cur.execute("""
                UPDATE audio_pipeline_jobs
                SET etapas        = jsonb_set(etapas, '{correccion_normalizacion}', %s::jsonb),
                    estado_global = %s
                WHERE id = %s
            """, (json.dumps(correccion), clasificacion, audio_id))

    conn.commit()


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    params = obtener_params()
    correctos   = 0
    reprocesar  = 0
    invalidos   = 0
    errores     = 0

    with psycopg2.connect(SCORING_DB_URL) as conn:
        while True:
            audio = obtener_siguiente_audio(conn)
            if not audio:
                break

            audio_id          = str(audio["id"])
            nombre            = audio["nombre_archivo"]
            etapa_actual_prev = audio["etapa_actual"]
            norm_entry        = audio["norm_entry"]

            if not norm_entry:
                log.warning("Sin norm_entry correcto para %s — omitiendo", nombre)
                continue

            grupo     = norm_entry["grupo"]
            input_key = norm_entry.get("ubicacion", {}).get("key")

            if not input_key:
                log.warning("Sin ubicacion en normalizacion para %s [grupo=%s]", nombre, grupo)
                continue

            duracion_original = (norm_entry.get("metricas") or {}).get("duracion_seg", 0)
            fecha_inicio      = datetime.now(timezone.utc).isoformat()

            log.info("Evaluando: %s [grupo=%s]", nombre, grupo)

            with tempfile.TemporaryDirectory() as tmp:
                wav_tmp = str(Path(tmp) / "audio.wav")

                try:
                    minio_client.fget_object(MINIO_BUCKET, input_key, wav_tmp)
                except S3Error as e:
                    log.error("Error descargando %s: %s", input_key, e)
                    actualizar_registro(conn, audio_id, etapa_actual_prev,
                                        grupo, "invalido", None, {}, fecha_inicio, str(e))
                    errores += 1
                    continue

                metricas = calcular_metricas(wav_tmp, duracion_original, params)

                if not metricas["valido"]:
                    log.warning("Invalido %s [grupo=%s]: %s", nombre, grupo, metricas["motivo_invalido"])
                    actualizar_registro(conn, audio_id, etapa_actual_prev,
                                        grupo, "invalido", input_key, metricas,
                                        fecha_inicio, metricas["motivo_invalido"])
                    invalidos += 1
                    continue

            clasificacion = metricas["clasificacion"]
            actualizar_registro(conn, audio_id, etapa_actual_prev,
                                grupo, clasificacion, input_key, metricas, fecha_inicio, None)
            log.info("OK: %s [grupo=%s score=%.2f → %s]", nombre, grupo, metricas["score"], clasificacion)
            if clasificacion == "correcto":
                correctos += 1
            elif clasificacion == "reprocesar":
                reprocesar += 1
            else:
                invalidos += 1

    log.info(
        "Finalizado — correcto: %d | reprocesar: %d | invalido: %d | errores: %d",
        correctos, reprocesar, invalidos, errores
    )


if __name__ == "__main__":
    main()
