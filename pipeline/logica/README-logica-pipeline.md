# Pipeline de Scoring de Conversaciones de Venta

Pipeline para procesar llamadas de venta en castellano: descarga los audios por scraping, los transcribe con identificación de hablantes y realiza varios analisis a partir de estas transcripciones. Cada etapa tiene un manejo de calidad para evaluar si la salida de cada una de las etapas puede continuar a traves del pipeline, debe ser reprocesado o bien descartado del analisis, asi nos aseguramos de que todos los datos almacenados finalmente tengan la mayor calidad posible.

---

## 1. Qué hace el sistema

```
Audio de llamada de venta
        │
        ▼
┌───────────────────────────────────────────────────────┐
│  Pipeline de 9 etapas (distribuido en 3 máquinas GPU) │
│                                                       │
│ descarga → normalizacion → correccion → transcripción │
│      → corrección → análisis LLM → corrección         │
│      → carga a DB                                     │
└───────────────────────────────────────────────────────┘
        │
        ▼
Equipo de ventas prioriza seguimiento
```

---

## 2. Pipeline — 9 etapas

Cada etapa vive en su propia carpeta.  
Cada audio pasa por todas las etapas en orden.  
Las etapas de corrección (4, 6, 8) actúan como *quality gates*: clasifican el output de la etapa anterior antes de continuar.

| # | Carpeta                          | Descripción                                                                 | Output en MinIO                                                          | Estado    |
|---|----------------------------------|-----------------------------------------------------------------------------|--------------------------------------------------------------------------|-----------|
| 1 | 1-descarga-de-audios/            | Scraping de Mitrol → sube WAV crudo a MinIO                                 | `audios/`                                                                | completa  |
| 2 | 2-creacion-de-registros/         | Crea la fila inicial en `audio_pipeline_jobs` en PostgreSQL                 | —                                                                        | completa  |
| 3 | 3-normalizacion-de-audios/       | Normalización con ffmpeg: *silence removal*, *loudnorm*                     | `audios-raw/`                                                            | completa  |
| 4 | 4-correcion-de-normalizacion/    | Quality gate: scorea el audio normalizado y clasifica; selección de ganador | `audios_procesados/{correcto\|reprocesar\|invalido}/`                    | completa  |
| 5 | 5-transcripcion-de-audios/       | WhisperX: transcripción + diarización en un solo paso                       | `transcripciones-raw/`                                                   | pendiente |
| 6 | 6-correccion-de-transcripciones/ | Quality gate: scorea la transcripción y clasifica                           | `transcripciones-procesadas/{correcto\|reprocesar\|invalido}/`           | pendiente |
| 7 | 7-analisis-de-transcripciones/   | Análisis con LLM en variantes independientes (A, B, …)                      | `analisis-raw/analisis-A/`, `analisis-raw/analisis-B/`                   | pendiente |
| 8 | 8-correccion-de-analisis/        | Quality gate: scorea cada análisis y clasifica (A y B por separado)         | `analisis-procesados/analisis-A/{correcto\|reprocesar\|invalido}/`       | pendiente |
| 9 | 9-carga-de-datos/                | Lee análisis correctos de MinIO → inserta en MongoDB                        | —                                                                        | pendiente |

---

### Estados posibles

**Etapas de corrección (4, 6, 8):**  
`correcto` · `reprocesar` · `invalido`

**Etapas de procesamiento (1, 3, 5, 7, 9):**  
`correcto` · `error`

**Estado global del job:**  
`pendiente` · `en_proceso` · `correcto` · `error` · `reprocesar` · `invalido`

### Flujo de estados — etapa 4

| Momento | `etapa_actual` | `estado_global` |
|---|---|---|
| Entra a etapa 4 | `normalizacion` | `correcto` |
| Mientras se evalúa | `normalizacion` | `en_proceso` |
| Primer grupo evaluado | `correccion_normalizacion` | `correcto` |
| Todos los grupos `reprocesar` | `normalizacion` | `reprocesar` |
| Audio irrecuperable | `correccion_normalizacion` | `invalido` |
| Ganador seleccionado | `correccion_normalizacion` | `correcto` + `grupo_ganador` en JSONB |

