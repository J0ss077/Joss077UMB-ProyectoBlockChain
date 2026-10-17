"""REQ-32 y REQ-36: el ingreso sólo abre sesión a una cuenta aprobada.

El servicio verifica la contraseña **antes** de decir nada del estado: así el
pendiente y el rechazado reciben su estado sólo si acertaron la contraseña, y una
contraseña equivocada da el mismo mensaje exista o no el usuario. La comparación
de la contraseña no filtra por tiempo, y el nombre no distingue mayúsculas.
"""
import pytest

from src.accounts.model import (
    APROBADO,
    PENDIENTE,
    RECHAZADO,
    UsuarioDuplicado,
)
from src.accounts.service import (
    CredencialesInvalidas,
    Cuentas,
    NoAprobado,
    UsuarioNoPendiente,
)


def test_req_32_el_pendiente_no_ingresa_y_se_le_dice_su_estado(cuentas: Cuentas):
    """Criterio: con `pendiente` no se abre sesión y el mensaje dice «esperando aprobación»."""
    creado = cuentas.registrar("ana", "secreta1")

    with pytest.raises(NoAprobado) as error:
        cuentas.autenticar("ana", "secreta1")

    assert error.value.estado == PENDIENTE
    assert "esperando aprobación" in str(error.value)
    assert cuentas.pendientes()[0].id == creado.id


def test_req_32_el_rechazado_ingresa_con_el_motivo(cuentas: Cuentas):
    """Criterio: con `rechazado` el ingreso no entra y recibe el motivo."""
    creado = cuentas.registrar("beto", "secreta1")
    cuentas.rechazar(creado.id, "documentación incompleta")

    with pytest.raises(NoAprobado) as error:
        cuentas.autenticar("beto", "secreta1")

    assert error.value.estado == RECHAZADO
    assert error.value.motivo == "documentación incompleta"
    assert "documentación incompleta" in str(error.value)


def test_req_32_con_contrasena_equivocada_el_mensaje_no_distingue_si_existe(
    cuentas: Cuentas,
):
    """Criterio: con contraseña equivocada no se dice si el usuario existe."""
    cuentas.registrar("ana", "secreta1")

    with pytest.raises(CredencialesInvalidas) as existente:
        cuentas.autenticar("ana", "equivocada")
    with pytest.raises(CredencialesInvalidas) as inexistente:
        cuentas.autenticar("nadie", "equivocada")

    assert type(existente.value) is type(inexistente.value)
    assert str(existente.value) == str(inexistente.value)
    assert "ana" not in str(existente.value)


def test_req_32_el_aprobado_ingresa(cuentas: Cuentas):
    """Criterio: con `aprobado` el ingreso devuelve la cuenta y su wallet."""
    creado = cuentas.registrar("ana", "secreta1")
    aprobado = cuentas.aprobar(creado.id)

    autenticado = cuentas.autenticar("ana", "secreta1")

    assert autenticado == aprobado
    assert autenticado.estado == APROBADO
    assert autenticado.wallet_id is not None


def test_req_30_el_ingreso_acepta_el_nombre_en_otra_caja(cuentas: Cuentas):
    """Criterio: el nombre no distingue mayúsculas, también en el ingreso."""
    creado = cuentas.registrar("ana", "secreta1")
    cuentas.aprobar(creado.id)

    assert cuentas.autenticar("ANA", "secreta1").id == creado.id


def test_req_31_rechazar_guarda_el_motivo_y_el_nombre_no_se_reusa(cuentas: Cuentas):
    """Criterio: el rechazo guarda el motivo, es final y no libera el nombre."""
    creado = cuentas.registrar("beto", "secreta1")

    rechazado = cuentas.rechazar(creado.id, "documentación incompleta")

    assert rechazado.estado == RECHAZADO
    assert rechazado.motivo_rechazo == "documentación incompleta"
    assert rechazado.wallet_id is None
    with pytest.raises(UsuarioNoPendiente):
        cuentas.rechazar(creado.id, "otra vez")
    with pytest.raises(UsuarioDuplicado):
        cuentas.registrar("beto", "secreta1")
