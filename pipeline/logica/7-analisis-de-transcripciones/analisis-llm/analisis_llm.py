"""
Etapa 7 — Análisis LLM de transcripciones.

Para cada audio elegible (con transcripción formateada en MinIO):
  1. Descarga el JSON de transcripción desde MinIO
  2. Aplica cada script de análisis definido en inputs/<script>.txt
  3. Infiere con el LLM (guided decoding JSON) si el clasificador detecta el patrón
  4. Sube el resultado agregado a MinIO: analisis-raw/YYYY-MM-DD/<script>_<run_id>.json
  5. Actualiza etapas.analisis.llm en PostgreSQL (sin sobreescribir etapas.analisis.determinista)

Uso:
    python analisis_llm.py

Requiere:
    - .env.tuberia en la raíz del proyecto
    - pip install vllm minio psycopg2-binary python-dotenv
"""

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from minio import Minio
from minio.error import S3Error

# ─── Configuración ────────────────────────────────────────────────────────────
ROOT_DIR   = Path(__file__).parents[4]
SCRIPT_DIR = Path(__file__).parent

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

minio_client = Minio(
    os.environ["MINIO_ENDPOINT"],
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=False,
)

# ─── Bloques de contexto (copiados de test_calidad_llm.py) ────────────────────
CTX_TRANSCRIPCION = (
    "IMPORTANTE: Esta transcripción fue generada automáticamente y puede contener "
    "errores ortográficos, palabras mal reconocidas o frases cortadas. "
    "No descartes un segmento solo porque tenga errores de tipeo."
)

CTX_DIARIZACION = (
    "IMPORTANTE: Los hablantes están marcados como DESCONOCIDO porque la diarización "
    "automática no identificó correctamente vendedor y cliente. "
    "El vendedor suele iniciar la llamada, presentarse y hacer preguntas. "
    "El cliente suele responder, expresar dudas o resistencia."
)

CTX_DOMINIO = (
    "Esta es una llamada de ventas de portabilidad de telefonía móvil en Argentina. "
    "El vendedor trabaja para Movistar e intenta convencer al cliente de cambiar "
    "su línea desde otra empresa (generalmente Claro o Personal) a Movistar. "
    "Términos del rubro: gigas/GB, chip, portabilidad, abono, plan, descuento fijo, "
    "cierre comercial, tienda Movistar, fibra óptica, WhatsApp gratis. "
    "Expresiones coloquiales argentinas (no son información relevante): "
    "'te robo un segundo', 'no te voy a mentir', 'dale', 'buenísimo'."
)

CTX_CIERRE = (
    "El 'cierre comercial' es un texto formal/legal que el vendedor lee al final "
    "de la llamada repitiendo datos del cliente: número de línea, nombre, email, "
    "precio, plan contratado y dirección de tienda."
)


# ─── Funciones reutilizadas de test_calidad_llm.py ───────────────────────────

def parsear_inputs(path: Path) -> list[dict]:
    """
    Formato de cada test:
        [nombre_test]
        descripcion        = texto libre
        schema             = {...json en una sola linea...}
        min_turnos         = N    (omitir archivos con menos de N turnos, default 1)
        segmento           = todo_N | inicio_N | fin_N      (default todo_40)
        max_tokens         = N    (default 100)
        contexto           = transcripcion,diarizacion,dominio,cierre  (opcional)
        few_shot           = texto libre multilinea (se inserta antes de la conversacion)
        prompt             = texto del prompt (puede ser multilinea)

    Lineas que empiezan con # son comentarios.
    """
    tests = []
    current: dict | None = None
    current_field: str | None = None
    current_lines: list[str] = []

    def guardar_campo():
        if current is not None and current_field is not None:
            current[current_field] = "\n".join(current_lines).strip()

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or line.strip() == "":
            continue
        if line.startswith("[") and line.endswith("]"):
            guardar_campo()
            if current is not None:
                tests.append(current)
            current = {"nombre": line[1:-1].strip()}
            current_field = None
            current_lines = []
            continue
        if "=" in line and not line[0].isspace():
            guardar_campo()
            key, _, val = line.partition("=")
            current_field = key.strip()
            current_lines = [val.strip()]
            continue
        if current_field is not None:
            current_lines.append(line.strip())

    guardar_campo()
    if current is not None:
        tests.append(current)

    return tests


