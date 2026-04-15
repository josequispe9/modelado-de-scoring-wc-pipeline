"""
Genera index.html con el mapa SVG interactivo y selector de prefijos.
- Cruza prefijos con departamentos del SVG
- Matching provincia-aware + mapa manual para ciudades
- Fallback a provincia completa cuando no hay match de departamento
"""

import pandas as pd
import json
import re

# ── Mapeo Excel→SVG para nombres de provincia ────────────────────────────────
PROV_MAP = {
    "AMBA":                  ["Buenos Aires", "Capital Federal"],
    "BUENOS AIRES":          ["Buenos Aires"],
    "CATAMARCA":             ["Catamarca"],
    "CHACO":                 ["Chaco"],
    "CHUBUT":                ["Chubut"],
    "CORDOBA":               ["Córdoba"],
    "CORRIENTES":            ["Corrientes"],
    "ENTRE RIOS":            ["Entre Ríos"],
    "FORMOSA":               ["Formosa"],
    "JUJUY":                 ["Jujuy"],
    "LA PAMPA":              ["La Pampa"],
    "LA RIOJA":              ["La Rioja"],
    "MENDOZA":               ["Mendoza"],
    "MISIONES":              ["Misiones"],
    "NEUQUEN":               ["Neuquén"],
    "RIO NEGRO":             ["Río Negro"],
    "SALTA":                 ["Salta"],
    "SAN JUAN":              ["San Juan"],
    "SAN LUIS":              ["San Luis"],
    "SANTA CRUZ":            ["Santa Cruz"],
    "SANTA FE":              ["Santa Fe"],
    "SANTIAGO DEL ESTERO":   ["Santiago del Estero"],
    "TIERRA DEL FUEGO":      ["Tierra del Fuego"],
    "TUCUMAN":               ["Tucumán"],
}

