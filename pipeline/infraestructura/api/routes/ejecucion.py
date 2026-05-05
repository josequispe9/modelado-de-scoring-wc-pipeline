from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional
import httpx
import os
import psycopg2
from api import airflow_client

router = APIRouter()

ETAPAS_DAG = {
    "descarga":                        "pipeline_descarga",
    "creacion_registros":              "pipeline_creacion_registros",
    "normalizacion":                   "pipeline_normalizacion",
    "correccion_normalizacion":        "pipeline_correccion_normalizacion",
    "seleccionar_ganador":             "pipeline_seleccionar_ganador",
    "transcripcion":                   "pipeline_transcripcion",
    "correccion_transcripciones":      "pipeline_correccion_transcripciones",
    "correccion_transcripciones_llm":  "pipeline_correccion_transcripciones_llm",
    "analisis":                        "pipeline_analisis",
    "correccion_analisis":             "pipeline_correccion_analisis",
    "carga_datos":                     "pipeline_carga_datos",
}

Etapa = Literal[
    "descarga", "creacion_registros", "normalizacion",
    "correccion_normalizacion", "seleccionar_ganador", "transcripcion",
    "correccion_transcripciones", "correccion_transcripciones_llm",
    "analisis", "correccion_analisis", "carga_datos"
]


class FiltroEjecucion(BaseModel):
    filtro: Literal["pendientes", "reprocesar", "todos"] = "pendientes"
    ids: Optional[list[str]] = None   # UUIDs específicos (opcional)


@router.post("/ejecutar")
def ejecutar_pipeline_completo():
    """Dispara el DAG maestro que corre todas las etapas en orden."""
    try:
        return airflow_client.trigger_dag("pipeline_completo")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))


@router.post("/etapa/{etapa}/ejecutar")
def ejecutar_etapa(etapa: Etapa, body: FiltroEjecucion = FiltroEjecucion()):
    """
    Dispara solo una etapa del pipeline.
    Ejemplo: POST /pipeline/etapa/analisis/ejecutar  {"filtro": "pendientes"}
    """
    dag_id = ETAPAS_DAG[etapa]
    conf = {"filtro": body.filtro, "ids": body.ids}
    try:
        return airflow_client.trigger_dag(dag_id, conf=conf)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))


@router.post("/etapa/correccion_normalizacion/limpiar")
def limpiar_audios_normalizacion():
    """
    Dispara el DAG seleccionar_ganador en Airflow:
    elige el grupo con mejor score por audio y elimina los duplicados de MinIO.
    """
    try:
        return airflow_client.trigger_dag("pipeline_seleccionar_ganador")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))


@router.post("/etapa/correccion_normalizacion/resetear")
def resetear_correccion_normalizacion():
    """
    Elimina los resultados de correccion_normalizacion del JSONB y devuelve
    los audios a etapa_actual='normalizacion' / estado_global='correcto'
    para poder volver a correr la etapa con nuevos parámetros.
    """
    with psycopg2.connect(os.environ["SCORING_DB_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE audio_pipeline_jobs
                SET etapas       = etapas - 'correccion_normalizacion',
                    etapa_actual = 'normalizacion',
                    estado_global = 'correcto'
                WHERE etapa_actual = 'correccion_normalizacion'
            """)
            afectados = cur.rowcount
        conn.commit()
    return {"reseteados": afectados}


@router.post("/etapa/correccion_transcripciones/limpiar")
def limpiar_transcripciones():
    """
    Dispara el DAG seleccionar_ganador_transcripciones en Airflow:
    elige el grupo con mejor score_total por audio, construye el JSON de salida
    y lo sube a MinIO bajo transcripciones-formateadas/.
    """
    try:
        return airflow_client.trigger_dag("pipeline_seleccionar_ganador_transcripciones")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))


@router.post("/etapa/correccion_transcripciones/resetear")
def resetear_correccion_transcripciones():
    """
    Elimina los resultados de correccion_transcripciones del JSONB y devuelve
    los audios a etapa_actual='transcripcion' / estado_global='correcto'
    para poder volver a correr la etapa con nuevos parámetros.
    """
    with psycopg2.connect(os.environ["SCORING_DB_URL"]) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE audio_pipeline_jobs
                SET etapas        = etapas - 'correccion_transcripciones',
                    etapa_actual  = 'transcripcion',
                    estado_global = 'correcto'
                WHERE etapa_actual = 'correccion_transcripciones'
            """)
            afectados = cur.rowcount
        conn.commit()
    return {"reseteados": afectados}


@router.post("/etapa/{etapa}/pausar")
def pausar_etapa(etapa: Etapa):
    """Pausa el DAG de una etapa para que no corra en el próximo schedule."""
    dag_id = ETAPAS_DAG[etapa]
    try:
        return airflow_client.pausar_dag(dag_id)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
