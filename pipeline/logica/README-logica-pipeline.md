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
| 4 | 4-correcion-de-normalizacion/    | Quality gate: scorea el audio normalizado y clasifica                       | — (clasificación en Postgres, audio permanece en `audios-raw/`)          | completa  |
| 5 | 5-transcripcion-de-audios/       | WhisperX: transcripción + diarización en un solo paso                       | `transcripciones-raw/`                                                   | completa  |
| 6 | 6-correccion-de-transcripciones/ | Quality gate: scorea la transcripción (determinista + LLM) y clasifica      | `transcripciones-formateadas/`                                           | completa  |
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

### Notas de implementación — etapa 4

**Bug fixes aplicados:**

- **Query multi-grupo:** La query original filtraba `etapa_actual = 'normalizacion' AND estado_global = 'correcto'`, lo que hacía que solo se procesara el primer grupo (B). Después de evaluar el primer grupo, `etapa_actual` cambia a `correccion_normalizacion`, y los grupos G y M quedaban excluidos. Fix: `etapa_actual IN ('normalizacion', 'correccion_normalizacion') AND estado_global != 'en_proceso'`.

- **AttributeError en `metricas`:** `norm_entry.get("metricas", {})` devuelve `None` cuando la clave existe pero tiene valor null. Fix: `(norm_entry.get("metricas") or {}).get("duracion_seg", 0)`.

**Optimizaciones de performance:**

- Reemplazado `librosa.load()` por `soundfile.read()` — mucho más rápido para WAV sin resampleo:
  ```python
  audio, _ = sf.read(wav_path, dtype="float32", always_2d=False)
  if audio.ndim > 1:
      audio = audio.mean(axis=1)
  ```

- Vectorizado el cálculo de SNR con numpy (reemplazó list comprehension sobre frames):
  ```python
  frames_matrix = audio[:n_frames * frame_size].reshape(n_frames, frame_size)
  energias = np.sqrt(np.mean(frames_matrix ** 2, axis=1))
  ```

**Nota:** Las etapas de corrección (4, 6, 8) no crean archivos nuevos en MinIO — solo clasifican. Sus ubicaciones en el JSONB apuntan a los archivos existentes de la etapa anterior. Por esto, `correccion_normalizacion` no aparece como ubicación independiente en el dashboard.

---

### Flujo de estados — etapa 4

La etapa 4 tiene dos pasos:

**`correccion_normalizacion.py`** — corre automáticamente, evalúa cada (audio, grupo) pendiente:

| Momento | `etapa_actual` | `estado_global` |
|---|---|---|
| Entra a etapa 4 | `normalizacion` | `correcto` |
| Mientras se evalúa un grupo | `normalizacion` | `en_proceso` |
| Primer grupo evaluado | `correccion_normalizacion` | `correcto` \| `reprocesar` \| `invalido` |
| Grupos siguientes evaluados | `correccion_normalizacion` | score del último grupo evaluado |

Cada grupo evaluado agrega su clave al objeto `correccion_normalizacion` en el JSONB. El audio no se mueve ni duplica en MinIO — la `ubicacion` de cada grupo apunta al archivo original en `audios-raw/`.

**`seleccionar_ganador.py`** — se corre manualmente una vez que todos los grupos están evaluados:

| Momento | `etapa_actual` | `estado_global` |
|---|---|---|
| Antes de correr | `correccion_normalizacion` | último grupo evaluado |
| Después de correr | `correccion_normalizacion` | estado del grupo ganador |

Compara los scores de todos los grupos del audio, elige el de mayor score (priorizando `correcto` sobre `reprocesar`), borra de `audios-raw/` los audios de los grupos perdedores, y escribe `ganador` en el JSONB. El historial de todos los grupos queda en Postgres para trazabilidad.

### Notas de implementación — etapa 5

**WhisperX — versión y modelos:**

- Versión: `3.8.5` en las 3 PCs
- Modelo de diarización: `pyannote/speaker-diarization-community-1` (nuevo en 3.8.5 — no usar `speaker-diarization-3.1`)
- Import correcto: `from whisperx.diarize import DiarizationPipeline` (no desde `whisperx` directamente)
- Parámetro de autenticación HuggingFace: `token=` (no `use_auth_token=` ni `hf_token=`)

**VRAM por PC y modelo recomendado:**

| PC       | VRAM  | Modelo recomendado | compute_type |
|----------|-------|--------------------|--------------|
| Gaspar   | 8 GB  | `large-v2`         | `int8`       |
| Melchor  | 10 GB | `large-v3`         | `int8`       |
| Baltazar | 8 GB  | `large-v2`         | `int8`       |

Budget VRAM con large-v2 int8: ~2.5 GB (Whisper) + ~0.4 GB (wav2vec2 alignment) + ~1.5 GB (pyannote) = **~4.4 GB total** — entra cómodo en 8 GB.
`large-v3 + float16` crashea por OOM en tarjetas de 8 GB.

**Cache de modelos — redirección a disco no-C:\:**

