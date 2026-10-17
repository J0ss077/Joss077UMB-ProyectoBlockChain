"""REQ-34: el envío del usuario común sale de su sesión y no del formulario.

El emisor lo decide la sesión: `g.user.wallet_id` es la única wallet desde la que
se puede proponer un envío desde el tablero. El formulario no tiene campo de
emisor y, si alguien inyecta uno, la ruta lo ignora. El destinatario se resuelve
primero por nombre de usuario y, si no existe, por el identificador de la wallet
(decisión 4 del diseño), y los rechazos del dominio se muestran con su motivo.

El cliente pide la aplicación real contra la base real, igual que el resto de las
pruebas de rutas: lo que se mide es el recorrido completo y no la fachada.
"""
from decimal import Decimal

import pytest

from src.domain.transaction import RejectionReason
from src.web.user import MENSAJE_DESTINATARIO_INEXISTENTE
from tests.integration.conftest import CONTRASENA_DE_PRUEBA


@pytest.fixture
def otra_persona(cuentas):
    """Un segundo usuario común aprobado, con su wallet y su saldo (REQ-33).

    Se aprueba por el servicio para que sea una cuenta real de la base: el envío
    resuelve el destinatario por nombre de usuario contra esa misma fila.
    """
    creado = cuentas.registrar("bruno", CONTRASENA_DE_PRUEBA)
    return cuentas.aprobar(creado.id)


def _envios_desde(conexion, wallet_id) -> list[tuple]:
    """Las filas de transacción en las que esa wallet es la emisora."""
    return conexion.execute(
        "SELECT receiver_id, amount, status FROM transactions "
        "WHERE sender_id = %s ORDER BY created_at, id",
        (wallet_id,),
    ).fetchall()


def test_req_34_el_emisor_sale_de_la_sesion_y_no_del_formulario(
    cliente_comun, usuario_comun, otra_persona, conexion
):
    """Criterio: un envío con un emisor ajeno en el formulario se registra con la
    wallet de la sesión, o se rechaza; nunca con la ajena."""
    respuesta = cliente_comun.post(
        "/mi-envio",
        data={
            "destinatario": "bruno",
            "amount": "10.00000000",
            # El formulario del tablero no tiene emisor: se inyecta para medir que
            # la ruta no confía en lo que llega.
            "sender_id": str(otra_persona.wallet_id),
        },
    )

    assert respuesta.status_code == 200
    enviadas = _envios_desde(conexion, usuario_comun.wallet_id)
    assert enviadas == [
        (otra_persona.wallet_id, Decimal("10.00000000"), "pending")
    ]
    # La wallet que llegó en el formulario no ganó ninguna fila como emisora: lo
    # único que tiene es el crédito de bienvenida, donde es la receptora.
    assert _envios_desde(conexion, otra_persona.wallet_id) == []


def test_req_34_el_destinatario_puede_ser_usuario_o_identificador_de_wallet(
    cliente_comun, usuario_comun, otra_persona, receptora, conexion
):
    """Criterio: el destinatario se resuelve por nombre de usuario y, si no existe,
    por el identificador de la wallet."""
    # El nombre va con mayúsculas a propósito: el repositorio normaliza, y el
    # tablero tiene que resolver «Bruno» como el usuario `bruno` que ya existe.
    por_nombre = cliente_comun.post(
        "/mi-envio", data={"destinatario": "Bruno", "amount": "10.00000000"}
    )
    por_wallet = cliente_comun.post(
        "/mi-envio", data={"destinatario": str(receptora.id), "amount": "5.00000000"}
    )

    assert por_nombre.status_code == 200
    assert por_wallet.status_code == 200
    destinos = _envios_desde(conexion, usuario_comun.wallet_id)
    assert (otra_persona.wallet_id, Decimal("10.00000000"), "pending") in destinos
    assert (receptora.id, Decimal("5.00000000"), "pending") in destinos


def test_req_34_el_destinatario_inexistente_se_rechaza_con_motivo(
    cliente_comun, usuario_comun, conexion
):
    """Criterio: un destinatario que no es ni cuenta ni wallet se informa y no escribe."""
    respuesta = cliente_comun.post(
        "/mi-envio", data={"destinatario": "nadie", "amount": "10.00000000"}
    )

    assert respuesta.status_code == 200
    assert MENSAJE_DESTINATARIO_INEXISTENTE in respuesta.get_data(as_text=True)
    assert _envios_desde(conexion, usuario_comun.wallet_id) == []


def test_req_34_un_envio_sin_saldo_se_rechaza_con_el_motivo_del_dominio(
    cliente_comun, usuario_comun, otra_persona, conexion
):
    """Criterio: los rechazos del dominio se muestran con su motivo.

    El monto supera el saldo de bienvenida, así que la transacción queda
    `rejected` con el motivo que decide el dominio, y el tablero lo muestra.
    """
    respuesta = cliente_comun.post(
        "/mi-envio", data={"destinatario": "bruno", "amount": "999999.00000000"}
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "no entró al pool" in cuerpo
    assert RejectionReason.INSUFFICIENT_FUNDS.value in cuerpo
    filas = conexion.execute(
        "SELECT status, amount FROM transactions WHERE sender_id = %s",
        (usuario_comun.wallet_id,),
    ).fetchall()
    assert filas == [("rejected", Decimal("999999.00000000"))]


def test_req_34_el_tablero_muestra_su_nombre_su_wallet_y_su_saldo(
    cliente_comun, usuario_comun
):
    """Criterio: el tablero es la pantalla del usuario común con sus propios datos."""
    respuesta = cliente_comun.get("/mi-tablero")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert usuario_comun.username in cuerpo
    # El identificador completo viaja en `data-copiar`, y la forma corta es la que
    # se ve: el botón de copiar ya existe en `_macros.html`.
    assert str(usuario_comun.wallet_id) in cuerpo
    assert str(usuario_comun.wallet_id)[:8] in cuerpo
    assert "1000.00000000" in cuerpo
    # Las transacciones propias se listan con su estado; el crédito de bienvenida
    # de la aprobación es la confirmada que toda cuenta tiene (REQ-33).
    assert "confirmed" in cuerpo


def test_req_34_el_formulario_del_tablero_no_tiene_emisor(cliente_comun):
    """Criterio: el emisor no aparece en el formulario; lo pone la sesión."""
    cuerpo = cliente_comun.get("/mi-tablero").get_data(as_text=True)
    # El formulario y no la página: la tabla sí tiene una columna «Emisor», que es
    # otra cosa. Lo que se mide es que el envío no ofrezca elegir el emisor.
    formulario = cuerpo.split('action="/mi-envio"', 1)[1].split("</form>", 1)[0]

    assert "sender_id" not in formulario
    assert "Emisor" not in formulario


def test_req_34_el_tablero_muestra_el_saldo_disponible_real(
    cliente_comun, otra_persona
):
    """Criterio: el saldo que se muestra es el disponible, no el confirmado.

    Un envío pendiente ya compromete su monto, así que el tablero tiene que
    descontarlo como lo hace la regla de saldo del dominio (REQ-05).
    """
    antes = cliente_comun.get("/mi-tablero").get_data(as_text=True)
    assert "1000.00000000" in antes

    cliente_comun.post(
        "/mi-envio", data={"destinatario": "bruno", "amount": "10.00000000"}
    )

    despues = cliente_comun.get("/mi-tablero").get_data(as_text=True)
    assert "990.00000000" in despues
