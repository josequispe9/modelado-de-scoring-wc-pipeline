"""
Detección determinista de clientes con problemas de señal/cobertura de Movistar.
IMPORTANTE: solo detecta cuando el problema de señal refiere explícitamente a Movistar
en el mismo turno. Evita falsos positivos de clientes que hablan de problemas de señal
con Claro u otra empresa.

Uso:
    python test_problema_senal_determinista.py                    # outputs9-determinista.txt
    python test_problema_senal_determinista.py mi_output.txt
"""

import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR   = Path(__file__).parent
EJEMPLOS_DIR = SCRIPT_DIR / "ejemplos_transcripciones"
PRIMEROS_N   = 40

# Movistar y variantes frecuentes en transcripciones automáticas
MOVISTAR = ["movistar", "modestar"]

# Frases inequívocas de problema de señal/cobertura
FRASES_PROBLEMA = [
    "no tengo señal",
    "no tenia señal",
    "no tenía señal",
    "no tiene señal",
    "nunca tuve señal",
    "mala señal",
    "sin señal",
    "no hay señal",
    "no tengo cobertura",
    "no hay cobertura",
    "falta de cobertura",
    "sin cobertura",
    "mala cobertura",
    "no tenía cobertura",
    "no tenía buena señal",
    "no llega la fibra",
    "no me llega la fibra",
]


def detectar_problema_senal(conversacion: list[dict], primeros_n: int) -> tuple[bool, str | None]:
    for turno in conversacion[:primeros_n]:
        texto = turno.get("texto", "")
        texto_lower = texto.lower()

        tiene_movistar = any(m in texto_lower for m in MOVISTAR)
        tiene_problema = any(p in texto_lower for p in FRASES_PROBLEMA)

        if tiene_movistar and tiene_problema:
            return True, texto[:120]

    return False, None


def main():
    output_name = sys.argv[1] if len(sys.argv) > 1 else "outputs9-determinista.txt"
    output_file = SCRIPT_DIR / output_name
    archivos    = sorted(EJEMPLOS_DIR.glob("*.json"))

    si_count = 0
    no_count = 0
    resultados = []

    for archivo in archivos:
        with open(archivo, encoding="utf-8") as f:
            data = json.load(f)
        conv = data.get("conversacion", [])

        es_problema, frase = detectar_problema_senal(conv, PRIMEROS_N)

        if es_problema:
            si_count += 1
        else:
            no_count += 1

        resultados.append({
            "archivo":        archivo.name,
            "n_turnos":       len(conv),
            "problema_senal": "si" if es_problema else "no",
            "frase_detectada": frase,
        })

    with open(output_file, "w", encoding="utf-8") as f:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"RESULTADOS DETERMINISTAS PROBLEMA DE SEÑAL — {ts}\n")
        f.write(f"Archivos         : {len(archivos)}\n")
        f.write(f"Primeros N turnos: {PRIMEROS_N}\n")
        f.write("=" * 72 + "\n\n")

        for r in resultados:
            if r["problema_senal"] == "no":
                continue
            f.write(f"  [{r['archivo']}]\n")
            f.write(f"  Turnos: {r['n_turnos']}\n")
            f.write(f"  Frase: \"{r['frase_detectada']}\"\n\n")

        f.write("=" * 72 + "\n")
        f.write(f"RESUMEN: {si_count} con problema de señal | {no_count} sin problema\n")

    print(f"Archivos analizados  : {len(archivos)}")
    print(f"Problema de señal    : {si_count}")
    print(f"Sin problema         : {no_count}")
    print(f"Output: {output_file}")


if __name__ == "__main__":
    main()
