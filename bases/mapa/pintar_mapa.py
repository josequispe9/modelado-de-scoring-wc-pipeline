"""
Script para pintar zonas del mapa SVG de Argentina.
Usa xml.etree.ElementTree para modificar los estilos de los paths.
"""

import xml.etree.ElementTree as ET
import copy
import re

# Namespaces del SVG
NS = {
    'svg': 'http://www.w3.org/2000/svg',
    'inkscape': 'http://www.inkscape.org/namespaces/inkscape',
    'sodipodi': 'http://sodipodi.sourceforge.net/DTD/sodipodi-0.0',
}

# Registrar namespaces para preservar prefijos al guardar
ET.register_namespace('', 'http://www.w3.org/2000/svg')
ET.register_namespace('inkscape', 'http://www.inkscape.org/namespaces/inkscape')
ET.register_namespace('sodipodi', 'http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd')
ET.register_namespace('svg', 'http://www.w3.org/2000/svg')
ET.register_namespace('rdf', 'http://www.w3.org/1999/02/22-rdf-syntax-ns#')
ET.register_namespace('cc', 'http://creativecommons.org/ns#')
ET.register_namespace('dc', 'http://purl.org/dc/elements/1.1/')

SVG_NS = 'http://www.w3.org/2000/svg'
INKSCAPE_NS = 'http://www.inkscape.org/namespaces/inkscape'

LABEL_ATTR = f'{{{INKSCAPE_NS}}}label'


def set_fill_in_style(style_str: str, color: str) -> str:
    """Reemplaza el fill en un atributo style inline."""
    if 'fill:' in style_str:
        return re.sub(r'fill:[^;]+', f'fill:{color}', style_str)
    return style_str + f';fill:{color}'


def pintar_provincia(root: ET.Element, provincia: str, color: str) -> int:
    """
    Pinta todos los paths dentro de la provincia indicada.
    Retorna la cantidad de paths modificados.
    """
    count = 0
    # Buscar el grupo de la provincia (hijo directo de layer1)
    for layer in root.iter(f'{{{SVG_NS}}}g'):
        if layer.get(LABEL_ATTR) == provincia:
            # Pintar todos los paths dentro de este grupo
            for path in layer.iter(f'{{{SVG_NS}}}path'):
                style = path.get('style', '')
                path.set('style', set_fill_in_style(style, color))
                count += 1
            break
    return count


def listar_provincias(root: ET.Element) -> list[str]:
    """Lista todas las provincias (grupos de segundo nivel)."""
    provincias = []
    # Encontrar layer1 (Departments)
    for g in root.iter(f'{{{SVG_NS}}}g'):
        if g.get(LABEL_ATTR) == 'Departments':
            for child in g:
                label = child.get(LABEL_ATTR)
                if label:
                    provincias.append(label)
            break
    return provincias


def main():
    svg_input = "Mapa_de_Argentina_(subdivisiones) (1).svg"
    svg_output = "mapa_pintado.svg"

    tree = ET.parse(svg_input)
    root = tree.getroot()

    # Mostrar todas las provincias disponibles
    provincias = listar_provincias(root)
    print("Provincias/regiones encontradas en el SVG:")
    for p in provincias:
        print(f"  - {p}")

    print()

    # Ejemplo: pintar con una escala de colores (simula datos de un dashboard)
    datos_dashboard = {
        "Buenos Aires":      "#1a6faf",   # azul oscuro  (valor alto)
        "Córdoba":           "#4a9fd4",   # azul medio
        "Santa Fe":          "#7fc4e8",   # azul claro
        "Mendoza":           "#f4a460",   # naranja
        "Tucumán":           "#e07b39",   # naranja oscuro
        "Salta":             "#c0392b",   # rojo
        "Misiones":          "#27ae60",   # verde
        "Entre Ríos":        "#2ecc71",   # verde claro
        "Chaco":             "#f39c12",   # amarillo
        "Santiago del Estero": "#d4ac0d", # dorado
    }

    print("Pintando provincias...")
    for provincia, color in datos_dashboard.items():
        n = pintar_provincia(root, provincia, color)
        if n:
            print(f"  ✓ {provincia}: {n} paths pintados con {color}")
        else:
            print(f"  ✗ {provincia}: no encontrada")

    tree.write(svg_output, encoding='unicode', xml_declaration=True)
    print(f"\nArchivo guardado: {svg_output}")


if __name__ == "__main__":
    main()
