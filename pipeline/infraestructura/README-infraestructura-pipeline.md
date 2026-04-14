# Infraestructura del Pipeline

Todo lo necesario para orquestar y controlar la ejecución del pipeline: API del dashboard, DAGs de Airflow, colas RabbitMQ y configuración de workers.

---

## Estructura

```
infraestructura/
├── api/           # FastAPI que expone el pipeline al dashboard (puerto 8001)
├── airflow/       # DAGs y docker-compose del scheduler (pendiente)
├── rabbitmq/      # definición de colas y exchanges (pendiente)
└── workers/       # docker-compose para levantar workers en las PCs remotas (pendiente)
```

---

## API — puerto 8001

Corre en gaspar (192.168.9.115). Es la única puerta de entrada del dashboard — nunca expone Airflow directamente.

### Levantar

```bash
cd api/
pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8001
```

Requiere variable de entorno:
```
DATABASE_URL=postgresql://user:pass@localhost:5432/scoring
```

### Endpoints

**Ejecución**

| Método | Endpoint                              | Descripción                                               |
|--------|---------------------------------------|-----------------------------------------------------------|
| POST   | `/pipeline/ejecutar`                  | Dispara el pipeline completo                              |
| POST   | `/pipeline/etapa/{etapa}/ejecutar`    | Dispara una etapa con filtro: `pendientes`, `reprocesar`, `todos` |
| POST   | `/pipeline/etapa/{etapa}/pausar`      | Pausa el DAG de una etapa                                 |

Etapas válidas: `descarga` · `normalizacion` · `correccion_normalizacion` · `transcripcion` · `correccion_transcripciones` · `analisis` · `correccion_analisis` · `carga_datos`

Ejemplo — ejecutar solo el análisis de los pendientes:
```bash
curl -X POST http://192.168.9.115:8001/pipeline/etapa/analisis/ejecutar \
     -H "Content-Type: application/json" \
     -d '{"filtro": "pendientes"}'
```

**Estado y métricas**

| Método | Endpoint                              | Descripción                                               |
|--------|---------------------------------------|-----------------------------------------------------------|
| GET    | `/pipeline/estado`                    | Resumen: cantidad de audios por etapa y estado            |
| GET    | `/pipeline/metricas`                  | Totales, scores promedio, duración promedio               |
| GET    | `/pipeline/conversaciones`            | Lista con filtros opcionales: `?estado=reprocesar&etapa=transcripcion` |
| GET    | `/pipeline/conversaciones/{id}`       | Detalle completo de un audio incluyendo el JSONB          |

**Parámetros**

| Método | Endpoint                              | Descripción                                               |
|--------|---------------------------------------|-----------------------------------------------------------|
| GET    | `/pipeline/parametros/{clave}`        | Lee los parámetros actuales de una etapa                  |
| PATCH  | `/pipeline/parametros/{clave}`        | Modifica los parámetros — tiene efecto en el próximo run  |

Claves válidas: `normalizacion` · `correccion_normalizacion` · `transcripcion` · `correccion_transcripciones` · `analisis_A` · `analisis_B` · `correccion_analisis_A` · `correccion_analisis_B`

Ejemplo — modificar parámetros de normalización:
```bash
curl -X PATCH http://192.168.9.115:8001/pipeline/parametros/normalizacion \
     -H "Content-Type: application/json" \
     -d '{"valor": {"silencio_db": -40, "min_duracion_seg": 3}}'
```

### Archivos

| Archivo                   | Responsabilidad                                              |
|---------------------------|--------------------------------------------------------------|
| `main.py`                 | Registra los tres routers                                    |
| `airflow_client.py`       | Única capa que habla con la API REST de Airflow              |
| `routes/ejecucion.py`     | Endpoints de disparo y pausa de DAGs                        |
| `routes/estado.py`        | Endpoints de consulta a `audio_pipeline_jobs`                |
| `routes/parametros.py`    | Endpoints de lectura y escritura de `pipeline_params`        |

---

## Arquitectura distribuida

Tres máquinas en LAN. Airflow distribuye tareas vía RabbitMQ: el worker libre toma el siguiente audio disponible, sin asignación fija.

