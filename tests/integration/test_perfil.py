"""El perfil (`/perfil`) y el cambio de contraseña con aprobación del administrador.

El usuario común pide el cambio con su contraseña actual; la nueva queda guardada
como hash en una solicitud y recién al aprobarla un administrador reemplaza a la
de la cuenta. Hasta entonces la persona entra con la de siempre. El administrador
cambia la suya de una vez, porque no tiene a quién pedírsela.
"""
import pytest

from src.accounts.service import (
    MENSAJE_CONTRASENA_ACTUAL_INCORRECTA,
    MENSAJE_SOLICITUD_YA_PENDIENTE,
    CambioDeContrasenaInvalido,
    CredencialesInvalidas,
)
from src.web.perfil import MENSAJE_CONTRASENAS_DISTINTAS, MENSAJE_SOLICITUD_ENVIADA
from tests.integration.conftest import (
    CONTRASENA_DE_PRUEBA,
    CONTRASENA_DEL_ADMINISTRADOR,
    ingresar_como,
)

NUEVA = "otra-clave-9"


def _pedir(cliente, actual=CONTRASENA_DE_PRUEBA, nueva=NUEVA, repetir=None):
    return cliente.post(
        "/perfil/contrasena",
        data={"actual": actual, "nueva": nueva, "repetir": nueva if repetir is None else repetir},
        follow_redirects=True,
    )


def test_el_perfil_exige_sesion(cliente):
    respuesta = cliente.get("/perfil")

    assert respuesta.status_code == 302
    assert "/ingresar" in respuesta.headers["Location"]


def test_el_perfil_muestra_los_datos_de_la_cuenta(cliente_comun, usuario_comun):
    cuerpo = cliente_comun.get("/perfil").get_data(as_text=True)

    assert usuario_comun.username in cuerpo
    assert str(usuario_comun.wallet_id) in cuerpo
    assert 'action="/perfil/contrasena"' in cuerpo
    assert 'href="/perfil" aria-current="page"' in cuerpo


def test_el_cambio_del_comun_espera_al_administrador(
    cliente_comun, usuario_comun, cuentas
):
    cuerpo = _pedir(cliente_comun).get_data(as_text=True)

    assert MENSAJE_SOLICITUD_ENVIADA in cuerpo
    assert "esperando aprobación" in cuerpo
    # Mientras no se apruebe, la contraseña de siempre sigue siendo la que vale.
    assert cuentas.autenticar("ana", CONTRASENA_DE_PRUEBA).id == usuario_comun.id
    with pytest.raises(CredencialesInvalidas):
        cuentas.autenticar("ana", NUEVA)
    # Con un cambio en espera no se ofrece otro formulario.
    assert 'action="/perfil/contrasena"' not in cuerpo


def test_al_aprobar_la_contrasena_nueva_reemplaza_a_la_anterior(
    aplicacion, cliente_comun, administrador, cuentas
):
    _pedir(cliente_comun)
    admin = aplicacion.test_client()
    ingresar_como(admin, administrador.username, CONTRASENA_DEL_ADMINISTRADOR)
    (solicitud,) = cuentas.solicitudes_pendientes()

    cola = admin.get("/admin/pendientes").get_data(as_text=True)
    assert f"/admin/contrasenas/{solicitud.id}/aprobar" in cola
    assert NUEVA not in cola

    admin.post(f"/admin/contrasenas/{solicitud.id}/aprobar")

    assert cuentas.solicitudes_pendientes() == []
    assert cuentas.autenticar("ana", NUEVA).username == "ana"
    with pytest.raises(CredencialesInvalidas):
        cuentas.autenticar("ana", CONTRASENA_DE_PRUEBA)
    assert "se aprobó el" in cliente_comun.get("/perfil").get_data(as_text=True)


def test_al_rechazar_sigue_la_anterior_y_se_ve_el_motivo(
    aplicacion, cliente_comun, administrador, cuentas
):
    _pedir(cliente_comun)
    admin = aplicacion.test_client()
    ingresar_como(admin, administrador.username, CONTRASENA_DEL_ADMINISTRADOR)
    (solicitud,) = cuentas.solicitudes_pendientes()

    admin.post(
        f"/admin/contrasenas/{solicitud.id}/rechazar", data={"motivo": "no la reconozco"}
    )

    assert cuentas.autenticar("ana", CONTRASENA_DE_PRUEBA).username == "ana"
    perfil = cliente_comun.get("/perfil").get_data(as_text=True)
    assert "rechazó tu último cambio" in perfil
    assert "no la reconozco" in perfil
    # Después de un rechazo se puede volver a pedir.
    assert 'action="/perfil/contrasena"' in perfil


def test_resolver_dos_veces_avisa_y_no_escribe(cuentas, usuario_comun):
    solicitud = cuentas.cambiar_contrasena(usuario_comun.id, CONTRASENA_DE_PRUEBA, NUEVA)
    cuentas.resolver_solicitud(solicitud.id, aprobada=False)

    with pytest.raises(CambioDeContrasenaInvalido):
        cuentas.resolver_solicitud(solicitud.id, aprobada=True)
    assert cuentas.autenticar("ana", CONTRASENA_DE_PRUEBA).username == "ana"


def test_sin_la_contrasena_actual_no_se_pide_nada(cliente_comun, cuentas):
    cuerpo = _pedir(cliente_comun, actual="equivocada").get_data(as_text=True)

    assert MENSAJE_CONTRASENA_ACTUAL_INCORRECTA in cuerpo
    assert cuentas.solicitudes_pendientes() == []


def test_si_la_repeticion_no_coincide_no_se_pide_nada(cliente_comun, cuentas):
    cuerpo = _pedir(cliente_comun, repetir="distinta-1").get_data(as_text=True)

    assert MENSAJE_CONTRASENAS_DISTINTAS in cuerpo
    assert cuentas.solicitudes_pendientes() == []


def test_una_sola_solicitud_pendiente_por_cuenta(cuentas, usuario_comun):
    cuentas.cambiar_contrasena(usuario_comun.id, CONTRASENA_DE_PRUEBA, NUEVA)

    with pytest.raises(CambioDeContrasenaInvalido, match=MENSAJE_SOLICITUD_YA_PENDIENTE):
        cuentas.cambiar_contrasena(usuario_comun.id, CONTRASENA_DE_PRUEBA, "tercera-clave")
    assert len(cuentas.solicitudes_pendientes()) == 1


def test_la_contrasena_nueva_cumple_la_regla_del_registro(cuentas, usuario_comun):
    with pytest.raises(CambioDeContrasenaInvalido):
        cuentas.cambiar_contrasena(usuario_comun.id, CONTRASENA_DE_PRUEBA, "corta")


def test_el_administrador_cambia_la_suya_sin_aprobacion(
    cliente_admin, administrador, cuentas
):
    cuerpo = _pedir(cliente_admin, actual=CONTRASENA_DEL_ADMINISTRADOR).get_data(as_text=True)

    assert "Tu contraseña se cambió." in cuerpo
    assert cuentas.solicitudes_pendientes() == []
    assert cuentas.autenticar(administrador.username, NUEVA).id == administrador.id


def test_el_comun_no_puede_resolver_solicitudes(cliente_comun, cuentas, usuario_comun):
    solicitud = cuentas.cambiar_contrasena(usuario_comun.id, CONTRASENA_DE_PRUEBA, NUEVA)

    respuesta = cliente_comun.post(f"/admin/contrasenas/{solicitud.id}/aprobar")

    assert respuesta.status_code in (302, 403)
    assert len(cuentas.solicitudes_pendientes()) == 1
