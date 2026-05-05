"""
Etapa 6c — Selección del grupo ganador de transcripción.

Para cada audio con todos sus grupos ya evaluados (tienen score_total):
  1. Elige el grupo con mayor score_total priorizando clasificacion='correcto'
  2. Construye el JSON formateado para la etapa 7:
     - Mapea SPEAKER_XX → VENDEDOR / CLIENTE con los roles del LLM
     - Incluye metadata de la llamada (agente, campaña, tipificación, etc.)
  3. Sube el JSON a MinIO: transcripciones-formateadas/YYYY-MM-DD/nombre.json
     (YYYY-MM-DD extraído del nombre del archivo, no de la fecha de ejecución)
  4. Marca ganador en etapas.correccion_transcripciones y avanza estado_global

Se corre manualmente (o via API) después de auditar los resultados del scoring.

Uso:
    python seleccionar_ganador.py

Requiere:
    - .env.tuberia en la raíz del proyecto
    - pip install minio psycopg2-binary python-dotenv
"""

import json
import logging
import os
import tempfile
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

# ─── Parámetros ───────────────────────────────────────────────────────────────
DEFAULTS_GANADOR = {
    "umbral_score_correcto":   0.75,
    "umbral_score_reprocesar": 0.40,
}


def obtener_params() -> dict:
    try:
        with psycopg2.connect(SCORING_DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT valor FROM pipeline_params WHERE clave = 'correccion_transcripciones_ganador'"
                )
                row = cur.fetchone()
        if row and row[0]:
            params = DEFAULTS_GANADOR.copy()
            params.update(row[0])
            log.info("Params ganador cargados desde Postgres")
            return params
    except Exception as e:
        log.warning("No se pudo leer pipeline_params: %s — usando DEFAULTS", e)
    return DEFAULTS_GANADOR.copy()


