"""
Detección determinista de llamadas atendidas por alguien vinculado al titular
(familiar, conviviente) pero que NO es el titular mismo.
NO incluye números equivocados ni llamadas donde el titular sí atendió.

Uso:
    python test_vinculado_titular_determinista.py                    # outputs7-determinista.txt
    python test_vinculado_titular_determinista.py mi_output.txt
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR   = Path(__file__).parent
EJEMPLOS_DIR = SCRIPT_DIR / "ejemplos_transcripciones"
PRIMEROS_N   = 20

FRASES_VINCULADO = [
    # Niega ser la persona buscada
    "no soy ella",
    "no soy él",
    "no es ella",
    "no es él",
    # Titular ausente (location)
    "no está aquí",
    "no esta aquí",
    "no está acá",
    "no esta acá",
    # Familiar se identifica como tal
    "soy su hermana",
    "soy su hermano",
    "soy su hija",
    "soy su hijo",
    "soy su madre",
    "soy su padre",
    "soy su mamá",
    "soy su papá",
    "soy la mamá",
    "soy el papá",
    # Línea a nombre de familiar
    "está a nombre de mi marido",
    "esta a nombre de mi marido",
    "está a nombre de mi esposo",
    "esta a nombre de mi esposo",
    "está a nombre de mi esposa",
    "esta a nombre de mi esposa",
    "está en nombre de mi marido",
    "esta en nombre de mi marido",
    "está en nombre de mi esposo",
    "esta en nombre de mi esposo",
    "está en nombre de mi esposa",
    "esta en nombre de mi esposa",
    # Familiar responde (como contestación a "¿hablo con X?")
    "con la madre",
    "con mi madre",
    "con la mamá",
    "con mi mamá",
    "con el padre",
    "con mi padre",
    "con el papá",
    "con mi papá",
    "con la hija",
    "con mi hija",
    "con el hijo",
    "con mi hijo",
    "con el hermano",
    "con mi hermano",
    "con la hermana",
    "con mi hermana",
    "con el marido",
    "con la esposa",
    # Titular ausente pero el que atiende sigue la llamada
    "no está mi mamá",
    "no esta mi mamá",
    "no está mi mama",
    "no esta mi mama",
    "no está mi papá",
    "no esta mi papá",
    "no está mi papa",
    "no esta mi papa",
    "no está mi marido",
    "no esta mi marido",
    "no está mi esposo",
    "no esta mi esposo",
    "no está mi esposa",
    "no esta mi esposa",
    "no está mi señora",
    "no esta mi señora",
    "no está mi señor",
    "no esta mi señor",
    "no está el dueño",
    "no esta el dueño",
    "no está la dueña",
    "no esta la dueña",
    "no está en este momento ella",
    "no esta en este momento ella",
    "no está en este momento él",
    "no esta en este momento el",
    "no se encuentra en este momento",
    "no se encuentra ella",
    "no se encuentra él",
    # Menciona explícitamente que es familiar
    "es familiar mío",
    "es familiar mio",
]

# "no soy [NombrePropio]" — e.g. "no soy Alejandro", "no soy Mabel"
PATRON_NO_SOY_NOMBRE = re.compile(r"no soy [A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]+")


def detectar_vinculado(conversacion: list[dict], primeros_n: int) -> tuple[bool, str | None]:
    for turno in conversacion[:primeros_n]:
        texto = turno.get("texto", "")
        texto_lower = texto.lower()

        for frase in FRASES_VINCULADO:
            if frase in texto_lower:
                return True, texto[:120]

        if PATRON_NO_SOY_NOMBRE.search(texto):
            return True, texto[:120]

    return False, None


def main():
    output_name = sys.argv[1] if len(sys.argv) > 1 else "outputs7-determinista.txt"
    output_file = SCRIPT_DIR / output_name
    archivos    = sorted(EJEMPLOS_DIR.glob("*.json"))

    si_count = 0
    no_count = 0
    resultados = []

    for archivo in archivos:
        with open(archivo, encoding="utf-8") as f:
            data = json.load(f)
        conv = data.get("conversacion", [])

        es_vinculado, frase = detectar_vinculado(conv, PRIMEROS_N)

        if es_vinculado:
            si_count += 1
        else:
            no_count += 1

        resultados.append({
            "archivo":       archivo.name,
            "n_turnos":      len(conv),
            "es_vinculado":  "si" if es_vinculado else "no",
            "frase_detectada": frase,
        })

    with open(output_file, "w", encoding="utf-8") as f:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"RESULTADOS DETERMINISTAS VINCULADO AL TITULAR — {ts}\n")
        f.write(f"Archivos         : {len(archivos)}\n")
        f.write(f"Primeros N turnos: {PRIMEROS_N}\n")
        f.write("=" * 72 + "\n\n")

        for r in resultados:
            if r["es_vinculado"] == "no":
                continue
            f.write(f"  [{r['archivo']}]\n")
            f.write(f"  Turnos: {r['n_turnos']}\n")
            f.write(f"  Frase: \"{r['frase_detectada']}\"\n\n")

        f.write("=" * 72 + "\n")
        f.write(f"RESUMEN: {si_count} vinculados | {no_count} normales\n")

    print(f"Archivos analizados : {len(archivos)}")
    print(f"Vinculados (si)     : {si_count}")
    print(f"Normales (no)       : {no_count}")
    print(f"Output: {output_file}")


if __name__ == "__main__":
    main()
