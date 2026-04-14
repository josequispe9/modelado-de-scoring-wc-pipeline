"""
Parametros por defecto para la descarga de audios desde Mitrol.
Estos valores pueden ser sobreescritos desde el dashboard via pipeline_params.
"""
from datetime import datetime

hoy = datetime.now().strftime("%d/%m/%Y")

DEFAULTS = {
    "cant_registros_max": "100000",
    "fecha_inicio":       hoy,
    "fecha_fin":          hoy,
    "hora_inicio":        "08",
    "hora_fin":           "22",
    "duracion_min":       "00",
    "duracion_max":       "00",
    "cliente":            "",
}
