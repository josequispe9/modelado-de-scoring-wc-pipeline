from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional
import httpx
import subprocess
import sys
import os
from api import airflow_client

router = APIRouter()

ETAPAS_DAG = {
    "descarga":                "pipeline_descarga",
    "creacion_registros":      "pipeline_creacion_registros",
    "normalizacion":           "pipeline_normalizacion",
    "correccion_normalizacion": "pipeline_correccion_normalizacion",
    "transcripcion":           "pipeline_transcripcion",
    "correccion_transcripciones": "pipeline_correccion_transcripciones",
    "analisis":                "pipeline_analisis",
    "correccion_analisis":     "pipeline_correccion_analisis",
    "carga_datos":             "pipeline_carga_datos",
}

Etapa = Literal[
    "descarga", "creacion_registros", "normalizacion",
    "correccion_normalizacion", "transcripcion",
    "correccion_transcripciones", "analisis",
    "correccion_analisis", "carga_datos"
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
    Corre seleccionar_ganador.py en gaspar:
    elige el grupo con mejor score por audio y elimina los duplicados de MinIO.
    """
    proyecto = os.environ.get(
        "PROYECTO_DIR",
        r"C:\Users\qjose\Desktop\modelado de scoring WC"
    )
    python = os.path.join(proyecto, r"pipeline\venv\Scripts\python.exe")
    script = os.path.join(
        proyecto,
        r"pipeline\logica\4-correcion-de-normalizacion\seleccionar_ganador.py"
    )
    try:
        proc = subprocess.Popen(
            [python, script],
            cwd=proyecto,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        return {"status": "iniciado", "pid": proc.pid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/etapa/{etapa}/pausar")
def pausar_etapa(etapa: Etapa):
    """Pausa el DAG de una etapa para que no corra en el próximo schedule."""
    dag_id = ETAPAS_DAG[etapa]
    try:
        return airflow_client.pausar_dag(dag_id)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
