# Setup etapa 6 — Melchor y Baltazar

Instrucciones para dejar lista la imagen Docker `pipeline-vllm` en Melchor y Baltazar.
La etapa 6 (corrección LLM de transcripciones) corre dentro de un contenedor Docker con GPU.
El código no se copia en la imagen — se monta como volumen desde el disco local.

---

## Requisitos previos (ambas PCs)

- Docker Desktop instalado y corriendo
- GPU NVIDIA visible en Docker: `docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu20.04 nvidia-smi`
- El proyecto clonado/copiado en la ruta correspondiente
- `.env.tuberia` en la raíz del proyecto

---

## MELCHOR (192.168.9.195 — RTX 3080 10 GB)

### 1. Sincronizar el proyecto

Asegurate de que la carpeta del proyecto esté actualizada en:
```
C:\Users\JUAN-T3\Desktop\modelado de scoring WC
```

### 2. Crear directorios de caché

El modelo LLM se descarga una sola vez y queda cacheado en `E:\`.
```powershell
mkdir E:\.cache\huggingface
mkdir E:\.cache\vllm
```

### 3. Construir la imagen

Desde PowerShell, en la raíz del proyecto:
```powershell
cd "C:\Users\JUAN-T3\Desktop\modelado de scoring WC"
docker build -t pipeline-vllm -f pipeline\infraestructura\docker\vllm\Dockerfile .
```

> La imagen base `vllm/vllm-openai:latest` pesa ~20 GB — la primera descarga tarda bastante.

### 4. Verificar

```powershell
docker run --rm --gpus all pipeline-vllm python3 -c "import vllm; import torch; print('vllm OK | GPU:', torch.cuda.is_available())"
```

Debe imprimir: `vllm OK | GPU: True`

---

## BALTAZAR (192.168.9.62 — RTX 3060 Ti 8 GB)

### 1. Sincronizar el proyecto

Asegurate de que la carpeta del proyecto esté actualizada en:
```
C:\Users\Bases\Desktop\modelado de scoring WC
```

### 2. Crear directorios de caché

```powershell
mkdir J:\.cache\huggingface
mkdir J:\.cache\vllm
```

### 3. Construir la imagen

```powershell
cd "C:\Users\Bases\Desktop\modelado de scoring WC"
docker build -t pipeline-vllm -f pipeline\infraestructura\docker\vllm\Dockerfile .
```

### 4. Verificar

```powershell
docker run --rm --gpus all pipeline-vllm python3 -c "import vllm; import torch; print('vllm OK | GPU:', torch.cuda.is_available())"
```

---

## Notas

- **Postgres**: Melchor y Baltazar se conectan a Gaspar por LAN (`192.168.9.115:5432`). Verificar que el portproxy esté activo en Gaspar antes de correr la etapa.
- **Modelo**: Por defecto se usa `Qwen/Qwen2.5-3B-Instruct-AWQ`. Se descarga automáticamente en el primer run y queda en `E:\.cache\huggingface` (Melchor) o `J:\.cache\huggingface` (Baltazar).
- **VRAM**: La imagen base de vLLM en WSL2 sobreestima la VRAM disponible. El parámetro `gpu_memory_utilization: 0.50` en `config_llm.py` compensa esto — no subir sin probar.
- **Reconstruir la imagen**: Solo hace falta si cambia el `Dockerfile`. Los cambios en los scripts Python no requieren rebuild porque el código se monta como volumen.
