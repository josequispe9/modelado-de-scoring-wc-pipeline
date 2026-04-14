import os
import glob
import subprocess
from pathlib import Path
import shutil
import json

# ===== CONFIGURACIÓN =====
INPUT_DIR = ""
OUTPUT_DIR = ""


def check_ffmpeg():
    """Verifica si ffmpeg está instalado"""
    try:
        subprocess.run(['ffmpeg', '-version'],
                      stdout=subprocess.PIPE,
                      stderr=subprocess.PIPE,
                      check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def build_ffmpeg_filter(params):
    """
    Construye la cadena de filtros de ffmpeg según parámetros

    Returns:
        str: Cadena de filtros para ffmpeg (-af parameter)
    """
    filters = []

    # 1. Remover silencios largos al inicio y final + en medio
    # stop_periods=-1 significa que también remueve silencios en medio del audio
    silence_filter = (
        f"silenceremove="
        f"start_periods=1:"           # Remover silencio al inicio
        f"start_silence={params['silence_duration']}:"
        f"start_threshold={params['silence_threshold']}:"
        f"stop_periods=-1:"           # Remover silencios en todo el audio
        f"stop_silence={params['silence_duration']}:"
        f"stop_threshold={params['silence_threshold']}:"
        f"detection=peak"             # Método de detección
    )
    filters.append(silence_filter)

    # 2. Filtro pasa-altos (opcional - remueve frecuencias bajas < 200Hz)
    if params.get('highpass_filter', False):
        filters.append("highpass=f=200")

    # 3. Reducción de ruido básica (opcional - MUY lento)
    if params.get('noise_reduction', False):
        filters.append("afftdn=nf=-25")

    # 4. Normalización de audio (loudnorm - EBU R128)
    if params.get('normalize', True):
        # Normalización en 2 pasos para mejor resultado
        filters.append("loudnorm=I=-16:TP=-1.5:LRA=11")

    return ','.join(filters)

def process_audio(input_file, output_file, params):
    """
    Procesa un archivo de audio con ffmpeg

    Args:
        input_file (str): Ruta del archivo de entrada
        output_file (str): Ruta del archivo de salida
        params (dict): Parámetros de procesamiento

    Returns:
        bool: True si exitoso, False si hay error
    """
    # Construir filtros
    audio_filter = build_ffmpeg_filter(params)

    # Comando ffmpeg
    cmd = [
        'ffmpeg',
        '-i', input_file,
        '-af', audio_filter,
        '-ar', '16000',        # Sample rate 16kHz (óptimo para Whisper)
        '-ac', '1',            # Mono (Whisper funciona mejor con mono)
        '-c:a', 'pcm_s16le',   # Codec WAV sin compresión
        '-y',                  # Sobrescribir sin preguntar
        output_file
    ]

    try:
        # Ejecutar comando (ocultar output verbose)
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=300  # Timeout de 5 minutos por archivo
        )
        return True

    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT: El procesamiento tardó más de 5 minutos")
        return False

    except subprocess.CalledProcessError as e:
        print(f"  ERROR ffmpeg: {e.stderr.decode('utf-8', errors='ignore')[:200]}")
        return False

    except Exception as e:
        print(f"  ERROR: {str(e)}")
        return False

def get_audio_duration(file_path):
    """
    Obtiene la duración de un archivo de audio usando ffprobe

    Returns:
        float: Duración en segundos, o None si hay error
    """
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        duration = float(result.stdout.decode('utf-8').strip())
        return duration
    except Exception:
        return None

def format_duration(seconds):
    """Formatea segundos a MM:SS"""
    if seconds is None:
        return "??:??"
    mins = int(seconds // 60)
    secs = int()
    return f"{mins:02d}:{secs:02d}"


def main():
    print("=" * 70)
    print("BATCH 1: PREPROCESAR AUDIOS")
    print("=" * 70)

    # Verificar ffmpeg
    if not check_ffmpeg():
        print("\nERROR: ffmpeg no está instalado o no está en el PATH")
        print("\nPara instalar ffmpeg:")
        print("  - Ubuntu/Debian: sudo apt install ffmpeg")
        print("  - Windows: descargar de https://ffmpeg.org/download.html")
        print("  - macOS: brew install ffmpeg")
        return

    print("ffmpeg encontrado")

    # Mostrar configuración
    print("\nConfiguración de procesamiento:")
    print(f"  - Umbral de silencio: {AUDIO_PARAMS['silence_threshold']}")
    print(f"  - Duración mínima de silencio: {AUDIO_PARAMS['silence_duration']}s")
    print(f"  - Normalización: {'Sí' if AUDIO_PARAMS['normalize'] else 'No'}")
    print(f"  - Reducción de ruido: {'Sí' if AUDIO_PARAMS['noise_reduction'] else 'No'}")
    print(f"  - Filtro pasa-altos: {'Sí' if AUDIO_PARAMS['highpass_filter'] else 'No'}")


if __name__ == '__main__':
    main()
