"""REQ-22: la verificación de la cadena solo lee.

El contenido de las tres tablas se guarda antes y después de verificar y tiene
que ser el mismo: la verificación recalcula hashes y compara, no escribe.
"""


def _tablas(conexion) -> dict[str, list[tuple]]:
    """Contenido de las tres tablas con orden fijo, para poder compararlo tal cual."""
    return {
        "wallets": conexion.execute("SELECT * FROM wallets ORDER BY id").fetchall(),
        "blocks": conexion.execute("SELECT * FROM blocks ORDER BY block_index").fetchall(),
        "transactions": conexion.execute("SELECT * FROM transactions ORDER BY id").fetchall(),
    }


def test_req_22_verificar_no_modifica_ninguna_fila(ledger, conexion, pendientes):
    """La verificación no modifica ninguna fila."""
    pendientes(2)
    ledger.group_pending()
    antes = _tablas(conexion)

    informe = ledger.verify_chain()

    assert informe.valid is True
    assert _tablas(conexion) == antes