# ─── Audios pendientes ────────────────────────────────────────────────────────
def obtener_audios_pendientes(conn) -> list[dict]:
    """
    Retorna audios con etapa_actual='correccion_transcripciones' y sin ganador aún.
    Solo incluye audios donde todos los grupos evaluados ya tienen score_total
    (es decir, ya corrió correccion_llm.py para cada grupo).
    """
    query = """
        SELECT
            id, nombre_archivo, etapas,
            duracion_conversacion_seg,
            agente, campania, empresa, tipificacion, clase_tipificacion,
            etapas->'correccion_transcripciones' AS correccion,
            etapas->'transcripcion'              AS transcripcion
        FROM audio_pipeline_jobs
        WHERE etapa_actual  = 'correccion_transcripciones'
          AND estado_global != 'en_proceso'
          AND (etapas->'correccion_transcripciones'->>'ganador') IS NULL
        ORDER BY created_at
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query)
        return [dict(r) for r in cur.fetchall()]


# ─── Fecha desde nombre de archivo ────────────────────────────────────────────
def fecha_desde_nombre(nombre: str) -> str:
    """
    Extrae la fecha del nombre del archivo.
    Ejemplo: amza50_1_260409133329904_MIT_01976 → '2026-04-09'
    """
    try:
        d = nombre.split("_")[2][:6]   # YYMMDD
        return f"20{d[:2]}-{d[2:4]}-{d[4:6]}"
    except (IndexError, ValueError):
        return datetime.now().strftime("%Y-%m-%d")


def todos_evaluados_con_llm(transcripcion: list, correccion: dict) -> bool:
    """
    Verifica que todos los grupos con estado='correcto' en el array transcripcion
    ya tienen score_total en correccion_transcripciones (ambas fases completadas).
    """
    grupos_transcriptos = {e["grupo"] for e in transcripcion if e.get("estado") == "correcto"}
    for grupo in grupos_transcriptos:
        entrada = correccion.get(grupo, {})
        if entrada.get("clasificacion_determinista") == "invalido":
            continue  # invalidos no necesitan score_total
        if entrada.get("score_total") is None:
            return False
    return True


# ─── Selección del ganador ────────────────────────────────────────────────────
def elegir_ganador(correccion: dict) -> tuple[str, dict] | None:
    """
    Elige el grupo con mayor score_total.
    Prioriza clasificacion='correcto' sobre 'reprocesar'. Ignora 'invalido'.
    """
    grupos = {k: v for k, v in correccion.items() if k != "ganador"}
    candidatos = {
        k: v for k, v in grupos.items()
        if v.get("clasificacion") in ("correcto", "reprocesar")
    }
    if not candidatos:
        return None

    correctos = {k: v for k, v in candidatos.items() if v.get("clasificacion") == "correcto"}
    elegibles = correctos if correctos else candidatos
    grupo_ganador = max(elegibles, key=lambda k: elegibles[k].get("score_total") or 0.0)
    return grupo_ganador, elegibles[grupo_ganador]


# ─── Construcción del JSON de salida para etapa 7 ────────────────────────────
def construir_json_salida(audio: dict, data: dict, entrada_ganadora: dict,
                          grupo_ganador: str) -> dict:
    """
    Construye el JSON formateado para la etapa 7 (análisis de conversación).

    Mapea SPEAKER_XX → VENDEDOR / CLIENTE usando los roles identificados por el LLM.
    Si los roles son desconocidos, mantiene los speaker IDs originales.
    """
    vendedor_id = entrada_ganadora.get("vendedor")
    cliente_id  = entrada_ganadora.get("cliente")

    def resolver_rol(speaker_id: str) -> str:
        if speaker_id == vendedor_id and vendedor_id not in (None, "desconocido"):
            return "VENDEDOR"
        if speaker_id == cliente_id and cliente_id not in (None, "desconocido"):
            return "CLIENTE"
        return "DESCONOCIDO"

    segments        = data.get("segments", [])
    metadata_whisper = data.get("metadata", {})
    metricas        = entrada_ganadora.get("metricas", {})

    conversacion = []
    for seg in segments:
        texto = seg.get("text", "").strip()
        if texto:
            conversacion.append({
                "rol":   resolver_rol(seg.get("speaker", "SPEAKER_00")),
                "texto": texto,
            })

    return {
        "audio_id":       str(audio["id"]),
        "nombre_archivo": audio["nombre_archivo"],

        "metadata_llamada": {
            "agente":             audio.get("agente"),
            "campania":           audio.get("campania"),
            "empresa":            audio.get("empresa"),
            "duracion_seg":       audio.get("duracion_conversacion_seg"),
            "tipificacion":       audio.get("tipificacion"),
            "clase_tipificacion": audio.get("clase_tipificacion"),
        },

        "roles": {
            "vendedor": vendedor_id,
            "cliente":  cliente_id,
        },

        "conversacion": conversacion,

        "procesamiento": {
            "grupo_ganador":        grupo_ganador,
            "modelo_transcripcion": metadata_whisper.get("modelo"),
            "score_total":          entrada_ganadora.get("score_total"),
            "coherencia_llm":       entrada_ganadora.get("coherencia_llm"),
            "fecha_formateado":     datetime.now(timezone.utc).isoformat(),
        },
    }


# ─── Actualización de Postgres ────────────────────────────────────────────────
def marcar_ganador(conn, audio_id: str, grupo_ganador: str,
                   output_key: str, estado_final: str) -> None:
    ganador_data = {
        "grupo":     grupo_ganador,
        "ubicacion": {"bucket": MINIO_BUCKET, "key": output_key},
        "fecha":     datetime.now(timezone.utc).isoformat(),
    }
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE audio_pipeline_jobs
            SET etapas = jsonb_set(
                    etapas,
                    '{correccion_transcripciones,ganador}',
                    %s::jsonb
                ),
                estado_global = %s,
                fecha_ultima_actualizacion = now()
            WHERE id = %s
        """, (json.dumps(ganador_data), estado_final, audio_id))
    conn.commit()


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    params      = obtener_params()
    procesados  = 0
    sin_ganador = 0
    incompletos = 0

    with psycopg2.connect(SCORING_DB_URL) as conn:
        audios = obtener_audios_pendientes(conn)
        log.info("Audios pendientes de selección: %d", len(audios))

        for audio in audios:
            audio_id      = str(audio["id"])
            nombre        = audio["nombre_archivo"]
            correccion    = audio["correccion"] or {}
            transcripcion = audio["transcripcion"] or []

            if not isinstance(correccion, dict):
                log.warning("Estructura inesperada en correccion_transcripciones para %s", nombre)
                sin_ganador += 1
                continue

            if not todos_evaluados_con_llm(transcripcion, correccion):
                log.info("Grupos aún sin score_total para %s — omitiendo", nombre)
                incompletos += 1
                continue

            resultado = elegir_ganador(correccion)
            if not resultado:
                log.warning("Ningún grupo apto para %s — todos invalidos", nombre)
                sin_ganador += 1
                continue

            grupo_ganador, entrada_ganadora = resultado
            estado_final = entrada_ganadora.get("clasificacion", "correcto")

            log.info("Ganador: %s → grupo=%s score_total=%.4f → %s",
                     nombre, grupo_ganador,
                     entrada_ganadora.get("score_total", 0.0),
                     estado_final)

            # ── Descargar JSON de transcripcion del grupo ganador ─────────────
            input_key = (entrada_ganadora.get("ubicacion_transcripcion") or {}).get("key")
            if not input_key:
                log.error("Sin ubicacion_transcripcion para ganador %s [grupo=%s]",
                          nombre, grupo_ganador)
                sin_ganador += 1
                continue

            with tempfile.TemporaryDirectory() as tmp:
                json_tmp = str(Path(tmp) / "transcripcion.json")

                try:
                    minio_client.fget_object(MINIO_BUCKET, input_key, json_tmp)
                except S3Error as e:
                    log.error("Error descargando %s: %s", input_key, e)
                    sin_ganador += 1
                    continue

                try:
                    with open(json_tmp, encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    log.error("Error leyendo JSON %s: %s", input_key, e)
                    sin_ganador += 1
                    continue

            json_salida = construir_json_salida(audio, data, entrada_ganadora, grupo_ganador)

            # ── Subir a MinIO ─────────────────────────────────────────────────
            fecha_carpeta = fecha_desde_nombre(nombre)
            output_key    = f"transcripciones-formateadas/{fecha_carpeta}/{nombre}.json"

            with tempfile.TemporaryDirectory() as tmp:
                out_path = str(Path(tmp) / "salida.json")
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(json_salida, f, ensure_ascii=False, indent=2)

                try:
                    minio_client.fput_object(
                        MINIO_BUCKET, output_key, out_path,
                        content_type="application/json"
                    )
                    log.info("Subido: %s", output_key)
                except S3Error as e:
                    log.error("Error subiendo %s: %s", output_key, e)
                    sin_ganador += 1
                    continue

            marcar_ganador(conn, audio_id, grupo_ganador, output_key, estado_final)
            procesados += 1

    log.info("Finalizado — seleccionados: %d | sin_ganador: %d | incompletos: %d",
             procesados, sin_ganador, incompletos)


if __name__ == "__main__":
    main()
