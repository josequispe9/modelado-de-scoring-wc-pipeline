"""
Etapa 1 — Descarga de audios desde Mitrol → MinIO.

Abre un navegador visible, inicia sesion, aplica los filtros definidos en config.py,
extrae la tabla de grabaciones y sube cada audio WAV al bucket MinIO:
    modelado-de-scoring-wc / audios / YYYY-MM-DD / <nombre>_<CUENTA>.wav

Uso:
    python scraping_mitrol.py

Requiere:
    - .env.pipeline en la raiz del proyecto con las variables de Mitrol y MinIO
    - pip install -r requirements-pipeline.txt
    - Selenium Manager descarga ChromeDriver automaticamente

Estructura de iframes (fija, no cambia entre sesiones):
    frame(0) — menu de navegacion lateral
    frame(1) — formulario de filtros
    frame(2) — tabla de resultados / paginacion
"""

import io
import os
import time
import logging
import requests
import psycopg2
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from minio import Minio
from minio.error import S3Error
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from config import DEFAULTS

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Configuracion ────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parents[3]
load_dotenv(ROOT_DIR / ".env.tuberia")

CUENTA          = os.environ["MITROL_CUENTA"]           # "G", "M" o "B"
MITROL_USER     = os.environ[f"mitrol_user_{CUENTA}"]
MITROL_PASSWORD = os.environ[f"mitrol_password_{CUENTA}"]
MITROL_URL      = "https://apps-alc.mitrol.cloud/reportes/login.aspx"

TIMEOUT = 60  # segundos maximos de espera por elemento

# ─── MinIO ────────────────────────────────────────────────────────────────────
MINIO_BUCKET   = "modelado-de-scoring-wc"
FECHA_CARPETA  = datetime.now().strftime("%Y-%m-%d")
MINIO_PREFIX   = f"audios/{FECHA_CARPETA}"

minio_client = Minio(
    os.environ["MINIO_ENDPOINT"],
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=False,
)


# ─── Parámetros ───────────────────────────────────────────────────────────────
def obtener_params() -> dict:
    """
    Lee los parámetros desde pipeline_params en Postgres (clave: descarga_G/M/B).
    Si no puede conectar o no existe la fila, usa config.py DEFAULTS como fallback.
    """
    db_url = os.getenv("SCORING_DB_URL")
    if not db_url:
        log.info("SCORING_DB_URL no configurado — usando DEFAULTS de config.py")
        return DEFAULTS.copy()

    clave = f"descarga_{CUENTA}"
    try:
        conn = psycopg2.connect(db_url)
        cur  = conn.cursor()
        cur.execute("SELECT valor FROM pipeline_params WHERE clave = %s", (clave,))
        row  = cur.fetchone()
        cur.close()
        conn.close()

        if row:
            params = DEFAULTS.copy()
            params.update(row[0])  # row[0] es JSONB → dict
            log.info("Params cargados desde Postgres (clave: %s)", clave)
            return params

        log.info("Sin entrada en pipeline_params para '%s' — usando DEFAULTS", clave)
        return DEFAULTS.copy()

    except Exception as e:
        log.warning("No se pudo leer pipeline_params: %s — usando DEFAULTS", e)
        return DEFAULTS.copy()


# ─── Browser ──────────────────────────────────────────────────────────────────
def crear_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)
    return driver


