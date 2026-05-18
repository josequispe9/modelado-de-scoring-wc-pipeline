"""
Clasificador determinista — cliente_molesto.

Detecta clientes que insultan durante la llamada.
"""

NOMBRE_SCRIPT: str = "cliente_molesto"

PRIMEROS_N_DEFAULT: int = 40

PALABRAS_CLAVE: list[str] = [
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
    "rompen las pelotas",
    "rompiendo las pelotas",
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


def detectar(conversacion: list[dict], primeros_n: int) -> tuple[bool, str | None]:
    """
    Revisa los primeros N turnos buscando insultos.
    Devuelve (detectado, frase_encontrada_o_None).
    """
    for turno in conversacion[:primeros_n]:
        texto_lower = turno.get("texto", "").lower()
        for insulto in PALABRAS_CLAVE:
            if insulto in texto_lower:
                return True, turno["texto"][:120]
    return False, None
