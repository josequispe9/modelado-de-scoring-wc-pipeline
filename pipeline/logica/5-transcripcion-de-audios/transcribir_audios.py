"""
Etapa 5 — Transcripción de audios.

Para cada audio pendiente en audio_pipeline_jobs:
  1. Descarga el WAV ganador de la etapa 4 desde MinIO a un archivo temporal
  2. Transcribe con WhisperX (transcripción + alineación + diarización)
  3. Sube el JSON resultante a MinIO (transcripciones-raw/YYYY-MM-DD/<grupo>/)
  4. Borra los temporales
  5. Actualiza audio_pipeline_jobs con el resultado y los params usados

Corre en las 3 PCs en paralelo. Cada PC lee su propia clave en pipeline_params
(transcripcion_G, transcripcion_M, transcripcion_B) para obtener sus params y grupo.

El modelo WhisperX se carga UNA vez al inicio y se reutiliza para todos los audios.
Cargar large-v3 tarda ~20-30 segundos — no hacerlo por audio.

Uso:
    python transcribir_audios.py

Requiere:
    - .env.tuberia en la raíz del proyecto (incluye HF_TOKEN)
    - entorno virtual env-gpu-transcripciones activado (WhisperX + PyTorch CUDA)
"""

import gc
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ─── Redirigir caches de HuggingFace y Torch al disco del venv ───────────────
# C:\ suele no tener espacio suficiente para los modelos (~3–4 GB).
# Se usa el mismo disco donde está el venv (D:\, E:\, J:\, etc.)
_venv_drive = Path(sys.executable).drive  # ej: "D:"
os.environ.setdefault("HF_HOME",    f"{_venv_drive}\\.cache\\huggingface")
os.environ.setdefault("TORCH_HOME", f"{_venv_drive}\\.cache\\torch")
# pyannote lee el token del entorno bajo este nombre
if "HF_TOKEN" in os.environ:
    os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", os.environ["HF_TOKEN"])
import psycopg2
import psycopg2.extras
import torch
import whisperx
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

CUENTA         = os.environ["MITROL_CUENTA"]   # G, M o B
CLAVE_PARAMS   = f"transcripcion_{CUENTA}"
MINIO_BUCKET   = "modelado-de-scoring-wc"
SCORING_DB_URL = os.environ["SCORING_DB_URL"]
DEVICE         = "cuda" if torch.cuda.is_available() else "cpu"

ESTADOS_VALIDOS = {"correcto", "reprocesar"}

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


# ─── Carga de modelos ─────────────────────────────────────────────────────────
def cargar_modelos(params: dict) -> tuple:
    """
    Carga los tres componentes de WhisperX en GPU una sola vez antes del loop.
    Retorna (whisper_model, align_model, align_metadata, diarize_pipeline).
    """
    modelo       = params.get("modelo", "large-v3")
    compute_type = params.get("compute_type", "float16")

    log.info("Cargando Whisper %s (%s) en %s...", modelo, compute_type, DEVICE)
    whisper_model = whisperx.load_model(
        modelo,
        device=DEVICE,
        compute_type=compute_type,
        language="es",
    )

    log.info("Cargando alignment model (es)...")
    align_model, align_metadata = whisperx.load_align_model(
        language_code="es",
        device=DEVICE,
    )

    log.info("Cargando diarization pipeline (pyannote)...")
    from whisperx.diarize import DiarizationPipeline
    diarize_pipeline = DiarizationPipeline(
        token=os.environ.get("HF_TOKEN"),
        device=DEVICE,
    )

    log.info("Modelos listos en %s.", DEVICE)
    return whisper_model, align_model, align_metadata, diarize_pipeline


