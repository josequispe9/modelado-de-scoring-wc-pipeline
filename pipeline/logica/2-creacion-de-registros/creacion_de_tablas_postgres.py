"""
Crea las tablas del pipeline en la base de datos 'scoring' en PostgreSQL.
Idempotente: se puede ejecutar múltiples veces sin errores.

Uso:
    SCORING_DB_URL=postgresql://scoring:scoring@192.168.9.115:5432/scoring python creacion_de_tablas_postgres.py

O con el .env.tuberia cargado:
    python creacion_de_tablas_postgres.py
"""
import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg2

ROOT_DIR = Path(__file__).parents[3]
load_dotenv(ROOT_DIR / ".env.tuberia")

DATABASE_URL = os.environ["SCORING_DB_URL"]

# ─────────────────────────────────────────────────────────────────────────────
# audio_pipeline_jobs
# Una fila por audio. Registra el progreso a través de las 9 etapas.
# ─────────────────────────────────────────────────────────────────────────────

DDL_AUDIO_PIPELINE_JOBS = """
CREATE TABLE IF NOT EXISTS audio_pipeline_jobs (
    id                         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identificación del audio
    nombre_archivo             VARCHAR(200) UNIQUE,     -- base sin sufijo _G/_M/_B ni .wav
    id_interaccion             VARCHAR(100),
    url_fuente                 TEXT,                    -- ruta MinIO del WAV
    cuenta                     VARCHAR(1),              -- G, M o B

    -- Metadata de la llamada
    numero_telefono            VARCHAR(20),
    inicio                     VARCHAR(30),             -- timestamp tal como viene de Mitrol
    agente                     VARCHAR(100),
    extension                  VARCHAR(20),
    empresa                    VARCHAR(100),
    campania                   VARCHAR(100),
    tipificacion               VARCHAR(100),
    clase_tipificacion         VARCHAR(100),

    -- Duraciones en segundos (convertidas desde HH:MM:SS)
    duracion_audio_seg         INTEGER,
    duracion_conversacion_seg  INTEGER,

    -- Control de flujo
    estado_global              VARCHAR(20)  NOT NULL DEFAULT 'correcto'
                                   CHECK (estado_global IN (
                                       'pendiente', 'en_proceso', 'correcto',
                                       'error', 'reprocesar', 'invalido'
                                   )),
    etapa_actual               VARCHAR(40)  NOT NULL DEFAULT 'descarga',

    created_at                 TIMESTAMPTZ  NOT NULL DEFAULT now(),
    fecha_ultima_actualizacion TIMESTAMPTZ  NOT NULL DEFAULT now(),

    etapas                     JSONB        NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_apj_estado_etapa
    ON audio_pipeline_jobs (estado_global, etapa_actual);

CREATE INDEX IF NOT EXISTS idx_apj_etapas_gin
    ON audio_pipeline_jobs USING GIN (etapas);

CREATE INDEX IF NOT EXISTS idx_apj_fecha_actualizacion
    ON audio_pipeline_jobs (fecha_ultima_actualizacion DESC);

CREATE INDEX IF NOT EXISTS idx_apj_created
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
# Parámetros por etapa, modificables desde el dashboard.
# Los scripts leen esta tabla al inicio del run; si no hay entrada usan config.py.
#
# Claves de descarga: una por PC (G=gaspar, M=melchor, B=pc-franco).
# Valor vacío {} → el script usa todos los DEFAULTS de config.py.
# ─────────────────────────────────────────────────────────────────────────────

DDL_PIPELINE_PARAMS = """
CREATE TABLE IF NOT EXISTS pipeline_params (
    clave      VARCHAR(40)  PRIMARY KEY,
    valor      JSONB        NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

INSERT INTO pipeline_params (clave, valor) VALUES
    -- Etapa 2 — creación de registros
    ('creacion_registros',                  '{}'),
    -- Etapa 1 — descarga (una por PC)
    ('descarga_G',                          '{}'),
    ('descarga_M',                          '{}'),
    ('descarga_B',                          '{}'),
    -- Etapa 3 — normalización (una por PC)
    ('normalizacion_G',                     '{}'),
    ('normalizacion_M',                     '{}'),
    ('normalizacion_B',                     '{}'),
    -- Etapa 4 — corrección de normalización (compartida)
    ('correccion_normalizacion',            '{}'),
    ('correccion_normalizacion_ganador',    '{}'),
    -- Etapa 5 — transcripción (una por PC)
    ('transcripcion_G',                     '{}'),
    ('transcripcion_M',                     '{}'),
    ('transcripcion_B',                     '{}'),
    -- Etapa 6 — corrección de transcripciones (una por PC + ganador)
    ('correccion_transcripciones_llm_G',    '{}'),
    ('correccion_transcripciones_llm_M',    '{}'),
    ('correccion_transcripciones_llm_B',    '{}'),
    ('correccion_transcripciones_ganador',  '{}'),
    -- Etapa 7 — análisis (una por tipo de análisis)
    ('analisis_A',                          '{}'),
    ('analisis_B',                          '{}'),
    -- Etapa 8 — corrección de análisis (una por tipo)
    ('correccion_analisis_A',               '{}'),
    ('correccion_analisis_B',               '{}')
ON CONFLICT (clave) DO NOTHING;
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
