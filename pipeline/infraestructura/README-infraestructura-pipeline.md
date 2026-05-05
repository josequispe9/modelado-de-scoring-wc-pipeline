# Infraestructura del Pipeline

Todo lo necesario para orquestar y controlar la ejecución del pipeline: API del dashboard, DAGs de Airflow, y configuración de workers.

---

## Estructura

```
infraestructura/
├── api/           # FastAPI que expone el pipeline al dashboard (puerto 8001)
├── airflow/       # docker-compose, DAGs, init-db.sql e inicialización de BD
└── workers/       # scripts de deploy SSH a melchor y pc-franco (pendiente)
```

Redis corre como servicio dentro del `docker-compose.yml` de `airflow/` — no tiene carpeta propia.

---

## Arquitectura distribuida

Tres máquinas Windows en LAN. Airflow corre en gaspar y distribuye trabajo a las otras PCs.

```
┌─────────────────────────────────────────────┐
│         gaspar  —  192.168.9.115            │
│                                             │
│  Airflow Scheduler  (decide qué ejecutar)   │
│  Airflow Webserver  (UI en :8080)           │
│  Redis              (broker Celery)         │
│  PostgreSQL         (dos bases de datos:)   │
│    · airflow   — metadata interna Airflow   │
│    · scoring   — audio_pipeline_jobs        │
│                  pipeline_params            │
│  Pipeline API       (dashboard en :8001)    │
│  Airflow Worker     (también procesa)       │
└───────────────────┬─────────────────────────┘
                    │  SSHOperator (etapa 1)
                    │  CeleryExecutor (etapas 2–9)
         ┌──────────┼──────────┐
         ▼          ▼          ▼
    gaspar       melchor    pc-franco (Baltazar)
    .9.115       .9.195      .9.62
    Cuenta G     Cuenta M    Cuenta B
         │          │          │
         └──────────┼──────────┘
                    ▼
             ┌────────────┐
             │   MinIO    │  Storage compartido
             │  .9.195    │  bucket: modelado-de-scoring-wc
             │:9000/:9001 │  accesible desde los 3 workers
             └────────────┘
```

### Máquinas

| Rol            | Hostname       | IP            | Usuario SSH   | Password SSH |
|----------------|----------------|---------------|---------------|--------------|
| Principal      | gaspar         | 192.168.9.115 | `airflow-ssh` | `1234`       |
| Worker + MinIO | melchor        | 192.168.9.195 | `juan-t3`     | `1234`       |
| Worker         | pc-franco (Baltazar) | 192.168.9.62  | `bases`  | `ruleta`     |

Todas las máquinas corren **Windows** con OpenSSH Server habilitado.

> **Nota gaspar — usuario `airflow-ssh`:** La cuenta principal `qjose` usa PIN de Windows (incompatible con SSH por contraseña) y está vinculada a una cuenta Microsoft (no se puede cambiar con `net user`). Por eso se usa un usuario local dedicado para SSH. Para recrearlo en gaspar:
> ```powershell
> net user airflow-ssh 1234 /add
> # No agregar al grupo Administradores — el sshd_config de Windows fuerza
> # clave SSH para ese grupo, bloqueando la autenticación por contraseña.
>
> # Dar acceso al proyecto y al Python del venv
> icacls "C:\Users\qjose\Desktop\modelado de scoring WC" /grant "airflow-ssh:(OI)(CI)RX" /T
> icacls "C:\Users\qjose\AppData\Local\Programs\Python" /grant "airflow-ssh:(OI)(CI)RX" /T
> ```

### Rutas del proyecto en cada máquina

| Máquina   | Ruta                                              |
|-----------|---------------------------------------------------|
| gaspar    | `C:\Users\qjose\Desktop\modelado de scoring WC`   |
| melchor   | `C:\Users\JUAN-T3\Desktop\modelado de scoring WC` |
| pc-franco | `C:\Users\Bases\Desktop\modelado de scoring WC`   |

### Servicios

