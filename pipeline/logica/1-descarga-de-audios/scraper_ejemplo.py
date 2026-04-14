from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import os
import requests
import config
from webdriver_manager.chrome import ChromeDriverManager
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, Event
import queue
import json
import sys
from datetime import datetime

# ========== CONFIGURACIÓN DE USUARIOS ==========
USUARIOS_A_SELECCIONAR = [
    "MZA 1", "MZA 2", "MZA 3", "MZA 4", "MZA 5", "MZA 6", "MZA 7", "MZA 8", "MZA 9", "MZA 10", "MZA 11", "MZA 12", "MZA 13", "MZA 14", "MZA 15", "MZA 16", "MZA 17", "MZA 18", "MZA 19", "MZA 20",
    "MZA 21", "MZA 22", "MZA 23", "MZA 24", "MZA 25", "MZA 26", "MZA 27", "MZA 28", "MZA 29", "MZA 30", "MZA 31", "MZA 32", "MZA 33", "MZA 34", "MZA 35", "MZA 36", "MZA 37", "MZA 38", "MZA 39", "MZA 40",
    "MZA 41", "MZA 42", "MZA 43", "MZA 44", "MZA 45", "MZA 306", "MZA 313", "MZA 314", "MZA 316", "MZA Sup", "MZA_Sup_Calidad", "MZA Sup2", "MZA Sup3", "MZA Sup4", "MZA_Sup_Calidad3", "MZA_Sup_Calidad4",
    "MZA 72", "MZA 73", "MZA 74", "MZA 75", "MZA 76", "MZA 77", "MZA 78", "MZA 79", "MZA 80", "MZA 81", "MZA 82", "MZA 83"
]

# ========== CONFIGURACIÓN INICIAL ==========
carpeta_descargas = config.carpeta_audios
archivo_checkpoint = os.path.join(carpeta_descargas, "checkpoint.json")
archivo_log = os.path.join(carpeta_descargas, "descarga_log.txt")

if not os.path.exists(carpeta_descargas):
    os.makedirs(carpeta_descargas)
    print(f"Carpeta creada: {carpeta_descargas}")

# Configuración de descarga concurrente
MAX_WORKERS = 20
TIMEOUT_DESCARGA = 120
CHUNK_SIZE = 131072  # 128KB
QUEUE_SIZE = 200
MAX_REINTENTOS_NAVEGACION = 12

# CONFIGURACIÓN AUTOMÁTICA DE HORARIOS
HORA_INICIO_AUTO = "08"  # 8:00 AM
HORA_FIN_AUTO = "23"     # 11:00 PM
DURACION_MINIMA = "01"   # Mínimo 1 minuto

