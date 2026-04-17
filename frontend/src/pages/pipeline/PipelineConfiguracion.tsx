import { useState, useEffect, useCallback } from "react"
import { ChevronDown, ChevronRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { getParametros, actualizarParametros, ejecutarEtapa } from "@/api/pipeline"

// ── Tipos ──────────────────────────────────────────────────────────────────────

type NormalizacionParams = {
  carpeta:           string
  silence_threshold: string
  silence_duration:  string
  normalize:         boolean
  noise_reduction:   boolean
  highpass_filter:   boolean
}

type DescargaParams = {
  fecha_inicio: string
  fecha_fin: string
  hora_inicio: string
  hora_fin: string
  duracion_min: string
  duracion_max: string
  cant_registros_max: string
  cliente: string
}

// ── Constantes ─────────────────────────────────────────────────────────────────

const MAQUINAS: { label: string; clave: string }[] = [
  { label: "Gaspar",   clave: "descarga_G" },
  { label: "Melchor",  clave: "descarga_M" },
  { label: "Baltazar", clave: "descarga_B" },
]

const ETAPAS = [
  { id: "descarga",                   label: "1. Descarga" },
  { id: "creacion_registros",         label: "2. Creación de registros" },
  { id: "normalizacion",              label: "3. Normalización" },
  { id: "correccion_normalizacion",   label: "4. Corrección de normalización" },
  { id: "transcripcion",              label: "5. Transcripción" },
  { id: "correccion_transcripciones", label: "6. Corrección de transcripciones" },
  { id: "analisis",                   label: "7. Análisis" },
  { id: "correccion_analisis",        label: "8. Corrección de análisis" },
  { id: "carga_datos",                label: "9. Carga de datos" },
]

// ── Constantes de normalización ───────────────────────────────────────────────

const NORM_DEFAULTS: NormalizacionParams = {
  carpeta:           "audios",
  silence_threshold: "-40dB",
  silence_duration:  "1",
  normalize:         true,
  noise_reduction:   false,
  highpass_filter:   false,
}

const NORM_PRESETS: { label: string; grupos: Record<string, string> }[] = [
  { label: "GBM",       grupos: { G: "GBM", M: "GBM", B: "GBM" } },
  { label: "GM | B",    grupos: { G: "GM",  M: "GM",  B: "B"   } },
  { label: "GB | M",    grupos: { G: "GB",  M: "M",   B: "GB"  } },
  { label: "G | MB",    grupos: { G: "G",   M: "MB",  B: "MB"  } },
  { label: "G | M | B", grupos: { G: "G",   M: "M",   B: "B"   } },
]

const CANT_REGISTROS_OPCIONES = ["10", "100", "500", "1000", "5000", "15000", "30000", "60000", "100000"]

const HORAS_OPCIONES = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, "0"))

const MINUTOS_OPCIONES = Array.from({ length: 60 }, (_, i) => String(i).padStart(2, "0"))

// ── Helpers de fecha ───────────────────────────────────────────────────────────

/** Convierte "dd/mm/yyyy" → "yyyy-mm-dd" para usar en <input type="date"> */
function ddmmyyyyToISO(val: string): string {
  if (!val) return ""
  const [dd, mm, yyyy] = val.split("/")
  if (!dd || !mm || !yyyy) return ""
  return `${yyyy}-${mm}-${dd}`
}

/** Convierte "yyyy-mm-dd" → "dd/mm/yyyy" para enviar a la API */
function isoToDdmmyyyy(val: string): string {
  if (!val) return ""
  const [yyyy, mm, dd] = val.split("-")
  if (!dd || !mm || !yyyy) return ""
  return `${dd}/${mm}/${yyyy}`
}

/** Fecha de hoy en formato "dd/mm/yyyy" */
function hoyDdmmyyyy(): string {
  const hoy = new Date()
  const dd   = String(hoy.getDate()).padStart(2, "0")
  const mm   = String(hoy.getMonth() + 1).padStart(2, "0")
  const yyyy = String(hoy.getFullYear())
  return `${dd}/${mm}/${yyyy}`
}

// ── Componentes auxiliares ─────────────────────────────────────────────────────

const selectClass =
  "h-7 text-sm border border-input rounded px-2 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring w-full"

const inputClass =
  "h-7 text-sm border border-input rounded px-2 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-ring w-full"