# ── Mapa manual: área_normalizada → (prov_svg, depto_svg)  ───────────────────
# Para ciudades cuyo nombre no coincide con el departamento que las contiene
MANUAL_MAP = {
    # AMBA / Buenos Aires
    ("AMBA",                    None):           [("Buenos Aires", None), ("Capital Federal", None)],
    ("MAR DEL PLATA",           "BUENOS AIRES"): [("Buenos Aires", "General Pueyrredón")],
    ("GONZALEZ CATAN",          "BUENOS AIRES"): [("Buenos Aires", "La Matanza")],
    ("CORONEL BRANDSEN",        "BUENOS AIRES"): [("Buenos Aires", "Brandsen")],
    ("GLEW",                    "BUENOS AIRES"): [("Buenos Aires", "Almirante Brown")],
    ("ALEJANDRO KORN",          "BUENOS AIRES"): [("Buenos Aires", "San Vicente")],
    ("JUAN MARIA GUTIERREZ",    "BUENOS AIRES"): [("Buenos Aires", "Florencio Varela")],
    ("SANTA TERESITA",          "BUENOS AIRES"): [("Buenos Aires", "La Costa")],
    ("SAN CLEMENTE DEL TUYU",   "BUENOS AIRES"): [("Buenos Aires", "La Costa")],
    ("MAR DE AJO",              "BUENOS AIRES"): [("Buenos Aires", "La Costa")],
    ("LA DULCE",                "BUENOS AIRES"): [("Buenos Aires", "Necochea")],
    ("CORONEL VIDAL",           "BUENOS AIRES"): [("Buenos Aires", "Mar Chiquita")],
    ("CARLOS SPEGAZZINI",       "BUENOS AIRES"): [("Buenos Aires", "Ezeiza")],
    ("MIRAMAR",                 "BUENOS AIRES"): [("Buenos Aires", "General Alvarado")],
    ("NORBERTO DE LA RIESTRA",  "BUENOS AIRES"): [("Buenos Aires", "Roque Pérez")],
    ("9 DE JULIO",              "BUENOS AIRES"): [("Buenos Aires", "Nueve de Julio")],
    ("25 DE MAYO",              "BUENOS AIRES"): [("Buenos Aires", "Veinticinco de Mayo")],
    ("VEDIA",                   "BUENOS AIRES"): [("Buenos Aires", "Leandro N. Alem")],
    ("LOS TOLDOS",              "BUENOS AIRES"): [("Buenos Aires", "General Viamonte")],
    ("SALAZAR",                 "BUENOS AIRES"): [("Buenos Aires", "Pehuajó")],
    ("AMERICA",                 "BUENOS AIRES"): [("Buenos Aires", "Rivadavia")],
    ("PIGÜE",                   "BUENOS AIRES"): [("Buenos Aires", "Saavedra")],
    ("PIGUE",                   "BUENOS AIRES"): [("Buenos Aires", "Saavedra")],
    ("DARREGUEIRA",             "BUENOS AIRES"): [("Buenos Aires", "Saavedra")],
    ("VILLA IRIS",              "BUENOS AIRES"): [("Buenos Aires", "Puan")],
    ("MEDANOS",                 "BUENOS AIRES"): [("Buenos Aires", "Villarino")],
    ("PEDRO LURO",              "BUENOS AIRES"): [("Buenos Aires", "Villarino")],
    ("PUNTA ALTA",              "BUENOS AIRES"): [("Buenos Aires", "Coronel Rosales")],
    ("HUANGUELEN SUR",          "BUENOS AIRES"): [("Buenos Aires", "Coronel Suárez")],
    ("SAN ANTONIO OESTE",       "BUENOS AIRES"): [("Buenos Aires", "Patagones")],
    ("RIVERA",                  "BUENOS AIRES"): [("Buenos Aires", "Coronel Pringles")],
    ("CARHUE",                  "BUENOS AIRES"): [("Buenos Aires", "Adolfo Alsina")],
    ("ORENSE",                  "BUENOS AIRES"): [("Buenos Aires", "Tres Arroyos")],
    ("LOPEZ CAMELO",            "BUENOS AIRES"): [("Buenos Aires", "Ramallo")],
    # Córdoba
    ("CORDOBA",                 "CORDOBA"):      [("Córdoba", "Capital")],
    ("VILLA MARIA",             "CORDOBA"):      [("Córdoba", "General San Martín")],
    ("HUINCA RENANCO",          "CORDOBA"):      [("Córdoba", "General Roca")],
    ("DEAN FUNES",              "CORDOBA"):      [("Córdoba", "Ischilín")],
    ("VILLA DE MARIA DE RIO SECO","CORDOBA"):    [("Córdoba", "Río Seco")],
    ("VILLA DEL TOTORAL",       "CORDOBA"):      [("Córdoba", "Totoral")],
    ("JESUS MARIA",             "CORDOBA"):      [("Córdoba", "Colón")],
    ("OLIVA",                   "CORDOBA"):      [("Córdoba", "Tercero Arriba")],
    ("LAS VARILLAS",            "CORDOBA"):      [("Córdoba", "Unión")],
    ("BELL VILLE",              "CORDOBA"):      [("Córdoba", "Unión")],
    ("VILLA CARLOS PAZ",        "CORDOBA"):      [("Córdoba", "Punilla")],
    ("SALSACATE",               "CORDOBA"):      [("Córdoba", "Pocho")],
    ("ARGUELLO",                "CORDOBA"):      [("Córdoba", "Capital")],
    ("VILLA DOLORES",           "CORDOBA"):      [("Córdoba", "San Alberto")],
    ("SANTA ROSA DE CALAMUCHITA","CORDOBA"):     [("Córdoba", "Calamuchita")],
    ("ALTA GRACIA",             "CORDOBA"):      [("Córdoba", "Santa María")],
    ("LA FALDA",                "CORDOBA"):      [("Córdoba", "Punilla")],
    ("MORTEROS",                "CORDOBA"):      [("Córdoba", "San Justo")],
    ("BALNEARIA",               "CORDOBA"):      [("Córdoba", "San Justo")],
    ("SAN FRANCISCO",           "CORDOBA"):      [("Córdoba", "San Justo")],
    ("RIO TERCERO",             "CORDOBA"):      [("Córdoba", "Tercero Arriba")],
    ("VILLA DEL ROSARIO",       "CORDOBA"):      [("Córdoba", "Río Segundo")],
    ("LA PUERTA",               "CORDOBA"):      [("Córdoba", "San Alberto")],
    ("ARROYITO",                "CORDOBA"):      [("Córdoba", "San Justo")],
    ("SAMPACHO",                "CORDOBA"):      [("Córdoba", "Río Cuarto")],
    ("VICUÑA MACKENNA",         "CORDOBA"):      [("Córdoba", "Juárez Celman")],
    ("LA CARLOTA",              "CORDOBA"):      [("Córdoba", "Juárez Celman")],
    ("ADELIA MARIA",            "CORDOBA"):      [("Córdoba", "Juárez Celman")],
    ("CANALS",                  "CORDOBA"):      [("Córdoba", "Marcos Juárez")],
    ("CORRAL DE BUSTOS",        "CORDOBA"):      [("Córdoba", "Marcos Juárez")],
    ("LABOULAYE",               "CORDOBA"):      [("Córdoba", "Presidente Roque Sáenz Peña")],
    ("BOUCHARD",                "CORDOBA"):      [("Córdoba", "General Roca")],
    # Santa Fe
    ("SANTA FE",                "SANTA FE"):     [("Santa Fe", "La Capital")],
    ("VILLA CONSTITUCION",      "SANTA FE"):     [("Santa Fe", "Constitución")],
    ("EL TREBOL",               "SANTA FE"):     [("Santa Fe", "San Justo")],
    ("ARROYO SECO",             "SANTA FE"):     [("Santa Fe", "Rosario")],
    ("SAN CARLOS CENTRO",       "SANTA FE"):     [("Santa Fe", "Las Colonias")],
    ("SAN JORGE",               "SANTA FE"):     [("Santa Fe", "San Justo")],
    ("MOISES VILLE",            "SANTA FE"):     [("Santa Fe", "Las Colonias")],
    ("RECONQUISTA",             "SANTA FE"):     [("Santa Fe", "General Obligado")],
    ("CERES",                   "SANTA FE"):     [("Santa Fe", "San Cristóbal")],
    ("RAFAELA",                 "SANTA FE"):     [("Santa Fe", "Castellanos")],
    ("SUNCHALES",               "SANTA FE"):     [("Santa Fe", "Castellanos")],
    ("ESPERANZA",               "SANTA FE"):     [("Santa Fe", "Las Colonias")],
    ("LLAMBI CAMPBELL",         "SANTA FE"):     [("Santa Fe", "Las Colonias")],
    ("SANTA TERESA",            "SANTA FE"):     [("Santa Fe", "General López")],
    ("VENADO TUERTO",           "SANTA FE"):     [("Santa Fe", "General López")],
    ("CASILDA",                 "SANTA FE"):     [("Santa Fe", "Caseros")],
    ("FIRMAT",                  "SANTA FE"):     [("Santa Fe", "General López")],
    ("BARRANCAS",               "SANTA FE"):     [("Santa Fe", "General López")],
    ("ACEBAL",                  "SANTA FE"):     [("Santa Fe", "Rosario")],
    ("CAÑADA DE GOMEZ",         "SANTA FE"):     [("Santa Fe", "Iriondo")],
    ("RUFINO",                  "SANTA FE"):     [("Santa Fe", "General López")],
    ("SAN JAVIER",              "SANTA FE"):     [("Santa Fe", "San Javier")],
    ("SAN LORENZO",             "SANTA FE"):     [("Santa Fe", "San Lorenzo")],
    ("SAN JUSTO",               "SANTA FE"):     [("Santa Fe", "San Justo")],
    # Entre Ríos
    ("BOVRIL",                  "ENTRE RIOS"):   [("Entre Ríos", "La Paz")],
    ("CONCEPCION DEL URUGUAY",  "ENTRE RIOS"):   [("Entre Ríos", "Uruguay")],
    ("ROSARIO DEL TALA",        "ENTRE RIOS"):   [("Entre Ríos", "Tala")],
    ("CHAJARI",                 "ENTRE RIOS"):   [("Entre Ríos", "Federación")],
    ("SAN JOSE DE FELICIANO",   "ENTRE RIOS"):   [("Entre Ríos", "Feliciano")],
    ("LA PAZ",                  "ENTRE RIOS"):   [("Entre Ríos", "La Paz")],
    ("COLON",                   "ENTRE RIOS"):   [("Entre Ríos", "Colón")],
    # Mendoza
    ("MENDOZA",                 "MENDOZA"):      [("Mendoza", "Capital")],
    ("USPALLATA",               "MENDOZA"):      [("Mendoza", "Las Heras")],
    ("SAN MARTIN",              "MENDOZA"):      [("Mendoza", "San Martín")],
    ("GENERAL ALVEAR",          "MENDOZA"):      [("Mendoza", "General Alvear")],
    ("LA PAZ",                  "MENDOZA"):      [("Mendoza", "La Paz")],
    # San Juan
    ("SAN JUAN",                "SAN JUAN"):     [("San Juan", "Capital")],
    ("SAN AGUSTIN DEL VALLE FERTIL","SAN JUAN"): [("San Juan", "Valle Fértil")],
    # San Luis
    ("SAN LUIS",                "SAN LUIS"):     [("San Luis", "Juan Martín de Pueyrredón")],
    ("SAN FRANCISCO DEL MONTE DE ORO","SAN LUIS"):[("San Luis", "Ayacucho")],
    ("LA TOMA",                 "SAN LUIS"):     [("San Luis", "Coronel Pringles")],
    ("TILISARAO",               "SAN LUIS"):     [("San Luis", "Chacabuco")],
    ("BUENA ESPERANZA",         "SAN LUIS"):     [("San Luis", "Gobernador Dupuy")],
    ("MERCEDES",                "SAN LUIS"):     [("San Luis", "General Pedernera")],
    # La Pampa
    ("SANTA ROSA",              "LA PAMPA"):     [("La Pampa", "Capital")],
    ("GENERAL PICO",            "LA PAMPA"):     [("La Pampa", "Maracó")],
    ("EDUARDO CASTEX",          "LA PAMPA"):     [("La Pampa", "Conhelo")],
    ("CALEUFU",                 "LA PAMPA"):     [("La Pampa", "Rancul")],
    ("VICTORICA",               "LA PAMPA"):     [("La Pampa", "Loventué")],
    ("GENERAL ACHA",            "LA PAMPA"):     [("La Pampa", "Utracán")],
    ("MACACHIN",                "LA Pampa"):     [("La Pampa", "Hucal")],
    # Neuquén
    ("NEUQUEN",                 "NEUQUEN"):      [("Neuquén", "Confluencia")],
    ("SAN MARTIN DE LOS ANDES", "NEUQUEN"):      [("Neuquén", "Lácar")],
    # Río Negro
    ("VIEDMA",                  "RIO NEGRO"):    [("Río Negro", "Adolfo Alsina")],
    ("RIO COLORADO",            "RIO NEGRO"):    [("Río Negro", "Pichi Mahuida")],
    ("SAN ANTONIO OESTE",       "RIO NEGRO"):    [("Río Negro", "San Antonio")],
    ("INGENIERO JACOBACCI",     "RIO NEGRO"):    [("Río Negro", "Ñorquincó")],
    ("CHOELE CHOEL",            "RIO NEGRO"):    [("Río Negro", "Avellaneda")],
    ("GENERAL ROCA",            "RIO NEGRO"):    [("Río Negro", "General Roca")],
    # Chubut
    ("TRELEW",                  "CHUBUT"):       [("Chubut", "Rawson")],
    ("COMODORO RIVADAVIA",      "CHUBUT"):       [("Chubut", "Escalante")],
    ("ESQUEL",                  "CHUBUT"):       [("Chubut", "Futaleufú")],
    ("RIO MAYO",                "CHUBUT"):       [("Chubut", "Río Senguer")],
    # Santa Cruz
    ("RIO GALLEGOS",            "SANTA CRUZ"):   [("Santa Cruz", "Güer Aike")],
    ("SAN JULIAN",              "SANTA CRUZ"):   [("Santa Cruz", "Magallanes")],
    ("PERITO MORENO",           "SANTA CRUZ"):   [("Santa Cruz", "Lago Buenos Aires")],
    ("RIO TURBIO",              "SANTA CRUZ"):   [("Santa Cruz", "Corpen Aike")],
    # Formosa
    ("INGENIERO GUILLERMO N. JUAREZ","FORMOSA"): [("Formosa", "Ramón Lista")],
    ("LAS LOMITAS",             "FORMOSA"):      [("Formosa", "Patiño")],
    ("IBARRETA",                "FORMOSA"):      [("Formosa", "Patiño")],
    ("CLORINDA",                "FORMOSA"):      [("Formosa", "Pilcomayo")],
    # Chaco
    ("RESISTENCIA",             "CHACO"):        [("Chaco", "San Fernando")],
    ("PRESIDENCIA ROQUE SAENZ PEÑA","CHACO"):    [("Chaco", "Comandante Fernández")],
    ("CHARATA",                 "CHACO"):        [("Chaco", "Chacabuco")],
    ("VILLA ANGELA",            "CHACO"):        [("Chaco", "Mayor Luis Jorge Fontana")],
    ("CHARADAI",                "CHACO"):        [("Chaco", "General Donovan")],
    ("SAN MARTIN",              "CHACO"):        [("Chaco", "San Martín")],
    ("SAN LORENZO",             "CHACO"):        [("Chaco", "San Lorenzo")],
    ("LIBERTADOR GENERAL SAN MARTIN","CHACO"):   [("Chaco", "Libertador General San Martín")],
    # Misiones
    ("POSADAS",                 "MISIONES"):     [("Misiones", "Capital")],
    ("BERNARDO DE IRIGOYEN",    "MISIONES"):     [("Misiones", "General Manuel Belgrano")],
    ("PUERTO RICO",             "MISIONES"):     [("Misiones", "Montecarlo")],
    ("PUERTO IGUAZU",           "MISIONES"):     [("Misiones", "Iguazú")],
    ("LEANDRO N. ALEM",         "MISIONES"):     [("Misiones", "Leandro N. Alem")],
    ("SAN JAVIER",              "MISIONES"):     [("Misiones", "San Javier")],
    # Corrientes
    ("CORRIENTES",              "CORRIENTES"):   [("Corrientes", "Capital")],
    ("CAA CATI",                "CORRIENTES"):   [("Corrientes", "General Paz")],
    ("CONCEPCION",              "CORRIENTES"):   [("Corrientes", "Concepción")],
    ("SANTO TOME",              "CORRIENTES"):   [("Corrientes", "Santo Tomé")],
    ("MERCEDES",                "CORRIENTES"):   [("Corrientes", "Mercedes")],
    # La Rioja
    ("LA RIOJA",                "LA RIOJA"):     [("La Rioja", "Capital")],
    ("CHEPES",                  "LA RIOJA"):     [("La Rioja", "General Ángel Vicente Peñaloza")],
    ("AIMOGASTA",               "LA RIOJA"):     [("La Rioja", "Arauco")],
    # Catamarca
    ("CATAMARCA",               "CATAMARCA"):    [("Catamarca", "Capital")],
    ("RECREO",                  "CATAMARCA"):    [("Catamarca", "La Paz")],
    ("LA PAZ",                  "CATAMARCA"):    [("Catamarca", "La Paz")],
    ("SANTA ROSA",              "CATAMARCA"):    [("Catamarca", "Santa Rosa")],
    # Tucumán
    ("SAN MIGUEL DE TUCUMAN",   "TUCUMAN"):      [("Tucumán", "Capital")],
    ("CONCEPCION",              "TUCUMAN"):      [("Tucumán", "Chicligasta")],
    ("RANCHILLOS",              "TUCUMAN"):      [("Tucumán", "Cruz Alta")],
    ("LA MADRID",               "TUCUMAN"):      [("Tucumán", "Graneros")],
    ("AMAICHA DEL VALLE",       "TUCUMAN"):      [("Tucumán", "Tafí del Valle")],
    # Salta
    ("SALTA",                   "SALTA"):        [("Salta", "Capital")],
    ("TARTAGAL",                "SALTA"):        [("Salta", "General José de San Martín")],
    ("JOAQUIN V. GONZALEZ",     "SALTA"):        [("Salta", "Anta")],
    ("SAN MARTIN",              "SALTA"):        [("Salta", "General José de San Martín")],
    # Jujuy
    ("SAN SALVADOR DE JUJUY",   "JUJUY"):        [("Jujuy", "Doctor Manuel Belgrano")],
    ("LA QUIACA",               "JUJUY"):        [("Jujuy", "Yavi")],
    ("SAN PEDRO",               "JUJUY"):        [("Jujuy", "San Pedro")],
    # Santiago del Estero
    ("SANTIAGO DEL ESTERO",     "SANTIAGO DEL ESTERO"): [("Santiago del Estero", "Robles")],
    ("MONTE QUEMADO",           "SANTIAGO DEL ESTERO"): [("Santiago del Estero", "Copo")],
    ("QUIMILI",                 "SANTIAGO DEL ESTERO"): [("Santiago del Estero", "Moreno")],
    ("AÑATUYA",                 "SANTIAGO DEL ESTERO"): [("Santiago del Estero", "General Taboada")],
    ("ANATUYA",                 "SANTIAGO DEL ESTERO"): [("Santiago del Estero", "General Taboada")],
    ("TINTINA",                 "SANTIAGO DEL ESTERO"): [("Santiago del Estero", "Copo")],
    ("FRIAS",                   "SANTIAGO DEL ESTERO"): [("Santiago del Estero", "Choya")],
    ("SUNCHO CORRAL",           "SANTIAGO DEL ESTERO"): [("Santiago del Estero", "Rivadavia")],
    ("BANDERA",                 "SANTIAGO DEL ESTERO"): [("Santiago del Estero", "General Taboada")],
    ("TERMAS DE RIO HONDO",     "SANTIAGO DEL ESTERO"): [("Santiago del Estero", "Río Hondo")],
    ("NUEVA ESPERANZA",         "SANTIAGO DEL ESTERO"): [("Santiago del Estero", "Copo")],
    ("LORETO",                  "SANTIAGO DEL ESTERO"): [("Santiago del Estero", "Loreto")],
    ("OJO DE AGUA",             "SANTIAGO DEL ESTERO"): [("Santiago del Estero", "Ojo de Agua")],
}

