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

// ── Parámetros ────────────────────────────────────────────────────────────────

export const getParametros = (clave) =>
    fetch(`${base}/pipeline/parametros/${clave}`).then(r => r.json())

export const actualizarParametros = (clave, valor) =>
    fetch(`${base}/pipeline/parametros/${clave}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ valor }),
    }).then(r => r.json())
