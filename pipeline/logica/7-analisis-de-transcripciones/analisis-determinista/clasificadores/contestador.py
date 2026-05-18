"""
Clasificador determinista — contestador.

Detecta contestadores automáticos (buzón de voz, casilla de mensajes, etc.).
"""

NOMBRE_SCRIPT: str = "contestador"

PRIMEROS_N_DEFAULT: int = 20

PALABRAS_CLAVE: list[str] = [
    "después del tono",
    "despues del tono",
    "deja tu mensaje",
    "deje su mensaje",
    "deje un mensaje",
    "buzón de voz",
    "buzon de voz",
    "casilla de mensajes",
    "casilla de voz",
    "para finalizar, corta",
    "marca la tecla numeral",
    "asistente de llamadas",
    "no está disponible en este momento",
    "bienvenido al buzón",
    "bienvenido al buzon",
    "usted está comunicado con la casilla",
    "usted esta comunicado con la casilla",
]


def detectar(conversacion: list[dict], primeros_n: int) -> tuple[bool, str | None]:
    """
    Revisa los primeros N turnos buscando frases de contestador automático.
    Devuelve (detectado, frase_encontrada_o_None).
    """
    for turno in conversacion[:primeros_n]:
        texto = turno.get("texto", "").lower()
        for frase in PALABRAS_CLAVE:
            if frase in texto:
                return True, frase
    return False, None
