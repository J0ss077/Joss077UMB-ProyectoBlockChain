"""REQ-37: la configuración de la sesión vive en el entorno.

Los dos lectores nuevos se prueban sin abrir ninguna conexión: esta suite corre con
la base apagada (REQ-17), y lo que se mide es de dónde sale cada valor y qué pasa
cuando falta. Los nombres de las variables se importan de `factory` en vez de
repetirlos como literales, igual que el guard de REQ-17 exige para la cadena de
conexión.
"""
import pathlib

import pytest

from src.persistence import factory
from src.web import app as aplicacion_web

SECRETO = "secreto-de-sesion-de-prueba"
CONTRASENA = "contrasena-del-administrador-de-prueba"


def _sin_el_env_del_repositorio(monkeypatch, tmp_path) -> None:
    """Deja la prueba sin variables en el proceso y sin el `.env` real de por medio."""
    monkeypatch.delenv(factory.VARIABLE_DEL_SECRETO_DE_SESION, raising=False)
    monkeypatch.delenv(factory.VARIABLE_DE_LA_CONTRASENA_DEL_ADMINISTRADOR, raising=False)
    monkeypatch.setattr(factory, "ENV_FILE", tmp_path / "no-existe.env")


def test_req_37_el_secreto_de_sesion_se_lee_del_entorno(monkeypatch):
    """REQ-37: la clave que firma la cookie de sesión sale del entorno."""
    monkeypatch.setenv(factory.VARIABLE_DEL_SECRETO_DE_SESION, SECRETO)
    assert factory.session_secret() == SECRETO.encode("utf-8")


def test_req_37_el_secreto_de_sesion_falta_y_lo_dice(monkeypatch, tmp_path):
    """REQ-37: sin la clave, la sesión falla nombrando la variable y qué hacer."""
    _sin_el_env_del_repositorio(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError) as error:
        factory.session_secret()
    mensaje = str(error.value)
    assert factory.VARIABLE_DEL_SECRETO_DE_SESION in mensaje
    assert "agregue" in mensaje and "`.env`" in mensaje


def test_req_37_la_contrasena_del_administrador_se_lee_del_entorno(monkeypatch):
    """REQ-37: la contraseña de la cuenta de administrador sale del entorno."""
    monkeypatch.setenv(factory.VARIABLE_DE_LA_CONTRASENA_DEL_ADMINISTRADOR, CONTRASENA)
    assert factory.admin_password() == CONTRASENA


def test_req_37_la_contrasena_del_administrador_falta_y_lo_dice(monkeypatch, tmp_path):
    """REQ-37: sin la contraseña, el arranque falla nombrando la variable y qué hacer."""
    _sin_el_env_del_repositorio(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError) as error:
        factory.admin_password()
    mensaje = str(error.value)
    assert factory.VARIABLE_DE_LA_CONTRASENA_DEL_ADMINISTRADOR in mensaje
    assert "agregue" in mensaje and "`.env`" in mensaje


def test_req_37_el_secreto_de_sesion_de_plantilla_se_rechaza(monkeypatch):
    """REQ-37: la clave de ceros de `.env.example` no firma la cookie de nadie.

    Es un valor público: aceptarlo dejaría que cualquiera fabricara una cookie con
    la clave que está en el repositorio.
    """
    monkeypatch.setenv(
        factory.VARIABLE_DEL_SECRETO_DE_SESION,
        factory.SECRETO_DE_SESION_DE_LA_PLANTILLA,
    )
    with pytest.raises(RuntimeError) as error:
        factory.session_secret()
    assert factory.VARIABLE_DEL_SECRETO_DE_SESION in str(error.value)
    assert "plantilla" in str(error.value)
    assert "reemplácela" in str(error.value)


def test_req_37_la_contrasena_de_plantilla_se_rechaza(monkeypatch):
    """REQ-37: la contraseña de ejemplo del administrador no se acepta en silencio."""
    monkeypatch.setenv(
        factory.VARIABLE_DE_LA_CONTRASENA_DEL_ADMINISTRADOR,
        factory.CONTRASENA_DEL_ADMINISTRADOR_DE_LA_PLANTILLA,
    )
    with pytest.raises(RuntimeError) as error:
        factory.admin_password()
    assert factory.VARIABLE_DE_LA_CONTRASENA_DEL_ADMINISTRADOR in str(error.value)
    assert "plantilla" in str(error.value)
    assert "reemplácela" in str(error.value)


def test_req_37_el_respaldo_de_la_aplicacion_rechaza_el_secreto_de_plantilla(
    monkeypatch,
):
    """REQ-37: el respaldo de `create_app` rechaza la misma clave pública.

    La aplicación real recibe el secreto del lector de la configuración, pero el
    respaldo también puede leerlo del entorno: si aceptara la clave de ceros, armar
    la aplicación sin `secret_key` dejaría la cookie firmada con un valor del
    repositorio.
    """
    assert (
        aplicacion_web.SECRETO_DE_SESION_DE_LA_PLANTILLA
        == factory.SECRETO_DE_SESION_DE_LA_PLANTILLA
    )
    monkeypatch.setenv(
        factory.VARIABLE_DEL_SECRETO_DE_SESION,
        factory.SECRETO_DE_SESION_DE_LA_PLANTILLA,
    )
    with pytest.raises(RuntimeError, match="plantilla"):
        aplicacion_web.create_app(lambda: None, lambda: None)


def test_req_37_los_valores_que_se_rechazan_son_los_de_la_plantilla():
    """REQ-37: los valores rechazados son exactamente los que trae `.env.example`.

    Si la plantilla cambiara y las constantes no, el rechazo dejaría pasar el valor
    público; atar los dos evita esa deriva.
    """
    valores = {}
    for linea in pathlib.Path(".env.example").read_text(encoding="utf-8").splitlines():
        if not linea.strip() or linea.lstrip().startswith("#"):
            continue
        clave, separador, valor = linea.partition("=")
        if separador:
            valores[clave.strip()] = valor.strip().strip("'\"")
    assert (
        valores[factory.VARIABLE_DEL_SECRETO_DE_SESION]
        == factory.SECRETO_DE_SESION_DE_LA_PLANTILLA
    )
    assert (
        valores[factory.VARIABLE_DE_LA_CONTRASENA_DEL_ADMINISTRADOR]
        == factory.CONTRASENA_DEL_ADMINISTRADOR_DE_LA_PLANTILLA
    )
    # La clave maestra de relleno recibe el mismo tratamiento: si la plantilla
    # cambiara y la constante no, el rechazo dejaría pasar el valor público.
    assert (
        valores[factory.VARIABLE_DE_LA_CLAVE_MAESTRA]
        == factory.CLAVE_MAESTRA_DE_LA_PLANTILLA
    )


def test_req_37_los_dos_lectores_toman_los_valores_de_env(monkeypatch, tmp_path):
    """REQ-37: sin variables en el proceso, los dos valores se leen del `.env`."""
    _sin_el_env_del_repositorio(monkeypatch, tmp_path)
    archivo = tmp_path / ".env"
    archivo.write_text(
        f"{factory.VARIABLE_DEL_SECRETO_DE_SESION}={SECRETO}\n"
        f"{factory.VARIABLE_DE_LA_CONTRASENA_DEL_ADMINISTRADOR}={CONTRASENA}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(factory, "ENV_FILE", archivo)
    assert factory.session_secret() == SECRETO.encode("utf-8")
    assert factory.admin_password() == CONTRASENA
