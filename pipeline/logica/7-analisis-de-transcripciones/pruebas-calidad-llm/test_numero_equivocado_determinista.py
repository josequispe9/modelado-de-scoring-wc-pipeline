"""
Detección determinista de llamadas a números equivocados.
Solo detecta casos donde quien atendió NO es el titular de la línea
(línea en nombre de otro, ya no es titular, número cambió de dueño).
NO incluye ausencias temporales ("no está mi mamá").

Uso:
    python test_numero_equivocado_determinista.py                    # outputs6-determinista.txt
    python test_numero_equivocado_determinista.py mi_output.txt
"""

import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR   = Path(__file__).parent
EJEMPLOS_DIR = SCRIPT_DIR / "ejemplos_transcripciones"
PRIMEROS_N   = 20

# Frases que indican que el número marcado era equivocado
FRASES_EQUIVOCADO = [
    "equivocado",
    "equivocada",
]


def detectar_numero_equivocado(conversacion: list[dict], primeros_n: int) -> tuple[bool, str | None]:
    for turno in conversacion[:primeros_n]:
        texto = turno.get("texto", "")
        texto_lower = texto.lower()

        for frase in FRASES_EQUIVOCADO:
            if frase in texto_lower:
                return True, texto[:120]

    return False, None


def main():
    output_name = sys.argv[1] if len(sys.argv) > 1 else "outputs6-determinista.txt"
    output_file = SCRIPT_DIR / output_name
    archivos    = sorted(EJEMPLOS_DIR.glob("*.json"))

    si_count = 0
    no_count = 0
    resultados = []

    for archivo in archivos:
        with open(archivo, encoding="utf-8") as f:
            data = json.load(f)
        conv = data.get("conversacion", [])

        es_equivocado, frase = detectar_numero_equivocado(conv, PRIMEROS_N)

        if es_equivocado:
            si_count += 1
        else:
            no_count += 1

        resultados.append({
            "archivo":           archivo.name,
            "n_turnos":          len(conv),
            "numero_equivocado": "si" if es_equivocado else "no",
            "frase_detectada":   frase,
        })

    with open(output_file, "w", encoding="utf-8") as f:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"RESULTADOS DETERMINISTAS NÚMERO EQUIVOCADO — {ts}\n")
        f.write(f"Archivos         : {len(archivos)}\n")
        f.write(f"Primeros N turnos: {PRIMEROS_N}\n")
        f.write("=" * 72 + "\n\n")

        for r in resultados:
            if r["numero_equivocado"] == "no":
                continue
            f.write(f"  [{r['archivo']}]\n")
            f.write(f"  Turnos: {r['n_turnos']}\n")
            f.write(f"  Frase: \"{r['frase_detectada']}\"\n\n")

        f.write("=" * 72 + "\n")
        f.write(f"RESUMEN: {si_count} números equivocados | {no_count} normales\n")

    print(f"Archivos analizados  : {len(archivos)}")
    print(f"Números equivocados  : {si_count}")
    print(f"Normales             : {no_count}")
    print(f"Output: {output_file}")


if __name__ == "__main__":
    main()
