"""El idioma de la interfaz: español por defecto, inglés a elección.

La elección viaja en una cookie que pone `POST /idioma`. Estas pruebas cuidan dos
cosas: que toda frase marcada para traducir tenga su versión en inglés —si no, la
página en inglés mostraría pedazos en español— y que la página efectivamente salga
en el idioma elegido, incluidos los mensajes que llegan armados del servicio.
"""
import pathlib
import re

import pytest

from src.accounts import fotos, service
from src.accounts.credentials import (
    AYUDA_DE_USUARIO,
    MOTIVO_DE_CONTRASENA_CORTA,
    MOTIVO_DE_USUARIO_INVALIDO,
)
from src.domain.transaction import RejectionReason
from src.web import admin, perfil, user
from src.web.idioma import COOKIE_DEL_IDIOMA
from src.web.traducciones import EN, MENSAJES_ARMADOS, TEXTOS_DE_JS
from tests.integration.conftest import CONTRASENA_DE_PRUEBA

PLANTILLAS = pathlib.Path("src/web/templates")
GUIONES = pathlib.Path("src/web/static/js")


def _frases_de_las_plantillas() -> set[str]:
    """Toda frase literal que las plantillas pasan por `t(...)` o como texto de `copiar`."""
    frases = set()
    for plantilla in PLANTILLAS.glob("*.html"):
        texto = plantilla.read_text(encoding="utf-8")
        frases |= {m[1] for m in re.findall(r"""\bt\(\s*(["'])(.*?)\1""", texto)}
        frases |= {m[1] for m in re.findall(r"""copiar\([^,]+,\s*(["'])(.*?)\1\s*\)""", texto)}
        # Las rutas de la navegación de `base.html` se traducen con `t(texto)`.
        frases |= set(re.findall(r'\("/[^"]*", "([^"]+)"\)', texto))
    return frases


def _mensajes_de_las_capas() -> set[str]:
    """Los textos que el servicio, las rutas o el dominio entregan para mostrar."""
    mensajes = {
        valor
        for modulo in (service, user, admin, perfil)
        for nombre, valor in vars(modulo).items()
        if nombre.startswith("MENSAJE") and isinstance(valor, str)
    }
    mensajes.discard(user.MENSAJE_CONTACTO_AGREGADO)  # es un mensaje armado
    mensajes |= set(user.MOTIVOS_EN_PALABRAS.values())
    mensajes |= set(user.MESES)
    mensajes |= {motivo.value for motivo in RejectionReason}
    mensajes |= {AYUDA_DE_USUARIO, MOTIVO_DE_USUARIO_INVALIDO, MOTIVO_DE_CONTRASENA_CORTA}
    mensajes |= {valor for nombre, valor in vars(fotos).items() if nombre.startswith("MOTIVO")}
    return mensajes


def test_toda_frase_de_las_plantillas_tiene_traduccion():
    faltan = sorted(_frases_de_las_plantillas() - EN.keys())

    assert faltan == []


def test_todo_mensaje_de_las_capas_tiene_traduccion():
    faltan = sorted(_mensajes_de_las_capas() - EN.keys())

    assert faltan == []


def test_los_guiones_solo_piden_textos_publicados():
    pedidos = set()
    for guion in GUIONES.glob("*.js"):
        pedidos |= set(re.findall(r'tr\("([^"]+)"\)', guion.read_text(encoding="utf-8")))
    pedidos |= {"Vacía", "Débil", "Regular", "Buena", "Fuerte"}  # van por `.map(tr)`

    assert pedidos - set(TEXTOS_DE_JS) == set()
    assert set(TEXTOS_DE_JS) - EN.keys() == set()
    assert set(MENSAJES_ARMADOS) - EN.keys() == set()


def test_por_defecto_la_pagina_va_en_espanol(cliente):
    cuerpo = cliente.get("/ingresar").get_data(as_text=True)

    assert '<html lang="es">' in cuerpo
    assert "Entra con la cuenta que aprobó un administrador." in cuerpo
    assert "window.TEXTOS = {};" in cuerpo


def test_elegir_ingles_guarda_la_cookie_y_vuelve(cliente):
    respuesta = cliente.post("/idioma", data={"idioma": "en", "volver": "/registrarme"})

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == "/registrarme"
    assert f"{COOKIE_DEL_IDIOMA}=en" in respuesta.headers["Set-Cookie"]
    cuerpo = cliente.get("/registrarme").get_data(as_text=True)
    assert '<html lang="en">' in cuerpo
    assert "Create account" in cuerpo
    assert "Crear cuenta" not in cuerpo
    assert '"Show password"' in cuerpo  # los textos de los guiones


@pytest.mark.parametrize("volver", ["//sitio-ajeno.example", "https://sitio-ajeno.example", ""])
def test_volver_no_sale_del_sitio(cliente, volver):
    respuesta = cliente.post("/idioma", data={"idioma": "en", "volver": volver})

    assert respuesta.headers["Location"] == "/"


def test_un_idioma_desconocido_no_se_guarda(cliente):
    respuesta = cliente.post("/idioma", data={"idioma": "fr", "volver": "/ingresar"})

    assert "Set-Cookie" not in respuesta.headers


def test_el_tablero_del_comun_sale_en_ingles(cliente_comun):
    cliente_comun.set_cookie(COOKIE_DEL_IDIOMA, "en")

    cuerpo = cliente_comun.get("/mi-tablero").get_data(as_text=True)

    assert "Send money" in cuerpo
    assert "Hi, ana" in cuerpo
    for frase in ("Enviar dinero", "Saldo disponible", "Con quién más te mueves"):
        assert frase not in cuerpo


def test_un_mensaje_armado_del_servicio_se_traduce(cliente, cuentas):
    rechazada = cuentas.registrar("rita", CONTRASENA_DE_PRUEBA)
    cuentas.rechazar(rechazada.id, "faltan datos")
    cliente.set_cookie(COOKIE_DEL_IDIOMA, "en")

    cuerpo = cliente.post(
        "/ingresar", data={"usuario": "rita", "contrasena": CONTRASENA_DE_PRUEBA}
    ).get_data(as_text=True)

    # El motivo lo escribió una persona: se muestra tal cual, dentro de la frase traducida.
    assert "Your account was rejected: faltan datos." in cuerpo


def test_las_paginas_del_administrador_salen_en_ingles(cliente_admin):
    cliente_admin.set_cookie(COOKIE_DEL_IDIOMA, "en")

    for ruta, frase in (
        ("/", "Ledger status"),
        ("/admin/pendientes", "Password changes"),
        ("/wallets", "Register wallet"),
        ("/transacciones", "Propose transaction"),
        ("/bloques", "Close block"),
        ("/verificar", "Verify chain"),
        ("/perfil", "Change password"),
    ):
        assert frase in cliente_admin.get(ruta).get_data(as_text=True), ruta


@pytest.mark.parametrize("ruta", ["/ingresar", "/registrarme"])
def test_sin_sesion_el_idioma_se_elige_en_la_barra(cliente, ruta):
    assert 'class="selector-idioma"' in cliente.get(ruta).get_data(as_text=True)


def test_con_sesion_el_idioma_y_el_perfil_estan_detras_del_nombre(cliente_comun):
    tablero = cliente_comun.get("/mi-tablero").get_data(as_text=True)

    assert 'class="selector-idioma"' not in tablero
    # El perfil no es una pestaña: se llega tocando el nombre de la barra.
    assert tablero.count('href="/perfil"') == 1
    assert 'class="usuario-sesion" href="/perfil"' in tablero
    assert 'class="opciones-idioma"' in cliente_comun.get("/perfil").get_data(as_text=True)