def aplicar_segmento(segmentos: list[dict], segmento: str) -> list[dict]:
    """
    segmento puede ser:
      todo_N   → primeros N/2 + últimos N/2
      inicio_N → primeros N
      fin_N    → últimos N
    """
    parte, _, n_str = segmento.partition("_")
    n = int(n_str) if n_str.isdigit() else 40

    total = len(segmentos)
    if total <= n:
        return segmentos

    if parte == "inicio":
        return segmentos[:n]
    if parte == "fin":
        return segmentos[-n:]
    # todo (default): mitad inicio + mitad fin
    mitad = n // 2
    return segmentos[:mitad] + segmentos[-mitad:]


def formatear_segmentos(segmentos: list[dict]) -> str:
    lineas = []
    for seg in segmentos:
        rol   = seg.get("rol", "DESCONOCIDO")
        texto = seg.get("texto", "").strip()
        if texto:
            lineas.append(f"{rol}: {texto}")
    return "\n".join(lineas)


def construir_prompt(test: dict, conversacion_txt: str) -> str:
    partes = []

    # Bloques de contexto solicitados
    ctx_keys = [c.strip() for c in test.get("contexto", "").split(",") if c.strip()]
    ctx_map = {
        "transcripcion": CTX_TRANSCRIPCION,
        "diarizacion":   CTX_DIARIZACION,
        "dominio":       CTX_DOMINIO,
        "cierre":        CTX_CIERRE,
    }
    for key in ctx_keys:
        if key in ctx_map:
            partes.append(ctx_map[key])

    # Instrucción principal
    partes.append(test["prompt"].strip())

    # Few-shot
    few_shot = test.get("few_shot", "").strip()
    if few_shot:
        partes.append(f"Ejemplos:\n{few_shot}")

    # Conversación
    partes.append(f"Conversación:\n{conversacion_txt}")

    partes.append("Responde en JSON.")
    return "\n\n".join(partes)


def inferir(llm, prompt: str, schema: dict, max_tokens: int) -> tuple[bool, str, dict | None, float]:
    from vllm import SamplingParams
    from vllm.sampling_params import StructuredOutputsParams

    guided   = StructuredOutputsParams(json=schema)
    sampling = SamplingParams(
        temperature=0.0,
        max_tokens=max_tokens,
        structured_outputs=guided,
    )
    t0 = time.time()
    output = llm.generate([prompt], sampling_params=sampling)
    elapsed = round(time.time() - t0, 2)

    raw = output[0].outputs[0].text
    try:
        obj = json.loads(raw)
        return True, raw, obj, elapsed
    except Exception:
        return False, raw, None, elapsed


# ─── Helpers ──────────────────────────────────────────────────────────────────

def obtener_params() -> dict:
    """Lee pipeline_params clave 'analisis_llm'. Si no existe usa DEFAULTS."""
    from config import DEFAULTS_ANALISIS_LLM

    try:
        with psycopg2.connect(SCORING_DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT valor FROM pipeline_params WHERE clave = 'analisis_llm'"
                )
                row = cur.fetchone()
        if row and row[0]:
            params = DEFAULTS_ANALISIS_LLM.copy()
            params.update({k: v for k, v in row[0].items() if k in DEFAULTS_ANALISIS_LLM})
            log.info("Params cargados desde Postgres (analisis_llm)")
            return params
    except Exception as e:
        log.warning("No se pudo leer pipeline_params: %s — usando DEFAULTS", e)
    return DEFAULTS_ANALISIS_LLM.copy()


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


