"""
Modo standalone — ejecutar manualmente desde cualquier PC.

Activa MODO_INTERACTIVO: el navegador queda abierto al finalizar y espera
que el operador presione ENTER antes de cerrar. Util para pruebas y auditorias.

Uso:
    python run_standalone.py

Requiere:
    - .env.tuberia en la raiz del proyecto
    - pip install -r requirements-pipeline.txt
"""
import os

os.environ["MODO_INTERACTIVO"] = "1"

from scraping_mitrol import main

if __name__ == "__main__":
    main()