# ========== SISTEMA DE LOGGING ==========
def log(mensaje, consola=True):
    """Escribe en log y opcionalmente en consola"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"[{timestamp}] {mensaje}"
    try:
        with open(archivo_log, 'a', encoding='utf-8') as f:
            f.write(linea + "\n")
    except Exception:
        pass
    
    if consola:
        print(mensaje)

# ========== SISTEMA DE CHECKPOINT ==========
def guardar_checkpoint(pagina_actual, total_paginas, fecha, hora_inicio, hora_final):
    """Guarda el estado actual para poder reanudar"""
    checkpoint = {
        "pagina_actual": pagina_actual,
        "total_paginas": total_paginas,
        "fecha": fecha,
        "hora_inicio": hora_inicio,
        "hora_final": hora_final,
        "timestamp": datetime.now().isoformat()
    }
    try:
        with open(archivo_checkpoint, 'w', encoding='utf-8') as f:
            json.dump(checkpoint, f, indent=2)
    except Exception as e:
        log(f"⚠️ Error guardando checkpoint: {e}")

def cargar_checkpoint():
    """Carga el último checkpoint si existe"""
    if os.path.exists(archivo_checkpoint):
        try:
            with open(archivo_checkpoint, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    return None

def eliminar_checkpoint():
    """Elimina el checkpoint al finalizar"""
    if os.path.exists(archivo_checkpoint):
        try:
            os.remove(archivo_checkpoint)
        except Exception:
            pass

# ========== VARIABLE GLOBAL DE COOKIES ==========
session_cookies_global = {}

# ========== CACHE DE ARCHIVOS EXISTENTES ==========
archivos_existentes_cache = set()
cache_lock = Lock()

def cargar_cache_archivos():
    """Carga en memoria todos los archivos .wav existentes para verificación rápida"""
    global archivos_existentes_cache
    try:
        archivos = [f.lower() for f in os.listdir(carpeta_descargas) if f.lower().endswith('.wav')]
        with cache_lock:
            archivos_existentes_cache = set(archivos)
        if len(archivos_existentes_cache) > 0:
            log(f"📦 Cache cargado: {len(archivos_existentes_cache)} archivos existentes detectados")
    except Exception as e:
        log(f"⚠️ Error cargando cache de archivos: {e}")
        archivos_existentes_cache = set()

def archivo_existe(nombre_archivo):
    """Verifica si un archivo ya existe (usa cache para rapidez)"""
    with cache_lock:
        return nombre_archivo.lower() in archivos_existentes_cache

def agregar_a_cache(nombre_archivo):
    """Agrega un archivo al cache thread-safe"""
    with cache_lock:
        archivos_existentes_cache.add(nombre_archivo.lower())

# ========== CONTADORES THREAD-SAFE ==========
class ContadorSeguro:
    def __init__(self):
        self.lock = Lock()
        self.exitos = 0
        self.errores = 0
        self.omitidos = 0
        self.total = 0
        self.descargando = 0
        self.paginas_procesadas = 0
    
    def incrementar_exito(self):
        with self.lock:
            self.exitos += 1
    
    def incrementar_error(self):
        with self.lock:
            self.errores += 1
    
    def incrementar_omitido(self):
        with self.lock:
            self.omitidos += 1
    
    def set_total(self, total):
        with self.lock:
            self.total = total
    
    def incrementar_descargando(self):
        with self.lock:
            self.descargando += 1
    
    def decrementar_descargando(self):
        with self.lock:
            if self.descargando > 0:
                self.descargando -= 1
    
    def incrementar_pagina(self):
        with self.lock:
            self.paginas_procesadas += 1
    
    def obtener_estado(self):
        with self.lock:
            return (
                self.exitos, 
                self.errores, 
                self.omitidos, 
                self.total, 
                self.descargando, 
                self.paginas_procesadas
            )


contador = ContadorSeguro()

# ========== COLA Y EVENTO DE DESCARGA ==========
cola_descargas = queue.Queue(maxsize=QUEUE_SIZE)
descarga_activa = Event()
descarga_activa.set()

# ========== CONFIGURAR CHROME ==========
chrome_options = Options()
# chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--disable-extensions")
chrome_options.add_argument("--disable-logging")
chrome_options.add_argument("--log-level=3")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")

prefs = {
    "download.default_directory": carpeta_descargas,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True
}
chrome_options.add_experimental_option("prefs", prefs)

from selenium.webdriver.chrome.service import Service
import os as _os
_os.environ['WDM_LOCAL'] = '1'
_os.environ['WDM_CACHE_DIR'] = r'D:\scraper_eva\.wdm'
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

# ========== FUNCIONES AUXILIARES ==========
def capturar_screenshot(nombre="debug"):
    """Captura screenshot para diagnóstico"""
    try:
        filename = os.path.join(carpeta_descargas, f"{nombre}_{int(time.time())}.png")
        driver.save_screenshot(filename)
        log(f"   💾 Screenshot guardado: {filename}")
        return filename
    except Exception as e:
        log(f"   ⚠️ Error guardando screenshot: {e}")
        return None

def esperar_elemento_clickable(xpath, timeout=30, descripcion="elemento"):
    """Espera a que un elemento sea clickeable"""
    try:
        elemento = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        return elemento
    except TimeoutException:
        return None

def buscar_elemento_por_texto(texto, tag="*"):
    """Busca elementos que contengan un texto específico"""
    try:
        xpath = f"//{tag}[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{texto.lower()}')]"
        elementos = driver.find_elements(By.XPATH, xpath)
        return elementos
    except Exception:
        return []

def navegar_a_pagina(numero_pagina, total_paginas):
    """Navega a una página específica con reintentos usando botón 'Siguiente' (fallback)"""
    for intento in range(MAX_REINTENTOS_NAVEGACION):
        try:
            pagina_actual_elem = driver.find_element(By.XPATH, '//*[@id="RViewer_ctl05_ctl00_CurrentPage"]')
            pagina_actual = int(pagina_actual_elem.get_attribute('value'))
            
            if pagina_actual == numero_pagina:
                return True
            
            boton_siguiente = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="RViewer_ctl05_ctl00_Next_ctl00_ctl00"]'))
            )
            driver.execute_script("arguments[0].click();", boton_siguiente)
            
            tiempo_inicio = time.time()
            timeout_pagina = 45
            
            while time.time() - tiempo_inicio < timeout_pagina:
                try:
                    pagina_actual_elem = driver.find_element(By.XPATH, '//*[@id="RViewer_ctl05_ctl00_CurrentPage"]')
                    nueva_pagina = int(pagina_actual_elem.get_attribute('value'))
                    
                    if nueva_pagina == numero_pagina:
                        time.sleep(1)
                        return True
                    
                    time.sleep(0.5)
                except Exception:
                    time.sleep(0.5)
            
            log(f"⚠️ Intento {intento + 1}/{MAX_REINTENTOS_NAVEGACION} falló para página {numero_pagina}")
            time.sleep(2)
            
        except Exception as e:
            log(f"⚠️ Error en intento {intento + 1} navegando a página {numero_pagina}: {e}")
            time.sleep(2)
    
    log(f"❌ No se pudo navegar a página {numero_pagina} después de {MAX_REINTENTOS_NAVEGACION} intentos")
    return False

def saltar_a_pagina(numero_pagina):
    """Navega directamente a una página específica usando el input de página"""
    try:
        campo_pagina = driver.find_element(By.XPATH, '//*[@id="RViewer_ctl05_ctl00_CurrentPage"]')
        campo_pagina.clear()
        campo_pagina.send_keys(str(numero_pagina))
        campo_pagina.send_keys(Keys.RETURN)
        time.sleep(3)
        
        tiempo_inicio = time.time()
        timeout_pagina = 15
        
        while time.time() - tiempo_inicio < timeout_pagina:
            try:
                campo_pagina = driver.find_element(By.XPATH, '//*[@id="RViewer_ctl05_ctl00_CurrentPage"]')
                nueva_pagina = int(campo_pagina.get_attribute('value'))
                if nueva_pagina == numero_pagina:
                    return True
            except Exception:
                pass
            time.sleep(1)
        
        log(f"⚠️ No se pudo verificar salto a página {numero_pagina}")
        return False
    
    except Exception as e:
        log(f"❌ Error en salto directo a página {numero_pagina}: {e}")
        return False

# ========== SELECCIONAR USUARIOS ==========
def seleccionar_usuarios_por_lista(lista_usuarios, modo_debug=False):
    """Selecciona múltiples usuarios del desplegable"""
    if not lista_usuarios or len(lista_usuarios) == 0:
        log("⚠️ No hay usuarios para seleccionar, continuando sin filtro de usuarios")
        return 0
    
    try:
        log(f"\n👥 Seleccionando {len(lista_usuarios)} usuarios...")
        
        radio = esperar_elemento_clickable('//*[@id="PEXT_idAgente_Rad2"]', timeout=10)
        if radio:
            driver.execute_script("arguments[0].click();", radio)
            log("   ✓ Radio button clickeado")
        else:
            log("   ⚠️ No se encontró el radio PEXT_idAgente_Rad2 (continuando de todas formas)")
        
        tbody_xpath = '//*[@id="PEXT_idAgente_UP_SMCa"]/table/tbody'
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, tbody_xpath)))
        log("   ✓ Desplegable abierto")
        
        if modo_debug:
            capturar_screenshot("desplegable_usuarios")
        
        labels = driver.find_elements(By.XPATH, "//*[starts-with(@id,'PEXT_idAgente_Lb')]")
        log(f"   📋 {len(labels)} usuarios encontrados en el sistema")
        
        if modo_debug:
            archivo_usuarios = os.path.join(carpeta_descargas, "usuarios_disponibles.txt")
            try:
                with open(archivo_usuarios, 'w', encoding='utf-8') as f:
                    f.write("USUARIOS DISPONIBLES EN EL SISTEMA\n")
                    f.write("=" * 60 + "\n\n")
                    for lab in labels:
                        try:
                            texto = lab.text.strip()
                            lab_id = lab.get_attribute('id')
                            if texto:
                                f.write(f"{lab_id}: {texto}\n")
                        except Exception:
                            continue
                    f.write(f"\n\nTotal: {len(labels)} usuarios\n")
                
                log(f"   💾 Lista completa guardada en: {archivo_usuarios}")
            except Exception as e:
                log(f"   ⚠️ Error guardando lista: {e}")
        
        usuarios_seleccionados = 0
        usuarios_encontrados = []
        usuarios_no_encontrados = []
        
        for nombre_agente in lista_usuarios:
            nombre_lower = nombre_agente.strip().lower()
            encontrado = False
            
            for lab in labels:
                try:
                    text = lab.text.strip().lower()
                    
                    if nombre_lower in text or text in nombre_lower:
                        lab_id = lab.get_attribute('id')
                        idx = lab_id.replace('PEXT_idAgente_Lb', '')
                        
                        cb_xpath = f"//*[@id='PEXT_idAgente_Chk{idx}']"
                        
                        try:
                            cb = driver.find_element(By.XPATH, cb_xpath)
                            
                            if not cb.is_selected():
                                driver.execute_script("arguments[0].click();", cb)
                                time.sleep(0.2)
                            
                            log(f"   ✓ Usuario seleccionado: '{lab.text.strip()}' (idx={idx})")
                            usuarios_seleccionados += 1
                            usuarios_encontrados.append(lab.text.strip())
                            encontrado = True
                            break
                            
                        except NoSuchElementException:
                            log(f"   ⚠️ Checkbox no encontrado para idx={idx}")
                            continue
                        
                except Exception:
                    continue
            
            if not encontrado:
                usuarios_no_encontrados.append(nombre_agente)
        
        log(f"\n   📊 RESUMEN DE SELECCIÓN:")
        log(f"      • Usuarios buscados: {len(lista_usuarios)}")
        log(f"      • Usuarios seleccionados: {usuarios_seleccionados}")
        log(f"      • Usuarios NO encontrados: {len(usuarios_no_encontrados)}")
        
        if usuarios_no_encontrados and len(usuarios_no_encontrados) <= 10:
            log(f"\n   ❌ Usuarios no encontrados:")
            for usuario in usuarios_no_encontrados:
                log(f"      • {usuario}")
        elif usuarios_no_encontrados:
            log(f"\n   ❌ {len(usuarios_no_encontrados)} usuarios no encontrados (ver log completo)")
        
        if modo_debug and usuarios_seleccionados == 0:
            log(f"\n   💡 SUGERENCIA: Revisa 'usuarios_disponibles.txt' para ver el formato exacto")
            log(f"      Compara con tu lista y ajusta los nombres si es necesario")
        
        time.sleep(1)
        return usuarios_seleccionados
        
    except TimeoutException:
        log("❌ Error: No se pudo abrir el desplegable de usuarios (timeout)")
        capturar_screenshot("error_desplegable_usuarios")
        return 0
    except Exception as e:
        log(f"❌ Error en selección de usuarios: {str(e)}")
        capturar_screenshot("error_seleccion_usuarios")
        import traceback
        log(f"   Traceback: {traceback.format_exc()}")
        return 0

seleccionar_usuarios = seleccionar_usuarios_por_lista

# ========== FUNCIÓN DE DESCARGA ==========
def descargar_audio_worker(session_cookies):
    """Worker que descarga audios desde la cola - VERSIÓN MEJORADA"""
    while True:
        try:
            item = cola_descargas.get(timeout=5)
            
            if item is None:
                cola_descargas.task_done()
                break
            
            url, nombre_archivo, num_global, num_pagina = item
            ruta_completa = os.path.join(carpeta_descargas, nombre_archivo)
            
            if archivo_existe(nombre_archivo):
                if os.path.exists(ruta_completa) and os.path.getsize(ruta_completa) > 0:
                    contador.incrementar_omitido()
                    contador.decrementar_descargando()
                    
                    exitos, errores, omitidos, total, desc, pags = contador.obtener_estado()
                    procesados = exitos + errores + omitidos
                    
                    if omitidos % 100 == 0:
                        progreso = (procesados / total * 100) if total > 0 else 0
                        log(f"  ⏭️  [{procesados}/{total}] {progreso:.1f}% | Pág {pags} | {omitidos} omitidos")
                    
                    cola_descargas.task_done()
                    continue
            
            max_reintentos = 3
            
            for intento in range(max_reintentos):
                try:
                    response = requests.get(
                        url, 
                        cookies=session_cookies, 
                        stream=True, 
                        timeout=TIMEOUT_DESCARGA
                    )
                    
                    if response.status_code == 200:
                        with open(ruta_completa, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                                if chunk:
                                    f.write(chunk)
                        
                        if os.path.exists(ruta_completa) and os.path.getsize(ruta_completa) > 0:
                            agregar_a_cache(nombre_archivo)
                            
                            tamaño = os.path.getsize(ruta_completa) / 1024
                            contador.incrementar_exito()
                            contador.decrementar_descargando()
                            exitos, errores, omitidos, total, desc, pags = contador.obtener_estado()
                            procesados = exitos + errores + omitidos
                            progreso = (procesados / total * 100) if total > 0 else 0
                            
                            if exitos % 50 == 0 or exitos % 100 == 0:
                                log(f"  ✓ [{procesados}/{total}] {progreso:.1f}% | Pág {pags} | ↓{exitos} ⏭{omitidos} | {nombre_archivo} ({tamaño:.0f}KB)")
                            
                            break
                        else:
                            if os.path.exists(ruta_completa):
                                os.remove(ruta_completa)
                            raise Exception("Archivo vacío o no se escribió correctamente")
                    else:
                        if intento == max_reintentos - 1:
                            contador.incrementar_error()
                            contador.decrementar_descargando()
                            log(f"  ✗ Error HTTP {response.status_code}: {nombre_archivo}")
                        time.sleep(1)
                        
                except Exception as e:
                    if intento == max_reintentos - 1:
                        contador.incrementar_error()
                        contador.decrementar_descargando()
                        log(f"  ✗ Error: {nombre_archivo[:30]} - {str(e)[:50]}")
                    time.sleep(1)
            
            cola_descargas.task_done()
            
        except queue.Empty:
            if not descarga_activa.is_set():
                break
            continue
        except Exception as e:
            log(f"  ⚠️ Error crítico en worker: {e}")
            cola_descargas.task_done()
            continue

# ========== FUNCIONES DE LOGIN Y SETUP (reutilizables para re-login) ==========

def hacer_login():
    """Realiza el login en la plataforma. Retorna True si exitoso."""
    global session_cookies_global
    log("\n🔐 Iniciando sesión...")
    driver.get(config.url)
    time.sleep(3)

    try:
        campo_usuario = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="TboxUser"]'))
        )
        campo_password = driver.find_element(By.XPATH, '//*[@id="TboxPass"]')

        campo_usuario.clear()
        campo_password.clear()
        campo_usuario.send_keys(config.user)
        campo_password.send_keys(config.password)

        boton_login = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//*[@id="Btn_LogIn_span_lnkBtn"]'))
        )
        boton_login.click()
        log("✓ Credenciales enviadas")

        log("⏳ Esperando carga de página principal...")
        iframes_cargados = False

        for _ in range(60):
            try:
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                if len(iframes) > 0:
                    log(f"✓ {len(iframes)} iframes detectados")
                    iframes_cargados = True
                    break
                time.sleep(1)
            except Exception:
                time.sleep(1)

        if not iframes_cargados:
            log("❌ Los iframes no se cargaron")
            capturar_screenshot("error_timeout_iframes")
            return False

        log("✓ Login exitoso")
        time.sleep(3)
        return True

    except Exception as e:
        log(f"❌ Error en login: {e}")
        capturar_screenshot("error_login")
        return False


def navegar_menu_grabaciones():
    """Navega al módulo Grabaciones > Detalle de grabaciones. Retorna True si exitoso."""
    log("\n📂 Navegando al módulo de grabaciones...")
    driver.switch_to.default_content()
    iframe_encontrado = False
    iframe_menu = None

    try:
        iframe_menu = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="IfTreeSP"]'))
        )
        iframe_encontrado = True
    except Exception:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        if len(iframes) > 0:
            iframe_menu = iframes[0]
            iframe_encontrado = True

    if not iframe_encontrado:
        log("❌ No se pudo localizar el iframe del menú")
        capturar_screenshot("error_iframe")
        return False

    driver.switch_to.frame(iframe_menu)
    time.sleep(3)

    # Buscar "Grabaciones"
    grabaciones_elemento = None
    try:
        grabaciones_elemento = esperar_elemento_clickable('//*[@id="tree1t52"]', timeout=10)
    except Exception:
        pass

    if not grabaciones_elemento:
        elementos = buscar_elemento_por_texto("grabacion")
        for elem in elementos:
            try:
                if elem.is_displayed():
                    grabaciones_elemento = elem
                    break
            except Exception:
                pass

    if not grabaciones_elemento:
        elementos_tree = driver.find_elements(By.XPATH, "//*[starts-with(@id, 'tree1t')]")
        for elem in elementos_tree:
            try:
                elem_text = elem.text.lower() if elem.text else ""
                if "grabaci" in elem_text and elem.is_displayed():
                    grabaciones_elemento = elem
                    break
            except Exception:
                continue

    if not grabaciones_elemento:
        log("❌ No se pudo encontrar 'Grabaciones'")
        capturar_screenshot("error_grabaciones")
        return False

    try:
        grabaciones_elemento.click()
    except Exception:
        driver.execute_script("arguments[0].click();", grabaciones_elemento)

    log("✓ Click en 'Grabaciones'")
    time.sleep(3)

    # Buscar "Detalle de grabaciones"
    detalle_elemento = None
    try:
        detalle_elemento = esperar_elemento_clickable('//*[@id="tree1t53"]', timeout=10)
    except Exception:
        pass

    if not detalle_elemento:
        elementos = buscar_elemento_por_texto("detalle")
        for elem in elementos:
            try:
                if "grabacion" in elem.text.lower() and elem.is_displayed():
                    detalle_elemento = elem
                    break
            except Exception:
                continue

    if not detalle_elemento:
        elementos = driver.find_elements(By.XPATH, "//*[starts-with(@id, 'tree1t5')]")
        for elem in elementos:
            try:
                elem_text = elem.text.lower() if elem.text else ""
                if "detalle" in elem_text and elem.is_displayed():
                    detalle_elemento = elem
                    break
            except Exception:
                continue

    if not detalle_elemento:
        log("❌ No se pudo encontrar 'Detalle de grabaciones'")
        capturar_screenshot("error_detalle")
        return False

    try:
        detalle_elemento.click()
    except Exception:
        driver.execute_script("arguments[0].click();", detalle_elemento)

    log("✓ Click en 'Detalle de grabaciones'")
    time.sleep(3)
    return True


def configurar_filtros_y_buscar(fecha, hora_inicio, hora_final):
    """Configura filtros, selecciona usuarios y ejecuta búsqueda. Retorna True si exitoso."""
    log("\n⚙️ Configurando filtros...")
    driver.switch_to.default_content()
    driver.switch_to.frame(1)
    time.sleep(2)

    try:
        seleccionar_fecha = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.XPATH, '//*[@id="PEXT_FechaRango_Rad1"]'))
        )
        driver.execute_script("arguments[0].click();", seleccionar_fecha)

        driver.execute_script(f"""
            document.getElementById('PEXT_FechaRango_TBoxFch1').value = '{fecha}';
            document.getElementById('PEXT_FechaRango_TBoxFch2').value = '{fecha}';
        """)

        dropdown_hora_inicio = Select(driver.find_element(By.XPATH, '//*[@id="PEXT_HIni_Ddl1"]'))
        dropdown_hora_inicio.select_by_value(hora_inicio)

        dropdown_hora_final = Select(driver.find_element(By.XPATH, '//*[@id="PEXT_HFin_Ddl1"]'))
        dropdown_hora_final.select_by_value(hora_final)

        log(f"✓ Filtros: {fecha} | {hora_inicio}:00 - {hora_final}:00")

        # Seleccionar usuarios
        if len(USUARIOS_A_SELECCIONAR) > 0:
            usuarios_ok = seleccionar_usuarios_por_lista(USUARIOS_A_SELECCIONAR, modo_debug=False)
            if usuarios_ok == 0:
                log("⚠️ No se pudo seleccionar ningún usuario, continuando sin filtro")

        # Máximo de filas
        dropdown_max_rows = Select(driver.find_element(By.XPATH, '//*[@id="PEXT_MaxRow_Ddl1"]'))
        dropdown_max_rows.select_by_index(8)
        time.sleep(1)

        # Duración mínima
        try:
            dropdown_duracion = Select(driver.find_element(By.XPATH, '//*[@id="PEXT_MinDuracion_Ddl2"]'))
            dropdown_duracion.select_by_value(DURACION_MINIMA)
            log(f"✓ Duración mínima: {DURACION_MINIMA} minutos")
        except Exception as e:
            log(f"⚠️ No se pudo configurar duración mínima: {e}")

        time.sleep(3)

        # Ejecutar búsqueda
        try:
            boton_ejecutar = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="Btn_execBotton_lbl_Button"]'))
            )
            boton_ejecutar.click()
        except Exception:
            driver.execute_script("document.getElementById('Btn_execBotton_lbl_Button').click();")

        log("\n⏳ Generando reporte...")
        driver.switch_to.default_content()
        driver.switch_to.frame(2)

        for _ in range(30):
            try:
                links_audio = driver.find_elements(By.XPATH, "//a[contains(@href, 'GetWave.ashx')]")
                if links_audio:
                    log(f"✓ Reporte generado ({len(links_audio)} audios en la página 1)")
                    return True

                body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
                if "sin resultados" in body_text or "no se encontraron" in body_text:
                    log("❌ Sin resultados")
                    return False

                time.sleep(2)
            except Exception:
                time.sleep(2)

        log("❌ Timeout esperando reporte")
        return False

    except Exception as e:
        log(f"❌ Error configurando filtros: {e}")
        capturar_screenshot("error_filtros")
        return False


def detectar_sesion_perdida():
    """Detecta si la sesión se perdió verificando la URL y elementos de la página."""
    try:
        driver.switch_to.default_content()
        url_actual = driver.current_url.lower()
        if "login" in url_actual:
            log("🔒 Sesión perdida: redirigido a página de login")
            return True

        # Verificar si hay iframes (indica sesión activa)
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        if len(iframes) == 0:
            log("🔒 Sesión perdida: no se encuentran iframes")
            return True

        # Intentar volver al frame de resultados
        try:
            driver.switch_to.frame(2)
            driver.find_element(By.TAG_NAME, "body")
            return False
        except Exception:
            log("🔒 Sesión perdida: no se puede acceder al frame de resultados")
            return True

    except Exception as e:
        log(f"🔒 Sesión perdida (error verificando): {e}")
        return True


def relogin_y_restaurar(fecha, hora_inicio, hora_final, pagina_destino):
    """Re-login completo y navega hasta la página indicada. Retorna (ok, nuevas_cookies, total_paginas)."""
    global session_cookies_global
    MAX_INTENTOS_RELOGIN = 5

    for intento in range(MAX_INTENTOS_RELOGIN):
        log(f"\n🔄 Re-login intento {intento + 1}/{MAX_INTENTOS_RELOGIN}...")

        if not hacer_login():
            log(f"❌ Re-login falló en intento {intento + 1}")
            time.sleep(10)
            continue

        if not navegar_menu_grabaciones():
            log(f"❌ Navegación al menú falló en intento {intento + 1}")
            time.sleep(10)
            continue

        if not configurar_filtros_y_buscar(fecha, hora_inicio, hora_final):
            log(f"❌ Configuración de filtros falló en intento {intento + 1}")
            time.sleep(10)
            continue

        # Obtener nuevas cookies
        cookies = driver.get_cookies()
        nuevas_cookies = {cookie['name']: cookie['value'] for cookie in cookies}
        session_cookies_global = nuevas_cookies

        # Obtener total de páginas
        try:
            total_paginas_elem = driver.find_element(By.XPATH, '//*[@id="RViewer_ctl05_ctl00_TotalPages"]')
            total_pags = int(total_paginas_elem.text)
        except Exception:
            total_pags = 1

        # Navegar a la página destino
        if pagina_destino > 1:
            log(f"⏩ Navegando a página {pagina_destino}...")
            if saltar_a_pagina(pagina_destino):
                log(f"✓ Re-login exitoso, en página {pagina_destino}")
                return True, nuevas_cookies, total_pags
            else:
                # Intentar navegación secuencial
                log(f"⚠️ Salto directo falló, navegando secuencialmente...")
                ok = True
                for p in range(2, pagina_destino + 1):
                    if not navegar_a_pagina(p, total_pags):
                        ok = False
                        break
                if ok:
                    log(f"✓ Re-login exitoso, en página {pagina_destino}")
                    return True, nuevas_cookies, total_pags
                else:
                    log(f"❌ No se pudo llegar a página {pagina_destino}")
                    time.sleep(10)
                    continue
        else:
            log("✓ Re-login exitoso, en página 1")
            return True, nuevas_cookies, total_pags

    log(f"❌ Re-login falló después de {MAX_INTENTOS_RELOGIN} intentos")
    return False, {}, 0


def validar_fecha(fecha_str):
    try:
        partes = fecha_str.split('/')
        return len(partes) == 3 and len(partes[0]) == 2 and len(partes[1]) == 2 and len(partes[2]) == 4
    except Exception:
        return False


# ========== INICIO DEL PROCESO ==========
log("\n📦 Verificando archivos existentes...")
cargar_cache_archivos()

# ========== VERIFICAR CHECKPOINT ==========
checkpoint = cargar_checkpoint()
reanudar = False
pagina_inicial = 1

# En modo batch (con argumento de fecha), auto-skip checkpoint
batch_mode = len(sys.argv) > 1

if checkpoint:
    log(f"\n🔄 Checkpoint encontrado:")
    log(f"   • Última página procesada: {checkpoint['pagina_actual']}/{checkpoint['total_paginas']}")
    log(f"   • Fecha: {checkpoint.get('timestamp', 'desconocida')}")
    log(f"   • Filtros: {checkpoint['fecha']} ({checkpoint['hora_inicio']}:00 - {checkpoint['hora_final']}:00)")

    if batch_mode:
        log("⏩ Modo batch: omitiendo checkpoint anterior")
        eliminar_checkpoint()
    else:
        respuesta = input("\n¿Deseas reanudar desde donde quedó? (si/no): ").strip().lower()
        if respuesta in ['si', 'sí', 's', 'yes', 'y']:
            reanudar = True
            pagina_inicial = checkpoint['pagina_actual'] + 1
            log(f"✓ Reanudando desde página {pagina_inicial}")

# ========== LOGIN INICIAL ==========
if not hacer_login():
    log("❌ No se pudo realizar el login inicial")
    driver.quit()
    raise SystemExit(1)

# ========== NAVEGACIÓN AL MENÚ ==========
if not navegar_menu_grabaciones():
    log("❌ No se pudo navegar al menú de grabaciones")
    driver.quit()
    raise SystemExit(1)

# ========== CONFIGURAR FILTROS ==========
if reanudar and checkpoint:
    fecha = checkpoint['fecha']
    hora_inicio = checkpoint['hora_inicio']
    hora_final = checkpoint['hora_final']
    log("✓ Usando filtros del checkpoint")
else:
    if batch_mode:
        fecha = sys.argv[1]
        log(f"✓ Fecha recibida por argumento: {fecha}")
    else:
        log("\nIngresa la fecha en formato DD/MM/YYYY")
        fecha = input("Fecha: ").strip()

    if not validar_fecha(fecha):
        log("❌ Formato de fecha incorrecto")
        driver.quit()
        raise SystemExit(1)

    hora_inicio = HORA_INICIO_AUTO
    hora_final = HORA_FIN_AUTO
    log(f"✓ Horario automático: {hora_inicio}:00 - {hora_final}:00")

if not configurar_filtros_y_buscar(fecha, hora_inicio, hora_final):
    log("❌ No se pudo configurar filtros y buscar")
    driver.quit()
    raise SystemExit(1)

# ========== OBTENER COOKIES Y DETECTAR PAGINACIÓN ==========
cookies = driver.get_cookies()
session_cookies = {cookie['name']: cookie['value'] for cookie in cookies}
session_cookies_global = session_cookies

try:
    total_paginas_elem = driver.find_element(By.XPATH, '//*[@id="RViewer_ctl05_ctl00_TotalPages"]')
    total_paginas_global = int(total_paginas_elem.text)
    log(f"\n📄 Total de páginas: {total_paginas_global}")
except Exception:
    total_paginas_global = 1
    log("\n📄 Total de páginas: 1 (no se encontró el control de paginación)")

# Si estamos reanudando y no estamos en la página inicial correcta, saltar
if reanudar and pagina_inicial > 1:
    log(f"\n⏩ Saltando directamente a página {pagina_inicial}...")
    if not saltar_a_pagina(pagina_inicial):
        log("⚠️ No se pudo saltar directamente, intentando navegación tradicional...")
        for pag in range(2, pagina_inicial + 1):
            if not navegar_a_pagina(pag, total_paginas_global):
                log(f"❌ No se pudo llegar a página {pag}")
                driver.quit()
                raise SystemExit(1)
            if pag % 10 == 0:
                log(f"   ... página {pag}/{pagina_inicial}")

# Estimar total de audios
audios_pagina_actual = len(driver.find_elements(By.XPATH, "//a[contains(@href, 'GetWave.ashx')]"))
total_estimado = audios_pagina_actual * total_paginas_global
contador.set_total(total_estimado)

log(f"\n{'='*70}")
log(f"  🚀 DESCARGA PARALELA ({MAX_WORKERS} workers)")
log(f"  📊 ~{total_estimado:,} audios en {total_paginas_global} páginas")
log(f"  📅 Fecha: {fecha} | ⏰ {hora_inicio}:00 - {hora_final}:00 | ⏱️ Duración mín: {DURACION_MINIMA} min")
if len(USUARIOS_A_SELECCIONAR) > 0:
    log(f"  👥 Filtro de usuarios: {len(USUARIOS_A_SELECCIONAR)} usuarios configurados")
if reanudar:
    log(f"  🔄 Reanudando desde página {pagina_inicial}")
if len(archivos_existentes_cache) > 0:
    log(f"  ⏭️  {len(archivos_existentes_cache)} archivos existentes serán omitidos")
log(f"{'='*70}\n")

# ========== INICIAR WORKERS DE DESCARGA Y RECORRER PÁGINAS ==========
tiempo_inicio = time.time()

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = [executor.submit(descargar_audio_worker, session_cookies) for _ in range(MAX_WORKERS)]
    log("✓ Workers iniciados\n")

    try:
        for num_pagina in range(pagina_inicial, total_paginas_global + 1):
            # Intentar obtener links de audio de la página actual
            try:
                links_audio = driver.find_elements(By.XPATH, "//a[contains(@href, 'GetWave.ashx')]")
                audios_en_pagina = len(links_audio)
            except Exception:
                audios_en_pagina = 0
                links_audio = []

            # Si no hay audios, verificar si perdimos la sesión
            if audios_en_pagina == 0 and num_pagina > 1:
                if detectar_sesion_perdida():
                    log(f"\n🔄 Sesión perdida en página {num_pagina}, intentando re-login...")
                    ok, nuevas_cookies, nuevo_total = relogin_y_restaurar(fecha, hora_inicio, hora_final, num_pagina)
                    if ok:
                        # Actualizar cookies para los workers (los workers usan session_cookies por referencia)
                        session_cookies.update(nuevas_cookies)
                        if nuevo_total > 0:
                            total_paginas_global = nuevo_total
                        # Re-leer links de la página actual
                        try:
                            links_audio = driver.find_elements(By.XPATH, "//a[contains(@href, 'GetWave.ashx')]")
                            audios_en_pagina = len(links_audio)
                        except Exception:
                            audios_en_pagina = 0
                            links_audio = []
                        log(f"✓ Sesión restaurada, página {num_pagina} tiene {audios_en_pagina} audios")
                    else:
                        log(f"❌ No se pudo restaurar la sesión. Guardando checkpoint...")
                        guardar_checkpoint(num_pagina - 1, total_paginas_global, fecha, hora_inicio, hora_final)
                        break

            log(f"📄 Página {num_pagina}/{total_paginas_global} | {audios_en_pagina} audios")

            if audios_en_pagina == 0:
                contador.incrementar_pagina()
            else:
                for j, link in enumerate(links_audio, 1):
                    try:
                        url = link.get_attribute('href')

                        if 'sFile=' in url:
                            nombre_archivo = url.split('sFile=')[1].split('&')[0]
                            if not nombre_archivo.endswith('.wav'):
                                nombre_archivo += '.wav'
                        else:
                            nombre_archivo = f"audio_pag{num_pagina}_num{j}.wav"

                        cola_descargas.put((url, nombre_archivo, j, num_pagina))
                        contador.incrementar_descargando()

                    except Exception as e:
                        log(f"⚠️ Error procesando audio {j} página {num_pagina}: {e}")
                        continue

                contador.incrementar_pagina()

            if num_pagina % 10 == 0:
                exitos, errores, omitidos, total, desc, pags = contador.obtener_estado()
                procesados = exitos + errores + omitidos
                progreso = (procesados / total * 100) if total > 0 else 0
                guardar_checkpoint(num_pagina, total_paginas_global, fecha, hora_inicio, hora_final)
                log(f"\n💾 Checkpoint - Pág {num_pagina}/{total_paginas_global} ({progreso:.1f}%) | ↓{exitos} ✗{errores} ⏭{omitidos}")

            if num_pagina < total_paginas_global:
                # Intentar saltar directamente
                nav_ok = saltar_a_pagina(num_pagina + 1)

                if not nav_ok:
                    log(f"⚠️ Salto directo falló, intentando navegación secuencial...")
                    reintentos_nav = 3
                    for _ in range(reintentos_nav):
                        if navegar_a_pagina(num_pagina + 1, total_paginas_global):
                            nav_ok = True
                            break

                if not nav_ok:
                    # Posible sesión perdida - intentar re-login
                    log(f"\n🔒 Navegación falló completamente. Verificando sesión...")
                    if detectar_sesion_perdida():
                        log(f"🔄 Sesión perdida, re-login para página {num_pagina + 1}...")
                        ok, nuevas_cookies, nuevo_total = relogin_y_restaurar(fecha, hora_inicio, hora_final, num_pagina + 1)
                        if ok:
                            session_cookies.update(nuevas_cookies)
                            if nuevo_total > 0:
                                total_paginas_global = nuevo_total
                            log(f"✓ Sesión restaurada, continuando desde página {num_pagina + 1}")
                        else:
                            log(f"❌ Re-login falló. Guardando checkpoint...")
                            guardar_checkpoint(num_pagina, total_paginas_global, fecha, hora_inicio, hora_final)
                            break
                    else:
                        log(f"⚠️ Sesión activa pero no se pudo navegar a página {num_pagina + 1}, guardando checkpoint...")
                        guardar_checkpoint(num_pagina, total_paginas_global, fecha, hora_inicio, hora_final)
                        continue

        log(f"\n✓ Navegación completada")

    except KeyboardInterrupt:
        log("\n⚠️ Interrupción detectada - guardando progreso...")
        exitos, errores, omitidos, total, desc, pags = contador.obtener_estado()
        guardar_checkpoint(pags, total_paginas_global, fecha, hora_inicio, hora_final)

    except Exception as e:
        log(f"\n⚠️ Error general durante la navegación: {e}")
        import traceback
        log(f"   Traceback: {traceback.format_exc()}")
        pags = contador.obtener_estado()[5]
        guardar_checkpoint(pags, total_paginas_global, fecha, hora_inicio, hora_final)

    finally:
        descarga_activa.clear()
        log("⏳ Esperando descargas pendientes...")

        # Esperar que terminen los workers
        cola_descargas.join()

        # Enviar señales de finalización
        for _ in range(MAX_WORKERS):
            cola_descargas.put(None)

        # Esperar a que cada worker termine
        for future in futures:
            future.result()

log("🛑 Cerrando navegador...")
driver.quit()

tiempo_total = time.time() - tiempo_inicio

# ========== RESUMEN FINAL ==========
exitos, errores, omitidos, total, desc, pags = contador.obtener_estado()
procesados = exitos + errores + omitidos

log(f"\n{'='*70}")
log(f"  ✅ DESCARGA COMPLETADA")
log(f"{'='*70}")
log(f"  📊 Estadísticas:")
log(f"     • Total procesado: {procesados} audios")
log(f"     • Descargados: {exitos} ✓")
log(f"     • Errores: {errores} ✗")
log(f"     • Omitidos (ya existían): {omitidos} ⏭")
log(f"     • Páginas procesadas: {pags}/{total_paginas_global}")
log(f"     • Tiempo total: {tiempo_total/60:.1f} min ({tiempo_total/3600:.2f} hrs)")

if tiempo_total > 0:
    log(f"     • Velocidad promedio: {procesados/(tiempo_total/60):.1f} audios/min")

log(f"  📁 Carpeta de descargas: {carpeta_descargas}")

try:
    archivos = [f for f in os.listdir(carpeta_descargas) if f.lower().endswith('.wav')]
    if archivos:
        tamaño_total = sum(os.path.getsize(os.path.join(carpeta_descargas, f)) for f in archivos)
        log(f"  💾 Tamaño total: {tamaño_total / (1024**3):.2f} GB")
except Exception as e:
    log(f"⚠️ No se pudo calcular el tamaño total de los archivos: {e}")

log(f"{'='*70}\n")

if pags >= total_paginas_global:
    eliminar_checkpoint()
    log("✅ Proceso completado al 100% - Checkpoint eliminado")
else:
    log(f"⚠️ Proceso interrumpido en página {pags}/{total_paginas_global}")
    log(f"💡 Ejecuta el script nuevamente para reanudar desde donde quedó")

log(f"\n📋 Log detallado guardado en: {archivo_log}")
