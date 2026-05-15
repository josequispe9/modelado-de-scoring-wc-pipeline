"""
Detección determinista de clientes que insultan durante la llamada.

Uso:
    python test_cliente_molesto_determinista.py                    # outputs5-determinista.txt
    python test_cliente_molesto_determinista.py mi_output.txt
"""

import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR   = Path(__file__).parent
EJEMPLOS_DIR = SCRIPT_DIR / "ejemplos_transcripciones"
PRIMEROS_N   = 40

INSULTOS = [
    "puta que te parió",
    "reconcha",
    "la concha",
    "concha de",
    "a cagar",
    "andate a cagar",
    "váyase a cagar",
    "vayase a cagar",
    "mierda",
    "boludo",
    "hdp",
    "hijo de puta",
    "hijo de p",
    "romper las pelotas",
    "los huevos llenos",
    "déjenme de joder",
    "dejenme de joder",
    "me tienen podrido",
    "imbécil",
    "imbecil",
    "idiota",
    "estúpido",
    "estupido",
    "pelotudo",
    "muertos de hambre",
    "miserables",
]


def detectar_insulto(conversacion: list[dict], primeros_n: int) -> tuple[bool, str | None]:
    for turno in conversacion[:primeros_n]:
        texto_lower = turno.get("texto", "").lower()
        for insulto in INSULTOS:
            if insulto in texto_lower:
                return True, turno["texto"][:120]
    return False, None


def main():
    output_name = sys.argv[1] if len(sys.argv) > 1 else "outputs5-determinista.txt"
    output_file = SCRIPT_DIR / output_name
    archivos    = sorted(EJEMPLOS_DIR.glob("*.json"))

    si_count = 0
    no_count = 0
    resultados = []

    for archivo in archivos:
        with open(archivo, encoding="utf-8") as f:
            data = json.load(f)
        conv = data.get("conversacion", [])

        es_insulto, frase = detectar_insulto(conv, PRIMEROS_N)

        if es_insulto:
            si_count += 1
        else:
            no_count += 1

        resultados.append({
            "archivo":         archivo.name,
            "n_turnos":        len(conv),
            "cliente_molesto": "si" if es_insulto else "no",
            "frase_detectada": frase,
        })

    with open(output_file, "w", encoding="utf-8") as f:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"RESULTADOS DETERMINISTAS INSULTOS — {ts}\n")
        f.write(f"Archivos         : {len(archivos)}\n")
        f.write(f"Primeros N turnos: {PRIMEROS_N}\n")
        f.write("=" * 72 + "\n\n")

        for r in resultados:
            if r["cliente_molesto"] == "no":
                continue
            f.write(f"  [{r['archivo']}]\n")
            f.write(f"  Turnos: {r['n_turnos']}\n")
            f.write(f"  Frase: \"{r['frase_detectada']}\"\n\n")

        f.write("=" * 72 + "\n")
        f.write(f"RESUMEN: {si_count} con insultos | {no_count} sin insultos\n")

    print(f"Archivos analizados : {len(archivos)}")
    print(f"Con insultos        : {si_count}")
    print(f"Sin insultos        : {no_count}")
    print(f"Output: {output_file}")


if __name__ == "__main__":
    main()
