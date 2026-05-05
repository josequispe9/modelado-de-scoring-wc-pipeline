import { PIPELINE_API_URL } from "./config"

const base = PIPELINE_API_URL

// ── Estado ────────────────────────────────────────────────────────────────────

export const getEstadoPipeline = () =>
    fetch(`${base}/pipeline/estado`).then(r => r.json())

export const getMetricas = () =>
    fetch(`${base}/pipeline/metricas`).then(r => r.json())

export const getConversaciones = (filtros = {}) => {
    const params = new URLSearchParams(filtros)
    return fetch(`${base}/pipeline/conversaciones?${params}`).then(r => r.json())
}

export const getConversacion = (id) =>
    fetch(`${base}/pipeline/conversaciones/${id}`).then(r => r.json())

// ── Ejecución ─────────────────────────────────────────────────────────────────

export const ejecutarPipeline = () =>
    fetch(`${base}/pipeline/ejecutar`, { method: "POST" }).then(r => r.json())

export const ejecutarEtapa = (etapa, filtro = "pendientes", ids = null) =>
    fetch(`${base}/pipeline/etapa/${etapa}/ejecutar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filtro, ids }),
    }).then(r => r.json())

export const pausarEtapa = (etapa) =>
    fetch(`${base}/pipeline/etapa/${etapa}/pausar`, { method: "POST" }).then(r => r.json())

export const limpiarAudiosNormalizacion = () =>
    fetch(`${base}/pipeline/etapa/correccion_normalizacion/limpiar`, { method: "POST" }).then(r => r.json())

export const resetearCorreccionNormalizacion = () =>
    fetch(`${base}/pipeline/etapa/correccion_normalizacion/resetear`, { method: "POST" }).then(r => r.json())

export const limpiarTranscripciones = () =>
    fetch(`${base}/pipeline/etapa/correccion_transcripciones/limpiar`, { method: "POST" }).then(r => r.json())

export const resetearCorreccionTranscripciones = () =>
    fetch(`${base}/pipeline/etapa/correccion_transcripciones/resetear`, { method: "POST" }).then(r => r.json())

// ── Parámetros ────────────────────────────────────────────────────────────────

export const getParametros = (clave) =>
    fetch(`${base}/pipeline/parametros/${clave}`).then(r => r.json())

export const actualizarParametros = (clave, valor) =>
    fetch(`${base}/pipeline/parametros/${clave}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ valor }),
    }).then(r => r.json())

export const getAudio = (identificador) =>
    fetch(`${base}/pipeline/audio/${encodeURIComponent(identificador)}`).then(r => {
        if (!r.ok) throw new Error("No encontrado")
        return r.json()
    })

export const getUrlDescargaAudio = (bucket, key) =>
    `${base}/pipeline/audio/descargar?bucket=${encodeURIComponent(bucket)}&key=${encodeURIComponent(key)}`

export const getUrlStreamAudio = (bucket, key) =>
    `${base}/pipeline/audio/descargar?bucket=${encodeURIComponent(bucket)}&key=${encodeURIComponent(key)}&inline=true`

// ── Estadísticas ──────────────────────────────────────────────────────────────

const buildFechaParams = (fechaDesde, fechaHasta) => {
    const p = new URLSearchParams()
    if (fechaDesde) p.append("fecha_desde", fechaDesde)
    if (fechaHasta) p.append("fecha_hasta", fechaHasta)
    return p.toString()
}

export const getEstadisticasGlobal = (fechaDesde, fechaHasta) => {
    const q = buildFechaParams(fechaDesde, fechaHasta)
    return fetch(`${base}/pipeline/estadisticas/global${q ? "?" + q : ""}`).then(r => r.json())
}

export const getEstadisticasEtapa1 = (fechaDesde, fechaHasta) => {
    const q = buildFechaParams(fechaDesde, fechaHasta)
    return fetch(`${base}/pipeline/estadisticas/etapa1${q ? "?" + q : ""}`).then(r => r.json())
}

export const getEstadisticasEtapa3 = (fechaDesde, fechaHasta) => {
    const q = buildFechaParams(fechaDesde, fechaHasta)
    return fetch(`${base}/pipeline/estadisticas/etapa3${q ? "?" + q : ""}`).then(r => r.json())
}

export const getEstadisticasEtapa4 = (fechaDesde, fechaHasta) => {
    const q = buildFechaParams(fechaDesde, fechaHasta)
    return fetch(`${base}/pipeline/estadisticas/etapa4${q ? "?" + q : ""}`).then(r => r.json())
}

export const getEstadisticasEtapa5 = (fechaDesde, fechaHasta) => {
    const q = buildFechaParams(fechaDesde, fechaHasta)
    return fetch(`${base}/pipeline/estadisticas/etapa5${q ? "?" + q : ""}`).then(r => r.json())
}

export const getEstadisticasEtapa6 = (fechaDesde, fechaHasta) => {
    const q = buildFechaParams(fechaDesde, fechaHasta)
    return fetch(`${base}/pipeline/estadisticas/etapa6${q ? "?" + q : ""}`).then(r => r.json())
}

export const getAudiosAleatorios = (filtros = {}) => {
    const params = new URLSearchParams()
    Object.entries(filtros).forEach(([k, v]) => {
        if (v !== null && v !== undefined && v !== "") params.append(k, v)
    })
    return fetch(`${base}/pipeline/audios/aleatorios?${params}`).then(r => {
        if (!r.ok) throw new Error("Error al buscar audios")
        return r.json()
    })
}
