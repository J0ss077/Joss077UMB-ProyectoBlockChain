"""REQ-15: el esquema no lo decide el código.

Aquí viven las dos comprobaciones del requisito: que ninguna ruta del código
contiene sentencias de definición de datos, y que el esquema que sí se aplica
—el de `db/init.sql`— tiene las tres tablas del modelo relacional del eje y el
índice único sobre `transactions.signature` de la decisión 4.
"""
import pathlib
import re

from psycopg.rows import dict_row


def test_req_15_no_hay_ddl_en_el_codigo():
    """Ninguna ruta del código contiene sentencias de definición de datos."""
    patron = re.compile(
        r"\b(CREATE|ALTER|DROP)\s+(TABLE|INDEX|EXTENSION|SCHEMA)\b", re.IGNORECASE
    )
    ofensores = [
        str(ruta)
        for ruta in pathlib.Path("src").rglob("*.py")
        if patron.search(ruta.read_text(encoding="utf-8"))
    ]
    assert ofensores == []


def test_req_15_el_esquema_aplicado_tiene_las_tres_tablas_y_el_indice_unico(conexion, base_limpia):
    """El esquema aplicado tiene `wallets`, `blocks` y `transactions`, y `signature` es única."""
    with conexion.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """
        )
        tablas = {fila["table_name"] for fila in cursor.fetchall()}
    assert tablas == {"wallets", "blocks", "transactions"}

    # El catálogo se consulta en vez de reaplicar `db/init.sql`: reaplicarlo
    # sería DDL desde la prueba, que es justo lo que REQ-15 prohíbe.
    with conexion.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND tablename = 'transactions'
              AND indexdef ILIKE '%unique%'
              AND indexdef ILIKE '%(signature)%'
            """
        )
        indices_unicos = cursor.fetchall()
    assert len(indices_unicos) == 1, "hace falta el índice único sobre transactions.signature"
