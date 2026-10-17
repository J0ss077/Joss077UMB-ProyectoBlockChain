"""REQ-31: la cola de pendientes del administrador.

El administrador ve cada cuenta pendiente con su usuario y la fecha de registro, y
desde la misma tabla la aprueba o la rechaza. Aprobar delega en `Cuentas.aprobar`,
que crea la wallet y acredita el saldo de bienvenida en una sola transacción
(REQ-33), y saca al usuario de la lista; rechazar exige un motivo no vacío y lo
guarda. Las dos acciones vuelven a la cola con el resultado, también cuando la
fila ya no estaba pendiente: la pantalla pudo quedar vieja y eso se informa sin
romper la petición.

La puerta de la cola es la de REQ-38: las tres rutas exigen administrador y el
usuario común recibe 403 sin ver ni ejecutar nada.
"""
from uuid import uuid4

from src.accounts.model import APROBADO, PENDIENTE, RECHAZADO
from src.accounts.service import Cuentas
from src.bootstrap import FONDO, USERNAME_DEL_ADMINISTRADOR
from src.domain.blockchain import Blockchain
from src.emision import SALDO_DE_BIENVENIDA
from src.persistence.factory import admin_password
from src.web.admin import MENSAJE_SIN_MOTIVO
from tests.integration.conftest import CONTRASENA_DE_PRUEBA, ingresar_como

RUTA_DE_LA_COLA = "/admin/pendientes"


def _registrar(cuentas: Cuentas, nombre: str):
    """Una cuenta pendiente real, por el mismo camino que usa el registro."""
    return cuentas.registrar(nombre, CONTRASENA_DE_PRUEBA)


def test_req_31_la_cola_muestra_el_panel_con_saldos(
    base_vacia_ejecutando_bootstrap, cliente
):
    """La cola pinta el mismo panel de wallets con saldos que las otras páginas.

    La lista sale de la fuente compartida y no de una consulta propia de la cola:
    se exige una línea de saldo por wallet sembrada y el saldo conocido del fondo
    (300), además de su clave pública completa en el marcado.
    """
    chain = base_vacia_ejecutando_bootstrap
    ingresar_como(cliente, USERNAME_DEL_ADMINISTRADOR, admin_password())

    respuesta = cliente.get(RUTA_DE_LA_COLA)

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "Wallets" in cuerpo
    assert cuerpo.count("Saldo:") == chain.ledger_state()["wallets"]
    assert FONDO in cuerpo
    assert "300.00000000" in cuerpo


def test_req_31_el_administrador_ve_los_pendientes(cliente_admin, cuentas):
    """Criterio: la cola lista cada pendiente con su usuario y su fecha, y sus dos acciones."""
    ana = _registrar(cuentas, "ana")
    beto = _registrar(cuentas, "beto")
    aprobada = _registrar(cuentas, "carla")
    cuentas.aprobar(aprobada.id)

    respuesta = cliente_admin.get(RUTA_DE_LA_COLA)

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert ana.username in cuerpo
    assert beto.username in cuerpo
    assert aprobada.username not in cuerpo
    assert ana.creado_en.strftime("%d/%m/%Y") in cuerpo
    assert beto.creado_en.strftime("%d/%m/%Y") in cuerpo
    # Cada fila trae sus dos acciones y el campo de motivo del rechazo.
    assert f"/admin/pendientes/{ana.id}/aprobar" in cuerpo
    assert f"/admin/pendientes/{ana.id}/rechazar" in cuerpo
    assert f"/admin/pendientes/{beto.id}/aprobar" in cuerpo
    assert f"/admin/pendientes/{beto.id}/rechazar" in cuerpo
    assert cuerpo.count('name="motivo"') == 2
    assert "Aprobar" in cuerpo
    assert "Rechazar" in cuerpo


def test_req_31_aprobar_desde_la_cola_crea_la_wallet_y_saca_al_usuario_de_la_lista(
    cliente_admin, cuentas, ledger: Blockchain
):
    """Criterio: aprobar deja el estado `aprobado`, la wallet con 1000 y la cola sin el usuario."""
    ana = _registrar(cuentas, "ana")
    antes = ledger.ledger_state()

    respuesta = cliente_admin.post(f"/admin/pendientes/{ana.id}/aprobar")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == RUTA_DE_LA_COLA
    aprobada = cuentas.por_id(ana.id)
    assert aprobada is not None
    assert aprobada.estado == APROBADO
    assert aprobada.wallet_id is not None
    assert ledger.available_balance(aprobada.wallet_id) == SALDO_DE_BIENVENIDA
    assert ledger.ledger_state() == {
        "wallets": antes["wallets"] + 1,
        "blocks": antes["blocks"] + 1,
        "transactions": antes["transactions"] + 1,
    }

    cola = cliente_admin.get(RUTA_DE_LA_COLA).get_data(as_text=True)
    assert f"/admin/pendientes/{ana.id}/aprobar" not in cola
    assert "No hay cuentas pendientes" in cola


