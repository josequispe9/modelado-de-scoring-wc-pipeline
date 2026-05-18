from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[3] / ".env.tuberia", override=True)

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from api.routes import ejecucion, estado, parametros, estadisticas

app = FastAPI(title="Pipeline API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def no_cache(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response

app.include_router(ejecucion.router,    prefix="/pipeline", tags=["ejecucion"])
app.include_router(estado.router,       prefix="/pipeline", tags=["estado"])
app.include_router(parametros.router,   prefix="/pipeline", tags=["parametros"])
app.include_router(estadisticas.router, prefix="/pipeline", tags=["estadisticas"])
