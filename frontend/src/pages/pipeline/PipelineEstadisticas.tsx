import { useState, useCallback } from "react"
import Plotly from "plotly.js-dist-min"
import createPlotlyComponent from "react-plotly.js/factory"
import { Button } from "@/components/ui/button"
import {
  getEstadisticasGlobal,
  getEstadisticasEtapa1,
  getEstadisticasEtapa3,
  getEstadisticasEtapa4,
  getEstadisticasEtapa5,
  getEstadisticasEtapa6,
} from "@/api/pipeline"

const Plot = createPlotlyComponent(Plotly)

// ── Paleta científica (desaturada, sin colores de semáforo) ───────────────────

const C = {
  correcto:   "#5c8a6e",  // sage green
  reprocesar: "#a07840",  // ochre
  invalido:   "#8a4f4f",  // wine
  error:      "#7a5a3a",  // brown
  en_proceso: "#5a6472",  // slate
  a:          "#4a7fa5",  // steel blue
  b:          "#7a6fa0",  // muted violet
  c:          "#5a8a7a",  // teal
  d:          "#a07850",  // amber
}

// ── Config base Plotly ────────────────────────────────────────────────────────

const GRID = "#e2e8f0"
const AXIS = "#64748b"
const FONT_COLOR = "#475569"

const BASE_LAYOUT: Partial<Plotly.Layout> = {
  paper_bgcolor: "transparent",
  plot_bgcolor:  "transparent",
  font:          { family: "Inter, system-ui, sans-serif", size: 11, color: FONT_COLOR },
  margin:        { t: 24, r: 16, b: 40, l: 52 },
}

const AXIS_STYLE = {
  color:          AXIS,
  gridcolor:      GRID,
  linecolor:      GRID,
  zerolinecolor:  GRID,
  tickfont:       { size: 10 },
  showline:       true,
  mirror:         true,
}

const BASE_CONFIG: Partial<Plotly.Config> = {
  displayModeBar: false,
  responsive:     true,
}

const PLOT_STYLE = { width: "100%", height: "100%" }

// ── Tipos ─────────────────────────────────────────────────────────────────────

type DatosGlobal = Record<string, Record<string, number>>
type DatosEtapa1 = {
  registrados:      number
  descargados:      number
  errores_descarga: number
  duraciones:       number[]
  ultimo_run: {
    disponibles_mitrol: number
    subidos:            number
    omitidos:           number
    errores:            number
    por_cuenta: Record<string, { total_disponibles_mitrol?: number; subidos?: number; omitidos?: number; errores?: number; fecha_run?: string }>
  }
}
type DatosEtapa3 = { correctos: number; solo_errores: number }
type DatosEtapa4 = {
  conteos:           { correcto: number; reprocesar: number; invalido: number }
  scores:            number[]
  snr:               number[]
  rms_dbfs:          number[]
  duracion_ratio:    number[]
  causas_invalido:   Record<string, number>
  scatter_snr_score: { x: number; y: number }[]
  scatter_dur_score: { x: number; y: number }[]
  umbrales:          { correcto: number; reprocesar: number }
}
type DatosEtapa5 = { correcto: number; error: number }
type DatosEtapa6 = {
  conteos:           { correcto: number; reprocesar: number; invalido: number }
  coherencia:        Record<string, number>
  causas_invalido:   Record<string, number>
  avg_logprob:       number[]
  total_words:       number[]
  low_score_ratio:   number[]
  speaker_dominance: number[]
  score_llm:         number[]
  score_total:       number[]
  scatter_det_llm:   { x: number; y: number }[]
  pct_roles:         number
  umbrales:          { correcto: number; reprocesar: number }
}

// ── Helpers de fecha ──────────────────────────────────────────────────────────

const hoy = () => new Date().toISOString().slice(0, 10)
const restarDias = (n: number) => {
  const d = new Date(); d.setDate(d.getDate() - n); return d.toISOString().slice(0, 10)
}

// ── Componentes base ──────────────────────────────────────────────────────────