| Servicio     | URL                        | Usuario    | Password           |
|--------------|----------------------------|------------|--------------------|
| Airflow UI   | http://192.168.9.115:8080  | admin      | admin123           |
| Redis        | redis://192.168.9.115:6379 | —          | —                  |
| MinIO UI     | http://192.168.9.195:9002  | minioadmin | minioadmin         |
| MinIO API    | http://192.168.9.195:9001  | minioadmin | minioadmin         |
| Pipeline API | http://192.168.9.115:8001  | —          | —                  |

---

## Cómo levantar el sistema

### Pipeline API (puerto 8001)

Corre en Windows (PowerShell) con el venv de `api/`:

```powershell
cd "pipeline\infraestructura"

# Primera vez
python -m venv api\venv
api\venv\Scripts\activate
pip install -r api\requirements.txt

# Levantar (lee .env.tuberia de la raíz del proyecto automáticamente)
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload
```

Las variables que necesita el `.env.tuberia` (en la raíz del proyecto):
```
SCORING_DB_URL=postgresql://scoring:scoring@localhost:5432/scoring
AIRFLOW_BASE_URL=http://localhost:8080/api/v1
AIRFLOW_USER=admin
AIRFLOW_PASSWORD=admin123
MINIO_ENDPOINT=192.168.9.195:9001
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
```

> **Bug — `set VAR=G && cmd` en cmd.exe:** El espacio antes de `&&` se incluye en el valor (`"G "`), haciendo que `CLAVE_PARAMS = "transcripcion_G "` no encuentre nada en pipeline_params y use DEFAULTS silenciosamente. Siempre usar la forma con comillas: `set "MITROL_CUENTA=G"`. Este fix está aplicado en los DAGs de descarga, normalización y transcripción.
>
> **Orden crítico en `main.py`:** `load_dotenv` debe llamarse **antes** de los imports de routers. Los módulos como `airflow_client.py` leen `os.environ` en el momento del import — si `load_dotenv` va después, las variables llegan vacías y Airflow devuelve 401.
>
> **Patrón `_auth()`:** Las credenciales de Airflow se leen en cada llamada (`_auth()` función) en vez de una constante de módulo. Esto evita que un reinicio de uvicorn quede con credenciales stale.
>
> La Pipeline API requiere que Airflow tenga habilitado el backend de autenticación básica.
> Está configurado en el `docker-compose.yml` con `AIRFLOW__API__AUTH_BACKENDS: airflow.api.auth.backend.basic_auth`.

**Resetear password de Airflow** (si el contenedor fue recreado y el password cambió):
```bash
docker exec airflow-airflow-webserver-1 airflow users reset-password --username admin --password admin123
```

---

### Primera vez

```bash
# 1. Completar AIRFLOW__CORE__FERNET_KEY en el .env.tuberia raíz del proyecto
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Pegar el resultado en .env.tuberia como AIRFLOW__CORE__FERNET_KEY

# 2. Crear las carpetas que Airflow necesita con permisos correctos
cd pipeline/infraestructura/airflow/
mkdir -p dags logs plugins

# 3. Inicializar la base de datos de Airflow y crear el usuario admin
docker compose up airflow-init

# 4. Levantar todo
docker compose up -d
```

### Operación diaria

```bash
# Levantar
cd pipeline/infraestructura/airflow/ && docker compose up -d

# Detener
docker compose down

# Ver logs de un servicio
docker compose logs -f airflow-scheduler
```

---

## Airflow

Versión: **2.10.3** con **CeleryExecutor** + Redis.
El scheduler encola tareas en Redis; el worker local las ejecuta. Todas las etapas usan SSHOperator para ejecutar scripts en las 3 PCs.

Un solo Airflow compartido con el proyecto scraping. Los DAGs del pipeline usan el prefijo `pipeline_*`.

Los DAGs viven en `pipeline/infraestructura/airflow/dags/` y se montan como volumen en todos los contenedores Airflow.

### Etapa 1 — Descarga (SSHOperator)

La etapa 1 usa Selenium con Chrome visible para auditar el funcionamiento. Como el worker de Airflow corre en Docker (sin acceso a pantalla), la descarga **no** corre dentro del contenedor: el DAG usa `SSHOperator` para lanzar el script Python directamente en el Windows nativo de cada máquina.