# ─── Navegacion ───────────────────────────────────────────────────────────────
def login(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    log.info("Navegando a la pagina de login (cuenta %s)...", CUENTA)
    driver.get(MITROL_URL)
    wait.until(EC.presence_of_element_located((By.ID, "TboxUser")))
    driver.find_element(By.ID, "TboxUser").send_keys(MITROL_USER)
    driver.find_element(By.ID, "TboxPass").send_keys(MITROL_PASSWORD)
    driver.find_element(By.XPATH, '//*[@id="Btn_LogIn_lnk_Button"]').click()
    log.info("Login enviado, esperando carga del menu...")


def navegar_a_grabaciones(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    time.sleep(3)
    driver.switch_to.default_content()
    driver.switch_to.frame(0)  # menu lateral
    wait.until(EC.element_to_be_clickable((By.ID, "tree1t46"))).click()
    log.info("Menu grabaciones abierto, seleccionando sub-opcion...")
    wait.until(EC.element_to_be_clickable((By.ID, "tree1t47"))).click()
    log.info("Pantalla de filtros cargada.")


def aplicar_filtros(driver: webdriver.Chrome, wait: WebDriverWait, params: dict) -> None:
    log.info("Aplicando filtros: %s", params)
    time.sleep(2)
    driver.switch_to.default_content()
    driver.switch_to.frame(1)  # formulario de filtros

    wait.until(EC.presence_of_element_located((By.ID, "PEXT_MaxRow_Ddl1")))
    Select(driver.find_element(By.ID, "PEXT_MaxRow_Ddl1")).select_by_value(params["cant_registros_max"])

    driver.find_element(By.ID, "PEXT_FechaRango_Rad1").click()
    time.sleep(0.5)

    def set_fecha(field_id: str, valor: str) -> None:
        campo = driver.find_element(By.ID, field_id)
        driver.execute_script("arguments[0].value = arguments[1];", campo, valor)
        driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", campo)
        try:
            WebDriverWait(driver, 2).until(EC.alert_is_present())
            driver.switch_to.alert.accept()
        except TimeoutException:
            pass

    set_fecha("PEXT_FechaRango_TBoxFch1", params["fecha_inicio"])
    set_fecha("PEXT_FechaRango_TBoxFch2", params["fecha_fin"])

    Select(driver.find_element(By.ID, "PEXT_HIni_Ddl1")).select_by_value(params["hora_inicio"])
    Select(driver.find_element(By.ID, "PEXT_HFin_Ddl1")).select_by_value(params["hora_fin"])
    Select(driver.find_element(By.ID, "PEXT_MinDuracion_Ddl2")).select_by_value(params["duracion_min"])
    Select(driver.find_element(By.ID, "PEXT_MaxDuracion_Ddl2")).select_by_value(params["duracion_max"])

    if params.get("cliente"):
        driver.find_element(By.ID, "PEXT_Cliente_Tbox1").send_keys(params["cliente"])

    log.info("Filtros aplicados.")


def ejecutar_reporte(driver: webdriver.Chrome) -> None:
    try:
        driver.find_element(By.ID, "Btn_execBotton_lbl_Button").click()
    except Exception:
        driver.find_element(By.ID, "Btn_execBotton_span_lnkBtn").click()
    log.info("Reporte ejecutado, esperando resultados en frame(2) (max 2 min)...")

    driver.switch_to.default_content()
    driver.switch_to.frame(2)  # tabla de resultados

    for _ in range(60):
        links = driver.find_elements(By.XPATH, "//a[contains(@href, 'GetWave.ashx')]")
        if links:
            log.info("Tabla cargada. Audios en pagina 1: %d", len(links))
            return
        body = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "sin resultados" in body or "no se encontraron" in body:
            raise Exception("El reporte no retorno resultados con los filtros indicados.")
        time.sleep(2)

    raise TimeoutException("Timeout esperando la tabla de resultados en frame(2).")


# ─── Extraccion de datos ──────────────────────────────────────────────────────
def extraer_filas(driver: webdriver.Chrome) -> list[dict]:
    """
    Extrae los registros de la pagina actual (driver debe estar en frame(2)).

    Columnas reales — 33 celdas por fila de datos:
      0=spacer  1=INICIO  2=AUDIO  3-5=MAIL  6-7=CHAT  8=PANTALLA
      9=IDINTERACCION  10=SEGMENTO  11=DUR_TOTAL  12=DUR_AUDIO
      13=IDGRUPO  14=GRUPO  15=LOGINID  16=AGENTE  17=CLIENTE
      18=EXTENSION  19=IDEMPRESA  20=EMPRESA  21=IDCAMPANIA
      22=CAMPANIA  23=SENTIDO  24=TIPIFICACION  25=CLASE_TIP  26=ARCHIVO
    """
    links_audio = driver.find_elements(By.XPATH, "//a[contains(@href, 'GetWave.ashx')]")
    log.info("Links de audio encontrados: %d", len(links_audio))

    registros = []
    for link in links_audio:
        try:
            fila   = link.find_element(By.XPATH, "./ancestor::tr[1]")
            celdas = fila.find_elements(By.TAG_NAME, "td")
            if len(celdas) < 27:
                continue
            registros.append({
                "inicio":             celdas[1].text.strip(),
                "audio_url":          link.get_attribute("href"),
                "id_interaccion":     celdas[9].text.strip(),
                "duracion_total":     celdas[11].text.strip(),
                "duracion_audio":     celdas[12].text.strip(),
                "agente":             celdas[16].text.strip(),
                "cliente":            celdas[17].text.strip(),
                "extension":          celdas[18].text.strip(),
                "empresa":            celdas[20].text.strip(),
                "campania":           celdas[22].text.strip(),
                "tipificacion":       celdas[24].text.strip(),
                "clase_tipificacion": celdas[25].text.strip(),
                "archivo":            celdas[26].text.strip(),
            })
        except Exception as e:
            log.warning("Error extrayendo fila: %s", e)

    return registros


# ─── Subida a MinIO ───────────────────────────────────────────────────────────
OMITIDO = "omitido"  # sentinel: objeto ya existe en MinIO

def subir_audio(session: requests.Session, registro: dict):
    """
    Descarga el audio desde Mitrol y lo sube a MinIO.
    Ruta destino: audios/YYYY-MM-DD/<nombre>_<CUENTA>.wav

    Retorna:
      str (object_name) → subido correctamente
      OMITIDO           → ya existia en MinIO
      None              → error
    """
    nombre_base = registro["archivo"] or registro["id_interaccion"]
    nombre      = f"{nombre_base}_{CUENTA}.wav"
    object_name = f"{MINIO_PREFIX}/{nombre}"

    # Verificar si ya existe en MinIO
    try:
        minio_client.stat_object(MINIO_BUCKET, object_name)
        log.info("Ya existe en MinIO, omitiendo: %s", nombre)
        return OMITIDO
    except S3Error:
        pass  # no existe, continuar con la descarga

    try:
        response = session.get(registro["audio_url"], stream=True, timeout=120)
        response.raise_for_status()

        # Leer a buffer en memoria para conocer el tamaño antes de subir
        buffer = io.BytesIO()
        for chunk in response.iter_content(chunk_size=65536):
            buffer.write(chunk)
        size = buffer.tell()
        buffer.seek(0)

        minio_client.put_object(
            MINIO_BUCKET,
            object_name,
            buffer,
            size,
            content_type="audio/wav",
        )
        log.info("Subido: %s (%.1f MB)", nombre, size / 1_000_000)
        return object_name

    except Exception as e:
        log.error("Error subiendo %s: %s", nombre, e)
        return None


def obtener_sesion_requests(driver: webdriver.Chrome) -> requests.Session:
    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie["name"], cookie["value"])
    return session


# ─── Paginacion ───────────────────────────────────────────────────────────────
def obtener_total_paginas(driver: webdriver.Chrome) -> int:
    try:
        return int(driver.find_element(By.ID, "RViewer_ctl05_ctl00_TotalPages").text.strip())
    except Exception:
        return 1


def ir_a_pagina_siguiente(driver: webdriver.Chrome) -> bool:
    """Click en 'Siguiente' y espera que cambie el numero de pagina (max 45 s)."""
    try:
        boton = driver.find_element(By.ID, "RViewer_ctl05_ctl00_Next_ctl00_ctl00")
    except Exception:
        return False

    pagina_antes = driver.find_element(By.ID, "RViewer_ctl05_ctl00_CurrentPage").get_attribute("value")
    driver.execute_script("arguments[0].click();", boton)

    fin = time.time() + 45
    while time.time() < fin:
        try:
            if driver.find_element(By.ID, "RViewer_ctl05_ctl00_CurrentPage").get_attribute("value") != pagina_antes:
                time.sleep(1)
                return True
        except Exception:
            pass
        time.sleep(0.5)

    log.warning("Timeout esperando cambio de pagina")
    return False


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    params = obtener_params()
    driver = crear_driver()
    wait   = WebDriverWait(driver, TIMEOUT)

    log.info("Destino MinIO: %s/%s/", MINIO_BUCKET, MINIO_PREFIX)

    try:
        login(driver, wait)
        navegar_a_grabaciones(driver, wait)
        aplicar_filtros(driver, wait, params)
        ejecutar_reporte(driver)  # deja el driver en frame(2)

        total_paginas = obtener_total_paginas(driver)
        log.info("Total de paginas: %d", total_paginas)

        session     = obtener_sesion_requests(driver)
        subidos     = 0
        omitidos    = 0
        errores     = 0
        total_audios = 0

        for pagina in range(1, total_paginas + 1):
            log.info("── Pagina %d/%d ──", pagina, total_paginas)
            registros = extraer_filas(driver)
            total_audios += len(registros)

            for registro in registros:
                nombre    = registro.get("archivo") or registro["id_interaccion"]
                resultado = subir_audio(session, registro)
                if resultado is None:
                    errores += 1
                    log.warning("Error en %s, continuando", nombre)
                elif resultado == OMITIDO:
                    omitidos += 1
                else:
                    subidos += 1

            if pagina < total_paginas and not ir_a_pagina_siguiente(driver):
                log.error("No se pudo avanzar a pagina %d. Deteniendo.", pagina + 1)
                break

        log.info(
            "Finalizado — paginas: %d | audios: %d | subidos: %d | omitidos: %d | errores: %d",
            total_paginas, total_audios, subidos, omitidos, errores,
        )

    except TimeoutException as e:
        log.error("Timeout esperando elemento: %s", e)
    except Exception as e:
        log.error("Error inesperado: %s", e)
        raise
    finally:
        if os.getenv("MODO_INTERACTIVO", "0") == "1":
            input("Presiona ENTER para cerrar el navegador...")
            driver.quit()
        # Modo Airflow: el navegador queda abierto para auditar.
        # El proceso termina y Airflow marca la tarea como completada.


if __name__ == "__main__":
    main()