# ── Helpers ──────────────────────────────────────────────────────────────────
def normalize(s: str) -> str:
    s = s.upper().strip()
    s = re.sub(r'\(.*?\)', '', s).strip()
    for a, b in [('Á','A'),('É','E'),('Í','I'),('Ó','O'),('Ú','U'),('Ñ','N')]:
        s = s.replace(a, b)
    return s

def to_slug(label: str) -> str:
    label = label.lower()
    for a, b in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),('ñ','n')]:
        label = label.replace(a, b)
    return label.replace(' ', '-')

# ── 1. Leer y modificar SVG con lxml ─────────────────────────────────────────
from lxml import etree

SVG_NS = 'http://www.w3.org/2000/svg'
INKSCAPE_NS = 'http://www.inkscape.org/namespaces/inkscape'
LABEL_ATTR = f'{{{INKSCAPE_NS}}}label'

parser = etree.XMLParser(remove_comments=False)
tree = etree.parse("Mapa_de_Argentina_(subdivisiones) (1).svg", parser)
root = tree.getroot()

# depto_lookup
depto_by_name = {}
depto_by_provname = {}

all_svg_provs = set()
for names in PROV_MAP.values():
    all_svg_provs.update(names)

for g in root.iter(f'{{{SVG_NS}}}g'):
    if g.get(LABEL_ATTR) == 'Departments':
        for prov_g in g:
            prov = prov_g.get(LABEL_ATTR)
            if not prov:
                continue
            norm_prov = normalize(prov)
            for dep_el in prov_g:
                dep = dep_el.get(LABEL_ATTR)
                if not dep:
                    continue
                norm_dep = normalize(dep)
                depto_by_provname[(norm_dep, norm_prov)] = (prov, dep)
                if norm_dep not in depto_by_name:
                    depto_by_name[norm_dep] = []
                depto_by_name[norm_dep].append((prov, dep))
        break

