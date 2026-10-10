"""REQ-24 a REQ-28: la presentación hace los casos de uso del eje.

Cada ruta toma su formulario, llama a la fachada del ledger y devuelve una página
con el resultado. Las pruebas piden el cliente contra la base de verdad y con la
fachada real, porque lo que miden es el recorrido de la ruta y no la fachada.

El escenario es el de la demostración del arranque: el fondo y los asociados ya
tienen saldo confirmado, así que las transacciones que proponen las pruebas se
aceptan por las reglas reales (REQ-05) y no por un atajo.
"""
from contextlib import contextmanager
from decimal import Decimal
from uuid import uuid4

import pytest

from src.bootstrap import FONDO
from src.domain.blockchain import ensure_genesis
from src.persistence.factory import master_key, open_ledger
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
    """El fondo y un asociado con saldo, que son los actores del caso del eje."""
    fondo = cadena.wallets.get_by_public_key(FONDO)
    asociados = [w for w in cadena.wallets.list() if w.id != fondo.id]
    asociado = next(w for w in asociados if cadena.available_balance(w.id) > 0)
    return {"fondo": fondo, "asociado": asociado, "tercero": asociados[-1]}


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


def test_req_24_post_wallets_devuelve_200_con_la_publica(cliente):
    """REQ-24: la ruta registra la wallet y la página muestra su clave pública."""
    respuesta = cliente.post("/wallets")

    assert respuesta.status_code == 200
    assert "public_key" in respuesta.get_data(as_text=True)


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


def test_req_28_rf5_historial_con_uuid_invalido_o_inexistente_responde_una_pagina_clara(cliente):
    """REQ-28 (RF-5): un identificador inválido o inexistente responde 404 y no un error del motor."""
    assert cliente.get("/historial/no-es-un-uuid").status_code == 404
    assert cliente.get(f"/historial/{uuid4()}").status_code == 404
