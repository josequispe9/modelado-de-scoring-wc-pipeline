"""
Endpoints de estadísticas del pipeline.
Todos los filtros de fecha usan la fecha de la llamada extraída del nombre_archivo.

Formato del nombre: amza84_1_260409113023330_ACD_08575
  → split_part(..., '_', 3) = '260409113023330'
  → left(..., 6) = '260409' = YYMMDD → 2026-04-09
"""
from fastapi import APIRouter, Query
from typing import Optional
import psycopg2
import psycopg2.extras
import os

router = APIRouter()

FECHA_EXPR = "to_date(left(split_part(nombre_archivo, '_', 3), 6), 'YYMMDD')"


def get_conn():
    return psycopg2.connect(os.environ["SCORING_DB_URL"])


def get_params(conn, clave: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT valor FROM pipeline_params WHERE clave = %s", (clave,))
        row = cur.fetchone()
    return row[0] if row and row[0] else {}


def fecha_conds(fecha_desde: Optional[str], fecha_hasta: Optional[str]) -> tuple[str, list]:
    """Retorna cláusulas AND y params para filtro de fecha (para añadir a WHERE existente)."""
    parts = []
    params = []
    if fecha_desde:
        parts.append(f"{FECHA_EXPR} >= %s")
        params.append(fecha_desde)
    if fecha_hasta:
        parts.append(f"{FECHA_EXPR} <= %s")
        params.append(fecha_hasta)
    clause = (" AND " + " AND ".join(parts)) if parts else ""
    return clause, params


# ─── Global ───────────────────────────────────────────────────────────────────

@router.get("/estadisticas/global")
def estadisticas_global(
    fecha_desde: Optional[str] = Query(None),
    fecha_hasta: Optional[str] = Query(None),
):
    """
    Cuenta cuántos audios PASARON por cada etapa (presencia en JSONB),
    no dónde están ahora. Esto evita que las etapas iniciales queden vacías
    cuando todos los audios ya avanzaron.

    - descarga / normalizacion: estado del propio campo en etapas
    - correccion_normalizacion: estado_global de audios que tienen esa clave
    - transcripcion: estado del último elemento del array
    - correccion_transcripciones: estado_global de audios que tienen esa clave
    """
    and_fecha, params = fecha_conds(fecha_desde, fecha_hasta)

    # params se repite una vez por cada bloque del UNION ALL que usa {and_fecha}
    all_params = params * 5

    query = f"""
        SELECT etapa, estado, COUNT(*) AS cantidad
        FROM (
            -- Descarga: etapas={{}} por diseño — toda fila = audio descargado correctamente
            SELECT 'descarga' AS etapa, 'correcto' AS estado
            FROM audio_pipeline_jobs
            WHERE 1=1 {and_fecha}

            UNION ALL

            -- Normalizacion: array de intentos por grupo — tomamos el último
            SELECT 'normalizacion',
                   etapas->'normalizacion'->-1->>'estado'
            FROM audio_pipeline_jobs
            WHERE etapas ? 'normalizacion'
              AND jsonb_array_length(etapas->'normalizacion') > 0
              {and_fecha}

            UNION ALL

            -- Correccion normalizacion
            SELECT 'correccion_normalizacion', estado_global
            FROM audio_pipeline_jobs
            WHERE etapas ? 'correccion_normalizacion' {and_fecha}

            UNION ALL

            -- Transcripcion: array de intentos, tomamos el último
            SELECT 'transcripcion',
                   etapas->'transcripcion'->-1->>'estado'
            FROM audio_pipeline_jobs
            WHERE etapas ? 'transcripcion'
              AND jsonb_array_length(etapas->'transcripcion') > 0
              {and_fecha}

            UNION ALL

            -- Correccion transcripciones
            SELECT 'correccion_transcripciones', estado_global
            FROM audio_pipeline_jobs
            WHERE etapas ? 'correccion_transcripciones' {and_fecha}
        ) sub
        WHERE estado IS NOT NULL
        GROUP BY etapa, estado
        ORDER BY etapa, estado
    """
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, all_params)
        rows = cur.fetchall()

    result: dict = {}
    for row in rows:
        etapa  = row["etapa"]
        estado = row["estado"]
        if etapa not in result:
            result[etapa] = {}
        result[etapa][estado] = row["cantidad"]
    return result


