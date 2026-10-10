"""REQ-24 a REQ-29: la presentación hace los casos de uso del eje.

Cada ruta toma su formulario, llama a la fachada del ledger y devuelve una página
con el resultado. Las pruebas piden el cliente contra la base de verdad y con la
fachada real, porque lo que miden es el recorrido de la ruta y no la fachada.

Los tres casos de REQ-29 viven aquí, con las demás pruebas de las páginas, porque
miden lo que se ve: que la interfaz no explique el proyecto, que el panel lateral
esté en todas las páginas y que los datos vayan en monoespaciada.

El escenario es el de la demostración del arranque: el fondo y los asociados ya
tienen saldo confirmado, así que las transacciones que proponen las pruebas se
aceptan por las reglas reales (REQ-05) y no por un atajo.
"""
from contextlib import contextmanager
from decimal import Decimal
from uuid import uuid4

import pytest

from src.bootstrap import CONSTITUYENTE_ID, FONDO
from src.domain.blockchain import ensure_genesis
from src.persistence.factory import open_ledger
from src.web.app import create_app

MONTO = "10.00000000"


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
def cadena(base_vacia_ejecutando_bootstrap):
    """La fachada sobre la conexión de la prueba, con la demostración cargada."""
    return base_vacia_ejecutando_bootstrap


@pytest.fixture
def partes(cadena):
    """El fondo y un asociado con saldo, que son los actores del caso del eje.

    El constituyente se excluye a propósito y no por su saldo: es la wallet por la
    que el capital entra al ledger y la única que queda en negativo, así que no es un
    asociado del ciclo de aportes y retiros.
    """
    fondo = cadena.wallets.get_by_public_key(FONDO)
    asociados = [
        wallet
        for wallet in cadena.wallets.list()
        if wallet.id not in {fondo.id, CONSTITUYENTE_ID}
    ]
    asociado = next(
        wallet for wallet in asociados if cadena.available_balance(wallet.id) > 0
    )
    return {"fondo": fondo, "asociado": asociado}


@pytest.fixture
def wallet_de_prueba(cadena):
    """Una wallet registrada por la fachada, para que el panel lateral tenga qué mostrar."""
    return cadena.register_wallet()


@pytest.fixture
def cadena_alterada(cadena, partes, conexion):
    """Una cadena con un bloque confirmado, la alteración hecha a mano y su índice.

    Se altera con `UPDATE` directo, que es la demostración del eje: la fila cambia
    sin pasar por la fachada, así que la única forma de detectarlo es recalcular el
    hash del bloque que la agrupa.
    """
    resultado = cadena.create_transaction(
        sender_id=partes["fondo"].id,
        receiver_id=partes["asociado"].id,
        amount=Decimal(MONTO),
    )
    bloque = cadena.group_pending()
    conexion.execute(
        "UPDATE transactions SET amount = amount + 1 WHERE id = %s",
        (resultado.stored.id,),
    )
    return bloque.block_index


def test_req_24_post_wallets_devuelve_200_con_la_publica(cliente, cadena):
    """REQ-24: la ruta registra la wallet y la página muestra su clave pública."""
    respuesta = cliente.post("/wallets")

    assert respuesta.status_code == 200
    registrada = cadena.wallets.list()[-1]
    texto = respuesta.get_data(as_text=True)
    # Con la forma corta, la llave completa sigue en el marcado (`title` y
    # `data-copiar`) y la que se ve es la corta: la aserción no se debilita.
    assert registrada.public_key in texto
    assert registrada.public_key[:8] in texto


def test_req_25_post_transacciones_devuelve_el_estado(cliente, partes):
    """REQ-25: la ruta propone la transacción y la página muestra su estado."""
    respuesta = cliente.post(
        "/transacciones",
        data={
            "sender_id": str(partes["fondo"].id),
            "receiver_id": str(partes["asociado"].id),
            "amount": MONTO,
        },
    )

    assert respuesta.status_code == 200
    texto = respuesta.get_data(as_text=True)
    assert "pending" in texto
    assert MONTO in texto


def test_req_25_post_transacciones_muestra_el_motivo_del_rechazo(cliente, partes):
    """REQ-25 (CU-02): cuando se rechaza, la página muestra el motivo del rechazo."""
    respuesta = cliente.post(
        "/transacciones",
        data={
            "sender_id": str(partes["fondo"].id),
            "receiver_id": str(partes["asociado"].id),
            "amount": "99999999.00000000",
        },
    )

    assert respuesta.status_code == 200
    # El motivo va en la página porque el CU-02 lo pide: quien propone tiene que
    # saber por qué no entró al pool.
    assert "saldo disponible no alcanza" in respuesta.get_data(as_text=True)


def test_req_25_post_transacciones_con_monto_nan_responde_el_rechazo(cliente, partes):
    """REQ-25: un monto no finito responde el rechazo en la página y no una excepción."""
    respuesta = cliente.post(
        "/transacciones",
        data={
            "sender_id": str(partes["fondo"].id),
            "receiver_id": str(partes["asociado"].id),
            "amount": "NaN",
        },
    )

    assert respuesta.status_code == 200
    assert "el monto debe ser mayor que cero" in respuesta.get_data(as_text=True)


