"""
Detección determinista de clientes que ya son clientes de Movistar.
La campaña apunta a portar líneas de Claro/Personal a Movistar,
pero algunos contactos ya tienen Movistar — la venta no aplica.

Uso:
    python test_ya_tiene_movistar_determinista.py                    # outputs10-determinista.txt
    python test_ya_tiene_movistar_determinista.py mi_output.txt
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR   = Path(__file__).parent
EJEMPLOS_DIR = SCRIPT_DIR / "ejemplos_transcripciones"
PRIMEROS_N   = 20

FRASES_YA_TIENE = [
    # El "ya" o el contexto anclan la frase al cliente
    "soy movistar",
    "ya soy de movistar",
    "ya tengo movistar",
    "tengo movistar",
    "estoy con movistar",
    "estoy en movistar",
    "ya estoy con movistar",
    "ya estoy en movistar",
    "estoy usando movistar",
    "uso movistar",
    "tengo una línea de movistar",
    "tengo una linea de movistar",
    "tengo línea de movistar",
    "tengo linea de movistar",
    "soy cliente de movistar",
]

# Negaciones que invalidan el match (ej: "no tengo movistar", "no soy movistar")
PATRON_NEGACION = re.compile(r"\bno\b.{0,10}(tengo|soy|estoy|uso) movistar")


def detectar_ya_tiene_movistar(conversacion: list[dict], primeros_n: int) -> tuple[bool, str | None]:
    for turno in conversacion[:primeros_n]:
        texto = turno.get("texto", "")
        texto_lower = texto.lower()

        # Turnos muy largos son casi siempre el vendedor
        if len(texto) > 200:
            continue

        # Descartar negaciones ("no tengo movistar", etc.)
        if PATRON_NEGACION.search(texto_lower):
            continue

        for frase in FRASES_YA_TIENE:
            idx = texto_lower.find(frase)
            if idx == -1:
                continue
            # Descartar si la frase está dentro de una pregunta (¿...?)
            fragmento_antes = texto_lower[:idx]
            if "¿" in fragmento_antes and "?" not in fragmento_antes:
                continue
            return True, texto[:120]

    return False, None


def main():
    output_name = sys.argv[1] if len(sys.argv) > 1 else "outputs10-determinista.txt"
    output_file = SCRIPT_DIR / output_name
    archivos    = sorted(EJEMPLOS_DIR.glob("*.json"))

    si_count = 0
    no_count = 0
    resultados = []

    for archivo in archivos:
        with open(archivo, encoding="utf-8") as f:
            data = json.load(f)
        conv = data.get("conversacion", [])

        ya_tiene, frase = detectar_ya_tiene_movistar(conv, PRIMEROS_N)

        if ya_tiene:
            si_count += 1
        else:
            no_count += 1

        resultados.append({
            "archivo":    archivo.name,
            "n_turnos":   len(conv),
            "ya_tiene":   "si" if ya_tiene else "no",
            "frase_detectada": frase,
        })

    with open(output_file, "w", encoding="utf-8") as f:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"RESULTADOS DETERMINISTAS YA TIENE MOVISTAR — {ts}\n")
        f.write(f"Archivos         : {len(archivos)}\n")
        f.write(f"Primeros N turnos: {PRIMEROS_N}\n")
        f.write("=" * 72 + "\n\n")

        for r in resultados:
            if r["ya_tiene"] == "no":
                continue
            f.write(f"  [{r['archivo']}]\n")
            f.write(f"  Turnos: {r['n_turnos']}\n")
            f.write(f"  Frase: \"{r['frase_detectada']}\"\n\n")

        f.write("=" * 72 + "\n")
        f.write(f"RESUMEN: {si_count} ya tienen Movistar | {no_count} no tienen\n")

    print(f"Archivos analizados  : {len(archivos)}")
    print(f"Ya tienen Movistar   : {si_count}")
    print(f"No tienen            : {no_count}")
    print(f"Output: {output_file}")


if __name__ == "__main__":
    main()
