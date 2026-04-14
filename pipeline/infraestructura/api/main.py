from fastapi import FastAPI
from api.routes import ejecucion, estado, parametros

app = FastAPI(title="Pipeline API", version="1.0.0")

app.include_router(ejecucion.router,  prefix="/pipeline", tags=["ejecucion"])
app.include_router(estado.router,     prefix="/pipeline", tags=["estado"])
app.include_router(parametros.router, prefix="/pipeline", tags=["parametros"])