function Metrica({
  label, valor, sub,
}: { label: string; valor: number | string; sub?: string }) {
  return (
    <div className="flex flex-col gap-0.5 py-3 px-4 border-l-2 border-border">
      <span className="text-[11px] uppercase tracking-widest text-muted-foreground">{label}</span>
      <span className="text-2xl font-light text-foreground tabular-nums">{valor}</span>
      {sub && <span className="text-[10px] text-muted-foreground">{sub}</span>}
    </div>
  )
}

function SeccionHeader({ n, titulo, desc }: { n: string; titulo: string; desc?: string }) {
  return (
    <div className="mb-5 pb-3 border-b border-border">
      <div className="flex items-baseline gap-3">
        <span className="text-[10px] text-muted-foreground tabular-nums">{n}</span>
        <h2 className="text-sm font-medium text-foreground">{titulo}</h2>
      </div>
      {desc && <p className="text-[11px] text-muted-foreground mt-1 ml-8">{desc}</p>}
    </div>
  )
}

function FigureLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] text-muted-foreground mb-1">{children}</p>
  )
}

function SinDatos() {
  return (
    <div className="flex items-center justify-center h-full text-[11px] text-muted-foreground border border-border/40 rounded-sm">
      n/a
    </div>
  )
}

function Figure({
  label, children, height = 220,
}: { label: string; children: React.ReactNode; height?: number }) {
  return (
    <div>
      <FigureLabel>{label}</FigureLabel>
      <div style={{ height }} className="w-full">{children}</div>
    </div>
  )
}

// ── Histograma ────────────────────────────────────────────────────────────────

function Hist({
  data, label, color = C.a, xbins, xaxis, shapes, height = 200,
}: {
  data:    number[]
  label:   string
  color?:  string
  xbins?:  Partial<Plotly.XBins>
  xaxis?:  Partial<Plotly.LayoutAxis>
  shapes?: Partial<Plotly.Shape>[]
  height?: number
}) {
  if (!data?.length) return <Figure label={label} height={height}><SinDatos /></Figure>

  const n = data.length
  const mean = data.reduce((a, b) => a + b, 0) / n
  const std  = Math.sqrt(data.reduce((a, b) => a + (b - mean) ** 2, 0) / n)

  const statsAnnotation: Partial<Plotly.Annotations> = {
    xref: "paper", yref: "paper",
    x: 0.98, y: 0.97,
    xanchor: "right", yanchor: "top",
    text: `n=${n} · μ=${mean.toFixed(3)} · σ=${std.toFixed(3)}`,
    showarrow: false,
    font: { size: 9, color: AXIS, family: "ui-monospace, monospace" },
  }

  return (
    <div>
      <FigureLabel>{label}</FigureLabel>
      <div style={{ height }} className="w-full">
        <Plot
          data={[{ type: "histogram", x: data, marker: { color }, xbins }]}
          layout={{
            ...BASE_LAYOUT,
            xaxis:       { ...AXIS_STYLE, ...xaxis },
            yaxis:       { ...AXIS_STYLE, title: { text: "n", font: { size: 10 } } },
            shapes,
            annotations: [statsAnnotation],
            bargap:      0.05,
          }}
          config={BASE_CONFIG}
          style={PLOT_STYLE}
        />
      </div>
    </div>
  )
}

// ── Scatter ───────────────────────────────────────────────────────────────────

function Scatter({
  puntos, label, xLabel, yLabel, color = C.a, height = 240,
}: {
  puntos: { x: number; y: number }[]
  label:  string
  xLabel?: string
  yLabel?: string
  color?:  string
  height?: number
}) {
  if (!puntos?.length) return <Figure label={label} height={height}><SinDatos /></Figure>

  return (
    <Figure label={label} height={height}>
      <Plot
        data={[{
          type:   "scatter",
          mode:   "markers",
          x:      puntos.map(p => p.x),
          y:      puntos.map(p => p.y),
          marker: { color, size: 5, opacity: 0.7, line: { width: 0 } },
        }]}
        layout={{
          ...BASE_LAYOUT,
          xaxis: { ...AXIS_STYLE, title: { text: xLabel, font: { size: 10 } } },
          yaxis: { ...AXIS_STYLE, title: { text: yLabel, font: { size: 10 } } },
        }}
        config={BASE_CONFIG}
        style={PLOT_STYLE}
      />
    </Figure>
  )
}

