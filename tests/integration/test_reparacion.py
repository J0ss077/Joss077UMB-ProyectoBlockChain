"""Reparaciones de la fachada sobre PostgreSQL: reparar, reencadenar y no escribir de más.

Cada prueba arma la cadena por el camino real, la rompe con SQL directo —lo que
puede pasar por fuera de la aplicación— y repara por la fachada, como lo hará la ruta
de la pantalla. Se exige que `verify_chain().valid` vuelva a ser cierto, que el estado
quede escrito en la base y que una segunda pasada no escriba nada. Las pruebas usan la
base de `TEST_DATABASE_URL`, nunca la de la aplicación.
"""
from src.domain.blockchain import GENESIS_PREVIOUS_HASH
from src.domain.transaction import TransactionStatus


def _tablas(conexion) -> dict[str, list[tuple]]:
    """Contenido de las tres tablas con orden fijo, para compararlo tal cual."""
    return {
        "wallets": conexion.execute("SELECT * FROM wallets ORDER BY id").fetchall(),
        "blocks": conexion.execute("SELECT * FROM blocks ORDER BY block_index").fetchall(),
        "transactions": conexion.execute("SELECT * FROM transactions ORDER BY id").fetchall(),
    }


def _bloque(conexion, block_index: int) -> tuple:
    """Fila del bloque: identificador, índice, marca de tiempo y los dos hashes."""
    return conexion.execute(
        "SELECT id, block_index, timestamp, previous_hash, hash "
        "FROM blocks WHERE block_index = %s",
        (block_index,),
    ).fetchone()


def _estado(conexion, transaction_id) -> tuple:
    """Estado y bloque de una transacción, tal como quedaron en la base."""
    return conexion.execute(
        "SELECT status, block_id FROM transactions WHERE id = %s", (transaction_id,)
    ).fetchone()


def test_reencadenar_restaura_la_cadena_despues_de_un_update_de_monto(
    ledger, conexion, transaccion
):
    """Un monto alterado por SQL rompe el hash; reencadenar lo corrige sin tocar el resto."""
    fila = ledger.transactions.add(transaccion())
    bloque = ledger.group_pending()
    conexion.execute(
        "UPDATE transactions SET amount = amount + 1 WHERE id = %s", (fila.id,)
    )
    assert ledger.verify_chain().valid is False
    antes = _bloque(conexion, bloque.block_index)

    reparacion = ledger.repair_chain()

    assert reparacion.accion == "encadenar"
    assert reparacion.aplicada is True
    assert reparacion.cambios == 1
    assert ledger.verify_chain().valid is True
    despues = _bloque(conexion, bloque.block_index)
    # Solo cambian los hashes: el índice y la marca de tiempo siguen igual.
    assert (despues[1], despues[2]) == (antes[1], antes[2])
    assert (despues[3], despues[4]) != (antes[3], antes[4])


def test_aislar_una_confirmada_con_firma_inventada_la_rechaza_y_reencadena(
    ledger, conexion, transaccion
):
    """La confirmada con firma inventada queda rechazada y sin bloque; el bloque se recalcula."""
    fila = ledger.transactions.add(transaccion())
    bloque = ledger.group_pending()
    conexion.execute(
        "UPDATE transactions SET signature = %s WHERE id = %s", ("ab" * 64, fila.id)
    )
    antes = _bloque(conexion, bloque.block_index)
    assert ledger.audit_chain().resumen.valida is False

    reparacion = ledger.isolate_invalid_transactions()

    assert reparacion.accion == "aislar"
    assert reparacion.aplicada is True
    assert reparacion.cambios == 2
    assert _estado(conexion, fila.id) == ("rejected", None)
    assert ledger.verify_chain().valid is True
    auditoria = ledger.audit_chain()
    assert auditoria.resumen.valida is True
    assert auditoria.resumen.confirmadas == 0
    revision = next(r for r in auditoria.bloques if r.indice == bloque.block_index)
    assert revision.transacciones == 0
    despues = _bloque(conexion, bloque.block_index)
    assert (despues[1], despues[2]) == (antes[1], antes[2])


def test_aislar_un_monto_nan_insertado_por_sql_no_tumba_la_reparacion(
    ledger, conexion, transaccion
):
    """Un monto `NaN` que el CHECK del esquema admite se aísla como cualquier inválido."""
    fila = ledger.transactions.add(transaccion())
    ledger.group_pending()
    conexion.execute("UPDATE transactions SET amount = 'NaN' WHERE id = %s", (fila.id,))

    reparacion = ledger.isolate_invalid_transactions()

    assert reparacion.aplicada is True
    assert _estado(conexion, fila.id) == ("rejected", None)
    assert ledger.verify_chain().valid is True


def test_rechazar_pendientes_invalidas_no_toca_las_validas(ledger, conexion, transaccion):
    """La pendiente con firma inválida se rechaza; la válida sigue en el pool."""
    invalida = transaccion()
    invalida.signature = "ab" * 64
    invalida = ledger.transactions.add(invalida)
    valida = ledger.transactions.add(transaccion())

    reparacion = ledger.reject_invalid_pending()

    assert reparacion.accion == "rechazar-pendientes"
    assert reparacion.aplicada is True
    assert reparacion.cambios == 1
    assert _estado(conexion, invalida.id) == ("rejected", None)
    assert _estado(conexion, valida.id) == ("pending", None)


