"""REQ-12: confirmar las transacciones de un bloque sin romper la coherencia.

Ninguna escritura deja una confirmada sin bloque ni una pendiente con bloque: el
CHECK del esquema lo impide y los dos caminos de escritura de la agrupación
—insertar el bloque y confirmar— lo respetan.
"""
from decimal import Decimal

from src.domain.transaction import TransactionStatus


def test_req_12_agrupar_deja_estado_y_bloque_coherentes(ledger, pendientes, emisora, receptora):
    """Ninguna fila queda con el estado y el bloque desacompasados."""
    pendientes(2)
    # Una rechazada por saldo en medio del escenario: tampoco puede traer bloque.
    ledger.create_transaction(
        sender_id=emisora.id,
        receiver_id=receptora.id,
        amount=Decimal("1.00000000"),
    )

    bloque = ledger.group_pending()

    filas = ledger.transactions.list()
    assert filas, "el escenario tiene que dejar filas que revisar"
    assert all(
        (fila.status is TransactionStatus.CONFIRMED) == (fila.block_id is not None)
        for fila in filas
    )
    assert all(
        fila.block_id == bloque.id
        for fila in filas
        if fila.status is TransactionStatus.CONFIRMED
    )
    rechazadas = [fila for fila in filas if fila.status is TransactionStatus.REJECTED]
    assert rechazadas, "el escenario tiene que incluir la rechazada"
    assert all(fila.block_id is None for fila in rechazadas)


def test_req_12_la_pendiente_que_crea_el_ledger_no_trae_bloque(ledger, emisora, receptora):
    """Una transacción rechazada por el ledger se guarda sin bloque (REQ-11, REQ-12)."""
    resultado = ledger.create_transaction(
        sender_id=emisora.id,
        receiver_id=receptora.id,
        amount=Decimal("1.00000000"),
    )

    assert resultado.stored is not None
    assert resultado.stored.status is TransactionStatus.REJECTED
    assert resultado.stored.block_id is None