def find_districts(area_raw: str, prov_raw: str) -> list:
    """
    Devuelve lista de {prov, dept} para pintar en el mapa.
    prov y dept son los labels del SVG; dept puede ser None (pinta toda la prov).
    """
    area_norm = normalize(area_raw)
    prov_norm = normalize(prov_raw)

    # 1. Manual map con provincia
    key_with_prov = (area_norm, prov_norm)
    if key_with_prov in MANUAL_MAP:
        return [{"prov": p, "dept": d} for p, d in MANUAL_MAP[key_with_prov]]

    # 2. Manual map sin provincia (AMBA)
    key_no_prov = (area_norm, None)
    if key_no_prov in MANUAL_MAP:
        return [{"prov": p, "dept": d} for p, d in MANUAL_MAP[key_no_prov]]

    # 3. Lookup departamento + provincia
    svg_provs = PROV_MAP.get(prov_norm, [])
    for svg_prov in svg_provs:
        norm_svg_prov = normalize(svg_prov)
        match = depto_by_provname.get((area_norm, norm_svg_prov))
        if match:
            return [{"prov": match[0], "dept": match[1]}]

    # 4. Lookup departamento solo (puede haber múltiples matches)
    matches = depto_by_name.get(area_norm, [])
    if len(matches) == 1:
        return [{"prov": matches[0][0], "dept": matches[0][1]}]

    # 5. Fallback: pintar provincia completa
    result = []
    for svg_prov in svg_provs:
        result.append({"prov": svg_prov, "dept": None})
    return result if result else [{"prov": prov_raw.title(), "dept": None}]

