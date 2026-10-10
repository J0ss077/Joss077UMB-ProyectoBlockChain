"""REQ-28 y CU-05: el historial de cualquier wallet se alcanza desde la lista.

El caso de uso funcionaba, pero para demostrarlo había que teclear a mano una llave
pública de 66 caracteres que no aparecía en ninguna página: `GET /wallets` solo
mostraba el formulario y las wallets existentes únicamente se veían dentro del
formulario de transacciones, donde no se pueden copiar. La lista va dentro de esa
ruta, que ya existe (REQ-24 a REQ-29), para no agregar una sexta al eje.

La prueba pide el cliente de Flask contra la base de verdad y con la fachada real,
igual que `test_req_24_rutas.py`: lo que mide es el recorrido de la ruta y no la
fachada.
"""
from contextlib import contextmanager

import pytest

from src.domain.blockchain import ensure_genesis
from src.persistence.factory import open_ledger
from src.web.app import create_app


@pytest.fixture
def cliente(conexion, base_limpia, master_key, base_vacia_ejecutando_bootstrap):
    """El cliente de Flask sobre la conexión de la prueba, con la demostración cargada.

    La fábrica entrega la fachada sobre la conexión de la sesión y no abre otra: así
    lo que escribe una ruta queda visible para las aserciones en el mismo instante.
    """

    @contextmanager
    def fabrica():
        chain = open_ledger(conexion, encryption_key=master_key)
        ensure_genesis(chain)
        yield chain

    return create_app(fabrica).test_client()


@pytest.fixture
def wallet_de_prueba(base_vacia_ejecutando_bootstrap):
    """Una wallet registrada por la fachada, para que la lista tenga qué mostrar."""
    return base_vacia_ejecutando_bootstrap.register_wallet()


def test_req_28_la_lista_de_wallets_lleva_al_historial(cliente, wallet_de_prueba):
    """REQ-28 y CU-05: el historial de cualquier wallet se alcanza desde la lista de wallets."""
    listado = cliente.get("/wallets")
    assert listado.status_code == 200
    cuerpo = listado.get_data(as_text=True)
    assert wallet_de_prueba.public_key in cuerpo      # la llave completa, copiable
    enlace = f"/historial/{wallet_de_prueba.id}"
    assert enlace in cuerpo                            # el enlace directo
    assert cliente.get(enlace).status_code == 200       # y el enlace funciona
