# Modelado de Scoring WC

Sistema distribuido compuesto por tres proyectos que corren diariamente de forma coordinada: un pipeline de procesamiento de audios de ventas, un sistema de scraping para enriquecimiento de datos, y un dashboard de control y monitoreo.

Cada proyecto corre sobre su propio grupo de computadoras en red local y es orquestado con Airflow. Ambos proyectos exponen una API que permite al dashboard tener control total sobre la ejecución, el monitoreo y la configuración de cada etapa sin tocar el código.

El sistema está diseñado para crecer: agregar nuevas etapas, nuevos tipos de análisis o nuevas fuentes de scraping no requiere modificar lo existente.

---

## Proyectos


### pipeline

Procesa llamadas de venta en castellano a través de 9 etapas: descarga de audios por scraping, normalización, transcripción con identificación de hablantes, análisis con LLM local y carga de resultados en MongoDB. Cada audio tiene un registro de trazabilidad en PostgreSQL que actúa como pasaporte a través del pipeline, registrando el estado, los parámetros utilizados y la ubicación de los archivos en cada etapa. Las etapas de corrección actúan como quality gates que clasifican cada audio como correcto, a reprocesar o inválido antes de continuar.

Ver `pipeline/README-pipeline.md` para el detalle completo.  
Ver `pipeline/logica/README-logica-pipeline.md` para los scripts de procesamiento.  
Ver `pipeline/infraestructura/README-infraestructura-pipeline.md` para la API, Airflow, workers y despliegue.

### scraping

Enriquece una base de datos a partir de fuentes externas: ENACOM, IRIS y RAPIPAGO. Corre periódicamente sobre su propio grupo de computadoras, de forma completamente independiente al pipeline, sin interferir con sus recursos.

Ver `scraping/README-scraping.md` para el detalle completo.  
Ver `scraping/logica/README-logica-scraping.md` para los scripts de extracción.  
Ver `scraping/infraestructura/README-infraestructura-scraping.md` para la API, Airflow, workers y despliegue.

### frontend

Dashboard React que centraliza el control y monitoreo de ambos proyectos. Permite visualizar el estado en tiempo real, disparar etapas individuales, modificar parámetros de procesamiento y consultar el historial de cada registro. Se comunica exclusivamente con las APIs de cada proyecto — nunca directamente con Airflow ni con las bases de datos.

Ver `frontend/README-frontend.md` para el detalle completo.

---

## Estructura

```
modelado-de-scoring-wc/
├── pipeline/               # procesamiento de audios de ventas (9 etapas)
│   ├── infraestructura/    # API, Airflow, RabbitMQ, workers
│   └── logica/             # scripts de las 9 etapas
├── scraping/               # enriquecimiento de base de datos
│   ├── infraestructura/    # API, Airflow, RabbitMQ, workers
│   └── logica/             # scripts de extracción por fuente
├── frontend/               # dashboard React de control y monitoreo
│   └── src/
│       ├── api/            # clientes hacia las APIs de pipeline y scraping
│       ├── projects/       # vistas y componentes por proyecto
│       └── shared/         # componentes compartidos entre proyectos
└── utils/
```

---

## Arquitectura general

```
                    ┌─────────────────────────┐
                    │      frontend            │
                    │   dashboard React        │
                    └────────┬────────┬────────┘
                             │        │
              ┌──────────────┘        └──────────────┐
              ▼                                       ▼
   ┌─────────────────────┐               ┌─────────────────────┐
   │    Pipeline API      │               │    Scraping API      │
   │  gaspar :8001        │               │  gaspar :8002        │
   └──────────┬──────────┘               └──────────┬──────────┘
              │                                       │
              ▼                                       ▼
   ┌─────────────────────┐               ┌─────────────────────┐
   │  Airflow + RabbitMQ  │               │  Airflow + RabbitMQ  │
   │  PostgreSQL + MinIO  │               │       (DAGs          │
   │  (pipeline_*)        │               │      scraping_*)     │
   └──────────┬──────────┘               └──────────┬──────────┘
              │                                       │
     ┌────────┴────────┐                    ┌────────┴────────┐
     ▼        ▼        ▼                    ▼        ▼        ▼
  gaspar   melchor  pc-franco            [grupo de PCs
  .9.115   .9.195   .9.62                 del scraping]
  GPU      GPU      GPU
```

Un solo Airflow gestiona ambos proyectos desde la máquina de control. Los DAGs del pipeline usan el prefijo `pipeline_*` y los del scraping `scraping_*`. Cada proyecto tiene sus propias colas en RabbitMQ para que los workers no se pisen entre sí.