C:\ suele no tener espacio. El script detecta el disco del venv automáticamente y redirige antes de cualquier import:
```python
_venv_drive = Path(sys.executable).drive  # "D:", "E:", "J:"
os.environ.setdefault("HF_HOME",    f"{_venv_drive}\\.cache\\huggingface")
os.environ.setdefault("TORCH_HOME", f"{_venv_drive}\\.cache\\torch")
```

**ffmpeg — PATH para el usuario `airflow-ssh`:**

WhisperX usa ffmpeg via subprocess. ffmpeg instalado con WinGet (`winget install Gyan.FFmpeg`) queda solo en el perfil del usuario que lo instaló — `airflow-ssh` no lo ve. El DAG de Airflow agrega explícitamente el bin de ffmpeg al PATH antes de ejecutar el script:
```
set "PATH=C:\Users\qjose\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin;%PATH%"
```
También es necesario dar permisos a `airflow-ssh` sobre esa carpeta:
```powershell
icacls "C:\Users\qjose\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe" /grant "airflow-ssh:(OI)(CI)RX" /T
```

**Estructura del JSONB — `transcripcion`:**

Array de intentos (mismo patrón que `normalizacion`). Múltiples grupos pueden transcribir el mismo audio con distintos parámetros en paralelo:
```json
"transcripcion": [
  {
    "estado": "correcto",
    "fecha": "2026-04-27T14:10:00Z",
    "cuenta": "G",
    "grupo": "GBM",
    "intento": 1,
    "params_usados": {
      "modelo": "large-v2",
      "compute_type": "int8",
      "min_speakers": 2,
      "max_speakers": 2,
      "duracion_desde": 30,
      "duracion_hasta": 35,
      "estados": ["reprocesar"]
    },
    "ubicacion": {
      "bucket": "modelado-de-scoring-wc",
      "key": "transcripciones-raw/2026-04-07/GBM/nombre.json"
    },
    "metricas": {
      "num_segmentos": 20,
      "num_hablantes_detectados": 2
    },
    "error": null
  }
]
```

**Estado — operativa en las 3 PCs (Gaspar, Melchor, Baltazar)**

Cada PC corre `transcribir_audios.py` con su propio `env-gpu-transcripciones`. Los parámetros (modelo, compute_type, batch_size, grupo, etc.) se configuran por PC desde el dashboard y se guardan en `pipeline_params` (`transcripcion_G/M/B`). Los grupos usan la misma nomenclatura que etapa 3 (`GBM`, `GM`, `G`, etc.) y el mismo mecanismo de `SELECT FOR UPDATE SKIP LOCKED` para repartir trabajo.

**Gestión de VRAM — estabilidad entre audios:**

El proceso carga los 3 modelos una sola vez (~4.4 GB) y los reutiliza en un loop. Para evitar fragmentación de VRAM que causa `0xC0000005 ACCESS_VIOLATION` (crash nativo de Windows/CUDA) después de ~14 audios:

- `batch_size=4` en `whisper_model.transcribe()` — reduce el pico de asignación por audio de ~2 GB a ~0.5 GB
- `gc.collect()` + `torch.cuda.empty_cache()` después de **cada** audio (éxito y todos los paths de error)

Sin estas dos medidas el proceso crashea irrecuperablemente y requiere reinicio de la máquina para liberar la VRAM corrompida.

**Input de la etapa 5:**

Lee el archivo ganador de la etapa 4: `etapas.correccion_normalizacion.ganador` → `etapas.correccion_normalizacion.<ganador>.ubicacion.key`. `seleccionar_ganador.py` debe haber corrido antes para que este campo esté seteado.

**Output MinIO:**
```
transcripciones-raw/YYYY-MM-DD/<grupo>/nombre.json
```

**Bug conocido — `set MITROL_CUENTA` en cmd.exe:**

En cmd.exe, `set VAR=G && cmd2` incluye el espacio antes de `&&` en el valor (`"G "`). Esto hace que `CLAVE_PARAMS = "transcripcion_G "` no encuentre nada en pipeline_params y use DEFAULTS silenciosamente. La forma correcta es siempre usar comillas: `set "VAR=G"`.

---

### Notas de implementación — etapa 6

La etapa 6 se divide en tres pasos, cada uno con su propio DAG:

**`correccion_determinista.py`** — evalúa métricas de transcripción sin GPU (solo gaspar):
- Valida umbrales duros: `avg_logprob`, `total_words`, `low_score_ratio`, `speaker_dominance`
- Calcula `score_determinista` como combinación ponderada de esas métricas
- Clasifica en `correcto` / `reprocesar` / `invalido`
- Log final incluye conteo de correcto / reprocesar / invalido / errores

**`correccion_llm.py`** — re-evalúa las transcripciones con vLLM (3 PCs GPU):
- Carga modelo una sola vez y procesa en loop
- Calcula `score_llm` (coherencia y roles) y `score_total = determinista * peso + llm * peso`
- Guarda en el JSONB: `score_determinista`, `score_llm`, `score_total`, `coherencia_llm`, `vendedor`, `cliente`, `metricas`
- Termina con `os._exit(0)` para evitar el leak de nanobind/xgrammar que hacía que Airflow marcara la tarea como fallida

