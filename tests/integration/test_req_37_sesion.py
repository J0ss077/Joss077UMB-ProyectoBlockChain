"""REQ-37, REQ-32 y REQ-30: la sesión de la web y los formularios de entrada.

El ingreso abre una sesión y la salida la cierra; sin sesión, ninguna ruta de
trabajo responde con datos. La cookie guarda sólo el identificador de la cuenta y
se recarga de la base en cada petición, así un cambio de estado o de rol se nota
sin reiniciar y una cuenta borrada descarta la sesión (diseño §9).

Las pruebas de los formularios miden lo que ve la persona: la pantalla de
pendiente del registro, el estado del pendiente y del rechazado en el ingreso, el
mensaje único de las credenciales equivocadas y el campo de usuario restringido
desde la propia interfaz. El cliente pide la aplicación real contra la base real.
"""
import re

from src.accounts.credentials import (
    AYUDA_DE_USUARIO,
    LARGO_MAXIMO_DE_USUARIO,
    PATRON_DE_USUARIO,
)
from src.accounts.model import ADMINISTRADOR
from src.accounts.service import MENSAJE_DE_CREDENCIALES_INVALIDAS
from src.persistence.factory import session_secret
from src.web.auth import CLAVE_DEL_USUARIO, requiere_sesion
from tests.integration.conftest import (
    CONTRASENA_DE_PRUEBA,
    CONTRASENA_DEL_ADMINISTRADOR,
    ingresar_como,
)

RUTAS_DE_TRABAJO = ("/wallets", "/transacciones", "/bloques", "/verificar")


def _mensaje_de_error(cuerpo: str) -> str:
    """El texto del aviso de error de los formularios de entrada."""
    encontrado = re.search(r'<div class="motivo"[^>]*>\s*<p>(.*?)</p>', cuerpo, re.S)
    assert encontrado is not None, cuerpo
    return encontrado.group(1).strip()


def test_req_37_sin_sesion_las_rutas_de_trabajo_redirigen(cliente):
    """Criterio: sin sesión, las rutas de trabajo redirigen al ingreso."""
    peticiones = (
        ("GET", "/wallets"),
        ("POST", "/wallets"),
        ("GET", "/transacciones"),
        ("POST", "/transacciones"),
        ("GET", "/bloques"),
        ("POST", "/bloques"),
        ("GET", "/verificar"),
        ("GET", "/historial/00000000-0000-0000-0000-000000000000"),
    )
    for metodo, ruta in peticiones:
        respuesta = cliente.open(ruta, method=metodo)
        assert respuesta.status_code == 302, (metodo, ruta)
        assert respuesta.headers["Location"].endswith("/ingresar"), (metodo, ruta)
        assert "Estado del ledger" not in respuesta.get_data(as_text=True)

    # La portada tampoco muestra los conteos: sin sesión manda al ingreso.
    portada = cliente.get("/")
    assert portada.status_code == 302
    assert portada.headers["Location"].endswith("/ingresar")


def test_req_37_ingresar_abre_sesion_y_salir_la_cierra(cliente, administrador):
    """Criterio: el ingreso abre la sesión y después de la salida ya no se entra."""
    respuesta = ingresar_como(
        cliente, administrador.username, CONTRASENA_DEL_ADMINISTRADOR
    )

    assert respuesta.headers["Location"] == "/"
    assert cliente.get("/").status_code == 200
    # `g.user` llega a la plantilla: la barra muestra el nombre de la sesión.
    assert administrador.username in cliente.get("/").get_data(as_text=True)

    salida = cliente.post("/salir")

    assert salida.status_code == 302
    assert salida.headers["Location"].endswith("/ingresar")
    for ruta in ("/", *RUTAS_DE_TRABAJO):
        respuesta = cliente.get(ruta)
        assert respuesta.status_code == 302, ruta
        assert respuesta.headers["Location"].endswith("/ingresar"), ruta


def test_req_37_la_cookie_es_httponly_samesite_lax_y_no_permanente(
    cliente, administrador
):
    """Criterio: la cookie es HttpOnly, SameSite=Lax y muere al cerrar el navegador."""
    respuesta = ingresar_como(
        cliente, administrador.username, CONTRASENA_DEL_ADMINISTRADOR
    )

    galleta = next(
        galleta
        for galleta in respuesta.headers.getlist("Set-Cookie")
        if "session=" in galleta
    )
    assert "HttpOnly" in galleta
    assert "SameSite=Lax" in galleta
    assert "Expires" not in galleta
    assert "Max-Age" not in galleta


def test_req_37_la_sesion_guarda_solo_el_identificador(cliente, administrador):
    """Criterio: la cookie lleva el identificador de la cuenta y nada más."""
    ingresar_como(cliente, administrador.username, CONTRASENA_DEL_ADMINISTRADOR)

    with cliente.session_transaction() as sesion:
        assert list(sesion.keys()) == [CLAVE_DEL_USUARIO]
        assert sesion[CLAVE_DEL_USUARIO] == str(administrador.id)


