"""
Etapa 3 — Normalización de audios.

Para cada audio pendiente en audio_pipeline_jobs:
  1. Descarga el WAV desde MinIO a un archivo temporal
  2. Normaliza con ffmpeg (silence removal, loudnorm, filtros opcionales)
  3. Sube el WAV normalizado a MinIO (audios-raw/YYYY-MM-DD/<grupo>/)
  4. Borra los temporales
  5. Actualiza audio_pipeline_jobs con el resultado y los params usados

Corre en las 3 PCs en paralelo. Cada PC lee su propia clave en pipeline_params
(normalizacion_G, normalizacion_M, normalizacion_B) para obtener sus params y grupo.

Uso:
    python preprocesar_audios.py

Requiere:
    - ffmpeg en el PATH
    - .env.tuberia en la raíz del proyecto
    - pip install minio psycopg2-binary python-dotenv
"""

import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
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

CUENTA        = os.environ["MITROL_CUENTA"]   # G, M o B
CLAVE_PARAMS  = f"normalizacion_{CUENTA}"
MINIO_BUCKET  = "modelado-de-scoring-wc"
SCORING_DB_URL = os.environ["SCORING_DB_URL"]

minio_client = Minio(
    os.environ["MINIO_ENDPOINT"],
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=False,
)


# ─── Parámetros ───────────────────────────────────────────────────────────────
def obtener_params() -> dict:
    """
    Lee los parámetros desde pipeline_params. Fallback a DEFAULTS si no hay entrada.
    """
    try:
        with psycopg2.connect(SCORING_DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT valor FROM pipeline_params WHERE clave = %s", (CLAVE_PARAMS,))
                row = cur.fetchone()
        if row and row[0]:
            params = DEFAULTS.copy()
            params.update(row[0])
            log.info("Params cargados desde Postgres (clave: %s)", CLAVE_PARAMS)
            return params
    except Exception as e:
        log.warning("No se pudo leer pipeline_params: %s — usando DEFAULTS", e)
    return DEFAULTS.copy()


# ─── Obtención a demanda ──────────────────────────────────────────────────────
def obtener_siguiente_audio(conn, carpeta: str, grupo: str) -> dict | None:
    """
    Obtiene el siguiente audio a procesar de forma atómica.

    SELECT FOR UPDATE SKIP LOCKED garantiza que dos workers del mismo grupo
    nunca procesen el mismo audio en paralelo.

    El filtro JSONB asegura que mi grupo no reprocese un audio que ya normalizó
    correctamente, pero sí permite que un segundo grupo procese audios que otro
    grupo ya completó.

    Criterios según carpeta:
      - 'audios':     etapa_actual='descarga'     y estado_global='correcto'
      - 'reprocesar': etapa_actual='normalizacion' y estado_global='reprocesar'
      - 'ambos':      unión de los dos anteriores
    Siempre incluye audios que otro grupo ya procesó (etapa_actual='normalizacion',
    estado_global='correcto') pero que mi grupo aún no tiene en el JSONB.
    """
    condiciones = []
    if carpeta in ("audios", "ambos"):
        condiciones.append("(etapa_actual = 'descarga' AND estado_global = 'correcto')")
    if carpeta in ("reprocesar", "ambos"):
        condiciones.append("(etapa_actual = 'normalizacion' AND estado_global = 'reprocesar')")

    if not condiciones:
        log.warning("Carpeta '%s' no reconocida — usando 'audios'", carpeta)
        condiciones = ["(etapa_actual = 'descarga' AND estado_global = 'correcto')"]

    # Otro grupo ya procesó este audio pero el mío todavía no
    condiciones.append("(etapa_actual = 'normalizacion' AND estado_global = 'correcto')")

    where = " OR ".join(condiciones)

    query = f"""
        SELECT id, nombre_archivo, url_fuente, etapa_actual, etapas
        FROM audio_pipeline_jobs
        WHERE ({where})
          AND estado_global != 'en_proceso'
          AND NOT EXISTS (
            SELECT 1
            FROM jsonb_array_elements(
              COALESCE(etapas->'normalizacion', '[]'::jsonb)
            ) elem
            WHERE elem->>'grupo'  = %(grupo)s
              AND elem->>'estado' = 'correcto'
          )
        ORDER BY created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    """

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, {"grupo": grupo})
        audio = cur.fetchone()
        if audio:
            cur.execute(
                "UPDATE audio_pipeline_jobs SET estado_global = 'en_proceso' WHERE id = %s",
                (str(audio["id"]),)
            )
    conn.commit()
    return dict(audio) if audio else None


