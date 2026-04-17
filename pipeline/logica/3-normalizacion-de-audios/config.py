"""
Parámetros por defecto para la normalización de audios.
Estos valores pueden ser sobreescritos desde el dashboard via pipeline_params
(claves: normalizacion_G, normalizacion_M, normalizacion_B).
"""

DEFAULTS = {
    # Carpeta de origen: 'audios', 'reprocesar' o 'ambos'
    "carpeta": "audios",

    # Grupo de normalización (define la subcarpeta en audios-raw/)
    # Se sobreescribe siempre desde pipeline_params
    "grupo": "GBM",

    # Detección de silencio
    "silence_threshold": "-40dB",   # -50dB más agresivo, -30dB más conservador
    "silence_duration":  "1",       # duración mínima de silencio a remover (segundos)

    # Normalización de volumen (loudnorm EBU R128)
    "normalize": True,

    # Filtros opcionales
    "noise_reduction": False,       # reducción de ruido (más lento)
    "highpass_filter": False,       # filtro pasa-altos para remover ruidos bajos (<200Hz)
}