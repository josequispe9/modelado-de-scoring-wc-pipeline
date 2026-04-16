# Modelado de Scoring WC

Sistema distribuido compuesto por tres proyectos que corren diariamente de forma coordinada: un pipeline de procesamiento de audios de ventas, un sistema de scraping para enriquecimiento de datos, y un dashboard de control y monitoreo.

Cada proyecto expone una API que permite al dashboard tener control total sobre la ejecución, el monitoreo y la configuración de cada etapa sin tocar el código.

---

## Proyectos

### pipeline

9 etapas: descarga de audios por scraping → normalización → transcripción con diarización → análisis con LLM local → carga en MongoDB. Las etapas de corrección (4, 6, 8) actúan como quality gates. Cada audio tiene trazabilidad completa en PostgreSQL.

- `pipeline/logica/` — scripts de las 9 etapas
- `pipeline/infraestructura/` — Pipeline API (:8001), Airflow 2.10.3, Redis, workers

### scraping

Enriquece una base de datos a partir de fuentes externas (ENACOM, IRIS, RAPIPAGO). Corre de forma independiente al pipeline, sin interferir con sus recursos.

- `scraping/logica/` — scripts de extracción por fuente
- `scraping/infraestructura/` — Scraping API (:8002), Airflow, workers

### frontend

Dashboard React que centraliza el control y monitoreo de ambos proyectos. Se comunica exclusivamente con las APIs — nunca directamente con Airflow ni con las bases de datos.

- `frontend/` — React + TypeScript + Vite

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
   │  Airflow + Redis     │               │  Airflow             │
   │  PostgreSQL + MinIO  │               │  (DAGs scraping_*)   │
   │  (DAGs pipeline_*)   │               └──────────┬──────────┘
   └──────────┬──────────┘                          │
              │                              [grupo de PCs
     ┌────────┴────────┐                     del scraping]
     ▼        ▼        ▼
  gaspar   melchor  pc-franco
  .9.115   .9.195   .9.62
```

Un solo Airflow gestiona ambos proyectos. Los DAGs del pipeline usan prefijo `pipeline_*`, los del scraping `scraping_*`.