def test_req_25_post_transacciones_con_una_fila_nan_en_la_base_no_cae(
    cliente, partes, conexion
):
    """REQ-25: un saldo envenenado por una fila `NaN` insertada directo no es un 500.

    El CHECK del esquema no detiene esa fila —PostgreSQL evalúa `'NaN'::numeric > 0`
    como verdadero—, así que la defensa tiene que estar en el dominio.
    """
    conexion.execute(
        "INSERT INTO transactions (id, sender_id, receiver_id, amount, status, signature, block_id)"
        " VALUES (%s, %s, %s, 'NaN', 'pending', %s, NULL)",
        (uuid4(), partes["fondo"].id, partes["asociado"].id, "firma-nan-de-la-prueba"),
    )

    respuesta = cliente.post(
        "/transacciones",
        data={
            "sender_id": str(partes["fondo"].id),
            "receiver_id": str(partes["asociado"].id),
            "amount": MONTO,
        },
    )

    assert respuesta.status_code == 200
    assert "saldo disponible no alcanza" in respuesta.get_data(as_text=True)


def test_req_26_post_bloques_devuelve_el_bloque_creado(cliente, cadena, partes):
    """REQ-26: la ruta agrupa el pool y la página muestra el bloque creado."""
    cadena.create_transaction(
        sender_id=partes["fondo"].id,
        receiver_id=partes["asociado"].id,
        amount=Decimal(MONTO),
    )

    respuesta = cliente.post("/bloques")

    assert respuesta.status_code == 200
    texto = respuesta.get_data(as_text=True)
    assert str(cadena.blocks.last().block_index) in texto
    assert cadena.blocks.last().hash in texto


def test_req_27_get_verificar_devuelve_el_dictamen_y_el_bloque_alterado(cliente, cadena_alterada):
    """REQ-27: la verificación informa que la cadena no es válida y dónde se alteró."""
    respuesta = cliente.get("/verificar")

    assert respuesta.status_code == 200
    texto = respuesta.get_data(as_text=True)
    assert "no es válida" in texto
    assert str(cadena_alterada) in texto


def test_req_28_get_historial_devuelve_las_transacciones_con_su_estado(cliente, cadena, partes):
    """REQ-28: el historial de una wallet lista sus transacciones con el estado."""
    cadena.create_transaction(
        sender_id=partes["fondo"].id,
        receiver_id=partes["asociado"].id,
        amount=Decimal(MONTO),
    )

    respuesta = cliente.get(f"/historial/{partes['asociado'].id}")

    assert respuesta.status_code == 200
    texto = respuesta.get_data(as_text=True)
    assert MONTO in texto
    assert "pending" in texto


def test_req_28_rf5_historial_con_uuid_invalido_o_inexistente_responde_una_pagina_clara(
    cliente,
):
    """REQ-28 (RF-5): un identificador inválido o inexistente responde 404.

    La página de error es la respuesta, nunca el error del motor en pantalla, y el
    texto va en español también cuando la ruta no existe.
    """
    invalido = cliente.get("/historial/no-es-un-uuid")
    inexistente = cliente.get(f"/historial/{uuid4()}")
    ruta_que_no_existe = cliente.get("/no-existe")

    assert invalido.status_code == 404
    assert inexistente.status_code == 404
    assert ruta_que_no_existe.status_code == 404
    assert "El identificador no es un UUID válido." in invalido.get_data(as_text=True)
    assert "No hay ninguna wallet registrada" in inexistente.get_data(as_text=True)
    # Werkzeug describe el 404 en inglés; la página no puede mostrarlo así.
    assert "The requested URL was not found" not in ruta_que_no_existe.get_data(as_text=True)
    assert "No se encontró lo que buscaba" in ruta_que_no_existe.get_data(as_text=True)


def test_req_29_la_interfaz_no_explica_el_proyecto(cliente):
    """REQ-29: la interfaz no explica el proyecto. Sin «CU-0X» ni prosa sobre el eje."""
    for ruta in ("/", "/wallets", "/transacciones", "/bloques", "/verificar"):
        cuerpo = cliente.get(ruta).get_data(as_text=True)
        assert "CU-0" not in cuerpo


def test_req_29_el_panel_lateral_aparece_en_todas_las_paginas(cliente, wallet_de_prueba):
    """REQ-29: el panel lateral lista las wallets en todas las páginas."""
    for ruta in ("/", "/transacciones", "/verificar", f"/historial/{wallet_de_prueba.id}"):
        cuerpo = cliente.get(ruta).get_data(as_text=True)
        assert f"/historial/{wallet_de_prueba.id}" in cuerpo
        assert wallet_de_prueba.public_key in cuerpo          # el valor completo sigue disponible
        assert wallet_de_prueba.public_key[:8] in cuerpo      # y la forma corta es la que se ve


def test_req_29_los_datos_numericos_van_en_monoespaciada(cliente, wallet_de_prueba):
    """REQ-29: los identificadores y los montos van en monoespaciada."""
    cuerpo = cliente.get(f"/historial/{wallet_de_prueba.id}").get_data(as_text=True)
    assert 'class="mono"' in cuerpo