// ── Bar horizontal ────────────────────────────────────────────────────────────

function BarH({
  data, label, color = C.a,
}: { data: Record<string, number>; label: string; color?: string }) {
  const entries = Object.entries(data ?? {})
  if (!entries.length) return <Figure label={label}><SinDatos /></Figure>

  const cats = entries.map(([k]) => k)
  const vals = entries.map(([, v]) => v)
  const h    = Math.max(160, cats.length * 28 + 56)

  return (
    <Figure label={label} height={h}>
      <Plot
        data={[{
          type:        "bar",
          orientation: "h",
          x:           vals,
          y:           cats,
          marker:      { color },
        }]}
        layout={{
          ...BASE_LAYOUT,
          margin: { t: 16, r: 16, b: 36, l: 160 },
          xaxis:  { ...AXIS_STYLE },
          yaxis:  { ...AXIS_STYLE, automargin: true },
        }}
        config={BASE_CONFIG}
        style={PLOT_STYLE}
      />
    </Figure>
  )
}

// ── Sección Global ────────────────────────────────────────────────────────────

const ETAPAS_ORD = [
  "descarga",
  "normalizacion",
  "correccion_normalizacion",
  "transcripcion",
  "correccion_transcripciones",
]
const ETAPAS_LBL: Record<string, string> = {
  descarga:                   "E1 Descarga",
  normalizacion:              "E3 Normalización",
  correccion_normalizacion:   "E4 Correc. Norm.",
  transcripcion:              "E5 Transcripción",
  correccion_transcripciones: "E6 Correc. Transcr.",
}
const ESTADOS_BARRAS = [
  { key: "correcto",   label: "correcto",   color: C.correcto   },
  { key: "reprocesar", label: "reprocesar", color: C.reprocesar },
  { key: "invalido",   label: "inválido",   color: C.invalido   },
  { key: "error",      label: "error",      color: C.error      },
  { key: "en_proceso", label: "en proceso", color: C.en_proceso },
]

function SeccionGlobal({ datos }: { datos: DatosGlobal | null }) {
  if (!datos) return <p className="text-xs text-muted-foreground font-mono">—</p>

  const labels = ETAPAS_ORD.map(e => ETAPAS_LBL[e] ?? e)
  const trazas: Plotly.Data[] = ESTADOS_BARRAS.map(({ key, label, color }) => ({
    type:   "bar",
    name:   label,
    x:      labels,
    y:      ETAPAS_ORD.map(e => datos[e]?.[key] ?? 0),
    marker: { color },
  }))

  return (
    <div style={{ height: 320 }} className="w-full">
      <Plot
        data={trazas}
        layout={{
          ...BASE_LAYOUT,
          barmode: "group",
          bargap:  0.2,
          xaxis:   { ...AXIS_STYLE },
          yaxis:   { ...AXIS_STYLE, title: { text: "n", font: { size: 10 } } },
          legend:  { orientation: "h", y: -0.22, font: { size: 10, color: AXIS }, bgcolor: "transparent" },
          margin:  { t: 16, r: 16, b: 72, l: 52 },
        }}
        config={BASE_CONFIG}
        style={PLOT_STYLE}
      />
    </div>
  )
}

// ── Secciones por etapa ───────────────────────────────────────────────────────