# ─── Etapa 1 ──────────────────────────────────────────────────────────────────

@router.get("/estadisticas/etapa1")
def estadisticas_etapa1(
    fecha_desde: Optional[str] = Query(None),
    fecha_hasta: Optional[str] = Query(None),
):
    and_fecha, params = fecha_conds(fecha_desde, fecha_hasta)
    with get_conn() as conn:
        # Stats guardadas por el scraping (último run por cuenta)
        stats_G = get_params(conn, "descarga_stats_G")
        stats_M = get_params(conn, "descarga_stats_M")
        stats_B = get_params(conn, "descarga_stats_B")

        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT
                    COUNT(*) AS registrados,
                    COUNT(*) FILTER (WHERE etapas->'descarga'->>'estado' = 'correcto') AS descargados,
                    COUNT(*) FILTER (WHERE etapas->'descarga'->>'estado' = 'error')    AS errores_descarga,
                    ARRAY_AGG(duracion_audio_seg ORDER BY duracion_audio_seg)
                        FILTER (WHERE duracion_audio_seg IS NOT NULL) AS duraciones
                FROM audio_pipeline_jobs
                WHERE 1=1 {and_fecha}
            """, params)
            row = cur.fetchone()

    def _sum(key):
        return sum(s.get(key, 0) or 0 for s in [stats_G, stats_M, stats_B])

    return {
        "registrados":              row["registrados"],
        "descargados":              row["descargados"],
        "errores_descarga":         row["errores_descarga"],
        "duraciones":               row["duraciones"] or [],
        "ultimo_run": {
            "disponibles_mitrol":   _sum("total_disponibles_mitrol"),
            "subidos":              _sum("subidos"),
            "omitidos":             _sum("omitidos"),
            "errores":              _sum("errores"),
            "por_cuenta": {
                "G": stats_G or {},
                "M": stats_M or {},
                "B": stats_B or {},
            },
        },
    }


# ─── Etapa 3 ──────────────────────────────────────────────────────────────────

@router.get("/estadisticas/etapa3")
def estadisticas_etapa3(
    fecha_desde: Optional[str] = Query(None),
    fecha_hasta: Optional[str] = Query(None),
):
    and_fecha, params = fecha_conds(fecha_desde, fecha_hasta)
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"""
            SELECT
                COUNT(*) FILTER (
                    WHERE EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements(COALESCE(etapas->'normalizacion', '[]'::jsonb)) e
                        WHERE e->>'estado' = 'correcto'
                    )
                ) AS correctos,
                COUNT(*) FILTER (
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements(COALESCE(etapas->'normalizacion', '[]'::jsonb)) e
                        WHERE e->>'estado' = 'correcto'
                    )
                    AND EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements(COALESCE(etapas->'normalizacion', '[]'::jsonb)) e
                        WHERE e->>'estado' = 'error'
                    )
                ) AS solo_errores
            FROM audio_pipeline_jobs
            WHERE etapas ? 'normalizacion' {and_fecha}
        """, params)
        row = cur.fetchone()

    return {
        "correctos":    row["correctos"]    or 0,
        "solo_errores": row["solo_errores"] or 0,
    }


# ─── Etapa 4 ──────────────────────────────────────────────────────────────────

@router.get("/estadisticas/etapa4")
def estadisticas_etapa4(
    fecha_desde: Optional[str] = Query(None),
    fecha_hasta: Optional[str] = Query(None),
):
    and_fecha, params = fecha_conds(fecha_desde, fecha_hasta)
    with get_conn() as conn:
        p = get_params(conn, "correccion_normalizacion")
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT
                    kv.value->>'estado'                              AS estado,
                    (kv.value->>'score')::float                     AS score,
                    (kv.value->'metricas'->>'snr')::float           AS snr,
                    (kv.value->'metricas'->>'rms_dbfs')::float      AS rms_dbfs,
                    (kv.value->'metricas'->>'duracion_ratio')::float AS duracion_ratio,
                    kv.value->>'motivo_invalido'                    AS motivo_invalido
                FROM audio_pipeline_jobs apj,
                     jsonb_each(COALESCE(apj.etapas->'correccion_normalizacion', '{{}}'::jsonb)) AS kv
                WHERE kv.key != 'ganador'
                  AND kv.value->>'estado' IS NOT NULL
                  {and_fecha}
            """, params)
            rows = [dict(r) for r in cur.fetchall()]

    conteos       = {"correcto": 0, "reprocesar": 0, "invalido": 0}
    scores        = []
    snr_vals      = []
    rms_vals      = []
    dur_ratio     = []
    causas        : dict = {}
    scatter_snr   = []
    scatter_dur   = []

    for r in rows:
        estado = r["estado"]
        if estado in conteos:
            conteos[estado] += 1

        if r["score"] is not None:
            scores.append(r["score"])
        if r["snr"] is not None:
            snr_vals.append(r["snr"])
        if r["rms_dbfs"] is not None:
            rms_vals.append(r["rms_dbfs"])
        if r["duracion_ratio"] is not None:
            dur_ratio.append(r["duracion_ratio"])

        if estado == "invalido":
            motivo = r["motivo_invalido"] or ""
            if "duracion" in motivo and "minimo" in motivo:
                cat = "duracion < minimo"
            elif "duracion" in motivo and "maximo" in motivo:
                cat = "duracion > maximo"
            elif "sample_rate" in motivo:
                cat = "sample_rate incorrecto"
            elif "canales" in motivo:
                cat = "canales incorrectos"
            elif r["score"] is not None:
                cat = "score bajo"
            else:
                cat = "otro"
            causas[cat] = causas.get(cat, 0) + 1

        if r["snr"] is not None and r["score"] is not None:
            scatter_snr.append({"x": r["snr"], "y": r["score"]})
        if r["duracion_ratio"] is not None and r["score"] is not None:
            scatter_dur.append({"x": r["duracion_ratio"], "y": r["score"]})

    return {
        "conteos":           conteos,
        "scores":            scores,
        "snr":               snr_vals,
        "rms_dbfs":          rms_vals,
        "duracion_ratio":    dur_ratio,
        "causas_invalido":   causas,
        "scatter_snr_score": scatter_snr,
        "scatter_dur_score": scatter_dur,
        "umbrales": {
            "correcto":   p.get("umbral_correcto",   0.75),
            "reprocesar": p.get("umbral_reprocesar", 0.40),
        },
    }


