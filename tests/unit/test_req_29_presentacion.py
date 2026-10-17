"""REQ-29: ninguna ruta decide reglas de negocio ni ejecuta consultas.

La presentación habla con la fachada del ledger y con sus objetos, nunca con el
motor: si `src/web/app.py` nombrara `psycopg` o `persistence`, la capa tendría una
decisión de negocio o una consulta propia. Las pruebas leen los fuentes y no
importan el módulo, así que corren sin base de datos (REQ-17).

El copiado de los valores tiene dos mitades que no comparten código: las macros de
`_macros.html`, que escriben el atributo con el valor completo, y el guion de
`base.html`, que lo busca y lo lee. La prueba de contrato las ata: el atributo y el
selector tienen que ser el mismo, o la copia deja de funcionar en silencio.
"""
import pathlib
import re

GUION = pathlib.Path("src/web/templates/base.html")
MACROS = pathlib.Path("src/web/templates/_macros.html")


def test_req_29_la_presentacion_no_importa_persistencia_ni_psycopg():
    """REQ-29: ninguna ruta decide reglas ni ejecuta consultas."""
    fuente = (pathlib.Path("src/web/app.py")).read_text(encoding="utf-8")
    assert "psycopg" not in fuente and "persistence" not in fuente


def test_req_29_el_guion_de_copiar_avisa_cuando_la_copia_no_sale():
    """REQ-29: el guion de copiar avisa en los dos desenlaces, no solo en el bueno.

    La escritura al portapapeles puede ser denegada y la API puede faltar por
    completo: en los dos casos la persona tiene que ver un aviso —el valor
    completo sigue en el `title` y en `data-copiar`— y ninguna promesa puede
    quedar rechazada sin manejar.
    """
    guion = GUION.read_text(encoding="utf-8")

    assert "navigator.clipboard" in guion
    assert "writeText(origen.dataset.copiar)" in guion
    # La rama de rechazo: sin ella la escritura denegada no avisa y la promesa queda sin manejar.
    assert re.search(r"\.then\([\s\S]*?\)\s*\.catch\(", guion)
    # El aviso de fallo cubre las dos salidas: la API ausente y la escritura rechazada.
    assert re.search(r"!navigator\.clipboard[\s\S]{0,200}?no se pudo copiar", guion)
    assert re.search(r"\.catch\([\s\S]{0,200}?no se pudo copiar", guion)


def test_req_29_el_guion_de_copiar_usa_el_atributo_que_escriben_las_macros():
    """REQ-29: el atributo de las macros y el selector del guion son el mismo.

    Las dos mitades no comparten código: la macro escribe el valor completo en un
    atributo `data-*` y el guion lo busca con un selector y lo lee con `dataset`. Si
    un lado cambia solo, la copia se rompe y nada más lo nota. La prueba saca las dos
    mitades de los archivos —no repite el nombre en un tercer lugar— y exige que
    coincidan: el atributo que escriben `dato` y `copiar` es el que selecciona y lee
    el guion.
    """
    guion = GUION.read_text(encoding="utf-8")
    macros = MACROS.read_text(encoding="utf-8")

    atributo = _atributo_de_las_macros(macros)
    assert f'closest("[{atributo}]")' in guion, (
        f"el guion no busca el atributo {atributo} que escriben las macros"
    )
    # `dataset` es como el DOM lee el atributo: `data-foo-bar` se lee `fooBar`. La
    # llamada se exige entera, no por prefijo: el guion tiene que escribir el valor
    # completo del origen con ese nombre.
    lectura = _como_lo_lee_el_dom(atributo)
    assert f"writeText(origen.dataset.{lectura})" in guion, (
        f"el guion no escribe `origen.dataset.{lectura}`"
    )


MACRO = re.compile(r"\{% macro (\w+)\((.*?)\{%- endmacro %\}", re.DOTALL)


def _atributo_de_las_macros(macros: str) -> str:
    """El atributo `data-*` con el que **cada** macro entrega el valor completo.

    Se mira macro por macro y no el conjunto de atributos del archivo: si una de las
    dos perdiera el atributo, el conjunto seguiría teniendo el de la otra y el botón
    quedaría sin coincidir con el guion sin que la prueba lo notara. El nombre se lee
    del propio marcado, no de una lista escrita acá.
    """
    escritos = {
        nombre: re.findall(r'\b(data-[a-z-]+)="\{\{ texto \}\}"', cuerpo)
        for nombre, cuerpo in MACRO.findall(macros)
    }
    con_atributo = {nombre: valores for nombre, valores in escritos.items() if valores}
    assert set(con_atributo) == {"dato", "copiar"}, (
        f"`dato` y `copiar` son las macros que entregan el valor completo: {sorted(con_atributo)}"
    )
    nombres = {valor for valores in con_atributo.values() for valor in valores}
    assert len(nombres) == 1, f"las dos macros tienen que escribir el mismo atributo: {nombres}"
    return nombres.pop()


def _como_lo_lee_el_dom(atributo: str) -> str:
    """El nombre con el que `dataset` lee un atributo `data-*`: `data-foo-bar` -> `fooBar`."""
    partes = atributo.removeprefix("data-").split("-")
    return partes[0] + "".join(parte.capitalize() for parte in partes[1:])
