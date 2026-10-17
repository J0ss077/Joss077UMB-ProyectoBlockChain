"""REQ-30: el registro de una cuenta y su validación.

El registro pasa por el servicio de cuentas, que normaliza el nombre antes de
validarlo, hashea la contraseña y escribe la fila con el repositorio. La cuenta
nace `pendiente` y sin wallet: la wallet y el saldo llegan recién con la
aprobación (REQ-33).
"""
import pytest

from src.accounts.credentials import MOTIVO_DE_CONTRASENA_CORTA, MOTIVO_DE_USUARIO_INVALIDO
from src.accounts.model import PENDIENTE, UsuarioDuplicado
from src.accounts.service import Cuentas


def test_req_30_registrar_deja_pendiente_sin_wallet(cuentas: Cuentas):
    """Criterio: la fila existe con estado `pendiente` y sin wallet."""
    creado = cuentas.registrar("  Ana  ", "secreta1")

    assert creado.username == "ana"
    assert creado.estado == PENDIENTE
    assert creado.wallet_id is None
    assert creado.aprobado_en is None
    assert creado.motivo_rechazo is None
    assert creado.password_hash != "secreta1"
    assert [usuario.id for usuario in cuentas.pendientes()] == [creado.id]


def test_req_30_no_se_puede_registrar_dos_veces_el_mismo_nombre(cuentas: Cuentas):
    """Criterio: un usuario repetido se rechaza con motivo y no deja otra fila."""
    cuentas.registrar("ana", "secreta1")

    with pytest.raises(UsuarioDuplicado):
        cuentas.registrar("ANA", "otraclave")
    assert len(cuentas.pendientes()) == 1


def test_req_30_el_registro_rechaza_la_forma_invalida(cuentas: Cuentas):
    """Criterio: el usuario sólo admite minúsculas, dígitos, punto, guion y guion bajo."""
    with pytest.raises(ValueError) as error:
        cuentas.registrar("ana perez", "secreta1")

    assert str(error.value) == MOTIVO_DE_USUARIO_INVALIDO
    assert cuentas.pendientes() == []


def test_req_30_el_registro_rechaza_la_contrasena_corta(cuentas: Cuentas):
    """Criterio: la contraseña del registro tiene un largo mínimo."""
    with pytest.raises(ValueError) as error:
        cuentas.registrar("ana", "corta")

    assert str(error.value) == MOTIVO_DE_CONTRASENA_CORTA
    assert cuentas.pendientes() == []
