from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import psycopg2
import psycopg2.extras
import json
import os

router = APIRouter()

CLAVES_VALIDAS = {
    "creacion_registros",
    "descarga_G", "descarga_M", "descarga_B",
    "normalizacion_G", "normalizacion_M", "normalizacion_B",
    "correccion_normalizacion",
    "transcripcion_G", "transcripcion_M", "transcripcion_B",
    "correccion_transcripciones",
    "correccion_transcripciones_llm_G",
    "correccion_transcripciones_llm_M",
    "correccion_transcripciones_llm_B",
    "correccion_transcripciones_ganador",
    "analisis_A", "analisis_B",
    "correccion_analisis_A", "correccion_analisis_B",
}

DEFAULTS_POR_CLAVE = {
    "creacion_registros": {
        "limite": None,
    },
    "correccion_transcripciones": {
        "estados":                   ["correcto"],
        "duracion_desde":            None,
        "duracion_hasta":            None,
        "umbral_logprob_invalido":   -0.6,
        "umbral_logprob_reprocesar": -0.4,
        "umbral_words_min":          20,
        "umbral_low_score_ratio":    0.25,
        "umbral_speaker_dominance":  0.95,
        "peso_logprob":              0.50,
        "peso_words":                0.25,
        "peso_speaker_balance":      0.25,
        "umbral_score_correcto":     0.75,
        "umbral_score_reprocesar":   0.40,
    },
    "correccion_transcripciones_llm_G": {
        "grupo": "GBM", "estados": ["correcto"],
        "duracion_desde": None, "duracion_hasta": None,
        "modelo": "Qwen/Qwen2.5-3B-Instruct-AWQ",
        "max_segmentos_inicio": 30, "max_segmentos_fin": 20,
        "usar_llm": True,
        "peso_score_determinista": 0.40, "peso_score_llm": 0.60,
        "umbral_score_correcto": 0.75, "umbral_score_reprocesar": 0.40,
    },
    "correccion_transcripciones_llm_M": {
        "grupo": "GBM", "estados": ["correcto"],
        "duracion_desde": None, "duracion_hasta": None,
        "modelo": "Qwen/Qwen2.5-3B-Instruct-AWQ",
        "max_segmentos_inicio": 30, "max_segmentos_fin": 20,
        "usar_llm": True,
        "peso_score_determinista": 0.40, "peso_score_llm": 0.60,
        "umbral_score_correcto": 0.75, "umbral_score_reprocesar": 0.40,
    },
    "correccion_transcripciones_llm_B": {
        "grupo": "GBM", "estados": ["correcto"],
        "duracion_desde": None, "duracion_hasta": None,
        "modelo": "Qwen/Qwen2.5-3B-Instruct-AWQ",
        "max_segmentos_inicio": 30, "max_segmentos_fin": 20,
        "usar_llm": True,
        "peso_score_determinista": 0.40, "peso_score_llm": 0.60,
        "umbral_score_correcto": 0.75, "umbral_score_reprocesar": 0.40,
    },
    "correccion_transcripciones_ganador": {
        "umbral_score_correcto":   0.75,
        "umbral_score_reprocesar": 0.40,
    },
    "correccion_normalizacion": {
        "duracion_minima_seg":  3,
        "duracion_maxima_seg":  1800,
        "sample_rate_esperado": 16000,
        "canales_esperados":    1,
        "peso_snr":             0.40,
        "peso_duracion_ratio":  0.30,
        "peso_rms":             0.30,
        "snr_min":              0.0,
        "snr_max":              40.0,
        "rms_ref_dbfs":        -16.0,
        "rms_tolerancia_db":    6.0,
        "duracion_ratio_min":   0.10,
        "umbral_correcto":      0.75,
        "umbral_reprocesar":    0.40,
    }
}


def get_conn():
    return psycopg2.connect(os.environ["SCORING_DB_URL"])


class ActualizarParametros(BaseModel):
    valor: dict


@router.get("/parametros/{clave}")
def get_parametros(clave: str):
    if clave not in CLAVES_VALIDAS:
        raise HTTPException(status_code=404, detail=f"Clave '{clave}' no existe")
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT clave, valor, updated_at FROM pipeline_params WHERE clave = %s", (clave,))
        row = cur.fetchone()
        if not row:
            defaults = DEFAULTS_POR_CLAVE.get(clave)
            if defaults:
                return {"clave": clave, "valor": defaults, "updated_at": None}
            raise HTTPException(status_code=404, detail="Parámetro no encontrado")
        return row


@router.patch("/parametros/{clave}")
def actualizar_parametros(clave: str, body: ActualizarParametros):
    """
    Actualiza los parámetros que los scripts leerán en el próximo run.
    Ejemplo: PATCH /pipeline/parametros/descarga_M
             body: {"valor": {"hora_inicio": "13", "hora_fin": "17"}}
    """
    if clave not in CLAVES_VALIDAS:
        raise HTTPException(status_code=404, detail=f"Clave '{clave}' no existe")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO pipeline_params (clave, valor)
            VALUES (%s, %s)
            ON CONFLICT (clave) DO UPDATE
                SET valor = EXCLUDED.valor, updated_at = now()
        """, (clave, json.dumps(body.valor)))
        conn.commit()
    return {"clave": clave, "valor": body.valor}