// ── Sub-sección de una máquina ─────────────────────────────────────────────────

function MaquinaPanel({ label, clave }: { label: string; clave: string }) {
  // Los params internos para fechas se almacenan en formato dd/mm/yyyy (igual que la API)
  const [params, setParams] = useState<DescargaParams>({
    fecha_inicio:       hoyDdmmyyyy(),
    fecha_fin:          hoyDdmmyyyy(),
    hora_inicio:        "08",
    hora_fin:           "22",
    duracion_min:       "00",
    duracion_max:       "00",
    cant_registros_max: "100000",
    cliente:            "",
  })
  const [guardando, setGuardando] = useState(false)
  const [mensaje,   setMensaje]   = useState<string | null>(null)

  useEffect(() => {
    getParametros(clave)
      .then((res: { valor?: Partial<DescargaParams> }) => {
        const v = res?.valor ?? {}
        setParams({
          fecha_inicio:       String(v.fecha_inicio       || hoyDdmmyyyy()),
          fecha_fin:          String(v.fecha_fin          || hoyDdmmyyyy()),
          hora_inicio:        String(v.hora_inicio        || "08"),
          hora_fin:           String(v.hora_fin           || "22"),
          duracion_min:       String(v.duracion_min       || "00"),
          duracion_max:       String(v.duracion_max       || "00"),
          cant_registros_max: String(v.cant_registros_max || "100000"),
          cliente:            String(v.cliente            || ""),
        })
      })
      .catch(() => setMensaje("Error al cargar parámetros"))
  }, [clave])

  const handleChange = useCallback(
    (key: keyof DescargaParams, value: string) =>
      setParams((prev) => ({ ...prev, [key]: value })),
    []
  )

  /** Al guardar, las fechas ya están en dd/mm/yyyy — se envían tal cual */
  const handleGuardar = async () => {
    setGuardando(true)
    setMensaje(null)
    try {
      await actualizarParametros(clave, params)
      setMensaje("Guardado")
    } catch {
      setMensaje("Error al guardar")
    } finally {
      setGuardando(false)
    }
  }

  return (
    <div className="flex-1 min-w-0 border border-border rounded p-4 flex flex-col gap-3">
      <p className="text-sm font-medium text-foreground">{label}</p>

      <div className="grid grid-cols-1 gap-2">

        {/* fecha_inicio — date picker nativo, convierte dd/mm/yyyy <-> yyyy-mm-dd */}
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${clave}-fecha_inicio`} className="text-xs text-muted-foreground">
            Fecha inicio
          </Label>
          <input
            id={`${clave}-fecha_inicio`}
            type="date"
            className={inputClass}
            value={ddmmyyyyToISO(params.fecha_inicio)}
            onChange={(e) => handleChange("fecha_inicio", isoToDdmmyyyy(e.target.value))}
          />
        </div>

        {/* fecha_fin — date picker nativo */}
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${clave}-fecha_fin`} className="text-xs text-muted-foreground">
            Fecha fin
          </Label>
          <input
            id={`${clave}-fecha_fin`}
            type="date"
            className={inputClass}
            value={ddmmyyyyToISO(params.fecha_fin)}
            onChange={(e) => handleChange("fecha_fin", isoToDdmmyyyy(e.target.value))}
          />
        </div>

        {/* hora_inicio — select 00-23 */}
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${clave}-hora_inicio`} className="text-xs text-muted-foreground">
            Hora inicio
          </Label>
          <select
            id={`${clave}-hora_inicio`}
            className={selectClass}
            value={params.hora_inicio}
            onChange={(e) => handleChange("hora_inicio", e.target.value)}
          >
            {HORAS_OPCIONES.map((h) => (
              <option key={h} value={h}>{h}</option>
            ))}
          </select>
        </div>

        {/* hora_fin — select 00-23 */}
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${clave}-hora_fin`} className="text-xs text-muted-foreground">
            Hora fin
          </Label>
          <select
            id={`${clave}-hora_fin`}
            className={selectClass}
            value={params.hora_fin}
            onChange={(e) => handleChange("hora_fin", e.target.value)}
          >
            {HORAS_OPCIONES.map((h) => (
              <option key={h} value={h}>{h}</option>
            ))}
          </select>
        </div>

        {/* duracion_min — select 00-59 */}
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${clave}-duracion_min`} className="text-xs text-muted-foreground">
            Duración mín
          </Label>
          <select
            id={`${clave}-duracion_min`}
            className={selectClass}
            value={params.duracion_min}
            onChange={(e) => handleChange("duracion_min", e.target.value)}
          >
            {MINUTOS_OPCIONES.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        {/* duracion_max — select 00-59 */}
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${clave}-duracion_max`} className="text-xs text-muted-foreground">
            Duración máx
          </Label>
          <select
            id={`${clave}-duracion_max`}
            className={selectClass}
            value={params.duracion_max}
            onChange={(e) => handleChange("duracion_max", e.target.value)}
          >
            {MINUTOS_OPCIONES.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        {/* cant_registros_max — select con valores fijos */}
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${clave}-cant_registros_max`} className="text-xs text-muted-foreground">
            Cant. registros máx
          </Label>
          <select
            id={`${clave}-cant_registros_max`}
            className={selectClass}
            value={params.cant_registros_max}
            onChange={(e) => handleChange("cant_registros_max", e.target.value)}
          >
            {CANT_REGISTROS_OPCIONES.map((o) => (
              <option key={o} value={o}>{Number(o).toLocaleString("es-AR")}</option>
            ))}
          </select>
        </div>

        {/* cliente — input numérico */}
        <div className="flex flex-col gap-1">
          <Label htmlFor={`${clave}-cliente`} className="text-xs text-muted-foreground">
            Cliente
          </Label>
          <input
            id={`${clave}-cliente`}
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            className={inputClass}
            value={params.cliente}
            onChange={(e) => {
              const val = e.target.value.replace(/\D/g, "")
              handleChange("cliente", val)
            }}
          />
        </div>

      </div>

      <div className="flex items-center gap-3 pt-1">
        <Button size="sm" onClick={handleGuardar} disabled={guardando}>
          {guardando ? "Guardando..." : "Guardar"}
        </Button>
        {mensaje && (
          <span className="text-xs text-muted-foreground">{mensaje}</span>
        )}
      </div>
    </div>
  )
}

// ── Contenido de la etapa Descarga ─────────────────────────────────────────────

function EtapaDescarga() {
  const [ejecutando,        setEjecutando]        = useState(false)
  const [mensajeEjecucion,  setMensajeEjecucion]  = useState<string | null>(null)

  const handleEjecutar = async () => {
    setEjecutando(true)
    setMensajeEjecucion(null)
    try {
      await ejecutarEtapa("descarga", "pendientes")
      setMensajeEjecucion("Ejecución iniciada")
    } catch {
      setMensajeEjecucion("Error al ejecutar")
    } finally {
      setEjecutando(false)
    }
  }

  return (
    <div className="flex flex-col gap-4 pt-3">
      <div className="flex gap-4 flex-wrap">
        {MAQUINAS.map(({ label, clave }) => (
          <MaquinaPanel key={clave} label={label} clave={clave} />
        ))}
      </div>
      <div className="flex items-center gap-3 pt-1 border-t border-border">
        <Button onClick={handleEjecutar} disabled={ejecutando}>
          {ejecutando ? "Ejecutando..." : "Ejecutar descarga"}
        </Button>
        {mensajeEjecucion && (
          <span className="text-xs text-muted-foreground">{mensajeEjecucion}</span>
        )}
      </div>
    </div>
  )
}

// ── Etapa Normalización ────────────────────────────────────────────────────────

function detectarPreset(grupos: Record<string, string>): number {
  for (let i = 0; i < NORM_PRESETS.length; i++) {
    const pg = NORM_PRESETS[i].grupos
    if (pg.G === grupos.G && pg.M === grupos.M && pg.B === grupos.B) return i
  }
  return 0
}

function GrupoParamsPanel({
  grupoNombre,
  maquinas,
  params,
  onChange,
}: {
  grupoNombre: string
  maquinas: string[]
  params: NormalizacionParams
  onChange: (p: NormalizacionParams) => void
}) {
  const set = (key: keyof NormalizacionParams, val: string | boolean) =>
    onChange({ ...params, [key]: val })

  return (
    <div className="flex-1 min-w-0 border border-border rounded p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-foreground">Grupo {grupoNombre}</p>
        <span className="text-xs text-muted-foreground">{maquinas.join(", ")}</span>
      </div>

      <div className="grid grid-cols-1 gap-2">
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Carpeta origen</Label>
          <select
            className={selectClass}
            value={params.carpeta}
            onChange={(e) => set("carpeta", e.target.value)}
          >
            <option value="audios">audios/</option>
            <option value="reprocesar">audios_procesados/reprocesar/</option>
            <option value="ambos">ambos</option>
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Umbral de silencio</Label>
          <input
            type="text"
            className={inputClass}
            value={params.silence_threshold}
            onChange={(e) => set("silence_threshold", e.target.value)}
            placeholder="-40dB"
          />
        </div>

        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Duración mín. silencio (seg)</Label>
          <input
            type="text"
            className={inputClass}
            value={params.silence_duration}
            onChange={(e) => set("silence_duration", e.target.value)}
            placeholder="1"
          />
        </div>

        <div className="flex flex-col gap-2 pt-1">
          {(["normalize", "highpass_filter", "noise_reduction"] as const).map((key) => (
            <label key={key} className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
              <input
                type="checkbox"
                checked={params[key] as boolean}
                onChange={(e) => set(key, e.target.checked)}
              />
              {key === "normalize"       && "Normalización de volumen (loudnorm)"}
              {key === "highpass_filter" && "Filtro pasa-altos (>200Hz)"}
              {key === "noise_reduction" && "Reducción de ruido (lento)"}
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}

function EtapaNormalizacion() {
  const [presetIdx,   setPresetIdx]   = useState(0)
  const [paramsMap,   setParamsMap]   = useState<Record<string, NormalizacionParams>>({
    GBM: { ...NORM_DEFAULTS },
  })
  const [guardando,   setGuardando]   = useState(false)
  const [ejecutando,  setEjecutando]  = useState(false)
  const [mensaje,     setMensaje]     = useState<string | null>(null)

  // Cargar params desde API al montar
  useEffect(() => {
    Promise.all([
      getParametros("normalizacion_G"),
      getParametros("normalizacion_M"),
      getParametros("normalizacion_B"),
    ]).then(([rG, rM, rB]) => {
      const valG = rG?.valor ?? {}
      const valM = rM?.valor ?? {}
      const valB = rB?.valor ?? {}

      const gruposActuales = {
        G: valG.grupo ?? "GBM",
        M: valM.grupo ?? "GBM",
        B: valB.grupo ?? "GBM",
      }
      setPresetIdx(detectarPreset(gruposActuales))

      // Construir paramsMap — una entrada por grupo único
      const map: Record<string, NormalizacionParams> = {}
      const entries = [
        { cuenta: "G", val: valG },
        { cuenta: "M", val: valM },
        { cuenta: "B", val: valB },
      ]
      for (const { val } of entries) {
        const g = val.grupo ?? "GBM"
        if (!map[g]) {
          map[g] = { ...NORM_DEFAULTS, ...Object.fromEntries(
            Object.entries(val).filter(([k]) => k !== "grupo")
          ) } as NormalizacionParams
        }
      }
      setParamsMap(map)
    }).catch(() => setMensaje("Error al cargar parámetros"))
  }, [])

  const preset = NORM_PRESETS[presetIdx]

  // Grupos únicos del preset actual con sus máquinas
  const gruposUnicos = Object.entries(
    Object.entries(preset.grupos).reduce<Record<string, string[]>>(
      (acc, [cuenta, grupo]) => {
        acc[grupo] = [...(acc[grupo] ?? []), cuenta]
        return acc
      },
      {}
    )
  )

  const handlePreset = (idx: number) => {
    setPresetIdx(idx)
    // Inicializar paramsMap para grupos nuevos con DEFAULTS
    const nuevosGrupos = NORM_PRESETS[idx].grupos
    const gruposNuevosUnicos = [...new Set(Object.values(nuevosGrupos))]
    setParamsMap((prev) => {
      const next: Record<string, NormalizacionParams> = {}
      for (const g of gruposNuevosUnicos) {
        next[g] = prev[g] ?? { ...NORM_DEFAULTS }
      }
      return next
    })
  }

  const handleGuardar = async () => {
    setGuardando(true)
    setMensaje(null)
    try {
      await Promise.all(
        (["G", "M", "B"] as const).map((cuenta) => {
          const grupo  = preset.grupos[cuenta]
          const params = paramsMap[grupo] ?? NORM_DEFAULTS
          return actualizarParametros(`normalizacion_${cuenta}`, { grupo, ...params })
        })
      )
      setMensaje("Guardado")
    } catch {
      setMensaje("Error al guardar")
    } finally {
      setGuardando(false)
    }
  }

  const handleEjecutar = async () => {
    setEjecutando(true)
    setMensaje(null)
    try {
      await ejecutarEtapa("normalizacion", "pendientes")
      setMensaje("Ejecución iniciada")
    } catch {
      setMensaje("Error al ejecutar")
    } finally {
      setEjecutando(false)
    }
  }

  return (
    <div className="flex flex-col gap-4 pt-3">

      {/* Selector de preset de grupos */}
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Configuración de grupos</Label>
        <div className="flex gap-2 flex-wrap">
          {NORM_PRESETS.map((p, i) => (
            <button
              key={p.label}
              type="button"
              onClick={() => handlePreset(i)}
              className={`px-3 py-1 rounded text-xs border transition-colors ${
                i === presetIdx
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-background text-foreground border-border hover:bg-muted"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Paneles de params por grupo */}
      <div className="flex gap-4 flex-wrap">
        {gruposUnicos.map(([grupo, maquinas]) => (
          <GrupoParamsPanel
            key={grupo}
            grupoNombre={grupo}
            maquinas={maquinas}
            params={paramsMap[grupo] ?? NORM_DEFAULTS}
            onChange={(p) => setParamsMap((prev) => ({ ...prev, [grupo]: p }))}
          />
        ))}
      </div>

      {/* Acciones */}
      <div className="flex items-center gap-3 pt-1 border-t border-border">
        <Button size="sm" onClick={handleGuardar} disabled={guardando}>
          {guardando ? "Guardando..." : "Guardar"}
        </Button>
        <Button onClick={handleEjecutar} disabled={ejecutando}>
          {ejecutando ? "Ejecutando..." : "Ejecutar normalización"}
        </Button>
        {mensaje && <span className="text-xs text-muted-foreground">{mensaje}</span>}
      </div>
    </div>
  )
}