function SeccionEtapa1({ datos }: { datos: DatosEtapa1 | null }) {
  if (!datos) return null
  const run = datos.ultimo_run
  return (
    <div className="flex flex-col gap-6">
      <div className="flex gap-0 flex-wrap">
        <Metrica label="Registrados en DB"      valor={datos.registrados} />
        <Metrica label="Descargados correctamente" valor={datos.descargados} />
        <Metrica label="Errores de descarga"    valor={datos.errores_descarga} />
      </div>
      {run.disponibles_mitrol > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-xs text-muted-foreground">Último run de descarga</p>
          <div className="flex gap-0 flex-wrap">
            <Metrica label="Disponibles en Mitrol" valor={run.disponibles_mitrol} sub="con los filtros aplicados" />
            <Metrica label="Subidos"   valor={run.subidos}  />
            <Metrica label="Omitidos"  valor={run.omitidos} sub="ya existían en MinIO" />
            <Metrica label="Errores"   valor={run.errores}  />
          </div>
        </div>
      )}
      <div className="grid grid-cols-2 gap-x-8">
        <Hist
          data={datos.duraciones}
          label="Fig. 1a — Distribución de duración de audios (segundos)"
          color={C.a}
          xaxis={{ title: { text: "duración (s)", font: { size: 10 } } }}
          height={200}
        />
        <Figure label="Fig. 1b — Boxplot de duración (outliers)" height={200}>
          {!datos.duraciones?.length ? <SinDatos /> : (
            <Plot
              data={[{
                type:        "box",
                x:           datos.duraciones,
                orientation: "h",
                marker:      { color: C.a },
                line:        { color: C.a },
                boxpoints:   "outliers",
                jitter:      0.3,
                pointpos:    0,
                name:        "",
              }]}
              layout={{
                ...BASE_LAYOUT,
                xaxis: { ...AXIS_STYLE, title: { text: "duración (s)", font: { size: 10 } } },
                yaxis: { ...AXIS_STYLE, showticklabels: false },
                showlegend: false,
              }}
              config={BASE_CONFIG}
              style={PLOT_STYLE}
            />
          )}
        </Figure>
      </div>
    </div>
  )
}

function SeccionEtapa3({ datos }: { datos: DatosEtapa3 | null }) {
  if (!datos) return null
  return (
    <div className="flex gap-0">
      <Metrica label="Procesados correctamente" valor={datos.correctos} />
      <Metrica label="Solo errores"             valor={datos.solo_errores} />
    </div>
  )
}

function SeccionEtapa4({ datos }: { datos: DatosEtapa4 | null }) {
  if (!datos) return null
  const total = datos.conteos.correcto + datos.conteos.reprocesar + datos.conteos.invalido

  const umb = datos.umbrales ?? { correcto: 0.75, reprocesar: 0.40 }

  const shapeRep4: Partial<Plotly.Shape> = {
    type: "line", x0: umb.reprocesar, x1: umb.reprocesar, y0: 0, y1: 1,
    xref: "x", yref: "paper",
    line: { color: C.reprocesar, width: 1.5, dash: "dot" },
  }
  const shapeCor4: Partial<Plotly.Shape> = {
    type: "line", x0: umb.correcto, x1: umb.correcto, y0: 0, y1: 1,
    xref: "x", yref: "paper",
    line: { color: C.correcto, width: 1.5, dash: "dot" },
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex gap-0">
        <Metrica label="Correcto"   valor={datos.conteos.correcto}
          sub={total ? `${((datos.conteos.correcto / total) * 100).toFixed(1)}%` : undefined} />
        <Metrica label="Reprocesar" valor={datos.conteos.reprocesar}
          sub={total ? `${((datos.conteos.reprocesar / total) * 100).toFixed(1)}%` : undefined} />
        <Metrica label="Inválido"   valor={datos.conteos.invalido}
          sub={total ? `${((datos.conteos.invalido / total) * 100).toFixed(1)}%` : undefined} />
        <Metrica label="Umbral correcto"   valor={umb.correcto}   sub={`score ≥ ${umb.correcto} → correcto`} />
        <Metrica label="Umbral reprocesar" valor={umb.reprocesar} sub={`score ≥ ${umb.reprocesar} → reprocesar`} />
      </div>

      <div className="grid grid-cols-2 gap-x-8 gap-y-8">
        <Hist
          data={datos.scores}
          label={`Fig. 2 — Distribución de score compuesto (umbrales: reprocesar=${umb.reprocesar} · correcto=${umb.correcto})`}
          color={C.a}
          xbins={{ size: 0.05 }}
          xaxis={{ title: { text: "score", font: { size: 10 } }, range: [0, 1] }}
          shapes={[shapeRep4, shapeCor4]}
        />
        <BarH
          data={datos.causas_invalido}
          label="Fig. 3 — Causas de clasificación inválida"
          color={C.invalido}
        />
        <Hist
          data={datos.snr}
          label="Fig. 4 — Distribución de SNR (dB)"
          color={C.b}
          xaxis={{ title: { text: "SNR (dB)", font: { size: 10 } } }}
        />
        <Hist
          data={datos.rms_dbfs}
          label="Fig. 5 — Distribución de nivel RMS (dBFS)"
          color={C.c}
          xaxis={{ title: { text: "RMS (dBFS)", font: { size: 10 } } }}
        />
        <Hist
          data={datos.duracion_ratio}
          label="Fig. 6 — Duration ratio (normalizado / original)"
          color={C.d}
          xbins={{ size: 0.05 }}
          xaxis={{ title: { text: "ratio", font: { size: 10 } }, range: [0, 1] }}
        />
      </div>

      <div className="grid grid-cols-2 gap-x-8">
        <Scatter
          puntos={datos.scatter_snr_score}
          label="Fig. 7 — SNR vs Score"
          xLabel="SNR (dB)"
          yLabel="score"
          color={C.b}
        />
        <Scatter
          puntos={datos.scatter_dur_score}
          label="Fig. 8 — Duration Ratio vs Score"
          xLabel="duration ratio"
          yLabel="score"
          color={C.d}
        />
      </div>
    </div>
  )
}

