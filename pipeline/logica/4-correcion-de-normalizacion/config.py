"""
Parámetros para el scoring y clasificación de audios normalizados (etapa 4).
Todos los valores son sobreescribibles desde pipeline_params (clave: correccion_normalizacion).
"""

DEFAULTS = {
    # ── Umbrales duros (→ invalido directo) ───────────────────────────────────
    "duracion_minima_seg":   3,        # audios más cortos no son transcribibles
    "sample_rate_esperado":  16000,
    "canales_esperados":     1,

    # ── Pesos del score compuesto (deben sumar 1.0) ───────────────────────────
    "peso_snr":              0.40,
    "peso_duracion_ratio":   0.30,
    "peso_rms":              0.30,

    # ── Rangos de referencia para normalizar cada métrica a [0, 1] ────────────
    # SNR: 0 dB = peor, 40 dB = mejor
    "snr_min":               0.0,
    "snr_max":               40.0,

    # RMS target: loudnorm apunta a -16 LUFS — penalizamos desviación
    # rms_ref es el valor ideal en dBFS; tolerancia es la banda aceptable
    "rms_ref_dbfs":         -16.0,
    "rms_tolerancia_db":     6.0,      # ±6 dB alrededor del target = score 1.0

    # Duración ratio: output/input — 1.0 es ideal, 0.0 es todo silencio
    "duracion_ratio_min":    0.10,     # por debajo de 10% → score 0

    # ── Umbrales de clasificación ─────────────────────────────────────────────
    "umbral_correcto":       0.75,
    "umbral_reprocesar":     0.40,     # por debajo → invalido
}