```
┌─────────────────────────────────────────────┐
│         gaspar  —  192.168.9.115            │
│                                             │
│  Airflow Scheduler  (decide qué ejecutar)   │
│  Airflow Webserver  (UI en :8080)           │
│  RabbitMQ           (broker en :5672)       │
│  PostgreSQL         (dos roles:)            │
│    · metadata interna de Airflow            │
│    · tabla audio_pipeline_jobs y            │
│      pipeline_params del proyecto           │
│  Pipeline API       (dashboard en :8001)    │
│  Airflow Worker     (también procesa)       │
└───────────────────┬─────────────────────────┘
                    │  RabbitMQ reparte tareas
         ┌──────────┼──────────┐
         ▼          ▼          ▼
    gaspar       melchor    pc-franco
    .9.115       .9.195      .9.62
      GPU          GPU         GPU
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

| Rol            | Hostname  | IP            | Usuario SSH | Password SSH |
|----------------|-----------|---------------|-------------|--------------|
| Principal      | gaspar    | 192.168.9.115 | qjose       | —            |
| Worker + MinIO | melchor   | 192.168.9.195 | juan-t3     | `1234`       |
| Worker         | pc-franco | 192.168.9.62  | bases       | `ruleta`     |

### Servicios

| Servicio     | URL                        | Usuario    | Password   |
|--------------|----------------------------|------------|------------|
| Airflow UI   | http://192.168.9.115:8080  | admin      | admin      |
| RabbitMQ UI  | http://192.168.9.115:15672 | rabbitmq   | rabbitmq   |
| MinIO UI     | http://192.168.9.195:9002  | minioadmin | minioadmin |
| MinIO API    | http://192.168.9.195:9001  | minioadmin | minioadmin |
| Pipeline API | http://192.168.9.115:8001  | —          | —          |

---

## Cómo levantar el sistema

### 1. PC principal — gaspar

```bash
cd airflow/
docker compose up -d
```

Levanta: PostgreSQL, RabbitMQ, Airflow Scheduler, Webserver, Triggerer, Worker, Pipeline API.

### 2. Workers — melchor y pc-franco (desde gaspar)

```bash
# melchor
sshpass -p "1234" ssh juan-t3@192.168.9.195 "mkdir C:\airflow-worker\dags 2>nul"
sshpass -p "1234" scp workers/docker-compose.yml juan-t3@192.168.9.195:"C:/airflow-worker/docker-compose.yml"
sshpass -p "1234" scp airflow/dags/*.py juan-t3@192.168.9.195:"C:/airflow-worker/dags/"
sshpass -p "1234" ssh juan-t3@192.168.9.195 "cd C:\airflow-worker && docker compose up -d"

# pc-franco
sshpass -p "ruleta" ssh bases@192.168.9.62 "mkdir C:\airflow-worker\dags 2>nul"
sshpass -p "ruleta" scp workers/docker-compose.yml bases@192.168.9.62:"C:/airflow-worker/docker-compose.yml"
sshpass -p "ruleta" scp airflow/dags/*.py bases@192.168.9.62:"C:/airflow-worker/dags/"
sshpass -p "ruleta" ssh bases@192.168.9.62 "cd C:\airflow-worker && docker compose up -d"
```

### 3. Sincronizar DAGs después de cambios

```bash
sshpass -p "1234"   scp airflow/dags/*.py juan-t3@192.168.9.195:"C:/airflow-worker/dags/"
sshpass -p "ruleta" scp airflow/dags/*.py bases@192.168.9.62:"C:/airflow-worker/dags/"
```

### 4. Detener todo

```bash
# Workers
sshpass -p "1234"   ssh juan-t3@192.168.9.195 "cd C:\airflow-worker && docker compose down"
sshpass -p "ruleta" ssh bases@192.168.9.62    "cd C:\airflow-worker && docker compose down"

# Principal
cd airflow/ && docker compose down
```

---

## Airflow

Un solo Airflow compartido con el proyecto scraping. Los DAGs del pipeline usan el prefijo `pipeline_*`.

Los DAGs se crean una vez que los scripts de `logica/` estén implementados. Ver `logica/README-logica-pipeline.md` para entender qué hace cada etapa.

---

## RabbitMQ — colas

| Cola              | Workers            | Tareas                                                                      |
|-------------------|--------------------|-----------------------------------------------------------------------------|
| `default`         | todos              | descarga (etapa 1), creación de registros (etapa 2), carga a MongoDB (etapa 9) |
| `gpu_normalizacion` | los 3 workers    | normalización ffmpeg (etapa 3) y corrección de normalización (etapa 4)      |
| `gpu_whisper`     | melchor, pc-franco | transcripción WhisperX (etapa 5) y corrección de transcripciones (etapa 6)  |
| `gpu_llm`         | melchor, pc-franco | análisis LLM (etapa 7) y corrección de análisis (etapa 8)                   |

---

## Workers

Los workers solo reciben el código de las etapas que ejecutan — no el proyecto completo. El `docker-compose.yml` de `workers/` se despliega en melchor y pc-franco vía SSH desde gaspar.

Ver comandos de deploy en `README-pipeline.md`.