def test_req_31_aprobar_dos_veces_no_crea_dos_wallets(cliente_admin, cuentas, ledger: Blockchain):
    """Criterio: la segunda aprobación desde la cola informa y no escribe otra wallet."""
    ana = _registrar(cuentas, "ana")
    cliente_admin.post(f"/admin/pendientes/{ana.id}/aprobar")
    aprobada = cuentas.por_id(ana.id)
    antes = ledger.ledger_state()

    respuesta = cliente_admin.post(
        f"/admin/pendientes/{ana.id}/aprobar", follow_redirects=True
    )

    assert respuesta.status_code == 200
    assert "ya no está pendiente" in respuesta.get_data(as_text=True)
    assert cuentas.por_id(ana.id) == aprobada
    assert ledger.ledger_state() == antes


def test_req_31_rechazar_sin_motivo_no_escribe_nada_y_avisa(cliente_admin, cuentas, ledger):
    """Criterio: un motivo en blanco no rechaza la cuenta; la cola avisa y nada cambia."""
    ana = _registrar(cuentas, "ana")
    antes = ledger.ledger_state()

    respuesta = cliente_admin.post(
        f"/admin/pendientes/{ana.id}/rechazar",
        data={"motivo": "   "},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert MENSAJE_SIN_MOTIVO in cuerpo
    assert f"/admin/pendientes/{ana.id}/rechazar" in cuerpo
    fila = cuentas.por_id(ana.id)
    assert fila is not None
    assert fila.estado == PENDIENTE
    assert fila.motivo_rechazo is None
    assert ledger.ledger_state() == antes


def test_req_31_rechazar_desde_la_cola_pide_motivo_y_lo_guarda(cliente_admin, cuentas):
    """Criterio: con motivo, la cuenta queda `rechazado` con ese texto y sale de la cola."""
    ana = _registrar(cuentas, "ana")

    respuesta = cliente_admin.post(
        f"/admin/pendientes/{ana.id}/rechazar",
        data={"motivo": "  El documento no coincide.  "},
    )

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == RUTA_DE_LA_COLA
    fila = cuentas.por_id(ana.id)
    assert fila is not None
    assert fila.estado == RECHAZADO
    assert fila.motivo_rechazo == "El documento no coincide."
    assert fila.wallet_id is None

    cola = cliente_admin.get(RUTA_DE_LA_COLA).get_data(as_text=True)
    assert f"/admin/pendientes/{ana.id}/rechazar" not in cola
    assert "rechazada" in cola


def test_req_31_rechazar_dos_veces_informa_y_no_cambia_el_motivo(cliente_admin, cuentas):
    """Criterio: rechazar una fila que ya no está pendiente informa sin reescribir el motivo."""
    ana = _registrar(cuentas, "ana")
    rechazada = cuentas.rechazar(ana.id, "El documento no coincide.")

    respuesta = cliente_admin.post(
        f"/admin/pendientes/{ana.id}/rechazar",
        data={"motivo": "otro motivo"},
        follow_redirects=True,
    )

    assert respuesta.status_code == 200
    assert "ya no está pendiente" in respuesta.get_data(as_text=True)
    assert cuentas.por_id(ana.id) == rechazada


def test_req_38_el_usuario_comun_no_entra_a_la_cola(cliente_comun):
    """Criterio: el usuario común recibe 403 en la cola y en sus dos acciones."""
    pendiente = uuid4()
    peticiones = (
        ("GET", RUTA_DE_LA_COLA, None),
        ("POST", f"/admin/pendientes/{pendiente}/aprobar", None),
        ("POST", f"/admin/pendientes/{pendiente}/rechazar", {"motivo": "no"}),
    )
    for metodo, ruta, datos in peticiones:
        respuesta = cliente_comun.open(ruta, method=metodo, data=datos)
        assert respuesta.status_code == 403, (metodo, ruta)
        assert "Pendientes de aprobación" not in respuesta.get_data(as_text=True), (
            metodo,
            ruta,
        )


def test_req_37_la_cola_sin_sesion_manda_al_ingreso(cliente):
    """Criterio: sin sesión, la cola y sus dos acciones redirigen al ingreso."""
    pendiente = uuid4()
    peticiones = (
        ("GET", RUTA_DE_LA_COLA, None),
        ("POST", f"/admin/pendientes/{pendiente}/aprobar", None),
        ("POST", f"/admin/pendientes/{pendiente}/rechazar", {"motivo": "no"}),
    )
    for metodo, ruta, datos in peticiones:
        respuesta = cliente.open(ruta, method=metodo, data=datos)
        assert respuesta.status_code == 302, (metodo, ruta)
        assert respuesta.headers["Location"].endswith("/ingresar"), (metodo, ruta)
        assert "Pendientes de aprobación" not in respuesta.get_data(as_text=True), (
            metodo,
            ruta,
        )
