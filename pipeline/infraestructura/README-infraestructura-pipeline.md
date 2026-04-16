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
| Airflow UI   | http://192.168.9.115:8080  | admin      | F9a9h2uGD3RhPHs2   |
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
pip install fastapi uvicorn httpx psycopg2-binary pydantic

# Cargar variables de entorno y levantar
Get-Content .\.env | ForEach-Object {
    if ($_ -match "^([^#][^=]+)=(.+)$") {
        [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim())
    }
}
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload
```

Las variables que necesita el `.env` (en `pipeline/infraestructura/.env`):
```
DATABASE_URL=postgresql://scoring:scoring@localhost:5432/scoring
AIRFLOW_BASE_URL=http://localhost:8080/api/v1
AIRFLOW_USER=admin
AIRFLOW_PASSWORD=F9a9h2uGD3RhPHs2
```

> La Pipeline API requiere que Airflow tenga habilitado el backend de autenticación básica.
> Está configurado en el `docker-compose.yml` con `AIRFLOW__API__AUTH_BACKENDS: airflow.api.auth.backend.basic_auth`.

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

### Etapas 2–9 — CeleryExecutor

Las etapas restantes corren dentro de contenedores Docker en los workers, distribuidas por Celery + Redis según la cola correspondiente.

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

| Método | Endpoint                           | Descripción                                                         |
|--------|------------------------------------|---------------------------------------------------------------------|
| POST   | `/pipeline/ejecutar`               | Dispara el pipeline completo                                        |
| POST   | `/pipeline/etapa/{etapa}/ejecutar` | Dispara una etapa con filtro: `pendientes`, `reprocesar`, `todos`   |
| POST   | `/pipeline/etapa/{etapa}/pausar`   | Pausa el DAG de una etapa                                           |

Etapas válidas: `descarga` · `normalizacion` · `correccion_normalizacion` · `transcripcion` · `correccion_transcripciones` · `analisis` · `correccion_analisis` · `carga_datos`

**Estado y métricas**

| Método | Endpoint                          | Descripción                                            |
|--------|-----------------------------------|--------------------------------------------------------|
| GET    | `/pipeline/estado`                | Resumen: cantidad de audios por etapa y estado         |
| GET    | `/pipeline/metricas`              | Totales, scores promedio, duración promedio            |
| GET    | `/pipeline/conversaciones`        | Lista con filtros opcionales                           |
| GET    | `/pipeline/conversaciones/{id}`   | Detalle completo incluyendo el JSONB                   |

**Parámetros**

| Método | Endpoint                          | Descripción                                            |
|--------|-----------------------------------|--------------------------------------------------------|
| GET    | `/pipeline/parametros/{clave}`    | Lee los parámetros actuales de una etapa               |
| PATCH  | `/pipeline/parametros/{clave}`    | Modifica los parámetros — tiene efecto en el próximo run |

Claves válidas: `descarga_G` · `descarga_M` · `descarga_B` · `normalizacion` · `correccion_normalizacion` · `transcripcion` · `correccion_transcripciones` · `analisis_A` · `analisis_B` · `correccion_analisis_A` · `correccion_analisis_B`

Ejemplo — modificar parámetros de descarga de melchor:
```bash
curl -X PATCH http://192.168.9.115:8001/pipeline/parametros/descarga_M \
     -H "Content-Type: application/json" \
     -d '{"valor": {"hora_inicio": "13", "hora_fin": "17", "fecha_inicio": "15/04/2026"}}'
```

### Archivos

| Archivo                | Responsabilidad                                              |
|------------------------|--------------------------------------------------------------|
| `main.py`              | Registra los tres routers                                    |
| `airflow_client.py`    | Única capa que habla con la API REST de Airflow              |
| `routes/ejecucion.py`  | Endpoints de disparo y pausa de DAGs                         |
| `routes/estado.py`     | Endpoints de consulta a `audio_pipeline_jobs`                |
| `routes/parametros.py` | Endpoints de lectura y escritura de `pipeline_params`        |
