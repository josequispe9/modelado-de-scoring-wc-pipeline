from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import psycopg2
import psycopg2.extras
import json
import os

router = APIRouter()

CLAVES_VALIDAS = {
    "descarga_G", "descarga_M", "descarga_B",
    "normalizacion_G", "normalizacion_M", "normalizacion_B",
    "correccion_normalizacion",
    "transcripcion", "correccion_transcripciones",
    "analisis_A", "analisis_B",
    "correccion_analisis_A", "correccion_analisis_B",
}


def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


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
