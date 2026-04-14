# Pipeline de Scoring de Conversaciones de Venta

Pipeline distribuido para procesar llamadas de venta en castellano: descarga los audios por scraping, los normaliza, transcribe con identificación de hablantes, los analiza con un LLM local y carga los resultados en MongoDB.

Para el detalle de cada subcarpeta leer el README correspondiente:
- `logica/README-logica-pipeline.md` — scripts de las 9 etapas, estructura MinIO, trazabilidad
- `infraestructura/README-infraestructura-pipeline.md` — API, Airflow, RabbitMQ, workers

---

## Estructura

```
pipeline/
├── infraestructura/    # orquestación, API, workers, colas
└── logica/             # scripts de procesamiento (9 etapas)
```

---

## Arquitectura y operación

Para el detalle de máquinas, servicios, comandos de deploy y configuración de workers ver `infraestructura/README-infraestructura-pipeline.md`.