```
airflow-worker (Docker, gaspar)
    ├── SSHOperator → ssh gaspar    → python scraping_mitrol.py  [cuenta G]
    ├── SSHOperator → ssh melchor   → python scraping_mitrol.py  [cuenta M]
    └── SSHOperator → ssh pc-franco → python scraping_mitrol.py  [cuenta B]
```

Las tres tareas corren en **paralelo**. Cada máquina usa su propia cuenta Mitrol y sus propios parámetros (`descarga_G`, `descarga_M`, `descarga_B` en `pipeline_params`).

### Etapa 2 — Creación de registros (SSHOperator, solo gaspar)

Lista todos los WAV en MinIO (`audios/`) y lee los CSV de metadatos generados por la etapa 1 (`audios/YYYY-MM-DD/metadatos_<CUENTA>_<timestamp>.csv`). Por cada audio sin fila en `audio_pipeline_jobs`, inserta un registro con toda la metadata. Idempotente.

```
airflow-worker (Docker, gaspar)
    └── SSHOperator → ssh gaspar → python creacion_de_registros.py
```

### Etapa 3 — Normalización (SSHOperator, 3 PCs en paralelo)

Normaliza los audios con ffmpeg (silence removal, loudnorm, filtros opcionales). Cada PC lee su propia clave en `pipeline_params` (`normalizacion_G/M/B`) para obtener sus params y su grupo. Las PCs del mismo grupo se reparten el trabajo a demanda usando `SELECT FOR UPDATE SKIP LOCKED` — la primera en tomar un audio lo procesa, las demás lo saltean. PCs de grupos distintos pueden procesar el mismo audio con params diferentes, generando outputs comparables.

```
audios-raw/YYYY-MM-DD/<grupo>/nombre_archivo_<CUENTA>.wav
```

```
airflow-worker (Docker, gaspar)
    ├── SSHOperator → ssh gaspar    → python preprocesar_audios.py  [cuenta G]
    ├── SSHOperator → ssh melchor   → python preprocesar_audios.py  [cuenta M]
    └── SSHOperator → ssh pc-franco → python preprocesar_audios.py  [cuenta B]
```

Claves de pipeline_params: `normalizacion_G` · `normalizacion_M` · `normalizacion_B`  
Campos del JSONB: `grupo`, `cuenta`, `params_usados`, `ubicacion`, `estado`, `intento`, `error`

### Etapa 4 — Corrección de normalización (SSHOperator, solo gaspar)

Scorea cada audio normalizado usando soundfile + numpy (SNR, RMS, duración ratio). Clasifica en `correcto` / `reprocesar` / `invalido`. La clasificación vive solo en Postgres — no se crean archivos nuevos en MinIO. Corre solo en gaspar — no requiere GPU.

```
airflow-worker (Docker, gaspar)
    └── SSHOperator → ssh gaspar → python correccion_normalizacion.py
```

Clave de pipeline_params: `correccion_normalizacion`  
Campos del JSONB: `grupo`, `score`, `metricas` (snr, rms_dbfs, duracion_seg, duracion_ratio), `ubicacion`, `estado`, `intento`, `error`

**Selección de ganador** — script manual (no DAG), disparado desde el dashboard (botón "Limpiar audios") o PowerShell:
```powershell
pipeline\venv\Scripts\python.exe pipeline\logica\4-correcion-de-normalizacion\seleccionar_ganador.py
```
Elige el grupo con mejor score por audio, borra de MinIO los audios de los grupos perdedores. El ganador queda en `audios-raw/` en su ubicación original.

**Resetear resultados** — disponible desde el dashboard (botón "Resetear resultados") o via API:
```bash
curl -X POST http://192.168.9.115:8001/pipeline/etapa/correccion_normalizacion/resetear
```
Borra la clave `correccion_normalizacion` del JSONB y devuelve los audios a `etapa_actual='normalizacion'` para poder volver a correr la etapa con nuevos parámetros.

### Etapa 5 — Transcripción (SSHOperator, 3 PCs en paralelo)

Transcribe los audios ganadores de la etapa 4 con WhisperX (transcripción + alineación + diarización). Cada PC lee su clave en `pipeline_params` (`transcripcion_G/M/B`) y usa su propio venv GPU (`env-gpu-transcripciones`). Las PCs del mismo grupo se reparten el trabajo a demanda con `SELECT FOR UPDATE SKIP LOCKED`.

