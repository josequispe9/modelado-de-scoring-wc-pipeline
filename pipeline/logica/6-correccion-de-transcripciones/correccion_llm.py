"""
Etapa 6b — Corrección de transcripciones (scoring con vLLM).

Para cada (audio, grupo) ya evaluado por correccion_determinista.py
que no sea 'invalido' y aún no tenga coherencia_llm:
  1. Descarga el JSON de transcripción desde MinIO
  2. Formatea una muestra de segmentos (inicio + fin)
  3. Llama al LLM para evaluar coherencia del diálogo
  4. Si es coherente, llama al LLM para identificar vendedor/cliente
  5. Calcula score_llm y score_total ponderado
  6. Guarda el resultado en etapas.correccion_transcripciones.<grupo>

El modelo vLLM se carga una sola vez al inicio. Corre en las 3 PCs con GPU.

Uso:
    CUENTA=G python correccion_llm.py   # o M / B

Requiere:
    - .env.tuberia en la raíz del proyecto
    - pip install vllm minio psycopg2-binary python-dotenv
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

from config_llm import DEFAULTS

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

CUENTA         = os.environ.get("CUENTA", "G")
MINIO_BUCKET   = "modelado-de-scoring-wc"
SCORING_DB_URL = os.environ["SCORING_DB_URL"]

minio_client = Minio(
    os.environ["MINIO_ENDPOINT"],
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=False,
)

# ─── JSON Schemas para guided decoding ────────────────────────────────────────
SCHEMA_COHERENCIA = {
    "type": "object",
    "properties": {
        "coherencia": {"type": "string", "enum": ["coherente", "incoherente", "dudoso"]}
    },
    "required": ["coherencia"]
}

SCHEMA_ROLES = {
    "type": "object",
    "properties": {
        "vendedor": {"type": "string", "enum": ["SPEAKER_00", "SPEAKER_01", "desconocido"]},
        "cliente":  {"type": "string", "enum": ["SPEAKER_00", "SPEAKER_01", "desconocido"]}
    },
    "required": ["vendedor", "cliente"]
}


# ─── Parámetros ───────────────────────────────────────────────────────────────
def obtener_params() -> dict:
    clave = f"correccion_transcripciones_llm_{CUENTA}"
    try:
        with psycopg2.connect(SCORING_DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT valor FROM pipeline_params WHERE clave = %s",
                    (clave,)
                )
                row = cur.fetchone()
        if row and row[0]:
            params = DEFAULTS.copy()
            params.update(row[0])
            log.info("Params cargados desde Postgres (clave=%s)", clave)
            return params
    except Exception as e:
        log.warning("No se pudo leer pipeline_params: %s — usando DEFAULTS", e)
    return DEFAULTS.copy()


# ─── Carga del modelo vLLM ────────────────────────────────────────────────────
def cargar_modelo(modelo: str, gpu_memory_utilization: float = 0.75, max_model_len: int = 2048):
    """Carga el modelo vLLM una sola vez. Retorna None si usar_llm=False."""
    from vllm import LLM
    log.info("Cargando modelo vLLM: %s (gpu_memory_utilization=%.2f, max_model_len=%d)", modelo, gpu_memory_utilization, max_model_len)
    llm = LLM(model=modelo, gpu_memory_utilization=gpu_memory_utilization, max_model_len=max_model_len, enforce_eager=True)
    log.info("Modelo cargado")
    return llm


# ─── Query SKIP LOCKED ────────────────────────────────────────────────────────
def obtener_siguiente_audio(conn, params: dict) -> dict | None:
    """
    Obtiene el siguiente (audio, grupo) con score determinista != invalido
    que aún no tenga coherencia_llm en su clave de correccion_transcripciones.

    Itera sobre todas las claves de correccion_transcripciones (todos los grupos)
    igual que la etapa 4 hace con normalizacion — sin filtrar por PC.
    """
    dur_col   = "COALESCE(apj.duracion_conversacion_seg, apj.duracion_audio_seg, 0)"
    dur_conds = ""
    if params.get("duracion_desde") is not None:
        dur_conds += f" AND {dur_col} >= {int(params['duracion_desde'])}"
    if params.get("duracion_hasta") is not None:
        dur_conds += f" AND {dur_col} <= {int(params['duracion_hasta'])}"

    query = f"""
        SELECT
            apj.id,
            apj.nombre_archivo,
            apj.etapas,
            apj.duracion_conversacion_seg,
            ct_entry.key   AS grupo,
            ct_entry.value AS corr_entry
        FROM audio_pipeline_jobs apj,
             jsonb_each(
               COALESCE(apj.etapas->'correccion_transcripciones', '{{}}'::jsonb)
             ) AS ct_entry
        WHERE apj.etapa_actual = 'correccion_transcripciones'
          AND apj.estado_global != 'en_proceso'
          {dur_conds}
          AND (ct_entry.value->>'clasificacion_determinista') != 'invalido'
          AND (ct_entry.value->>'coherencia_llm') IS NULL
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


