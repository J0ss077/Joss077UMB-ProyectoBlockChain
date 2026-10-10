"""REQ-08: encadenar cada bloque con el hash del anterior.

El hash previo del bloque que se agrupa es el hash del último bloque de la
cadena, así que la cadena no se puede reordenar ni insertar un eslabón sin que el
siguiente deje de verificar (CU-03).
"""
from src.domain.block import Block


def test_req_08_el_hash_previo_del_bloque_nuevo_es_el_del_ultimo(ledger, pendientes):
    """El hash previo del bloque nuevo es el del último bloque."""
    genesis = ledger.blocks.last()
    pendientes(2)

    nuevo = ledger.group_pending()

    assert isinstance(nuevo, Block)
    assert nuevo.block_index == genesis.block_index + 1
    assert nuevo.previous_hash == genesis.hash
    assert ledger.blocks.last().id == nuevo.id
    # El hash propio cubre lo que quedó agrupado: se recalcula con las
    # transacciones ya ligadas al bloque y tiene que dar el guardado (REQ-07).
    assert nuevo.hash == nuevo.calculate_hash(ledger.transactions.of_block(nuevo.id))


def test_req_08_la_segunda_agrupacion_se_encadena_con_la_primera(ledger, pendientes):
    """Cada bloque nuevo se encadena con el último que haya, no siempre con el génesis."""
    pendientes(1)
    primero = ledger.group_pending()
    pendientes(1)

    segundo = ledger.group_pending()

    assert segundo.previous_hash == primero.hash
    assert segundo.block_index == primero.block_index + 1
