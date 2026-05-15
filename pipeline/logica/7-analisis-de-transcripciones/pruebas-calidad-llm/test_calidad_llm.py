"""
Prueba de calidad del LLM para etapa 7 — análisis de transcripciones.

Uso:
    python test_calidad_llm.py                          # usa inputs.txt  → outputs.txt
    python test_calidad_llm.py inputs2.txt outputs2.txt # usa inputs2.txt → outputs2.txt

Requiere vLLM y GPU disponible.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

# ─── Configuración del modelo ─────────────────────────────────────────────────
MODELO          = "Qwen/Qwen2.5-3B-Instruct-AWQ"
GPU_MEMORY_UTIL = 0.50
MAX_MODEL_LEN   = 4096

SCRIPT_DIR = Path(__file__).parent

# ─── Bloques de contexto reutilizables ────────────────────────────────────────
CTX_TRANSCRIPCION = (
    "IMPORTANTE: Esta transcripción fue generada automáticamente y puede contener "
    "errores ortográficos, palabras mal reconocidas o frases cortadas. "
    "No descartes un segmento solo porque tenga errores de tipeo."
)

CTX_DIARIZACION = (
    "IMPORTANTE: Los hablantes están marcados como DESCONOCIDO porque la diarización "
    "automática no identificó correctamente vendedor y cliente. "
    "El vendedor suele iniciar la llamada, presentar el producto y hacer preguntas. "
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


# ─── Parser de inputs.txt ─────────────────────────────────────────────────────
def parsear_inputs(path: Path) -> list[dict]:
    """
    Formato de cada test:
        [nombre_test]
        descripcion        = texto libre
        schema             = {...json en una sola linea...}
        conversacion_archivo  = ruta/relativa.json          (un solo archivo)
        conversaciones_dir    = ruta/relativa/directorio    (todos los .json del dir)
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


