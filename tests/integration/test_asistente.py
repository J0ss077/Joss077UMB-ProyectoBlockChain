"""REQ-44 y REQ-45: el ayudante sin sesión, su guía local y el aviso de privacidad.

REQ-44 cuida el alcance y el camino de datos: sin sesión el ayudante no existe,
con sesión común explica la cuenta y contesta con la guía, y el administrador
recibe sólo los conteos de su portada, nunca los nombres de las personas.

REQ-45 cuida lo que sale del equipo: cuando hay un servicio de IA configurado, la
página lo avisa antes de la primera pregunta y cualquier fallo del proveedor cae
en la guía. La configuración usa una URL de loopback que no responde, así que
estas pruebas no salen a la red.
"""
from contextlib import contextmanager

import pytest

from src.domain.blockchain import ensure_genesis
from src.persistence.factory import open_ledger
from src.web.ia import ConectorDeIA
from tests.integration.conftest import (
    CONTRASENA_DE_PRUEBA,
    CONTRASENA_DEL_ADMINISTRADOR,
    crear_app_de_prueba,
    ingresar_como,
)

URL_QUE_NO_RESPONDE = "http://127.0.0.1:9/v1"
CONFIGURACION_CON_IA = {
    "ASISTENTE_PROVEEDOR": "ollama",
    "ASISTENTE_URL": URL_QUE_NO_RESPONDE,
}
AVISO_DE_PRIVACIDAD = (
    "Si escribes una pregunta, tu pregunta y el resumen de tu cuenta (saldo y "
    "últimos movimientos) se envían a un servicio externo de inteligencia "
    "artificial. Los botones de sugerencia no salen de este equipo."
)


@pytest.fixture
def aplicacion_con_ia(conexion, base_limpia, master_key):
    """La aplicación con un conector de IA que existe pero no puede responder."""

    @contextmanager
    def fabrica():
        chain = open_ledger(conexion, encryption_key=master_key)
        ensure_genesis(chain)
        yield chain

    return crear_app_de_prueba(fabrica, asistente=CONFIGURACION_CON_IA)


@pytest.fixture
def cliente_comun_con_ia(aplicacion_con_ia, usuario_comun):
    """Cliente común sobre la aplicación con IA, ya dentro de su sesión."""
    cliente = aplicacion_con_ia.test_client()
    ingresar_como(cliente, usuario_comun.username, CONTRASENA_DE_PRUEBA)
    return cliente


@pytest.fixture
def cliente_admin_con_ia(aplicacion_con_ia, administrador):
    """Cliente administrador sobre la aplicación con IA, ya dentro de su sesión."""
    cliente = aplicacion_con_ia.test_client()
    ingresar_como(cliente, administrador.username, CONTRASENA_DEL_ADMINISTRADOR)
    return cliente


def test_req_44_sin_sesion_el_ayudante_no_existe(cliente):
    """Criterio: la página manda al ingreso y las rutas de datos responden 401."""
    respuesta = cliente.get("/asistente")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/ingresar"
    assert cliente.get("/asistente/ahora").status_code == 401
    assert cliente.post(
        "/asistente/preguntar", json={"pregunta": "¿Qué es esto?"}
    ).status_code == 401


def test_req_44_el_comun_abre_la_pagina_del_ayudante(cliente_comun):
    """Criterio: con sesión común la pestaña del ayudante responde 200."""
    respuesta = cliente_comun.get("/asistente")

    assert respuesta.status_code == 200
    assert "data-asistente" in respuesta.get_data(as_text=True)


def test_req_44_ahora_dice_el_saldo_en_palabras(cliente_comun):
    """Criterio: `/ahora` es JSON, sin IA y con el saldo de bienvenida en palabras."""
    respuesta = cliente_comun.get("/asistente/ahora?pagina=/mi-tablero")

    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["ia"] is False
    assert "tablero" in datos["pagina"]
    assert any(
        "Puedes usar" in punto and "1000" in punto for punto in datos["puntos"]
    )


def test_req_44_ahora_sin_pagina_sugiere_temas_del_rol(
    cliente_comun, aplicacion, administrador
):
    """Criterio: sin `?pagina`, cada rol recibe sugerencias que le sirven.

    La guía de la portada es del administrador. Antes de filtrar por rol, una
    persona común que abría el ayudante sin venir de una pantalla se quedaba con
    cero botones, porque la lista de la portada no le sirve y el respaldo no se
    aplicaba. Los dos clientes son distintos: `cliente_comun` y `cliente_admin`
    comparten el mismo objeto y el segundo ingreso pisaría al primero.
    """
    del_administrador = aplicacion.test_client()
    ingresar_como(del_administrador, administrador.username, CONTRASENA_DEL_ADMINISTRADOR)

    comun = cliente_comun.get("/asistente/ahora").get_json()
    admin = del_administrador.get("/asistente/ahora").get_json()

    assert comun["sugerencias"], "el usuario común se queda sin botones"
    assert admin["sugerencias"], "el administrador se queda sin botones"
    claves_comun = {sugerencia["clave"] for sugerencia in comun["sugerencias"]}
    claves_admin = {sugerencia["clave"] for sugerencia in admin["sugerencias"]}
    assert claves_comun.isdisjoint({"pool", "cerrar_bloque", "pendientes_admin"})
    assert claves_admin & {"pool", "cerrar_bloque", "verificar"}