def test_req_37_requiere_sesion_deja_pasar_al_usuario_comun(aplicacion, usuario_comun):
    """Criterio: la puerta de sesión deja entrar a cualquier cuenta aprobada.

    Es la puerta que usan las rutas del tablero: sin sesión redirige al ingreso y
    con una sesión de usuario común deja ejecutar la vista. Se monta un endpoint
    angosto para medirla, porque las rutas del tablero llegan con su pantalla.
    """

    @aplicacion.get("/solo-con-sesion")
    @requiere_sesion
    def solo_con_sesion():
        return "con sesión"

    cliente = aplicacion.test_client()
    assert cliente.get("/solo-con-sesion").status_code == 302

    ingresar_como(cliente, usuario_comun.username, CONTRASENA_DE_PRUEBA)

    respuesta = cliente.get("/solo-con-sesion")
    assert respuesta.status_code == 200
    assert respuesta.get_data(as_text=True) == "con sesión"


def test_req_37_la_clave_de_la_cookie_es_el_secreto_del_entorno(aplicacion):
    """Criterio: la cookie se firma con el `SESSION_SECRET` de la configuración."""
    assert aplicacion.secret_key == session_secret()


def test_req_37_el_usuario_se_recarga_de_la_base_en_cada_peticion(
    cliente_comun, usuario_comun, conexion
):
    """Criterio: un cambio de rol se nota sin reiniciar la aplicación."""
    assert cliente_comun.get("/bloques").status_code == 403

    conexion.execute(
        "UPDATE users SET role = %s WHERE id = %s",
        (ADMINISTRADOR, usuario_comun.id),
    )

    assert cliente_comun.get("/bloques").status_code == 200


def test_req_37_una_cuenta_que_deja_de_estar_aprobada_pierde_la_sesion(
    cliente_comun, usuario_comun, conexion
):
    """Criterio: una cuenta que deja de estar aprobada ya no tiene sesión."""
    conexion.execute(
        """
        UPDATE users
        SET estado = 'pendiente', wallet_id = NULL, aprobado_en = NULL
        WHERE id = %s
        """,
        (usuario_comun.id,),
    )

    respuesta = cliente_comun.get("/bloques")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/ingresar")
    with cliente_comun.session_transaction() as sesion:
        assert CLAVE_DEL_USUARIO not in sesion


def test_req_37_una_cuenta_borrada_descarta_la_sesion(
    cliente_comun, usuario_comun, conexion
):
    """Criterio: si la cuenta ya no existe, la sesión se descarta."""
    conexion.execute("DELETE FROM users WHERE id = %s", (usuario_comun.id,))

    respuesta = cliente_comun.get("/bloques")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/ingresar")
    with cliente_comun.session_transaction() as sesion:
        assert CLAVE_DEL_USUARIO not in sesion


def test_req_37_el_administrador_va_a_la_portada_y_el_comun_a_su_tablero(
    aplicacion, administrador, usuario_comun
):
    """Criterio: cada rol aterriza en su pantalla y la portada respeta el rol."""
    cliente_del_administrador = aplicacion.test_client()
    respuesta = ingresar_como(
        cliente_del_administrador,
        administrador.username,
        CONTRASENA_DEL_ADMINISTRADOR,
    )
    assert respuesta.headers["Location"] == "/"
    assert cliente_del_administrador.get("/").status_code == 200

    cliente_del_comun = aplicacion.test_client()
    respuesta = ingresar_como(
        cliente_del_comun, usuario_comun.username, CONTRASENA_DE_PRUEBA
    )
    assert respuesta.headers["Location"] == "/mi-tablero"
    # La portada de trabajo es del administrador: el común vuelve a su tablero.
    assert cliente_del_comun.get("/").headers["Location"] == "/mi-tablero"
    # `g.user` está disponible en las plantillas para las páginas del común.
    cuerpo = cliente_del_comun.get("/ingresar").get_data(as_text=True)
    assert usuario_comun.username in cuerpo
    assert "Salir" in cuerpo


def test_req_32_el_pendiente_no_abre_sesion_y_ve_su_estado(cliente, cuentas):
    """Criterio: un pendiente que acierta la contraseña ve «esperando aprobación»."""
    cuentas.registrar("beto", CONTRASENA_DE_PRUEBA)

    respuesta = cliente.post(
        "/ingresar", data={"usuario": "beto", "contrasena": CONTRASENA_DE_PRUEBA}
    )

    assert respuesta.status_code == 200
    assert "esperando aprobación" in _mensaje_de_error(respuesta.get_data(as_text=True))
    assert cliente.get("/").status_code == 302


def test_req_32_el_rechazado_ve_el_motivo_y_no_entra(cliente, cuentas):
    """Criterio: un rechazado ve «rechazada» con el motivo y no abre sesión."""
    creado = cuentas.registrar("carla", CONTRASENA_DE_PRUEBA)
    cuentas.rechazar(creado.id, "documentación incompleta")

    respuesta = cliente.post(
        "/ingresar", data={"usuario": "carla", "contrasena": CONTRASENA_DE_PRUEBA}
    )

    assert respuesta.status_code == 200
    mensaje = _mensaje_de_error(respuesta.get_data(as_text=True))
    assert "rechazada" in mensaje
    assert "documentación incompleta" in mensaje
    assert cliente.get("/").status_code == 302


