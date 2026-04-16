# Dashboard — Frontend

React + TypeScript + Vite. Muestra el estado del pipeline y permite configurar y disparar ejecuciones.

---

## Comunicación con el backend

El frontend habla exclusivamente con la **Pipeline API** (FastAPI, puerto 8001). La URL se configura en `.env`:

```
VITE_PIPELINE_API_URL=http://localhost:8001
```

Las funciones de fetch viven en `src/api/pipeline.js`. Los tres grupos de endpoints que usa:

| Grupo        | Uso en el frontend                                                  |
|--------------|---------------------------------------------------------------------|
| Parámetros   | `GET /pipeline/parametros/{clave}` — carga los valores al abrir cada panel de máquina |
|              | `PATCH /pipeline/parametros/{clave}` — guarda al presionar "Guardar" |
| Ejecución    | `POST /pipeline/etapa/{etapa}/ejecutar` — dispara el DAG desde el botón "Ejecutar" |
| Estado       | `GET /pipeline/estado` — (pendiente de implementar en el monitoreo) |

El frontend nunca habla con Airflow directamente — todo pasa por la Pipeline API.

---

## Levantar

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173 (o el siguiente puerto libre)
```