# ─── Carga y formateo de conversación ─────────────────────────────────────────
def cargar_conversacion(path: Path) -> list[dict]:
    """Carga el JSON y devuelve solo la lista conversacion[], sin metadata."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("conversacion", [])


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


# ─── Construcción del prompt ──────────────────────────────────────────────────
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


# ─── Inferencia sobre un archivo ─────────────────────────────────────────────
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
    except Exception as e:
        return False, raw, None, elapsed


# ─── Ejecutar test contra uno o varios archivos ───────────────────────────────
def ejecutar_test(llm, test: dict, script_dir: Path) -> list[dict]:
    schema     = json.loads(test["schema"])
    segmento   = test.get("segmento", "todo_40")
    max_tokens = int(test.get("max_tokens", 100))
    min_turnos = int(test.get("min_turnos", 1))

    # Resolver lista de archivos
    archivos: list[Path] = []
    if "conversaciones_dir" in test:
        dir_path = (script_dir / test["conversaciones_dir"]).resolve()
        archivos = sorted(p for p in dir_path.glob("*.json"))
    elif "conversacion_archivo" in test:
        archivos = [(script_dir / test["conversacion_archivo"]).resolve()]
    else:
        raise ValueError(f"Test '{test['nombre']}': falta conversacion_archivo o conversaciones_dir")

    resultados = []
    for archivo in archivos:
        conv = cargar_conversacion(archivo)

        if len(conv) < min_turnos:
            resultados.append({
                "archivo":   archivo.name,
                "n_turnos":  len(conv),
                "omitido":   f"menos de {min_turnos} turnos",
            })
            continue

        segs_recortados = aplicar_segmento(conv, segmento)
        conv_txt        = formatear_segmentos(segs_recortados)
        prompt          = construir_prompt(test, conv_txt)
        tokens_aprox    = len(prompt.split())

        try:
            valido, raw, obj, elapsed = inferir(llm, prompt, schema, max_tokens)
            resultados.append({
                "archivo":      archivo.name,
                "n_turnos":     len(conv),
                "n_turnos_llm": len(segs_recortados),
                "tokens_aprox": tokens_aprox,
                "tiempo_seg":   elapsed,
                "valido":       valido,
                "raw":          raw if not valido else None,
                "resultado":    obj,
            })
        except Exception as e:
            resultados.append({
                "archivo":    archivo.name,
                "n_turnos":   len(conv),
                "excepcion":  str(e),
            })

    return resultados


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    args         = sys.argv[1:]
    inputs_file  = SCRIPT_DIR / (args[0] if len(args) > 0 else "inputs.txt")
    outputs_file = SCRIPT_DIR / (args[1] if len(args) > 1 else "outputs.txt")

    print(f"Inputs : {inputs_file.name}")
    print(f"Outputs: {outputs_file.name}")
    print(f"Cargando modelo: {MODELO} ...")

    from vllm import LLM
    llm = LLM(
        model=MODELO,
        gpu_memory_utilization=GPU_MEMORY_UTIL,
        max_model_len=MAX_MODEL_LEN,
        enforce_eager=True,
    )
    print("Modelo listo.\n")

    tests = parsear_inputs(inputs_file)
    print(f"Tests encontrados: {len(tests)}\n")

    todos_resultados = []
    for i, test in enumerate(tests, 1):
        nombre = test.get("nombre", f"test_{i}")
        print(f"[{i}/{len(tests)}] {nombre} ...")
        try:
            filas = ejecutar_test(llm, test, SCRIPT_DIR)
        except Exception as e:
            print(f"  ERROR en test: {e}")
            filas = [{"excepcion_test": str(e)}]

        ok      = sum(1 for r in filas if r.get("valido") is True)
        omitidos = sum(1 for r in filas if "omitido" in r)
        errores  = sum(1 for r in filas if "excepcion" in r or r.get("valido") is False)
        print(f"  {len(filas)} archivos → {ok} OK | {omitidos} omitidos | {errores} errores")

        todos_resultados.append({"test": test, "filas": filas})

    # ── Escribir outputs ──────────────────────────────────────────────────────
    with open(outputs_file, "w", encoding="utf-8") as f:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"RESULTADOS — {ts}\n")
        f.write(f"Modelo : {MODELO}\n")
        f.write(f"Inputs : {inputs_file.name}\n")
        f.write("=" * 72 + "\n\n")

        for bloque in todos_resultados:
            test  = bloque["test"]
            filas = bloque["filas"]

            f.write(f"╔══ TEST: {test['nombre']}\n")
            f.write(f"║  Descripcion : {test.get('descripcion','')}\n")
            f.write(f"║  Segmento    : {test.get('segmento','todo_40')}\n")
            f.write(f"║  Contexto    : {test.get('contexto','ninguno')}\n")
            f.write(f"║  Archivos    : {len(filas)}\n")
            f.write("╚" + "═" * 71 + "\n\n")

            for r in filas:
                f.write(f"  [{r['archivo']}]\n")

                if "omitido" in r:
                    f.write(f"  OMITIDO: {r['omitido']}  ({r['n_turnos']} turnos)\n")
                elif "excepcion_test" in r:
                    f.write(f"  EXCEPCION EN TEST: {r['excepcion_test']}\n")
                elif "excepcion" in r:
                    f.write(f"  EXCEPCION: {r['excepcion']}\n")
                elif not r.get("valido"):
                    f.write(f"  JSON INVALIDO — {r['n_turnos']} turnos | ~{r.get('tokens_aprox','?')} tokens | {r.get('tiempo_seg','?')}s\n")
                    f.write(f"  Raw: {r.get('raw','')[:200]}\n")
                else:
                    f.write(f"  Turnos conv: {r['n_turnos']}  |  turnos al LLM: {r['n_turnos_llm']}  |  ~{r['tokens_aprox']} tokens  |  {r['tiempo_seg']}s\n")
                    f.write(f"  {json.dumps(r['resultado'], ensure_ascii=False)}\n")

                f.write("\n")

            # Resumen del test
            ok       = sum(1 for r in filas if r.get("valido") is True)
            omitidos = sum(1 for r in filas if "omitido" in r)
            errores  = sum(1 for r in filas if "excepcion" in r or r.get("valido") is False)
            f.write(f"  RESUMEN: {ok} OK | {omitidos} omitidos | {errores} errores\n")
            f.write("─" * 72 + "\n\n")

    print(f"\nResultados escritos en: {outputs_file}")

    import gc
    del llm
    gc.collect()
    import os as _os
    _os._exit(0)


if __name__ == "__main__":
    main()
