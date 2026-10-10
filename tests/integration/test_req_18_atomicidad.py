"""REQ-18: la agrupación es atómica.

Las dos escrituras de la agrupación —insertar el bloque y confirmar sus
transacciones— ocurren en una sola transacción de base de datos: si falla la
segunda, la primera no queda aplicada. El fallo se inyecta en lugar de esperarlo:
un fallo real de PostgreSQL en ese punto exigiría una condición de carrera o un
dato inválido, y el esquema ya impide los datos inválidos.
"""
import pytest

from src.domain.transaction import TransactionStatus
from src.persistence.ports import TransactionRepository


class FalloForzado(Exception):
    """Fallo inyectado en la confirmación para probar el ROLLBACK (REQ-18)."""


class FailingTransactionRepository:
    """Envuelve el repositorio real y levanta `FalloForzado` al confirmar.

    Es la forma de provocar el fallo de la segunda escritura sin depender de la
    suerte: la primera escritura —el bloque— ya ocurrió cuando esta levanta, así
    que lo único que puede salvarla es el ROLLBACK de la unidad de trabajo.
    """

    def __init__(self, real: TransactionRepository) -> None:
        self._real = real

    def __getattr__(self, name: str):
        return getattr(self._real, name)

    def confirm(self, transaction_ids, block_id):
        raise FalloForzado("la confirmación falla a propósito")


@pytest.fixture
def repositorio_que_falla(ledger, monkeypatch):
    """Deja la unidad de trabajo del ledger con el repositorio de transacciones que falla.

    Se reemplaza la fábrica de la unidad de trabajo y no `ledger.transactions`
    porque la agrupación escribe a través de ella (REQ-18): así las aserciones de
    la prueba siguen leyendo por el repositorio real. La fábrica original se
    captura antes de reemplazarla para no llamarse a sí misma.
    """
    original = ledger._unit_of_work

    def unit_of_work():
        work = original()
        work.transactions = FailingTransactionRepository(work.transactions)
        return work

    monkeypatch.setattr(ledger, "_unit_of_work", unit_of_work)
    return unit_of_work


def test_req_18_si_falla_la_confirmacion_no_queda_el_bloque(
    ledger, pendientes, repositorio_que_falla
):
    """REQ-18: si falla una de las dos escrituras, ninguna queda aplicada."""
    pendientes(2)

    with pytest.raises(FalloForzado):
        ledger.group_pending()

    assert ledger.blocks.count() == 1          # solo el génesis
    assert all(t.status is not TransactionStatus.CONFIRMED for t in ledger.transactions.list())
    # El flujo alterno del CU-03 lo dice: las transacciones siguen en pending.
    assert {t.status for t in ledger.transactions.list()} == {TransactionStatus.PENDING}
