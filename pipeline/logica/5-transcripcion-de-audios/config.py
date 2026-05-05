"""
Parámetros por defecto para la transcripción de audios.
Estos valores pueden ser sobreescritos desde el dashboard via pipeline_params
(claves: transcripcion_G, transcripcion_M, transcripcion_B).
"""

DEFAULTS = {
    # Grupo de transcripción (define la subcarpeta en transcripciones-raw/)
    # Se sobreescribe siempre desde pipeline_params
    "grupo": "GBM",

    # Cantidad de fragmentos de audio que Whisper procesa en paralelo en GPU
    # Mayor = más rápido pero más VRAM en el pico. Referencia para large-v2/v3:
    #   batch_size=4  → pico ~0.5 GB extra → total ~4.9 GB → seguro en 8 GB
    #   batch_size=8  → pico ~1.0 GB extra → total ~5.4 GB → ok en 8 GB con int8
    #   batch_size=16 → pico ~2.0 GB extra → total ~6.4 GB → requiere 8+ GB libres
    "batch_size": 4,

    # Modelo WhisperX a usar
    # Opciones: "large-v3", "large-v2", "medium", "small"
    # large-v3 es el más preciso; large-v2 es más rápido con calidad similar
    "modelo": "large-v2",

    # Tipo de cómputo en GPU
    # "float16" → mejor calidad (requiere más VRAM, recomendado solo para 10+ GB)
    # "int8"    → más rápido, menor uso de VRAM (recomendado para 8 GB)
    "compute_type": "int8",

    # Cantidad de hablantes esperados en la conversación
    # None → WhisperX auto-detecta (puede equivocarse con ruido de fondo)
    # int  → fuerza exactamente N hablantes en la diarización
    "min_speakers": 2,
    "max_speakers": 2,

    # Filtro de duración del audio normalizado (en segundos)
    # None → sin límite
    # Útil para asignar audios cortos/largos a distintas PCs según su VRAM
    # Ejemplo: Melchor (10 GB) toma audios > 5 min; Gaspar y Baltazar los cortos
    "duracion_desde": None,    # ej: 300 para audios de más de 5 minutos
    "duracion_hasta": None,    # ej: 300 para audios de hasta 5 minutos

    # Estados de correccion_normalizacion que esta PC/grupo va a procesar
    # Opciones: ["correcto"], ["reprocesar"], ["correcto", "reprocesar"]
    # "correcto"   → audios que pasaron el quality gate de la etapa 4
    # "reprocesar" → audios marcados para reintento (útil para experimentar con ellos)
    "estados": ["correcto"],
}
