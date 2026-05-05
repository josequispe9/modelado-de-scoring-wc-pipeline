# Reporte de entornos GPU — Etapa 5 y 7

Estado de hardware y entornos virtuales GPU por máquina.

---

## Nota operativa — instalación en discos distintos a C:\

Cuando el entorno virtual está en un disco distinto a `C:\` (ej: `D:\`), pip usa `/tmp` (WSL) o `%TEMP%` (Windows) como directorio temporal durante la descarga. Si `C:\` no tiene espacio suficiente, la instalación falla con `Input/output error` o errores similares.

**Solución — WSL (entorno de análisis):**
```bash
mkdir -p /mnt/d/pip-tmp
TMPDIR=/mnt/d/pip-tmp pip install <paquete>
```

**Solución — PowerShell (entorno de transcripciones):**
No aplica en este caso porque `%TEMP%` suele tener espacio suficiente, pero si falla:
```powershell
$env:TEMP = "D:\pip-tmp"
$env:TMP = "D:\pip-tmp"
New-Item -ItemType Directory -Force -Path D:\pip-tmp
pip install <paquete>
```

---

# GASPAR (192.168.9.115)

## Sistema y GPU

| Campo             | Valor                        |
|-------------------|------------------------------|
| GPU               | NVIDIA GeForce RTX 3060 Ti   |
| Compute Cap       | 8.6                          |
| Driver            | 591.74 (soporta hasta CUDA 13.1) |
| VRAM              | 8.0 GB                       |
| SO                | Windows 11 (WDDM)            |
| Disco disponible  | D:\                          |

## Entorno transcripciones (`D:\env-gpu-transcripciones`)

| Campo             | Valor           |
|-------------------|-----------------|
| Python            | 3.13.9          |
| PyTorch           | 2.6.0+cu124     |
| CUDA embebido     | 12.4            |
| GPU disponible    | True            |
| WhisperX          | 3.8.5           |
| psycopg2-binary   | OK              |
| python-dotenv     | OK              |
| minio             | OK              |

```powershell
python -m venv D:\env-gpu-transcripciones
D:\env-gpu-transcripciones\Scripts\activate
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install whisperx
```

> Instalar torch antes que whisperx — si no, whisperx jala la versión CPU automáticamente.

## Entorno análisis (`/mnt/d/env-gpu-analisis` — WSL2)

| Campo             | Valor           |
|-------------------|-----------------|
| Python            | 3.12.3          |
| PyTorch           | 2.10.0+cu128    |
| CUDA embebido     | 12.8            |
| GPU disponible    | True            |
| vLLM              | 0.19.1          |
| openai SDK        | 2.32.0          |

```bash
python3 -m venv /mnt/d/env-gpu-analisis
source /mnt/d/env-gpu-analisis/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install vllm
pip install openai
```

---

# MELCHOR (192.168.9.195)

## Sistema y GPU

| Campo             | Valor                        |
|-------------------|------------------------------|
| GPU               | NVIDIA GeForce RTX 3080      |
| Compute Cap       | 8.6                          |
| Driver            | 591.86 (soporta hasta CUDA 13.1) |
| VRAM              | 10 GB                        |
| SO                | Windows 11 (WDDM)            |
| Disco disponible  | E:\                          |

## Entorno transcripciones (`E:\env-gpu-transcripciones`)

| Campo             | Valor           |
|-------------------|-----------------|
| Ruta              | E:\env-gpu-transcripciones |
| Python            | 3.12.10         |
| PyTorch           | 2.6.0+cu124     |
| CUDA embebido     | 12.4            |
| GPU disponible    | True            |
| WhisperX          | 3.8.5           |
| psycopg2-binary   | OK              |
| python-dotenv     | OK              |
| minio             | OK              |

```powershell
# Redirigir temp a E:\ antes de instalar (C:\ puede no tener espacio)
New-Item -ItemType Directory -Force -Path E:\pip-tmp
$env:TEMP = "E:\pip-tmp"
$env:TMP  = "E:\pip-tmp"

python -m venv E:\env-gpu-transcripciones
E:\env-gpu-transcripciones\Scripts\activate
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install whisperx

# whisperx puede forzar torch a la versión CPU más nueva del PyPI público.
# Reinstalar torch desde el índice cu124 después de whisperx:
pip uninstall -y torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

## Entorno análisis (`/mnt/e/env-gpu-analisis` — WSL2)

| Campo             | Valor           |
|-------------------|-----------------|
| Ruta              | /mnt/e/env-gpu-analisis |
| Python            | 3.12.3          |
| PyTorch           | 2.10.0+cu128    |
| CUDA embebido     | 12.8            |
| GPU disponible    | True            |
| vLLM              | 0.19.1          |
| openai SDK        | 2.32.0          |

```bash
mkdir -p /mnt/e/pip-tmp
python3 -m venv /mnt/e/env-gpu-analisis
source /mnt/e/env-gpu-analisis/bin/activate
TMPDIR=/mnt/e/pip-tmp pip install torch --index-url https://download.pytorch.org/whl/cu124
TMPDIR=/mnt/e/pip-tmp pip install vllm
TMPDIR=/mnt/e/pip-tmp pip install openai
```

---

# BALTAZAR (192.168.9.62)

## Sistema y GPU

| Campo             | Valor                        |
|-------------------|------------------------------|
| GPU               | NVIDIA GeForce RTX 3060 Ti   |
| Compute Cap       | 8.6                          |
| Driver            | 591.74 (soporta hasta CUDA 13.1) |
| VRAM              | 8 GB                         |
| SO                | Windows 11 (WDDM)            |
| Disco disponible  | J:\                          |

## Entorno transcripciones (`J:\env-gpu-transcripciones`)

| Campo             | Valor           |
|-------------------|-----------------|
| Ruta              | J:\env-gpu-transcripciones |
| Python            | 3.13.9          |
| PyTorch           | 2.6.0+cu124     |
| CUDA embebido     | 12.4            |
| GPU disponible    | True            |
| WhisperX          | 3.8.5           |
| psycopg2-binary   | OK              |
| python-dotenv     | OK              |
| minio             | OK              |

```powershell
# Redirigir temp a J:\ antes de instalar (C:\ puede no tener espacio)
New-Item -ItemType Directory -Force -Path J:\pip-tmp
$env:TEMP = "J:\pip-tmp"
$env:TMP  = "J:\pip-tmp"

python -m venv J:\env-gpu-transcripciones
J:\env-gpu-transcripciones\Scripts\activate
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
pip install whisperx

# whisperx suele pisar torch con la versión CPU del PyPI público.
# Reinstalar torch desde el índice cu124 DESPUÉS de whisperx:
pip uninstall -y torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

# Verificar que torch quede con +cu124 y GPU disponible:
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

## Entorno análisis (`/mnt/j/env-gpu-analisis` — WSL2)

| Campo             | Valor           |
|-------------------|-----------------|
| Ruta              | /mnt/j/env-gpu-analisis |
| Python            |                 |
| PyTorch           |                 |
| CUDA embebido     |                 |
| GPU disponible    |                 |
| vLLM              |                 |
| openai SDK        |                 |

```bash
mkdir -p /mnt/j/pip-tmp
python3 -m venv /mnt/j/env-gpu-analisis
source /mnt/j/env-gpu-analisis/bin/activate
TMPDIR=/mnt/j/pip-tmp pip install --upgrade pip
TMPDIR=/mnt/j/pip-tmp pip install torch --index-url https://download.pytorch.org/whl/cu124
TMPDIR=/mnt/j/pip-tmp pip install vllm
TMPDIR=/mnt/j/pip-tmp pip install openai
```
