"""
Configuración por defecto para el análisis determinista (etapa 7).

Los valores aquí son los defaults. En producción se leen desde la tabla
pipeline_params clave 'analisis_determinista' y se sobreescriben.
"""

DEFAULTS_ANALISIS_DETERMINISTA = {
    "scripts": [
        "cliente_molesto",
        "contestador",
        "linea_empresa",
        "numero_equivocado",
        "rellamado",
        "vinculado_titular",
        "ya_tiene_movistar",
    ],
    "estados_a_procesar": ["correcto"],
    "primeros_n": {
        "cliente_molesto":   40,
        "contestador":       20,
        "linea_empresa":     40,
        "numero_equivocado": 20,
        "rellamado":         30,
        "vinculado_titular": 20,
        "ya_tiene_movistar": 20,
    },
}