`seleccionar_ganador.py` actúa sobre audios con `etapa_actual='correccion_normalizacion'` y sin `grupo_ganador` en el JSONB. Elimina de MinIO los audios descartados en `audios_procesados/` y en `audios-raw/`, dejando una sola versión por audio.

### Nota sobre los tipos de análisis

Las etapas 7 y 8 están diseñadas para ejecutar múltiples tipos de análisis en paralelo sobre la misma transcripción. Actualmente existen `analisis-A` y `analisis-B`, que representan dos enfoques distintos para determinar cuál produce resultados de mayor calidad.

Agregar un nuevo tipo de análisis en el futuro no requiere modificar nada de lo existente. Solo implica:
- Nueva carpeta `7-analisis-de-transcripciones/analisis-X/` con su `config.py`
- Nueva carpeta `8-correccion-de-analisis/analisis-X/`
- Nueva subclave `analisis_X` en el JSONB (dentro de `analisis` y `correccion_analisis`)
- Nuevas filas `analisis_X` y `correccion_analisis_X` en la tabla `pipeline_params`
- Nuevos prefijos en MinIO: `analisis-raw/analisis-X/` y `analisis-procesados/analisis-X/`

---

## 3. Stack tecnológico

### Procesamiento de audio
- **ffmpeg** — normalización (silenceremove, loudnorm EBU R128, highpass)
- **subprocess** — interfaz Python → ffmpeg

### Audio ML
- **WhisperX** — transcripción + diarización en un único paso (faster-whisper + pyannote internamente)
- Modelo: `whisperx-large-v3`

### LLM local
- **vLLM ≥ 0.6.0** — servidor con API OpenAI-compatible (`/v1/chat/completions`)
- Modelos candidatos: Qwen2.5-7B-Instruct, Llama-3.1-8B-Instruct, Mistral-7B-Instruct
- **Guided decoding** con schema Pydantic → output JSON estructurado garantizado
- Cliente: `openai` SDK apuntando a `http://localhost:8000/v1`
- No se usa Claude API en producción — todo el inference es local

### Storage
- **MinIO** (S3-compatible) — archivos de audio y JSONs de resultados intermedios
- **PostgreSQL** — estado y metadata de cada conversación (tabla `audio_pipeline_jobs`)
- **MongoDB** — destino final de los análisis (etapa 9)
- **boto3** — cliente S3 para leer/escribir MinIO desde cualquier etapa

---

## 4. Trazabilidad — tabla `audio_pipeline_jobs`

Cada audio tiene una fila en `audio_pipeline_jobs` (PostgreSQL) que actúa como su "pasaporte" a través del pipeline. Esto permite:
- Ejecutar cualquier etapa de forma individual sin Airflow
- Reanudar el procesamiento desde cualquier punto
- Consultar el estado del pipeline en tiempo real desde el dashboard
- Detectar audios bloqueados o en reprocesamiento infinito
- Modificar los parámetros de cada etapa desde el dashboard sin tocar el código

El DDL ejecutable está en `2-creacion-de-registros/creacion_de_tablas_postgres.py`.  
A continuación se muestra la estructura de referencia:

