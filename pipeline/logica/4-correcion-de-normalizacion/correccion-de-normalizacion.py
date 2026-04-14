import os


# ===== CONFIGURACIÓN =====
INPUT_DIR = ""
OUTPUT_BASE = ""
OUTPUT_DIRS = {
    'correctos': os.path.join(OUTPUT_BASE, "correctos"),
    'reprocesar': os.path.join(OUTPUT_BASE, "reprocesar"),
    'invalido': os.path.join(OUTPUT_BASE, "invalido"),
}