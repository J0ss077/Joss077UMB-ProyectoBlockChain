"""REQ-11: rechazar una transacción inválida dejándola en `rejected`, sin bloque.

La fila rechazada se guarda con `block_id` nulo y nunca entra a un bloque; el
esquema es el que impide lo contrario con su CHECK de coherencia entre estado y
bloque (REQ-12), cuyos dos lados se provocan aquí.
"""
import psycopg
import pytest

from src.domain.transaction import TransactionStatus
from src.persistence.postgres import PostgresTransactionRepository


@pytest.fixture
def transacciones(conexion):
    """El repositorio de transacciones contra la conexión de la sesión."""
    return PostgresTransactionRepository(conexion)


def test_req_11_una_rechazada_se_guarda_con_block_id_nulo(transacciones, base_limpia, transaccion):
    """La transacción inválida queda en `rejected`, sin bloque, y no entra al pool."""
    firmada = transaccion(status=TransactionStatus.REJECTED, block_id=None)

    guardada = transacciones.add(firmada)

    assert guardada.status is TransactionStatus.REJECTED
    assert guardada.block_id is None
    assert transacciones.pending() == []
    assert transacciones.count() == 1


def test_req_11_una_confirmada_sin_bloque_levanta_check_violation(
    transacciones, base_limpia, transaccion
):
    """El esquema no admite una confirmada sin bloque: el estado y el bloque van juntos."""
    sin_bloque = transaccion(status=TransactionStatus.CONFIRMED, block_id=None)

    with pytest.raises(psycopg.errors.CheckViolation):
        transacciones.add(sin_bloque)

    assert transacciones.count() == 0


def test_req_11_una_pendiente_con_bloque_levanta_check_violation(
    transacciones, base_limpia, transaccion, bloque
):
    """El otro lado de la coherencia: una pendiente tampoco puede traer bloque."""
    pendiente_con_bloque = transaccion(block_id=bloque().id)

    with pytest.raises(psycopg.errors.CheckViolation):
        transacciones.add(pendiente_con_bloque)

    assert transacciones.count() == 0