```sql
CREATE TABLE audio_pipeline_jobs (
    id                         UUID         PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identificación del audio
    nombre_archivo             VARCHAR(200) UNIQUE,     -- base sin sufijo _G/_M/_B ni .wav
    id_interaccion             VARCHAR(100),
    url_fuente                 TEXT,                    -- ruta MinIO del WAV
    cuenta                     VARCHAR(1),              -- G, M o B

    -- Metadata de la llamada (poblada en etapa 2 desde los CSV de Mitrol)
    numero_telefono            VARCHAR(20),
    inicio                     VARCHAR(30),             -- timestamp tal como viene de Mitrol
    agente                     VARCHAR(100),
    extension                  VARCHAR(20),
    empresa                    VARCHAR(100),
    campania                   VARCHAR(100),
    tipificacion               VARCHAR(100),
    clase_tipificacion         VARCHAR(100),

    -- Duraciones en segundos (convertidas desde HH:MM:SS)
    duracion_audio_seg         INTEGER,
    duracion_conversacion_seg  INTEGER,

    -- Control de flujo
    estado_global              VARCHAR(20)  NOT NULL DEFAULT 'correcto'
                                   CHECK (estado_global IN (
                                       'pendiente', 'en_proceso', 'correcto',
                                       'error', 'reprocesar', 'invalido'
                                   )),
    etapa_actual               VARCHAR(40)  NOT NULL DEFAULT 'descarga',

    created_at                 TIMESTAMPTZ  NOT NULL DEFAULT now(),
    fecha_ultima_actualizacion TIMESTAMPTZ  NOT NULL DEFAULT now(),

    etapas                     JSONB        NOT NULL DEFAULT '{}'::jsonb
);
```

### Estructura del campo `etapas` (JSONB)

Solo se agrega cada clave cuando la etapa comienza. Las etapas no iniciadas no existen en el objeto.

```json
{
  "descarga": {
    "estado": "correcto",
    "fecha_inicio": "2026-04-13T08:00:00Z",
    "fecha_fin":    "2026-04-13T08:00:45Z",
    "ubicacion":    { "bucket": "modelado-de-scoring-wc", "key": "audios/uuid.wav" },
    "intentos": 1,
    "error": null
  },
  "normalizacion": {
    "estado": "correcto",
    "fecha_inicio": "2026-04-13T08:01:00Z",
    "fecha_fin":    "2026-04-13T08:01:50Z",
    "ubicacion":    { "bucket": "modelado-de-scoring-wc", "key": "audios-raw/uuid.wav" },
    "intentos": 1,
    "error": null
  },
  "correccion_normalizacion": {
    "estado": "correcto",
    "fecha_inicio": "2026-04-13T08:02:00Z",
    "fecha_fin":    "2026-04-13T08:02:20Z",
    "ubicacion":    { "bucket": "modelado-de-scoring-wc", "key": "audios_procesados/correcto/uuid.wav" },
    "intentos": 1,
    "error": null,
    "score": 0.92
  },
  "transcripcion": {
    "estado": "correcto",
    "fecha_inicio": "2026-04-13T08:02:30Z",
    "fecha_fin":    "2026-04-13T08:06:00Z",
    "ubicacion":    { "bucket": "modelado-de-scoring-wc", "key": "transcripciones-raw/uuid.json" },
    "intentos": 1,
    "error": null,
    "modelo": "whisperx-large-v3",
    "num_hablantes": 2
  },
  "correccion_transcripciones": {
    "estado": "correcto",
    "fecha_inicio": "2026-04-13T08:06:10Z",
    "fecha_fin":    "2026-04-13T08:06:30Z",
    "ubicacion":    { "bucket": "modelado-de-scoring-wc", "key": "transcripciones-procesadas/correcto/uuid.json" },
    "intentos": 1,
    "error": null,
    "score": 0.88,
    "num_hablantes": 2
  },
  "analisis": {
    "analisis_A": {
      "estado": "correcto",
      "fecha_inicio": "2026-04-13T08:07:00Z",
      "fecha_fin":    "2026-04-13T08:08:30Z",
      "ubicacion":    { "bucket": "modelado-de-scoring-wc", "key": "analisis-raw/analisis-A/uuid.json" },
      "intentos": 1,
      "error": null,
      "modelo": "Qwen2.5-7B-Instruct"
    },
    "analisis_B": {
      "estado": "correcto",
      "fecha_inicio": "2026-04-13T08:07:00Z",
      "fecha_fin":    "2026-04-13T08:08:45Z",
      "ubicacion":    { "bucket": "modelado-de-scoring-wc", "key": "analisis-raw/analisis-B/uuid.json" },
      "intentos": 1,
      "error": null,
      "modelo": "Qwen2.5-7B-Instruct"
    }
  },
  "correccion_analisis": {
    "analisis_A": {
      "estado": "correcto",
      "fecha_inicio": "2026-04-13T08:09:00Z",
      "fecha_fin":    "2026-04-13T08:09:20Z",
      "ubicacion":    { "bucket": "modelado-de-scoring-wc", "key": "analisis-procesados/analisis-A/correcto/uuid.json" },
      "intentos": 1,
      "error": null,
      "score_lead": 78,
      "confidence_score": 0.91
    },
    "analisis_B": {
      "estado": "correcto",
      "fecha_inicio": "2026-04-13T08:09:00Z",
      "fecha_fin":    "2026-04-13T08:09:25Z",
      "ubicacion":    { "bucket": "modelado-de-scoring-wc", "key": "analisis-procesados/analisis-B/correcto/uuid.json" },
      "intentos": 1,
      "error": null,
      "score_lead": 75,
      "confidence_score": 0.88
    }
  },
  "carga_datos": {
    "estado": "correcto",
    "fecha_inicio": "2026-04-13T08:10:00Z",
    "fecha_fin":    "2026-04-13T08:10:05Z",
    "intentos": 1,
    "error": null
  }
}
```

