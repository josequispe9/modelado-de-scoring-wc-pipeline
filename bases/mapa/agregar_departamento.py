import csv
import os
import unicodedata
from difflib import get_close_matches, SequenceMatcher

LOCALIDADES_DIR = "/mnt/c/Users/qjose/Desktop/modelado de scoring WC/bases/mapa/provincias/localidades"
CSV_PATH = "/mnt/c/Users/qjose/Desktop/modelado de scoring WC/bases/mapa/datos-de-mapeo.csv"
OUTPUT_PATH = "/mnt/c/Users/qjose/Desktop/modelado de scoring WC/bases/mapa/datos-de-mapeo-con-departamento.csv"

# Mapa de nombre de provincia en CSV → nombre del archivo txt
PROVINCIA_A_ARCHIVO = {
    "BUENOS AIRES": "buenos_aires",
    "CATAMARCA": "catamarca",
    "CHACO": "chaco",
    "CHUBUT": "chubut",
    "CORDOBA": "cordoba",
    "CORRIENTES": "corrientes",
    "ENTRE RIOS": "entre_rios",
    "FORMOSA": "formosa",
    "JUJUY": "jujuy",
    "LA PAMPA": "la_pampa",
    "LA RIOJA": "la_rioja",
    "MENDOZA": "mendoza",
    "MISIONES": "misiones",
    "NEUQUEN": "neuquen",
    "RIO NEGRO": "rio_negro",
    "SALTA": "salta",
    "SAN JUAN": "san_juan",
    "SAN LUIS": "san_luis",
    "SANTA CRUZ": "santa_cruz",
    "SANTA FE": "santa_fe",
    "SANTIAGO DEL ESTERO": "santiago_del_estero",
    "TIERRA DEL FUEGO": "tierra_del_fuego",
    "TUCUMAN": "tucuman",
}

def normalizar(texto):
    """Pasa a mayúsculas y elimina tildes."""
    texto = texto.upper().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto

# Cargar todas las localidades de los TXT → {provincia: {localidad_norm: departamento}}
datos_por_provincia = {}
for provincia_csv, nombre_archivo in PROVINCIA_A_ARCHIVO.items():
    ruta = LOCALIDADES_DIR + "/" + nombre_archivo + ".txt"
    if not os.path.exists(ruta):
        print(f"AVISO: no encontrado {ruta}")
        continue
    localidades = {}
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            partes = linea.strip().split("\t")
            if len(partes) >= 3:
                nombre_loc = partes[0].strip()
                departamento = partes[2].strip()
                localidades[normalizar(nombre_loc)] = departamento
    datos_por_provincia[provincia_csv] = localidades
    print(f"  {provincia_csv}: {len(localidades)} localidades cargadas")

def buscar_departamento(localidad, provincia):
    """Busca el departamento usando fuzzy matching."""
    if provincia == "CIUDAD AUTONOMA DE BUENOS AIRES":
        return ""

    localidades_prov = datos_por_provincia.get(provincia)
    if not localidades_prov:
        return ""

    loc_norm = normalizar(localidad)

    # Búsqueda exacta primero
    if loc_norm in localidades_prov:
        return localidades_prov[loc_norm]

    # Containment: loc_norm está contenido en el candidato o viceversa
    # El fragmento contenido debe tener al menos 6 chars para evitar falsos positivos
    if len(loc_norm) >= 6:
        for cand, dep in localidades_prov.items():
            if loc_norm in cand or (len(cand) >= 7 and cand in loc_norm):
                print(f"  [CONTAIN] '{localidad}' → '{cand}' ({provincia})")
                return dep

    # Fuzzy matching con cutoff alto como fallback
    candidatos = list(localidades_prov.keys())
    matches = get_close_matches(loc_norm, candidatos, n=1, cutoff=0.85)
    if matches:
        score = SequenceMatcher(None, loc_norm, matches[0]).ratio()
        print(f"  [FUZZY {score:.2f}] '{localidad}' → '{matches[0]}' ({provincia})")
        return localidades_prov[matches[0]]

    return ""

# Procesar CSV
sin_match = []
with open(CSV_PATH, encoding="utf-8") as fin, \
     open(OUTPUT_PATH, "w", encoding="utf-8", newline="") as fout:

    reader = csv.DictReader(fin, delimiter=";")
    fieldnames = reader.fieldnames + ["DEPARTAMENTO"]
    writer = csv.DictWriter(fout, fieldnames=fieldnames, delimiter=";")
    writer.writeheader()

    for row in reader:
        localidad = row["LOCALIDAD"]
        provincia = row["PROVINCIA"]
        departamento = buscar_departamento(localidad, provincia)
        dep_upper = departamento.upper()
        dep_upper = unicodedata.normalize("NFD", dep_upper)
        dep_upper = "".join(c for c in dep_upper if unicodedata.category(c) != "Mn")
        row["DEPARTAMENTO"] = dep_upper
        writer.writerow(row)
        if not departamento and provincia != "CIUDAD AUTONOMA DE BUENOS AIRES":
            sin_match.append(f"{localidad} | {provincia}")

print(f"\nListo. Output: {OUTPUT_PATH}")
print(f"Filas sin departamento (excl. CABA): {len(sin_match)}")
if sin_match:
    print("Sin match:")
    for s in sin_match[:30]:
        print(f"  - {s}")
    if len(sin_match) > 30:
        print(f"  ... y {len(sin_match) - 30} más")
