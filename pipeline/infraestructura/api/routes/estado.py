from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Optional
import psycopg2
import psycopg2.extras
import os
import sys
from pathlib import Path
from minio.error import S3Error

sys.path.insert(0, str(Path(__file__).parents[3] / "logica" / "obtener-datos"))
from obtener_audio import obtener_audio, _extraer_ubicaciones_minio
from descargar_audio import obtener_stream

router = APIRouter()

def get_conn():
    return psycopg2.connect(os.environ["SCORING_DB_URL"])


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
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
        return row


@router.get("/audio/descargar")
def descargar_audio(
    bucket: str  = Query(...),
    key:    str  = Query(...),
    inline: bool = Query(False),
):
    """
    Sirve un archivo de MinIO.
    inline=false (default) → descarga forzada.
    inline=true            → reproducción en el browser (para <audio>).
    """
    try:
        response, tamanio = obtener_stream(bucket, key)
    except S3Error as e:
        raise HTTPException(status_code=404, detail=f"Objeto no encontrado: {e}")

    filename = key.split("/")[-1]
    disposition = f'inline; filename="{filename}"' if inline else f'attachment; filename="{filename}"'
    headers = {"Content-Disposition": disposition}
    if tamanio:
        headers["Content-Length"] = str(tamanio)

    return StreamingResponse(
        response,
        media_type="audio/wav",
        headers=headers,
        background=None,
    )


@router.get("/audio/{identificador}")
def detalle_audio(identificador: str):
    """
    Detalle completo de un audio por UUID o nombre_archivo.
    Incluye todas las columnas de audio_pipeline_jobs más las ubicaciones
    en MinIO extraídas del JSONB de etapas.
    """
    datos = obtener_audio(identificador)
    if not datos:
        raise HTTPException(status_code=404, detail=f"Audio no encontrado: {identificador}")
    return datos


@router.get("/audios/aleatorios")
def audios_aleatorios(
    cantidad:       int           = Query(10, ge=1, le=100),
    duracion_desde: Optional[int] = Query(None),
    duracion_hasta: Optional[int] = Query(None),
    fecha_desde:    Optional[str] = Query(None),   # dd/mm/yyyy
    fecha_hasta:    Optional[str] = Query(None),   # dd/mm/yyyy
    hora_desde:     Optional[str] = Query(None),   # HH:MM
    hora_hasta:     Optional[str] = Query(None),   # HH:MM
    agente:         Optional[str] = Query(None),
    telefono:       Optional[str] = Query(None),
    etapa:          Optional[str] = Query(None),
    estado:         Optional[str] = Query(None),
):
    """Retorna N audios aleatorios según filtros opcionales."""
    filters = []
    params  = []

    if duracion_desde is not None:
        filters.append("duracion_audio_seg >= %s")
        params.append(duracion_desde)
    if duracion_hasta is not None:
        filters.append("duracion_audio_seg <= %s")
        params.append(duracion_hasta)
    if agente:
        filters.append("agente ILIKE %s")
        params.append(f"%{agente}%")
    if telefono:
        filters.append("numero_telefono ILIKE %s")
        params.append(f"%{telefono}%")
    if etapa:
        filters.append("etapa_actual = %s")
        params.append(etapa)
    if estado:
        filters.append("estado_global = %s")
        params.append(estado)
    if fecha_desde:
        filters.append("inicio IS NOT NULL AND TO_DATE(SUBSTRING(inicio, 1, 10), 'DD/MM/YYYY') >= TO_DATE(%s, 'DD/MM/YYYY')")
        params.append(fecha_desde)
    if fecha_hasta:
        filters.append("inicio IS NOT NULL AND TO_DATE(SUBSTRING(inicio, 1, 10), 'DD/MM/YYYY') <= TO_DATE(%s, 'DD/MM/YYYY')")
        params.append(fecha_hasta)
    if hora_desde:
        filters.append("inicio IS NOT NULL AND SUBSTRING(inicio, 12, 5) >= %s")
        params.append(hora_desde)
    if hora_hasta:
        filters.append("inicio IS NOT NULL AND SUBSTRING(inicio, 12, 5) <= %s")
        params.append(hora_hasta)

    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    params.append(cantidad)

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"SELECT * FROM audio_pipeline_jobs {where} ORDER BY RANDOM() LIMIT %s",
                params,
            )
            rows = cur.fetchall()

    resultado = []
    for row in rows:
        d = dict(row)
        for campo in ("id", "fecha_llamada", "created_at", "fecha_ultima_actualizacion"):
            if d.get(campo) is not None:
                d[campo] = str(d[campo])
        d["ubicaciones_minio"] = _extraer_ubicaciones_minio(d.get("etapas") or {})
        resultado.append(d)

    return {"audios": resultado}
