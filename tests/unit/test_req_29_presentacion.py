"""REQ-29: ninguna ruta decide reglas de negocio ni ejecuta consultas.

La presentación habla con la fachada del ledger y con sus objetos, nunca con el
motor: si `src/web/app.py` nombrara `psycopg` o `persistence`, la capa tendría una
decisión de negocio o una consulta propia. La prueba lee el fuente y no importa el
módulo, así que corre sin base de datos (REQ-17).
"""
import pathlib
import re


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
    guion = pathlib.Path("src/web/templates/base.html").read_text(encoding="utf-8")

    assert "navigator.clipboard" in guion
    assert "writeText(origen.dataset.copiar)" in guion
    # La rama de rechazo: sin ella la escritura denegada no avisa y la promesa queda sin manejar.
    assert re.search(r"\.then\([\s\S]*?\)\s*\.catch\(", guion)
    # El aviso de fallo cubre las dos salidas: la API ausente y la escritura rechazada.
    assert re.search(r"!navigator\.clipboard[\s\S]{0,200}?no se pudo copiar", guion)
    assert re.search(r"\.catch\([\s\S]{0,200}?no se pudo copiar", guion)