function SeccionEtapa5({ datos }: { datos: DatosEtapa5 | null }) {
  if (!datos) return null
  return (
    <div className="flex gap-0">
      <Metrica label="Correctos" valor={datos.correcto} />
      <Metrica label="Errores"   valor={datos.error}    />
    </div>
  )
}

function SeccionEtapa6({ datos }: { datos: DatosEtapa6 | null }) {
  if (!datos) return null

  const total = datos.conteos.correcto + datos.conteos.reprocesar + datos.conteos.invalido
  const umb6  = datos.umbrales ?? { correcto: 0.75, reprocesar: 0.40 }

  const cohKeys    = Object.keys(datos.coherencia)
  const cohColors  = cohKeys.map(k =>
    k === "coherente" ? C.correcto : k === "incoherente" ? C.invalido : C.reprocesar
  )

  const shapeRep: Partial<Plotly.Shape> = {
    type: "line", x0: umb6.reprocesar, x1: umb6.reprocesar, y0: 0, y1: 1,
    xref: "x", yref: "paper",
    line: { color: C.reprocesar, width: 1.5, dash: "dot" },
  }
  const shapeCor: Partial<Plotly.Shape> = {
    type: "line", x0: umb6.correcto, x1: umb6.correcto, y0: 0, y1: 1,
    xref: "x", yref: "paper",
    line: { color: C.correcto, width: 1.5, dash: "dot" },
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex gap-0">
        <Metrica label="Correcto"   valor={datos.conteos.correcto}
          sub={total ? `${((datos.conteos.correcto / total) * 100).toFixed(1)}%` : undefined} />
        <Metrica label="Reprocesar" valor={datos.conteos.reprocesar}
          sub={total ? `${((datos.conteos.reprocesar / total) * 100).toFixed(1)}%` : undefined} />
        <Metrica label="Inválido"   valor={datos.conteos.invalido}
          sub={total ? `${((datos.conteos.invalido / total) * 100).toFixed(1)}%` : undefined} />
        <Metrica
          label="Roles identificados"
          valor={`${(datos.pct_roles * 100).toFixed(1)}%`}
          sub="vendedor + cliente"
        />
      </div>

      <div className="grid grid-cols-2 gap-x-8 gap-y-8">

        {/* Pie coherencia */}
        <Figure label="Fig. 9 — Coherencia LLM" height={220}>
          {!cohKeys.length ? <SinDatos /> : (
            <Plot
              data={[{
                type:    "pie",
                labels:  cohKeys,
                values:  cohKeys.map(k => datos.coherencia[k]),
                marker:  { colors: cohColors, line: { color: "#ffffff", width: 1 } },
                textinfo: "label+percent",
                textfont: { size: 10, color: FONT_COLOR },
                hole:    0.4,
              }]}
              layout={{
                ...BASE_LAYOUT,
                margin:     { t: 16, r: 16, b: 16, l: 16 },
                showlegend: false,
              }}
              config={BASE_CONFIG}
              style={PLOT_STYLE}
            />
          )}
        </Figure>

        <BarH
          data={datos.causas_invalido}
          label="Fig. 10 — Causas de clasificación inválida"
          color={C.invalido}
        />

        <Hist
          data={datos.avg_logprob}
          label="Fig. 11 — avg_logprob (confianza Whisper)"
          color={C.b}
          xaxis={{ title: { text: "logprob", font: { size: 10 } } }}
        />
        <Hist
          data={datos.total_words}
          label="Fig. 12 — Total de palabras por transcripción"
          color={C.a}
          xaxis={{ title: { text: "palabras", font: { size: 10 } } }}
        />
        <Hist
          data={datos.low_score_ratio}
          label="Fig. 13 — Low score ratio (palabras de baja confianza)"
          color={C.d}
          xbins={{ size: 0.05 }}
          xaxis={{ title: { text: "ratio", font: { size: 10 } }, range: [0, 1] }}
        />
        <Hist
          data={datos.speaker_dominance}
          label="Fig. 14 — Speaker dominance"
          color={C.c}
          xbins={{ size: 0.05 }}
          xaxis={{ title: { text: "dominance", font: { size: 10 } }, range: [0, 1] }}
        />
        <Hist
          data={datos.score_llm}
          label="Fig. 15 — Score LLM"
          color={C.b}
          xbins={{ size: 0.05 }}
          xaxis={{ title: { text: "score", font: { size: 10 } }, range: [0, 1] }}
        />
        <Hist
          data={datos.score_total}
          label={`Fig. 16 — Score total (umbrales: reprocesar=${umb6.reprocesar} · correcto=${umb6.correcto})`}
          color={C.a}
          xbins={{ size: 0.05 }}
          xaxis={{ title: { text: "score", font: { size: 10 } }, range: [0, 1] }}
          shapes={[shapeRep, shapeCor]}
        />
      </div>

      <div className="grid grid-cols-2 gap-x-8">
        <Scatter
          puntos={datos.scatter_det_llm}
          label="Fig. 17 — Score determinista vs Score LLM"
          xLabel="score determinista"
          yLabel="score LLM"
          color={C.b}
        />
      </div>
    </div>
  )
}