# ─── Formateo de muestra ──────────────────────────────────────────────────────
def formatear_muestra(data: dict, max_inicio: int, max_fin: int) -> str:
    """
    Genera texto plano con los primeros `max_inicio` + últimos `max_fin` segmentos.
    Formato: SPEAKER_XX: texto
    """
    segments = data.get("segments", [])
    if len(segments) <= max_inicio + max_fin:
        muestra = segments
    else:
        muestra = segments[:max_inicio] + segments[-max_fin:]

    lineas = []
    for seg in muestra:
        speaker = seg.get("speaker", "SPEAKER_00")
        texto   = seg.get("text", "").strip()
        if texto:
            lineas.append(f"{speaker}: {texto}")
    return "\n".join(lineas)


# ─── Llamadas al LLM ─────────────────────────────────────────────────────────
def evaluar_coherencia(llm, texto: str, params) -> str:
    """
    Llama al LLM para evaluar si el diálogo es coherente.
    Retorna: 'coherente' | 'incoherente' | 'dudoso'
    """
    from vllm import SamplingParams
    from vllm.sampling_params import StructuredOutputsParams

    prompt = (
        "Eres un evaluador de calidad de transcripciones de llamadas de venta.\n"
        "La transcripción siempre corresponde a una llamada de venta en español. "
        "Tu única tarea es detectar si la transcripción está corrupta.\n\n"
        "Considera 'incoherente' si:\n"
        "- El texto contiene caracteres aleatorios, símbolos extraños o es ilegible\n"
        "- Está en otro idioma (no español)\n"
        "- Es repetición de la misma palabra o frase sin sentido\n\n"
        "Considera 'dudoso' si solo una parte del texto tiene esos problemas.\n\n"
        "Considera 'coherente' en cualquier otro caso, incluso si la llamada "
        "es corta, el cliente rechaza, hay silencio o la conversación no resulta en venta.\n\n"
        f"Conversación:\n{texto}\n\n"
        "Responde en JSON."
    )

    guided = StructuredOutputsParams(json=SCHEMA_COHERENCIA)
    sampling = SamplingParams(
        temperature=0.0,
        max_tokens=50,
        structured_outputs=guided,
    )
    output = llm.generate([prompt], sampling_params=sampling)
    resultado = json.loads(output[0].outputs[0].text)
    return resultado["coherencia"]


