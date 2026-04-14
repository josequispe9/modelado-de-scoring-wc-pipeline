from fastapi import APIRouter, Query
from typing import Optional
import psycopg2
import psycopg2.extras
import os

router = APIRouter()

def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


@router.get("/estado")
def estado_pipeline():
    """Resumen global: cuántos audios hay en cada etapa/estado."""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT etapa_actual, estado_global, COUNT(*) AS total
            FROM conversaciones
            GROUP BY etapa_actual, estado_global
            ORDER BY etapa_actual, estado_global
        """)
        return {"resumen": cur.fetchall()}


@router.get("/metricas")
def metricas_dashboard():
    """Métricas para el dashboard: totales, scores promedio, etc."""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("""
            SELECT
                COUNT(*)                                                     AS total_audios,
                COUNT(*) FILTER (WHERE estado_global = 'correcto')           AS completados,
                COUNT(*) FILTER (WHERE estado_global = 'error')              AS con_error,
                COUNT(*) FILTER (WHERE estado_global = 'reprocesar')         AS a_reprocesar,
                COUNT(*) FILTER (WHERE estado_global = 'en_proceso')         AS en_proceso,
                ROUND(AVG(duracion_conversacion_seg)::numeric, 1)            AS duracion_promedio_seg,
                ROUND(AVG((etapas->'analisis'->>'score_lead')::numeric), 2)  AS score_lead_promedio
            FROM conversaciones
        """)
        return cur.fetchone()


@router.get("/conversaciones")
def listar_conversaciones(
    estado: Optional[str] = Query(None),
    etapa:  Optional[str] = Query(None),
    limit:  int = Query(50, le=200),
    offset: int = Query(0),
):
    """Lista conversaciones con filtros opcionales para el dashboard."""
    filters = []
    params  = []

    if estado:
        filters.append("estado_global = %s")
        params.append(estado)
    if etapa:
        filters.append("etapa_actual = %s")
        params.append(etapa)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    params += [limit, offset]

    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"""
            SELECT id, numero_telefono, etapa_actual, estado_global,
                   duracion_conversacion_seg, fecha_llamada, fecha_ultima_actualizacion,
                   etapas->'analisis'->>'score_lead' AS score_lead
            FROM conversaciones
            {where}
            ORDER BY fecha_ultima_actualizacion DESC
            LIMIT %s OFFSET %s
        """, params)
        return {"conversaciones": cur.fetchall()}


@router.get("/conversaciones/{id}")
def detalle_conversacion(id: str):
    """Detalle completo de una conversación incluyendo el JSONB de etapas."""
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM conversaciones WHERE id = %s", (id,))
        row = cur.fetchone()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
        return row