```
airflow-worker (Docker, gaspar)
    ├── SSHOperator → ssh gaspar    → python transcribir_audios.py  [cuenta G, venv D:\env-gpu-transcripciones]
    ├── SSHOperator → ssh melchor   → python transcribir_audios.py  [cuenta M, venv E:\env-gpu-transcripciones]
    └── SSHOperator → ssh pc-franco → python transcribir_audios.py  [cuenta B, venv J:\env-gpu-transcripciones]
```

Claves de pipeline_params: `transcripcion_G` · `transcripcion_M` · `transcripcion_B`  
Campos del JSONB: array de intentos con `grupo`, `cuenta`, `modelo`, `params_usados`, `ubicacion`, `metricas` (num_segmentos, num_hablantes), `estado`, `intento`, `error`

Grupos usan la misma nomenclatura que etapa 3: `GBM`, `GM`, `GB`, `G`, `MB`, `M`, `B`. Seleccionables desde el dashboard con los mismos presets.

**Modelos por PC:**

| PC       | VRAM  | Modelo     | compute_type |
|----------|-------|------------|--------------|
| Gaspar   | 8 GB  | `large-v2` | `int8`       |
| Melchor  | 10 GB | `large-v3` | `int8`       |
| Baltazar | 8 GB  | `large-v2` | `int8`       |

**Prerrequisito — ffmpeg en PATH para `airflow-ssh`:**

WhisperX llama a ffmpeg via subprocess. ffmpeg instalado con WinGet solo queda en el perfil del usuario que lo instaló. El DAG agrega el bin al PATH explícitamente y `airflow-ssh` necesita permisos:
```powershell
icacls "C:\Users\qjose\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe" /grant "airflow-ssh:(OI)(CI)RX" /T
```

**Estado — operativa en las 3 PCs**

Gaspar, Melchor y Baltazar corren el script en paralelo. Requiere `env-gpu-transcripciones` instalado en cada PC (ver `pipeline/logica/5-transcripcion-de-audios/reporte-gpu2.md`) y el script `transcribir_audios.py` + `config.py` en `pipeline\logica\5-transcripcion-de-audios\` de cada máquina.

> **Nota Baltazar SSH:** la conexión `ssh_pc_franco` usa usuario `bases` con password `ruleta`. Confirmar en Airflow UI → Admin → Connections que el password coincida con el usuario Windows de Baltazar — ya resuelto.

**Prerrequisito — ganador seteado:**

`seleccionar_ganador.py` debe haber corrido para que los audios tengan `etapas.correccion_normalizacion.ganador` seteado. Si es null, el script skipea el audio sin marcarlo como error.

**Resetear resultados de transcripción:**
```sql
UPDATE audio_pipeline_jobs
SET etapas        = etapas - 'transcripcion',
    etapa_actual  = 'correccion_normalizacion',
    estado_global = 'reprocesar'
WHERE etapa_actual  = 'transcripcion'
  AND estado_global = 'error';
```

**Estabilidad VRAM:** `batch_size=4` en WhisperX + `gc.collect()` y `torch.cuda.empty_cache()` después de cada audio (éxito y error). Sin esto el proceso crashea con `0xC0000005` tras ~14 audios y requiere reinicio de la máquina.

**DAG:** `pipeline/infraestructura/airflow/dags/pipeline_transcripcion.py`  
`cmd_timeout=14400` (4 horas — transcribir es lento)

---

### Etapa 6 — Corrección de transcripciones (SSHOperator, 3 pasos)

Tres DAGs separados, cada uno disparable desde el dashboard de forma independiente:

**`pipeline_correccion_determinista`** — solo gaspar, sin GPU:
```
airflow-worker (Docker, gaspar)
    └── SSHOperator → ssh gaspar → python correccion_determinista.py
