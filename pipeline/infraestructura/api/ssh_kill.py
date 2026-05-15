"""
Mata procesos Python por nombre de script en las máquinas remotas via SSH.
Usa PowerShell + Get-CimInstance para filtrar por CommandLine en Windows.
"""
import logging
import paramiko

log = logging.getLogger(__name__)

# ─── Máquinas por etapa ───────────────────────────────────────────────────────

_G = {"host": "192.168.9.115", "user": "airflow-ssh", "password": "1234"}
_M = {"host": "192.168.9.195", "user": "juan-t3",     "password": "1234"}
_B = {"host": "192.168.9.62",  "user": "bases",       "password": "ruleta"}

MAQUINAS_ETAPA: dict[str, list[dict]] = {
    "descarga": [
        {**_G, "script": "scraping_mitrol.py"},
        {**_M, "script": "scraping_mitrol.py"},
        {**_B, "script": "scraping_mitrol.py"},
    ],
    "creacion_registros": [
        {**_G, "script": "creacion_de_registros.py"},
    ],
    "normalizacion": [
        {**_G, "script": "preprocesar_audios.py"},
        {**_M, "script": "preprocesar_audios.py"},
        {**_B, "script": "preprocesar_audios.py"},
    ],
    "correccion_normalizacion": [
        {**_G, "script": "correccion_normalizacion.py"},
    ],
    "transcripcion": [
        {**_G, "script": "transcribir_audios.py"},
        {**_M, "script": "transcribir_audios.py"},
        {**_B, "script": "transcribir_audios.py"},
    ],
    "correccion_transcripciones": [
        {**_G, "script": "correccion_determinista.py"},
    ],
    "seleccionar_ganador": [
        {**_G, "script": "seleccionar_ganador.py"},
    ],
}


def _kill_en_maquina(host: str, user: str, password: str, script: str) -> dict:
    """
    Conecta por SSH a una máquina Windows y mata todos los procesos Python
    cuyo CommandLine contiene el nombre del script.
    Retorna dict con host, killed (bool) y detalle.
    """
    cmd = (
        f'powershell -NoProfile -Command "'
        f'$procs = Get-CimInstance Win32_Process | '
        f'Where-Object {{ $_.CommandLine -like \'*{script}*\' }}; '
        f'if ($procs) {{ $procs | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}; '
        f'Write-Output (\'killed:\' + ($procs | Measure-Object).Count) }} '
        f'else {{ Write-Output \'none\' }}"'
    )

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, username=user, password=password, timeout=8)
        _, stdout, stderr = client.exec_command(cmd, timeout=10)
        output = stdout.read().decode().strip()
        err    = stderr.read().decode().strip()
        killed = output.startswith("killed:")
        count  = int(output.split(":")[1]) if killed else 0
        log.info("SSH kill %s [%s]: %s", host, script, output or err)
        return {"host": host, "killed": killed, "count": count, "detalle": output or err}
    except Exception as e:
        log.warning("SSH kill %s [%s] falló: %s", host, script, e)
        return {"host": host, "killed": False, "count": 0, "detalle": str(e)}
    finally:
        client.close()


def matar_procesos(etapa: str) -> list[dict]:
    """
    Mata los procesos de la etapa dada en todas sus máquinas.
    Retorna lista de resultados por máquina.
    """
    maquinas = MAQUINAS_ETAPA.get(etapa, [])
    if not maquinas:
        return [{"host": "—", "killed": False, "count": 0, "detalle": f"etapa '{etapa}' sin maquinas configuradas"}]
    return [_kill_en_maquina(**m) for m in maquinas]
