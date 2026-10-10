"""REQ-14: registrar el bloque génesis.

Existe un bloque de índice cero cuyo hash previo son sesenta y cuatro ceros, y
`ensure_genesis` es idempotente: llamarlo de nuevo no duplica el eslabón.
"""
from src.domain.blockchain import ensure_genesis


def test_req_14_el_genesis_tiene_indice_cero_y_hash_previo_de_ceros(ledger):
    """Existe un bloque de índice cero cuyo hash previo son sesenta y cuatro ceros."""
    genesis = ledger.blocks.get_by_index(0)

    assert genesis is not None
    assert genesis.block_index == 0
    assert genesis.previous_hash == "0" * 64
    # El hash propio sale de su cabecera y de ninguna transacción: la verificación
    # de REQ-10 lo recalcula y una alteración suya tiene que notarse (decisión 13).
    assert genesis.hash == genesis.calculate_hash([])


def test_req_14_ensure_genesis_es_idempotente(ledger):
    """Volver a asegurar el génesis devuelve el mismo bloque y no escribe otro."""
    genesis = ledger.blocks.get_by_index(0)

    otra_vez = ensure_genesis(ledger)

    assert otra_vez.id == genesis.id
    assert ledger.blocks.count() == 1