def obtener_input_key(audio: dict, carpeta: str) -> str | None:
    """
    Retorna la key de MinIO del WAV a normalizar.
    - Para audios nuevos (etapa_actual='descarga'): url_fuente
    - Para reprocesar: etapas.correccion_normalizacion[-1].ubicacion.key
    """
    if audio["etapa_actual"] == "descarga":
        return audio["url_fuente"]

    etapas = audio.get("etapas") or {}
    correccion = etapas.get("correccion_normalizacion")
    if correccion:
        ultimo = correccion[-1] if isinstance(correccion, list) else correccion
        return ultimo.get("ubicacion", {}).get("key")

    log.warning("Sin ubicacion en correccion_normalizacion para %s", audio["nombre_archivo"])
    return None


# ─── ffmpeg ───────────────────────────────────────────────────────────────────
def build_ffmpeg_filter(params: dict) -> str:
    filters = []

    silence_filter = (
        f"silenceremove="
        f"start_periods=1:"
        f"start_silence={params['silence_duration']}:"
        f"start_threshold={params['silence_threshold']}:"
        f"stop_periods=-1:"
        f"stop_silence={params['silence_duration']}:"
        f"stop_threshold={params['silence_threshold']}:"
        f"detection=peak"
    )
    filters.append(silence_filter)

    if params.get("highpass_filter"):
        filters.append("highpass=f=200")

    if params.get("noise_reduction"):
        filters.append("afftdn=nf=-25")

    if params.get("normalize", True):
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")

    return ",".join(filters)


def obtener_duracion(wav_path: str) -> float | None:
    """Retorna la duración en segundos del WAV, o None si no se puede leer."""
    try:
        import soundfile as sf
        info = sf.info(wav_path)
        return round(info.duration, 2)
    except Exception:
        return None


def normalizar(input_path: str, output_path: str, params: dict) -> bool:
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-af", build_ffmpeg_filter(params),
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        "-y",
        output_path,
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       check=True, timeout=300)
        return True
    except subprocess.TimeoutExpired:
        log.error("Timeout ffmpeg en %s", input_path)
        return False
    except subprocess.CalledProcessError as e:
        log.error("Error ffmpeg: %s", e.stderr.decode("utf-8", errors="ignore")[:300])
        return False


