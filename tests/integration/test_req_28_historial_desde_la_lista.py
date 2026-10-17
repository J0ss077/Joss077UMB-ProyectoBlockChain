"""REQ-28 y CU-05: el historial de cualquier wallet se alcanza desde la lista.

El caso de uso funcionaba, pero para demostrarlo había que teclear a mano una llave
pública de 66 caracteres que no aparecía en ninguna página: `GET /wallets` solo
mostraba el formulario y las wallets existentes únicamente se veían dentro del
formulario de transacciones, donde no se pueden copiar. La lista vive ahora en el
panel lateral de `base.html`, así que está en las cinco rutas —las que ya existen
(REQ-24 a REQ-29)— sin agregar una sexta al eje.

La prueba pide el cliente de Flask contra la base de verdad y con la fachada real,
igual que `test_req_24_rutas.py`: lo que mide es el recorrido de la ruta y no la
fachada.
"""
from contextlib import contextmanager

import pytest

from src.domain.blockchain import ensure_genesis
from src.persistence.factory import open_ledger
from tests.integration.conftest import (
    CONTRASENA_DEL_ADMINISTRADOR,
    crear_app_de_prueba,
    ingresar_como,
)


@pytest.fixture
def cliente(
    conexion, base_limpia, master_key, base_vacia_ejecutando_bootstrap, administrador
):
    """El cliente de Flask sobre la conexión de la prueba, ya con sesión de administrador.

    Las rutas del eje exigen administrador (REQ-38); la prueba entra con la cuenta
    sembrada y después pide la lista. La fábrica entrega la fachada sobre la
    conexión de la sesión y no abre otra: así lo que escribe una ruta queda visible
    para las aserciones en el mismo instante.
    """

    @contextmanager
    def fabrica():
        chain = open_ledger(conexion, encryption_key=master_key)
        ensure_genesis(chain)
        yield chain

    cliente = crear_app_de_prueba(fabrica).test_client()
    ingresar_como(cliente, administrador.username, CONTRASENA_DEL_ADMINISTRADOR)
    return cliente


@pytest.fixture
def wallet_de_prueba(base_vacia_ejecutando_bootstrap):
    """Una wallet registrada por la fachada, para que la lista tenga qué mostrar."""
    return base_vacia_ejecutando_bootstrap.register_wallet()


def test_req_28_la_lista_de_wallets_lleva_al_historial(cliente, wallet_de_prueba):
    """REQ-28 y CU-05: el historial de cualquier wallet se alcanza desde la lista de wallets."""
    listado = cliente.get("/wallets")
    assert listado.status_code == 200
    cuerpo = listado.get_data(as_text=True)
    # El valor completo sigue en el marcado (`title` y `data-copiar`) y la forma
    # corta es la que se ve; el enlace directo lleva al historial.
    assert wallet_de_prueba.public_key in cuerpo
    assert wallet_de_prueba.public_key[:8] in cuerpo
    enlace = f"/historial/{wallet_de_prueba.id}"
    assert enlace in cuerpo                            # el enlace directo
    assert cliente.get(enlace).status_code == 200       # y el enlace funciona
