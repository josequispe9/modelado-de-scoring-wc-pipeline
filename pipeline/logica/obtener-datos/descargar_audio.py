"""
Utilidad para obtener un objeto de MinIO como stream de bytes.
Usado por la API FastAPI para servir descargas al frontend.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from minio import Minio

load_dotenv(Path(__file__).parents[3] / ".env.tuberia", override=True)

_client = None

def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            os.environ["MINIO_ENDPOINT"],
            access_key=os.environ["MINIO_ACCESS_KEY"],
            secret_key=os.environ["MINIO_SECRET_KEY"],
            secure=False,
        )
    return _client


def obtener_stream(bucket: str, key: str):
    """
    Retorna (response, tamanio) donde response es el objeto HTTP de MinIO.
    El llamador es responsable de cerrar response.
    Lanza S3Error si el objeto no existe.
    """
    client = _get_client()
    response = client.get_object(bucket, key)
    tamanio  = response.headers.get("Content-Length")
    return response, int(tamanio) if tamanio else None
