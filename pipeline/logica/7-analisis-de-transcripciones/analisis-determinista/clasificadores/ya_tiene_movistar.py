"""
Clasificador determinista — ya_tiene_movistar.

Detecta clientes que ya son clientes de Movistar. La campaña apunta
a portar líneas de Claro/Personal a Movistar, pero algunos contactos
ya tienen Movistar — la venta no aplica.
"""

import re

NOMBRE_SCRIPT: str = "ya_tiene_movistar"

PRIMEROS_N_DEFAULT: int = 20

PALABRAS_CLAVE: list[str] = [
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
    "tengo otra línea de movistar",
    "tengo otra linea de movistar",
    "tengo línea de movistar",
    "tengo linea de movistar",
    "soy cliente de movistar",
    # Portabilidad completada
    "ya me pasé a movistar",
    "ya me pase a movistar",
]

# Negaciones que invalidan el match (ej: "no tengo movistar", "no estoy en movistar")
_PATRON_NEGACION = re.compile(r"\bno (tengo|soy|estoy|uso).{0,5}movistar")

# Turno del vendedor explicando que trabaja en Movistar
_PATRON_VENDOR = re.compile(
    r"(llamo|llamamos|comunico|contacto).{0,30}movistar"
    r"|movistar.{0,30}(llamo|llamamos|descuento para|personas que)"
)


def detectar(conversacion: list[dict], primeros_n: int) -> tuple[bool, str | None]:
    """
    Revisa los primeros N turnos buscando indicadores de que el cliente
    ya tiene Movistar. Filtra negaciones y turnos del vendedor.
    Devuelve (detectado, frase_encontrada_o_None).
    """
    for turno in conversacion[:primeros_n]:
        texto = turno.get("texto", "")
        texto_lower = texto.lower()

        # Turnos muy largos son casi siempre el vendedor
        if len(texto) > 200:
            continue

        # Descartar negaciones ("no tengo movistar", etc.)
        if _PATRON_NEGACION.search(texto_lower):
            continue

        # Descartar turno del vendedor explicando que trabaja en Movistar
        if _PATRON_VENDOR.search(texto_lower):
            continue

        for frase in PALABRAS_CLAVE:
            idx = texto_lower.find(frase)
            if idx == -1:
                continue
            # Descartar si la frase está dentro de una pregunta (¿...?)
            fragmento_antes = texto_lower[:idx]
            if "¿" in fragmento_antes and "?" not in fragmento_antes:
                continue
            return True, texto[:120]

    return False, None
