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
  getCalendarioAudios,
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
  conteos:               { correcto: number; reprocesar: number; invalido: number }
  scores:                number[]
  snr:                   number[]
  rms_dbfs:              number[]
  duracion_ratio:        number[]
  causas_invalido:       Record<string, number>
  scatter_snr_score:     { x: number; y: number }[]
  scatter_dur_score:     { x: number; y: number }[]
  distribucion_duracion: Record<string, number>
  umbrales:              { correcto: number; reprocesar: number }
}
type DatosEtapa5 = { correcto: number; error: number }
type DatosEtapa6 = {
  conteos:           { correcto: number; reprocesar: number; invalido: number; pendiente: number; sin_datos: number }
  causas_invalido:   Record<string, number>
  avg_logprob:       { correcto: number; reprocesar: number; invalido: number }
  total_words:       { correcto: number; reprocesar: number; invalido: number }
  low_score_ratio:   { correcto: number; reprocesar: number; invalido: number }
  speaker_dominance: { correcto: number; reprocesar: number; invalido: number }
  score_determinista: { bins: number[]; counts: number[] }
  umbrales:          { umbral_score_correcto: number; umbral_score_reprocesar: number }
}

type DiaCal = { fecha: string; cantidad: number }
type DatosCalendario = {
  dias: DiaCal[]
  total: number
  dias_con_datos: number
  fecha_min: string
  fecha_max: string
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
  return (
    <div className="flex flex-col gap-6">
      <div className="flex gap-0 flex-wrap">
        <Metrica label="Registrados en DB"      valor={datos.registrados} />
        <Metrica label="Descargados correctamente" valor={datos.descargados} />
        <Metrica label="Errores de descarga"    valor={datos.errores_descarga} />
      </div>
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
        <div className="flex flex-col gap-2">
          <span className="text-xs text-slate-500 font-medium">Fig. 9 — Distribución de duración del audio original</span>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-slate-200">
                <th className="text-left py-1 px-2 text-slate-500 font-medium">Rango</th>
                <th className="text-right py-1 px-2 text-slate-500 font-medium">Cantidad</th>
                <th className="text-right py-1 px-2 text-slate-500 font-medium">%</th>
              </tr>
            </thead>
            <tbody>
              {(() => {
                const totalDur = Object.values(datos.distribucion_duracion).reduce((a, b) => a + b, 0)
                return Object.entries(datos.distribucion_duracion).map(([rango, cant]) => (
                  <tr key={rango} className="border-b border-slate-100">
                    <td className="py-1 px-2 font-mono text-slate-700">{rango}</td>
                    <td className="py-1 px-2 text-right text-slate-700">{cant.toLocaleString()}</td>
                    <td className="py-1 px-2 text-right text-slate-500">
                      {totalDur ? ((cant / totalDur) * 100).toFixed(1) + "%" : "—"}
                    </td>
                  </tr>
                ))
              })()}
            </tbody>
          </table>
        </div>
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
  const umb   = datos.umbrales ?? { umbral_score_correcto: 0.75, umbral_score_reprocesar: 0.40 }
  const umbCor = umb.umbral_score_correcto
  const umbRep = umb.umbral_score_reprocesar

  const shapeRep: Partial<Plotly.Shape> = {
    type: "line", x0: umbRep, x1: umbRep, y0: 0, y1: 1,
    xref: "x", yref: "paper",
    line: { color: C.reprocesar, width: 1.5, dash: "dot" },
  }
  const shapeCor: Partial<Plotly.Shape> = {
    type: "line", x0: umbCor, x1: umbCor, y0: 0, y1: 1,
    xref: "x", yref: "paper",
    line: { color: C.correcto, width: 1.5, dash: "dot" },
  }

  const det = datos.score_determinista
  const hasDet = det?.bins?.length && det?.counts?.length

  // Tabla de métricas por estado
  const metricasFilas: { label: string; key: keyof Omit<DatosEtapa6, "conteos" | "causas_invalido" | "score_determinista" | "umbrales"> }[] = [
    { label: "avg_logprob",       key: "avg_logprob"       },
    { label: "total_words",       key: "total_words"       },
    { label: "low_score_ratio",   key: "low_score_ratio"   },
    { label: "speaker_dominance", key: "speaker_dominance" },
  ]

  return (
    <div className="flex flex-col gap-8">
      {/* Conteos */}
      <div className="flex gap-0 flex-wrap">
        <Metrica label="Correcto"   valor={datos.conteos.correcto}
          sub={total ? `${((datos.conteos.correcto / total) * 100).toFixed(1)}%` : undefined} />
        <Metrica label="Reprocesar" valor={datos.conteos.reprocesar}
          sub={total ? `${((datos.conteos.reprocesar / total) * 100).toFixed(1)}%` : undefined} />
        <Metrica label="Inválido"   valor={datos.conteos.invalido}
          sub={total ? `${((datos.conteos.invalido / total) * 100).toFixed(1)}%` : undefined} />
        <Metrica label="Pendiente"  valor={datos.conteos.pendiente} />
        <Metrica label="Umbral correcto"   valor={umbCor} sub={`score ≥ ${umbCor} → correcto`} />
        <Metrica label="Umbral reprocesar" valor={umbRep} sub={`score ≥ ${umbRep} → reprocesar`} />
      </div>

      <div className="grid grid-cols-2 gap-x-8 gap-y-8">

        {/* Histograma score determinista — bins pre-calculados */}
        <Figure label={`Fig. 9 — Score determinista (umbrales: reprocesar=${umbRep} · correcto=${umbCor})`} height={220}>
          {!hasDet ? <SinDatos /> : (
            <Plot
              data={[{
                type:    "bar",
                x:       det.bins,
                y:       det.counts,
                marker:  { color: C.a },
                width:   det.bins.length > 1 ? (det.bins[1] - det.bins[0]) * 0.9 : 0.09,
              }]}
              layout={{
                ...BASE_LAYOUT,
                xaxis:   { ...AXIS_STYLE, title: { text: "score", font: { size: 10 } }, range: [0, 1] },
                yaxis:   { ...AXIS_STYLE, title: { text: "n", font: { size: 10 } } },
                shapes:  [shapeRep, shapeCor],
                bargap:  0.05,
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
      </div>

      {/* Tabla de métricas promedio por estado */}
      <div>
        <FigureLabel>Fig. 11 — Métricas promedio por estado (Whisper)</FigureLabel>
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-1 px-2 text-muted-foreground font-medium">Métrica</th>
              <th className="text-right py-1 px-2 text-muted-foreground font-medium">Correcto</th>
              <th className="text-right py-1 px-2 text-muted-foreground font-medium">Reprocesar</th>
              <th className="text-right py-1 px-2 text-muted-foreground font-medium">Inválido</th>
            </tr>
          </thead>
          <tbody>
            {metricasFilas.map(({ label, key }) => {
              const obj = datos[key] as { correcto: number; reprocesar: number; invalido: number }
              return (
                <tr key={key} className="border-b border-border/40">
                  <td className="py-1 px-2 font-mono text-foreground">{label}</td>
                  <td className="py-1 px-2 text-right tabular-nums text-foreground">{obj?.correcto?.toFixed(3) ?? "—"}</td>
                  <td className="py-1 px-2 text-right tabular-nums text-foreground">{obj?.reprocesar?.toFixed(3) ?? "—"}</td>
                  <td className="py-1 px-2 text-right tabular-nums text-foreground">{obj?.invalido?.toFixed(3) ?? "—"}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Calendario tipo GitHub ────────────────────────────────────────────────────

function colorCelda(cantidad: number): string {
  if (cantidad === 0) return "#f1f5f9"        // slate-100
  if (cantidad <= 10)  return "#b8d0e8"       // steel blue cuartil 1
  if (cantidad <= 50)  return "#7aafd4"       // cuartil 2
  if (cantidad <= 150) return "#4a7fa5"       // cuartil 3 — color base del proyecto
  return "#2d5a7a"                            // cuartil 4
}

const DIAS_SEMANA = ["Lun", "", "Mié", "", "Vie", "", ""]
const NOMBRES_MES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

function CalendarioGitHub({ dias }: { dias: DiaCal[] }) {
  // Construir mapa fecha → cantidad
  const mapa = new Map<string, number>()
  for (const d of dias) mapa.set(d.fecha, d.cantidad)

  // Helper: fecha local como YYYY-MM-DD (evita el desfase UTC en zonas negativas como ART)
  const isoLocal = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`

  // Calcular 52 semanas hacia atrás desde hoy, arrancando en lunes (semana laboral AR)
  const hoyDate = new Date()
  const diasDesdeHoy = (hoyDate.getDay() + 6) % 7 // 0=lun … 6=dom
  const lunes = new Date(hoyDate)
  lunes.setDate(hoyDate.getDate() - diasDesdeHoy)

  // Inicio: 51 semanas hacia atrás desde el lunes actual
  const inicioSemana = new Date(lunes)
  inicioSemana.setDate(lunes.getDate() - 51 * 7)

  // Construir array de semanas. Cada semana: 7 días (lun a dom)
  const semanas: { fecha: string; cantidad: number }[][] = []
  for (let s = 0; s < 52; s++) {
    const semana: { fecha: string; cantidad: number }[] = []
    for (let d = 0; d < 7; d++) {
      const fecha = new Date(inicioSemana)
      fecha.setDate(inicioSemana.getDate() + s * 7 + d)
      const iso = isoLocal(fecha)
      semana.push({ fecha: iso, cantidad: mapa.get(iso) ?? 0 })
    }
    semanas.push(semana)
  }

  // Calcular labels de meses: dónde aparece cada mes nuevo
  const labelsMes: { col: number; mes: string }[] = []
  let mesActual = -1
  for (let s = 0; s < semanas.length; s++) {
    const mes = new Date(semanas[s][1].fecha).getMonth() // usar martes para evitar borde
    if (mes !== mesActual) {
      labelsMes.push({ col: s, mes: NOMBRES_MES[mes] })
      mesActual = mes
    }
  }

  // Tooltip state
  const [tooltip, setTooltip] = useState<{ x: number; y: number; texto: string } | null>(null)

  const CELL = 12
  const GAP  = 2
  const paso  = CELL + GAP

  return (
    <div className="flex flex-col gap-2">
      <div className="overflow-x-auto">
        <div style={{ display: "inline-block", position: "relative" }}>
          {/* Labels de meses */}
          <div style={{ display: "flex", paddingLeft: 28, marginBottom: 4, position: "relative", height: 14 }}>
            {labelsMes.map(({ col, mes }) => (
              <span
                key={`${col}-${mes}`}
                style={{
                  position: "absolute",
                  left: 28 + col * paso,
                  fontSize: 10,
                  color: "#64748b",
                  whiteSpace: "nowrap",
                  lineHeight: 1,
                }}
              >
                {mes}
              </span>
            ))}
          </div>

          {/* Grid principal */}
          <div style={{ display: "flex", gap: GAP, alignItems: "flex-start" }}>
            {/* Eje Y */}
            <div style={{ display: "flex", flexDirection: "column", gap: GAP, marginTop: 0 }}>
              {DIAS_SEMANA.map((lbl, i) => (
                <div
                  key={i}
                  style={{
                    height: CELL,
                    width: 24,
                    fontSize: 9,
                    color: "#94a3b8",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "flex-end",
                    paddingRight: 3,
                    userSelect: "none",
                  }}
                >
                  {lbl}
                </div>
              ))}
            </div>

            {/* Semanas */}
            {semanas.map((semana, si) => (
              <div key={si} style={{ display: "flex", flexDirection: "column", gap: GAP }}>
                {semana.map((dia, di) => (
                  <div
                    key={di}
                    style={{
                      width: CELL,
                      height: CELL,
                      borderRadius: 2,
                      backgroundColor: colorCelda(dia.cantidad),
                      cursor: dia.cantidad > 0 ? "default" : "default",
                      flexShrink: 0,
                    }}
                    onMouseEnter={e => {
                      const rect = (e.target as HTMLElement).getBoundingClientRect()
                      setTooltip({
                        x: rect.left + window.scrollX + CELL / 2,
                        y: rect.top  + window.scrollY - 6,
                        texto: `${dia.fecha} · ${dia.cantidad} audio${dia.cantidad !== 1 ? "s" : ""}`,
                      })
                    }}
                    onMouseLeave={() => setTooltip(null)}
                  />
                ))}
              </div>
            ))}
          </div>

          {/* Leyenda */}
          <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 8, paddingLeft: 28 }}>
            <span style={{ fontSize: 9, color: "#94a3b8" }}>Menos</span>
            {[0, 5, 30, 100, 200].map(v => (
              <div
                key={v}
                style={{
                  width: CELL,
                  height: CELL,
                  borderRadius: 2,
                  backgroundColor: colorCelda(v),
                  flexShrink: 0,
                }}
              />
            ))}
            <span style={{ fontSize: 9, color: "#94a3b8" }}>Más</span>
          </div>
        </div>
      </div>

      {/* Tooltip via fixed positioning */}
      {tooltip && (
        <div
          style={{
            position: "fixed",
            left: tooltip.x,
            top: tooltip.y,
            transform: "translate(-50%, -100%)",
            background: "#1e293b",
            color: "#f8fafc",
            fontSize: 11,
            padding: "3px 8px",
            borderRadius: 4,
            pointerEvents: "none",
            zIndex: 9999,
            whiteSpace: "nowrap",
          }}
        >
          {tooltip.texto}
        </div>
      )}
    </div>
  )
}

function SeccionCalendario({ datos }: { datos: DatosCalendario | null }) {
  if (!datos) return null

  const promedio = datos.dias_con_datos > 0
    ? (datos.total / datos.dias_con_datos).toFixed(1)
    : "—"

  // Día más activo
  const diaMasActivo = datos.dias.reduce<DiaCal | null>(
    (max, d) => (!max || d.cantidad > max.cantidad ? d : max),
    null
  )

  return (
    <div className="flex flex-col gap-6">
      <CalendarioGitHub dias={datos.dias} />
      <div className="flex gap-0 flex-wrap">
        <Metrica label="Total audios"       valor={datos.total.toLocaleString()} />
        <Metrica label="Días con datos"     valor={datos.dias_con_datos} />
        <Metrica label="Promedio / día activo" valor={promedio} sub="audios por día con al menos 1 llamada" />
        {diaMasActivo && (
          <Metrica
            label="Fecha más activa"
            valor={diaMasActivo.cantidad.toLocaleString()}
            sub={diaMasActivo.fecha}
          />
        )}
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

  const [global,     setGlobal]     = useState<DatosGlobal | null>(null)
  const [etapa1,     setEtapa1]     = useState<DatosEtapa1 | null>(null)
  const [etapa3,     setEtapa3]     = useState<DatosEtapa3 | null>(null)
  const [etapa4,     setEtapa4]     = useState<DatosEtapa4 | null>(null)
  const [etapa5,     setEtapa5]     = useState<DatosEtapa5 | null>(null)
  const [etapa6,     setEtapa6]     = useState<DatosEtapa6 | null>(null)
  const [calendario, setCalendario] = useState<DatosCalendario | null>(null)

  const fetchTodo = useCallback(async (d: string, h: string) => {
    setLoading(true); setError(null)
    try {
      const [g, e1, e3, e4, e5, e6, cal] = await Promise.all([
        getEstadisticasGlobal(d, h),
        getEstadisticasEtapa1(d, h),
        getEstadisticasEtapa3(d, h),
        getEstadisticasEtapa4(d, h),
        getEstadisticasEtapa5(d, h),
        getEstadisticasEtapa6(d, h),
        getCalendarioAudios(d, h),
      ])
      setGlobal(g); setEtapa1(e1); setEtapa3(e3); setEtapa4(e4); setEtapa5(e5); setEtapa6(e6)
      setCalendario(cal)
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

      {!global && !calendario && !loading && (
        <p className="text-sm text-muted-foreground">
          Seleccioná un rango de fechas y presioná <em>Aplicar</em>.
        </p>
      )}

      {(global || calendario) && (
        <>
          <section className="flex flex-col gap-4">
            <SeccionHeader
              n="§ —"
              titulo="Cobertura de audios"
              desc="Audios registrados en PostgreSQL por fecha de llamada."
            />
            <SeccionCalendario datos={calendario} />
          </section>

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
              desc="Score determinista: avg_logprob, total words, low score ratio, speaker dominance."
            />
            <SeccionEtapa6 datos={etapa6} />
          </section>
        </>
      )}

    </div>
  )
}