def test_reparar_todo_es_idempotente(ledger, conexion, transaccion):
    """La primera pasada repara todo; la segunda no encuentra nada y no escribe filas."""
    confirmada = ledger.transactions.add(transaccion())
    ledger.group_pending()
    conexion.execute(
        "UPDATE transactions SET signature = %s WHERE id = %s",
        ("cd" * 64, confirmada.id),
    )
    invalida_del_pool = transaccion()
    invalida_del_pool.signature = "ab" * 64
    ledger.transactions.add(invalida_del_pool)

    primera = ledger.repair_all()

    assert tuple(r.accion for r in primera) == (
        "rechazar-pendientes",
        "aislar",
        "encadenar",
    )
    assert ledger.verify_chain().valid is True
    antes = _tablas(conexion)

    segunda = ledger.repair_all()

    assert tuple(r.aplicada for r in segunda) == (False, False, False)
    assert tuple(r.cambios for r in segunda) == (0, 0, 0)
    assert _tablas(conexion) == antes


def test_aislar_sin_confirmadas_invalidas_no_escribe_nada(ledger, conexion, transaccion):
    """Una cadena sana no se toca: la reparación no aplica y las tablas quedan iguales."""
    ledger.transactions.add(transaccion())
    ledger.group_pending()
    antes = _tablas(conexion)

    reparacion = ledger.isolate_invalid_transactions()

    assert reparacion.aplicada is False
    assert reparacion.cambios == 0
    assert _tablas(conexion) == antes


def test_aislar_sin_genesis_no_fabrica_el_encadenamiento(ledger, conexion, transaccion):
    """Sin el bloque 0 se rechaza la inválida, pero el encadenamiento no se reescribe.

    Reencadenar sin génesis pondría el `previous_hash` del primer bloque en 64 ceros y
    borraría el rastro de la cabeza eliminada; aislar solo debe rechazar.
    """
    fila = ledger.transactions.add(transaccion())
    ledger.group_pending()
    conexion.execute("DELETE FROM blocks WHERE block_index = 0")
    conexion.execute(
        "UPDATE transactions SET signature = %s WHERE id = %s", ("ab" * 64, fila.id)
    )
    antes = _bloque(conexion, 1)

    reparacion = ledger.isolate_invalid_transactions()

    assert reparacion.aplicada is True
    assert reparacion.cambios == 1
    assert _estado(conexion, fila.id) == ("rejected", None)
    despues = _bloque(conexion, 1)
    assert despues[3] == antes[3]
    assert despues[3] != GENESIS_PREVIOUS_HASH
    assert despues[4] == antes[4]
    assert "no se aplicó" in reparacion.detalle
    assert any(h.codigo == "cabeza" for h in ledger.audit_chain().hallazgos)


def test_reparar_todo_sin_genesis_conserva_el_encadenamiento(ledger, conexion, transaccion):
    """«Reparar todo» sin génesis no inventa el encadenamiento ni renumera."""
    fila = ledger.transactions.add(transaccion())
    ledger.group_pending()
    conexion.execute("DELETE FROM blocks WHERE block_index = 0")
    conexion.execute(
        "UPDATE transactions SET signature = %s WHERE id = %s", ("ab" * 64, fila.id)
    )
    antes = _bloque(conexion, 1)

    reparaciones = ledger.repair_all()

    assert tuple(r.accion for r in reparaciones) == (
        "rechazar-pendientes",
        "aislar",
        "encadenar",
    )
    assert reparaciones[2].aplicada is False
    assert _estado(conexion, fila.id) == ("rejected", None)
    despues = _bloque(conexion, 1)
    assert despues[3] == antes[3]
    assert despues[3] != GENESIS_PREVIOUS_HASH
    assert despues[4] == antes[4]
    assert any(h.codigo == "cabeza" for h in ledger.audit_chain().hallazgos)


def test_reparar_una_cadena_sin_bloques_crea_el_genesis(ledger, conexion):
    """Sin ningún bloque, la reparación crea el eslabón cero y la cadena vuelve a ser válida."""
    conexion.execute("DELETE FROM blocks")
    assert ledger.blocks.count() == 0

    reparacion = ledger.repair_chain()

    assert reparacion.aplicada is True
    assert reparacion.cambios == 1
    genesis = ledger.blocks.get_by_index(0)
    assert genesis is not None
    assert genesis.previous_hash == GENESIS_PREVIOUS_HASH
    assert ledger.verify_chain().valid is True


def test_un_hueco_de_indices_se_declara_y_no_se_renumera(ledger, conexion, bloque):
    """Una cadena 0, 2 no se renumera: se declara el hueco y los índices quedan como están."""
    genesis = ledger.blocks.get_by_index(0)
    bloque(2, genesis.hash)

    reparacion = ledger.repair_chain()

    assert reparacion.aplicada is False
    assert reparacion.cambios == 0
    assert "índices" in reparacion.detalle
    indices = [
        fila[0]
        for fila in conexion.execute(
            "SELECT block_index FROM blocks ORDER BY block_index"
        ).fetchall()
    ]
    assert indices == [0, 2]


def test_si_falta_el_genesis_no_se_renumera(ledger, conexion, transaccion):
    """Una cadena que empieza en el índice 1 no se toca: renumerar reescribiría la historia."""
    ledger.transactions.add(transaccion())
    ledger.group_pending()
    conexion.execute("DELETE FROM blocks WHERE block_index = 0")

    reparacion = ledger.repair_chain()

    assert reparacion.aplicada is False
    assert reparacion.cambios == 0
    assert "no se renumera" in reparacion.detalle
    indices = [
        fila[0]
        for fila in conexion.execute(
            "SELECT block_index FROM blocks ORDER BY block_index"
        ).fetchall()
    ]
    assert indices == [1]
    # La confirmada del bloque 1 sigue donde estaba: no se reasignó a otro bloque.
    fila = conexion.execute("SELECT status, block_id FROM transactions").fetchone()
    assert fila[0] == TransactionStatus.CONFIRMED.value
    assert fila[1] is not None
