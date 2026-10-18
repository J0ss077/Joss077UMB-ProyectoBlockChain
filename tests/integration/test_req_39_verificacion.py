"""REQ-39: la verificación del historial propio.

La página unificada del usuario común (`/mi-historial`) corre la verificación de la
cadena y muestra su dictamen junto con todas las transacciones de **su** wallet.
Con la cadena válida dice que su historial está respaldado; con la cadena alterada
dice que no puede verificar su historial. En los dos casos lista sólo lo propio: ni
los identificadores ni las claves públicas de otras wallets.

La unificación trae una adaptación declarada: la página ya no filtra las
confirmadas, porque muestra todas las transacciones con su estado. La pendiente
propia, que antes no aparecía, ahora tiene que aparecer con su estado `pending`;
la aserción de alcance —lo ajeno no se lista— no cambia. `/mi-verificacion` sigue
existiendo como redirección para que un enlace guardado no se rompa.

La alteración se hace con un `UPDATE` directo sobre el génesis, que es el mismo
camino que usa REQ-10: la cadena se cambia por fuera de la aplicación y la
verificación tiene que notarlo.
"""
import re
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


def _indice_del_bloque(ledger, transaction) -> int:
    """El índice del bloque que confirma la transacción, buscado por su identificador."""
    return next(
        block.block_index for block in ledger.blocks.list() if block.id == transaction.block_id
    )


def test_req_39_mi_historial_lista_solo_sus_transacciones(
    cliente_comun, usuario_comun, ledger, emisora, receptora, transaccion
):
    """Criterio: con la cadena válida, la página dice que su historial está
    respaldado y lista sólo sus transacciones, con el estado y el índice del bloque."""
    ajena = _confirmar_ajena(ledger, emisora, receptora, transaccion)
    wallet_propia = ledger.wallets.get(usuario_comun.wallet_id)
    # Una pendiente propia: la página unificada la muestra con su estado, pero no
    # como una transacción respaldada por un bloque.
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
    indice = _indice_del_bloque(ledger, confirmadas[0])

    respuesta = cliente_comun.get("/mi-historial")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "respaldado" in cuerpo
    assert str(confirmadas[0].id) in cuerpo
    # La confirmada va con el índice del bloque que la agrupa, no con un UUID.
    # La plantilla puede partir la celda en varias líneas, así que se tolera el
    # espacio en blanco alrededor del valor y no se exige una cadena literal.
    assert re.search(rf"<td>\s*<code>{indice}</code>\s*</td>", cuerpo)
    # La pendiente propia se lista con su estado: es la adaptación declarada.
    assert str(pendiente.id) in cuerpo
    assert "<td><code>pending</code></td>" in cuerpo
    assert "4.00000000" in cuerpo
    # El alcance no cambia: lo de otra wallet no aparece, ni su monto ni su clave.
    assert str(ajena.id) not in cuerpo
    assert "77.00000000" not in cuerpo
    assert emisora.public_key not in cuerpo
    assert receptora.public_key not in cuerpo


def test_req_39_con_la_cadena_alterada_mi_historial_dice_que_no_puede_verificar(
    cliente_comun, usuario_comun, ledger, conexion, emisora, receptora, transaccion
):
    """Criterio: con la cadena alterada, su página dice que no puede verificar."""
    ajena = _confirmar_ajena(ledger, emisora, receptora, transaccion)
    conexion.execute(
        "UPDATE blocks SET timestamp = timestamp + interval '1 hour' WHERE block_index = 0"
    )

    respuesta = cliente_comun.get("/mi-historial")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "No se puede verificar tu historial" in cuerpo
    assert "La cadena es válida" not in cuerpo
    assert str(ajena.id) not in cuerpo
    assert "77.00000000" not in cuerpo


def test_req_39_mi_verificacion_redirige_a_mi_historial(cliente_comun):
    """Un enlace guardado a la página vieja llega a la unificada, con 302."""
    respuesta = cliente_comun.get("/mi-verificacion")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/mi-historial"

    # Siguiendo la redirección se ve la página unificada, no un alias vacío.
    pagina = cliente_comun.get("/mi-verificacion", follow_redirects=True)
    assert pagina.status_code == 200
    assert "respaldado" in pagina.get_data(as_text=True)


def test_req_39_la_navegacion_del_comun_tiene_una_sola_entrada(cliente_comun):
    """La navegación del usuario común deja una sola entrada a la página unificada."""
    cuerpo = cliente_comun.get("/mi-tablero").get_data(as_text=True)

    assert cuerpo.count('href="/mi-historial"') == 1
    assert 'href="/mi-verificacion"' not in cuerpo
