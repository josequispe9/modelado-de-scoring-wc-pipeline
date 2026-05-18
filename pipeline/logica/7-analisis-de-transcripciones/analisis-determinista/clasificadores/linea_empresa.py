"""
Clasificador determinista — linea_empresa.

Detecta líneas corporativas o de empresa: el que atiende no puede tomar
decisiones sobre el proveedor porque la línea pertenece a su empleador
o es un plan corporativo.
"""

NOMBRE_SCRIPT: str = "linea_empresa"

PRIMEROS_N_DEFAULT: int = 40

PALABRAS_CLAVE: list[str] = [
    # Línea corporativa explícita
    "línea corporativa",
    "linea corporativa",
    "es corporativo",
    "plan corporativo",
    "plan de empresa",
    "plan empresa",
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
    "me las paga la empresa",
    "me las paga el laburo",
    "me las paga mi jefe",
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


def detectar(conversacion: list[dict], primeros_n: int) -> tuple[bool, str | None]:
    """
    Revisa los primeros N turnos buscando indicadores de línea corporativa.
    Devuelve (detectado, frase_encontrada_o_None).
    """
    for turno in conversacion[:primeros_n]:
        texto = turno.get("texto", "")
        texto_lower = texto.lower()
        for frase in PALABRAS_CLAVE:
            if frase in texto_lower:
                return True, texto[:120]
    return False, None
