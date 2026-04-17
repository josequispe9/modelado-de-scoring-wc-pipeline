# Reporte de estado GPU — Etapa 5

Ejecutar cada comando en **gaspar**, **melchor** y **baltazar** y completar los resultados.

---

## 1. GPU y driver

```powershell
nvidia-smi --query-gpu=name,driver_version,memory.total,compute_cap --format=csv
```

| Máquina  | Resultado |
|----------|-----------|
| gaspar   |           |
| melchor  |           |
| baltazar |           |

---

## 2. CUDA del sistema

```powershell
nvcc --version
```

| Máquina  | Resultado |
|----------|-----------|
| gaspar   |           |
| melchor  |           |
| baltazar |           |

---

## 3. PyTorch y CUDA

```powershell
pipeline\venv\Scripts\python.exe -c "import torch; print('PyTorch:', torch.__version__); print('CUDA disponible:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'ninguna')"
```

| Máquina  | Resultado |
|----------|-----------|
| gaspar   |           |
| melchor  |           |
| baltazar |           |

---

## 4. Versión CUDA y cuDNN que ve PyTorch

```powershell
pipeline\venv\Scripts\python.exe -c "import torch; print('CUDA version:', torch.version.cuda); print('cuDNN version:', torch.backends.cudnn.version())"
```

| Máquina  | Resultado |
|----------|-----------|
| gaspar   |           |
| melchor  |           |
| baltazar |           |

---

## 5. VRAM disponible

```powershell
pipeline\venv\Scripts\python.exe -c "import torch; print('VRAM total:', round(torch.cuda.get_device_properties(0).total_memory/1024**3, 1), 'GB'); print('VRAM libre:', round(torch.cuda.memory_reserved(0)/1024**3, 1), 'GB')"
```

| Máquina  | Resultado |
|----------|-----------|
| gaspar   |           |
| melchor  |           |
| baltazar |           |

---

## 6. WhisperX instalado

```powershell
pipeline\venv\Scripts\python.exe -c "import whisperx; print('WhisperX OK')"
```

| Máquina  | Resultado |
|----------|-----------|
| gaspar   |           |
| melchor  |           |
| baltazar |           |

---

## 7. Espacio en disco

```powershell
Get-PSDrive | Where-Object {$_.Used -ne $null} | Select-Object Name, @{N='Libre GB';E={[math]::Round($_.Free/1GB,1)}}, @{N='Total GB';E={[math]::Round(($_.Used+$_.Free)/1GB,1)}}
```

| Máquina  | Resultado |
|----------|-----------|
| gaspar   |           |
| melchor  |           |
| baltazar |           |
