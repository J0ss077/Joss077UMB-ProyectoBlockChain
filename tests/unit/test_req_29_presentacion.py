"""REQ-29: ninguna ruta decide reglas de negocio ni ejecuta consultas.

La presentación habla con la fachada del ledger y con sus objetos, nunca con el
motor: si `src/web/app.py` nombrara `psycopg` o `persistence`, la capa tendría una
decisión de negocio o una consulta propia. La prueba lee el fuente y no importa el
módulo, así que corre sin base de datos (REQ-17).
"""
import pathlib


def test_req_29_la_presentacion_no_importa_persistencia_ni_psycopg():
    """REQ-29: ninguna ruta decide reglas ni ejecuta consultas."""
    fuente = (pathlib.Path("src/web/app.py")).read_text(encoding="utf-8")
    assert "psycopg" not in fuente and "persistence" not in fuente
