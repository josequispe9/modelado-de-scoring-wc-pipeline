"""
parametros para el scoring de clasificacion de normalizacion de audios
"""
# Umbrales de validacion de audios
VALIDACION = {
    'duracion_minima': 10,      # segundos - menos es sospechoso
    'duracion_maxima': 1800,    # 30 minutos - más es sospechoso
    'reduccion_maxima': 0.90,   # si pierde más del 90% de duracion despues de la limpieza es sospechoso
}
