"""REQ-36 y REQ-30: las credenciales se guardan hasheadas y el usuario se valida.

Las reglas de contraseña y de forma del usuario son de la capa de cuentas y no
tocan la base: esta suite corre con el motor apagado (REQ-17). El patrón de la
interfaz y la validación se prueban juntos para que no puedan divergir.
"""
import re

from src.accounts.credentials import (
    PATRON_DE_USUARIO,
    hashear_contrasena,
    normalizar_usuario,
    validar_contrasena,
    validar_usuario,
    verificar_contrasena,
)


def test_req_36_dos_usuarios_con_la_misma_contrasena_tienen_hashes_distintos():
    """REQ-36: dos usuarios con la misma contraseña tienen hashes distintos."""
    assert hashear_contrasena("secreta1") != hashear_contrasena("secreta1")


def test_req_36_el_hash_no_contiene_la_contrasena():
    """REQ-36: la contraseña no queda en claro dentro del valor guardado."""
    assert "secreta1" not in hashear_contrasena("secreta1")


def test_req_36_verifica_la_correcta_y_rechaza_la_equivocada():
    """REQ-36: la contraseña correcta verifica y la equivocada no."""
    guardado = hashear_contrasena("secreta1")
    assert verificar_contrasena("secreta1", guardado) is True
    assert verificar_contrasena("secreta2", guardado) is False


def test_req_36_el_hash_es_autodescriptivo():
    """REQ-36: el valor guardado declara el algoritmo y su costo."""
    campos = hashear_contrasena("secreta1").split("$")
    assert campos[0] == "scrypt"
    assert campos[1:4] == ["16384", "8", "1"]
    assert len(campos) == 6


def test_req_36_un_valor_guardado_corrupto_no_verifica():
    """REQ-36: un valor guardado con formato inválido devuelve False, sin lanzar."""
    for guardado in ("", "no-es-un-hash", "scrypt$16384$8$1$@@@$@@@", "md5$1$2$3$a$b"):
        assert verificar_contrasena("secreta1", guardado) is False


def test_req_30_el_usuario_se_normaliza_y_se_valida():
    """REQ-30: el usuario del registro se normaliza y se valida con sus reglas."""
    assert normalizar_usuario("  Ana ") == "ana"
    assert validar_usuario("ana") is None
    assert validar_usuario("a") is not None  # demasiado corto
    assert validar_usuario("ana perez") is not None  # espacios


def test_req_30_el_patron_y_la_validacion_dicen_lo_mismo():
    """REQ-30: el patrón de la interfaz acepta exactamente lo que acepta la validación."""
    for nombre in ("ana", "ana.perez", "ana_perez-2", "a1b"):
        assert re.fullmatch(PATRON_DE_USUARIO, nombre) and validar_usuario(nombre) is None
    for nombre in ("Ana", "ana perez", "a", "ana@x", "ñ"):
        assert not (re.fullmatch(PATRON_DE_USUARIO, nombre) and validar_usuario(nombre) is None)


def test_req_30_la_contrasena_exige_un_largo_minimo():
    """REQ-30: el registro no acepta una contraseña más corta que el mínimo."""
    assert validar_contrasena("secreta1") is None
    assert validar_contrasena("secreta") is not None
    assert validar_contrasena("") is not None
