"""REQ-38: la autorización por rol de las rutas de trabajo.

Cada ruta declara el rol que exige y el usuario común no puede reemplazar al
administrador. Las rutas del eje (`/wallets`, `/transacciones`, `/bloques`,
`/verificar` y `/historial/<wallet>`) quedan del lado del administrador; el común
recibe 403 y la vista no se ejecuta. La portada no es una ruta de trabajo: sin
sesión manda al ingreso y al común a su tablero.

La aprobación de usuarios todavía no tiene ruta propia en esta entrega; se mide
la puerta sobre el endpoint angosto de la cola que monta la Task 8, con la misma
vista inalcanzable para el común y alcanzable para el administrador.
"""
from uuid import uuid4

from src.web.auth import requiere_administrador
from tests.integration.conftest import (
    CONTRASENA_DE_PRUEBA,
    CONTRASENA_DEL_ADMINISTRADOR,
    ingresar_como,
)

RUTAS_DEL_ADMINISTRADOR = ("/wallets", "/transacciones", "/bloques", "/verificar")


def test_req_38_el_usuario_comun_no_puede_agrupar_un_bloque(cliente_comun, conexion):
    """Criterio: el usuario común que intenta agrupar un bloque recibe 403."""
    antes = conexion.execute("SELECT count(*) FROM blocks").fetchone()[0]

    respuesta = cliente_comun.post("/bloques")

    assert respuesta.status_code == 403
    assert "permiso" in respuesta.get_data(as_text=True)
    assert conexion.execute("SELECT count(*) FROM blocks").fetchone()[0] == antes


def test_req_38_el_usuario_comun_no_puede_aprobar_usuarios(aplicacion, usuario_comun):
    """Criterio: el usuario común que intenta aprobar a otro usuario recibe 403."""

    @aplicacion.post("/admin/pendientes/<identificador>/aprobar")
    @requiere_administrador
    def aprobar(identificador: str):
        raise AssertionError("la vista de aprobación no debería ejecutarse")

    cliente = aplicacion.test_client()
    ingresar_como(cliente, usuario_comun.username, CONTRASENA_DE_PRUEBA)

    respuesta = cliente.post(f"/admin/pendientes/{uuid4()}/aprobar")

    assert respuesta.status_code == 403


def test_req_38_el_administrador_si_puede_aprobar_usuarios(aplicacion, administrador):
    """Criterio: la misma puerta deja pasar al administrador; no es un 403 general."""

    @aplicacion.post("/admin/pendientes/<identificador>/aprobar")
    @requiere_administrador
    def aprobar(identificador: str):
        return f"aprobado {identificador}"

    cliente = aplicacion.test_client()
    ingresar_como(cliente, administrador.username, CONTRASENA_DEL_ADMINISTRADOR)

    respuesta = cliente.post(f"/admin/pendientes/{uuid4()}/aprobar")

    assert respuesta.status_code == 200
    assert respuesta.get_data(as_text=True).startswith("aprobado ")


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
