"""La navegación de la entrega: cada enlace del menú abre su pantalla (Fase 4).

El criterio de la revisión pide «validar que los botones y las opciones de navegación
funcionen correctamente». La prueba recorre el menú que la aplicación pinta de verdad
—no una lista copiada acá— y abre cada enlace con la sesión del rol que lo ve: los dos
roles tienen que llegar a todas sus pantallas, ninguna pantalla puede perder el menú y
el usuario común no puede ver opciones del administrador.
"""
import html
import re

MENU = re.compile(r'<nav class="navegacion"[^>]*>(.*?)</nav>', re.S)
ENLACE = re.compile(r'href="([^"]+)"')

# Las pantallas que cada rol tiene que poder alcanzar; el resto de los enlaces del
# menú se descubre del marcado. El ayudante va con `?desde=`, así que se compara
# por su ruta y no por el valor completo.
PANTALLAS_DEL_ADMINISTRADOR = {
    "/",
    "/admin/pendientes",
    "/wallets",
    "/transacciones",
    "/bloques",
    "/verificar",
    "/admin/estadisticas",
    "/asistente",
}
PANTALLAS_DEL_COMUN = {
    "/mi-tablero",
    "/mi-historial",
    "/mis-contactos",
    "/mis-estadisticas",
    "/asistente",
}
# Las rutas que sólo son del administrador: el menú del común no puede ofrecerlas.
SOLO_DEL_ADMINISTRADOR = {
    "/",
    "/admin/pendientes",
    "/wallets",
    "/transacciones",
    "/bloques",
    "/verificar",
    "/admin/estadisticas",
}


def _enlaces_del_menu(cliente, ruta: str) -> list[str]:
    """Los `href` del menú de la página, ya desescapados."""
    respuesta = cliente.get(ruta)
    assert respuesta.status_code == 200, f"{ruta} respondió {respuesta.status_code}"
    cuerpo = respuesta.get_data(as_text=True)
    bloque = MENU.search(cuerpo)
    assert bloque, f"la página {ruta} no trae el menú de navegación"
    return [html.unescape(valor) for valor in ENLACE.findall(bloque.group(1))]


def _ruta_de(enlace: str) -> str:
    """La ruta del enlace, sin el `?desde=` con el que viaja el ayudante."""
    return enlace.split("?", 1)[0]


def test_el_menu_del_administrador_abre_todas_sus_pantallas(cliente_admin):
    enlaces = _enlaces_del_menu(cliente_admin, "/")

    assert {_ruta_de(enlace) for enlace in enlaces} == PANTALLAS_DEL_ADMINISTRADOR
    for enlace in enlaces:
        respuesta = cliente_admin.get(enlace)
        assert respuesta.status_code == 200, (
            f"el enlace {enlace} del menú respondió {respuesta.status_code}"
        )
        # La misma barra en todas las pantallas: desde cualquiera se puede salir.
        assert 'class="navegacion"' in respuesta.get_data(as_text=True), (
            f"la pantalla {enlace} perdió el menú"
        )


def test_el_menu_del_comun_abre_todas_sus_pantallas(cliente_comun):
    enlaces = _enlaces_del_menu(cliente_comun, "/mi-tablero")

    assert {_ruta_de(enlace) for enlace in enlaces} == PANTALLAS_DEL_COMUN
    for enlace in enlaces:
        respuesta = cliente_comun.get(enlace)
        assert respuesta.status_code == 200, (
            f"el enlace {enlace} del menú respondió {respuesta.status_code}"
        )
        assert 'class="navegacion"' in respuesta.get_data(as_text=True), (
            f"la pantalla {enlace} perdió el menú"
        )


def test_el_comun_no_ve_opciones_del_administrador(cliente_comun):
    enlaces = {_ruta_de(enlace) for enlace in _enlaces_del_menu(cliente_comun, "/mi-tablero")}

    # `"/"` no se cuenta: es la portada del administrador y para el común redirige
    # a su tablero, pero el menú del común no la enlaza en ningún lado.
    assert enlaces.isdisjoint(SOLO_DEL_ADMINISTRADOR - {"/"})


def test_el_logo_vuelve_a_la_portada_del_administrador(cliente_admin):
    cuerpo = cliente_admin.get("/wallets").get_data(as_text=True)

    assert '<a class="marca" href="/">' in cuerpo
    assert cliente_admin.get("/").status_code == 200


def test_el_logo_lleva_al_comun_a_su_tablero(cliente_comun):
    cuerpo = cliente_comun.get("/mi-historial").get_data(as_text=True)

    assert '<a class="marca" href="/">' in cuerpo
    respuesta = cliente_comun.get("/")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/mi-tablero")
