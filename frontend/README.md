# Dashboard — Frontend

React + TypeScript + Vite + shadcn/ui. Panel de control del sistema de scoring de conversaciones de venta.

---

## Levantar

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173 (o el siguiente puerto libre)
```

La URL base de cada API se configura en `src/api/config.js`:

```js
export const PIPELINE_API_URL = "http://192.168.9.115:8001"
export const SCRAPING_API_URL  = "http://192.168.9.115:8002"
```

---

## Estructura de rutas

| Ruta                         | Componente                   | Estado      |
|------------------------------|------------------------------|-------------|
| `/pipeline/estadisticas`     | `PipelineEstadisticas.tsx`   | completo    |
| `/pipeline/monitoreo`        | `PipelineMonitoreo.tsx`      | completo    |
| `/pipeline/configuracion`    | `PipelineConfiguracion.tsx`  | completo    |
| `/scraping`                  | `ScrapingPage.tsx`           | placeholder |
| `/bases`                     | `BasesPage.tsx`              | placeholder |

---

## Sidebar (`AppSidebar.tsx`)

Implementado con `<button>` + `useNavigate` (no `SidebarMenuButton asChild` — ese patrón rompía el layout flex al renderizarse como `<a>` con NavLink). Pipeline tiene submenú colapsable con `ChevronDown`. Cuando el sidebar está colapsado solo muestra íconos — el texto queda completamente oculto.

---

## Página — Pipeline Estadísticas (`/pipeline/estadisticas`)

Dashboard de análisis de calidad por etapa del pipeline. Usa **react-plotly.js** con la factory `createPlotlyComponent(Plotly)` y `plotly.js-dist-min` para no cargar Plotly completo.

### Filtro de fechas

- Inputs de fecha `desde` / `hasta` — filtran por fecha de la llamada (extraída del nombre del archivo)
- Botones de rango rápido: Hoy · 7 días · 30 días · Todo
- Los datos se cargan solo al presionar **Aplicar** (no al montar el componente)

### Secciones

| Sección | Contenido |
|---------|-----------|
| § 0 — Resumen global | Bar chart agrupado: distribución de audios por etapa y estado |
| § 1 — Descarga | Total de audios · histograma de duración |
| § 3 — Normalización | Correctos / solo errores |
| § 4 — Control de calidad de normalización | Conteos con % · umbrales desde Postgres · histogramas (score, SNR, RMS, duration ratio) · causas de invalido · scatter SNR vs score y duration ratio vs score |
| § 5 — Transcripción | Correctos / errores |
| § 6 — Control de calidad de transcripción | Conteos · roles identificados · pie de coherencia LLM · causas de invalido · histogramas (avg_logprob, total_words, low_score_ratio, speaker_dominance, score_llm, score_total) · scatter score determinista vs LLM |

Los umbrales de etapa 4 y 6 se leen desde `pipeline_params` en Postgres en cada carga (no están hardcodeados). Se muestran como métricas y como líneas verticales punteadas en los histogramas de score.

Los histogramas muestran `n · μ · σ` como anotación dentro del recuadro del gráfico.

---

## Página — Pipeline Monitoreo (`/pipeline/monitoreo`)

### Búsqueda individual de audio

- Campo de texto: acepta UUID o `nombre_archivo`
- Llama a `GET /pipeline/audio/{identificador}`
- El resultado persiste en `sessionStorage` con la clave `"audioResult"` — sobrevive navegación dentro de la misma pestaña, se limpia al recargar

**`ResultadoAudio`** — muestra:
- Grid con metadata del audio (nombre, cuenta, empresa, campaña, agente, fecha, duración)
- Tabla de ubicaciones MinIO por etapa con botones de reproducción y descarga
  - Solo muestra etapas que tienen archivos físicos: `descarga`, `normalizacion`, `transcripcion`, `analisis`
  - Las etapas de corrección (4, 6, 8) no crean archivos propios — no aparecen en la tabla
- Secciones colapsables por etapa con el JSON completo del JSONB

**Reproducción de audio:**
- Usa `<audio>` nativo del navegador
- URL construida con `getUrlStreamAudio(bucket, key)` → `GET /pipeline/audio/descargar?bucket=...&key=...&inline=true`
- Header `Content-Disposition: inline` permite reproducción sin forzar descarga

### Control de calidad — muestra aleatoria

Tres secciones colapsables por etapa del pipeline:

| Sección             | Estado      |
|---------------------|-------------|
| Normalización       | completo    |
| Transcripción       | pendiente   |
| Análisis            | pendiente   |

**Filtros disponibles (normalización):**
- Estado: `correcto`, `reprocesar`, `invalido`, `en_proceso`, `error`
- Cuenta: `G`, `M`, `B`
- Fecha (formato `DD/MM/YYYY` — como viene del campo `inicio` en Postgres)
- Hora inicio / Hora fin (formato `HH:MM`)
- N — cantidad de audios a samplear (default: 5)

La API ejecuta `ORDER BY RANDOM() LIMIT n`. La fecha y hora se parsean desde el campo `inicio` de Postgres (string `DD/MM/YYYY HH:MM:SS`) con `SUBSTRING` y `TO_DATE`.

---

## Página — Pipeline Configuración (`/pipeline/configuracion`)

Parámetros editables por etapa. Todas las etapas implementadas son colapsables.

### Etapa 3 — Normalización y Etapa 5 — Transcripción

Ambas usan el mismo patrón de **configuración de grupos**:

- **Selector de preset** — botones `GBM` · `GM | B` · `GB | M` · `G | MB` · `G | M | B` que definen qué máquinas comparten grupo de trabajo (y por ende se reparten los audios via `SKIP LOCKED`)
- **Un panel por grupo único** — muestra las máquinas del grupo en el encabezado y los parámetros compartidos
- Al guardar se escribe `{grupo, ...params}` en `pipeline_params` para cada cuenta (`normalizacion_G/M/B` o `transcripcion_G/M/B`)
- Al cargar detecta el preset activo comparando la estructura de grupos (no el nombre exacto)

**Campos de etapa 5 por grupo:**

| Campo | Descripción |
|---|---|
| Modelo | `large-v2`, `large-v3`, etc. |
| Compute type | `int8`, `int8_float16`, `float16`, `float32` |
| Batch size | 1 / 2 / 4 / 8 / 16 — fragmentos de audio en paralelo en GPU |
| Min / Max speakers | hablantes esperados para la diarización |
| Duración desde / hasta | filtro en segundos (null = sin límite) |
| Estados a procesar | checkboxes: `correcto`, `reprocesar`, etc. |

### Etapa 4 — Corrección de normalización

- **"Ejecutar scoring"** — `POST /pipeline/etapa/correccion_normalizacion/ejecutar`
- **"Limpiar audios"** — `POST /pipeline/etapa/correccion_normalizacion/limpiar` (corre `seleccionar_ganador.py`)
- **"Resetear resultados"** — `POST /pipeline/etapa/correccion_normalizacion/resetear`; tiene `confirm()` de confirmación porque es destructivo (borra todos los resultados de etapa 4 del JSONB)

---

## API client (`src/api/pipeline.js`)

El frontend nunca habla con Airflow directamente — todo pasa por la Pipeline API.

| Función                                    | Endpoint                                                        |
|--------------------------------------------|-----------------------------------------------------------------|
| `getEstadoPipeline()`                      | `GET /pipeline/estado`                                          |
| `getMetricas()`                            | `GET /pipeline/metricas`                                        |
| `getConversaciones(filtros)`               | `GET /pipeline/conversaciones`                                  |
| `getConversacion(id)`                      | `GET /pipeline/conversaciones/{id}`                             |
| `ejecutarPipeline()`                       | `POST /pipeline/ejecutar`                                       |
| `ejecutarEtapa(etapa, filtro, ids)`        | `POST /pipeline/etapa/{etapa}/ejecutar`                         |
| `pausarEtapa(etapa)`                       | `POST /pipeline/etapa/{etapa}/pausar`                           |
| `limpiarAudiosNormalizacion()`             | `POST /pipeline/etapa/correccion_normalizacion/limpiar`         |
| `resetearCorreccionNormalizacion()`        | `POST /pipeline/etapa/correccion_normalizacion/resetear`        |
| `limpiarTranscripciones()`                 | `POST /pipeline/etapa/correccion_transcripciones/limpiar`       |
| `resetearCorreccionTranscripciones()`      | `POST /pipeline/etapa/correccion_transcripciones/resetear`      |
| `getParametros(clave)`                     | `GET /pipeline/parametros/{clave}`                              |
| `actualizarParametros(clave, val)`         | `PATCH /pipeline/parametros/{clave}`                            |
| `getAudio(identificador)`                  | `GET /pipeline/audio/{identificador}`                           |
| `getUrlStreamAudio(bucket, key)`           | URL con `inline=true` para usar en `<audio src>`                |
| `getUrlDescargaAudio(bucket, key)`         | URL con `attachment` para descarga directa                      |
| `getAudiosAleatorios(filtros)`             | `GET /pipeline/audios/aleatorios`                               |
| `getEstadisticasGlobal(desde, hasta)`      | `GET /pipeline/estadisticas/global`                             |
| `getEstadisticasEtapa1(desde, hasta)`      | `GET /pipeline/estadisticas/etapa1`                             |
| `getEstadisticasEtapa3(desde, hasta)`      | `GET /pipeline/estadisticas/etapa3`                             |
| `getEstadisticasEtapa4(desde, hasta)`      | `GET /pipeline/estadisticas/etapa4`                             |
| `getEstadisticasEtapa5(desde, hasta)`      | `GET /pipeline/estadisticas/etapa5`                             |
| `getEstadisticasEtapa6(desde, hasta)`      | `GET /pipeline/estadisticas/etapa6`                             |
