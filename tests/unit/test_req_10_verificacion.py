"""REQ-10: verificar la integridad de la cadena y localizar la alteración.

Cada prueba altera una cosa distinta —un monto confirmado, un hueco en los
índices, un `previous_hash` que no corresponde o la marca de tiempo del génesis—
y exige que el dictamen señale el bloque donde empieza la alteración. Corre sin
base de datos (REQ-17), sobre los dobles de `tests/dobles.py`.
"""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from src.domain.transaction import Transaction, TransactionStatus
from tests.dobles import BLOCK_AT, build_block, build_chain


def _confirmed(index: int) -> Transaction:
    """Transacción confirmada de monto reconocible, para ligarla a un bloque."""
    return Transaction(
        id=uuid4(),
        sender_id=uuid4(),
        receiver_id=uuid4(),
        amount=Decimal(f"{index + 1}.00000000"),
        status=TransactionStatus.CONFIRMED,
        signature=f"firma-{index}",
        block_id=None,
        created_at=BLOCK_AT,
    )


@pytest.fixture
def bloque():
    """Fábrica de bloques encadenados por el hash del anterior."""
    return build_block


@pytest.fixture
def cadena_de_tres_bloques():
    """Tres bloques bien encadenados, cada uno con una transacción confirmada.

    Tres y no dos: alterar el del medio deja predecesor y sucesor, que es donde se
    nota si la verificación se detiene en el primer bloque que falla.
    """
    transacciones = [_confirmed(index) for index in range(3)]
    genesis = build_block(0, transactions=[transacciones[0]])
    segundo = build_block(1, genesis, transactions=[transacciones[1]])
    tercero = build_block(2, segundo, transactions=[transacciones[2]])
    for block, transaction in zip((genesis, segundo, tercero), transacciones):
        transaction.block_id = block.id
    chain = build_chain(blocks=[genesis, segundo, tercero], transactions=transacciones)
    return {
        "chain": chain,
        "bloques": [genesis, segundo, tercero],
        "transacciones": transacciones,
    }


def test_req_10_cadena_intacta_es_valida(cadena_de_tres_bloques):
    """Una cadena sin alteraciones se informa como válida y sin bloque señalado."""
    informe = cadena_de_tres_bloques["chain"].verify_chain()

    assert informe.valid is True
    assert informe.altered_block_index is None


def test_req_10_monto_alterado_señala_ese_bloque(cadena_de_tres_bloques):
    """Alterar el monto de una transacción confirmada señala el bloque que la agrupa."""
    alterada = cadena_de_tres_bloques["transacciones"][1]
    alterada.amount = alterada.amount + Decimal("1.00000000")

    informe = cadena_de_tres_bloques["chain"].verify_chain()

    assert informe.valid is False
    assert informe.altered_block_index == 1


def test_req_10_rf3_hueco_en_los_indices_señala_donde_deja_de_encadenar(bloque):
    """Un hueco en los índices señala el bloque donde la cadena deja de encadenar."""
    genesis = bloque(0)
    segundo = bloque(1, genesis)
    # El eslabón 2 no existe: el 3 sigue apuntando al hash del 1, así que sus
    # hashes están bien y lo único que delata el hueco es el índice que falta.
    salteado = bloque(3, segundo)
    chain = build_chain(blocks=[genesis, segundo, salteado])

    assert chain.verify_chain().altered_block_index == 3


def test_req_10_rf3_previous_hash_huerfano_señala_ese_bloque(bloque):
    """Un `previous_hash` que no es el del bloque anterior señala ese bloque."""
    genesis = bloque(0)
    huerfano = bloque(1, previous_hash="a" * 64)
    chain = build_chain(blocks=[genesis, huerfano])

    assert chain.verify_chain().altered_block_index == 1


def test_req_10_rf4_marca_de_tiempo_del_genesis_alterada_se_detecta(cadena_de_tres_bloques):
    """Alterar la marca de tiempo del génesis con su hash intacto se detecta en el índice cero."""
    genesis = cadena_de_tres_bloques["bloques"][0]
    genesis.timestamp = genesis.timestamp + timedelta(hours=1)

    informe = cadena_de_tres_bloques["chain"].verify_chain()

    assert informe.valid is False
    assert informe.altered_block_index == 0


def test_req_10_borrar_el_genesis_señala_la_cabeza(bloque):
    """Borrar el génesis deja los hashes de 1..n intactos, así que hay que señalar la cabeza."""
    genesis = bloque(0)
    segundo = bloque(1, genesis)
    chain = build_chain(blocks=[segundo])

    informe = chain.verify_chain()

    assert informe.valid is False
    assert informe.altered_block_index == 1


def test_req_10_una_cadena_sin_bloques_no_es_valida():
    """Sin ningún bloque falta el génesis, así que la cadena no puede darse por válida."""
    informe = build_chain().verify_chain()

    assert informe.valid is False
    assert informe.altered_block_index == 0


def test_req_10_la_cabeza_declara_el_hash_previo_del_genesis(bloque):
    """Un eslabón cero con un hash previo distinto de los sesenta y cuatro ceros se señala."""
    ajeno = bloque(0, previous_hash="b" * 64)
    chain = build_chain(blocks=[ajeno])

    informe = chain.verify_chain()

    assert informe.valid is False
    assert informe.altered_block_index == 0