def obtener_audios_elegibles(conn, estados: list[str]) -> list[dict]:
    """
    Retorna audios con transcripción formateada disponible para analizar.
    Solo procesa audios que aún no tienen analisis.llm completado correctamente.
    """
    query = """
        SELECT
            id,
            nombre_archivo,
            etapas->'correccion_transcripciones'->'ganador'->'ubicacion'->>'key'
                AS transcripcion_key
        FROM audio_pipeline_jobs
        WHERE etapa_actual IN ('correccion_transcripciones', 'analisis')
          AND estado_global = ANY(%s)
          AND etapas->'correccion_transcripciones'->'ganador'->'ubicacion'->>'key' IS NOT NULL
          AND (
              etapas->'analisis'->'llm'->>'estado' IS NULL
              OR etapas->'analisis'->'llm'->>'estado' != 'correcto'
          )
        ORDER BY created_at
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, (estados,))
        return [dict(r) for r in cur.fetchall()]


def actualizar_postgres_audio(conn, audio_id: str, llm_entry: dict) -> None:
    """
    Escribe etapas.analisis.llm sin sobreescribir etapas.analisis.determinista.
    """
    estado_global = llm_entry["estado"]
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE audio_pipeline_jobs
            SET etapas = jsonb_set(
                    coalesce(etapas, '{}'::jsonb),
                    '{analisis,llm}',
                    %s::jsonb
                ),
                etapa_actual = 'analisis',
                estado_global = %s,
                fecha_ultima_actualizacion = now()
            WHERE id = %s
            """,
            (json.dumps(llm_entry), estado_global, audio_id),
        )
    conn.commit()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    run_id         = datetime.now().strftime("%Y%m%d_%H%M%S")
    fecha_inicio   = datetime.now(timezone.utc).isoformat()

    params              = obtener_params()
    scripts_seleccionados = params["scripts"]
    estados_a_procesar  = params["estados_a_procesar"]
    modelo              = params["modelo"]
    gpu_memory_util     = params["gpu_memory_utilization"]
    max_model_len       = params["max_model_len"]

    log.info("run_id: %s", run_id)
    log.info("Scripts a ejecutar: %s", scripts_seleccionados)
    log.info("Estados a procesar: %s", estados_a_procesar)
    log.info("Modelo: %s", modelo)

    # ── Cargar definiciones de cada script ────────────────────────────────────
    scripts_defs: dict[str, dict] = {}
    for script_name in scripts_seleccionados:
        input_path = SCRIPT_DIR / "inputs" / f"{script_name}.txt"
        if not input_path.exists():
            log.error("No se encontró el archivo de inputs: %s — saltando script", input_path)
            continue
        tests = parsear_inputs(input_path)
        if not tests:
            log.error("No se encontró ningún test en %s — saltando script", input_path)
            continue
        # Un archivo de inputs = un clasificador = primer (y único) test
        scripts_defs[script_name] = tests[0]
        log.info("Script '%s' cargado: test='%s'", script_name, tests[0].get("nombre"))

    if not scripts_defs:
        log.error("Ningún script válido disponible — abortando")
        return

    # ── Consultar audios elegibles ─────────────────────────────────────────────
    with psycopg2.connect(SCORING_DB_URL) as conn:
        audios = obtener_audios_elegibles(conn, estados_a_procesar)

    log.info("Audios elegibles: %d", len(audios))
    if not audios:
        log.info("Nada que procesar.")
        return

    # ── Cargar modelo LLM una sola vez ────────────────────────────────────────
    log.info("Cargando modelo: %s ...", modelo)
    from vllm import LLM
    llm = LLM(
        model=modelo,
        gpu_memory_utilization=gpu_memory_util,
        max_model_len=max_model_len,
        enforce_eager=True,
    )
    log.info("Modelo listo.")

    # ── Procesar cada script ───────────────────────────────────────────────────
    # resultados_por_script: script_name → {fecha → lista de detecciones}
    resultados_por_script: dict[str, dict[str, list]] = {
        name: {} for name in scripts_defs
    }
    # estadisticas_por_script: script_name → {total_analizados, total_detectados}
    estadisticas_por_script: dict[str, dict] = {
        name: {"total_analizados": 0, "total_detectados": 0} for name in scripts_defs
    }
    # detecciones_por_audio: audio_id → set de script_names detectados
    detecciones_por_audio: dict[str, set] = {
        str(a["id"]): set() for a in audios
    }
    # errores_por_audio: audio_id → bool (si hubo error en cualquier script)
    errores_por_audio: dict[str, bool] = {
        str(a["id"]): False for a in audios
    }

    for script_name, test_def in scripts_defs.items():
        log.info("=== Ejecutando script: %s ===", script_name)

        schema     = json.loads(test_def["schema"])
        segmento   = test_def.get("segmento", "todo_40")
        max_tokens = int(test_def.get("max_tokens", 100))
        min_turnos = int(test_def.get("min_turnos", 1))

        # El primer campo del schema es el campo de detección booleana
        campo_deteccion = list(schema.get("properties", {}).keys())[0] if schema.get("properties") else script_name

        detecciones_script: list[dict] = []
        total_analizados = 0
        total_detectados = 0
        total_audios     = len(audios)
        log_cada         = max(1, total_audios // 20)   # log cada ~5%

        for idx, audio in enumerate(audios, 1):
            audio_id          = str(audio["id"])
            nombre_archivo    = audio["nombre_archivo"]
            transcripcion_key = audio["transcripcion_key"]

            if idx % log_cada == 0 or idx == total_audios:
                pct = idx / total_audios * 100
                log.info("[%s] Progreso: %d/%d (%.0f%%) | detectados=%d",
                         script_name, idx, total_audios, pct, total_detectados)

            if not transcripcion_key:
                log.warning("[%s] Sin transcripcion_key — saltando", nombre_archivo)
                errores_por_audio[audio_id] = True
                continue

            # ── Leer JSON de transcripción desde MinIO (stream, sin disco) ────
            try:
                response = minio_client.get_object(MINIO_BUCKET, transcripcion_key)
                data     = json.loads(response.read())
                response.close()
                response.release_conn()
            except S3Error as e:
                log.error("[%s] Error descargando %s: %s", nombre_archivo, transcripcion_key, e)
                errores_por_audio[audio_id] = True
                continue
            except Exception as e:
                log.error("[%s] Error leyendo JSON: %s", nombre_archivo, e)
                errores_por_audio[audio_id] = True
                continue

            conversacion = data.get("conversacion", [])
            metadata     = data.get("metadata_llamada", {})
            id_interaccion = data.get("nombre_archivo", nombre_archivo)
            linea_cliente  = metadata.get("numero_telefono")
            duracion_llamada = metadata.get("duracion_seg")

            if len(conversacion) < min_turnos:
                log.debug("[%s] Omitido: %d turnos < min_turnos=%d",
                          nombre_archivo, len(conversacion), min_turnos)
                continue

            # ── Aplicar segmento y construir prompt ───────────────────────────
            segs_recortados = aplicar_segmento(conversacion, segmento)
            conv_txt        = formatear_segmentos(segs_recortados)
            prompt          = construir_prompt(test_def, conv_txt)
            tokens_aprox    = len(prompt.split())

            # ── Inferencia ────────────────────────────────────────────────────
            try:
                valido, raw, resultado, elapsed = inferir(llm, prompt, schema, max_tokens)
            except Exception as e:
                log.error("[%s][%s] Excepción en inferencia: %s", script_name, nombre_archivo, e)
                errores_por_audio[audio_id] = True
                continue

            total_analizados += 1

            if not valido:
                log.warning("[%s][%s] JSON inválido — raw: %s",
                            script_name, nombre_archivo, (raw or "")[:100])
                errores_por_audio[audio_id] = True
                continue

            # ── Determinar detección ──────────────────────────────────────────
            valor_deteccion = resultado.get(campo_deteccion, "no") if resultado else "no"
            detectado = (str(valor_deteccion).lower() == "si")

            log.debug("[%s][%s] %s=%s  turnos=%d  tokens≈%d  %.2fs",
                      script_name, nombre_archivo, campo_deteccion,
                      valor_deteccion, len(segs_recortados), tokens_aprox, elapsed)

            if detectado:
                total_detectados += 1
                detecciones_por_audio[audio_id].add(script_name)

                fecha_audio = fecha_desde_nombre(nombre_archivo)
                if fecha_audio not in resultados_por_script[script_name]:
                    resultados_por_script[script_name][fecha_audio] = []

                detecciones_script.append({
                    "id_interaccion":    id_interaccion,
                    "linea_cliente":     linea_cliente,
                    "turnos":            len(conversacion),
                    "frase":             None,
                    "duracion_llamada":  duracion_llamada,
                    "turno_llm":         len(segs_recortados),
                    "cant_tokens":       tokens_aprox,
                    "tiempo_inferencia": elapsed,
                })

        estadisticas_por_script[script_name]["total_analizados"] = total_analizados
        estadisticas_por_script[script_name]["total_detectados"] = total_detectados

        log.info("[%s] Analizados: %d | Detectados: %d",
                 script_name, total_analizados, total_detectados)

        # ── Subir resultado del script a MinIO ────────────────────────────────
        fecha_fin_script = datetime.now(timezone.utc).isoformat()

        # Agrupamos todas las detecciones bajo la fecha del run (no la del audio)
        # para que el archivo de output sea uno por script por run
        fecha_run = datetime.now().strftime("%Y-%m-%d")
        output_key = f"analisis-raw/{fecha_run}/{script_name}_{run_id}.json"

        output_json = {
            "script":             script_name,
            "tipo":               "llm",
            "run_id":             run_id,
            "fecha_ejecucion":    fecha_inicio,
            "modelo":             modelo,
            "estados_procesados": estados_a_procesar,
            "total_analizados":   total_analizados,
            "total_detectados":   total_detectados,
            "detecciones":        detecciones_script,
        }

        try:
            with tempfile.TemporaryDirectory() as tmp:
                out_path = str(Path(tmp) / "output.json")
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(output_json, f, ensure_ascii=False, indent=2)
                minio_client.fput_object(
                    MINIO_BUCKET, output_key, out_path,
                    content_type="application/json",
                )
            log.info("Output subido: %s", output_key)
        except S3Error as e:
            log.error("Error subiendo output de script '%s': %s", script_name, e)

    # ── Actualizar PostgreSQL por audio ───────────────────────────────────────
    fecha_fin = datetime.now(timezone.utc).isoformat()
    scripts_ejecutados = list(scripts_defs.keys())

    with psycopg2.connect(SCORING_DB_URL) as conn:
        for audio in audios:
            audio_id = str(audio["id"])

            detectados_en_audio = sorted(detecciones_por_audio.get(audio_id, set()))
            hubo_error = errores_por_audio.get(audio_id, False)
            estado = "error" if hubo_error else "correcto"

            llm_entry = {
                "estado":             estado,
                "fecha_inicio":       fecha_inicio,
                "fecha_fin":          fecha_fin,
                "run_id":             run_id,
                "modelo":             modelo,
                "scripts_ejecutados": scripts_ejecutados,
                "detecciones":        detectados_en_audio,
            }

            try:
                actualizar_postgres_audio(conn, audio_id, llm_entry)
                log.debug("Postgres actualizado para audio %s — estado=%s detecciones=%s",
                          audio["nombre_archivo"], estado, detectados_en_audio)
            except Exception as e:
                log.error("Error actualizando Postgres para audio %s: %s",
                          audio["nombre_archivo"], e)

    # Resumen final
    log.info("=== Finalizado — run_id: %s ===", run_id)
    for script_name in scripts_ejecutados:
        st = estadisticas_por_script[script_name]
        log.info("  %s: %d analizados | %d detectados",
                 script_name, st["total_analizados"], st["total_detectados"])

    # Evitar leak de nanobind/xgrammar de vLLM que causa que Airflow marque
    # la tarea como fallida aunque el procesamiento haya terminado correctamente.
    import os as _os
    _os._exit(0)


if __name__ == "__main__":
    main()
