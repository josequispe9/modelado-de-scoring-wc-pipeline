import { useState } from "react"
import { ChevronDown, ChevronRight, Search, Download, Play, X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { getAudio, getUrlDescargaAudio, getUrlStreamAudio, getAudiosAleatorios } from "@/api/pipeline"

// ── Tipos ──────────────────────────────────────────────────────────────────────

type AudioDetalle = {
  id: string
  nombre_archivo: string | null
  etapa_actual: string
  estado_global: string
  numero_telefono: string | null
  url_fuente: string | null
  duracion_audio_seg: number | null
  duracion_conversacion_seg: number | null
  fecha_llamada: string | null
  created_at: string
  fecha_ultima_actualizacion: string
  id_interaccion: string | null
  cuenta: string | null
  inicio: string | null
  agente: string | null
  extension: string | null
  empresa: string | null
  campania: string | null
  tipificacion: string | null
  clase_tipificacion: string | null
  etapas: Record<string, unknown>
  ubicaciones_minio: Record<string, string>
}

// ── Helpers ────────────────────────────────────────────────────────────────────

const inputClass =
  "h-7 text-sm border border-input rounded px-2 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring w-full"

const selectClass =
  "h-7 text-sm border border-input rounded px-2 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring w-full"

function colorEstado(estado: string) {
  if (estado === "correcto")                               return "text-green-600"
  if (estado === "invalido" || estado === "error")        return "text-red-500"
  if (estado === "reprocesar" || estado === "en_proceso") return "text-yellow-600"
  return "text-muted-foreground"
}

function fmtValor(val: unknown): string {
  if (val === null || val === undefined) return "—"
  return String(val)
}

function isoToDdmmyyyy(val: string): string {
  if (!val) return ""
  const [yyyy, mm, dd] = val.split("-")
  if (!dd || !mm || !yyyy) return ""
  return `${dd}/${mm}/${yyyy}`
}

// ── Fila de info general ───────────────────────────────────────────────────────

function InfoFila({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-muted-foreground">{label}</span>
      <span className="text-sm text-foreground">{children}</span>
    </div>
  )
}

// ── Sección de etapa colapsable ────────────────────────────────────────────────

function EtapaDetalle({ nombre, datos }: { nombre: string; datos: unknown }) {
  const [open, setOpen] = useState(false)

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="border border-border rounded">
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="w-full flex items-center justify-between px-4 py-2 text-sm font-medium text-foreground hover:bg-muted/50 transition-colors rounded"
          >
            <span>{nombre}</span>
            {open
              ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
              : <ChevronRight className="h-4 w-4 text-muted-foreground" />
            }
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="px-4 pb-4">
            <pre className="text-xs bg-muted rounded p-3 overflow-auto whitespace-pre-wrap break-all">
              {JSON.stringify(datos, null, 2)}
            </pre>
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}

// ── Transcripción diarizada ────────────────────────────────────────────────────

const BUCKET = "modelado-de-scoring-wc"

// Formato del JSON en transcripciones-formateadas/
// conversacion: [{ rol: "VENDEDOR" | "CLIENTE" | "DESCONOCIDO", texto: string }]
type LineaConversacion = { rol: string; texto: string }

type BloqueConversacion = { rol: string; texto: string }

function agruparConversacion(lineas: LineaConversacion[]): BloqueConversacion[] {
  const bloques: BloqueConversacion[] = []
  for (const linea of lineas) {
    const ultimo = bloques[bloques.length - 1]
    if (ultimo && ultimo.rol === linea.rol) {
      ultimo.texto += " " + linea.texto
    } else {
      bloques.push({ rol: linea.rol, texto: linea.texto })
    }
  }
  return bloques
}

function colorRol(rol: string): string {
  if (rol === "VENDEDOR")    return "text-blue-600"
  if (rol === "CLIENTE")     return "text-green-600"
  return "text-muted-foreground"
}

function labelRol(rol: string): string {
  if (rol === "VENDEDOR")    return "Vendedor"
  if (rol === "CLIENTE")     return "Cliente"
  if (rol === "DESCONOCIDO") return "Desconocido"
  return rol
}

function TranscripcionDiarizada({ audio }: { audio: AudioDetalle }) {
  const [open,     setOpen]     = useState(false)
  const [cargando, setCargando] = useState(false)
  const [error,    setError]    = useState<string | null>(null)
  const [bloques,  setBloques]  = useState<BloqueConversacion[] | null>(null)
  const [totalPalabras, setTotalPalabras] = useState<number | null>(null)

  // ganador es un objeto { grupo, ubicacion: { bucket, key }, fecha }
  const resolverKey = (): string | null => {
    const etapas = audio.etapas as Record<string, unknown>
    const corrTx = etapas?.correccion_transcripciones as Record<string, unknown> | undefined
    if (corrTx) {
      const ganador = corrTx.ganador as Record<string, unknown> | undefined
      const key = (ganador?.ubicacion as Record<string, unknown> | undefined)?.key as string | undefined
      if (key) return key
    }
    return null
  }

  const handleCargar = async () => {
    const key = resolverKey()
    if (!key) {
      setError("Este audio aún no tiene transcripción formateada (falta correr seleccionar_ganador).")
      return
    }
    setCargando(true)
    setError(null)
    try {
      const res = await fetch(getUrlDescargaAudio(BUCKET, key))
      if (!res.ok) throw new Error(`Archivo no encontrado en MinIO (${res.status})`)
      const json = await res.json()
      const lineas: LineaConversacion[] = json.conversacion ?? []
      const agrupados = agruparConversacion(lineas)
      setBloques(agrupados)
      setTotalPalabras(
        lineas.reduce((acc, l) => acc + l.texto.split(/\s+/).filter(Boolean).length, 0)
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar transcripción")
    } finally {
      setCargando(false)
    }
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="border border-border rounded">
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-foreground hover:bg-muted/50 transition-colors rounded"
          >
            <span>Transcripción diarizada</span>
            {open
              ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
              : <ChevronRight className="h-4 w-4 text-muted-foreground" />
            }
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="px-4 pb-4 pt-2 flex flex-col gap-3">
            {!bloques && !cargando && (
              <Button size="sm" variant="outline" onClick={handleCargar}>
                Cargar transcripción
              </Button>
            )}
            {cargando && <p className="text-xs text-muted-foreground">Cargando...</p>}
            {error    && <p className="text-xs text-red-500">{error}</p>}
            {bloques  && (
              <>
                {totalPalabras !== null && (
                  <p className="text-xs text-muted-foreground">{totalPalabras} palabras</p>
                )}
                <div className="flex flex-col gap-3">
                  {bloques.map((b, i) => (
                    <div key={i} className="flex flex-col gap-0.5">
                      <span className={`text-xs font-medium ${colorRol(b.rol)}`}>
                        {labelRol(b.rol)}
                      </span>
                      <p className="text-sm text-foreground leading-snug">{b.texto}</p>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}

// ── Resultado del audio ────────────────────────────────────────────────────────

function ResultadoAudio({ audio }: { audio: AudioDetalle }) {
  const ubicaciones = Object.entries(audio.ubicaciones_minio ?? {})
  const etapas = Object.entries(audio.etapas ?? {})
  const [playerKey,   setPlayerKey]   = useState<string | null>(null)
  const [audioError,  setAudioError]  = useState<string | null>(null)
  const [descargando, setDescargando] = useState<string | null>(null)

  const handleDescargar = async (key: string) => {
    setDescargando(key)
    try {
      const res = await fetch(getUrlDescargaAudio(BUCKET, key))
      if (!res.ok) throw new Error("Archivo no encontrado en MinIO")
      const blob = await res.blob()
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement("a")
      a.href     = url
      a.download = key.split("/").pop() ?? "audio.wav"
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      alert(e instanceof Error ? e.message : "Error al descargar")
    } finally {
      setDescargando(null)
    }
  }

  const handlePlay = (key: string) => {
    setAudioError(null)
    setPlayerKey(playerKey === key ? null : key)
  }

  return (
    <div className="flex flex-col gap-4">

      {/* Sección 1 — Info general */}
      <div className="border border-border rounded p-4 flex flex-col gap-3">
        <p className="text-sm font-medium text-foreground mb-2">Info general</p>
        <div className="grid grid-cols-2 gap-x-6 gap-y-3">
          <InfoFila label="Estado global">
            <span className={colorEstado(audio.estado_global)}>
              {fmtValor(audio.estado_global)}
            </span>
          </InfoFila>
          <InfoFila label="Etapa actual">{fmtValor(audio.etapa_actual)}</InfoFila>
          <InfoFila label="Nombre archivo">{fmtValor(audio.nombre_archivo)}</InfoFila>
          <InfoFila label="ID">{fmtValor(audio.id)}</InfoFila>
          <InfoFila label="Agente">{fmtValor(audio.agente)}</InfoFila>
          <InfoFila label="Empresa">{fmtValor(audio.empresa)}</InfoFila>
          <InfoFila label="Campana">{fmtValor(audio.campania)}</InfoFila>
          <InfoFila label="Telefono">{fmtValor(audio.numero_telefono)}</InfoFila>
          <InfoFila label="Cuenta">{fmtValor(audio.cuenta)}</InfoFila>
          <InfoFila label="Duracion audio (seg)">{fmtValor(audio.duracion_audio_seg)}</InfoFila>
          <InfoFila label="Grabacion">{fmtValor(audio.inicio)}</InfoFila>
          <InfoFila label="Ultima actualizacion">{fmtValor(audio.fecha_ultima_actualizacion)}</InfoFila>
        </div>
      </div>

      {/* Sección 2 — Ubicaciones en MinIO */}
      {ubicaciones.length > 0 && (
        <div className="border border-border rounded p-4 flex flex-col gap-2">
          <p className="text-sm font-medium text-foreground mb-2">Ubicaciones en MinIO</p>
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="text-xs text-muted-foreground font-normal text-left pb-1 pr-4 w-32">Etapa / grupo</th>
                <th className="text-xs text-muted-foreground font-normal text-left pb-1">Key</th>
                <th className="pb-1 w-6"></th>
              </tr>
            </thead>
            <tbody>
              {ubicaciones.map(([etapa, key]) => (
                <>
                  <tr key={etapa} className="border-t border-border">
                    <td className="py-1 pr-4 text-foreground align-top">{etapa}</td>
                    <td className="py-1">
                      <code className="text-xs text-muted-foreground break-all">{key}</code>
                    </td>
                    <td className="py-1 pl-3 align-top">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => handlePlay(key)}
                          className="text-muted-foreground hover:text-foreground transition-colors"
                          title={playerKey === key ? "Cerrar player" : "Escuchar"}
                        >
                          {playerKey === key
                            ? <X className="h-3.5 w-3.5" />
                            : <Play className="h-3.5 w-3.5" />
                          }
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDescargar(key)}
                          disabled={descargando === key}
                          className="text-muted-foreground hover:text-foreground transition-colors disabled:opacity-40"
                          title="Descargar"
                        >
                          <Download className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                  {playerKey === key && (
                    <tr key={`${etapa}-player`}>
                      <td colSpan={3} className="pb-2 pt-1">
                        {audioError ? (
                          <p className="text-xs text-red-500">{audioError}</p>
                        ) : (
                          <audio
                            controls
                            autoPlay
                            src={getUrlStreamAudio(BUCKET, key)}
                            className="w-full h-8"
                            onError={() => setAudioError("Archivo no encontrado en MinIO")}
                          />
                        )}
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Sección 3 — Detalle de etapas colapsable */}
      {etapas.length > 0 && (
        <div className="border border-border rounded p-4 flex flex-col gap-2">
          <p className="text-sm font-medium text-foreground mb-2">Detalle de etapas</p>
          <div className="flex flex-col gap-2">
            {etapas.map(([nombre, datos]) => (
              <EtapaDetalle key={nombre} nombre={nombre} datos={datos} />
            ))}
          </div>
        </div>
      )}

      {/* Sección 4 — Transcripción diarizada */}
      <TranscripcionDiarizada audio={audio} />

    </div>
  )
}

// ── Control de calidad ─────────────────────────────────────────────────────────

const ESTADOS_OPCIONES = [
  "pendiente", "en_proceso", "correcto",
  "reprocesar", "invalido", "error",
]

type FiltrosCalidad = {
  cantidad:       string
  duracion_desde: string
  duracion_hasta: string
  fecha_desde:    string
  fecha_hasta:    string
  hora_desde:     string
  hora_hasta:     string
  agente:         string
  telefono:       string
  etapa:          string
  estado:         string
}

const FILTROS_DEFAULTS: FiltrosCalidad = {
  cantidad:       "10",
  duracion_desde: "",
  duracion_hasta: "",
  fecha_desde:    "",
  fecha_hasta:    "",
  hora_desde:     "",
  hora_hasta:     "",
  agente:         "",
  telefono:       "",
  etapa:          "",
  estado:         "",
}

// ── Lista de resultados reutilizable ──────────────────────────────────────────

function ListaAudios({ audios }: { audios: AudioDetalle[] }) {
  const [abiertos, setAbiertos] = useState<Set<string>>(new Set())

  const toggle = (id: string) =>
    setAbiertos(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  return (
    <div className="flex flex-col gap-2">
      {audios.map(audio => (
        <Collapsible
          key={audio.id}
          open={abiertos.has(audio.id)}
          onOpenChange={() => toggle(audio.id)}
        >
          <div className="border border-border rounded">
            <CollapsibleTrigger asChild>
              <button
                type="button"
                className="w-full flex items-center justify-between px-4 py-2.5 text-sm hover:bg-muted/50 transition-colors rounded"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-foreground truncate font-mono text-xs">
                    {audio.nombre_archivo ?? audio.id}
                  </span>
                  <span className={`text-xs shrink-0 ${colorEstado(audio.estado_global)}`}>
                    {audio.estado_global}
                  </span>
                  <span className="text-xs text-muted-foreground shrink-0">
                    {audio.etapa_actual}
                  </span>
                  {audio.duracion_audio_seg != null && (
                    <span className="text-xs text-muted-foreground shrink-0">
                      {audio.duracion_audio_seg}s
                    </span>
                  )}
                </div>
                {abiertos.has(audio.id)
                  ? <ChevronDown className="h-4 w-4 text-muted-foreground shrink-0 ml-2" />
                  : <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0 ml-2" />
                }
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="px-4 pb-4 pt-1">
                <ResultadoAudio audio={audio} />
              </div>
            </CollapsibleContent>
          </div>
        </Collapsible>
      ))}
    </div>
  )
}

// ── Muestra aleatoria genérica ─────────────────────────────────────────────────

function MuestraAleatoria({
  filtrosIniciales,
}: {
  filtrosIniciales?: Partial<FiltrosCalidad>
}) {
  const [filtros,  setFiltros]  = useState<FiltrosCalidad>({ ...FILTROS_DEFAULTS, ...filtrosIniciales })
  const [cargando, setCargando] = useState(false)
  const [error,    setError]    = useState<string | null>(null)
  const [audios,   setAudios]   = useState<AudioDetalle[]>([])

  const set = (key: keyof FiltrosCalidad, val: string) =>
    setFiltros(prev => ({ ...prev, [key]: val }))

  const handleBuscar = async () => {
    setCargando(true)
    setError(null)
    setAudios([])
    try {
      const params: Record<string, string> = { cantidad: filtros.cantidad }
      if (filtros.duracion_desde) params.duracion_desde = filtros.duracion_desde
      if (filtros.duracion_hasta) params.duracion_hasta = filtros.duracion_hasta
      if (filtros.fecha_desde)    params.fecha_desde    = isoToDdmmyyyy(filtros.fecha_desde)
      if (filtros.fecha_hasta)    params.fecha_hasta    = isoToDdmmyyyy(filtros.fecha_hasta)
      if (filtros.hora_desde)     params.hora_desde     = filtros.hora_desde
      if (filtros.hora_hasta)     params.hora_hasta     = filtros.hora_hasta
      if (filtros.agente)         params.agente         = filtros.agente
      if (filtros.telefono)       params.telefono       = filtros.telefono
      if (filtros.etapa)          params.etapa          = filtros.etapa
      if (filtros.estado)         params.estado         = filtros.estado

      const data = await getAudiosAleatorios(params)
      setAudios(data.audios ?? [])
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al buscar")
    } finally {
      setCargando(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Filtros */}
      <div className="grid grid-cols-3 gap-3">
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Cantidad</Label>
          <input type="number" min={1} max={100} className={inputClass}
            value={filtros.cantidad} onChange={e => set("cantidad", e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Duración desde (seg)</Label>
          <input type="number" min={0} className={inputClass} placeholder="—"
            value={filtros.duracion_desde} onChange={e => set("duracion_desde", e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Duración hasta (seg)</Label>
          <input type="number" min={0} className={inputClass} placeholder="—"
            value={filtros.duracion_hasta} onChange={e => set("duracion_hasta", e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Fecha grabación desde</Label>
          <input type="date" className={inputClass}
            value={filtros.fecha_desde} onChange={e => set("fecha_desde", e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Fecha grabación hasta</Label>
          <input type="date" className={inputClass}
            value={filtros.fecha_hasta} onChange={e => set("fecha_hasta", e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Agente</Label>
          <input type="text" className={inputClass} placeholder="—"
            value={filtros.agente} onChange={e => set("agente", e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Hora grabación desde</Label>
          <input type="time" className={inputClass}
            value={filtros.hora_desde} onChange={e => set("hora_desde", e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Hora grabación hasta</Label>
          <input type="time" className={inputClass}
            value={filtros.hora_hasta} onChange={e => set("hora_hasta", e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Teléfono</Label>
          <input type="text" className={inputClass} placeholder="—"
            value={filtros.telefono} onChange={e => set("telefono", e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Estado</Label>
          <select className={selectClass} value={filtros.estado} onChange={e => set("estado", e.target.value)}>
            <option value="">Todos</option>
            {ESTADOS_OPCIONES.map(e => <option key={e} value={e}>{e}</option>)}
          </select>
        </div>
      </div>

      <div className="flex items-center gap-3 pt-1 border-t border-border">
        <Button size="sm" onClick={handleBuscar} disabled={cargando}>
          <Search className="h-4 w-4 mr-1" />
          {cargando ? "Buscando..." : "Buscar muestra"}
        </Button>
        {error && <span className="text-xs text-red-500">{error}</span>}
        {!cargando && audios.length > 0 && (
          <span className="text-xs text-muted-foreground">{audios.length} audios encontrados</span>
        )}
      </div>

      {audios.length > 0 && <ListaAudios audios={audios} />}
    </div>
  )
}

// ── Sección colapsable de control de calidad ──────────────────────────────────

function SeccionCalidad({
  label,
  children,
  defaultOpen = false,
}: {
  label: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="border border-border rounded">
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-foreground hover:bg-muted/50 transition-colors rounded"
          >
            <span>{label}</span>
            {open
              ? <ChevronDown className="h-4 w-4 text-muted-foreground" />
              : <ChevronRight className="h-4 w-4 text-muted-foreground" />
            }
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="px-4 pb-4 pt-2">{children}</div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}

// ── Secciones por etapa ───────────────────────────────────────────────────────

function ControlCalidadNormalizacion() {
  return (
    <MuestraAleatoria
      filtrosIniciales={{ etapa: "correccion_normalizacion" }}
    />
  )
}

function ControlCalidadTranscripcion() {
  return (
    <MuestraAleatoria
      filtrosIniciales={{ etapa: "correccion_transcripciones" }}
    />
  )
}

function ControlCalidadAnalisis() {
  return (
    <p className="text-sm text-muted-foreground">Próximamente</p>
  )
}

// ── Página principal ───────────────────────────────────────────────────────────

const SESSION_KEY_QUERY     = "monitoreo_query"
const SESSION_KEY_RESULTADO = "monitoreo_resultado"

function leerSession(): { query: string; resultado: AudioDetalle | null } {
  try {
    return {
      query:     sessionStorage.getItem(SESSION_KEY_QUERY) ?? "",
      resultado: JSON.parse(sessionStorage.getItem(SESSION_KEY_RESULTADO) ?? "null"),
    }
  } catch {
    return { query: "", resultado: null }
  }
}

export default function PipelineMonitoreo() {
  const session = leerSession()
  const [query,     setQuery]     = useState(session.query)
  const [cargando,  setCargando]  = useState(false)
  const [error,     setError]     = useState<string | null>(null)
  const [resultado, setResultado] = useState<AudioDetalle | null>(session.resultado)

  const handleBuscar = async () => {
    const q = query.trim()
    if (!q) return
    setCargando(true)
    setError(null)
    setResultado(null)
    try {
      const data = await getAudio(q)
      setResultado(data)
      sessionStorage.setItem(SESSION_KEY_QUERY,     q)
      sessionStorage.setItem(SESSION_KEY_RESULTADO, JSON.stringify(data))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Error al buscar")
      sessionStorage.removeItem(SESSION_KEY_RESULTADO)
    } finally {
      setCargando(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") handleBuscar()
  }

  return (
    <div className="p-6 flex flex-col gap-6 max-w-4xl">
      <h1 className="text-lg font-semibold text-foreground mb-1">
        Monitoreo de audio
      </h1>

      {/* Buscador individual */}
      <div className="border border-border rounded p-4 flex flex-col gap-3">
        <Label className="text-xs text-muted-foreground">
          Buscar por UUID o nombre de archivo
        </Label>
        <div className="flex gap-2">
          <input
            type="text"
            className={inputClass}
            placeholder="UUID o nombre_archivo..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
          />
          <Button size="sm" onClick={handleBuscar} disabled={cargando}>
            <Search className="h-4 w-4 mr-1" />
            {cargando ? "Buscando..." : "Buscar"}
          </Button>
        </div>
      </div>

      {cargando && <p className="text-sm text-muted-foreground">Buscando...</p>}
      {error    && <p className="text-sm text-red-500">{error}</p>}
      {resultado && <ResultadoAudio audio={resultado} />}

      {/* Control de calidad por etapa */}
      <div className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-foreground">Control de calidad</h2>
        <SeccionCalidad label="Normalización / Corrección de normalización" defaultOpen>
          <ControlCalidadNormalizacion />
        </SeccionCalidad>
        <SeccionCalidad label="Transcripción / Corrección de transcripciones">
          <ControlCalidadTranscripcion />
        </SeccionCalidad>
        <SeccionCalidad label="Análisis / Corrección de análisis">
          <ControlCalidadAnalisis />
        </SeccionCalidad>
      </div>
    </div>
  )
}