**`seleccionar_ganador.py`** — elige el mejor intento por audio:
- Compara scores de todos los grupos procesados
- Borra de MinIO los JSONs de los grupos perdedores
- Escribe `ganador` en el JSONB

**Bug corregido — loop infinito:** Si un audio no tiene ganador en etapa 4, `restaurar_estado()` lo devolvía a `correcto` y la misma iteración lo volvía a encontrar. Fix: `omitir_ids: set` acumula IDs vistos en el run actual y los excluye de la query con `AND id NOT IN (...)`.

**Estructura del JSONB — `correccion_transcripciones`:**

Objeto con una clave por grupo evaluado más la clave `ganador`:
```json
"correccion_transcripciones": {
  "G": {
    "clasificacion":    "correcto",
    "score_determinista": 0.82,
    "score_llm":        0.91,
    "score_total":      0.87,
    "coherencia_llm":   "coherente",
    "vendedor":         "SPEAKER_0",
    "cliente":          "SPEAKER_1",
    "metricas": {
      "avg_logprob":       -0.18,
      "total_words":       312,
      "low_score_ratio":   0.04,
      "speaker_dominance": 0.61
    },
    "ubicacion": { "bucket": "modelado-de-scoring-wc", "key": "transcripciones-formateadas/2026-04-09/nombre.json" }
  },
  "ganador": "G"
}
```

Claves de pipeline_params: `correccion_transcripciones` (determinista) · `correccion_transcripciones_llm_G/M/B` (LLM por PC)

---

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
- **WhisperX 3.8.5** — transcripción + diarización en un único paso (faster-whisper + pyannote internamente)
- Modelo por defecto: `large-v2` (8 GB VRAM); `large-v3` solo para Melchor (10 GB)
- Diarización: `pyannote/speaker-diarization-community-1`

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
    "G": {
      "estado": "correcto",
      "fecha_inicio": "2026-04-13T08:02:00Z",
      "fecha_fin":    "2026-04-13T08:02:20Z",
      "ubicacion":    { "bucket": "modelado-de-scoring-wc", "key": "audios-raw/2026-04-13/G/uuid_G.wav" },
      "error": null,
      "score": 0.92
    },
    "M": {
      "estado": "reprocesar",
      "fecha_inicio": "2026-04-13T08:02:21Z",
      "fecha_fin":    "2026-04-13T08:02:38Z",
      "ubicacion":    { "bucket": "modelado-de-scoring-wc", "key": "audios-raw/2026-04-13/M/uuid_M.wav" },
      "error": null,
      "score": 0.61
    },
    "ganador": "G"
  },
  "transcripcion": [
    {
      "estado": "correcto",
      "fecha": "2026-04-13T08:06:00Z",
      "cuenta": "G",
      "grupo": "GBM",
      "intento": 1,
      "params_usados": {
        "modelo": "large-v2",
        "compute_type": "int8",
        "min_speakers": 2,
        "max_speakers": 2,
        "duracion_desde": null,
        "duracion_hasta": null,
        "estados": ["correcto"]
      },
      "ubicacion": { "bucket": "modelado-de-scoring-wc", "key": "transcripciones-raw/2026-04-13/GBM/uuid.json" },
      "metricas": { "num_segmentos": 18, "num_hablantes_detectados": 2 },
      "error": null
    }
  ],
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
│   └── YYYY-MM-DD/<grupo>/nombre_G.wav          # también input de 5-transcripcion-de-audios (clasificacion en Postgres)
│
├── transcripciones-raw/                         # output de 5-transcripcion-de-audios
│   └── YYYY-MM-DD/<grupo>/nombre.json           # <grupo> = GBM/GM/G/etc. según pipeline_params
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
    ├── 4-correcion-de-normalizacion/       # scorea la normalizacion y clasifica en correcto/reprocesar/invalido (clasificacion en Postgres)  [completa]
    │   ├── correccion_normalizacion.py     # script principal: evalúa cada (audio, grupo), guarda score por grupo en JSONB
    │   ├── seleccionar_ganador.py          # corre manualmente: elige grupo con mejor score, borra perdedores de audios-raw/
    │   └── config.py                       # umbrales duros, pesos del score y umbrales de clasificación
    ├── obtener-datos/                       # scripts de consulta usados por la Pipeline API
    │   ├── obtener_audio.py                # busca un audio por UUID o nombre_archivo, extrae ubicaciones MinIO por etapa
    │   └── descargar_audio.py              # cliente MinIO singleton: devuelve stream + tamaño para StreamingResponse
    ├── 5-transcripcion-de-audios/          # transcribe con WhisperX, output a MinIO (transcripciones-raw/YYYY-MM-DD/<grupo>/)  [funcional]
    │   ├── transcribir_audios.py           # script principal: SELECT FOR UPDATE SKIP LOCKED, WhisperX, upload a MinIO
    │   ├── config.py                       # parámetros por defecto (sobreescribibles desde pipeline_params)
    │   └── reporte-gpu2.md                 # hardware y entornos GPU de cada PC (venv-gpu-transcripciones y venv-gpu-analisis)
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
