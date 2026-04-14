"""
Crea las tablas del pipeline en PostgreSQL.
Idempotente: se puede ejecutar múltiples veces sin errores.

Requiere la variable de entorno DATABASE_URL, ej:
    postgresql://user:pass@localhost:5432/scoring
"""
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

# ─────────────────────────────────────────────────────────────────────────────
# audio_pipeline_jobs
# Una fila por audio. Registra el progreso a través de las 9 etapas.
#
# Estructura del JSONB `etapas` (se agrega cada clave al iniciar la etapa):
# {
#   "descarga": {
#       "estado": "correcto|error",
#       "fecha_inicio": "...", "fecha_fin": "...",
#       "ubicacion": {"bucket": "modelado-de-scoring-wc", "key": "audios/uuid.wav"},
#       "intentos": 1, "error": null
#   },
#   "normalizacion": {
#       "estado": "correcto|error",
#       "ubicacion": {"bucket": "modelado-de-scoring-wc", "key": "audios-raw/uuid.wav"},
#       ...
#   },
#   "correccion_normalizacion": {
#       "estado": "correcto|reprocesar|invalido",
#       "ubicacion": {"bucket": "modelado-de-scoring-wc", "key": "audios_procesados/correcto/uuid.wav"},
#       "score": 0.92, ...
#   },
#   "transcripcion": {
#       "estado": "correcto|error",
#       "ubicacion": {"bucket": "modelado-de-scoring-wc", "key": "transcripciones-raw/uuid.json"},
#       "modelo": "whisperx-large-v3", "num_hablantes": 2, ...
#   },
#   "correccion_transcripciones": {
#       "estado": "correcto|reprocesar|invalido",
#       "ubicacion": {"bucket": "modelado-de-scoring-wc", "key": "transcripciones-procesadas/correcto/uuid.json"},
#       "score": 0.88, "num_hablantes": 2, ...
#   },
#   "analisis": {
#       "analisis_A": {
#           "estado": "correcto|error",
#           "ubicacion": {"bucket": "modelado-de-scoring-wc", "key": "analisis-raw/analisis-A/uuid.json"},
#           "modelo": "...", ...
#       },
#       "analisis_B": { ... }
#   },
#   "correccion_analisis": {
#       "analisis_A": {
#           "estado": "correcto|reprocesar|invalido",
#           "ubicacion": {"bucket": "modelado-de-scoring-wc", "key": "analisis-procesados/analisis-A/correcto/uuid.json"},
#           "score_lead": 78, "confidence_score": 0.91, ...
#       },
#       "analisis_B": { ... }
#   },
#   "carga_datos": {
#       "estado": "correcto|error",
#       "intentos": 1, "error": null
#   }
# }
# ─────────────────────────────────────────────────────────────────────────────

DDL_AUDIO_PIPELINE_JOBS = """
CREATE TABLE IF NOT EXISTS audio_pipeline_jobs (
    id                        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    numero_telefono           VARCHAR(20),
    url_fuente                TEXT,

    duracion_audio_seg        INTEGER,
    duracion_conversacion_seg INTEGER,
    fecha_llamada             TIMESTAMPTZ,

    estado_global             VARCHAR(20)  NOT NULL DEFAULT 'pendiente'
                                  CHECK (estado_global IN (
                                      'pendiente', 'en_proceso', 'correcto',
                                      'error', 'reprocesar', 'invalido'
                                  )),
    etapa_actual              VARCHAR(40)  NOT NULL DEFAULT 'descarga',

    created_at                TIMESTAMPTZ  NOT NULL DEFAULT now(),
    fecha_ultima_actualizacion TIMESTAMPTZ NOT NULL DEFAULT now(),

    etapas                    JSONB        NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_audio_pipeline_estado_etapa
    ON audio_pipeline_jobs (estado_global, etapa_actual);

CREATE INDEX IF NOT EXISTS idx_audio_pipeline_etapas_gin
    ON audio_pipeline_jobs USING GIN (etapas);

CREATE INDEX IF NOT EXISTS idx_audio_pipeline_fecha
    ON audio_pipeline_jobs (fecha_ultima_actualizacion DESC);

CREATE INDEX IF NOT EXISTS idx_audio_pipeline_created
    ON audio_pipeline_jobs (created_at DESC);

CREATE OR REPLACE FUNCTION update_fecha_actualizacion()
RETURNS TRIGGER AS $$
BEGIN
    NEW.fecha_ultima_actualizacion = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_update_fecha_audio_pipeline ON audio_pipeline_jobs;
CREATE TRIGGER trg_update_fecha_audio_pipeline
BEFORE UPDATE ON audio_pipeline_jobs
FOR EACH ROW EXECUTE FUNCTION update_fecha_actualizacion();
"""

# ─────────────────────────────────────────────────────────────────────────────
# pipeline_params
# Parámetros globales por etapa, modificables desde el dashboard.
# Los scripts de cada etapa leen esta tabla al inicio del run.
# Si no existe entrada para una etapa, el script usa los defaults de config.py.
# ─────────────────────────────────────────────────────────────────────────────

DDL_PIPELINE_PARAMS = """
CREATE TABLE IF NOT EXISTS pipeline_params (
    etapa      VARCHAR(40)  PRIMARY KEY,
    params     JSONB        NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

INSERT INTO pipeline_params (etapa, params) VALUES
    ('normalizacion',              '{}'),
    ('correccion_normalizacion',   '{}'),
    ('transcripcion',              '{}'),
    ('correccion_transcripciones', '{}'),
    ('analisis_A',                 '{}'),
    ('analisis_B',                 '{}'),
    ('correccion_analisis_A',      '{}'),
    ('correccion_analisis_B',      '{}')
ON CONFLICT (etapa) DO NOTHING;
"""


def crear_tablas():
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(DDL_AUDIO_PIPELINE_JOBS)
            cur.execute(DDL_PIPELINE_PARAMS)
        conn.commit()
    print("Tablas creadas correctamente.")


if __name__ == "__main__":
    crear_tablas()
