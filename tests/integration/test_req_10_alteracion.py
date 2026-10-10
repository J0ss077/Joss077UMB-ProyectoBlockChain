"""REQ-10 contra PostgreSQL: la demostración central del proyecto.

La cadena se arma con la aplicación y después se altera a mano una transacción
confirmada con un `UPDATE` directo: la verificación tiene que señalar el bloque
donde empieza la alteración, que es lo que el eje promete demostrar. También se
borra el eslabón cero para comprobar que la cabeza de la cadena se revisa.
"""
from src.domain.blockchain import VerificationReport


def test_req_10_la_cadena_recien_armada_es_valida(ledger, pendientes):
    """Una cadena de tres bloques armada con la aplicación verifica como válida."""
    pendientes(2)
    ledger.group_pending()
    pendientes(1)
    ledger.group_pending()

    assert ledger.verify_chain() == VerificationReport(valid=True, altered_block_index=None)
    assert ledger.blocks.count() == 3


def test_req_10_alterar_una_confirmada_con_update_directo_señala_su_bloque(
    ledger, conexion, pendientes
):
    """Alterar el monto de una confirmada con `UPDATE` directo localiza el bloque."""
    pendientes(2)
    bloque = ledger.group_pending()
    objetivo = conexion.execute(
        "SELECT id FROM transactions WHERE block_id = %s ORDER BY id LIMIT 1",
        (bloque.id,),
    ).fetchone()[0]

    conexion.execute("UPDATE transactions SET amount = amount + 1 WHERE id = %s", (objetivo,))

    informe = ledger.verify_chain()

    assert informe.valid is False
    assert informe.altered_block_index == bloque.block_index


def test_req_10_borrar_el_genesis_con_delete_directo_señala_la_cabeza(
    ledger, conexion, pendientes
):
    """Borrar el eslabón cero deja los hashes de 1..n intactos: la cabeza se señala."""
    pendientes(2)
    bloque = ledger.group_pending()

    conexion.execute("DELETE FROM blocks WHERE block_index = 0")

    informe = ledger.verify_chain()

    assert informe.valid is False
    assert informe.altered_block_index == bloque.block_index
