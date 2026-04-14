"""
parametros para la normalizacion de audios
"""

# Parámetros de limpieza de audio
AUDIO_PARAMS = {
    # Detección de silencio (ajustar según necesidad)
    'silence_threshold': '-40dB',  # Umbral de silencio (-50dB más agresivo, -30dB más conservador)
    'silence_duration': '1',     # Duración mínima de silencio a remover (segundos)

    # Normalización de audio
    'normalize': True,             # Activar normalización de volumen

    # Filtros adicionales
    'noise_reduction': False,      # Reducción de ruido (más lento, usar solo si necesario)
    'highpass_filter': False,      # Filtro pasa-altos para remover ruidos bajos
}