from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[3] / ".env.tuberia", override=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import ejecucion, estado, parametros, estadisticas

app = FastAPI(title="Pipeline API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ejecucion.router,    prefix="/pipeline", tags=["ejecucion"])
app.include_router(estado.router,       prefix="/pipeline", tags=["estado"])
app.include_router(parametros.router,   prefix="/pipeline", tags=["parametros"])
app.include_router(estadisticas.router, prefix="/pipeline", tags=["estadisticas"])
