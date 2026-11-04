"""La aplicación cuando el motor no responde: página propia y 503 (Fase 4).

El criterio de la entrega pide «manejo básico de errores de conexión». Antes, una
base apagada se veía como el 500 genérico de Flask —en inglés y sin pista—; desde
`src/persistence/conexion.py` el fallo del motor se levanta como `NoHayConexion` y
la aplicación lo pinta con la misma página de error que ya usan el 403 y el 404.

Estas pruebas no necesitan PostgreSQL: la fábrica que se inyecta no abre nada y el
motor que se intenta de verdad es un puerto cerrado de `127.0.0.1`.
"""
from contextlib import contextmanager
from uuid import uuid4

import pytest

import src.bootstrap as arranque
from src.errores import MENSAJE_SIN_CONEXION, NoHayConexion
from src.persistence.conexion import abrir
from src.web.app import create_app
from src.web.auth import CLAVE_DEL_USUARIO
from src.web.traducciones import EN

CLAVE_DE_PRUEBA = "clave-de-prueba-para-la-sesion-del-503"
CREDENCIALES = {"usuario": "ana", "contrasena": "clave-de-prueba"}


class FabricaQueNoAbre:
    """Fábrica que cuenta sus aperturas y siempre falla con el motor caído."""

    def __init__(self) -> None:
        self.aperturas = 0

    @contextmanager
    def __call__(self):
        self.aperturas += 1
        raise NoHayConexion(MENSAJE_SIN_CONEXION)
        yield  # pragma: no cover


def _cliente(fabrica=None):
    fabrica = fabrica if fabrica is not None else FabricaQueNoAbre()
    app = create_app(fabrica, fabrica, secret_key=CLAVE_DE_PRUEBA)
    return app, app.test_client()


def test_una_conexion_imposible_se_levanta_como_no_hay_conexion():
    """`abrir` traduce sólo el fallo de conexión y conserva la causa original."""
    with pytest.raises(NoHayConexion) as fallo:
        abrir("host=127.0.0.1 port=1 dbname=no-existe connect_timeout=1")

    assert str(fallo.value) == MENSAJE_SIN_CONEXION
    assert fallo.value.__cause__ is not None, "el error del motor tiene que quedar encadenado"


def test_una_pagina_con_la_base_caida_responde_503_y_no_el_500_generico():
    """El primer acceso a la base de un formulario es el que falla y se explica."""
    _, cliente = _cliente()

    respuesta = cliente.post("/ingresar", data=CREDENCIALES)

    assert respuesta.status_code == 503
    cuerpo = respuesta.get_data(as_text=True)
    assert "La base de datos no respondió" in cuerpo
    assert "No se pudo conectar con la base de datos" in cuerpo
    assert "Traceback" not in cuerpo


def test_la_pagina_de_error_no_reintenta_la_conexion_para_pintarse():
    """Pintar el error no puede volver a abrir la base: sería fallar dos veces."""
    fabrica = FabricaQueNoAbre()
    _, cliente = _cliente(fabrica)

    cliente.post("/ingresar", data=CREDENCIALES)

    assert fabrica.aperturas == 1


def test_el_503_ofrece_reintentar_cuando_la_peticion_fue_una_consulta():
    """La recarga de la cuenta en cada petición también se cae con el motor."""
    _, cliente = _cliente()
    with cliente.session_transaction() as sesion:
        sesion[CLAVE_DEL_USUARIO] = str(uuid4())

    cuerpo = cliente.get("/verificar").get_data(as_text=True)

    assert 'href="/verificar"' in cuerpo
    assert "Reintentar" in cuerpo


def test_el_503_no_ofrece_reintentar_despues_de_un_envio():
    """Repetir un POST desde un enlace no es recargar la página: el enlace no va."""
    _, cliente = _cliente()

    cuerpo = cliente.post("/ingresar", data=CREDENCIALES).get_data(as_text=True)

    assert "Reintentar" not in cuerpo


def test_el_mensaje_del_503_esta_traducido():
    """El texto largo también viaja al inglés: la página se pinta con `t()`."""
    assert MENSAJE_SIN_CONEXION in EN
    assert EN["La base de datos no respondió"] == "The database didn't answer"


def test_el_arranque_avisa_en_vez_de_mostrar_una_traza(monkeypatch):
    """`python -m src.bootstrap` con la base caída termina con la instrucción."""

    @contextmanager
    def sin_base():
        raise NoHayConexion(MENSAJE_SIN_CONEXION)
        yield  # pragma: no cover

    monkeypatch.setattr(arranque, "ledger", sin_base)

    with pytest.raises(SystemExit) as salida:
        arranque.main()

    assert "No se pudo conectar con la base de datos" in str(salida.value.code)