```
Evalúa avg_logprob, total_words, low_score_ratio y speaker_dominance. Clasifica en `correcto` / `reprocesar` / `invalido`. Clave: `correccion_transcripciones`. `cmd_timeout=1800`.

**`pipeline_correccion_llm`** — 3 PCs en paralelo, requiere GPU:
```
airflow-worker (Docker, gaspar)
    ├── SSHOperator → ssh gaspar    → python correccion_llm.py  [cuenta G, venv D:\env-gpu-analisis]
    ├── SSHOperator → ssh melchor   → python correccion_llm.py  [cuenta M, venv E:\env-gpu-analisis]
    └── SSHOperator → ssh pc-franco → python correccion_llm.py  [cuenta B, venv J:\env-gpu-analisis]
```
Calcula score_llm (coherencia + roles) y score_total. Guarda score_determinista, score_llm, score_total, coherencia_llm, vendedor, cliente y metricas en el JSONB. Termina con `os._exit(0)` para evitar el leak de nanobind/xgrammar que marcaba la tarea como fallida en Airflow. Claves: `correccion_transcripciones_llm_G/M/B`. `cmd_timeout=3600`.

**`pipeline_seleccionar_ganador_transcripciones`** — solo gaspar:
```
airflow-worker (Docker, gaspar)
    └── SSHOperator → ssh gaspar → python seleccionar_ganador.py  [etapa 6]
