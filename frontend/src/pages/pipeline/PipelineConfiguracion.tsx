import { useState, useEffect, useCallback } from "react"
import { ChevronDown, ChevronRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { getParametros, actualizarParametros, ejecutarEtapa, limpiarAudiosNormalizacion, resetearCorreccionNormalizacion, limpiarTranscripciones, resetearCorreccionTranscripciones } from "@/api/pipeline"

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

// ── Etapa Corrección de normalización ─────────────────────────────────────────

type CorreccionNormParams = {
  duracion_minima_seg:  number
  duracion_maxima_seg:  number
  peso_snr:             number
  peso_duracion_ratio:  number
  peso_rms:             number
  snr_max:              number
  rms_ref_dbfs:         number
  rms_tolerancia_db:    number
  duracion_ratio_min:   number
  umbral_correcto:      number
  umbral_reprocesar:    number
}

const CORR_NORM_DEFAULTS: CorreccionNormParams = {
  duracion_minima_seg:  3,
  duracion_maxima_seg:  1800,
  peso_snr:             0.40,
  peso_duracion_ratio:  0.30,
  peso_rms:             0.30,
  snr_max:              40,
  rms_ref_dbfs:        -16,
  rms_tolerancia_db:    6,
  duracion_ratio_min:   0.10,
  umbral_correcto:      0.75,
  umbral_reprocesar:    0.40,
}

function EtapaCorreccionNormalizacion() {
  const [params,     setParams]     = useState<CorreccionNormParams>(CORR_NORM_DEFAULTS)
  const [guardando,   setGuardando]   = useState(false)
  const [ejecutando,  setEjecutando]  = useState(false)
  const [limpiando,   setLimpiando]   = useState(false)
  const [reseteando,  setReseteando]  = useState(false)
  const [mensaje,     setMensaje]     = useState<string | null>(null)

  useEffect(() => {
    getParametros("correccion_normalizacion")
      .then((res: { valor?: Partial<CorreccionNormParams> }) => {
        const v = res?.valor ?? {}
        setParams({ ...CORR_NORM_DEFAULTS, ...v })
      })
      .catch(() => setMensaje("Error al cargar parámetros"))
  }, [])

  const set = (key: keyof CorreccionNormParams, val: string) =>
    setParams((prev) => ({ ...prev, [key]: Number(val) }))

  const handleGuardar = async () => {
    setGuardando(true)
    setMensaje(null)
    try {
      await actualizarParametros("correccion_normalizacion", params)
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
      await ejecutarEtapa("correccion_normalizacion", "pendientes")
      setMensaje("Ejecución iniciada")
    } catch {
      setMensaje("Error al ejecutar")
    } finally {
      setEjecutando(false)
    }
  }

  const handleLimpiar = async () => {
    setLimpiando(true)
    setMensaje(null)
    try {
      await limpiarAudiosNormalizacion()
      setMensaje("Limpieza iniciada")
    } catch {
      setMensaje("Error al iniciar limpieza")
    } finally {
      setLimpiando(false)
    }
  }

  const handleResetear = async () => {
    if (!confirm("¿Resetear todos los resultados de corrección de normalización? Esta acción no se puede deshacer.")) return
    setReseteando(true)
    setMensaje(null)
    try {
      const res = await resetearCorreccionNormalizacion()
      setMensaje(`Reseteados: ${res.reseteados} audios`)
    } catch {
      setMensaje("Error al resetear")
    } finally {
      setReseteando(false)
    }
  }

  const numInput = (key: keyof CorreccionNormParams, label: string, step = "0.01") => (
    <div className="flex flex-col gap-1">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <input
        type="number"
        step={step}
        className={inputClass}
        value={params[key]}
        onChange={(e) => set(key, e.target.value)}
      />
    </div>
  )

  return (
    <div className="flex flex-col gap-4 pt-3">

      <div className="grid grid-cols-2 gap-4">

        {/* Umbrales duros */}
        <div className="border border-border rounded p-4 flex flex-col gap-3">
          <p className="text-sm font-medium text-foreground">Umbrales duros</p>
          {numInput("duracion_minima_seg", "Duración mínima (seg)", "1")}
          {numInput("duracion_maxima_seg", "Duración máxima (seg)", "1")}
        </div>

        {/* Pesos del score */}
        <div className="border border-border rounded p-4 flex flex-col gap-3">
          <p className="text-sm font-medium text-foreground">Pesos del score</p>
          {numInput("peso_snr",            "Peso SNR")}
          {numInput("peso_duracion_ratio", "Peso duración ratio")}
          {numInput("peso_rms",            "Peso RMS")}
        </div>

        {/* Referencias de métricas */}
        <div className="border border-border rounded p-4 flex flex-col gap-3">
          <p className="text-sm font-medium text-foreground">Referencias de métricas</p>
          {numInput("snr_max",           "SNR máximo referencia (dB)", "1")}
          {numInput("rms_ref_dbfs",      "RMS objetivo (dBFS)", "0.5")}
          {numInput("rms_tolerancia_db", "Tolerancia RMS (dB)", "0.5")}
          {numInput("duracion_ratio_min","Ratio duración mínimo")}
        </div>

        {/* Umbrales de clasificación */}
        <div className="border border-border rounded p-4 flex flex-col gap-3">
          <p className="text-sm font-medium text-foreground">Umbrales de clasificación</p>
          {numInput("umbral_correcto",   "Score mínimo → correcto")}
          {numInput("umbral_reprocesar", "Score mínimo → reprocesar")}
          <p className="text-xs text-muted-foreground">
            Por debajo de reprocesar → inválido
          </p>
        </div>

      </div>

      <div className="flex items-center gap-3 pt-1 border-t border-border">
        <Button size="sm" onClick={handleGuardar} disabled={guardando}>
          {guardando ? "Guardando..." : "Guardar"}
        </Button>
        <Button onClick={handleEjecutar} disabled={ejecutando}>
          {ejecutando ? "Ejecutando..." : "Ejecutar scoring"}
        </Button>
        <Button variant="outline" onClick={handleLimpiar} disabled={limpiando}>
          {limpiando ? "Limpiando..." : "Limpiar audios duplicados"}
        </Button>
        <Button variant="outline" onClick={handleResetear} disabled={reseteando}>
          {reseteando ? "Reseteando..." : "Resetear resultados"}
        </Button>
        {mensaje && <span className="text-xs text-muted-foreground">{mensaje}</span>}
      </div>
    </div>
  )
}

// ── Etapa Transcripción ────────────────────────────────────────────────────────

type TranscripcionParams = {
  modelo:         string
  compute_type:   string
  batch_size:     number
  min_speakers:   number
  max_speakers:   number
  duracion_desde: number | null
  duracion_hasta: number | null
  estados:        string[]
}

const TRANSCRIPCION_DEFAULTS: TranscripcionParams = {
  modelo:         "large-v2",
  compute_type:   "int8",
  batch_size:     4,
  min_speakers:   2,
  max_speakers:   2,
  duracion_desde: null,
  duracion_hasta: null,
  estados:        ["correcto"],
}

const MODELOS_WHISPER  = ["tiny", "base", "small", "medium", "large-v1", "large-v2", "large-v3"]
const COMPUTE_TYPES    = ["int8", "int8_float16", "float16", "float32"]
const ESTADOS_OPCIONES = ["pendiente", "en_proceso", "correcto", "error", "reprocesar", "invalido"]

const TRANSCRIPCION_PRESETS: { label: string; grupos: Record<string, string> }[] = [
  { label: "GBM",       grupos: { G: "GBM", M: "GBM", B: "GBM" } },
  { label: "GM | B",    grupos: { G: "GM",  M: "GM",  B: "B"   } },
  { label: "GB | M",    grupos: { G: "GB",  M: "M",   B: "GB"  } },
  { label: "G | MB",    grupos: { G: "G",   M: "MB",  B: "MB"  } },
  { label: "G | M | B", grupos: { G: "G",   M: "M",   B: "B"   } },
]

function detectarPresetTranscripcion(grupos: Record<string, string>): number {
  for (let i = 0; i < TRANSCRIPCION_PRESETS.length; i++) {
    const pg = TRANSCRIPCION_PRESETS[i].grupos
    if (pg.G === grupos.G && pg.M === grupos.M && pg.B === grupos.B) return i
  }
  return 0
}

function GrupoTranscripcionPanel({
  grupoNombre,
  maquinas,
  params,
  onChange,
}: {
  grupoNombre: string
  maquinas: string[]
  params: TranscripcionParams
  onChange: (p: TranscripcionParams) => void
}) {
  const set = <K extends keyof TranscripcionParams>(key: K, val: TranscripcionParams[K]) =>
    onChange({ ...params, [key]: val })

  const toggleEstado = (estado: string) => {
    const estados = params.estados.includes(estado)
      ? params.estados.filter((e) => e !== estado)
      : [...params.estados, estado]
    onChange({ ...params, estados })
  }

  return (
    <div className="flex-1 min-w-0 border border-border rounded p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-foreground">Grupo {grupoNombre}</p>
        <span className="text-xs text-muted-foreground">{maquinas.join(", ")}</span>
      </div>

      <div className="grid grid-cols-1 gap-2">

        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Modelo</Label>
          <select
            className={selectClass}
            value={params.modelo}
            onChange={(e) => set("modelo", e.target.value)}
          >
            {MODELOS_WHISPER.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Compute type</Label>
          <select
            className={selectClass}
            value={params.compute_type}
            onChange={(e) => set("compute_type", e.target.value)}
          >
            {COMPUTE_TYPES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Batch size</Label>
          <select
            className={selectClass}
            value={params.batch_size}
            onChange={(e) => set("batch_size", Number(e.target.value))}
          >
            {[1, 2, 4, 8, 16].map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        </div>

        <div className="flex gap-2">
          <div className="flex flex-col gap-1 flex-1">
            <Label className="text-xs text-muted-foreground">Min speakers</Label>
            <input
              type="number"
              min={1}
              max={10}
              step={1}
              className={inputClass}
              value={params.min_speakers}
              onChange={(e) => set("min_speakers", Number(e.target.value))}
            />
          </div>
          <div className="flex flex-col gap-1 flex-1">
            <Label className="text-xs text-muted-foreground">Max speakers</Label>
            <input
              type="number"
              min={1}
              max={10}
              step={1}
              className={inputClass}
              value={params.max_speakers}
              onChange={(e) => set("max_speakers", Number(e.target.value))}
            />
          </div>
        </div>

        <div className="flex gap-2">
          <div className="flex flex-col gap-1 flex-1">
            <Label className="text-xs text-muted-foreground">Duración desde (seg)</Label>
            <input
              type="number"
              min={0}
              step={1}
              className={inputClass}
              value={params.duracion_desde ?? ""}
              placeholder="—"
              onChange={(e) => set("duracion_desde", e.target.value === "" ? null : Number(e.target.value))}
            />
          </div>
          <div className="flex flex-col gap-1 flex-1">
            <Label className="text-xs text-muted-foreground">Duración hasta (seg)</Label>
            <input
              type="number"
              min={0}
              step={1}
              className={inputClass}
              value={params.duracion_hasta ?? ""}
              placeholder="—"
              onChange={(e) => set("duracion_hasta", e.target.value === "" ? null : Number(e.target.value))}
            />
          </div>
        </div>

        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Estados a procesar</Label>
          <div className="flex flex-col gap-1.5 pt-0.5">
            {ESTADOS_OPCIONES.map((estado) => (
              <label key={estado} className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={params.estados.includes(estado)}
                  onChange={() => toggleEstado(estado)}
                />
                {estado}
              </label>
            ))}
          </div>
        </div>

      </div>
    </div>
  )
}

function EtapaTranscripcion() {
  const [presetIdx,  setPresetIdx]  = useState(0)
  const [paramsMap,  setParamsMap]  = useState<Record<string, TranscripcionParams>>({
    GBM: { ...TRANSCRIPCION_DEFAULTS },
  })
  const [guardando,  setGuardando]  = useState(false)
  const [ejecutando, setEjecutando] = useState(false)
  const [mensaje,    setMensaje]    = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      getParametros("transcripcion_G"),
      getParametros("transcripcion_M"),
      getParametros("transcripcion_B"),
    ]).then(([rG, rM, rB]) => {
      const valG = rG?.valor ?? {}
      const valM = rM?.valor ?? {}
      const valB = rB?.valor ?? {}

      const gruposActuales = {
        G: valG.grupo ?? "T1",
        M: valM.grupo ?? "T1",
        B: valB.grupo ?? "T1",
      }
      setPresetIdx(detectarPresetTranscripcion(gruposActuales))

      const map: Record<string, TranscripcionParams> = {}
      const entries = [
        { val: valG },
        { val: valM },
        { val: valB },
      ]
      for (const { val } of entries) {
        const g = val.grupo ?? "T1"
        if (!map[g]) {
          map[g] = { ...TRANSCRIPCION_DEFAULTS, ...Object.fromEntries(
            Object.entries(val).filter(([k]) => k !== "grupo")
          ) } as TranscripcionParams
        }
      }
      setParamsMap(map)
    }).catch(() => setMensaje("Error al cargar parámetros"))
  }, [])

  const preset = TRANSCRIPCION_PRESETS[presetIdx]

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
    const nuevosGrupos = TRANSCRIPCION_PRESETS[idx].grupos
    const gruposNuevosUnicos = [...new Set(Object.values(nuevosGrupos))]
    setParamsMap((prev) => {
      const next: Record<string, TranscripcionParams> = {}
      for (const g of gruposNuevosUnicos) {
        next[g] = prev[g] ?? { ...TRANSCRIPCION_DEFAULTS }
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
          const params = paramsMap[grupo] ?? TRANSCRIPCION_DEFAULTS
          return actualizarParametros(`transcripcion_${cuenta}`, { grupo, ...params })
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
      await ejecutarEtapa("transcripcion", "pendientes")
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
          {TRANSCRIPCION_PRESETS.map((p, i) => (
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
          <GrupoTranscripcionPanel
            key={grupo}
            grupoNombre={grupo}
            maquinas={maquinas}
            params={paramsMap[grupo] ?? TRANSCRIPCION_DEFAULTS}
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
          {ejecutando ? "Ejecutando..." : "Ejecutar transcripción"}
        </Button>
        {mensaje && <span className="text-xs text-muted-foreground">{mensaje}</span>}
      </div>
    </div>
  )
}

// ── Contenido de la etapa Creación de registros ───────────────────────────────

const LIMITE_OPCIONES = [
  { label: "Todos",   value: "" },
  { label: "100",     value: "100" },
  { label: "200",     value: "200" },
  { label: "500",     value: "500" },
  { label: "1.000",   value: "1000" },
  { label: "2.000",   value: "2000" },
  { label: "5.000",   value: "5000" },
  { label: "10.000",  value: "10000" },
]

function EtapaCreacionRegistros() {
  const [limite,           setLimite]           = useState<string>("")
  const [guardando,        setGuardando]        = useState(false)
  const [ejecutando,       setEjecutando]       = useState(false)
  const [mensaje,          setMensaje]          = useState<string | null>(null)

  useEffect(() => {
    getParametros("creacion_registros")
      .then((res: { valor?: { limite?: number | null } }) => {
        const v = res?.valor?.limite
        setLimite(v != null ? String(v) : "")
      })
      .catch(() => {})
  }, [])

  const handleGuardar = async () => {
    setGuardando(true)
    setMensaje(null)
    try {
      await actualizarParametros("creacion_registros", {
        limite: limite === "" ? null : Number(limite),
      })
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
      await ejecutarEtapa("creacion_registros", "pendientes")
      setMensaje("Ejecución iniciada")
    } catch {
      setMensaje("Error al ejecutar")
    } finally {
      setEjecutando(false)
    }
  }

  return (
    <div className="flex flex-col gap-4 pt-3">
      <div className="flex flex-col gap-1 max-w-xs">
        <Label className="text-xs text-muted-foreground">
          Cantidad de registros a crear (aleatoria)
        </Label>
        <select
          className={selectClass}
          value={limite}
          onChange={(e) => setLimite(e.target.value)}
        >
          {LIMITE_OPCIONES.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-3 pt-1 border-t border-border">
        <Button size="sm" onClick={handleGuardar} disabled={guardando}>
          {guardando ? "Guardando..." : "Guardar"}
        </Button>
        <Button onClick={handleEjecutar} disabled={ejecutando}>
          {ejecutando ? "Ejecutando..." : "Crear registros"}
        </Button>
        {mensaje && (
          <span className="text-xs text-muted-foreground">{mensaje}</span>
        )}
      </div>
    </div>
  )
}

// ── Etapa Corrección de transcripciones ───────────────────────────────────────

// ── Params determinista ─────────────────────────────────────────────────────

type CorrTranscrDetParams = {
  duracion_desde:            number | null
  duracion_hasta:            number | null
  umbral_logprob_invalido:   number
  umbral_logprob_reprocesar: number
  umbral_words_min:          number
  umbral_low_score_ratio:    number
  umbral_speaker_dominance:  number
  peso_logprob:              number
  peso_words:                number
  peso_speaker_balance:      number
  umbral_score_correcto:     number
  umbral_score_reprocesar:   number
}

const CORR_TRANSCR_DET_DEFAULTS: CorrTranscrDetParams = {
  duracion_desde:            null,
  duracion_hasta:            null,
  umbral_logprob_invalido:   -0.6,
  umbral_logprob_reprocesar: -0.4,
  umbral_words_min:          20,
  umbral_low_score_ratio:    0.25,
  umbral_speaker_dominance:  0.95,
  peso_logprob:              0.50,
  peso_words:                0.25,
  peso_speaker_balance:      0.25,
  umbral_score_correcto:     0.75,
  umbral_score_reprocesar:   0.40,
}

// ── Params LLM ──────────────────────────────────────────────────────────────

type CorrTranscrLLMParams = {
  grupo:                   string
  modelo:                  string
  max_segmentos_inicio:    number
  max_segmentos_fin:       number
  usar_llm:                boolean
  duracion_desde:          number | null
  duracion_hasta:          number | null
  peso_score_determinista: number
  peso_score_llm:          number
  umbral_score_correcto:   number
  umbral_score_reprocesar: number
}

const CORR_TRANSCR_LLM_DEFAULTS: CorrTranscrLLMParams = {
  grupo:                   "GBM",
  modelo:                  "Qwen/Qwen2.5-3B-Instruct-AWQ",
  max_segmentos_inicio:    30,
  max_segmentos_fin:       20,
  usar_llm:                true,
  duracion_desde:          null,
  duracion_hasta:          null,
  peso_score_determinista: 0.40,
  peso_score_llm:          0.60,
  umbral_score_correcto:   0.75,
  umbral_score_reprocesar: 0.40,
}

// ── Params ganador ──────────────────────────────────────────────────────────

type CorrTranscrGanadorParams = {
  umbral_score_correcto:   number
  umbral_score_reprocesar: number
}

const CORR_TRANSCR_GANADOR_DEFAULTS: CorrTranscrGanadorParams = {
  umbral_score_correcto:   0.75,
  umbral_score_reprocesar: 0.40,
}

const MODELOS_LLM = [
  "Qwen/Qwen2.5-3B-Instruct-AWQ",
  "Qwen/Qwen2.5-3B-Instruct",
  "Qwen/Qwen2.5-7B-Instruct-AWQ",
  "Qwen/Qwen2.5-7B-Instruct",
  "microsoft/Phi-3-mini-4k-instruct",
]

const CT_PRESETS = TRANSCRIPCION_PRESETS   // reutiliza los mismos grupos GBM

function detectarPresetCT(grupos: Record<string, string>): number {
  for (let i = 0; i < CT_PRESETS.length; i++) {
    const pg = CT_PRESETS[i].grupos
    if (pg.G === grupos.G && pg.M === grupos.M && pg.B === grupos.B) return i
  }
  return -1
}

function GrupoLLMPanel({
  cuenta,
  params,
  onChange,
}: {
  cuenta: string
  params: CorrTranscrLLMParams
  onChange: (key: keyof CorrTranscrLLMParams, val: string | boolean | null) => void
}) {
  return (
    <div className="border border-border rounded p-4 flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <Label className="text-xs text-muted-foreground">Modelo LLM</Label>
        <select
          className={inputClass}
          value={params.modelo}
          onChange={(e) => onChange("modelo", e.target.value)}
        >
          {MODELOS_LLM.map((m) => <option key={m} value={m}>{m.split("/")[1]}</option>)}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Segmentos inicio</Label>
          <input type="number" step="1" className={inputClass}
            value={params.max_segmentos_inicio}
            onChange={(e) => onChange("max_segmentos_inicio", e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Segmentos fin</Label>
          <input type="number" step="1" className={inputClass}
            value={params.max_segmentos_fin}
            onChange={(e) => onChange("max_segmentos_fin", e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Duración desde (seg)</Label>
          <input type="number" step="1" className={inputClass}
            value={params.duracion_desde ?? ""}
            placeholder="sin límite"
            onChange={(e) => onChange("duracion_desde", e.target.value === "" ? null : e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Duración hasta (seg)</Label>
          <input type="number" step="1" className={inputClass}
            value={params.duracion_hasta ?? ""}
            placeholder="sin límite"
            onChange={(e) => onChange("duracion_hasta", e.target.value === "" ? null : e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Peso score determinista</Label>
          <input type="number" step="0.05" className={inputClass}
            value={params.peso_score_determinista}
            onChange={(e) => onChange("peso_score_determinista", e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Peso score LLM</Label>
          <input type="number" step="0.05" className={inputClass}
            value={params.peso_score_llm}
            onChange={(e) => onChange("peso_score_llm", e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Umbral correcto</Label>
          <input type="number" step="0.05" className={inputClass}
            value={params.umbral_score_correcto}
            onChange={(e) => onChange("umbral_score_correcto", e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">Umbral reprocesar</Label>
          <input type="number" step="0.05" className={inputClass}
            value={params.umbral_score_reprocesar}
            onChange={(e) => onChange("umbral_score_reprocesar", e.target.value)} />
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
        <input type="checkbox" checked={params.usar_llm}
          onChange={(e) => onChange("usar_llm", e.target.checked)} />
        Usar LLM (desactivar para debug sin GPU)
      </label>
    </div>
  )
}

function EtapaCorreccionTranscripciones() {
  // ── Estado params determinista ──────────────────────────────────────────────
  const [detParams, setDetParams] = useState<CorrTranscrDetParams>(CORR_TRANSCR_DET_DEFAULTS)

  // ── Estado params LLM por cuenta ────────────────────────────────────────────
  const [llmParams, setLlmParams] = useState<Record<string, CorrTranscrLLMParams>>({
    G: { ...CORR_TRANSCR_LLM_DEFAULTS },
    M: { ...CORR_TRANSCR_LLM_DEFAULTS },
    B: { ...CORR_TRANSCR_LLM_DEFAULTS },
  })
  const [presetIdx, setPresetIdx] = useState(0)

  // ── Estado params ganador ────────────────────────────────────────────────────
  const [ganadorParams, setGanadorParams] = useState<CorrTranscrGanadorParams>(CORR_TRANSCR_GANADOR_DEFAULTS)

  // ── UI ───────────────────────────────────────────────────────────────────────
  const [guardando,      setGuardando]      = useState(false)
  const [ejecutando,     setEjecutando]     = useState(false)
  const [ejecutandoLLM,  setEjecutandoLLM]  = useState(false)
  const [limpiando,      setLimpiando]      = useState(false)
  const [reseteando,     setReseteando]     = useState(false)
  const [mensaje,        setMensaje]        = useState<string | null>(null)

  // ── Carga inicial ────────────────────────────────────────────────────────────
  useEffect(() => {
    getParametros("correccion_transcripciones")
      .then((res: { valor?: Partial<CorrTranscrDetParams> }) => {
        const v = res?.valor ?? {}
        setDetParams({ ...CORR_TRANSCR_DET_DEFAULTS, ...v })
      })
      .catch(() => {})

    const cargarLLM = async () => {
      const gruposActuales: Record<string, string> = { G: "GBM", M: "GBM", B: "GBM" }
      const nuevosParams: Record<string, CorrTranscrLLMParams> = {
        G: { ...CORR_TRANSCR_LLM_DEFAULTS },
        M: { ...CORR_TRANSCR_LLM_DEFAULTS },
        B: { ...CORR_TRANSCR_LLM_DEFAULTS },
      }
      for (const cuenta of ["G", "M", "B"]) {
        try {
          const res = await getParametros(`correccion_transcripciones_llm_${cuenta}`)
          const v = res?.valor ?? {}
          nuevosParams[cuenta] = { ...CORR_TRANSCR_LLM_DEFAULTS, ...v }
          if (v.grupo) gruposActuales[cuenta] = v.grupo
        } catch { /* usa defaults */ }
      }
      setLlmParams(nuevosParams)
      const idx = detectarPresetCT(gruposActuales)
      if (idx >= 0) setPresetIdx(idx)
    }
    cargarLLM()

    getParametros("correccion_transcripciones_ganador")
      .then((res: { valor?: Partial<CorrTranscrGanadorParams> }) => {
        const v = res?.valor ?? {}
        setGanadorParams({ ...CORR_TRANSCR_GANADOR_DEFAULTS, ...v })
      })
      .catch(() => {})
  }, [])

  // ── Selección de preset ──────────────────────────────────────────────────────
  const aplicarPreset = (idx: number) => {
    setPresetIdx(idx)
    const grupos = CT_PRESETS[idx].grupos
    setLlmParams((prev) => {
      const next = { ...prev }
      for (const cuenta of ["G", "M", "B"] as const) {
        next[cuenta] = { ...prev[cuenta], grupo: grupos[cuenta] }
      }
      return next
    })
  }

  // ── Helpers ──────────────────────────────────────────────────────────────────
  const setDet = (key: keyof CorrTranscrDetParams, val: string | null) =>
    setDetParams((prev) => ({ ...prev, [key]: val === null ? null : Number(val) }))

  const setLLM = (cuenta: string, key: keyof CorrTranscrLLMParams, val: string | boolean | null) =>
    setLlmParams((prev) => ({
      ...prev,
      [cuenta]: {
        ...prev[cuenta],
        [key]: val === null ? null
             : typeof val === "boolean" ? val
             : isNaN(Number(val)) ? val
             : Number(val),
      },
    }))

  const setGanador = (key: keyof CorrTranscrGanadorParams, val: string) =>
    setGanadorParams((prev) => ({ ...prev, [key]: Number(val) }))

  // ── Guardado ─────────────────────────────────────────────────────────────────
  const handleGuardar = async () => {
    setGuardando(true)
    setMensaje(null)
    try {
      await actualizarParametros("correccion_transcripciones", detParams)
      for (const cuenta of ["G", "M", "B"]) {
        await actualizarParametros(`correccion_transcripciones_llm_${cuenta}`, llmParams[cuenta])
      }
      await actualizarParametros("correccion_transcripciones_ganador", ganadorParams)
      setMensaje("Guardado")
    } catch {
      setMensaje("Error al guardar")
    } finally {
      setGuardando(false)
    }
  }

  const handleEjecutarDet = async () => {
    setEjecutando(true)
    setMensaje(null)
    try {
      await ejecutarEtapa("correccion_transcripciones", "pendientes")
      setMensaje("Scoring determinista iniciado")
    } catch {
      setMensaje("Error al ejecutar")
    } finally {
      setEjecutando(false)
    }
  }

  const handleEjecutarLLM = async () => {
    setEjecutandoLLM(true)
    setMensaje(null)
    try {
      await ejecutarEtapa("correccion_transcripciones_llm", "pendientes")
      setMensaje("Scoring LLM iniciado")
    } catch {
      setMensaje("Error al ejecutar LLM")
    } finally {
      setEjecutandoLLM(false)
    }
  }

  const handleLimpiar = async () => {
    setLimpiando(true)
    setMensaje(null)
    try {
      await limpiarTranscripciones()
      setMensaje("Selección de ganador iniciada")
    } catch {
      setMensaje("Error al iniciar limpieza")
    } finally {
      setLimpiando(false)
    }
  }

  const handleResetear = async () => {
    if (!confirm("¿Resetear todos los resultados de corrección de transcripciones? Esta acción no se puede deshacer.")) return
    setReseteando(true)
    setMensaje(null)
    try {
      const res = await resetearCorreccionTranscripciones()
      setMensaje(`Reseteados: ${res.reseteados} audios`)
    } catch {
      setMensaje("Error al resetear")
    } finally {
      setReseteando(false)
    }
  }

  const grupos = CT_PRESETS[presetIdx >= 0 ? presetIdx : 0].grupos
  const gruposUnicos = [...new Set(Object.values(grupos))]

  return (
    <div className="flex flex-col gap-6 pt-3">

      {/* ── Scoring determinista ─────────────────────────────────────── */}
      <div className="flex flex-col gap-3">
        <p className="text-sm font-semibold text-foreground">Scoring determinista (CPU · Gaspar)</p>
        <div className="grid grid-cols-2 gap-4">

          <div className="border border-border rounded p-4 flex flex-col gap-3">
            <p className="text-sm font-medium text-foreground">Filtros por conversación</p>
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">Duración desde (seg)</Label>
              <input type="number" step="1" className={inputClass}
                value={detParams.duracion_desde ?? ""}
                placeholder="sin límite"
                onChange={(e) => setDet("duracion_desde", e.target.value === "" ? null : e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">Duración hasta (seg)</Label>
              <input type="number" step="1" className={inputClass}
                value={detParams.duracion_hasta ?? ""}
                placeholder="sin límite"
                onChange={(e) => setDet("duracion_hasta", e.target.value === "" ? null : e.target.value)} />
            </div>
          </div>

          <div className="border border-border rounded p-4 flex flex-col gap-3">
            <p className="text-sm font-medium text-foreground">Filtros duros (→ inválido)</p>
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">avg_logprob mínimo (invalido)</Label>
              <input type="number" step="0.05" className={inputClass}
                value={detParams.umbral_logprob_invalido}
                onChange={(e) => setDet("umbral_logprob_invalido", e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">avg_logprob mínimo (reprocesar)</Label>
              <input type="number" step="0.05" className={inputClass}
                value={detParams.umbral_logprob_reprocesar}
                onChange={(e) => setDet("umbral_logprob_reprocesar", e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">Palabras mínimas</Label>
              <input type="number" step="1" className={inputClass}
                value={detParams.umbral_words_min}
                onChange={(e) => setDet("umbral_words_min", e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">Ratio palabras con score bajo (&lt; 0.15)</Label>
              <input type="number" step="0.01" className={inputClass}
                value={detParams.umbral_low_score_ratio}
                onChange={(e) => setDet("umbral_low_score_ratio", e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">Speaker dominance máximo</Label>
              <input type="number" step="0.01" className={inputClass}
                value={detParams.umbral_speaker_dominance}
                onChange={(e) => setDet("umbral_speaker_dominance", e.target.value)} />
            </div>
          </div>

          <div className="border border-border rounded p-4 flex flex-col gap-3">
            <p className="text-sm font-medium text-foreground">Pesos del score</p>
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">Peso avg_logprob</Label>
              <input type="number" step="0.05" className={inputClass}
                value={detParams.peso_logprob}
                onChange={(e) => setDet("peso_logprob", e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">Peso palabras totales</Label>
              <input type="number" step="0.05" className={inputClass}
                value={detParams.peso_words}
                onChange={(e) => setDet("peso_words", e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">Peso balance de hablantes</Label>
              <input type="number" step="0.05" className={inputClass}
                value={detParams.peso_speaker_balance}
                onChange={(e) => setDet("peso_speaker_balance", e.target.value)} />
            </div>
          </div>

          <div className="border border-border rounded p-4 flex flex-col gap-3">
            <p className="text-sm font-medium text-foreground">Umbrales de clasificación</p>
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">Score mínimo → correcto</Label>
              <input type="number" step="0.05" className={inputClass}
                value={detParams.umbral_score_correcto}
                onChange={(e) => setDet("umbral_score_correcto", e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <Label className="text-xs text-muted-foreground">Score mínimo → reprocesar</Label>
              <input type="number" step="0.05" className={inputClass}
                value={detParams.umbral_score_reprocesar}
                onChange={(e) => setDet("umbral_score_reprocesar", e.target.value)} />
            </div>
            <p className="text-xs text-muted-foreground">Por debajo de reprocesar → inválido</p>
          </div>
        </div>
      </div>

      {/* ── Scoring LLM ──────────────────────────────────────────────── */}
      <div className="flex flex-col gap-3">
        <p className="text-sm font-semibold text-foreground">Scoring LLM (GPU · 3 PCs)</p>

        {/* Selector de preset */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Grupos:</span>
          {CT_PRESETS.map((preset, i) => (
            <button
              key={i}
              type="button"
              onClick={() => aplicarPreset(i)}
              className={`px-3 py-1 rounded text-xs border transition-colors ${
                presetIdx === i
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-background text-foreground border-border hover:bg-muted"
              }`}
            >
              {preset.label}
            </button>
          ))}
        </div>

        {/* Panels por grupo único */}
        <div className="grid grid-cols-1 gap-4">
          {gruposUnicos.map((grupo) => {
            const cuentas = (["G", "M", "B"] as const).filter((c) => grupos[c] === grupo)
            // Toma los params de la primera cuenta del grupo
            const cuenta0 = cuentas[0]
            return (
              <div key={grupo}>
                <p className="text-xs text-muted-foreground mb-2">
                  Grupo <strong>{grupo}</strong> — máquinas: {cuentas.join(", ")}
                </p>
                <GrupoLLMPanel
                  cuenta={cuenta0}
                  params={llmParams[cuenta0]}
                  onChange={(key, val) => {
                    // propaga a todas las cuentas del grupo
                    for (const c of cuentas) setLLM(c, key, val)
                  }}
                />
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Selección de ganador ─────────────────────────────────────── */}
      <div className="flex flex-col gap-3">
        <p className="text-sm font-semibold text-foreground">Selección de ganador</p>
        <div className="border border-border rounded p-4 flex flex-col gap-3 max-w-sm">
          <div className="flex flex-col gap-1">
            <Label className="text-xs text-muted-foreground">Score mínimo → correcto</Label>
            <input type="number" step="0.05" className={inputClass}
              value={ganadorParams.umbral_score_correcto}
              onChange={(e) => setGanador("umbral_score_correcto", e.target.value)} />
          </div>
          <div className="flex flex-col gap-1">
            <Label className="text-xs text-muted-foreground">Score mínimo → reprocesar</Label>
            <input type="number" step="0.05" className={inputClass}
              value={ganadorParams.umbral_score_reprocesar}
              onChange={(e) => setGanador("umbral_score_reprocesar", e.target.value)} />
          </div>
        </div>
      </div>

      {/* ── Acciones ─────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3 pt-1 border-t border-border">
        <Button size="sm" onClick={handleGuardar} disabled={guardando}>
          {guardando ? "Guardando..." : "Guardar"}
        </Button>
        <Button onClick={handleEjecutarDet} disabled={ejecutando}>
          {ejecutando ? "Ejecutando..." : "Ejecutar determinista"}
        </Button>
        <Button onClick={handleEjecutarLLM} disabled={ejecutandoLLM}>
          {ejecutandoLLM ? "Ejecutando..." : "Ejecutar LLM"}
        </Button>
        <Button variant="outline" onClick={handleLimpiar} disabled={limpiando}>
          {limpiando ? "Seleccionando..." : "Seleccionar ganador"}
        </Button>
        <Button variant="outline" onClick={handleResetear} disabled={reseteando}>
          {reseteando ? "Reseteando..." : "Resetear resultados"}
        </Button>
        {mensaje && <span className="text-xs text-muted-foreground">{mensaje}</span>}
      </div>
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
          {id === "descarga"                   && <EtapaDescarga />}
          {id === "creacion_registros"         && <EtapaCreacionRegistros />}
          {id === "normalizacion"              && <EtapaNormalizacion />}
          {id === "correccion_normalizacion"   && <EtapaCorreccionNormalizacion />}
          {id === "transcripcion"              && <EtapaTranscripcion />}
          {id === "correccion_transcripciones" && <EtapaCorreccionTranscripciones />}
          {id === "analisis"                   && <p className="pt-3 text-sm text-muted-foreground">Pendiente de implementación</p>}
          {id === "correccion_analisis"        && <p className="pt-3 text-sm text-muted-foreground">Pendiente de implementación</p>}
        </EtapaContainer>
      ))}
    </div>
  )
}
