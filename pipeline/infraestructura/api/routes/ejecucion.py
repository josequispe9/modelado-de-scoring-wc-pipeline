from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional
from api import airflow_client

router = APIRouter()

ETAPAS_DAG = {
    "descarga":               "pipeline_descarga",
    "limpieza":               "pipeline_limpieza",
    "transcripcion":          "pipeline_transcripcion",
    "correccion_transcripcion": "pipeline_correccion_transcripcion",
    "analisis":               "pipeline_analisis",
    "correccion_analisis":    "pipeline_correccion_analisis",
    "carga_datos":            "pipeline_carga_datos",
}

Etapa = Literal[
    "descarga", "limpieza", "transcripcion",
    "correccion_transcripcion", "analisis",
    "correccion_analisis", "carga_datos"
]


class FiltroEjecucion(BaseModel):
    filtro: Literal["pendientes", "reprocesar", "todos"] = "pendientes"
    ids: Optional[list[str]] = None   # UUIDs específicos (opcional)


@router.post("/ejecutar")
def ejecutar_pipeline_completo():
    """Dispara el DAG maestro que corre todas las etapas en orden."""
    return airflow_client.trigger_dag("pipeline_completo")


@router.post("/etapa/{etapa}/ejecutar")
def ejecutar_etapa(etapa: Etapa, body: FiltroEjecucion = FiltroEjecucion()):
    """
    Dispara solo una etapa del pipeline.
    Ejemplo: POST /pipeline/etapa/analisis/ejecutar  {"filtro": "pendientes"}
    """
    dag_id = ETAPAS_DAG[etapa]
    conf = {"filtro": body.filtro, "ids": body.ids}
    return airflow_client.trigger_dag(dag_id, conf=conf)


@router.post("/etapa/{etapa}/pausar")
def pausar_etapa(etapa: Etapa):
    """Pausa el DAG de una etapa para que no corra en el próximo schedule."""
    dag_id = ETAPAS_DAG[etapa]
    return airflow_client.pausar_dag(dag_id)