# ─── Actualización de Postgres ────────────────────────────────────────────────
def actualizar_registro(conn, audio_id: str, etapa_actual_previa: str,
                        estado: str, object_key: str | None,
                        params: dict, error: str | None,
                        duracion_seg: float | None = None) -> None:
    """
    Agrega un intento al array etapas.normalizacion (no reemplaza intentos previos).

    - Si es el primer grupo en procesar (etapa_actual_previa='descarga'):
      avanza etapa_actual a 'normalizacion' y actualiza estado_global.
    - Si es un grupo adicional (etapa_actual_previa='normalizacion'):
      solo agrega al JSONB, no toca etapa_actual ni estado_global
      (ya fueron establecidos por el primer grupo).
    """
    intento = {
        "estado":       estado,
        "fecha":        datetime.now(timezone.utc).isoformat(),
        "cuenta":       CUENTA,
        "grupo":        params.get("grupo", "GBM"),
        "params_usados": {
            k: params[k] for k in
            ("silence_threshold", "silence_duration", "normalize",
             "noise_reduction", "highpass_filter")
            if k in params
        },
        "ubicacion": {"bucket": MINIO_BUCKET, "key": object_key} if object_key else None,
        "metricas":  {"duracion_seg": duracion_seg} if duracion_seg is not None else None,
        "error":    error,
    }

    with conn.cursor() as cur:
        cur.execute(
            "SELECT etapas->'normalizacion' FROM audio_pipeline_jobs WHERE id = %s",
            (audio_id,)
        )
        row = cur.fetchone()
        previos = row[0] if row and row[0] else []
        if not isinstance(previos, list):
            previos = [previos]
        intento["intento"] = len(previos) + 1
        nuevos_intentos = previos + [intento]

        if etapa_actual_previa == "descarga":
            # Primer grupo: avanza estado y etapa
            nuevo_estado = "correcto" if estado == "correcto" else "error"
            cur.execute("""
                UPDATE audio_pipeline_jobs
                SET etapas        = jsonb_set(etapas, '{normalizacion}', %s::jsonb),
                    estado_global = %s,
                    etapa_actual  = 'normalizacion'
                WHERE id = %s
            """, (json.dumps(nuevos_intentos), nuevo_estado, audio_id))
        else:
            # Grupo adicional: solo agrega al JSONB
            cur.execute("""
                UPDATE audio_pipeline_jobs
                SET etapas        = jsonb_set(etapas, '{normalizacion}', %s::jsonb),
                    estado_global = %s
                WHERE id = %s
            """, (json.dumps(nuevos_intentos),
                  "correcto" if estado == "correcto" else "error",
                  audio_id))

    conn.commit()


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    params  = obtener_params()
    grupo   = params.get("grupo", "GBM")
    carpeta = params.get("carpeta", "audios")

    log.info("Cuenta: %s | Grupo: %s | Carpeta: %s", CUENTA, grupo, carpeta)

    procesados = 0
    errores    = 0

    with psycopg2.connect(SCORING_DB_URL) as conn:
        while True:
            audio = obtener_siguiente_audio(conn, carpeta, grupo)
            if not audio:
                break

            nombre            = audio["nombre_archivo"]
            etapa_actual_prev = audio["etapa_actual"]
            input_key         = obtener_input_key(audio, carpeta)

            if not input_key:
                log.warning("Sin input key para %s — omitiendo", nombre)
                continue

            partes        = input_key.split("/")
            fecha_carpeta = partes[1] if len(partes) > 1 else datetime.now().strftime("%Y-%m-%d")
            output_key    = f"audios-raw/{fecha_carpeta}/{grupo}/{nombre}_{CUENTA}.wav"

            log.info("Procesando: %s → %s", nombre, output_key)

            with tempfile.TemporaryDirectory() as tmp:
                input_tmp  = str(Path(tmp) / "input.wav")
                output_tmp = str(Path(tmp) / "output.wav")

                try:
                    minio_client.fget_object(MINIO_BUCKET, input_key, input_tmp)
                except S3Error as e:
                    log.error("Error descargando %s: %s", input_key, e)
                    actualizar_registro(conn, str(audio["id"]), etapa_actual_prev,
                                        "error", None, params, str(e))
                    errores += 1
                    continue

                ok = normalizar(input_tmp, output_tmp, params)
                if not ok:
                    actualizar_registro(conn, str(audio["id"]), etapa_actual_prev,
                                        "error", None, params, "ffmpeg falló")
                    errores += 1
                    continue

                try:
                    minio_client.fput_object(MINIO_BUCKET, output_key, output_tmp,
                                             content_type="audio/wav")
                except S3Error as e:
                    log.error("Error subiendo %s: %s", output_key, e)
                    actualizar_registro(conn, str(audio["id"]), etapa_actual_prev,
                                        "error", None, params, str(e))
                    errores += 1
                    continue

            duracion = obtener_duracion(output_tmp)
            actualizar_registro(conn, str(audio["id"]), etapa_actual_prev,
                                "correcto", output_key, params, None,
                                duracion_seg=duracion)
            log.info("OK: %s", nombre)
            procesados += 1

    log.info("Finalizado — procesados: %d | errores: %d", procesados, errores)


if __name__ == "__main__":
    main()
