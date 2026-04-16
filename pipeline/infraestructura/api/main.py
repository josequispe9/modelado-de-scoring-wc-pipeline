from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import ejecucion, estado, parametros

app = FastAPI(title="Pipeline API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ejecucion.router,  prefix="/pipeline", tags=["ejecucion"])
app.include_router(estado.router,     prefix="/pipeline", tags=["estado"])
app.include_router(parametros.router, prefix="/pipeline", tags=["parametros"])
