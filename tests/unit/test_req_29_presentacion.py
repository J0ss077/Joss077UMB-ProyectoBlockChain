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
    # El atributo exacto lo ata la prueba de contrato; acá se mira que se escriba el
    # valor completo del origen y no el texto que se ve.
    assert "writeText(origen.dataset." in guion
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
    # `dataset` es como el DOM lee el atributo: `data-foo-bar` se lee `fooBar`.
    assert f"dataset.{_como_lo_lee_el_dom(atributo)}" in guion, (
        f"el guion no lee el atributo {atributo} con la forma de `dataset`"
    )


def _atributo_de_las_macros(macros: str) -> str:
    """El atributo `data-*` con el que las dos macros entregan el valor completo.

    Se lee del propio marcado y no de una lista escrita acá: una prueba que nombrara
    el atributo por su cuenta seguiría pasando si las dos mitades cambiaran juntas.
    """
    escritos = set(re.findall(r'\b(data-[a-z-]+)="\{\{ texto \}\}"', macros))
    assert len(escritos) == 1, f"las macros escriben un solo atributo de copia: {escritos}"
    return escritos.pop()


def _como_lo_lee_el_dom(atributo: str) -> str:
    """El nombre con el que `dataset` lee un atributo `data-*`: `data-foo-bar` -> `fooBar`."""
    partes = atributo.removeprefix("data-").split("-")
    return partes[0] + "".join(parte.capitalize() for parte in partes[1:])
