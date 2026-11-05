"""La pestaña de estadísticas: el común ve las suyas y el administrador elige de quién.

El alcance es el de REQ-35: la página del común arma sus gráficas sólo con la
wallet de la sesión, y la del administrador sólo muestra a un usuario común que
él elija. Los filtros y las gráficas corren en el navegador; acá se revisa lo que
el servidor deja en la página: el JSON de movimientos y el resumen.
"""
import json
import re
from decimal import Decimal

from src.domain.transaction import TransactionStatus
from src.web.estadisticas import (
    NOMBRE_DE_LA_BIENVENIDA,
    movimientos_para_graficas,
    resumen_de_estadisticas,
)


def _movimientos_de_la_pagina(cuerpo: str) -> list[dict]:
    hallado = re.search(
        r'<script type="application/json" id="datos-estadisticas">(.*?)</script>', cuerpo, re.S
    )
    assert hallado, "la página no trae los movimientos"
    return json.loads(hallado.group(1))


def test_el_comun_ve_sus_estadisticas_y_no_las_de_otros(
    cliente_comun, usuario_comun, ledger, emisora, receptora, transaccion
):
    propia = ledger.transactions.add(
        transaccion(
            sender=ledger.wallets.get(usuario_comun.wallet_id),
            receiver=receptora,
            amount=Decimal("3.00000000"),
        )
    )
    ledger.transactions.add(
        transaccion(sender=emisora, receiver=receptora, amount=Decimal("77.00000000"))
    )

    respuesta = cliente_comun.get("/mis-estadisticas")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    movimientos = _movimientos_de_la_pagina(cuerpo)
    montos = {m["monto"] for m in movimientos}
    assert "3.00000000" in montos
    assert "77.00000000" not in montos
    # Ni identificadores de transacción ni de wallets ajenas: sólo nombres.
    assert str(propia.id) not in cuerpo
    assert str(receptora.id) not in cuerpo
    assert {m["persona"] for m in movimientos} <= {NOMBRE_DE_LA_BIENVENIDA, "otra cuenta"}


def test_el_administrador_no_entra_a_las_estadisticas_del_comun(cliente_admin):
    respuesta = cliente_admin.get("/mis-estadisticas")

    # El administrador no tiene wallet propia: la puerta lo devuelve a su tablero
    # en vez de mostrarle estadísticas de una cuenta que no es la suya.
    assert respuesta.status_code in (302, 403)
    if respuesta.status_code == 302:
        destino = respuesta.headers["Location"]
        assert "/mis-estadisticas" not in destino, destino
        assert "/admin" in destino or destino.endswith("/"), destino
    else:
        assert "No tienes permiso para esta operación" in respuesta.get_data(as_text=True)


def test_el_comun_no_entra_a_las_del_administrador(cliente_comun):
    respuesta = cliente_comun.get("/admin/estadisticas?usuario=ana")

    assert respuesta.status_code == 403, "una redirección al ingreso también pasaría"
    assert "No tienes permiso para esta operación" in respuesta.get_data(as_text=True)


def test_el_administrador_elige_a_un_usuario_comun(cliente_admin, usuario_comun):
    sin_elegir = cliente_admin.get("/admin/estadisticas").get_data(as_text=True)
    assert '<option value="ana"' in sin_elegir
    assert '<option value="adminprueba"' not in sin_elegir
    assert "datos-estadisticas" not in sin_elegir

    elegido = cliente_admin.get("/admin/estadisticas?usuario=ana")

    assert elegido.status_code == 200
    movimientos = _movimientos_de_la_pagina(elegido.get_data(as_text=True))
    # El saldo de bienvenida de la aprobación es su primer movimiento.
    assert movimientos[0]["tipo"] == "entra"
    assert movimientos[0]["persona"] == NOMBRE_DE_LA_BIENVENIDA


def test_el_administrador_no_ve_a_otro_administrador_ni_a_un_desconocido(
    cliente_admin, administrador
):
    assert cliente_admin.get("/admin/estadisticas?usuario=adminprueba").status_code == 404
    assert cliente_admin.get("/admin/estadisticas?usuario=nadie").status_code == 404


def test_el_resumen_suma_solo_lo_completado(usuario_comun, ledger):
    historial = ledger.wallet_history(usuario_comun.wallet_id)
    completado = sum(
        (t.amount for t in historial if t.status is TransactionStatus.CONFIRMED), Decimal(0)
    )

    resumen = resumen_de_estadisticas(historial, usuario_comun.wallet_id)
    movimientos = movimientos_para_graficas(historial, usuario_comun.wallet_id, {})

    assert resumen.recibido == completado
    assert resumen.enviado == Decimal(0)
    assert resumen.movimientos == len(historial) == len(movimientos)
