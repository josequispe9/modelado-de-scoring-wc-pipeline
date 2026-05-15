"""
Detección determinista de líneas de empresa/corporativas.
El que atiende no puede tomar decisiones sobre el proveedor porque
la línea pertenece a su empleador o es un plan corporativo.

Uso:
    python test_linea_empresa_determinista.py                    # outputs8-determinista.txt
    python test_linea_empresa_determinista.py mi_output.txt
"""

import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR   = Path(__file__).parent
EJEMPLOS_DIR = SCRIPT_DIR / "ejemplos_transcripciones"
PRIMEROS_N   = 40

FRASES_EMPRESA = [
    # Línea corporativa explícita
    "línea corporativa",
    "linea corporativa",
    "es corporativo",
    "plan corporativo",
    "plan de empresa",
    "línea de empresa",
    "linea de empresa",
    "línea de cuerpo",
    "linea de cuerpo",
    # La empresa paga / es dueña
    "es de la empresa",
    "es de empresa",
    "lo paga la empresa",
    "la paga la empresa",
    "lo paga el laburo",
    "la paga el laburo",
    "me lo paga la empresa",
    "me lo paga el laburo",
    "me lo paga mi jefe",
    "me la paga la empresa",
    "me la paga el laburo",
    "me la paga mi jefe",
    "paga mi jefe",
    # El teléfono pertenece al trabajo
    "es de donde trabajo",
    "es del trabajo",
    "es de mi trabajo",
    "teléfono del trabajo",
    "telefono del trabajo",
    "teléfono de la empresa",
    "telefono de la empresa",
    "celular del trabajo",
    "celular de la empresa",
    "celular de donde trabajo",
    # Sin poder de decisión
    "no tengo ningún tipo de poder",
    "no tengo ningun tipo de poder",
]


def detectar_linea_empresa(conversacion: list[dict], primeros_n: int) -> tuple[bool, str | None]:
    for turno in conversacion[:primeros_n]:
        texto = turno.get("texto", "")
        texto_lower = texto.lower()

        for frase in FRASES_EMPRESA:
            if frase in texto_lower:
                return True, texto[:120]

    return False, None


def main():
    output_name = sys.argv[1] if len(sys.argv) > 1 else "outputs8-determinista.txt"
    output_file = SCRIPT_DIR / output_name
    archivos    = sorted(EJEMPLOS_DIR.glob("*.json"))

    si_count = 0
    no_count = 0
    resultados = []

    for archivo in archivos:
        with open(archivo, encoding="utf-8") as f:
            data = json.load(f)
        conv = data.get("conversacion", [])

        es_empresa, frase = detectar_linea_empresa(conv, PRIMEROS_N)

        if es_empresa:
            si_count += 1
        else:
            no_count += 1

        resultados.append({
            "archivo":    archivo.name,
            "n_turnos":   len(conv),
            "es_empresa": "si" if es_empresa else "no",
            "frase_detectada": frase,
        })

    with open(output_file, "w", encoding="utf-8") as f:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"RESULTADOS DETERMINISTAS LÍNEA DE EMPRESA — {ts}\n")
        f.write(f"Archivos         : {len(archivos)}\n")
        f.write(f"Primeros N turnos: {PRIMEROS_N}\n")
        f.write("=" * 72 + "\n\n")

        for r in resultados:
            if r["es_empresa"] == "no":
                continue
            f.write(f"  [{r['archivo']}]\n")
            f.write(f"  Turnos: {r['n_turnos']}\n")
            f.write(f"  Frase: \"{r['frase_detectada']}\"\n\n")

        f.write("=" * 72 + "\n")
        f.write(f"RESUMEN: {si_count} líneas de empresa | {no_count} líneas personales\n")

    print(f"Archivos analizados  : {len(archivos)}")
    print(f"Líneas de empresa    : {si_count}")
    print(f"Líneas personales    : {no_count}")
    print(f"Output: {output_file}")


if __name__ == "__main__":
    main()