def test_req_44_una_pregunta_conocida_contesta_la_guia(cliente_comun):
    """Criterio: sin IA, una pregunta de la guía se contesta con la guía."""
    respuesta = cliente_comun.post(
        "/asistente/preguntar", json={"pregunta": "¿Cómo envío dinero?"}
    )

    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["fuente"] == "guia"
    assert "Enviar dinero" in datos["respuesta"]


def test_req_44_un_tema_sugerido_contesta_la_guia(cliente_comun):
    """Criterio: el botón sugerido trae el tema y no gasta ninguna llamada."""
    respuesta = cliente_comun.post(
        "/asistente/preguntar", json={"pregunta": "cuéntame", "tema": "saldo"}
    )

    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["fuente"] == "guia"
    assert "saldo disponible" in datos["respuesta"]


@pytest.mark.parametrize("cuerpo", [[], 3, "texto"])
def test_req_44_un_cuerpo_que_no_es_objeto_da_400(cliente_comun, cuerpo):
    """Criterio: un JSON válido que no es objeto no termina en un 500."""
    respuesta = cliente_comun.post("/asistente/preguntar", json=cuerpo)

    assert respuesta.status_code == 400
    assert respuesta.get_json()["error"] == "cuerpo_invalido"


def test_req_44_el_contexto_del_admin_no_lleva_nombres(
    cliente_admin_con_ia, usuario_comun, monkeypatch
):
    """Criterio: al administrador se le pasan conteos, no los nombres de las cuentas."""
    capturado: dict[str, str] = {}

    def responder(self, instrucciones, mensajes):
        capturado["contexto"] = mensajes[-1]["content"]
        return None

    monkeypatch.setattr(ConectorDeIA, "responder", responder)
    respuesta = cliente_admin_con_ia.post(
        "/asistente/preguntar",
        json={
            "pregunta": "¿Cuántas cuentas hay por aprobar?",
            "pagina": "/admin/pendientes",
        },
    )

    assert respuesta.status_code == 200
    assert respuesta.get_json()["fuente"] == "guia"
    assert usuario_comun.username not in capturado["contexto"]


def test_req_45_la_pagina_avisa_antes_de_preguntar(cliente_comun_con_ia):
    """Criterio: con IA configurada, la página avisa qué datos salen del equipo."""
    respuesta = cliente_comun_con_ia.get("/asistente")

    assert respuesta.status_code == 200
    cuerpo = respuesta.get_data(as_text=True)
    assert AVISO_DE_PRIVACIDAD in cuerpo
    assert "asistente-privacidad" in cuerpo


def test_req_45_sin_ia_el_aviso_no_se_muestra(cliente_comun):
    """Criterio: sin servicio de IA no hay nada que avisar."""
    cuerpo = cliente_comun.get("/asistente").get_data(as_text=True)

    assert AVISO_DE_PRIVACIDAD not in cuerpo
    assert "asistente-privacidad" not in cuerpo


def test_req_45_si_la_ia_falla_contesta_la_guia(cliente_comun_con_ia):
    """Criterio: un proveedor que no responde no produce un 500."""
    respuesta = cliente_comun_con_ia.post(
        "/asistente/preguntar",
        json={"pregunta": "Háblame de los nodos de la red", "pagina": "/mi-tablero"},
    )

    assert respuesta.status_code == 200
    assert respuesta.get_json()["fuente"] == "guia"


def test_req_45_el_tope_por_minuto_corta_la_ia(cliente_comun_con_ia):
    """Criterio: pasadas cinco preguntas, la sexta se contesta con la guía y avisa."""
    respuestas = [
        cliente_comun_con_ia.post(
            "/asistente/preguntar",
            json={"pregunta": f"Háblame de los nodos de la red {numero}"},
        ).get_json()
        for numero in range(6)
    ]

    assert all(datos["fuente"] == "guia" for datos in respuestas)
    assert "Espera un minuto" in respuestas[-1]["respuesta"]
    assert all("Espera un minuto" not in datos["respuesta"] for datos in respuestas[:-1])
