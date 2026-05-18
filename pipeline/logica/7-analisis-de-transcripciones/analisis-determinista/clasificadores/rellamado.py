"""
Clasificador determinista — rellamado.

Detecta clientes hartos de recibir llamadas repetidas.
Usa frases literales y patrones regex para cantidades de llamadas.
"""

import re

NOMBRE_SCRIPT: str = "rellamado"

PRIMEROS_N_DEFAULT: int = 30

PALABRAS_CLAVE: list[str] = [
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
_PATRONES_CANTIDAD: list[str] = [
    r"\d{2,}\s*veces",
    r"\d+\s*llamad[oa]s",
    r"\d+\s*veces\s*(por|al)\s*día",
    r"\d+\s*llamad[oa]s\s*(por|al)\s*día",
    r"llam\w+.{0,30}(dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|veinte|treinta)\s+veces",
    r"(dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|veinte|treinta)\s+veces.{0,30}llam",
    r"(dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|veinte|treinta)\s+llamad[oa]s",
]

_COMPILED_PATRONES = [re.compile(p) for p in _PATRONES_CANTIDAD]


def detectar(conversacion: list[dict], primeros_n: int) -> tuple[bool, str | None]:
    """
    Revisa los primeros N turnos buscando frases y patrones de rellamado.
    Devuelve (detectado, frase_encontrada_o_None).
    """
    for turno in conversacion[:primeros_n]:
        texto = turno.get("texto", "")
        texto_lower = texto.lower()

        for frase in PALABRAS_CLAVE:
            if frase in texto_lower:
                return True, texto[:120]

        for patron in _COMPILED_PATRONES:
            if patron.search(texto_lower):
                return True, texto[:120]

    return False, None
