"""Punto de entrada de la aplicación: `python -m src.web`.

Aquí, y no en `app.py`, vive la única línea que conoce la capa que arma el ledger
y el servicio de cuentas: el módulo de la aplicación tiene que poder importarse sin
arrastrar el motor (REQ-29), y quien cablea las fábricas reales es este arranque.
La clave de la cookie también se resuelve acá, con el lector que sabe mirar el
entorno y el `.env` (REQ-37).
"""
import os
from contextlib import contextmanager

from src.accounts.almacen import CarpetaDeFotos
from src.accounts.service import Cuentas
from src.persistence.factory import (
    carpeta_de_fotos,
    configuracion_del_asistente,
    ledger,
    session_secret,
    transaction,
)
from src.web.app import create_app


@contextmanager
def cuentas():
    """Entrega un servicio de cuentas por petición sobre la transacción real.

    `Cuentas` no guarda conexión: cada operación abre la que necesita con la
    fábrica recibida. Se arma por petición igual que el ledger para que la
    presentación no dependa de una instancia compartida entre hilos. Las fotos
    de perfil son archivos en la carpeta de `FOTOS_DIR`.
    """
    yield Cuentas(transaction, fotos=CarpetaDeFotos(carpeta_de_fotos()))


app = create_app(
    ledger,
    cuentas,
    secret_key=session_secret(),
    asistente=configuracion_del_asistente(),
)


if __name__ == "__main__":
    conector = app.extensions.get("asistente")
    if conector is None:
        print(" * Ayudante: sin IA configurada, contesta con su guía local")
    else:
        print(f" * Ayudante: conectado a {conector.proveedor.nombre} ({conector.modelo})")
    # El depurador interactivo y el recargador no van por defecto: el primero deja
    # ejecutar código desde el navegador y el segundo reinicia el proceso en cada
    # cambio. Se activan con `FLASK_DEBUG=1` en el entorno, para desarrollo local.
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