def test_req_32_credenciales_equivocadas_dan_el_mismo_mensaje_exista_o_no(
    cliente, cuentas
):
    """Criterio: con contraseña equivocada no se dice si el usuario existe."""
    cuentas.registrar("ana", CONTRASENA_DE_PRUEBA)

    existente = cliente.post(
        "/ingresar", data={"usuario": "ana", "contrasena": "equivocada"}
    )
    inexistente = cliente.post(
        "/ingresar", data={"usuario": "nadie", "contrasena": "equivocada"}
    )

    assert existente.status_code == 200
    assert inexistente.status_code == 200
    assert _mensaje_de_error(existente.get_data(as_text=True)) == (
        MENSAJE_DE_CREDENCIALES_INVALIDAS
    )
    assert _mensaje_de_error(inexistente.get_data(as_text=True)) == (
        MENSAJE_DE_CREDENCIALES_INVALIDAS
    )
    assert "ana" not in _mensaje_de_error(existente.get_data(as_text=True))


def test_req_32_el_registro_muestra_la_pantalla_de_pendiente(cliente, conexion):
    """Criterio: el registro responde 200 con el estado «pendiente» y el usuario."""
    respuesta = cliente.post(
        "/registrarme",
        data={
            "usuario": "nueva",
            "contrasena": CONTRASENA_DE_PRUEBA,
            "repetir": CONTRASENA_DE_PRUEBA,
        },
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert "Tu cuenta está esperando aprobación" in cuerpo
    assert "nueva" in cuerpo
    fila = conexion.execute(
        "SELECT estado, wallet_id FROM users WHERE username = %s", ("nueva",)
    ).fetchone()
    assert fila == ("pendiente", None)


def test_req_32_el_registro_normaliza_el_usuario_y_lo_muestra(cliente, conexion):
    """Criterio: el nombre se guarda normalizado y la pantalla muestra cuál ingresar."""
    respuesta = cliente.post(
        "/registrarme",
        data={
            "usuario": "  Nueva  ",
            "contrasena": CONTRASENA_DE_PRUEBA,
            "repetir": CONTRASENA_DE_PRUEBA,
        },
    )

    assert respuesta.status_code == 200
    assert "nueva" in respuesta.get_data(as_text=True)
    fila = conexion.execute(
        "SELECT username FROM users WHERE username = %s", ("nueva",)
    ).fetchone()
    assert fila == ("nueva",)


def test_req_32_el_registro_exige_que_las_contrasenas_coincidan(cliente, conexion):
    """Criterio: las dos contraseñas tienen que ser iguales para crear la cuenta."""
    respuesta = cliente.post(
        "/registrarme",
        data={
            "usuario": "nueva",
            "contrasena": CONTRASENA_DE_PRUEBA,
            "repetir": "otra-clave-distinta",
        },
    )

    assert respuesta.status_code == 200
    assert "Las contraseñas no coinciden" in respuesta.get_data(as_text=True)
    assert conexion.execute("SELECT count(*) FROM users").fetchone()[0] == 0


def test_req_32_el_registro_duplicado_avisa_sin_crear_otra_cuenta(cliente, cuentas):
    """Criterio: un usuario repetido se rechaza con motivo y no deja otra fila."""
    cuentas.registrar("nueva", CONTRASENA_DE_PRUEBA)

    respuesta = cliente.post(
        "/registrarme",
        data={
            "usuario": "nueva",
            "contrasena": CONTRASENA_DE_PRUEBA,
            "repetir": CONTRASENA_DE_PRUEBA,
        },
    )

    assert respuesta.status_code == 200
    assert "ya está registrado" in respuesta.get_data(as_text=True)
    assert len(cuentas.pendientes()) == 1


def test_req_30_el_formulario_limita_el_usuario_a_los_caracteres_permitidos(cliente):
    """Criterio: el campo de usuario lleva el patrón y la ayuda de la constante.

    Se mira el formulario renderizado, no la validación del servicio: el `pattern`,
    el `maxlength`, el `autocapitalize` y el `spellcheck` tienen que estar en el
    HTML, y la ayuda visible sale de la misma constante para no desincronizarse.
    """
    for ruta in ("/registrarme", "/ingresar"):
        cuerpo = cliente.get(ruta).get_data(as_text=True)
        assert f'pattern="{PATRON_DE_USUARIO}"' in cuerpo, ruta
        assert f'maxlength="{LARGO_MAXIMO_DE_USUARIO}"' in cuerpo, ruta
        assert 'autocapitalize="off"' in cuerpo, ruta
        assert 'spellcheck="false"' in cuerpo, ruta
        assert AYUDA_DE_USUARIO in cuerpo, ruta
