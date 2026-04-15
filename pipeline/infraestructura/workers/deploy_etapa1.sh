#!/bin/bash
# Deploy de la etapa 1 (descarga de audios) a melchor y pc-franco.
# Ejecutar desde la raiz del proyecto en WSL:
#   bash pipeline/infraestructura/workers/deploy_etapa1.sh

set -e

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

# ─── Configuración de máquinas ────────────────────────────────────────────────

declare -A HOSTS=( ["M"]="192.168.9.195" ["B"]="192.168.9.62" )
declare -A USERS=( ["M"]="juan-t3"       ["B"]="bases" )
declare -A PASWS=( ["M"]="1234"          ["B"]="ruleta" )
declare -A RUTAS=(
    ["M"]="C:/Users/JUAN-T3/Desktop/modelado de scoring WC"
    ["B"]="C:/Users/Bases/Desktop/modelado de scoring WC"
)

# Archivos a copiar
ARCHIVOS=(
    "pipeline/logica/1-descarga-de-audios/scraping_mitrol.py"
    "pipeline/logica/1-descarga-de-audios/config.py"
    "pipeline/logica/1-descarga-de-audios/run_standalone.py"
    "pipeline/requirements-pipeline.txt"
)

# ─── Deploy por máquina ───────────────────────────────────────────────────────

for CUENTA in "M" "B"; do
    HOST="${HOSTS[$CUENTA]}"
    USER="${USERS[$CUENTA]}"
    PASS="${PASWS[$CUENTA]}"
    RUTA="${RUTAS[$CUENTA]}"

    echo ""
    echo "══════════════════════════════════════════"
    echo "  Desplegando en $HOST (cuenta $CUENTA)"
    echo "══════════════════════════════════════════"

    SSH="sshpass -p $PASS ssh -o StrictHostKeyChecking=no $USER@$HOST"
    SCP="sshpass -p $PASS scp -o StrictHostKeyChecking=no"

    # 1. Crear estructura de carpetas
    echo "→ Creando carpetas..."
    $SSH "mkdir \"$RUTA\\pipeline\\logica\\1-descarga-de-audios\" 2>nul & exit 0"

    # 2. Copiar archivos del proyecto
    echo "→ Copiando archivos..."
    for ARCHIVO in "${ARCHIVOS[@]}"; do
        DESTINO="$USER@$HOST:\"$RUTA\\$(echo $ARCHIVO | tr '/' '\\')\""
        $SCP "$ROOT/$ARCHIVO" "$USER@$HOST:$RUTA/${ARCHIVO//\//\\}"
        echo "   ✓ $ARCHIVO"
    done

    # 3. Crear .env.tuberia con MITROL_CUENTA correcto para esta máquina
    echo "→ Creando .env.tuberia (MITROL_CUENTA=$CUENTA)..."
    TMPENV=$(mktemp)
    sed "s/^MITROL_CUENTA=.*/MITROL_CUENTA=$CUENTA/" "$ROOT/.env.tuberia" > "$TMPENV"
    $SCP "$TMPENV" "$USER@$HOST:$RUTA/.env.tuberia"
    rm "$TMPENV"

    echo "✅ $HOST listo"
done

echo ""
echo "Deploy completo. Para instalar/actualizar dependencias en el venv de cada PC:"
echo "  sshpass -p '1234'   ssh juan-t3@192.168.9.195 \"cd \\\"C:/Users/JUAN-T3/Desktop/modelado de scoring WC\\\" && pipeline\\\\venv\\\\Scripts\\\\pip install -r pipeline/requirements-pipeline.txt\""
echo "  sshpass -p 'ruleta' ssh bases@192.168.9.62    \"cd \\\"C:/Users/Bases/Desktop/modelado de scoring WC\\\"   && pipeline\\\\venv\\\\Scripts\\\\pip install -r pipeline/requirements-pipeline.txt\""
