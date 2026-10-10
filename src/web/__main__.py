"""Punto de entrada de la aplicación: `python -m src.web`.

Aquí, y no en `app.py`, vive la única línea que conoce la capa que arma el ledger:
el módulo de la aplicación tiene que poder importarse sin arrastrar el motor
(REQ-29), y quien cablea la fábrica real es este arranque.
"""
import os

from src.persistence.factory import ledger
from src.web.app import create_app

app = create_app(ledger)


if __name__ == "__main__":
    # El depurador interactivo y el recargador no van por defecto: el primero deja
    # ejecutar código desde el navegador y el segundo reinicia el proceso en cada
    # cambio. Se activan con `FLASK_DEBUG=1` en el entorno, para desarrollo local.
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
