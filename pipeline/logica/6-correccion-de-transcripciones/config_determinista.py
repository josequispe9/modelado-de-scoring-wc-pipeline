"""
Etapa 6 — Corrección de transcripciones (scoring determinista).

Parámetros leídos desde pipeline_params clave 'correccion_transcripciones'.
Si no existe la clave, se usan estos DEFAULTS.
"""

DEFAULTS = {
    # Estados de transcripcion que se evalúan
    "estados":                   ["correcto"],

    # Filtro por tamaño de conversación (segundos). None = sin límite.
    "duracion_desde":            None,
    "duracion_hasta":            None,

    # Filtros duros → invalido inmediato
    "umbral_logprob_invalido":   -0.6,    # avg_logprob por debajo de este → invalido
    "umbral_words_min":          20,      # total de palabras mínimas
    "umbral_low_score_ratio":    0.25,    # % palabras con score < 0.15
    "umbral_speaker_dominance":  0.95,    # un speaker ocupa > 95% de segmentos

    # Umbral de reprocesamiento (por encima del duro pero sin garantía)
    "umbral_logprob_reprocesar": -0.4,

    # Pesos del score compuesto (deben sumar 1.0)
    "peso_logprob":              0.50,
    "peso_words":                0.25,
    "peso_speaker_balance":      0.25,

    # Clasificación final
    "umbral_score_correcto":     0.75,
    "umbral_score_reprocesar":   0.40,
}
