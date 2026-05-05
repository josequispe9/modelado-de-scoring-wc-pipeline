# Networking — Windows nativo · Docker Desktop · WSL2

Describe cómo se comunican los tres entornos de ejecución del pipeline en Gaspar.

---

## Los tres entornos

```
┌──────────────────────────────────────────────────────────────┐
│  Windows nativo                                              │
│                                                              │
│  Pipeline API  :8001  (uvicorn)                              │
│  Etapas 1–5   (scripts Python con pipeline\venv)             │
│  Etapa 6a     correccion_determinista.py  (CPU, pipeline\venv)│
│                                                              │
│  ┌────────────────────────────────────────────┐             │
│  │  Docker Desktop (backend WSL2)             │             │
│  │                                            │             │
│  │  postgres  :5432   (scoring + airflow)     │             │
│  │  redis     :6379                           │             │
│  │  airflow-* :8080                           │             │
│  └────────────────────────────────────────────┘             │
│                                                              │
│  ┌────────────────────────────────────────────┐             │
│  │  WSL2 — Ubuntu                             │             │
│  │                                            │             │
│  │  Etapa 6b  correccion_llm.py  (vLLM, GPU) │             │
│  │  Etapa 7   analisis LLM       (vLLM, GPU) │             │
│  └────────────────────────────────────────────┘             │
└──────────────────────────────────────────────────────────────┘
```

Los tres entornos corren en la misma máquina física (Gaspar, 192.168.9.115).
MinIO vive en Melchor (192.168.9.195) y es accesible directamente por LAN desde los tres entornos.

---

## Por qué los scripts de etapa 6 y 7 usan WSL2

vLLM requiere Linux. No existe wheel de vLLM para Windows. Por eso los scripts que
cargan modelos LLM (etapa 6b `correccion_llm.py`, etapa 7) corren en el Ubuntu de WSL2
usando un venv de GPU instalado en Linux (`/mnt/d/env-gpu-analisis` o similar).

Los scripts CPU-only (etapa 6a `correccion_determinista.py`) pueden correr en Windows
nativo con `pipeline\venv` — no necesitan GPU ni Linux.

---

## Cómo Docker expone sus puertos en Gaspar

Docker Desktop usa WSL2 como backend. Al exponer un puerto (`ports: "5432:5432"`),
Docker lo bindea en el host de **dos formas**:

| Dirección      | Accesible desde              |
|----------------|------------------------------|
| `[::1]:5432`   | Windows nativo (IPv6 loopback) |
| `0.0.0.0:5432` | LAN (requiere portproxy — ver más abajo) |

**Observado en Gaspar:** después de cambios en `.wslconfig` y `wsl --shutdown`,
Docker queda vinculado solo a `[::1]:5432`. Para verificar:

```powershell
netstat -an | findstr 5432
```

---

## Comunicación Windows nativo → PostgreSQL (Docker)

Los scripts de etapas 1–5 y la Pipeline API corren en Windows nativo y conectan a
Postgres vía `SCORING_DB_URL` del `.env.tuberia`:

```
SCORING_DB_URL=postgresql://scoring:scoring@localhost:5432/scoring
```

`localhost` en Windows resuelve a `::1` (IPv6 loopback) — donde Docker está escuchando.
**No usar la IP de LAN `192.168.9.115`**: Docker en estado normal no la expone en esa interfaz.

> **Nota:** La URL de Airflow dentro de Docker usa el hostname interno `postgres`
> (red Docker), no `localhost`. El override está en el `docker-compose.yml`:
> `SCORING_DB_URL: postgresql+psycopg2://scoring:scoring@postgres/scoring`

---

## Comunicación WSL2 → PostgreSQL (Docker)

Desde Ubuntu WSL2, `localhost` apunta a la propia instancia de Ubuntu — no a Windows.
Para conectar al Postgres de Docker hay dos opciones:

### Opción A — IP de LAN con portproxy (configuración actual)

Portproxy activo en Gaspar que reenvía `0.0.0.0:5432 → ::1:5432`:

```powershell
# Crear (como admin en PowerShell)
netsh interface portproxy add v4tov6 listenport=5432 listenaddress=0.0.0.0 connectport=5432 connectaddress=::1
netsh advfirewall firewall add rule name="Postgres 5432" dir=in action=allow protocol=TCP localport=5432

# Verificar
netsh interface portproxy show all   # debe mostrar v4tov6: 0.0.0.0:5432 → ::1:5432
netstat -an | findstr 5432           # debe mostrar 0.0.0.0:5432 LISTENING
```