# ─── Obtención a demanda ──────────────────────────────────────────────────────
def obtener_siguiente_audio(conn, grupo: str, estados: list,
                             duracion_desde: int | None,
                             duracion_hasta: int | None,
                             omitir_ids: set | None = None) -> dict | None:
    """
    Obtiene el siguiente audio a transcribir de forma atómica.

    SELECT FOR UPDATE SKIP LOCKED garantiza que dos workers del mismo grupo
    nunca procesen el mismo audio en paralelo.

    Criterios:
      - etapa_actual = 'correccion_normalizacion' con estado_global en `estados`
      - O etapa_actual = 'transcripcion' (otro grupo ya transcribió, el mío no)
      - Filtro por duracion_conversacion_seg si se especifica
      - NOT EXISTS transcripción correcta de mi grupo ya en el JSONB
      - omitir_ids: IDs ya vistos en esta sesión sin ganador (evita loop infinito)
    """
    estados_filtrados = [e for e in estados if e in ESTADOS_VALIDOS]
    if not estados_filtrados:
        log.warning("Ningún estado válido en params — usando ['correcto']")
        estados_filtrados = ["correcto"]

    # Condiciones principales según los estados configurados
    condiciones = [
        f"(etapa_actual = 'correccion_normalizacion' AND estado_global = '{e}')"
        for e in estados_filtrados
    ]
    # Otro grupo ya transcribió pero el mío todavía no
    condiciones.append(
        "(etapa_actual = 'transcripcion' AND estado_global IN ('correcto', 'error'))"
    )
    where_estado = " OR ".join(condiciones)

    # Filtro de duración — usa duracion_conversacion_seg con fallback a duracion_audio_seg
    dur_col   = "COALESCE(duracion_conversacion_seg, duracion_audio_seg, 0)"
    dur_conds = ""
    if duracion_desde is not None:
        dur_conds += f" AND {dur_col} >= {int(duracion_desde)}"
    if duracion_hasta is not None:
        dur_conds += f" AND {dur_col} <= {int(duracion_hasta)}"

    omitir_cond = ""
    if omitir_ids:
        ids_str = ", ".join(f"'{i}'" for i in omitir_ids)
        omitir_cond = f"AND id NOT IN ({ids_str})"

    query = f"""
        SELECT id, nombre_archivo, etapa_actual, estado_global, etapas,
               duracion_conversacion_seg, duracion_audio_seg
        FROM audio_pipeline_jobs
        WHERE ({where_estado})
          AND estado_global != 'en_proceso'
          {dur_conds}
          {omitir_cond}
          AND NOT EXISTS (
            SELECT 1
            FROM jsonb_array_elements(
              COALESCE(etapas->'transcripcion', '[]'::jsonb)
            ) elem
            WHERE elem->>'grupo'  = %(grupo)s
              AND elem->>'estado' IN ('correcto', 'error')
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


def obtener_input_key(audio: dict) -> str | None:
    """
    Retorna la key de MinIO del WAV ganador seleccionado en la etapa 4.
    Lee etapas->correccion_normalizacion->ganador y extrae su ubicacion.
    Si no hay ganador (seleccionar_ganador.py aún no corrió), retorna None.
    """
    etapas     = audio.get("etapas") or {}
    correccion = etapas.get("correccion_normalizacion") or {}
    ganador    = correccion.get("ganador")
    if not ganador:
        return None
    grupo_data = correccion.get(ganador) or {}
    return grupo_data.get("ubicacion", {}).get("key")


def restaurar_estado(conn, audio_id: str, estado_previo: str) -> None:
    """Devuelve el audio a su estado anterior (cuando se omite sin error)."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE audio_pipeline_jobs SET estado_global = %s WHERE id = %s",
            (estado_previo, audio_id)
        )
    conn.commit()


# ─── Transcripción ────────────────────────────────────────────────────────────
def transcribir(audio_path: str, whisper_model, align_model, align_metadata,
                diarize_pipeline, params: dict) -> dict:
    """
    Corre el pipeline completo de WhisperX:
      1. Transcripción con Whisper
      2. Alineación a nivel de palabra (wav2vec2)
      3. Diarización (pyannote) — quién habló cuándo
      4. Asignación de speaker a cada segmento/palabra
    """
    min_speakers = params.get("min_speakers")
    max_speakers = params.get("max_speakers")

    audio_array = whisperx.load_audio(audio_path)

    result = whisper_model.transcribe(audio_array, batch_size=params.get("batch_size", 4), language="es")

    result = whisperx.align(
        result["segments"], align_model, align_metadata,
        audio_array, DEVICE, return_char_alignments=False,
    )

    diarize_kwargs = {}
    if min_speakers is not None:
        diarize_kwargs["min_speakers"] = int(min_speakers)
    if max_speakers is not None:
        diarize_kwargs["max_speakers"] = int(max_speakers)
    diarize_segments = diarize_pipeline(audio_array, **diarize_kwargs)

    result = whisperx.assign_word_speakers(diarize_segments, result)
    return result


