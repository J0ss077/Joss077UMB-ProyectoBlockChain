"""Persistencia de reparación contra PostgreSQL: leer todo, rechazar y reescribir hashes.

Fija los tres métodos nuevos que la auditoría y las reparaciones necesitan: leer
todas las transacciones de una sola vez, pasar filas a `rejected` sin bloque y
reescribir los dos hashes de un bloque por su identificador. Las pruebas de
integración usan la base de `TEST_DATABASE_URL`, nunca la de la aplicación.
"""
import dataclasses
from datetime import timedelta
from uuid import uuid4

from src.domain.transaction import TransactionStatus
from tests.integration.conftest import CREATED_AT


def test_all_devuelve_las_filas_de_los_tres_estados(ledger, transaccion):
    """`all` no filtra por estado: devuelve confirmadas, del pool y rechazadas."""
    confirmada = ledger.transactions.add(transaccion())
    ledger.group_pending()
    rechazada = ledger.transactions.add(transaccion(status=TransactionStatus.REJECTED))
    pendiente = ledger.transactions.add(transaccion())

    filas = list(ledger.transactions.all())

    assert {fila.id for fila in filas} == {confirmada.id, rechazada.id, pendiente.id}
    estados = [fila.status for fila in filas]
    assert estados.count(TransactionStatus.CONFIRMED) == 1
    assert estados.count(TransactionStatus.REJECTED) == 1
    assert estados.count(TransactionStatus.PENDING) == 1


def test_all_ordena_por_creacion_e_identificador(ledger, transaccion):
    """El orden es el de la consulta real: la más antigua primero y el id desempata."""
    temprana = ledger.transactions.add(
        transaccion(created_at=CREATED_AT - timedelta(minutes=1))
    )
    tardia = ledger.transactions.add(transaccion())

    filas = list(ledger.transactions.all())

    assert [fila.id for fila in filas] == [temprana.id, tardia.id]


def test_reject_deja_la_fila_rechazada_y_sin_bloque(ledger, conexion, transaccion):
    """`reject` escribe `rejected` y `block_id` nulo, y devuelve cuántas filas tocó."""
    transaccion_confirmada = ledger.transactions.add(transaccion())
    ledger.group_pending()

    assert ledger.transactions.reject([transaccion_confirmada.id]) == 1

    fila = conexion.execute(
        "SELECT status, block_id FROM transactions WHERE id = %s",
        (transaccion_confirmada.id,),
    ).fetchone()
    assert fila == ("rejected", None)
    assert ledger.transactions.get(transaccion_confirmada.id).block_id is None


def test_reject_cuenta_solo_las_filas_que_existen(ledger, transaccion):
    """El valor devuelto es el número de filas tocadas, no el largo de la lista."""
    transaccion_confirmada = ledger.transactions.add(transaccion())
    ledger.group_pending()

    assert ledger.transactions.reject([transaccion_confirmada.id, uuid4()]) == 1


def test_reject_sin_identificadores_devuelve_cero_y_no_cambia_nada(ledger, conexion, transaccion):
    """Una lista vacía no ejecuta ningún cambio."""
    pendiente = ledger.transactions.add(transaccion())

    assert ledger.transactions.reject([]) == 0

    fila = conexion.execute(
        "SELECT status FROM transactions WHERE id = %s", (pendiente.id,)
    ).fetchone()
    assert fila == ("pending",)


def test_set_hashes_escribe_los_dos_hashes_y_devuelve_la_fila(ledger, conexion, transaccion):
    """`set_hashes` actualiza `previous_hash` y `hash` por id y devuelve la fila escrita."""
    ledger.transactions.add(transaccion())
    bloque = ledger.group_pending()
    nuevo = dataclasses.replace(bloque, previous_hash="f" * 64, hash="e" * 64)

    escrito = ledger.blocks.set_hashes(nuevo)

    assert escrito.id == bloque.id
    assert escrito.block_index == bloque.block_index
    assert escrito.timestamp == bloque.timestamp
    assert escrito.previous_hash == "f" * 64
    assert escrito.hash == "e" * 64
    fila = conexion.execute(
        "SELECT previous_hash, hash FROM blocks WHERE id = %s", (bloque.id,)
    ).fetchone()
    assert fila == ("f" * 64, "e" * 64)
