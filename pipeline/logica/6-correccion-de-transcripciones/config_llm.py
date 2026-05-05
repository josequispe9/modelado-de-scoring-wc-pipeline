"""
Etapa 6 — Corrección de transcripciones (scoring con vLLM).

Parámetros leídos desde pipeline_params clave 'correccion_transcripciones_llm_<CUENTA>'
donde CUENTA es G, M o B. Si no existe la clave, se usan estos DEFAULTS.
"""

DEFAULTS = {
    # Estados de transcripcion que se evalúan
    "estados":                   ["correcto"],

    # Filtro por tamaño de conversación (segundos). None = sin límite.
    "duracion_desde":            None,
    "duracion_hasta":            None,

    # Modelo vLLM — se carga una sola vez al inicio del script
    "modelo":                    "Qwen/Qwen2.5-3B-Instruct-AWQ",

    # Parámetros de carga del modelo (ajustar por PC según VRAM disponible).
    # gpu_memory_utilization bajo (0.50) compensa el overhead de WSL2 que
    # provoca que vLLM sobreestime la VRAM disponible para el KV cache.
    "gpu_memory_utilization":    0.50,
    "max_model_len":             4096,

    # Muestra de segmentos para el prompt (inicio + fin)
    "max_segmentos_inicio":      30,
    "max_segmentos_fin":         20,

    # False → omite el LLM (modo debug / fallback sin GPU)
    "usar_llm":                  True,

    # Pesos para score_total = determinista * w1 + llm * w2
    "peso_score_determinista":   0.40,
    "peso_score_llm":            0.60,

    # Clasificación final
    "umbral_score_correcto":     0.75,
    "umbral_score_reprocesar":   0.40,
}
