"""REQ-39: la verificación del historial propio.

La página del usuario común corre la verificación de la cadena y muestra su
dictamen junto con las transacciones confirmadas de **su** wallet. Con la cadena
válida dice que su historial está respaldado; con la cadena alterada dice que no
puede verificar su historial. En los dos casos lista sólo lo propio: ni los
identificadores ni las claves públicas de otras wallets.

La alteración se hace con un `UPDATE` directo sobre el génesis, que es el mismo
camino que usa REQ-10: la cadena se cambia por fuera de la aplicación y la
verificación tiene que notarlo.
"""
from decimal import Decimal

from src.domain.transaction import TransactionStatus


def _confirmar_ajena(ledger, emisora, receptora, transaccion):
    """Escribe y confirma una transacción entre wallets que no son de la sesión.

    Se agrupa con `group_pending` para que la fila quede confirmada por el camino
    real; el bloque nuevo la incluye y sólo a ella, porque el pool está vacío.
    """
    ajena = ledger.transactions.add(
        transaccion(sender=emisora, receiver=receptora, amount=Decimal("77.00000000"))
    )
    ledger.group_pending()
    return ajena


def test_req_39_mi_verificacion_lista_solo_sus_transacciones(
    cliente_comun, usuario_comun, ledger, emisora, receptora, transaccion
):
    """Criterio: con la cadena válida, la página dice que su historial está
    respaldado y lista sólo sus transacciones confirmadas."""
    ajena = _confirmar_ajena(ledger, emisora, receptora, transaccion)
    wallet_propia = ledger.wallets.get(usuario_comun.wallet_id)
    # Una pendiente propia: todavía no está confirmada, así que la verificación no
    # tiene que listarla como respaldada.
    pendiente = ledger.transactions.add(
        transaccion(sender=wallet_propia, receiver=receptora, amount=Decimal("4.00000000"))
    )
    confirmadas = [
        fila
        for fila in ledger.wallet_history(usuario_comun.wallet_id)
        if fila.status is TransactionStatus.CONFIRMED
    ]
    # El crédito de bienvenida de la aprobación es la confirmada de la cuenta
    # (REQ-33), y es la única.
    assert len(confirmadas) == 1

    respuesta = cliente_comun.get("/mi-verificacion")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "respaldado" in cuerpo
    assert str(confirmadas[0].id) in cuerpo
    assert str(pendiente.id) not in cuerpo
    assert str(ajena.id) not in cuerpo
    assert "77.00000000" not in cuerpo
    assert emisora.public_key not in cuerpo
    assert receptora.public_key not in cuerpo


def test_req_39_con_la_cadena_alterada_mi_verificacion_dice_que_no_puede_verificar(
    cliente_comun, usuario_comun, ledger, conexion, emisora, receptora, transaccion
):
    """Criterio: con la cadena alterada, su página dice que no puede verificar."""
    ajena = _confirmar_ajena(ledger, emisora, receptora, transaccion)
    conexion.execute(
        "UPDATE blocks SET timestamp = timestamp + interval '1 hour' WHERE block_index = 0"
    )

    respuesta = cliente_comun.get("/mi-verificacion")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "No se puede verificar su historial" in cuerpo
    assert "La cadena es válida" not in cuerpo
    assert str(ajena.id) not in cuerpo
    assert "77.00000000" not in cuerpo
