"""
Busca en todos los discos de Windows archivos .txt que tengan el formato:
    ID;fecha;descripcion
    (delimitador ;, exactamente 3 campos, primer campo ID numérico, segundo campo fecha DD/MM/YYYY)

Ejemplo de línea:
    32079387;2/12/2025;Aprobación del ABD

Los archivos que coincidan se MUEVEN a la carpeta 'info_id_encontrados'
ubicada en el mismo directorio que este script.
"""

import os
import re
import shutil
import string
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "info_id_encontrados"

# Mínimo de líneas con el formato para considerar que el archivo coincide
MIN_MATCHING_LINES = 3

# Fracción del archivo a leer desde el inicio y desde el final
SAMPLE_FRACTION = 0.40

# Encodings a intentar al abrir los archivos
ENCODINGS = ["utf-8", "latin-1", "cp1252"]

# Regex: exactamente 3 campos separados por ;
#   campo 1: ID numérico (5+ dígitos)
#   campo 2: fecha D/M/YYYY o DD/MM/YYYY
#   campo 3: texto libre (no vacío)
LINE_RE = re.compile(
    r"^\d{5,};"                         # ID numérico al inicio
    r"\d{1,2}/\d{1,2}/\d{4};"          # fecha D/M/YYYY
    r".+$"                              # descripción no vacía
)


def is_matching_line(line: str) -> bool:
    return bool(LINE_RE.match(line)) and line.count(";") == 2


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def get_all_drives() -> list[str]:
    """Devuelve las letras de unidades disponibles en Windows (C:\\, D:\\, ...)."""
    drives = []
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if os.path.exists(drive):
            drives.append(drive)
    return drives


def read_sample(filepath: Path) -> str:
    """
    Lee el primer 40% y el último 40% del archivo.
    Retorna el texto combinado, o cadena vacía si no se puede leer.
    """
    for enc in ENCODINGS:
        try:
            with open(filepath, "r", encoding=enc, errors="replace") as f:
                lines = f.readlines()

            if not lines:
                return ""

            total = len(lines)
            top_end = max(1, int(total * SAMPLE_FRACTION))
            bot_start = min(total, int(total * (1 - SAMPLE_FRACTION)))

            sample = lines[:top_end] + lines[bot_start:]
            return "".join(sample)
        except (OSError, PermissionError):
            return ""
        except Exception:
            continue
    return ""


def matches_format(text: str) -> bool:
    """Devuelve True si el texto contiene al menos MIN_MATCHING_LINES líneas con el formato."""
    count = 0
    for line in text.splitlines():
        line = line.strip()
        if is_matching_line(line):
            count += 1
            if count >= MIN_MATCHING_LINES:
                return True
    return False


def find_and_move():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    drives = get_all_drives()
    print(f"Unidades encontradas: {', '.join(drives)}")
    print(f"Destino: {OUTPUT_DIR}\n")

    found = 0
    scanned = 0
    skipped_permission = 0

    for drive in drives:
        print(f"[>] Escaneando {drive} ...")
        for root, dirs, files in os.walk(drive, topdown=True, onerror=lambda e: None):
            # Saltar carpetas del sistema
            dirs[:] = [
                d for d in dirs
                if d.lower() not in {
                    "windows", "system32", "syswow64", "winsxs",
                    "$recycle.bin", "recovery", "perflogs",
                    "programdata", "appdata",
                }
            ]

            for filename in files:
                if not filename.lower().endswith(".txt"):
                    continue

                filepath = Path(root) / filename
                scanned += 1

                try:
                    sample = read_sample(filepath)
                    if not sample:
                        continue

                    if matches_format(sample):
                        # Nombre aplanado para evitar colisiones
                        safe_name = (
                            str(filepath)
                            .replace(":\\", "__")
                            .replace("\\", "_")
                            .replace("/", "_")
                        )
                        dest = OUTPUT_DIR / safe_name
                        shutil.move(str(filepath), dest)
                        found += 1
                        print(f"  [+] Movido: {filepath}")

                except PermissionError:
                    skipped_permission += 1
                except Exception as e:
                    print(f"  [!] Error en {filepath}: {e}", file=sys.stderr)

    print(f"\n--- Resumen ---")
    print(f"Archivos .txt escaneados : {scanned}")
    print(f"Archivos movidos         : {found}")
    print(f"Saltados (sin permiso)   : {skipped_permission}")
    print(f"Resultado en             : {OUTPUT_DIR}")


if __name__ == "__main__":
    find_and_move()