def evaluar_roles(llm, texto: str) -> dict:
    """
    Llama al LLM para identificar vendedor y cliente.
    Retorna dict con 'vendedor' y 'cliente'.
    """
    from vllm import SamplingParams
    from vllm.sampling_params import StructuredOutputsParams

    prompt = (
        "Eres un evaluador de transcripciones de llamadas de ventas.\n"
        "En la siguiente conversación, identifica qué speaker es el vendedor "
        "y cuál es el cliente.\n\n"
        "El vendedor suele: presentarse, ofrecer productos/servicios, hacer preguntas de calificación.\n"
        "El cliente suele: responder preguntas, expresar necesidades o dudas, decidir.\n\n"
        f"Conversación:\n{texto}\n\n"
        "Responde solo con SPEAKER_00, SPEAKER_01, o 'desconocido'. Responde en JSON."
    )

    guided = StructuredOutputsParams(json=SCHEMA_ROLES)
    sampling = SamplingParams(
        temperature=0.0,
        max_tokens=80,
        structured_outputs=guided,
    )
    output = llm.generate([prompt], sampling_params=sampling)
    return json.loads(output[0].outputs[0].text)


# ─── Cálculo de score LLM ────────────────────────────────────────────────────
def calcular_score_llm(coherencia: str, roles: dict | None) -> float:
    """
    score_llm basado en coherencia e identificación de roles.
    - incoherente → 0.0
    - dudoso       → 0.3
    - coherente sin roles claros → 0.7
    - coherente con roles identificados → 0.9–1.0
    """
    if coherencia == "incoherente":
        return 0.0
    if coherencia == "dudoso":
        return 0.3
    # coherente
    if roles is None:
        return 0.7
    vendedor = roles.get("vendedor", "desconocido")
    cliente  = roles.get("cliente", "desconocido")
    if vendedor != "desconocido" and cliente != "desconocido" and vendedor != cliente:
        return 1.0
    if vendedor != "desconocido" or cliente != "desconocido":
        return 0.85
    return 0.7


