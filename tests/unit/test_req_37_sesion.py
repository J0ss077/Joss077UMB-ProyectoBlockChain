"""REQ-37: la configuración de la sesión vive en el entorno.

Los dos lectores nuevos se prueban sin abrir ninguna conexión: esta suite corre con
la base apagada (REQ-17), y lo que se mide es de dónde sale cada valor y qué pasa
cuando falta. Los nombres de las variables se importan de `factory` en vez de
repetirlos como literales, igual que el guard de REQ-17 exige para la cadena de
conexión.
"""
import pytest

from src.persistence import factory

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
    assert "`.env.example`" in mensaje


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
    assert "`.env.example`" in mensaje


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