---

## 5. Storage en MinIO

MinIO corre en `melchor` (192.168.9.195:9001). Bucket: `modelado-de-scoring-wc`. Todas las máquinas leen y escriben del mismo bucket vía boto3. Cada etapa de normalizacion, transcripcion y analisis tiene una etapa posterior de calidad donde se determina el score del procesamiento y se clasifica como correcto en el caso de que este apto para la siguiente etapa, reprocesar en caso de que se necesite un nuevo analisis variando los parametros iniciales o invalido en caso de que el archivo este corrupto o no cumpla con las condiciones para pasar a la proxima etapa a pesar de los reintentos de reprocesamiento, en esos casos los archivos se auditan manualmente.

Todas las carpetas usan subcarpetas `YYYY-MM-DD/` con la fecha del propio audio (extraída del nombre del archivo), no la fecha de ejecución.

> **Extensión a grupos:** La etapa 3 agrega un nivel `<grupo>/` dentro de la fecha (`YYYY-MM-DD/<grupo>/`) para separar outputs de distintas configuraciones de parámetros procesadas en paralelo. Las etapas siguientes no usan grupos por ahora, pero la estructura `YYYY-MM-DD/` deja el hueco para incorporarlo sin romper nada — bastaría agregar `YYYY-MM-DD/<grupo>/` si en el futuro se quiere comparar, por ejemplo, dos configuraciones de WhisperX o dos prompts de LLM sobre los mismos audios.

```
modelado-de-scoring-wc/
│
├── audios/                                      # output de 1-descarga-de-audios
│   └── YYYY-MM-DD/nombre.wav
│
├── audios-raw/                                  # output de 3-normalizacion-de-audios
│   └── YYYY-MM-DD/<grupo>/nombre_G.wav
│
├── audios_procesados/                           # output de 4-correcion-de-normalizacion
│   ├── correcto/YYYY-MM-DD/nombre.wav           # input de 5-transcripcion-de-audios
│   ├── reprocesar/YYYY-MM-DD/nombre.wav         # input de 3-normalizacion-de-audios
│   └── invalido/YYYY-MM-DD/nombre.wav
│
├── transcripciones-raw/                         # output de 5-transcripcion-de-audios
│   └── YYYY-MM-DD/nombre.json
│
├── transcripciones-procesadas/                  # output de 6-correccion-de-transcripciones
│   ├── correcto/YYYY-MM-DD/nombre.json          # input de 7-analisis-de-transcripciones
│   ├── reprocesar/YYYY-MM-DD/nombre.json        # input de 5-transcripcion-de-audios
│   └── invalido/YYYY-MM-DD/nombre.json
│
├── analisis-raw/                                # output de 7-analisis-de-transcripciones
│   ├── analisis-A/YYYY-MM-DD/nombre.json
│   └── analisis-B/YYYY-MM-DD/nombre.json
│
└── analisis-procesados/                         # output de 8-correccion-de-analisis
    ├── analisis-A/
    │   ├── correcto/YYYY-MM-DD/nombre.json      # input de 9-carga-de-datos
    │   ├── reprocesar/YYYY-MM-DD/nombre.json    # input de 7-analisis-de-transcripciones
    │   └── invalido/YYYY-MM-DD/nombre.json
    └── analisis-B/
        ├── correcto/YYYY-MM-DD/nombre.json
        ├── reprocesar/YYYY-MM-DD/nombre.json
        └── invalido/YYYY-MM-DD/nombre.json
```

