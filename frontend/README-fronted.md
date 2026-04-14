# Frontend — Dashboard de Control

Dashboard React que centraliza el control y monitoreo del pipeline y el scraping. Permite visualizar el estado en tiempo real, disparar etapas, modificar parámetros y consultar el historial de cada registro. Se comunica exclusivamente con las APIs de cada proyecto.

---

## Stack

- React + Vite
- Variables de entorno en `.env` (ver `.env.example`)

---

## Estructura

```
frontend/
├── src/
│   ├── api/                  # clientes HTTP hacia las APIs
│   │   ├── config.js         # URLs base leídas desde .env
│   │   ├── pipeline.js       # todas las llamadas a la API del pipeline
│   │   └── scraping.js       # todas las llamadas a la API del scraping
│   ├── projects/             # una carpeta por proyecto
│   │   ├── pipeline/
│   │   │   ├── pages/
│   │   │   ├── components/
│   │   │   └── hooks/
│   │   └── scraping/
│   │       ├── pages/
│   │       ├── components/
│   │       └── hooks/
│   └── shared/               # componentes y hooks reutilizables entre proyectos
│       ├── components/
│       └── hooks/
└── public/
```

Agregar un tercer proyecto: nueva carpeta en `projects/` y nuevo archivo en `api/`.

---

## APIs

| Proyecto | URL base | Definida en |
|----------|----------|-------------|
| Pipeline | `http://192.168.9.115:8001` | `VITE_PIPELINE_API_URL` |
| Scraping | `http://192.168.9.115:8002` | `VITE_SCRAPING_API_URL` |

El frontend nunca habla con Airflow ni con las bases de datos directamente. Todo pasa por `src/api/`.
