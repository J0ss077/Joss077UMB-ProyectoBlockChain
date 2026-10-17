"""REQ-33: el saldo de bienvenida es un bloque propio en la cadena real.

La prueba siembra con el arranque del proyecto y comprueba que acreditar mueve
los saldos disponibles, deja una sola transacción confirmada en un eslabón nuevo
y no arrastra las pendientes que la semilla ya tiene en el pool.
"""
import psycopg
import pytest

from src.domain.transaction import TransactionStatus
from src.domain.wallet import verify
from src.emision import CONSTITUYENTE_ID, SALDO_DE_BIENVENIDA

# La semilla del proyecto, como la deja `python -m src.bootstrap`: cinco wallets,
# cuatro bloques y diez transacciones. Se afirma acá para que esta prueba no pueda
# pasar sobre un arranque que cambió de forma.
SEMILLA_ESPERADA = {"wallets": 5, "blocks": 4, "transactions": 10}


def test_req_33_acreditar_sube_el_saldo_del_destino_y_baja_el_del_emisor(
    base_vacia_ejecutando_bootstrap,
):
    """Criterio: destino con 1000 disponibles, emisor 1000 más negativo y un bloque nuevo.

    El bloque del crédito tiene esa única transacción, confirmada y ligada a él, y
    la cadena sigue verificando después de la emisión.
    """
    chain = base_vacia_ejecutando_bootstrap
    assert chain.ledger_state() == SEMILLA_ESPERADA
    antes_emisor = chain.available_balance(CONSTITUYENTE_ID)
    ultimo = chain.blocks.last()
    destino = chain.register_wallet()

    bloque = chain.acreditar(
        emisor_id=CONSTITUYENTE_ID,
        destino_id=destino.id,
        monto=SALDO_DE_BIENVENIDA,
    )

    assert chain.available_balance(destino.id) == SALDO_DE_BIENVENIDA
    assert chain.available_balance(CONSTITUYENTE_ID) == antes_emisor - SALDO_DE_BIENVENIDA
    assert bloque.block_index == ultimo.block_index + 1
    assert bloque.previous_hash == ultimo.hash

    filas = chain.transactions.of_block(bloque.id)
    assert len(filas) == 1
    credito = filas[0]
    assert credito.status is TransactionStatus.CONFIRMED
    assert credito.block_id == bloque.id
    assert credito.sender_id == CONSTITUYENTE_ID
    assert credito.receiver_id == destino.id
    assert credito.amount == SALDO_DE_BIENVENIDA

    constituyente = chain.wallets.get(CONSTITUYENTE_ID)
    assert verify(
        constituyente.public_key,
        credito.signature,
        credito.signing_payload(constituyente.public_key, destino.public_key),
    )
    assert chain.verify_chain().valid is True
    assert chain.ledger_state() == {
        "wallets": SEMILLA_ESPERADA["wallets"] + 1,
        "blocks": SEMILLA_ESPERADA["blocks"] + 1,
        "transactions": SEMILLA_ESPERADA["transactions"] + 1,
    }


def test_req_33_la_emision_no_arrastra_las_pendientes(base_vacia_ejecutando_bootstrap):
    """Criterio: el bloque del crédito tiene una sola transacción aunque haya pool.

    La semilla deja retiros pendientes; acreditar no los agrupa ni los confirma, y
    la cadena sigue verificando con el eslabón nuevo.
    """
    chain = base_vacia_ejecutando_bootstrap
    pendientes_antes = chain.transactions.pending()
    assert pendientes_antes, "la semilla deja retiros en el pool"
    destino = chain.register_wallet()

    bloque = chain.acreditar(
        emisor_id=CONSTITUYENTE_ID,
        destino_id=destino.id,
        monto=SALDO_DE_BIENVENIDA,
    )

    assert len(chain.transactions.of_block(bloque.id)) == 1
    assert [t.id for t in chain.transactions.pending()] == [
        t.id for t in pendientes_antes
    ]
    assert chain.verify_chain().valid is True


def test_req_33_el_esquema_impide_acreditar_a_la_misma_wallet(
    base_vacia_ejecutando_bootstrap,
):
    """El destino no puede ser el emisor: el CHECK del esquema detiene la emisión.

    El dominio no agrega una regla que el esquema ya tiene; la violación sube cruda
    (REQ-19), y en la aprobación real la unidad de trabajo deshace el bloque a medio
    escribir (REQ-33).
    """
    with pytest.raises(psycopg.errors.CheckViolation):
        base_vacia_ejecutando_bootstrap.acreditar(
            emisor_id=CONSTITUYENTE_ID,
            destino_id=CONSTITUYENTE_ID,
            monto=SALDO_DE_BIENVENIDA,
        )