# ─── Actualización de Postgres ────────────────────────────────────────────────
def actualizar_registro(conn, audio_id: str, grupo: str,
                        score_determinista: float,
                        resultado_llm: dict, params: dict) -> None:
    """
    Actualiza etapas.correccion_transcripciones.<grupo> con los resultados LLM
    y el score_total ponderado.
    """
    coherencia = resultado_llm["coherencia_llm"]
    score_llm  = resultado_llm["score_llm"]

    score_total = round(
        params["peso_score_determinista"] * score_determinista +
        params["peso_score_llm"]          * score_llm,
        4
    )

    if score_total >= params["umbral_score_correcto"]:
        clasificacion = "correcto"
    elif score_total >= params["umbral_score_reprocesar"]:
        clasificacion = "reprocesar"
    else:
        clasificacion = "invalido"

    resultado_llm["score_determinista"] = score_determinista
    resultado_llm["score_total"]        = score_total
    resultado_llm["clasificacion"]      = clasificacion

    with conn.cursor() as cur:
        cur.execute(
            "SELECT etapas->'correccion_transcripciones' FROM audio_pipeline_jobs WHERE id = %s",
            (audio_id,)
        )
        row = cur.fetchone()
        correccion = row[0] if row and row[0] else {}
        if not isinstance(correccion, dict):
            correccion = {}

        if grupo not in correccion:
            correccion[grupo] = {}
        correccion[grupo].update(resultado_llm)

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
    params = obtener_params()
    usar_llm = params.get("usar_llm", True)

    log.info("Cuenta: %s | Modelo: %s | usar_llm: %s",
             CUENTA, params.get("modelo"), usar_llm)

    llm = cargar_modelo(
        params["modelo"],
        gpu_memory_utilization=params.get("gpu_memory_utilization", 0.75),
        max_model_len=int(params.get("max_model_len", 2048)),
    ) if usar_llm else None

    procesados  = 0
    correctos   = 0
    reprocesar  = 0
    invalidos   = 0
    errores     = 0

    with psycopg2.connect(SCORING_DB_URL) as conn:
        while True:
            audio = obtener_siguiente_audio(conn, params)
            if not audio:
                break

            audio_id   = str(audio["id"])
            nombre     = audio["nombre_archivo"]
            grupo      = audio["grupo"]
            corr_entry = audio.get("corr_entry") or {}

            score_determinista = corr_entry.get("score_determinista", 0.0)
            input_key = (corr_entry.get("ubicacion_transcripcion") or {}).get("key")

            if not input_key:
                log.warning("Sin ubicacion_transcripcion para %s [grupo=%s]", nombre, grupo)
                continue

            log.info("Procesando LLM: %s [grupo=%s score_det=%.4f]",
                     nombre, grupo, score_determinista)

            fecha_inicio = datetime.now(timezone.utc).isoformat()

            with tempfile.TemporaryDirectory() as tmp:
                json_tmp = str(Path(tmp) / "transcripcion.json")

                try:
                    minio_client.fget_object(MINIO_BUCKET, input_key, json_tmp)
                except S3Error as e:
                    log.error("Error descargando %s: %s", input_key, e)
                    errores += 1
                    continue

                try:
                    with open(json_tmp, encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as e:
                    log.error("Error leyendo JSON %s: %s", input_key, e)
                    errores += 1
                    continue

            texto_muestra = formatear_muestra(
                data,
                params.get("max_segmentos_inicio", 30),
                params.get("max_segmentos_fin", 20),
            )

            resultado_llm = {
                "coherencia_llm":   None,
                "vendedor":         None,
                "cliente":          None,
                "score_llm":        0.0,
                "modelo_llm":       params["modelo"],
                "fecha_evaluacion": fecha_inicio,
            }

            if not usar_llm:
                # Modo debug: asigna score_llm neutro
                resultado_llm["coherencia_llm"] = "coherente"
                resultado_llm["score_llm"]       = 0.7
                log.info("usar_llm=False — score_llm neutro para %s", nombre)
            else:
                try:
                    coherencia = evaluar_coherencia(llm, texto_muestra, params)
                    resultado_llm["coherencia_llm"] = coherencia
                    log.info("Coherencia %s [grupo=%s]: %s", nombre, grupo, coherencia)

                    if coherencia == "incoherente":
                        resultado_llm["score_llm"] = 0.0
                    elif coherencia == "dudoso":
                        resultado_llm["score_llm"] = 0.3
                    else:
                        # Llamada 2: identificación de roles
                        roles = evaluar_roles(llm, texto_muestra)
                        resultado_llm["vendedor"] = roles.get("vendedor")
                        resultado_llm["cliente"]  = roles.get("cliente")
                        resultado_llm["score_llm"] = calcular_score_llm(coherencia, roles)
                        log.info("Roles %s: vendedor=%s cliente=%s",
                                 nombre, roles.get("vendedor"), roles.get("cliente"))

                except Exception as e:
                    log.error("Error en inferencia LLM para %s: %s", nombre, e)
                    resultado_llm["coherencia_llm"] = "dudoso"
                    resultado_llm["score_llm"]       = 0.3
                    errores += 1

            actualizar_registro(conn, audio_id, grupo,
                                score_determinista, resultado_llm, params)
            procesados += 1
            clasificacion = resultado_llm.get("clasificacion", "?")
            if clasificacion == "correcto":
                correctos += 1
            elif clasificacion == "reprocesar":
                reprocesar += 1
            else:
                invalidos += 1
            log.info("Guardado: %s [grupo=%s score_total=%.4f → %s]",
                     nombre, grupo,
                     resultado_llm.get("score_total", 0.0),
                     clasificacion)

    log.info("Finalizado — procesados: %d | correcto: %d | reprocesar: %d | invalido: %d | errores: %d",
             procesados, correctos, reprocesar, invalidos, errores)

    # Liberar el modelo explícitamente para evitar warnings de nanobind/xgrammar al salir
    if llm is not None:
        import gc
        del llm
        gc.collect()

    # os._exit(0) bypasea el shutdown de Python evitando que nanobind/NCCL
    # impriman en stderr y generen exit code != 0, lo que confunde a Airflow.
    import os as _os
    _os._exit(0)


if __name__ == "__main__":
    main()