# ── 2. Leer Excel ─────────────────────────────────────────────────────────────
df = pd.read_excel("Indicativos Interurbanos (300 A.L.).xls")
df.columns = ["prefijo", "area", "provincia"]
df["prefijo"]   = df["prefijo"].astype(str)
df["area"]      = df["area"].str.strip()
df["provincia"] = df["provincia"].str.strip()

data = []
for _, row in df.iterrows():
    districts = find_districts(row["area"], row["provincia"])
    data.append({
        "prefijo":   row["prefijo"],
        "area":      row["area"],
        "provincia": row["provincia"],
        "districts": districts,   # [{prov, dept}, ...]
    })

# Debug: mostrar cobertura
matched_dept = sum(1 for d in data if d["districts"] and d["districts"][0]["dept"] is not None)
matched_prov = sum(1 for d in data if d["districts"] and d["districts"][0]["dept"] is None)
print(f"Match departamento: {matched_dept}/300")
print(f"Fallback provincia: {matched_prov}/300")

# ── 3. Modificar SVG con lxml: agregar id/class a provincias Y departamentos ──
prov_labels = set(all_svg_provs)

for g in root.iter(f'{{{SVG_NS}}}g'):
    if g.get(LABEL_ATTR) == 'Departments':
        for prov_el in g:
            prov = prov_el.get(LABEL_ATTR)
            if not prov or prov not in prov_labels:
                continue
            pslug = to_slug(prov)
            # Marcar provincia
            prov_el.set('id', f'prov-{pslug}')
            prov_el.set('class', 'province')
            prov_el.set('data-prov', pslug)

            # Marcar cada departamento (puede ser <g> o <path>)
            for dep_el in prov_el:
                dep = dep_el.get(LABEL_ATTR)
                if not dep:
                    continue
                dslug = to_slug(dep)
                dep_el.set('id', f'dept-{pslug}--{dslug}')
                dep_el.set('class', 'dept')
                dep_el.set('data-prov', pslug)
                dep_el.set('data-dept', dslug)
        break

