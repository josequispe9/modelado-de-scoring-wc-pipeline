"""
Clasificador determinista — vinculado_titular.

Detecta llamadas atendidas por alguien vinculado al titular
(familiar, conviviente) pero que NO es el titular mismo.
No incluye números equivocados ni llamadas donde el titular sí atendió.
"""

import re

NOMBRE_SCRIPT: str = "vinculado_titular"

PRIMEROS_N_DEFAULT: int = 20

PALABRAS_CLAVE: list[str] = [
    # Niega ser la persona buscada
    "no soy ella",
    "no soy él",
    "no es ella",
    "no es él",
    # Titular ausente (location)
    "no está ella",
    "no esta ella",
    "no está él",
    "no esta él",
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
    # Familiar responde (solo formas con artículo "con la/el")
    "con la madre",
    "con la mamá",
    "con el padre",
    "con el papá",
    "con la hija",
    "con el hijo",
    "con el hermano",
    "con la hermana",
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
_PATRON_NO_SOY_NOMBRE = re.compile(r"no soy [A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]+")


def detectar(conversacion: list[dict], primeros_n: int) -> tuple[bool, str | None]:
    """
    Revisa los primeros N turnos buscando indicadores de vinculado al titular.
    Omite turnos que son preguntas (terminan en '?').
    Devuelve (detectado, frase_encontrada_o_None).
    """
    for turno in conversacion[:primeros_n]:
        texto = turno.get("texto", "")
        texto_lower = texto.lower()

        # Descartar turnos que son preguntas (vendedor preguntando)
        if texto.strip().endswith("?"):
            continue

        for frase in PALABRAS_CLAVE:
            if frase in texto_lower:
                return True, texto[:120]

        if _PATRON_NO_SOY_NOMBRE.search(texto):
            return True, texto[:120]

    return False, None
