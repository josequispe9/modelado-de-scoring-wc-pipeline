"""
Detección determinista de contestadores automáticos.
No usa LLM — busca frases clave en los primeros N turnos.

Uso:
    python test_contestador_determinista.py                        # outputs3-determinista.txt
    python test_contestador_determinista.py mi_output.txt          # nombre custom
"""

import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR   = Path(__file__).parent
EJEMPLOS_DIR = SCRIPT_DIR / "ejemplos_transcripciones"
PRIMEROS_N   = 20  # turnos a revisar (igual que los tests LLM)

# Frases que delatan un contestador automático (lowercase, se busca por substring)
FRASES_CONTESTADOR = [
    "después del tono",
    "despues del tono",
    "deja tu mensaje",
    "deje su mensaje",
    "deje un mensaje",
    "buzón de voz",
    "buzon de voz",
    "casilla de mensajes",
    "casilla de voz",
    "para finalizar, corta",
    "marca la tecla numeral",
    "asistente de llamadas",
    "no está disponible en este momento",
    "bienvenido al buzón",
    "bienvenido al buzon",
    "usted está comunicado con la casilla",
    "usted esta comunicado con la casilla",
]


def detectar_contestador(conversacion: list[dict], primeros_n: int) -> tuple[bool, str | None]:
    """
    Revisa los primeros N turnos. Devuelve (es_contestador, frase_encontrada).
    """
    turnos = conversacion[:primeros_n]
    for turno in turnos:
        texto = turno.get("texto", "").lower()
        for frase in FRASES_CONTESTADOR:
            if frase in texto:
                return True, frase
    return False, None


def main():
    output_name  = sys.argv[1] if len(sys.argv) > 1 else "outputs3-determinista.txt"
    output_file  = SCRIPT_DIR / output_name
    archivos     = sorted(EJEMPLOS_DIR.glob("*.json"))

    si_count  = 0
    no_count  = 0
    resultados = []

    for archivo in archivos:
        with open(archivo, encoding="utf-8") as f:
            data = json.load(f)
        conv = data.get("conversacion", [])

        es_contestador, frase = detectar_contestador(conv, PRIMEROS_N)

        if es_contestador:
            si_count += 1
        else:
            no_count += 1

        resultados.append({
            "archivo":        archivo.name,
            "n_turnos":       len(conv),
            "es_contestador": "si" if es_contestador else "no",
            "frase_detectada": frase,
        })

    # ── Escribir output ──────────────────────────────────────────────────────
    with open(output_file, "w", encoding="utf-8") as f:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"RESULTADOS DETERMINISTAS — {ts}\n")
        f.write(f"Archivos  : {len(archivos)}\n")
        f.write(f"Primeros N turnos: {PRIMEROS_N}\n")
        f.write("=" * 72 + "\n\n")

        for r in resultados:
            f.write(f"  [{r['archivo']}]\n")
            f.write(f"  Turnos: {r['n_turnos']}  |  es_contestador: {r['es_contestador']}")
            if r["frase_detectada"]:
                f.write(f"  |  frase: \"{r['frase_detectada']}\"\n")
            else:
                f.write("\n")
            f.write("\n")

        f.write("=" * 72 + "\n")
        f.write(f"RESUMEN: {si_count} contestadores | {no_count} personas reales\n")

    print(f"Archivos analizados : {len(archivos)}")
    print(f"Contestadores (si)  : {si_count}")
    print(f"Personas reales (no): {no_count}")
    print(f"Output: {output_file}")


if __name__ == "__main__":
    main()