// ── Filtro ────────────────────────────────────────────────────────────────────

const inputCls = "h-7 text-sm border border-input rounded px-2 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring"

function Filtro({
  fechaDesde, fechaHasta, onDesde, onHasta, onAplicar, loading,
}: {
  fechaDesde: string; fechaHasta: string
  onDesde: (v: string) => void; onHasta: (v: string) => void
  onAplicar: () => void; loading: boolean
}) {
  const set = (d: string, h: string) => { onDesde(d); onHasta(h) }
  return (
    <div className="flex flex-wrap items-center gap-3 pb-5 border-b border-border">
      <span className="text-xs text-muted-foreground">Rango de fechas</span>
      <div className="flex items-center gap-1.5">
        <input type="date" className={inputCls} value={fechaDesde} onChange={e => onDesde(e.target.value)} />
        <span className="text-muted-foreground text-xs">—</span>
        <input type="date" className={inputCls} value={fechaHasta} onChange={e => onHasta(e.target.value)} />
      </div>
      <div className="flex items-center gap-1">
        {[
          { label: "Hoy",    fn: () => set(hoy(), hoy()) },
          { label: "7 días", fn: () => set(restarDias(7), hoy()) },
          { label: "30 días",fn: () => set(restarDias(30), hoy()) },
          { label: "Todo",   fn: () => set("", "") },
        ].map(({ label, fn }) => (
          <button
            key={label}
            onClick={fn}
            className="text-xs px-2 py-0.5 rounded border border-border/50 text-muted-foreground hover:text-foreground hover:border-border transition-colors"
          >
            {label}
          </button>
        ))}
      </div>
      <Button size="sm" className="h-7 text-xs ml-auto" onClick={onAplicar} disabled={loading}>
        {loading ? "Cargando..." : "Aplicar"}
      </Button>
    </div>
  )
}

// ── Página ────────────────────────────────────────────────────────────────────

