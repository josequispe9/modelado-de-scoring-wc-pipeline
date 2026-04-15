-- Se ejecuta automáticamente al primer arranque del contenedor postgres.
-- Crea la base de datos del proyecto y su usuario.

CREATE DATABASE scoring;
CREATE USER scoring WITH PASSWORD 'scoring';
GRANT ALL PRIVILEGES ON DATABASE scoring TO scoring;
\connect scoring
GRANT ALL ON SCHEMA public TO scoring;