```
Elige el grupo con mejor score_total, borra JSONs de los perdedores de MinIO, escribe `ganador` en el JSONB. `cmd_timeout=1800`.

**Operaciones de mantenimiento** — disponibles desde el dashboard:
- **"Limpiar transcripciones"** — `POST /pipeline/etapa/correccion_transcripciones/limpiar` → dispara `pipeline_seleccionar_ganador_transcripciones`
- **"Resetear resultados"** — `POST /pipeline/etapa/correccion_transcripciones/resetear` → borra `correccion_transcripciones` del JSONB

---

### Etapas 7–9 — pendientes

---

## Colas de Celery

| Cola                | Workers            | Etapas                                                         |
|---------------------|--------------------|----------------------------------------------------------------|
| `default`           | todos              | creación de registros (2), carga a MongoDB (9)                 |
| `gpu_normalizacion` | los 3              | normalización ffmpeg (3) y corrección de normalización (4)     |
| `gpu_whisper`       | melchor, pc-franco | transcripción WhisperX (5) y corrección de transcripciones (6) |
| `gpu_llm`           | melchor, pc-franco | análisis LLM (7) y corrección de análisis (8)                  |

---

## API — puerto 8001

Corre en gaspar. Es la única puerta de entrada del dashboard — nunca expone Airflow directamente.

### Endpoints

**Ejecución**

| Método | Endpoint                                              | Descripción                                                         |
|--------|-------------------------------------------------------|---------------------------------------------------------------------|
| POST   | `/pipeline/ejecutar`                                  | Dispara el pipeline completo                                        |
| POST   | `/pipeline/etapa/{etapa}/ejecutar`                    | Dispara una etapa con filtro: `pendientes`, `reprocesar`, `todos`   |
| POST   | `/pipeline/etapa/{etapa}/pausar`                      | Pausa el DAG de una etapa                                           |
| POST   | `/pipeline/etapa/correccion_normalizacion/limpiar`      | Dispara DAG `pipeline_seleccionar_ganador`: elige ganador y borra perdedores de MinIO     |
| POST   | `/pipeline/etapa/correccion_normalizacion/resetear`     | Borra resultados de etapa 4 del JSONB, vuelve audios a normalizacion                     |
| POST   | `/pipeline/etapa/correccion_transcripciones/limpiar`    | Dispara DAG `pipeline_seleccionar_ganador_transcripciones`: elige ganador de etapa 6     |
| POST   | `/pipeline/etapa/correccion_transcripciones/resetear`   | Borra resultados de etapa 6 del JSONB                                                    |

Etapas válidas: `descarga` · `creacion_registros` · `normalizacion` · `correccion_normalizacion` · `transcripcion` · `correccion_transcripciones` · `analisis` · `correccion_analisis` · `carga_datos`

**Estado y métricas**

| Método | Endpoint                              | Descripción                                                                         |
|--------|---------------------------------------|-------------------------------------------------------------------------------------|
| GET    | `/pipeline/estado`                    | Resumen: cantidad de audios por etapa y estado                                      |
| GET    | `/pipeline/metricas`                  | Totales, scores promedio, duración promedio                                         |
| GET    | `/pipeline/conversaciones`            | Lista con filtros opcionales                                                        |
| GET    | `/pipeline/conversaciones/{id}`       | Detalle completo incluyendo el JSONB                                                |
| GET    | `/pipeline/audio/{identificador}`     | Info completa de un audio por UUID o nombre_archivo, con ubicaciones MinIO por etapa|
| GET    | `/pipeline/audio/descargar`           | Stream de un archivo de MinIO (`?bucket=&key=&inline=true` para reproducción)       |
| GET    | `/pipeline/audios/aleatorios`         | Muestra aleatoria con filtros: etapa, estado, cuenta, fecha, hora, n                |

> **Nota de orden de rutas:** `/pipeline/audio/descargar` debe estar definido **antes** de `/pipeline/audio/{identificador}` en `routes/estado.py` para que FastAPI no interprete "descargar" como un path parameter.

**Estadísticas**

| Método | Endpoint                              | Descripción                                                                              |
|--------|---------------------------------------|------------------------------------------------------------------------------------------|
| GET    | `/pipeline/estadisticas/global`       | Distribución de audios por etapa y estado — acepta `fecha_desde` y `fecha_hasta`        |
| GET    | `/pipeline/estadisticas/etapa1`       | Total de audios y distribución de duración                                               |
| GET    | `/pipeline/estadisticas/etapa3`       | Conteos correcto / solo_errores de normalización                                         |
| GET    | `/pipeline/estadisticas/etapa4`       | Conteos, scores, SNR, RMS, duracion_ratio, causas de invalido, umbrales desde Postgres   |
| GET    | `/pipeline/estadisticas/etapa5`       | Conteos correcto / error de transcripción                                                |
| GET    | `/pipeline/estadisticas/etapa6`       | Conteos, coherencia LLM, causas de invalido, distribuciones de métricas, umbrales       |

Todos los endpoints filtran por fecha de la llamada (`to_date(left(split_part(nombre_archivo,'_',3),6),'YYMMDD')`). Los umbrales de etapa 4 y 6 se leen en tiempo real desde `pipeline_params`.

**Parámetros**

| Método | Endpoint                          | Descripción                                            |
|--------|-----------------------------------|--------------------------------------------------------|
| GET    | `/pipeline/parametros/{clave}`    | Lee los parámetros actuales de una etapa               |
| PATCH  | `/pipeline/parametros/{clave}`    | Modifica los parámetros — tiene efecto en el próximo run |

Claves válidas: `descarga_G` · `descarga_M` · `descarga_B` · `normalizacion_G` · `normalizacion_M` · `normalizacion_B` · `correccion_normalizacion` · `transcripcion_G` · `transcripcion_M` · `transcripcion_B` · `correccion_transcripciones` · `analisis_A` · `analisis_B` · `correccion_analisis_A` · `correccion_analisis_B`

Ejemplo — modificar parámetros de descarga de melchor:
```bash
curl -X PATCH http://192.168.9.115:8001/pipeline/parametros/descarga_M \
     -H "Content-Type: application/json" \
     -d '{"valor": {"hora_inicio": "13", "hora_fin": "17", "fecha_inicio": "15/04/2026"}}'
```

### Archivos

| Archivo                    | Responsabilidad                                                                    |
|----------------------------|------------------------------------------------------------------------------------|
| `main.py`                  | Registra los cuatro routers; `load_dotenv` va antes de los imports de routers      |
| `airflow_client.py`        | Única capa que habla con la API REST de Airflow; usa `_auth()` función (no constante)|
| `routes/ejecucion.py`      | Endpoints de disparo, pausa y reset de DAGs                                        |
| `routes/estado.py`         | Endpoints de consulta, detalle de audio, stream MinIO y muestra aleatoria          |
| `routes/parametros.py`     | Endpoints de lectura y escritura de `pipeline_params`                              |
| `routes/estadisticas.py`   | Endpoints de estadísticas por etapa; lee umbrales en tiempo real desde `pipeline_params` |
| `requirements.txt`         | Dependencias: `fastapi`, `uvicorn`, `httpx`, `psycopg2-binary`, `pydantic`, `minio`|