export default function PipelineEstadisticas() {
  const [fechaDesde, setFechaDesde] = useState("")
  const [fechaHasta, setFechaHasta] = useState("")
  const [loading,    setLoading]    = useState(false)
  const [error,      setError]      = useState<string | null>(null)

  const [global, setGlobal] = useState<DatosGlobal | null>(null)
  const [etapa1, setEtapa1] = useState<DatosEtapa1 | null>(null)
  const [etapa3, setEtapa3] = useState<DatosEtapa3 | null>(null)
  const [etapa4, setEtapa4] = useState<DatosEtapa4 | null>(null)
  const [etapa5, setEtapa5] = useState<DatosEtapa5 | null>(null)
  const [etapa6, setEtapa6] = useState<DatosEtapa6 | null>(null)

  const fetchTodo = useCallback(async (d: string, h: string) => {
    setLoading(true); setError(null)
    try {
      const [g, e1, e3, e4, e5, e6] = await Promise.all([
        getEstadisticasGlobal(d, h),
        getEstadisticasEtapa1(d, h),
        getEstadisticasEtapa3(d, h),
        getEstadisticasEtapa4(d, h),
        getEstadisticasEtapa5(d, h),
        getEstadisticasEtapa6(d, h),
      ])
      setGlobal(g); setEtapa1(e1); setEtapa3(e3); setEtapa4(e4); setEtapa5(e5); setEtapa6(e6)
    } catch (e) {
      setError(e instanceof Error ? e.message : "error")
    } finally {
      setLoading(false)
    }
  }, [])

  return (
    <div className="p-8 flex flex-col gap-10 max-w-5xl">

      <div className="flex flex-col gap-1">
        <h1 className="text-base font-medium text-foreground">
          Pipeline — Análisis de procesamiento de audios
        </h1>
        <p className="text-sm text-muted-foreground">
          Estadísticas de calidad por etapa. El filtro de fecha corresponde a la fecha de la llamada.
        </p>
      </div>

      <Filtro
        fechaDesde={fechaDesde} fechaHasta={fechaHasta}
        onDesde={setFechaDesde} onHasta={setFechaHasta}
        onAplicar={() => fetchTodo(fechaDesde, fechaHasta)}
        loading={loading}
      />

      {error && <p className="text-xs text-muted-foreground font-mono">Error: {error}</p>}

      {!global && !loading && (
        <p className="text-sm text-muted-foreground">
          Seleccioná un rango de fechas y presioná <em>Aplicar</em>.
        </p>
      )}

      {global && (
        <>
          <section className="flex flex-col gap-4">
            <SeccionHeader
              n="§ 0"
              titulo="Resumen global por etapa"
              desc="Distribución de audios según etapa actual y estado en el pipeline."
            />
            <SeccionGlobal datos={global} />
          </section>

          <section className="flex flex-col gap-4">
            <SeccionHeader n="§ 1" titulo="Etapa 1 — Descarga" desc="Audios descargados de Mitrol." />
            <SeccionEtapa1 datos={etapa1} />
          </section>

          <section className="flex flex-col gap-4">
            <SeccionHeader n="§ 3" titulo="Etapa 3 — Normalización de audio" desc="Procesamiento ffmpeg: silence removal, loudnorm, filtros opcionales." />
            <SeccionEtapa3 datos={etapa3} />
          </section>

          <section className="flex flex-col gap-4">
            <SeccionHeader
              n="§ 4"
              titulo="Etapa 4 — Control de calidad de normalización"
              desc="Score compuesto: SNR (40%) + RMS (30%) + duration ratio (30%)."
            />
            <SeccionEtapa4 datos={etapa4} />
          </section>

          <section className="flex flex-col gap-4">
            <SeccionHeader n="§ 5" titulo="Etapa 5 — Transcripción WhisperX" desc="Transcripción + alineación + diarización." />
            <SeccionEtapa5 datos={etapa5} />
          </section>

          <section className="flex flex-col gap-4">
            <SeccionHeader
              n="§ 6"
              titulo="Etapa 6 — Control de calidad de transcripción"
              desc="Score combinado: determinista (avg_logprob, words, speaker balance) + LLM (coherencia, roles)."
            />
            <SeccionEtapa6 datos={etapa6} />
          </section>
        </>
      )}

    </div>
  )
}
