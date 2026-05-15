"""
Detección determinista de clientes hartos de recibir llamadas (rellamados).
No usa LLM — busca frases y patrones clave en los primeros N turnos.

Uso:
    python test_rellamado_determinista.py                        # outputs4-determinista.txt
    python test_rellamado_determinista.py mi_output.txt          # nombre custom
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR   = Path(__file__).parent
EJEMPLOS_DIR = SCRIPT_DIR / "ejemplos_transcripciones"
PRIMEROS_N   = 30

# Frases literales (lowercase, substring)
FRASES_RELLAMADO = [
    "no me llamen",
    "no me llames",
    "no me llame ",
    "no me vuelvan a llamar",
    "no me vuelvas a llamar",
    "dejen de llamar",
    "deja de llamar",
    "dejen de molestar",
    "saquen del sistema",
    "sacarme del sistema",
    "base de datos",
    "ya les dije",
    "ya le dije",
    "ya te dije",
    "ya les pedí",
    "ya pedí",
    "mil veces",
    "muchas veces",
    "varias veces",
    "veces por día",
    "veces al día",
    "llamados por día",
    "llamados al día",
    "todo el día me llaman",
    "todos los días me llaman",
    "todos los días le digo",
    "no sé cómo pedirles",
    "no se como pedirles",
    "no sé de qué forma",
    "no se de que forma",
    "spamean",
    "me tienen harto",
    "me tienen cansado",
    "estoy harto",
    "estoy cansado de que",
    "agotador",
    "acaban de llamar",
    "recién me llamaron",
    "me llamaron recién",
    "me llamó recién",
    "recién me llamó",
]

# Patrones regex para cantidades de llamadas (números dígitos o palabras)
PATRONES_CANTIDAD = [
    r"\d{2,}\s*veces",                          # "20 veces", "150 veces"
    r"\d+\s*llamad[oa]s",                       # "5 llamados", "10 llamadas"
    r"\d+\s*veces\s*(por|al)\s*día",
    r"\d+\s*llamad[oa]s\s*(por|al)\s*día",
    r"llam\w+.{0,30}(dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|veinte|treinta)\s+veces",  # "llamaron cuatro veces"
    r"(dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|veinte|treinta)\s+veces.{0,30}llam",      # "cuatro veces que me llaman"
    r"(dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|veinte|treinta)\s+llamad[oa]s",
]


def detectar_rellamado(conversacion: list[dict], primeros_n: int) -> tuple[bool, str | None]:
    turnos = conversacion[:primeros_n]
    for turno in turnos:
        texto = turno.get("texto", "")
        texto_lower = texto.lower()

        for frase in FRASES_RELLAMADO:
            if frase in texto_lower:
                return True, texto[:120]

        for patron in PATRONES_CANTIDAD:
            if re.search(patron, texto_lower):
                return True, texto[:120]

    return False, None


def main():
    output_name = sys.argv[1] if len(sys.argv) > 1 else "outputs4-determinista.txt"
    output_file = SCRIPT_DIR / output_name
    archivos    = sorted(EJEMPLOS_DIR.glob("*.json"))

    si_count  = 0
    no_count  = 0
    resultados = []

    for archivo in archivos:
        with open(archivo, encoding="utf-8") as f:
            data = json.load(f)
        conv = data.get("conversacion", [])

        es_rellamado, frase = detectar_rellamado(conv, PRIMEROS_N)

        if es_rellamado:
            si_count += 1
        else:
            no_count += 1

        resultados.append({
            "archivo":       archivo.name,
            "n_turnos":      len(conv),
            "es_rellamado":  "si" if es_rellamado else "no",
            "frase_detectada": frase,
        })

    with open(output_file, "w", encoding="utf-8") as f:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"RESULTADOS DETERMINISTAS RELLAMADO — {ts}\n")
        f.write(f"Archivos        : {len(archivos)}\n")
        f.write(f"Primeros N turnos: {PRIMEROS_N}\n")
        f.write("=" * 72 + "\n\n")

        for r in resultados:
            if r["es_rellamado"] == "no":
                continue
            f.write(f"  [{r['archivo']}]\n")
            f.write(f"  Turnos: {r['n_turnos']}  |  es_rellamado: {r['es_rellamado']}\n")
            if r["frase_detectada"]:
                f.write(f"  Frase: \"{r['frase_detectada']}\"\n")
            f.write("\n")

        f.write("=" * 72 + "\n")
        f.write(f"RESUMEN: {si_count} rellamados | {no_count} normales\n")

    print(f"Archivos analizados : {len(archivos)}")
    print(f"Rellamados (si)     : {si_count}")
    print(f"Normales (no)       : {no_count}")
    print(f"Output: {output_file}")


if __name__ == "__main__":
    main()
