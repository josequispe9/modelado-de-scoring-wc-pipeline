"""
Cliente interno para la API REST de Airflow.
Solo esta capa habla con Airflow — las rutas no lo tocan directamente.
"""
import os
import httpx
from typing import Optional

AIRFLOW_BASE_URL = os.environ.get("AIRFLOW_BASE_URL", "http://localhost:8080/api/v1")


def _auth():
    return (
        os.environ.get("AIRFLOW_USER", "admin"),
        os.environ.get("AIRFLOW_PASSWORD", "admin"),
    )


def trigger_dag(dag_id: str, conf: Optional[dict] = None) -> dict:
    response = httpx.post(
        f"{AIRFLOW_BASE_URL}/dags/{dag_id}/dagRuns",
        json={"conf": conf or {}},
        auth=_auth(),
    )
    response.raise_for_status()
    return response.json()


def pausar_dag(dag_id: str) -> dict:
    response = httpx.patch(
        f"{AIRFLOW_BASE_URL}/dags/{dag_id}",
        json={"is_paused": True},
        auth=_auth(),
    )
    response.raise_for_status()
    return response.json()


def get_dag_runs(dag_id: str, limit: int = 20) -> dict:
    response = httpx.get(
        f"{AIRFLOW_BASE_URL}/dags/{dag_id}/dagRuns",
        params={"limit": limit, "order_by": "-start_date"},
        auth=_auth(),
    )
    response.raise_for_status()
    return response.json()


def cancelar_ultimo_dag_run(dag_id: str) -> dict:
    """
    Busca el último DAG run en estado 'running' o 'queued' y lo marca como failed.
    Retorna el dag_run_id cancelado, o indica que no había nada activo.
    """
    response = httpx.get(
        f"{AIRFLOW_BASE_URL}/dags/{dag_id}/dagRuns",
        params={"limit": 5, "order_by": "-start_date"},
        auth=_auth(),
    )
    response.raise_for_status()
    runs = response.json().get("dag_runs", [])

    activo = next(
        (r for r in runs if r.get("state") in ("running", "queued")),
        None,
    )
    if not activo:
        return {"cancelado": False, "mensaje": "No hay ejecución activa"}

    dag_run_id = activo["dag_run_id"]
    patch = httpx.patch(
        f"{AIRFLOW_BASE_URL}/dags/{dag_id}/dagRuns/{dag_run_id}",
        json={"state": "failed"},
        auth=_auth(),
    )
    patch.raise_for_status()
    return {"cancelado": True, "dag_run_id": dag_run_id}
