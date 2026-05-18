"""
Clasificador determinista — numero_equivocado.

Detecta llamadas donde quien atendió NO es el titular de la línea
(línea en nombre de otro, ya no es titular, número cambió de dueño).
No incluye ausencias temporales ("no está mi mamá").
"""

NOMBRE_SCRIPT: str = "numero_equivocado"

PRIMEROS_N_DEFAULT: int = 20

PALABRAS_CLAVE: list[str] = [
    "equivocado",
    "equivocada",
]


def detectar(conversacion: list[dict], primeros_n: int) -> tuple[bool, str | None]:
    """
    Revisa los primeros N turnos buscando indicadores de número equivocado.
    Devuelve (detectado, frase_encontrada_o_None).
    """
    for turno in conversacion[:primeros_n]:
        texto = turno.get("texto", "")
        texto_lower = texto.lower()
        for frase in PALABRAS_CLAVE:
            if frase in texto_lower:
                return True, texto[:120]
    return False, None
