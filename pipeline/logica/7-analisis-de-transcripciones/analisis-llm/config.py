"""
Configuración por defecto para analisis_llm.py (etapa 7 — análisis LLM).

Los valores aquí son los DEFAULTS. En producción se leen desde pipeline_params
con clave 'analisis_llm'. Si no existe esa clave, se usan estos valores.
"""

DEFAULTS_ANALISIS_LLM = {
    "scripts": ["problema_senal"],
    "estados_a_procesar": ["correcto"],
    "modelo": "Qwen/Qwen2.5-7B-Instruct-AWQ",
    "gpu_memory_utilization": 0.85,
    "max_model_len": 4096,
}