# Serializar con lxml (preserva namespaces correctamente)
svg_bytes = etree.tostring(root, encoding='unicode', xml_declaration=False)
# lxml incluye xmlns en el root, lo que está bien para HTML embebido
svg_str = svg_bytes

# ── 4. Construir HTML ─────────────────────────────────────────────────────────
data_json = json.dumps(data, ensure_ascii=False)

html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Mapa de Prefijos Argentina</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Segoe UI', system-ui, sans-serif;
      background: #0f172a;
      color: #e2e8f0;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }}
    header {{
      padding: 12px 24px;
      background: #1e293b;
      border-bottom: 1px solid #334155;
      display: flex;
      align-items: center;
      gap: 12px;
      flex-shrink: 0;
    }}
    header h1 {{ font-size: 1rem; font-weight: 600; color: #f1f5f9; }}
    header span {{ font-size: 0.78rem; color: #94a3b8; }}
    .layout {{ display: flex; flex: 1; overflow: hidden; }}

    /* MAP */
    .map-panel {{
      flex: 1 1 58%;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px;
      background: #0f172a;
      overflow: hidden;
    }}
    .map-panel svg {{
      max-height: 100%;
      max-width: 100%;
      height: 100%;
      width: auto;
      filter: drop-shadow(0 4px 24px rgba(0,0,0,.5));
    }}

    /* SIDEBAR */
    .sidebar {{
      flex: 0 0 370px;
      display: flex;
      flex-direction: column;
      background: #1e293b;
      border-left: 1px solid #334155;
      overflow: hidden;
    }}
    .sidebar-section {{ padding: 14px; border-bottom: 1px solid #334155; }}
    .sidebar-section label {{
      display: block; font-size: 0.72rem;
      text-transform: uppercase; letter-spacing: .05em;
      color: #94a3b8; margin-bottom: 7px;
    }}
    .search-wrap {{ position: relative; }}
    .search-wrap input {{
      width: 100%; padding: 8px 10px 8px 34px;
      background: #0f172a; border: 1px solid #334155;
      border-radius: 6px; color: #e2e8f0; font-size: 0.88rem; outline: none;
    }}
    .search-wrap input:focus {{ border-color: #3b82f6; }}
    .search-wrap .ico {{
      position: absolute; left: 9px; top: 50%;
      transform: translateY(-50%); color: #64748b; font-size: .95rem;
    }}
    .prefix-list {{
      max-height: 270px; overflow-y: auto; margin-top: 7px;
      border: 1px solid #334155; border-radius: 6px; background: #0f172a;
    }}
    .prefix-list::-webkit-scrollbar {{ width: 5px; }}
    .prefix-list::-webkit-scrollbar-thumb {{ background: #334155; border-radius: 3px; }}
    .prefix-item {{
      display: flex; align-items: center; gap: 9px;
      padding: 7px 10px; cursor: pointer;
      border-bottom: 1px solid #1e293b; transition: background .12s;
      user-select: none;
    }}
    .prefix-item:last-child {{ border-bottom: none; }}
    .prefix-item:hover {{ background: #1e293b; }}
    .prefix-item.selected {{ background: #1e3a5f; }}
    .prefix-badge {{
      background: #1e40af; color: #bfdbfe; font-size: 0.72rem;
      font-weight: 700; padding: 2px 6px; border-radius: 4px;
      min-width: 42px; text-align: center; flex-shrink: 0;
    }}
    .prefix-item.selected .prefix-badge {{ background: #3b82f6; color: #fff; }}
    .prefix-info {{ font-size: 0.8rem; line-height: 1.3; }}
    .prefix-info .city {{ color: #e2e8f0; font-weight: 500; }}
    .prefix-info .prov {{ color: #64748b; font-size: 0.72rem; }}
    .dept-tag {{
      margin-left: auto; font-size: 0.68rem; color: #475569;
      background: #0f172a; padding: 2px 6px; border-radius: 3px;
      flex-shrink: 0; max-width: 110px; text-align: right;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }}
    .prefix-item.selected .dept-tag {{ color: #60a5fa; background: #1e293b; }}

    .actions {{ display: flex; gap: 7px; }}
    .btn {{
      flex: 1; padding: 7px 10px; border-radius: 6px; border: none;
      cursor: pointer; font-size: 0.8rem; font-weight: 600; transition: background .15s;
    }}
    .btn-clear {{ background: #334155; color: #cbd5e1; }}
    .btn-clear:hover {{ background: #475569; }}
    .btn-all {{ background: #1e3a5f; color: #93c5fd; }}
    .btn-all:hover {{ background: #1e40af; color: #fff; }}

    .table-wrap {{ flex: 1; overflow-y: auto; padding: 0 14px 14px; }}
    .table-wrap::-webkit-scrollbar {{ width: 5px; }}
    .table-wrap::-webkit-scrollbar-thumb {{ background: #334155; border-radius: 3px; }}
    .selected-title {{
      font-size: 0.72rem; text-transform: uppercase;
      letter-spacing: .05em; color: #94a3b8; padding: 10px 0 7px;
    }}
    .selected-count {{
      display: inline-block; background: #1e40af; color: #bfdbfe;
      border-radius: 10px; padding: 1px 7px; font-size: 0.68rem; margin-left: 5px;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; }}
    thead th {{
      position: sticky; top: 0; background: #1e293b;
      padding: 7px 8px; text-align: left; color: #64748b;
      font-weight: 600; font-size: 0.7rem; text-transform: uppercase;
      border-bottom: 1px solid #334155; z-index: 1;
    }}
    tbody tr {{ border-bottom: 1px solid #1e293b; transition: background .1s; }}
    tbody tr:hover {{ background: #1e3a5f22; }}
    tbody td {{ padding: 6px 8px; color: #cbd5e1; vertical-align: middle; }}
    tbody td:first-child {{ font-weight: 700; color: #60a5fa; font-family: monospace; }}
    .empty-msg {{ text-align: center; color: #475569; padding: 28px 0; font-size: 0.82rem; }}
    .swatch {{
      display: inline-block; width: 9px; height: 9px;
      border-radius: 50%; margin-right: 5px; vertical-align: middle; flex-shrink: 0;
    }}
    .prov-badge {{
      font-size: 0.65rem; color: #64748b;
      display: block; margin-top: 1px;
    }}
  </style>
</head>
<body>
<header>
  <h1>Prefijos Interurbanos — Argentina</h1>
  <span>Seleccioná prefijos para resaltar departamentos en el mapa</span>
</header>
<div class="layout">
  <div class="map-panel" id="mapPanel">
    {svg_str}
  </div>
  <div class="sidebar">
    <div class="sidebar-section">
      <label>Buscar por prefijo / ciudad / provincia</label>
      <div class="search-wrap">
        <span class="ico">🔍</span>
        <input type="text" id="searchInput" placeholder="Ej: 351, Rosario, Santa Fe…" autocomplete="off" />
      </div>
      <div class="prefix-list" id="prefixList"></div>
    </div>
    <div class="sidebar-section">
      <div class="actions">
        <button class="btn btn-clear" onclick="clearAll()">Limpiar todo</button>
        <button class="btn btn-all"   onclick="selectVisible()">Seleccionar visibles</button>
      </div>
    </div>
    <div class="table-wrap">
      <div class="selected-title">
        Seleccionados <span class="selected-count" id="countBadge">0</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>Prefijo</th>
            <th>Área Local</th>
            <th>Provincia</th>
          </tr>
        </thead>
        <tbody id="tableBody">
          <tr><td colspan="3" class="empty-msg">Ningún prefijo seleccionado</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</div>

<script>
const DATA = {data_json};

const PALETTE = [
  '#3b82f6','#ef4444','#22c55e','#f59e0b','#a855f7',
  '#06b6d4','#f97316','#ec4899','#14b8a6','#84cc16',
  '#6366f1','#e11d48','#0ea5e9','#d97706','#7c3aed',
  '#059669','#dc2626','#2563eb','#65a30d','#db2777',
];

// colores asignados por (prov--dept) o (prov)
const zoneColors = {{}};
let colorIdx = 0;

function zoneKey(prov, dept) {{
  return dept ? `${{prov}}--${{dept}}` : prov;
}}

function getColor(prov, dept) {{
  const k = zoneKey(prov, dept);
  if (!zoneColors[k]) zoneColors[k] = PALETTE[colorIdx++ % PALETTE.length];
  return zoneColors[k];
}}

const selected = new Set();

// Inicializar mapa: gris en todos los paths del mapa
function initMap() {{
  // Pintar gris solo los paths dentro de departamentos o provincias
  document.querySelectorAll('#mapPanel svg .dept, #mapPanel svg .province').forEach(el => {{
    if (el.tagName === 'path') {{
      const s = el.getAttribute('style') || '';
      el.setAttribute('style', s.replace(/fill:[^;]+/, 'fill:#cbd5e1'));
    }} else {{
      el.querySelectorAll('path').forEach(p => {{
        const s = p.getAttribute('style') || '';
        p.setAttribute('style', s.replace(/fill:[^;]+/, 'fill:#cbd5e1'));
      }});
    }}
  }});
}}

function toSlug(s) {{
  return s.toLowerCase()
    .replace(/á/g,'a').replace(/é/g,'e').replace(/í/g,'i')
    .replace(/ó/g,'o').replace(/ú/g,'u').replace(/ñ/g,'n')
    .replace(/\\s+/g,'-');
}}

function paintEl(el, color) {{
  if (!el) return;
  if (el.tagName === 'path') {{
    // departamento es un <path> directo
    const s = el.getAttribute('style') || '';
    el.setAttribute('style', s.replace(/fill:[^;]+/, `fill:${{color}}`));
  }} else {{
    // departamento es un <g> con paths dentro
    el.querySelectorAll('path').forEach(p => {{
      const s = p.getAttribute('style') || '';
      p.setAttribute('style', s.replace(/fill:[^;]+/, `fill:${{color}}`));
    }});
  }}
}}

function updateMap() {{
  // Reset
  initMap();

  // Recolectar zonas activas
  DATA.forEach(item => {{
    if (!selected.has(item.prefijo)) return;
    item.districts.forEach(d => {{
      const color = getColor(d.prov, d.dept);
      if (d.dept) {{
        const pslug = toSlug(d.prov);
        const dslug = toSlug(d.dept);
        const el = document.getElementById(`dept-${{pslug}}--${{dslug}}`);
        paintEl(el, color);
      }} else {{
        const pslug = toSlug(d.prov);
        const el = document.getElementById(`prov-${{pslug}}`);
        paintEl(el, color);
      }}
    }});
  }});
}}

function renderList(filter='') {{
  const list = document.getElementById('prefixList');
  const fl = filter.toLowerCase();
  list.innerHTML = '';
  DATA.forEach(item => {{
    if (fl && !item.prefijo.includes(fl) &&
               !item.area.toLowerCase().includes(fl) &&
               !item.provincia.toLowerCase().includes(fl)) return;
    const isSel = selected.has(item.prefijo);
    const deptLabel = item.districts[0]?.dept || '';
    const div = document.createElement('div');
    div.className = 'prefix-item' + (isSel ? ' selected' : '');
    div.dataset.prefijo = item.prefijo;
    div.innerHTML = `
      <span class="prefix-badge">${{item.prefijo}}</span>
      <span class="prefix-info">
        <span class="city">${{item.area}}</span><br>
        <span class="prov">${{item.provincia}}</span>
      </span>
      ${{deptLabel ? `<span class="dept-tag">${{deptLabel}}</span>` : ''}}`;
    div.addEventListener('click', () => toggleItem(item.prefijo));
    list.appendChild(div);
  }});
  if (!list.children.length)
    list.innerHTML = '<div style="padding:10px;color:#475569;font-size:.8rem">Sin resultados</div>';
}}

function toggleItem(prefijo) {{
  selected.has(prefijo) ? selected.delete(prefijo) : selected.add(prefijo);
  updateMap();
  updateTable();
  renderList(document.getElementById('searchInput').value);
}}

function clearAll() {{
  selected.clear();
  updateMap();
  updateTable();
  renderList(document.getElementById('searchInput').value);
}}

function selectVisible() {{
  document.querySelectorAll('#prefixList .prefix-item').forEach(el => selected.add(el.dataset.prefijo));
  updateMap();
  updateTable();
  renderList(document.getElementById('searchInput').value);
}}

function updateTable() {{
  const tbody = document.getElementById('tableBody');
  const badge = document.getElementById('countBadge');
  const rows = DATA.filter(d => selected.has(d.prefijo));
  badge.textContent = rows.length;
  if (!rows.length) {{
    tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">Ningún prefijo seleccionado</td></tr>';
    return;
  }}
  tbody.innerHTML = rows.map(r => {{
    const d = r.districts[0] || {{}};
    const color = d.prov ? getColor(d.prov, d.dept) : '#64748b';
    const deptInfo = d.dept
      ? `<span class="prov-badge">${{d.dept}}</span>`
      : `<span class="prov-badge" style="color:#94a3b8">(provincia)</span>`;
    return `<tr>
      <td>${{r.prefijo}}</td>
      <td><span class="swatch" style="background:${{color}}"></span>${{r.area}}${{deptInfo}}</td>
      <td>${{r.provincia}}</td>
    </tr>`;
  }}).join('');
}}

document.getElementById('searchInput').addEventListener('input', e => renderList(e.target.value));

initMap();
renderList();
</script>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)

print("index.html generado.")