---

## 6. Estructura del repositorio

```
pipeline/logica/
    ├── 1-descarga-de-audios/               # descarga audios desde Mitrol y los sube a MinIO (audios/)  [completa]
    │   ├── scraping_mitrol.py              # script principal: login, filtros, paginación, upload a MinIO + CSV de metadatos
    │   ├── run_standalone.py              # modo interactivo para ejecutar manualmente desde la PC
    │   └── config.py                      # parámetros por defecto (sobreescribibles desde pipeline_params)
    ├── 2-creacion-de-registros/            # lista MinIO y crea filas en audio_pipeline_jobs para audios nuevos  [completa]
    │   ├── creacion_de_tablas_postgres.py  # DDL ejecutable: crea audio_pipeline_jobs y pipeline_params
    │   ├── creacion_de_registros.py        # lee CSVs de MinIO e inserta filas en audio_pipeline_jobs
    │   └── DDL.txt                         # referencia rapida del esquema y estructura del JSONB
    ├── 3-normalizacion-de-audios/          # normaliza audios con ffmpeg, output a MinIO (audios-raw/YYYY-MM-DD/<grupo>/)  [completa]
    │   ├── preprocesar_audios.py           # script principal: SELECT FOR UPDATE SKIP LOCKED, ffmpeg, upload a MinIO
    │   └── config.py                      # parámetros por defecto (sobreescribibles desde pipeline_params)
    ├── 4-correcion-de-normalizacion/       # scorea la normalizacion y clasifica en correcto/reprocesar/invalido (audios_procesados/)  [completa]
    │   ├── correccion_normalizacion.py     # script principal: descarga WAV, calcula SNR/RMS/duración, clasifica y sube a audios_procesados/
    │   ├── seleccionar_ganador.py          # corre manualmente: elige grupo con mejor score por audio y elimina duplicados de MinIO
    │   └── config.py                       # umbrales duros, pesos del score y umbrales de clasificación
    ├── 5-transcripcion-de-audios/          # transcribe con WhisperX, output a MinIO (transcripciones-raw/)
    │   └── config.py
    ├── 6-correccion-de-transcripciones/    # scorea la transcripcion y clasifica en correcto/reprocesar/invalido (transcripciones-procesadas/)
    │   └── config.py
    ├── 7-analisis-de-transcripciones/      # analiza la transcripcion con LLM, hay dos tipos de analisis independientes
    │   ├── analisis-A/                     # primer tipo de analisis, output a MinIO (analisis-raw/analisis-A/)
    │   │   └── config.py
    │   └── analisis-B/                     # segundo tipo de analisis, output a MinIO (analisis-raw/analisis-B/)
    │       └── config.py
    ├── 8-correccion-de-analisis/           # scorea cada analisis y clasifica en correcto/reprocesar/invalido (analisis-procesados/)
    │   ├── analisis-A/
    │   │   └── config.py
    │   └── analisis-B/
    │       └── config.py
    └── 9-carga-de-datos/                   # lee los analisis correctos de MinIO y los carga en MongoDB
```

---