# ─── Serialización ────────────────────────────────────────────────────────────
def construir_json_output(result: dict, params: dict) -> dict:
    """
    Construye el JSON a guardar en MinIO.
    Incluye los segmentos con speaker labels y metadata del procesamiento.
    """
    segmentos  = result.get("segments", [])
    hablantes  = {s.get("speaker") for s in segmentos if s.get("speaker")}

    return {
        "segments": segmentos,
        "metadata": {
            "modelo":                  params.get("modelo", "large-v3"),
            "compute_type":            params.get("compute_type", "float16"),
            "language":                "es",
            "min_speakers_param":      params.get("min_speakers"),
            "max_speakers_param":      params.get("max_speakers"),
            "num_hablantes_detectados": len(hablantes),
            "num_segmentos":           len(segmentos),
        },
    }


# ─── Actualización de Postgres ────────────────────────────────────────────────
def actualizar_registro(conn, audio_id: str, etapa_actual_previa: str,
                        estado: str, object_key: str | None,
                        params: dict, error: str | None,
                        metricas: dict | None = None) -> None:
    """
    Agrega un intento al array etapas.transcripcion (no reemplaza intentos previos).

    - Si es el primer grupo (etapa_actual_previa='correccion_normalizacion'):
      avanza etapa_actual a 'transcripcion' y actualiza estado_global.
    - Si es un grupo adicional (etapa_actual_previa='transcripcion'):
      solo agrega al array JSONB, no toca etapa_actual.
    """
    intento = {
        "estado":       estado,
        "fecha":        datetime.now(timezone.utc).isoformat(),
        "cuenta":       CUENTA,
        "grupo":        params.get("grupo", "GBM"),
        "params_usados": {
            k: params[k] for k in
            ("modelo", "compute_type", "min_speakers", "max_speakers",
             "duracion_desde", "duracion_hasta", "estados")
            if k in params
        },
        "ubicacion": {"bucket": MINIO_BUCKET, "key": object_key} if object_key else None,
        "metricas":  metricas,
        "error":     error,
    }

    with conn.cursor() as cur:
        cur.execute(
            "SELECT etapas->'transcripcion' FROM audio_pipeline_jobs WHERE id = %s",
            (audio_id,)
        )
        row = cur.fetchone()
        previos = row[0] if row and row[0] else []
        if not isinstance(previos, list):
            previos = [previos]
        intento["intento"] = len(previos) + 1
        nuevos_intentos    = previos + [intento]

        nuevo_estado = "correcto" if estado == "correcto" else "error"

        if etapa_actual_previa == "correccion_normalizacion":
            # Primer grupo: avanza etapa y estado
            cur.execute("""
                UPDATE audio_pipeline_jobs
                SET etapas        = jsonb_set(etapas, '{transcripcion}', %s::jsonb),
                    estado_global = %s,
                    etapa_actual  = 'transcripcion',
                    fecha_ultima_actualizacion = now()
                WHERE id = %s
            """, (json.dumps(nuevos_intentos), nuevo_estado, audio_id))
        else:
            # Grupo adicional: solo agrega al array
            cur.execute("""
                UPDATE audio_pipeline_jobs
                SET etapas        = jsonb_set(etapas, '{transcripcion}', %s::jsonb),
                    estado_global = %s,
                    fecha_ultima_actualizacion = now()
                WHERE id = %s
            """, (json.dumps(nuevos_intentos), nuevo_estado, audio_id))

    conn.commit()


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    params         = obtener_params()
    grupo          = params.get("grupo", "GBM")
    estados        = params.get("estados", ["correcto"])
    duracion_desde = params.get("duracion_desde")
    duracion_hasta = params.get("duracion_hasta")

    log.info("Cuenta: %s | Grupo: %s | Estados: %s | Duración: %s–%s seg",
             CUENTA, grupo, estados, duracion_desde, duracion_hasta)

    whisper_model, align_model, align_metadata, diarize_pipeline = cargar_modelos(params)

    procesados  = 0
    errores     = 0
    sin_ganador = 0
    omitir_ids: set = set()

    with psycopg2.connect(SCORING_DB_URL) as conn:
        while True:
            audio = obtener_siguiente_audio(conn, grupo, estados, duracion_desde, duracion_hasta,
                                            omitir_ids)
            if not audio:
                log.info("Sin más audios para procesar.")
                break

            nombre            = audio["nombre_archivo"]
            etapa_actual_prev = audio["etapa_actual"]
            estado_prev       = audio["estado_global"]
            input_key         = obtener_input_key(audio)

            if not input_key:
                # seleccionar_ganador.py no corrió aún para este audio — omitir sin marcar error
                log.warning("Sin ganador en etapa 4 para %s — omitiendo", nombre)
                restaurar_estado(conn, str(audio["id"]), estado_prev)
                omitir_ids.add(str(audio["id"]))
                sin_ganador += 1
                continue

            partes        = input_key.split("/")
            fecha_carpeta = partes[1] if len(partes) > 1 else datetime.now().strftime("%Y-%m-%d")
            output_key    = f"transcripciones-raw/{fecha_carpeta}/{grupo}/{nombre}.json"

            log.info("Transcribiendo: %s → %s", nombre, output_key)

            with tempfile.TemporaryDirectory() as tmp:
                input_tmp  = str(Path(tmp) / "audio.wav")
                output_tmp = str(Path(tmp) / "transcripcion.json")

                try:
                    minio_client.fget_object(MINIO_BUCKET, input_key, input_tmp)
                except S3Error as e:
                    log.error("Error descargando %s: %s", input_key, e)
                    actualizar_registro(conn, str(audio["id"]), etapa_actual_prev,
                                        "error", None, params, str(e))
                    errores += 1
                    gc.collect()
                    torch.cuda.empty_cache()
                    continue

                try:
                    result = transcribir(input_tmp, whisper_model, align_model,
                                         align_metadata, diarize_pipeline, params)
                except Exception as e:
                    log.error("Error WhisperX en %s: %s", nombre, e)
                    actualizar_registro(conn, str(audio["id"]), etapa_actual_prev,
                                        "error", None, params, str(e))
                    errores += 1
                    gc.collect()
                    torch.cuda.empty_cache()
                    continue

                output_json = construir_json_output(result, params)
                metricas = {
                    "num_segmentos":            output_json["metadata"]["num_segmentos"],
                    "num_hablantes_detectados": output_json["metadata"]["num_hablantes_detectados"],
                }

                Path(output_tmp).write_bytes(
                    json.dumps(output_json, ensure_ascii=False, indent=2).encode("utf-8")
                )

                try:
                    minio_client.fput_object(
                        MINIO_BUCKET, output_key, output_tmp,
                        content_type="application/json",
                    )
                except S3Error as e:
                    log.error("Error subiendo JSON %s: %s", output_key, e)
                    actualizar_registro(conn, str(audio["id"]), etapa_actual_prev,
                                        "error", None, params, str(e))
                    errores += 1
                    gc.collect()
                    torch.cuda.empty_cache()
                    continue

            actualizar_registro(conn, str(audio["id"]), etapa_actual_prev,
                                "correcto", output_key, params, None,
                                metricas=metricas)
            log.info("OK: %s — %d segmentos, %d hablantes detectados",
                     nombre, metricas["num_segmentos"], metricas["num_hablantes_detectados"])
            procesados += 1
            gc.collect()
            torch.cuda.empty_cache()

    log.info("Finalizado — procesados: %d | errores: %d | sin_ganador: %d",
             procesados, errores, sin_ganador)


if __name__ == "__main__":
    main()