Con este portproxy activo, los scripts de WSL2 conectan usando la IP de LAN:

```
SCORING_DB_URL=postgresql://scoring:scoring@192.168.9.115:5432/scoring
```

Esta URL también es la que usan Melchor y Baltazar para alcanzar el Postgres de Gaspar.

### Opción B — networkingMode=mirrored (alternativa, no activa)

Con `C:\Users\qjose\.wslconfig`:
```ini
[wsl2]
networkingMode=mirrored
```
WSL2 espeja las interfaces de Windows, por lo que `localhost` en Ubuntu apunta
directamente a los servicios de Windows (incluido Docker en `[::1]:5432`).
Requiere `wsl --shutdown` para aplicar. **No está activo actualmente** — fue borrado
porque generaba efectos secundarios en otros servicios.

---

## Portproxy activo en Gaspar (estado actual)

```
Escuchar en ipv4:       Conectar a ipv6:
0.0.0.0:5432       →   ::1:5432        (PostgreSQL Docker — acceso LAN y WSL2)
```

El portproxy no persiste al reiniciar Windows. Para hacerlo permanente, crear una
tarea programada similar a la del portproxy SSH de WSL (ver etapa 6b si se implementa
persistencia):

```powershell
$action = New-ScheduledTaskAction -Execute "netsh.exe" `
    -Argument "interface portproxy add v4tov6 listenport=5432 listenaddress=0.0.0.0 connectport=5432 connectaddress=::1"
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName "Postgres portproxy" -Action $action -Trigger $trigger -RunLevel Highest -Force
```

---

## Flujo de comunicación por etapa

| Etapa | Entorno de ejecución | Postgres | MinIO |
|-------|----------------------|----------|-------|
| 1–5   | Windows nativo (`pipeline\venv`) | `localhost:5432` | `192.168.9.195:9001` |
| 6a `correccion_determinista.py` | Windows nativo (`pipeline\venv`) | `localhost:5432` | `192.168.9.195:9001` |
| 6b `correccion_llm.py` | WSL2 Ubuntu (venv GPU Linux) | `192.168.9.115:5432` (via portproxy) | `192.168.9.195:9001` |
| 7–8 análisis LLM | WSL2 Ubuntu (venv GPU Linux) | `192.168.9.115:5432` (via portproxy) | `192.168.9.195:9001` |
| Pipeline API | Windows nativo (`api\venv`) | `localhost:5432` | `192.168.9.195:9001` |
| Airflow containers | Docker (red interna) | `postgres:5432` (hostname Docker) | `192.168.9.195:9001` |

---

## Variables de entorno según entorno de ejecución

El `.env.tuberia` tiene una sola `SCORING_DB_URL`. Usar `localhost` para que funcione
en Windows nativo (la mayoría de las etapas). Los scripts de WSL2 necesitan sobreescribir
la variable antes de correr:

```bash
# En WSL2 — sobreescribir SCORING_DB_URL para apuntar a Gaspar por LAN
export SCORING_DB_URL=postgresql://scoring:scoring@192.168.9.115:5432/scoring
python correccion_llm.py
```

O bien el DAG de Airflow puede pasar la variable correcta vía SSH:

```python
# En el DAG — comando para WSL2
f'export SCORING_DB_URL=postgresql://scoring:scoring@192.168.9.115:5432/scoring && '
f'wsl -d Ubuntu -e bash -c "source /mnt/d/env-gpu-analisis/bin/activate && python ..."'
```

---

## Resumen de puertos relevantes en Gaspar

| Puerto | Servicio | Bindeo actual | Accesible desde |
|--------|----------|---------------|-----------------|
| 5432 | PostgreSQL (Docker) | `[::1]:5432` + portproxy `0.0.0.0:5432` | Windows nativo (`localhost`), LAN, WSL2 |
| 6379 | Redis (Docker) | `[::1]:6379` (típico) | Windows nativo, containers Docker |
| 8080 | Airflow UI (Docker) | `0.0.0.0:8080` | LAN |
| 8001 | Pipeline API (Windows nativo) | `0.0.0.0:8001` | LAN, Dashboard |
| 2222 | (eliminado — era portproxy mal configurado) | — | — |
