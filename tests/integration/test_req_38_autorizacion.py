"""REQ-38: la autorización por rol de las rutas de trabajo.

Cada ruta declara el rol que exige y el usuario común no puede reemplazar al
administrador. Las rutas del eje (`/wallets`, `/transacciones`, `/bloques`,
`/verificar` y `/historial/<wallet>`) quedan del lado del administrador; el común
recibe 403 y la vista no se ejecuta. La portada no es una ruta de trabajo: sin
sesión manda al ingreso y al común a su tablero.

La cola de pendientes es la ruta real de la aprobación (Task 8): se mide la
puerta sobre `/admin/pendientes/<id>/aprobar`, con la vista inalcanzable para el
común y la aprobación efectiva para el administrador.
"""
from uuid import uuid4

from src.accounts.model import APROBADO
from tests.integration.conftest import CONTRASENA_DE_PRUEBA

RUTAS_DEL_ADMINISTRADOR = ("/wallets", "/transacciones", "/bloques", "/verificar")


def test_req_38_el_usuario_comun_no_puede_agrupar_un_bloque(cliente_comun, conexion):
    """Criterio: el usuario común que intenta agrupar un bloque recibe 403."""
    antes = conexion.execute("SELECT count(*) FROM blocks").fetchone()[0]

    respuesta = cliente_comun.post("/bloques")

    assert respuesta.status_code == 403
    assert "permiso" in respuesta.get_data(as_text=True)
    assert conexion.execute("SELECT count(*) FROM blocks").fetchone()[0] == antes


def test_req_38_el_usuario_comun_no_puede_aprobar_usuarios(cliente_comun):
    """Criterio: el usuario común que intenta aprobar a otro usuario recibe 403."""
    respuesta = cliente_comun.post(f"/admin/pendientes/{uuid4()}/aprobar")

    assert respuesta.status_code == 403


def test_req_38_el_administrador_si_puede_aprobar_usuarios(cliente_admin, cuentas):
    """Criterio: la misma puerta deja pasar al administrador; no es un 403 general."""
    pendiente = cuentas.registrar("nuevo", CONTRASENA_DE_PRUEBA)

    respuesta = cliente_admin.post(f"/admin/pendientes/{pendiente.id}/aprobar")

    assert respuesta.status_code == 302
    aprobado = cuentas.por_id(pendiente.id)
    assert aprobado is not None
    assert aprobado.estado == APROBADO


def test_req_38_el_usuario_comun_no_puede_registrar_wallets(cliente_comun, conexion):
    """Criterio: el usuario común no puede registrar wallets (matriz de permisos)."""
    antes = conexion.execute("SELECT count(*) FROM wallets").fetchone()[0]

    respuesta = cliente_comun.post("/wallets")

    assert respuesta.status_code == 403
    assert conexion.execute("SELECT count(*) FROM wallets").fetchone()[0] == antes


def test_req_38_el_usuario_comun_no_puede_verificar_la_cadena(cliente_comun):
    """Criterio: verificar la cadena completa es del administrador."""
    assert cliente_comun.get("/verificar").status_code == 403


def test_req_38_el_usuario_comun_no_puede_ver_el_historial_de_otro(cliente_comun):
    """Criterio: el usuario común no ve el historial de otra wallet; nunca el contenido."""
    respuesta = cliente_comun.get(f"/historial/{uuid4()}")

    assert respuesta.status_code == 403
    assert "Historial" not in respuesta.get_data(as_text=True)


def test_req_38_el_usuario_comun_no_entra_a_ninguna_ruta_de_trabajo(cliente_comun):
    """Criterio: la matriz se cumple ruta por ruta para el usuario común."""
    peticiones = tuple(
        ("GET", ruta) for ruta in RUTAS_DEL_ADMINISTRADOR
    ) + (
        ("POST", "/wallets"),
        ("POST", "/transacciones"),
        ("POST", "/bloques"),
        ("GET", f"/historial/{uuid4()}"),
    )
    for metodo, ruta in peticiones:
        respuesta = cliente_comun.open(ruta, method=metodo)
        assert respuesta.status_code == 403, (metodo, ruta)
        assert "Estado del ledger" not in respuesta.get_data(as_text=True), (metodo, ruta)


def test_req_38_el_administrador_conserva_las_rutas_de_hoy(cliente_admin, administrador):
    """Criterio: el administrador sigue entrando a las rutas que ya existían."""
    for ruta in RUTAS_DEL_ADMINISTRADOR:
        assert cliente_admin.get(ruta).status_code == 200, ruta
    assert cliente_admin.get("/").status_code == 200
    assert administrador.wallet_id is not None
    assert cliente_admin.get(f"/historial/{administrador.wallet_id}").status_code == 200
