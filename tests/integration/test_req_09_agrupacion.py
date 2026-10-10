"""REQ-09: agrupar las transacciones pendientes en un bloque nuevo.

Después de agrupar, las del pool quedan confirmadas y ligadas al bloque; con el
pool vacío no se crea ningún bloque (flujo alterno del CU-03).
"""
from src.domain.transaction import TransactionStatus


def test_req_09_agrupar_confirma_las_pendientes_y_las_liga_al_bloque(ledger, pendientes):
    """Tras agrupar, las del pool quedan confirmadas y ligadas al bloque."""
    del_pool = pendientes(3)

    bloque = ledger.group_pending()

    assert bloque is not None
    assert ledger.transactions.pending() == []
    agrupadas = ledger.transactions.of_block(bloque.id)
    assert {fila.id for fila in agrupadas} == {fila.id for fila in del_pool}
    assert all(fila.status is TransactionStatus.CONFIRMED for fila in agrupadas)
    assert all(fila.block_id == bloque.id for fila in agrupadas)
    # El génesis y el bloque nuevo: la agrupación suma un eslabón, no reemplaza.
    assert ledger.blocks.count() == 2


def test_req_09_con_el_pool_vacio_no_se_crea_bloque(ledger):
    """Flujo alterno del CU-03: sin pendientes no hay bloque que agrupar."""
    assert ledger.group_pending() is None
    assert ledger.blocks.count() == 1
    assert ledger.transactions.pending() == []
