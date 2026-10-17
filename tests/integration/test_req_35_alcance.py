"""REQ-35: el alcance de la vista del usuario común.

El usuario común ve su saldo, su historial y la verificación de su historial; el
administrador ve todo. El criterio se mide por los dos lados: el común recibe 403
(o 404) cuando pide el historial de otra wallet y nunca su contenido, y el
administrador sí lo recibe. Las pantallas del común tampoco listan las wallets de
otros, que es lo que el panel lateral del administrador sí hace.

Las rutas del tablero exigen sesión (REQ-37) y al administrador lo devuelven a su
portada: entrar a ellas no es un error, pero tampoco es su pantalla.
"""
from decimal import Decimal

RUTAS_DEL_TABLERO = ("/mi-tablero", "/mi-historial", "/mi-verificacion")


def test_req_35_el_usuario_comun_no_ve_el_historial_de_otro(
    cliente_comun, ledger, emisora, receptora, transaccion
):
    """Criterio: el usuario común que pide el historial de otra wallet recibe 403
    o 404, nunca el contenido."""
    ajena = ledger.transactions.add(
        transaccion(sender=emisora, receiver=receptora, amount=Decimal("77.00000000"))
    )

    respuesta = cliente_comun.get(f"/historial/{receptora.id}")

    assert respuesta.status_code == 403
    cuerpo = respuesta.get_data(as_text=True)
    assert str(ajena.id) not in cuerpo
    assert "77.00000000" not in cuerpo
    assert receptora.public_key not in cuerpo


def test_req_35_mi_historial_solo_lista_sus_transacciones(
    cliente_comun, usuario_comun, ledger, receptora, emisora, transaccion
):
    """Criterio: el historial propio son sólo las transacciones de la wallet de la
    sesión, y la pantalla no lista las wallets de otros."""
    propia = ledger.transactions.add(
        transaccion(
            sender=ledger.wallets.get(usuario_comun.wallet_id),
            receiver=receptora,
            amount=Decimal("3.00000000"),
        )
    )
    ajena = ledger.transactions.add(
        transaccion(sender=emisora, receiver=receptora, amount=Decimal("77.00000000"))
    )

    respuesta = cliente_comun.get("/mi-historial")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert str(propia.id) in cuerpo
    assert str(ajena.id) not in cuerpo
    assert "77.00000000" not in cuerpo
    # Sin panel lateral: las claves públicas de otras wallets no aparecen.
    assert emisora.public_key not in cuerpo
    assert receptora.public_key not in cuerpo


def test_req_35_el_administrador_si_ve_el_historial_de_otro(
    cliente_admin, ledger, emisora, receptora, transaccion
):
    """Criterio: el administrador sí recibe el historial de cualquier wallet."""
    ajena = ledger.transactions.add(
        transaccion(sender=emisora, receiver=receptora, amount=Decimal("77.00000000"))
    )

    respuesta = cliente_admin.get(f"/historial/{receptora.id}")

    assert respuesta.status_code == 200
    assert str(ajena.id) in respuesta.get_data(as_text=True)


def test_req_35_el_administrador_en_las_rutas_del_comun_va_a_su_portada(
    cliente_admin,
):
    """Criterio: el administrador conserva su portada; entrar al tablero no es un error."""
    for ruta in RUTAS_DEL_TABLERO:
        respuesta = cliente_admin.get(ruta)
        assert respuesta.status_code == 302, ruta
        assert respuesta.headers["Location"] == "/", ruta

    respuesta = cliente_admin.post(
        "/mi-envio", data={"destinatario": "ana", "amount": "10.00000000"}
    )
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/"


def test_req_35_las_rutas_del_tablero_exigen_sesion(cliente):
    """Criterio: sin sesión, las rutas del tablero mandan al ingreso y no dan datos."""
    peticiones = tuple(("GET", ruta) for ruta in RUTAS_DEL_TABLERO) + (
        ("POST", "/mi-envio"),
    )
    for metodo, ruta in peticiones:
        respuesta = cliente.open(ruta, method=metodo)
        assert respuesta.status_code == 302, (metodo, ruta)
        assert respuesta.headers["Location"].endswith("/ingresar"), (metodo, ruta)


def test_req_35_el_tablero_no_lista_las_wallets_de_otros(
    cliente_comun, usuario_comun, receptora
):
    """Criterio: el tablero muestra la wallet de la sesión y ninguna otra."""
    cuerpo = cliente_comun.get("/mi-tablero").get_data(as_text=True)

    assert str(usuario_comun.wallet_id) in cuerpo
    assert receptora.public_key not in cuerpo
    assert str(receptora.id) not in cuerpo
    assert "/historial/" not in cuerpo
