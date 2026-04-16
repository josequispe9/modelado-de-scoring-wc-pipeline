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
          {id === "descarga" && <EtapaDescarga />}
        </EtapaContainer>
      ))}
    </div>
  )
}