// ── Contenido de la etapa Creación de registros ───────────────────────────────

function EtapaCreacionRegistros() {
  const [ejecutando,       setEjecutando]       = useState(false)
  const [mensajeEjecucion, setMensajeEjecucion] = useState<string | null>(null)

  const handleEjecutar = async () => {
    setEjecutando(true)
    setMensajeEjecucion(null)
    try {
      await ejecutarEtapa("creacion_registros", "pendientes")
      setMensajeEjecucion("Ejecución iniciada")
    } catch {
      setMensajeEjecucion("Error al ejecutar")
    } finally {
      setEjecutando(false)
    }
  }

  return (
    <div className="flex items-center gap-3 pt-3">
      <Button onClick={handleEjecutar} disabled={ejecutando}>
        {ejecutando ? "Ejecutando..." : "Crear registros"}
      </Button>
      {mensajeEjecucion && (
        <span className="text-xs text-muted-foreground">{mensajeEjecucion}</span>
      )}
    </div>
  )
}

// ── Container colapsable genérico ──────────────────────────────────────────────

function EtapaContainer({
  label,
  children,
  defaultOpen = false,
}: {
  label: string
  children?: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <div className="border border-border rounded">
        <CollapsibleTrigger asChild>
          <button
            className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-foreground hover:bg-muted/50 transition-colors rounded"
            type="button"
          >
            <span>{label}</span>
            {open ? (
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            )}
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="px-4 pb-4">
            {children}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}

// ── Página principal ───────────────────────────────────────────────────────────

export default function PipelineConfiguracion() {
  return (
    <div className="p-6 flex flex-col gap-3 max-w-6xl">
      <h1 className="text-lg font-semibold text-foreground mb-1">
        Configuración del pipeline
      </h1>

      {ETAPAS.map(({ id, label }) => (
        <EtapaContainer key={id} label={label} defaultOpen={id === "descarga"}>
          {id === "descarga"           && <EtapaDescarga />}
          {id === "creacion_registros" && <EtapaCreacionRegistros />}
          {id === "normalizacion"      && <EtapaNormalizacion />}
        </EtapaContainer>
      ))}
    </div>
  )
}
