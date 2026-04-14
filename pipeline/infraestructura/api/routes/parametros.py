from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import psycopg2
import psycopg2.extras
import json
import os

router = APIRouter()

CLAVES_VALIDAS = {"limpieza", "transcripcion", "analisis"}

def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


class ActualizarParametros(BaseModel):
    valor: dict


@router.get("/parametros/{clave}")
def get_parametros(clave: str):
    if clave not in CLAVES_VALIDAS:
        raise HTTPException(status_code=404, detail=f"Clave '{clave}' no existe")
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT clave, valor, updated_at FROM parametros_pipeline WHERE clave = %s", (clave,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Parámetro no encontrado")
        return row


@router.patch("/parametros/{clave}")
def actualizar_parametros(clave: str, body: ActualizarParametros):
    """
    Actualiza parámetros que los DAGs leerán en el próximo run.
    Ejemplo: PATCH /pipeline/parametros/limpieza
             body: {"valor": {"silencio_db": -40, "min_duracion_seg": 3}}
    """
    if clave not in CLAVES_VALIDAS:
        raise HTTPException(status_code=404, detail=f"Clave '{clave}' no existe")
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO parametros_pipeline (clave, valor)
            VALUES (%s, %s)
            ON CONFLICT (clave) DO UPDATE
                SET valor = EXCLUDED.valor, updated_at = now()
        """, (clave, json.dumps(body.valor)))
        conn.commit()
    return {"clave": clave, "valor": body.valor}
