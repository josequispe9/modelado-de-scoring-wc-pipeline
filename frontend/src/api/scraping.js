import { SCRAPING_API_URL } from "./config"

const base = SCRAPING_API_URL

// ── Estado ────────────────────────────────────────────────────────────────────

export const getEstadoScraping = () =>
    fetch(`${base}/scraping/estado`).then(r => r.json())

export const getMetricas = () =>
    fetch(`${base}/scraping/metricas`).then(r => r.json())

// ── Ejecución ─────────────────────────────────────────────────────────────────

export const ejecutarScraping = (filtro = "pendientes") =>
    fetch(`${base}/scraping/ejecutar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filtro }),
    }).then(r => r.json())

export const pausarScraping = () =>
    fetch(`${base}/scraping/pausar`, { method: "POST" }).then(r => r.json())

// ── Parámetros ────────────────────────────────────────────────────────────────

export const getParametros = (clave) =>
    fetch(`${base}/scraping/parametros/${clave}`).then(r => r.json())

export const actualizarParametros = (clave, valor) =>
    fetch(`${base}/scraping/parametros/${clave}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ valor }),
    }).then(r => r.json())