# ─── Etapa 5 ──────────────────────────────────────────────────────────────────

@router.get("/estadisticas/etapa5")
def estadisticas_etapa5(
    fecha_desde: Optional[str] = Query(None),
    fecha_hasta: Optional[str] = Query(None),
):
    and_fecha, params = fecha_conds(fecha_desde, fecha_hasta)
    with get_conn() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"""
            SELECT elem->>'estado' AS estado, COUNT(*) AS cantidad
            FROM audio_pipeline_jobs,
                 jsonb_array_elements(COALESCE(etapas->'transcripcion', '[]'::jsonb)) AS elem
            WHERE 1=1 {and_fecha}
            GROUP BY elem->>'estado'
        """, params)
        rows = cur.fetchall()

    conteos = {"correcto": 0, "error": 0}
    for r in rows:
        estado = r["estado"]
        if estado in conteos:
            conteos[estado] = r["cantidad"]
    return conteos


# ─── Etapa 6 ──────────────────────────────────────────────────────────────────

@router.get("/estadisticas/etapa6")
def estadisticas_etapa6(
    fecha_desde: Optional[str] = Query(None),
    fecha_hasta: Optional[str] = Query(None),
):
    and_fecha, params = fecha_conds(fecha_desde, fecha_hasta)
    with get_conn() as conn:
      p6 = get_params(conn, "correccion_transcripciones")
      with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"""
            SELECT
                kv.value->>'clasificacion'                           AS clasificacion,
                (kv.value->>'score_determinista')::float            AS score_det,
                (kv.value->>'score_llm')::float                     AS score_llm,
                (kv.value->>'score_total')::float                   AS score_total,
                kv.value->>'coherencia_llm'                         AS coherencia_llm,
                (kv.value->'metricas'->>'avg_logprob')::float       AS avg_logprob,
                (kv.value->'metricas'->>'total_words')::float       AS total_words,
                (kv.value->'metricas'->>'low_score_ratio')::float   AS low_score_ratio,
                (kv.value->'metricas'->>'speaker_dominance')::float AS speaker_dominance,
                kv.value->>'error'                                  AS motivo_invalido,
                kv.value->>'vendedor'                               AS vendedor,
                kv.value->>'cliente'                                AS cliente
            FROM audio_pipeline_jobs apj,
                 jsonb_each(COALESCE(apj.etapas->'correccion_transcripciones', '{{}}'::jsonb)) AS kv
            WHERE kv.key != 'ganador'
              AND kv.value->>'clasificacion' IS NOT NULL
              {and_fecha}
        """, params)
        rows = [dict(r) for r in cur.fetchall()]

    conteos          = {"correcto": 0, "reprocesar": 0, "invalido": 0}
    coherencia_cnt   : dict = {}
    causas_invalido  : dict = {}
    avg_logprob_vals = []
    total_words_vals = []
    low_score_vals   = []
    speaker_dom_vals = []
    score_llm_vals   = []
    score_total_vals = []
    scatter_det_llm  = []
    roles_ok         = 0
    total_con_llm    = 0

    for r in rows:
        clf = r["clasificacion"]
        if clf in conteos:
            conteos[clf] += 1

        if r["coherencia_llm"]:
            coh = r["coherencia_llm"]
            coherencia_cnt[coh] = coherencia_cnt.get(coh, 0) + 1
            total_con_llm += 1

        if clf == "invalido" and r["motivo_invalido"]:
            m = r["motivo_invalido"]
            if "num_hablantes" in m:
                cat = "hablantes < 2"
            elif "total_words" in m:
                cat = "pocas palabras"
            elif "avg_logprob" in m:
                cat = "logprob bajo"
            elif "speaker_dominance" in m:
                cat = "un speaker domina"
            elif "low_score_ratio" in m:
                cat = "palabras inciertas"
            else:
                cat = "otro"
            causas_invalido[cat] = causas_invalido.get(cat, 0) + 1

        if r["avg_logprob"] is not None:
            avg_logprob_vals.append(r["avg_logprob"])
        if r["total_words"] is not None:
            total_words_vals.append(r["total_words"])
        if r["low_score_ratio"] is not None:
            low_score_vals.append(r["low_score_ratio"])
        if r["speaker_dominance"] is not None:
            speaker_dom_vals.append(r["speaker_dominance"])
        if r["score_llm"] is not None:
            score_llm_vals.append(r["score_llm"])
        if r["score_total"] is not None:
            score_total_vals.append(r["score_total"])
        if r["score_det"] is not None and r["score_llm"] is not None:
            scatter_det_llm.append({"x": r["score_det"], "y": r["score_llm"]})
        if r["vendedor"] not in (None, "desconocido") or r["cliente"] not in (None, "desconocido"):
            roles_ok += 1

    return {
        "conteos":           conteos,
        "coherencia":        coherencia_cnt,
        "causas_invalido":   causas_invalido,
        "avg_logprob":       avg_logprob_vals,
        "total_words":       total_words_vals,
        "low_score_ratio":   low_score_vals,
        "speaker_dominance": speaker_dom_vals,
        "score_llm":         score_llm_vals,
        "score_total":       score_total_vals,
        "scatter_det_llm":   scatter_det_llm,
        "pct_roles":         round(roles_ok / total_con_llm, 4) if total_con_llm > 0 else 0.0,
        "umbrales": {
            "correcto":   p6.get("umbral_score_correcto",   0.75),
            "reprocesar": p6.get("umbral_score_reprocesar", 0.40),
        },
    }
